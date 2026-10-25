"""Check release ZIPs and the isolated background lifecycle without trusting certificates.

Run: python tests/test_word_install.py
No Word profile, login startup, registry or certificate trust is changed.
"""
import importlib.util
from pathlib import Path
import plistlib
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("installer", ROOT / "tools/install_word.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def eventually(predicate, message):
    deadline = time.monotonic() + 10
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(message)
        time.sleep(0.05)


def run():
    subprocess.run([sys.executable, str(ROOT / "tools/build.py")], check=True)
    # Downloaded packages contain complete runtimes and only their platform's entry points.
    for platform, suffix in (("macos", "command"), ("windows", "cmd")):
        with ZipFile(ROOT / "dist" / ("lod-pane-word-" + platform + ".zip")) as archive:
            names = set(archive.namelist())
            for action in ("install", "start", "stop", "status", "uninstall"):
                name = "lod-pane-word/" + action + "-word." + suffix
                assert name in names
                assert ("tools/install_word.py " + action).encode() in archive.read(name)
                if suffix == "command":
                    assert archive.getinfo(name).external_attr >> 16 & 0o111
            assert "lod-pane-word/tools/install_word.py" in names
            assert not any("certificate" in name or name.endswith((".key", ".sqlite3")) for name in names)
            assert "lod-pane-word/install-word." + ("cmd" if suffix == "command" else "command") not in names

    with TemporaryDirectory(prefix="lod installer space ") as temporary:
        directory = Path(temporary) / "installed companion"
        directory.mkdir()
        # A substitute child records starts. No sockets, real data or Office settings are used.
        (directory / "server.py").write_text(
            "from pathlib import Path\nimport time\n"
            "with Path('starts').open('a') as f: f.write('start\\n')\n"
            "while True: time.sleep(0.1)\n")
        runner = [sys.executable, str(ROOT / "tools/install_word.py"), "run", "--install-dir", str(directory)]
        child = subprocess.Popen(runner, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            eventually(lambda: (directory / "starts").is_file(), "supervisor did not launch its child")
            assert installer.running(directory)
            duplicate = subprocess.run(runner, capture_output=True, timeout=10)
            assert duplicate.returncode == 0, duplicate.stderr
            assert (directory / "starts").read_text().splitlines() == ["start"]
            # A stop request ends only the owned child and releases the lock.
            installer.stop(directory)
            stdout, stderr = child.communicate(timeout=10)
            assert child.returncode == 0, (stdout, stderr)
            assert not installer.running(directory)
            assert not (directory / "stop-request").exists()
            installer.stop(directory)  # repeated stop is harmless
        finally:
            if child.poll() is None:
                (directory / "stop-request").touch()
                child.communicate(timeout=10)

        # An occupied companion port is rejected before a second process is launched.
        with patch.object(installer.socket, "socket") as socket_factory:
            socket_factory.return_value.__enter__.return_value.bind.side_effect = OSError("occupied")
            with patch.object(installer.subprocess, "Popen") as spawn:
                try:
                    installer.start(directory)
                    raise AssertionError("occupied port accepted")
                except RuntimeError as error:
                    assert "already in use" in str(error)
                spawn.assert_not_called()

        # Build a LaunchAgent with structured arguments, including paths with spaces.
        with patch.object(installer.sys, "platform", "darwin"), \
             patch.object(installer.Path, "home", return_value=Path(temporary)), \
             patch.object(installer.os, "getuid", return_value=501, create=True), \
             patch.object(installer.subprocess, "run") as run_command:
            installer.login_startup(directory, True)
            plist = Path(temporary) / "Library/LaunchAgents/org.lodpane.word.plist"
            config = plistlib.loads(plist.read_bytes())
            assert config["ProgramArguments"][-1] == str(directory)
            assert config["RunAtLoad"] is True
            assert run_command.call_args.args[0] == ["launchctl", "bootstrap", "gui/501", str(plist)]
            installer.login_startup(directory, False)
            assert not plist.exists()

        # Removing startup must retain vocabulary and shared certificates.
        (directory / "dist").mkdir()
        (directory / "dist/word-manifest.xml").write_text("manifest")
        (directory / "vocabulary.sqlite3").write_text("retained")
        with patch.object(installer, "office_tool") as office, \
             patch.object(installer, "login_startup") as startup:
            installer.uninstall(directory)
            office.assert_called_once_with("office-addin-dev-settings@4.0.1", "unregister", directory / "dist/word-manifest.xml")
            startup.assert_called_once_with(directory, False)
        assert (directory / "vocabulary.sqlite3").read_text() == "retained"
        assert not (directory / "server.py").exists()

        (directory / "dist/word-manifest.xml").write_text("manifest")
        with patch.object(installer, "office_tool", side_effect=RuntimeError("Node unavailable")), \
             patch.object(installer, "login_startup") as startup, patch.object(installer, "stop") as stop:
            try:
                installer.uninstall(directory)
                raise AssertionError("unregister failure hidden")
            except RuntimeError:
                pass
            startup.assert_called_once_with(directory, False)
            stop.assert_called_once_with(directory)
            assert (directory / "dist/word-manifest.xml").exists()

        # Setup copies the complete payload; failed updates restore prior files and state.
        with patch.object(installer, "office_tool") as office, \
             patch.object(installer, "startup_enabled", return_value=False), \
             patch.object(installer, "login_startup"), \
             patch.object(installer, "start"), patch.object(installer, "stop"):
            installer.install(directory)
            assert (directory / "server.py").read_bytes() == (ROOT / "server.py").read_bytes()
            assert office.call_count == 2
        (directory / "server.py").write_text("previous version")
        with patch.object(installer, "office_tool", side_effect=[None, RuntimeError("registration failed"), None]), \
             patch.object(installer, "startup_enabled", return_value=True), \
             patch.object(installer, "login_startup") as startup, \
             patch.object(installer, "start"), patch.object(installer, "stop"):
            try:
                installer.install(directory)
                raise AssertionError("registration error hidden")
            except RuntimeError as error:
                assert "registration failed" in str(error)
            assert (directory / "server.py").read_text() == "previous version"
            assert startup.call_args.args == (directory, True)
            assert (directory / "vocabulary.sqlite3").read_text() == "retained"

        with installer.instance_lock(directory, "management.lock") as acquired:
            assert acquired
            result = subprocess.run([sys.executable, str(ROOT / "tools/install_word.py"), "stop",
                                     "--install-dir", str(directory)], capture_output=True, timeout=10)
            assert result.returncode == 1
            assert b"operation is in progress" in result.stderr

        if sys.platform == "win32":
            # Exercise the real user Run-key branch with a substitute registry handle.
            import winreg
            from unittest.mock import MagicMock
            registry = MagicMock()
            with patch.object(winreg, "CreateKey", return_value=registry), \
                 patch.object(winreg, "SetValueEx") as set_value, \
                 patch.object(winreg, "DeleteValue") as delete_value, \
                 patch.object(installer, "command", return_value=[r"C:\Python\pythonw.exe", r"C:\LOD pane\tools\install_word.py", "run"]):
                installer.login_startup(directory, True)
                assert "install_word.py" in set_value.call_args.args[-1]
                assert '"' in set_value.call_args.args[-1]
                installer.login_startup(directory, False)
                delete_value.assert_called_once()

    print("PASS: platform ZIP contents, supervisor exclusivity/stop, occupied-port rejection, startup configuration, and data-preserving uninstall.")


if __name__ == "__main__":
    run()

"""Install and manage the per-user Word companion on macOS and Windows."""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import plistlib
import shutil
import signal
import socket
import ssl
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.request import urlopen

LABEL = "org.lodpane.word"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
PAYLOAD = ("server.py", "lodpane.py", "SETUP.md", "word/index.html", "word/app.js",
           "word/style.css", "word/icon.png", "dist/word-manifest.xml", "tools/install_word.py")


def default_directory():
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/LOD pane/word-companion"
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "LOD pane/word-companion"


@contextmanager
def instance_lock(directory, name="companion.lock"):
    """Hold one OS-released lock for the supervisor's full lifetime."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / name).open("a+b") as lock:
        # Windows byte locks also deny reads by other handles. Inspect size only.
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            lock.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def running(directory):
    with instance_lock(directory) as acquired:
        return not acquired


def stop(directory):
    if not running(directory):
        return
    (directory / "stop-request").touch()
    deadline = time.monotonic() + 15
    while running(directory):
        if time.monotonic() > deadline:
            raise RuntimeError("Companion did not stop. Check companion.log; no unrelated process was terminated.")
        time.sleep(0.1)


def run_background(directory):
    with instance_lock(directory) as acquired:
        if not acquired:
            return
        stop_requested = False

        def request_stop(signum, frame):
            nonlocal stop_requested
            stop_requested = True

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        with (directory / "companion.log").open("ab") as log:
            # Terminate only this owned child, never a saved PID or process-name match.
            args = ([sys.executable, "serve", "--install-dir", str(directory)] if getattr(sys, "frozen", False)
                    else [sys.executable, "-u", str(directory / "server.py")])
            child = subprocess.Popen(args,
                                     cwd=directory, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            try:
                while child.poll() is None:
                    if stop_requested or (directory / "stop-request").exists():
                        break
                    time.sleep(0.2)
                if child.poll() is not None and child.returncode:
                    raise RuntimeError("Companion exited. See " + str(directory / "companion.log"))
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                (directory / "stop-request").unlink(missing_ok=True)


def background_python():
    executable = Path(sys.executable)
    if sys.platform == "win32":
        pythonw = executable.with_name("pythonw.exe")
        if not pythonw.is_file():
            raise RuntimeError("pythonw.exe is required for background startup. Install Python from python.org.")
        return str(pythonw)
    return str(executable)


def command(directory):
    if getattr(sys, "frozen", False):
        return [sys.executable, "run", "--install-dir", str(directory)]
    args = [background_python(), str(directory / "tools/install_word.py"), "run"]
    if directory != default_directory().resolve():
        args += ["--install-dir", str(directory)]
    return args


def wait_ready(directory):
    # Validate TLS using the same local development certificate, never an unverified context.
    native = getattr(sys, "frozen", False)
    certificate = (directory / "certificates/ca.crt" if native
                   else Path.home() / ".office-addin-dev-certs/ca.crt")
    context = ssl.create_default_context(cafile=str(certificate))
    root = Path(sys._MEIPASS) if native else directory
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with urlopen("https://localhost:43127/word.html", context=context, timeout=1) as response:
                if response.read() == (root / "word/index.html").read_bytes() and running(directory):
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError("Companion did not become ready. Check " + str(directory / "companion.log"))


def start(directory):
    if not getattr(sys, "frozen", False) and not (directory / "server.py").is_file():
        raise RuntimeError("Install the companion first.")
    if not running(directory):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", 43127))
            except OSError:
                raise RuntimeError("Port 43127 is already in use. Close the existing companion and retry.") from None
        (directory / "stop-request").unlink(missing_ok=True)
        with (directory / "companion.log").open("ab") as log:
            subprocess.Popen(command(directory), cwd=directory, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=sys.platform != "win32",
                             creationflags=(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
                             if sys.platform == "win32" else 0)
    wait_ready(directory)


def login_startup(directory, enable):
    if sys.platform == "darwin":
        plist = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")
        target = "gui/" + str(os.getuid())
        # bootout may report that a job isn't loaded; never unload other agents.
        subprocess.run(["launchctl", "bootout", target + "/" + LABEL], capture_output=True)
        if enable:
            plist.parent.mkdir(parents=True, exist_ok=True)
            plist.write_bytes(plistlib.dumps({"Label": LABEL, "ProgramArguments": command(directory),
                "RunAtLoad": True, "StandardOutPath": str(directory / "companion.log"),
                "StandardErrorPath": str(directory / "companion.log")}))
            subprocess.run(["launchctl", "bootstrap", target, str(plist)], check=True)
        else:
            plist.unlink(missing_ok=True)
    else:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if enable:
                value = subprocess.list2cmdline(command(directory))
                if len(value) > 260:
                    raise RuntimeError("Installation path is too long for Windows login startup.")
                winreg.SetValueEx(key, LABEL, 0, winreg.REG_SZ, value)
            else:
                try:
                    winreg.DeleteValue(key, LABEL)
                except FileNotFoundError:
                    pass


def office_tool(package, *args):
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        raise RuntimeError("Install Node.js 22 LTS first, then run setup again. See SETUP.md.")
    invocation = [npx]
    if sys.platform == "win32":
        # Invoke npm's JS entry point directly, avoiding cmd.exe interpretation of paths.
        cli = Path(npx).parent / "node_modules/npm/bin/npx-cli.js"
        node = shutil.which("node")
        if not node or not cli.is_file():
            raise RuntimeError("Cannot locate Node.js npm tools. Install Node.js 22 LTS from nodejs.org.")
        invocation = [node, str(cli)]
    subprocess.run([*invocation, "--yes", package, *map(str, args)], check=True)


def startup_enabled():
    if sys.platform == "darwin":
        return (Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")).is_file()
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, LABEL)
        return True
    except FileNotFoundError:
        return False


def install(directory):
    source = Path(__file__).resolve().parent.parent
    if source == directory:
        raise RuntimeError("Run setup from the extracted download, outside the installed companion folder.")
    if not (source / "dist/word-manifest.xml").is_file():
        from build import main as build
        build()
    for name in PAYLOAD:
        if not (source / name).is_file():
            raise RuntimeError("Missing package file: " + name + ". Extract the entire download before setup.")
    # Trust is explicit through Microsoft's utility; no certificate or policy bypass.
    print("Microsoft's utility will ask to trust a localhost development certificate.")
    office_tool("office-addin-dev-certs@3.0.1", "install")
    manifest = directory / "dist/word-manifest.xml"
    was_enabled, was_running = startup_enabled(), running(directory)
    with TemporaryDirectory(prefix="lod-word-backup-") as backup_dir:
        backup = Path(backup_dir)
        existing = [name for name in PAYLOAD if (directory / name).is_file()]
        for name in existing:
            (backup / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(directory / name, backup / name)
        registered = False
        try:
            stop(directory)
            login_startup(directory, False)
            for name in PAYLOAD:
                target = directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / name, target)
            office_tool("office-addin-dev-settings@4.0.1", "register", manifest)
            registered = True
            login_startup(directory, True)
            start(directory)
        except Exception:
            login_startup(directory, False)
            stop(directory)
            if registered and "dist/word-manifest.xml" not in existing:
                office_tool("office-addin-dev-settings@4.0.1", "unregister", manifest)
            for name in PAYLOAD:
                if name in existing:
                    shutil.copy2(backup / name, directory / name)
                else:
                    (directory / name).unlink(missing_ok=True)
            if "dist/word-manifest.xml" in existing:
                office_tool("office-addin-dev-settings@4.0.1", "register", manifest)
            login_startup(directory, was_enabled)
            if was_running:
                start(directory)
            else:
                stop(directory)
            raise
    print("Installed. The companion runs in the background and starts at sign-in.")
    print("Restart Word, then open Home > Add-ins > LOD pane. Development sideloading must be allowed.")
    print("Installed files and logs: " + str(directory))


def uninstall(directory):
    # Always stop startup/server, even if npm or Office registration is unavailable.
    # Retain the payload on unregister failure so cleanup can be retried.
    login_startup(directory, False)
    stop(directory)
    manifest = directory / "dist/word-manifest.xml"
    if manifest.is_file():
        office_tool("office-addin-dev-settings@4.0.1", "unregister", manifest)
    # Keep the manager available while this process is running, especially on Windows.
    for name in PAYLOAD:
        if name != "tools/install_word.py":
            (directory / name).unlink(missing_ok=True)
    print("Uninstalled startup and manifest. Vocabulary and shared development certificates are retained.")
    print("Logs and the inactive management script remain at " + str(directory))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="install", choices=("install", "start", "stop", "status", "uninstall", "run"))
    parser.add_argument("--install-dir", type=Path, default=default_directory())
    args = parser.parse_args()
    if sys.platform not in ("darwin", "win32"):
        parser.error("Word setup supports macOS and Windows.")
    directory = args.install_dir.expanduser().resolve()
    if sys.version_info < (3, 9):
        parser.error("Python 3.9 or later is required.")
    try:
        if args.action == "status":
            if running(directory):
                wait_ready(directory)
                print("Companion is running and HTTPS is ready.")
            else:
                print("Companion is stopped.")
                return 1
        elif args.action == "run":
            run_background(directory)
        else:
            # Serialize user start/stop/setup actions through startup readiness.
            with instance_lock(directory, "management.lock") as acquired:
                if not acquired:
                    raise RuntimeError("Another setup/start/stop operation is in progress. Retry when it completes.")
                {"install": install, "start": start, "stop": stop, "uninstall": uninstall}[args.action](directory)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print("LOD pane: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

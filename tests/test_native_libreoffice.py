"""Check native LibreOffice setup without opening UI or changing a user profile."""
import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("native_libreoffice", ROOT / "tools/native_libreoffice.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def run():
    package = ROOT / "dist/lod-pane.oxt"
    helper.validate_package(package)
    with TemporaryDirectory(prefix="lod-native-lo-test-") as temporary:
        root = Path(temporary).resolve()
        host = root / "LibreOffice.app/Contents/MacOS/soffice"
        host.parent.mkdir(parents=True)
        host.write_text("test executable")
        assert helper.find_libreoffice(root / "LibreOffice.app") == host
        try:
            helper.find_libreoffice(root / "absent")
            raise AssertionError("missing host accepted")
        except RuntimeError as error:
            assert "not found" in str(error)

        with patch.object(helper.sys, "platform", "darwin"), patch.object(helper.subprocess, "run") as launch:
            helper.open_extension(host, package)
            launch.assert_called_once_with(["open", "-a", str(root / "LibreOffice.app"), str(package)], check=True, timeout=30)
        with patch.object(helper.sys, "platform", "win32"), patch.object(helper.subprocess, "Popen") as launch:
            helper.open_extension(host, package)
            launch.assert_called_once_with([str(host), str(package)], cwd=host.parent)

        profile = root / "isolated profile"
        with patch.object(helper.subprocess, "Popen") as launch:
            helper.open_extension(host, package, profile)
            args = launch.call_args.args[0]
            assert "-env:UserInstallation=" + profile.as_uri() in args
            assert launch.call_args.kwargs["env"]["LOD_PANE_DATA_DIR"] == str(profile / "vocabulary-data")
            try:
                helper.open_extension(host, package, profile)
                raise AssertionError("existing test profile accepted")
            except RuntimeError:
                pass
            assert launch.call_count == 1

        # A frozen self-test validates the bundled OXT and does not locate/start LibreOffice.
        (root / "dist").mkdir()
        (root / "dist/lod-pane.oxt").write_bytes(package.read_bytes())
        with patch.object(helper.sys, "_MEIPASS", str(root), create=True), \
             patch.object(helper.sys, "argv", ["native", "--self-test", "--no-dialog"]), \
             patch.object(helper, "find_libreoffice", side_effect=AssertionError("host discovery in smoke test")), \
             patch.object(helper, "notify", side_effect=AssertionError("dialog in smoke test")):
            assert helper.main() == 0

        bad = root / "bad.oxt"
        with ZipFile(bad, "w") as archive:
            archive.writestr("description.xml", '<description xmlns="http://openoffice.org/extensions/description/2006"><identifier value="unrelated.extension"/></description>')
        try:
            helper.validate_package(bad)
            raise AssertionError("wrong extension accepted")
        except RuntimeError as error:
            assert "identifier" in str(error)
    print("PASS: bundled OXT, host detection, platform launch paths, isolated profile/data handling, and side-effect-free frozen smoke.")


if __name__ == "__main__":
    run()

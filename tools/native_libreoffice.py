"""Native LibreOffice setup: open the bundled OXT in the real Extension Manager."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree
from zipfile import ZipFile

EXTENSION_ID = "org.lodpane.Notebook"


def resources():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def notify(message, question=False):
    if sys.platform == "win32":
        import ctypes
        return ctypes.windll.user32.MessageBoxW(None, message, "LOD pane LibreOffice",
                                                0x24 if question else 0x40) == 6
    script = ('on run argv\ndisplay dialog (item 1 of argv) with title "LOD pane LibreOffice" buttons '
              + ('{"Cancel", "Install"} default button "Install"' if question else '{"OK"} default button "OK"')
              + '\nend run')
    result = subprocess.run(["osascript", "-e", script, message], capture_output=True, text=True)
    if result.returncode and "(-128)" not in result.stderr:
        raise RuntimeError("Could not show setup instructions: " + result.stderr.strip())
    return result.returncode == 0


def host_binary(path):
    path = Path(path).expanduser()
    if path.suffix.lower() == ".app":
        path = path / "Contents/MacOS/soffice"
    elif path.is_dir():
        path = path / "program/soffice.exe"
    return path if path.is_file() else None


def find_libreoffice(explicit=None):
    if explicit is not None:
        found = host_binary(explicit)
        if found is None:
            raise RuntimeError("LibreOffice was not found at the selected path.")
        return found
    candidates = []
    if sys.platform == "darwin":
        candidates = [Path("/Applications/LibreOffice.app"), Path.home() / "Applications/LibreOffice.app"]
    elif sys.platform == "win32":
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\soffice.exe",
                                        0, winreg.KEY_READ | view) as key:
                        candidates.append(Path(winreg.QueryValueEx(key, "")[0].strip('"')))
                except OSError:
                    pass
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            if os.environ.get(variable):
                candidates.append(Path(os.environ[variable]) / "LibreOffice/program/soffice.exe")
    for candidate in candidates:
        found = host_binary(candidate)
        if found is not None:
            return found
    raise RuntimeError("Install LibreOffice 7.4 or later from libreoffice.org first, then run this installer again. For a custom location, use --libreoffice with the LibreOffice app or soffice executable path.")


def validate_package(package):
    with ZipFile(package) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("The bundled extension is damaged. Download the installer again.")
        description = ElementTree.fromstring(archive.read("description.xml"))
        ns = {"d": "http://openoffice.org/extensions/description/2006"}
        if description.find("d:identifier", ns).get("value") != EXTENSION_ID:
            raise RuntimeError("The bundled extension identifier is incorrect.")
        for name in ("panel.py", "pythonpath/lodpane.py"):
            compile(archive.read(name), name, "exec")
        for name in ("META-INF/manifest.xml", "Factory.xcu", "Sidebar.xcu", "panel.component"):
            ElementTree.fromstring(archive.read(name))


def open_extension(host, package, profile=None):
    if profile is not None:
        # Test profiles must be new. Never borrow an existing user's profile or vocabulary.
        profile = profile.expanduser().resolve()
        if profile.exists():
            raise RuntimeError("Test profile already exists; choose a new directory.")
        profile.mkdir(parents=True)
        data = profile / "vocabulary-data"
        data.mkdir()
        environment = dict(os.environ, LOD_PANE_DATA_DIR=str(data))
        subprocess.Popen([str(host), "-env:UserInstallation=" + profile.as_uri(),
                          "--norestore", str(package)], cwd=host.parent, env=environment)
    elif sys.platform == "darwin":
        # macOS's supported app-open path also works when LibreOffice is already running.
        app = next((parent for parent in host.parents if parent.suffix == ".app"), None)
        if app is None:
            raise RuntimeError("Choose the installed LibreOffice.app bundle on macOS.")
        subprocess.run(["open", "-a", str(app), str(package)], check=True, timeout=30)
    else:
        subprocess.Popen([str(host), str(package)], cwd=host.parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libreoffice", type=Path)
    parser.add_argument("--profile-dir", type=Path, help="new disposable test profile only")
    parser.add_argument("--no-dialog", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        package = resources() / "dist/lod-pane.oxt"
        validate_package(package)
        if args.self_test:
            return 0
        if sys.platform not in ("darwin", "win32"):
            raise RuntimeError("Use lod-pane.oxt directly on this platform.")
        host = find_libreoffice(args.libreoffice)
        if not args.no_dialog and not notify(
                "Install or update LOD pane for LibreOffice?\n\nLibreOffice will show its Extension Manager. Confirm Add and choose Only for me if asked, then fully quit and reopen LibreOffice. Open View > Sidebar > LOD pane.\n\nNo server, login startup, or localhost certificate is needed. Extension removal is through Tools > Extensions in LibreOffice.", question=True):
            return 1
        open_extension(host, package, args.profile_dir)
        # Launching the manager is not confirmation that the user installed the OXT.
        return 0
    except Exception as error:
        if args.no_dialog or args.self_test:
            if sys.stderr is not None:
                print(str(error), file=sys.stderr)
        else:
            notify("LOD pane could not open extension setup.\n" + str(error) +
                   "\nYou can also download lod-pane.oxt and add it through Tools > Extensions.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

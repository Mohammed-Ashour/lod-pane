"""Build, trust the development certificate, and sideload Word on macOS."""
from pathlib import Path
import shutil
import subprocess
import sys

from build import main as build


def main():
    if sys.platform not in ("darwin", "win32"):
        raise SystemExit("This setup targets desktop Word on macOS or Windows. For LibreOffice, run python3 tools/build.py.")
    build()
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        raise SystemExit("Install Node.js 22 LTS first, then run this command again. See SETUP.md.")
    print("Microsoft's certificate tool will ask to trust a localhost development certificate.")
    subprocess.run([npx, "--yes", "office-addin-dev-certs@3.0.1", "install"], check=True)
    root = Path(__file__).resolve().parent.parent
    if sys.platform == "darwin":
        target = Path.home() / "Library/Containers/com.microsoft.Word/Data/Documents/wef"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / "dist/word-manifest.xml", target / "lod-pane.xml")
        print("Manifest installed. Restart Word, then Home > Add-ins > LOD pane.")
    else:
        print("Certificate installed. Use the Word sideloading steps in SETUP.md with dist/word-manifest.xml.")
    print("Start the local companion: " + sys.executable + " server.py")


if __name__ == "__main__":
    main()

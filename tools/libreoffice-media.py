#!/usr/bin/env python3
"""Prepare an isolated LibreOffice profile and open a Writer demo.

Run: python3 tools/libreoffice-media.py [--profile-dir /private/tmp/empty-path]
Add the printed OXT through Tools > Extensions. The profile and vocabulary
database are intentionally retained for capture.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
MACOS = Path("/Applications/LibreOffice.app/Contents/MacOS")
MIMETYPE = "application/vnd.oasis.opendocument.text"


def create_demo_document(path):
    content = '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">
 <office:body><office:text>
  <text:h text:outline-level="1">Luxembourgish vocabulary</text:h>
  <text:p>Haut ass d'Wieder schéin.</text:p>
  <text:p>D'Wieder zu Lëtzebuerg ännert sech séier.</text:p>
 </office:text></office:body>
</office:document-content>'''.encode("utf-8")
    manifest = b'''<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
 <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
 <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
 </manifest:manifest>'''
    with ZipFile(path, "w") as document:
        document.writestr("mimetype", MIMETYPE, compress_type=ZIP_STORED)
        document.writestr("content.xml", content, compress_type=ZIP_DEFLATED)
        document.writestr("META-INF/manifest.xml", manifest, compress_type=ZIP_DEFLATED)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--soffice", default=str(MACOS / "soffice"))
    parser.add_argument("--profile-dir", help="new, empty profile path under /private/tmp")
    args = parser.parse_args()

    soffice = Path(args.soffice)
    if not soffice.is_file():
        parser.error("LibreOffice soffice executable does not exist.")

    if args.profile_dir:
        profile = Path(args.profile_dir).expanduser().resolve()
        if profile.exists():
            parser.error("profile path already exists; choose a new path to avoid reusing a profile")
        if not profile.is_relative_to(Path("/private/tmp")):
            parser.error("profile path must be under /private/tmp")
        profile.mkdir(parents=True)
    else:
        profile = Path(mkdtemp(prefix="lod-pane-media-", dir="/private/tmp"))

    package = ROOT / "dist/lod-pane.oxt"
    document = profile / "Writer-demo.odt"
    data = profile / "vocabulary-data"
    data.mkdir()
    create_demo_document(document)
    profile_url = profile.as_uri()
    environment = dict(os.environ, LOD_PANE_DATA_DIR=str(data))
    profile_arg = "-env:UserInstallation=" + profile_url

    subprocess.run([sys.executable, str(ROOT / "tools/build.py")], cwd=ROOT, check=True)
    subprocess.run(
        ["/usr/bin/open", "-n", "-a", str(soffice.parents[2]), "--args", profile_arg,
         "--writer", "--nologo", "--norestore", str(document)],
        cwd=ROOT, env=environment, check=True, timeout=30,
    )
    print("Add this built package through Tools > Extensions:", package)
    print("Isolated profile:", profile)
    print("Isolated vocabulary:", data)
    print("Writer document:", document)
    print("After installation, restart this Writer instance and select Wieder in the first sentence.")


if __name__ == "__main__":
    main()

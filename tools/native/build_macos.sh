#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/../.."

test -f dist/native-build-info.json || {
  echo "Missing dist/native-build-info.json; run tools/native/build_info.py first." >&2
  exit 1
}

python -m pip install pyinstaller==6.16.0 cryptography==43.0.3
mkdir -p dist/native-macos
swiftc -target arm64-apple-macos12.0 -module-cache-path dist/native-swift-cache tools/native/word_folder_access.swift -o dist/native-macos/word-folder-access
codesign --force --sign - dist/native-macos/word-folder-access
dist/native-macos/word-folder-access --self-test
python tests/test_native_word.py
python -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --name LOD-pane-Word \
  --osx-bundle-identifier org.lodpane.word.app \
  --paths . \
  --paths tools \
  --workpath dist/native-build \
  --copy-metadata cryptography \
  --copy-metadata cffi \
  --add-binary "dist/native-macos/word-folder-access:macos" \
  --add-data "word:word" \
  --add-data "SETUP.md:." \
  --add-data "dist/native-build-info.json:." \
  --add-data "dist/word-manifest.xml:dist" \
  tools/native_word.py

python - <<'PY'
from pathlib import Path
import json
import plistlib

info = Path("dist/LOD-pane-Word.app/Contents/Info.plist")
build = json.loads(Path("dist/native-build-info.json").read_text(encoding="utf-8"))
with info.open("rb") as source:
    values = plistlib.load(source)
values["CFBundleVersion"] = build["bundle_version"]
values["CFBundleShortVersionString"] = build["marketing_version"]
values["LODPaneBuildCommit"] = build["commit_sha"]
values["NSAppDataUsageDescription"] = (
    "LOD pane Word needs access to the Word add-in folder you select to install "
    "or remove its manifest."
)
with info.open("wb") as target:
    plistlib.dump(values, target)
PY
python tools/native/copy_licenses.py dist/LOD-pane-Word.app/Contents/Resources
codesign --force --deep --sign - dist/LOD-pane-Word.app
if ! dist/LOD-pane-Word.app/Contents/MacOS/LOD-pane-Word --self-test --no-dialog; then
  diagnostics="$(python -c 'import tempfile; print(tempfile.gettempdir())')/lod-native-smoke-diagnostics/companion.log"
  if [[ -f "$diagnostics" ]]; then cat "$diagnostics"; fi
  exit 1
fi

python tools/native/package_macos.py \
  --app dist/LOD-pane-Word.app \
  --output dist/lod-pane-word-macos-arm64.pkg \
  --package-identifier org.lodpane.word.app \
  --bundle-identifier org.lodpane.word.app

python tests/test_native_libreoffice.py
python -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --name LOD-pane-LibreOffice \
  --osx-bundle-identifier org.lodpane.libreoffice.app \
  --paths . \
  --paths tools \
  --workpath dist/native-build-libreoffice \
  --add-data "dist/lod-pane.oxt:dist" \
  --add-data "dist/native-build-info.json:." \
  tools/native_libreoffice.py

python - <<'PY'
from pathlib import Path
import json
import plistlib

info = Path("dist/LOD-pane-LibreOffice.app/Contents/Info.plist")
build = json.loads(Path("dist/native-build-info.json").read_text(encoding="utf-8"))
with info.open("rb") as source:
    values = plistlib.load(source)
values["CFBundleVersion"] = build["bundle_version"]
values["CFBundleShortVersionString"] = build["marketing_version"]
values["LODPaneBuildCommit"] = build["commit_sha"]
with info.open("wb") as target:
    plistlib.dump(values, target)
PY
python tools/native/copy_licenses.py dist/LOD-pane-LibreOffice.app/Contents/Resources
codesign --force --deep --sign - dist/LOD-pane-LibreOffice.app
dist/LOD-pane-LibreOffice.app/Contents/MacOS/LOD-pane-LibreOffice --self-test --no-dialog

python tools/native/package_macos.py \
  --app dist/LOD-pane-LibreOffice.app \
  --output dist/lod-pane-libreoffice-macos-arm64.pkg \
  --package-identifier org.lodpane.libreoffice.app \
  --bundle-identifier org.lodpane.libreoffice.app

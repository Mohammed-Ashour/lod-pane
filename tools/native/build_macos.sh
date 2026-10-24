#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/../.."

python -m pip install pyinstaller==6.16.0 cryptography==43.0.3
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
  --add-data "word:word" \
  --add-data "SETUP.md:." \
  --add-data "dist/word-manifest.xml:dist" \
  tools/native_word.py

python tools/native/copy_licenses.py dist/LOD-pane-Word.app/Contents/Resources
codesign --force --deep --sign - dist/LOD-pane-Word.app
if ! dist/LOD-pane-Word.app/Contents/MacOS/LOD-pane-Word --self-test --no-dialog; then
  diagnostics="$(python -c 'import tempfile; print(tempfile.gettempdir())')/lod-native-smoke-diagnostics/companion.log"
  if [[ -f "$diagnostics" ]]; then cat "$diagnostics"; fi
  exit 1
fi

pkgbuild \
  --component dist/LOD-pane-Word.app \
  --install-location /Applications \
  --identifier org.lodpane.word.app \
  --version 0.7.0 \
  dist/lod-pane-word-macos-arm64.pkg

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
  tools/native_libreoffice.py

python tools/native/copy_licenses.py dist/LOD-pane-LibreOffice.app/Contents/Resources
codesign --force --deep --sign - dist/LOD-pane-LibreOffice.app
dist/LOD-pane-LibreOffice.app/Contents/MacOS/LOD-pane-LibreOffice --self-test --no-dialog

pkgbuild \
  --component dist/LOD-pane-LibreOffice.app \
  --install-location /Applications \
  --identifier org.lodpane.libreoffice.app \
  --version 0.7.0 \
  dist/lod-pane-libreoffice-macos-arm64.pkg

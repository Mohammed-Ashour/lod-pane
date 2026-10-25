# README captures

LibreOffice captures refreshed on 2026-10-25. Word previews are from 2026-10-24.

## LibreOffice

`libreoffice-install.png` shows LOD pane 0.8.0 enabled in the real Extension
Manager. `libreoffice-usage.png` shows the installed sidebar in LibreOffice
26.8.1.1 on macOS, with `Wieder` selected and live LOD results visible.

The GIF and WebM are an eight-second, 1920-pixel-wide step animation assembled
from five real window screenshots, rather than a continuous screen recording. The sequence
shows lookup, the meaning chooser, a second meaning, a Favorites save, and the
saved list. No host frame or dictionary result was fabricated.

To prepare another disposable capture session on macOS:

```sh
python3 tools/libreoffice-media.py
```

The helper prints the new profile, vocabulary folder, document, and OXT paths.
Install the OXT through that instance's Extension Manager and restart it. Verify
the process uses the printed `UserInstallation` and `LOD_PANE_DATA_DIR` before
saving vocabulary. Capture that window through the native UI. The helper retains
the disposable folder for inspection and does not automate capture or cleanup.

This smoke check covered live selection lookup, meaning/example changes,
Favorites saving, reopening Saved, and light/dark rendering. Native regression
tests also cover the 272-pixel inner viewport left after the deck adds its scrollbar. This does
not complete the acceptance checklist in `SETUP.md`.

## Word

The Word images use the production task-pane code with fixture LOD responses
and an Office.js stub. They are UI previews, not real Word acceptance evidence.

Regenerate with Playwright, Chrome, OpenSSL, ffmpeg, and ffprobe available:

```sh
PLAYWRIGHT_MODULE=/path/to/playwright node tests/readme-media.cjs
```

Use `LOD_TEST_PORT` if port 43127 is occupied. The harness uses an isolated
vocabulary folder and removes its fixture server and temporary files on exit.

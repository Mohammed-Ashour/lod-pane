# LOD pane

LOD pane is a reading-first dictionary for Luxembourgish. Select a word in
Microsoft Word or LibreOffice Writer, read its meaning and example, and save it
to a local vocabulary notebook.

This is an early implementation. The LibreOffice extension and the Word task
pane still need acceptance testing in the real applications. The project is not
an official LOD product.

## What it does

- Looks up Luxembourgish words through the LOD API.
- Keeps distinct meanings separate and shows English, French, or German translations.
- Saves notes, an optional nearby paragraph, and a Study or Favorites destination in local SQLite.
- Replaces a selected word with its LOD headword, but only after a preview and confirmation.
- Works without an account, analytics, or cloud sync.

Only the lookup word or dictionary ID goes to LOD. Notes and document excerpts
stay in the local database.

## Quick start

Python 3.9 or later is required. LibreOffice 7.4 or later must include Python
UNO support.

### LibreOffice Writer

```sh
python3 tools/build.py
```

Install `dist/lod-pane.oxt` through **Tools > Extensions**, restart LibreOffice,
then open **View > Sidebar > LOD pane**. Writer does not need Node or a server.

### Microsoft Word

Word currently needs the local HTTPS companion and a trusted development
certificate:

```sh
npx --yes office-addin-dev-certs install
python3 tools/build.py
python3 server.py
```

Keep the companion running and upload `dist/word-manifest.xml` through
**Home > Add-ins > More Settings > Upload My Add-in**. Desktop Word has
additional sideloading routes in [SETUP.md](SETUP.md).

The manifest requests `ReadWriteDocument` because replacement is an explicit
feature. Lookup, saving vocabulary, and Home do not edit the document.

## Project layout

```text
lodpane.py             LOD parsing, validation, and SQLite storage
server.py              loopback HTTPS API for the Word pane
word/                  Word task pane: HTML, CSS, Office.js
libreoffice/panel.py   native LibreOffice Writer sidebar
tools/                 package build and host setup helpers
tests/                 fixture-backed runtime and package checks
docs/agdr/             architecture decision records
```

The runtime uses only the Python standard library. The Word pane is plain
HTML, CSS, and JavaScript.

## Checks

The core suite needs only Python and does not call the live LOD service:

```sh
python3 tests/test_runtime.py
python3 -m py_compile lodpane.py server.py tools/*.py tests/*.py
node --check word/app.js
```

Optional host checks:

```sh
python3 tests/libreoffice-runtime.py [--soffice /path/to/soffice]
```

This runs the real UNO panel in a disposable LibreOffice profile. It requires a
local LibreOffice installation.

The Playwright checks require Google Chrome, OpenSSL, and Playwright:

```sh
npm install --prefix /tmp/lod-pane-browser-tests playwright
PLAYWRIGHT_MODULE=/tmp/lod-pane-browser-tests/node_modules/playwright \
  node tests/word-runtime.cjs
```

They use port `43127`, replace LOD with fixtures, and stub the Office
JavaScript boundary. They do not prove that the add-in works in real Word.

## Documentation

- [Setup and host installation](SETUP.md)
- [Architecture](ARCHITECTURE.md)
- [Decision records](docs/agdr/)
- [Original prototype gallery](prototypes.html)
- [Learner prototype gallery](learner-prototypes.html)

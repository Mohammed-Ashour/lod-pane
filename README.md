# LOD pane

LOD pane is a reading-first dictionary for Luxembourgish. Select a word in
Microsoft Word or LibreOffice Writer, read its meaning and example, and save it
to a local vocabulary notebook.

This is an early implementation. Lookup, meaning changes, and vocabulary saving
have been checked in the installed LibreOffice sidebar on macOS. The full
acceptance checklist and real Word testing remain open. This is not an official
LOD product.

## Demo

### LibreOffice Writer

[![Writer lookup, meaning selection, and Favorites save](docs/media/libreoffice-demo.gif)](docs/media/libreoffice-demo.webm)

This step animation uses screenshots from the installed native sidebar with live
LOD results and an isolated vocabulary database.

![Selected word and live dictionary result in Writer](docs/media/libreoffice-usage.png)

### Word task-pane preview

[![Short Word task pane demo](docs/media/word-demo.gif)](docs/media/word-demo.webm)

The Word captures use the real task-pane code with a fixture dictionary and an
Office.js boundary stub. They are product previews, not evidence of real Word
acceptance.

## How it works

### Look up a selected word

Select a Luxembourgish word in the document. The pane opens its LOD meaning,
grammar, example, and separate senses when the entry has more than one.

<img src="docs/media/word-lookup.png" width="336" alt="Word task pane showing the Luxembourgish word Wieder, its grammar, meaning, and example">

### Add a note and document excerpt

Notes stay hidden until requested or saved. A document excerpt is optional,
limited to 1,000 characters, and kept around the selected word.

<img src="docs/media/word-note-context.png" width="336" alt="Word task pane with a personal note and document excerpt open">

### Save and revisit vocabulary

Save a meaning to Study or Favorites, then search, edit, remove, or export the
local vocabulary.

<img src="docs/media/word-saved.png" width="336" alt="Saved vocabulary view with a word, translation, note, and document excerpt">

### Preview a replacement

Replacement uses the LOD headword, not a translation. Nothing changes until the
preview is confirmed, and the host's normal Undo remains available.

<img src="docs/media/word-replace.png" width="336" alt="Replacement preview showing the selected word and the LOD headword">

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

<img src="docs/media/libreoffice-install.png" width="588" alt="LibreOffice Extension Manager showing LOD pane 0.7.0 enabled">

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

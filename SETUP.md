# Setup

LOD pane has two hosts:

- LibreOffice Writer uses a native UNO sidebar and needs no server.
- Microsoft Word uses a local HTTPS companion and Office.js.

This is a development setup. Real Word and rendered Writer acceptance still
need to be completed before daily use.

## Requirements

| Component | Requirement |
| --- | --- |
| Core and package build | Python 3.9 or later |
| LibreOffice Writer | LibreOffice 7.4 or later with Python UNO support |
| Word companion | Node.js 22 LTS for certificate setup |
| Browser checks | Google Chrome, OpenSSL, Playwright |

Linux distributions may package UNO support separately as `python3-uno`.
Sandboxed or store editions of LibreOffice are not covered.

## Build

From the repository root:

```sh
python3 tools/build.py
```

The build creates the following ignored development artifacts:

```text
dist/lod-pane.oxt
dist/word-manifest.xml
dist/start-word.command
dist/start-word.cmd
```

It also writes `word/icon.png`, which the Word pane uses.

## LibreOffice Writer

1. Run `python3 tools/build.py`.
2. Open **Tools > Extensions** or **Tools > Extension Manager**.
3. Remove an older LOD pane installation if one exists.
4. Add `dist/lod-pane.oxt`.
5. Quit LibreOffice completely, reopen Writer, then choose **View > Sidebar > LOD pane**.
6. Open Settings and confirm the extension reports `v0.7.0`.

Do not lower macro security or enable a UNO network listener. The sidebar is a
registered extension, not a document macro.

## Microsoft Word

### 1. Trust a localhost certificate

```sh
npx --yes office-addin-dev-certs install
```

Follow the certificate utility's prompts. Do not disable certificate checks or
an organization security policy.

### 2. Build and start the companion

```sh
python3 tools/build.py
python3 server.py
```

The companion binds to `127.0.0.1:43127` and serves the pane at
`https://localhost:43127/word.html`. Keep it running while you use Word.

### 3. Install the manifest

Word on the web:

1. Open a document and choose **Home > Add-ins > More Settings > Upload My Add-in**.
2. Select `dist/word-manifest.xml`.
3. Open the pane's Settings and confirm that it follows the Word selection.

Desktop Word on macOS:

1. Copy `dist/word-manifest.xml` to
   `~/Library/Containers/com.microsoft.Word/Data/Documents/wef/lod-pane.xml`.
2. Restart Word and open **Home > Add-ins > LOD pane**.

Desktop Word on Windows:

1. Share the `dist` folder with your Windows user and note its UNC path.
2. In Word, open **File > Options > Trust Center > Trust Center Settings > Trusted Add-in Catalogs**.
3. Add the shared folder as a catalog, enable **Show in Menu**, and restart Word.
4. Open **Home > Add-ins > Get Add-ins > Shared Folder** and choose **LOD pane**.

If sideloading or local network access is blocked, ask your administrator.
Do not bypass the policy.

## Data

Both hosts use `vocabulary.sqlite3` when they run as the same OS user:

| OS | Folder |
| --- | --- |
| macOS | `~/Library/Application Support/LOD pane/` |
| Windows | `%LOCALAPPDATA%\LOD pane\` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/lod-pane/` |

Set `LOD_PANE_DATA_DIR` to isolate tests or development runs. Close the hosts
before copying the database. Export JSON from the pane for a portable snapshot.
Removing the host integration does not delete the database.

## Verification

Run the core suite before changing the project:

```sh
python3 tests/test_runtime.py
```

It checks parsing, validation, SQLite persistence, HTTP boundaries, and both
package formats without calling the live LOD service.

Run the optional native and browser checks when their dependencies are
available:

```sh
python3 tests/libreoffice-runtime.py [--soffice /path/to/soffice]
npm install --prefix /tmp/lod-pane-browser-tests playwright
PLAYWRIGHT_MODULE=/tmp/lod-pane-browser-tests/node_modules/playwright \
  node tests/word-runtime.cjs
```

The native check uses a disposable LibreOffice profile. The browser check uses
a fixture dictionary and an Office.js stub. Neither is proof of real host
acceptance.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Word pane is blank | Start `python3 server.py`, confirm the development certificate, and check local-network policy. |
| Word add-in is missing | Restart Word and verify the manifest location or catalog. |
| Writer sidebar is blank | Reinstall the extension, fully restart LibreOffice, and inspect `panel-error.log` in the data folder. |
| Writer shows an old layout | Remove the cached extension and confirm `v0.7.0` in Settings. |
| LOD lookup fails | Check internet access, retry, or open Saved to use a saved entry. |
| HTTPS certificate error | Use the approved CA bundle through `SSL_CERT_FILE`; do not disable verification. |
| Replacement is rejected | Select one word in an editable document and reopen the preview. |
| Save fails | Keep the draft, check disk permissions and companion availability, then retry. |

## Before daily use

In both hosts, test:

1. Lookup for `Wieder`, `fläisseg`, and `heem`, including ambiguous entries.
2. Notes, theme changes, language changes, and Study/Favorites saves.
3. Separate meanings for `Wieder`, then reload persistence and export.
4. Offline access to saved entries.
5. Replacement preview, no-op before confirmation, one-step Undo, moved selection, and read-only documents.
6. Keyboard navigation, screen-reader output, long text, resizing, and both themes.

Official references:

- [Sideload Office Add-ins for testing](https://learn.microsoft.com/en-us/office/dev/add-ins/testing/sideload-office-add-ins-for-testing)
- [Sideload an Office Add-in on Mac](https://learn.microsoft.com/en-us/office/dev/add-ins/testing/sideload-an-office-add-in-on-mac)
- [Create a network shared folder catalog](https://learn.microsoft.com/en-us/office/dev/add-ins/testing/create-a-network-shared-folder-catalog-for-task-pane-and-content-add-ins)
- [LibreOffice Python tool panel example](https://api.libreoffice.org/examples/python/toolpanel/)

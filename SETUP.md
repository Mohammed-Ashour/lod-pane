# Setup

LOD pane has two hosts:

- LibreOffice Writer uses a native UNO sidebar and needs no server.
- Microsoft Word uses a local HTTPS companion and Office.js.

This is a development setup. The installed Writer sidebar has passed a macOS
smoke check for live lookup, meaning changes, and saving. Complete the checklist
below before daily use. Real Word remains unverified.

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

For installation, download the `.oxt` or your platform's Word ZIP from
[GitHub Releases](https://github.com/Mohammed-Ashour/lod-pane/releases).
You do not need a source checkout or build. The repository is private; downloads
require repository access.

To build from source instead:

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
dist/lod-pane-word-macos.zip
dist/lod-pane-word-windows.zip
dist/lod-pane-word.zip
dist/SHA256SUMS
```

It also writes `word/icon.png`, which the Word pane uses.

## LibreOffice Writer

1. Download `lod-pane.oxt` from the release, or run `python3 tools/build.py`.
2. Open **Tools > Extensions** or **Tools > Extension Manager**.
3. Remove an older LOD pane installation if one exists.
4. Add the downloaded `lod-pane.oxt`, or `dist/lod-pane.oxt` from a source build.
5. Quit LibreOffice completely, reopen Writer, then choose **View > Sidebar > LOD pane**.
6. Open Settings and confirm the extension reports `v0.7.0`.

Do not lower macro security or enable a UNO network listener. The sidebar is a
registered extension, not a document macro.

## Microsoft Word

### Installer scripts for macOS and Windows

1. Install Python 3.9+ from [python.org](https://www.python.org/downloads/) and
   Node.js 22 LTS from [nodejs.org](https://nodejs.org/). On Windows, include the
   Python launcher and `pythonw.exe`.
2. Download and extract `lod-pane-word-macos.zip` or `lod-pane-word-windows.zip`.
3. Close Word. Run `install-word.command` on macOS or `install-word.cmd` on
   Windows. Follow Microsoft's localhost certificate trust prompts.
4. Restart Word and open **Home > Add-ins > LOD pane**.

Setup copies the companion into your application-data folder, registers the
manifest using Microsoft's `office-addin-dev-settings`, and starts the HTTPS
server in the background. It starts again at sign-in through a per-user macOS
LaunchAgent or Windows Run entry. No terminal needs to stay open. Development
sideloading must be permitted by your Word installation and organization.

The download includes matching `start-word`, `stop-word`, `status-word`, and
`uninstall-word` scripts. Stop affects the current session; uninstall removes
login startup and manifest registration. Vocabulary and the shared Microsoft
development certificates are retained. Re-running setup updates the installed
files; failed updates attempt to restore the previous files and startup state.

| OS | Installed files and `companion.log` |
| --- | --- |
| macOS | `~/Library/Application Support/LOD pane/word-companion/` |
| Windows | `%LOCALAPPDATA%\LOD pane\word-companion\` |

The management script also remains in `tools/install_word.py` under that folder.
Run it with `start`, `stop`, `status`, or `uninstall` if you removed the download.
Keep Python installed, because login startup records its absolute executable
path. After moving or upgrading Python, run setup again.

These are script installers, not signed `.pkg` or `.exe` packages. The tests
exercise isolated lifecycle behavior and mock Office/startup settings; they do
not establish real Word acceptance. If OS or organization policy blocks setup,
use an approved deployment route rather than bypassing the policy.

### Manual setup

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
| Installed Word companion is unavailable | Run `status-word`, inspect `companion.log`, then run `start-word`. Re-run setup if Python moved or the certificate expired. |
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

- [Microsoft Office add-in development tooling](https://github.com/OfficeDev/Office-Addin-Scripts)
- [macOS launch agents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
- [Windows login Run entries](https://learn.microsoft.com/en-us/windows/win32/setupapi/run-and-runonce-registry-keys)
- [Sideload Office Add-ins for testing](https://learn.microsoft.com/en-us/office/dev/add-ins/testing/sideload-office-add-ins-for-testing)
- [Sideload an Office Add-in on Mac](https://learn.microsoft.com/en-us/office/dev/add-ins/testing/sideload-an-office-add-in-on-mac)
- [Create a network shared folder catalog](https://learn.microsoft.com/en-us/office/dev/add-ins/testing/create-a-network-shared-folder-catalog-for-task-pane-and-content-add-ins)
- [LibreOffice Python tool panel example](https://api.libreoffice.org/examples/python/toolpanel/)

---
id: AgDR-0012
timestamp: 2026-10-24T18:00:00Z
agent: codex
model: gpt-6.1-sol
trigger: user-prompt
status: executed
---

# Native LibreOffice extension installers

> In the context of downloadable Word installers, facing the same request for LibreOffice, I decided to package a separate native helper around LibreOffice's extension manager to install the bundled OXT for the current user, accepting a final Add confirmation in the real Extension Manager.

## Context

- Writer uses a native UNO extension and does not need Word's server, certificate trust or login startup.
- `tools/build.py` already creates `dist/lod-pane.oxt`.
- macOS PKG and Windows EXE builds already exist for Word.

## Options considered

| Option | Benefit | Cost |
| --- | --- | --- |
| Separate native helper using LibreOffice's own extension tools | Reuses the supported OXT installation format; no host-profile file copying or server setup | Needs an installed LibreOffice; CLI failures require a clear Extension Manager fallback |
| Copy extension files into the user's profile | Avoids launching the extension tool | Bypasses registration, locking and validation; depends on internal profile layout |
| Keep only the OXT download | Already works through Extension Manager | Does not provide the requested native installer experience |

## Decision

Use a dedicated frozen helper and native packages because LibreOffice needs only extension registration. A fresh disposable-profile test of unopkg add timed out on macOS on 2026-10-24, even after profile initialization and using the host program directory. Use LibreOffice's documented OXT-open flow instead. Detect the installed host and open the bundled OXT directly in its real Extension Manager. Tell the user to confirm Add and restart Writer; never report that opening the dialog installed the extension.

Use per-user registration only. Never modify macro security, create a UNO listener, trust certificates, start a companion service, or terminate user documents. Test against disposable profiles and retain the raw OXT as a manual alternative. Package builds and checksums remain gated by successful main CI.

## Consequences

- End users need LibreOffice but no separate Python or Node.js installation.
- A bundled helper opens install/update confirmation; Writer owns extension registration, removal and persistence. Removing the native helper does not remove the extension.
- The native preview remains unsigned; the existing per-download macOS approval instructions also apply.
- Real GUI confirmation remains distinct from frozen helper and isolated-profile tests.

## Artifacts

- `tools/native_libreoffice.py`, native packaging scripts, release workflow
- Installer tests, `SETUP.md`, `README.md`, `ARCHITECTURE.md`

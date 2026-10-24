---
id: AgDR-0013
timestamp: 2026-10-24T18:00:00Z
agent: codex
model: gpt-6.1-sol
trigger: user-prompt
status: executed
---

# Explicit access to Word's protected add-in folder

> In the context of a real macOS installation failing with EPERM on Word's container Documents/wef folder, facing OS app-data protection, I decided to request a folder-scoped grant through NSOpenPanel and perform manifest operations in that granted process, accepting a folder-selection step during setup and removal.

## Context

- The user's photo confirms `[Errno 1] Operation not permitted` at `~/Library/Containers/com.microsoft.Word/Data/Documents/wef`.
- The current helper writes directly into that protected container. Frozen smoke tests did not exercise this privacy boundary.
- Apple's documented file picker provides access to user-selected resources without requiring Full Disk Access.

## Options considered

| Option | Benefit | Cost |
| --- | --- | --- |
| Request Full Disk Access for the entire app | Allows direct container access | Much broader access than a single add-in manifest needs |
| Require a manual Finder copy of the manifest | Explicit user action; no additional helper | Does not meet automated setup expectations and complicates repair/uninstall |
| Native folder picker and a bounded manifest helper | User grants access to Word's Documents/wef folder only; supports verified registration and rollback | Adds a small Swift/AppKit helper to the macOS build |

## Decision

Use a small Swift helper because it can own the NSOpenPanel grant and all protected manifest operations in the same process. Accept only Word's exact Documents folder or its wef child. Expose a fixed protocol for snapshot/write/remove/restore of `wef/lod-pane.xml`, with no arbitrary file names or folder paths. Keep the helper alive for one setup transaction so rollback uses the same grant. Never request Full Disk Access or change privacy databases.

The Python companion receives only manifest snapshots and operation results. Background lookup/server processes never access Word's container or prompt for this grant. Windows registration is unchanged. Add an explanatory App Data usage string to the app, test the helper protocol against temporary files, and distinguish tests from real remote Word acceptance.

## Consequences

- Users select the Word add-in folder during installation and removal.
- Cancelling selection must leave registration and the existing companion unchanged.
- The helper exits after the transaction and releases the scoped resource; no persistent broad grant or stored bookmark is needed.
- Tests now cover the protected-folder integration boundary with a substitute session and the compiled helper's isolated filesystem self-test.

## Artifacts

- `tools/native/word_folder_access.swift`, `tools/native_word.py`, macOS packaging
- Installer tests, `SETUP.md`, `ARCHITECTURE.md`

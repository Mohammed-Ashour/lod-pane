---
id: AgDR-0009
timestamp: 2026-10-18T10:46:54Z
agent: pi
model: gpt-6.1-sol
trigger: user-prompt
status: executed
---

# Selection replacement and Home

> In the context of the Word and Writer dictionary panes, facing a request to replace selected document text and return home easily, I decided to add an explicit headword replacement preview backed by a captured document range and a persistent Home action, accepting Word's additional document-write permission and host-specific editing code.

## Context
- The user approved adding replacement after being told it would be explicit, selection-checked and undoable. The default replacement is the Luxembourgish LOD headword, not an automatically chosen translation or inflection.
- The core, API and vocabulary storage must not edit documents or receive replacement previews. Editing belongs to the two host UIs.
- Word currently has ReadDocument permission. Writer already has a native document controller and uses standard buttons.

## Options considered

| Option | Benefit | Cost |
| --- | --- | --- |
| Replace the current selection after comparing its text only | Less code | Can edit another occurrence of the same word after the selection moves |
| Preview a captured range, then check text and location before replacing | Rejects stale/different selections, including duplicate words; supports native Undo | Tracked Word range lifecycle and native Writer range comparison |

## Decision

Use an explicit preview and captured range because text equality alone does not identify the selection. Capture the currently selected single word when the user opens the preview, show the exact before/after text, preserve surrounding whitespace, and replace only after confirmation. Use tracked Word ranges and compareLocationWith; use Writer text cursors and range comparison. Writer groups the edit through its UndoManager; Word uses normal insertText replacement and the host's Undo. Reject empty, changed, different-location or read-only selections; never use a global search/replace.

Home is a visible header action in both UIs. It cancels pending lookups, closes transient replacement/settings/meaning UI, clears the current result and focuses search. It retains in-memory notes and saved vocabulary. Back from Saved remains distinct from Home.

## Consequences
- The Word manifest moves to ReadWriteDocument and a new manifest version. Existing installations must re-upload/accept the new permission. No edits happen merely from selection, lookup, saving, or Home.
- Replacement is the dictionary headword. No automatic translation or grammatical inflection is inferred. The preview warns users to check the headword's grammar.
- A stale preview is rejected and must be reopened. Tracked Word ranges are released when previews close, results change, Home is used, or an edit completes.
- Real Word remains unverified. Native probes use an isolated profile/document, not the user's open documents. Do not claim real-host acceptance from the browser stub or isolated native host.

## Artifacts
- `word/index.html`, `word/style.css`, `word/app.js`
- `libreoffice/panel.py`, `tools/build.py`
- `tests/test_runtime.py`, `tests/word-runtime.cjs`, `tests/libreoffice-runtime.py`
- `ARCHITECTURE.md`, `README.md`, `SETUP.md`

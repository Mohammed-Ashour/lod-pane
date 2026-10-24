---
id: AgDR-0008
timestamp: 2026-10-18T10:25:29Z
agent: pi
model: gpt-6.1-sol
trigger: user-prompt
status: executed
---

# Native Writer actions

> In the context of repeated click failures in Writer's actual sidebar, facing custom hyperlink mouse filters that passed synthetic dialog tests but failed for the user, I decided to use native UNO buttons and their action events for all actions and choices, accepting platform button styling instead of a guaranteed flat appearance.

## Context
- Read-only inspection confirms that the installed extension is v0.6.1. This is not merely an older package in the extension cache.
- v0.6.1 requires mouseReleased.Buttons == 1 and ClickCount == 1. Its robot tests supplied those exact values. That does not establish compatibility with real sidebar mouse events.
- Save already uses a standard native button. The existing core, storage, labelled meaning choices and per-sense drafts need no redesign.

## Options considered

| Option | Benefit | Cost |
| --- | --- | --- |
| Expand the hyperlink mouse filter to track press/release variants | Preserves the flat look | Still implements button behavior manually and needs platform event evidence |
| Use native buttons and XActionListener for all actions | Delegates activation, focus and keyboard behavior to LibreOffice; removes the mouse filter | Native platform styling, including button borders |

## Decision

Use native buttons because repeated failures make activation reliability more important than the flat-control workaround. Use native toggle buttons for mutually exclusive choices, repainting their selected state from panel state. Remove custom mouse listeners and explicit Enter/Space activation for those controls, avoiding duplicate dispatch with native button behavior. Keep Enter in search and Escape handling.

## Consequences
- This supersedes AgDR-0005 and AgDR-0007's use of clickable text/hyperlinks for actions. Meaning labels, pagination and example fixes remain.
- Tests must exercise mouse and keyboard activation of actual native button peers, selected toggle state, the Moien regression, and drafts. Tests in a separate dialog are not proof of actual-sidebar compatibility.
- The current environment has not yet reproduced the user's physical mouse events in the installed sidebar. Do not claim the real-host issue resolved from the isolated probe alone.

## Artifacts
- `libreoffice/panel.py`, `tools/build.py`, `dist/lod-pane.oxt`
- `tests/libreoffice-runtime.py`
- `ARCHITECTURE.md`, `README.md`, `SETUP.md`

---
id: AgDR-0006
timestamp: 2026-10-18T09:44:17Z
agent: pi
model: gpt-6.1-sol
session: 01a14e61-cf73-7105-8742-0d3583a2bb9d
trigger: user-prompt
status: executed
---

# Reading-first pane

> In the context of the Word and Writer dictionary panes, facing a crowded lookup screen and mouse-only Writer actions, I decided to retain the existing runtimes and palette while introducing optional note/context disclosures and native interactive controls, accepting an extra action to annotate a word and platform styling on Writer's primary button.

## Context
- The user approved the UI/UX review and a reading-first redesign.
- Word uses plain HTML/CSS/Office.js; Writer uses UNO controls. Dictionary parsing and persistence must remain unchanged.
- The previous flat FixedText actions cannot receive keyboard focus or expose actionable accessibility roles.
- The current Word source calls the loopback API for vocabulary. Documentation about browser storage does not describe this implementation; this change must not silently migrate storage.

## Options considered

| Option | Pros | Cons |
| --- | --- | --- |
| Restyle the existing form and FixedText actions | Smallest visual change | Keeps optional fields crowded and Writer inaccessible |
| Disclosures and native interactive controls in each host | Keeps installation and data contracts; native keyboard/accessibility support | Host-specific UI code; primary Writer button retains native styling |
| Replace Writer with an embedded web UI | Could share web layout | New runtime and packaging dependencies; much broader than the UI task |

## Decision

Chosen: disclosures and native interactive controls, because they reduce routine lookup effort without changing the core or adding a framework. Keep white/navy/teal, the host UI font for controls, and Georgia for headwords. Use HTML details in Word, native hyperlinks for secondary Writer actions, a native button for Save, and native lists for language and meanings. Use the controls' native text measurement rather than fixed entry text heights. Make every saved word reachable through filtering and pagination. Keep drafts per sense and automatically reveal existing notes/context.

## Consequences
- This supersedes AgDR-0005's mouse-only FixedText approach. Secondary Writer actions have link semantics, not fabricated button semantics.
- Word keeps its pinned save footer. Writer continues to use the host sidebar's scrolling contract; a separate custom scrolling system is outside this pass.
- Real Word and rendered Writer appearance still require host acceptance. The initial native probe reported a pass, but later investigation found that its Basic assertion path could report success despite failed checks. AgDR-0007 corrects that harness, tests native input in a separate dialog, and withdraws the earlier accessibility-role verification claim. Browser checks and light/dark screenshots used an Office boundary stub. Screen-reader behavior remains unverified.
- Vocabulary continues through the existing API/SQLite boundary. Correct user-facing storage copy and documentation to describe that runtime; do not promise browser storage or deployed hosting that is absent from the source.

## Artifacts
- `word/index.html`, `word/style.css`, `word/app.js`
- `libreoffice/panel.py`
- `tests/word-runtime.cjs`, `tests/libreoffice-runtime.py`
- `README.md`, `SETUP.md`, `ARCHITECTURE.md`

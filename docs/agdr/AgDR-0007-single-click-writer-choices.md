---
id: AgDR-0007
timestamp: 2026-10-18T10:07:24Z
agent: pi
model: gpt-6.1-sol
trigger: user-prompt
status: executed
---

# Single-click Writer choices

> In the context of the Writer sidebar, facing a real screenshot with clipped ListBoxes and a selected meaning whose definition/example did not update, I decided to replace native dropdown lists with explicit single-click choices, accepting a little more vertical space and paginated meaning choices.

## Context
- The screenshot shows language and destination controls rendered as tiny scrolling lists rather than dropdowns. Meaning 3 is selected while meaning 1's translation, grammar and example remain visible.
- The live MOIEN1 response has three separate meanings and examples. The core correctly preserves these; the native selection interaction is the failing boundary.
- Word's HTML controls do not need replacement. Core parsing and SQLite contracts remain unchanged.

## Options considered

| Option | Pros | Cons |
| --- | --- | --- |
| Configure ListBox models before attaching peers | Could restore native dropdown appearance | Keeps a platform-sensitive interaction the user has repeatedly rejected |
| Explicit single-click language/destination choices and labelled meaning rows | No collapsed lists or double-click selection; reuses existing native links and palette | More vertical space; longer meaning lists need pagination |

## Decision

Chosen: explicit choices, because the selection action can update the definition, grammar, example and draft together without relying on dropdown commit events. Keep the existing palette and type. Use a single mouse-release event for the full control, ignore a second click in a double-click sequence, and retain Enter/Space activation. Language controls change meaning translations; dictionary examples remain Luxembourgish and say so explicitly. Give the example label and text separate measured controls.

## Consequences
- Writer has no ListBox or ItemListener choice path. Secondary actions keep native hyperlink controls, explicit keyboard activation and the existing TabController. Save remains a native button. Accessible roles and assistive-technology behavior still need real-host verification.
- More than five meanings remain reachable through meaning pagination. Existing per-sense notes and destinations survive choices.
- Regression checks send real single mouse events to native peers in an isolated dialog, not select a list item and manually invoke an item listener. They cover the screenshot's Moien meanings, language switching, missing examples and draft preservation. Failed Basic assertions now write an explicit FAIL report and stop; the former Error-statement path could produce false passes.
- AgDR-0006's ListBox choice decision is superseded; the rest of its reading-first layout and storage boundary stays unchanged.

## Artifacts
- `libreoffice/panel.py`
- `tests/libreoffice-runtime.py`, `tests/fixtures/moien.json`
- `tools/build.py`, `dist/lod-pane.oxt`
- `ARCHITECTURE.md`, `README.md`, `SETUP.md`

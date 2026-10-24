---
id: AgDR-0005
timestamp: 2026-10-17T21:00:00Z
agent: pi
model: unknown
trigger: user-prompt
status: executed
---

# Flat Writer controls

> In the context of the native Writer sidebar, facing repeated rejection of beveled buttons, I decided to use clickable UNO fixed-text controls to remove the bevel, accepting incomplete keyboard and accessibility support for these actions.

## Context
- The user's screenshot shows platform button bevels around language, sense, destination, and action controls.
- The existing runtime is UNO/Python with local SQLite, without a browser or service dependency.
- The current probe found no flat appearance property on its button models. This is not proof that every possible UNO button variant is unsuitable.

## Options considered

| Option | Pros | Cons |
|--------|------|------|
| Keep native buttons | Built-in keyboard, focus, and accessibility semantics | Retains the appearance the user rejected |
| Clickable fixed-text controls | Flat fills, no new dependency, keeps existing sidebar | Actions lack native button semantics and keyboard focus |
| Custom canvas | Full drawing control | Requires custom hit testing, focus, layout, and accessibility |

## Decision

Chosen: clickable fixed-text controls, because they remove the observed bevel without introducing a browser or custom drawing system. Native edit controls remain for input. Query Enter is handled separately.

## Consequences
- Flat controls use one palette for selected, inactive, primary, and link states.
- Lookup completion still requires the declared UNO XCallback interface.
- Keyboard-only use of flat actions and screen-reader button semantics remain limitations, not verified accessibility.
- Native runtime tests verify state and persistence, not rendered visual quality. A fresh screenshot is still needed.

## Artifacts
- `libreoffice/panel.py`
- `tests/libreoffice-runtime.py`
- `dist/lod-pane.oxt`, version 0.5.0

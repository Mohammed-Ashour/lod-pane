---
id: AgDR-0002
timestamp: 2026-10-17T14:06:44Z
agent: pi
model: unknown
trigger: user-prompt
status: executed
---

# Separate learner layouts from theme choice

> In the context of the user's preference for learner tools and the existing light and dark designs, facing the need to compare five more prototypes fairly, I decided to provide five learner layouts with one shared light/dark theme switch in a separate standalone gallery, accepting some duplicated gallery code to preserve the first study unchanged.

## Context
- The first gallery and its saved data must remain available.
- Every new layout needs grammar, a personal note, and Study/Favorites.
- Palette and layout should be independent decisions. Different colors must not masquerade as different prototypes.

## Options Considered
| Option | Pros | Cons |
| --- | --- | --- |
| Add five more concepts to the original gallery | One file for everything | Changes the first study and makes navigation and comparisons longer |
| Separate standalone round-two gallery with shared theme tokens | Preserves the original; compares layouts in either theme; works offline | Duplicates the original gallery frame |
| Extract a shared multi-file app | Less shared-source duplication | Breaks single-file portability and adds refactoring unrelated to choosing a concept |

## Decision
Chosen: **Separate standalone gallery**, because the user is narrowing a design direction rather than choosing a production architecture. Both galleries stay directly openable without a server. Each new layout uses the same light and navy/teal themes.

## Consequences
- New file: `learner-prototypes.html`, with concepts 06 through 10.
- Browser storage uses a separate key. Theme applies across layouts; saved vocabulary remains isolated per layout.
- Design preference records layout and theme together.
- Theme switching must not clear input, change the selected word, or save anything implicitly.
- Real host integrations and live LOD results remain out of scope.

## Artifacts
- learner-prototypes.html
- tests/learner-prototypes.cjs

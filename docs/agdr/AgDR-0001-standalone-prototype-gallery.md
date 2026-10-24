---
id: AgDR-0001
timestamp: 2026-10-17T13:37:46Z
agent: pi
model: unknown
trigger: user-prompt
status: executed
---

# Standalone prototype gallery

> In the context of a fresh repository, facing the need to compare five office-sidebar experiences, I decided to use one self-contained HTML file with simulated host applications to make the concepts directly comparable, accepting that native integrations and live dictionary behavior are not validated.

## Context
- The repository has no application code or existing architecture documentation.
- The user requested five prototypes together in HTML, with reasons for the UX choices.
- The adjacent lod-vault project uses a teal accent, Georgia dictionary entries, and local vocabulary storage. Its browser-extension storage APIs cannot run directly in an office add-in.

## Options Considered
| Option | Pros | Cons |
|--------|------|------|
| Self-contained HTML with CSS and JavaScript | Opens offline, easy to share, no build dependencies | Host behavior is simulated; one file is less modular |
| Framework app with separate prototype routes | Reusable components and route-level tests | Requires tooling and installation for a disposable design comparison |
| Native Word and LibreOffice prototypes | Tests actual host constraints | Separate integration work would slow the requested initial UX exploration |

## Decision
Chosen: **Self-contained HTML**, because the immediate decision is about interaction design rather than extension packaging. Keep the five interaction models distinct while sharing the same sample document and entries.

## Consequences
- No dependencies, external assets, telemetry, or network calls.
- Prototype saves and design preference use browser localStorage when available, with an in-memory fallback.
- Native selection events, focus restoration, sidebar sizing, persistence, and dictionary access remain separate engineering validation tasks.
- Sample meanings and UI timing are illustrative, not verified LOD responses or measured latency.

## Artifacts
- prototypes.html

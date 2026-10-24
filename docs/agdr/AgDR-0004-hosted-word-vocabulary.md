---
id: AgDR-0004
timestamp: 2026-10-17T15:22:00Z
agent: pi
model: unknown
trigger: user-prompt
status: executed
---

# Host Word pane and browser vocabulary; keep LibreOffice standalone

> In the context of real user feedback that the local Python companion setup is not acceptable installation UX, facing Word's HTTPS requirement against a local-only architecture, I decided to move the Word pane and lookup endpoint to hosting and use browser vocabulary as the first product, accepting a persistent host dependency and no offline Word pane.

## Context
- Confirmed LibreOffice blank-panel cause and fix: standalone UNO models lack the dialog-only `Name` property. The panel now renders and saves in a real LibreOffice probe. The oversized deck icon was replaced with a 24px sidebar icon.
- Word web and desktop both embed the same pane from an HTTPS URL. The local companion forces users to install Python, run a terminal server, and trust a development certificate. Users should not manage infrastructure.
- Local SQLite cannot be reached by a hosted pane; browser storage is the natural first vocabulary. LibreOffice cannot read browser storage, so both hosts cannot share a store without a backend.

## Options Considered
| Option | Pros | Cons |
| --- | --- | --- |
| Keep local companion and package it as an app | Fully local; no host dependency | Rejected by user; hides a Python server inside an installer |
| Hosted pane and API, browser vocabulary | One install step per user; no Python or terminal; Word web and desktop behave the same | Pane and lookups need internet; browser and LibreOffice vocabulary are separate; provider costs |
| Publisher-only hosted pane with server-side vocabulary | One store; cross-device sync | Accounts/privacy policy/server storage; out of scope for a first user release |

## Decision
Chosen: **Hosted pane/API with browser vocabulary**, because the simplest real user path is: upload one manifest, open the pane, select a word. Lookup requests still carry only the selected word. Notes and excerpts stay in the user's browser. LibreOffice keeps its direct Python core, SQLite, and no server.

## Consequences
- Word users need a working internet connection for the pane, lookups, and saving. Saved lookups cannot open in Word when offline; the hosted pane cannot load. LibreOffice keeps offline saved lookups and exports.
- The host serves static assets and a small stateless API with no accounts. Privacy terms must state that lookup words are received by the host, while document text, notes, and excerpts stay in the browser. Server-side word frequency counts may appear; no per-user profiles.
- Vocabulary is per browser: manual JSON export/import is the cross-browser path. Any future cross-device sync needs explicit opt-in, a real account, and its own decision record.
- Publishing a production manifest requires a real HTTPS origin, appdomain updates, store review, and maintenance of a database/cache for translation values. The manifest's origin and icon URL are therefore not finalized in this record.
- LibreOffice vocabulary stays SQLite-based and is not shared with Word unless a later decision adds a backend.
- The current local companion remains for development; it must not be described as user installation.

## Artifacts
- README.md, SETUP.md, ARCHITECTURE.md

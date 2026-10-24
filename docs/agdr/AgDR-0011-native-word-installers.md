---
id: AgDR-0011
timestamp: 2026-10-24T18:00:00Z
agent: codex
model: gpt-6.1-sol
trigger: user-prompt
status: executed
---

# Native Word installers with a bundled runtime

> In the context of Word setup requiring Python and Node.js, facing the user's explicit request for EXE and PKG installers, I decided to freeze the companion with PyInstaller and package it with Inno Setup and Apple's pkgbuild, accepting larger OS-specific artifacts and unsigned preview installers.

## Context

- AgDR-0010's script installers do not meet the requested native installation experience.
- Word still needs the loopback HTTPS server; its parser, SQLite storage, UI, and API stay intact.
- No developer signing certificates are available in the repository.

## Options considered

| Option | Benefit | Cost |
| --- | --- | --- |
| Wrap script installers in native packages | Familiar installer UI | Users still need Python and Node.js |
| Freeze Python and bundle local certificate provisioning | No Python/Node installation; native platform packages | Build-only PyInstaller and bundled cryptography; OS-specific builds |
| Rewrite as hosted add-in | No local server install | Changes storage and deployment; exceeds installer scope |

## Decision

Use a frozen companion because the user explicitly requires native installers with bundled prerequisites. Preserve the standard-library core; add cryptography only to native certificate provisioning. Create a per-user localhost CA and leaf certificate, discard the CA private key after signing, and request explicit trust through native OS tools. Never bundle certificates or keys in a release.

Register the Word XML manifest through the same per-user macOS folder and Windows WEF Developer registry mechanism used by Microsoft's tooling. Reuse the existing lock-protected supervisor and login startup behavior. Package Windows with Inno Setup and macOS as an application inside a PKG. Complete per-user setup on the app's first launch, with certificate approval and a management dialog.

## Consequences

- Native artifacts include the Python runtime. Node.js and npm are not needed by end users.
- The unsigned preview installers may be blocked by OS or organization policy. Signing/notarization requires credentials and is not claimed here.
- Frozen smoke tests use temporary certificate/data folders without modifying host trust or Office registration. Real Word acceptance remains open.
- This supersedes AgDR-0010's script-only distribution choice; script downloads remain a manual alternative.

## Artifacts

- `tools/native_word.py`, `tools/install_word.py`
- Native packaging scripts and `.github/workflows/release.yml`

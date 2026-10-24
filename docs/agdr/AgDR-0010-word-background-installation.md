---
id: AgDR-0010
timestamp: 2026-10-24T18:00:00Z
agent: codex
model: gpt-6.1-sol
trigger: user-prompt
status: executed
---

# Word background installation and preview releases

> In the context of a Word add-in that depends on a loopback HTTPS companion, facing manual terminal startup and source-only distribution, I decided to ship per-user setup scripts with OS login startup and release them after successful main CI, accepting Python and Node.js prerequisites and development sideloading.

## Context

- `server.py` serves the pane and local SQLite API. Removing it requires a separate storage and hosting redesign.
- `tools/install_word.py` already uses Microsoft's certificate utility and installs the macOS manifest, but does not manage the companion lifecycle.
- Users requested macOS and Windows installation, background operation, and downloadable releases for every merge to main.

## Options considered

| Option | Benefit | Cost |
| --- | --- | --- |
| Per-user Python setup, launch agent on macOS, login startup on Windows | Reuses the existing runtime and standard library; no administrator service or new runtime dependency | Requires Python and Node.js installed; platform script installers rather than signed native packages |
| Frozen companion with signed PKG and EXE installers | Removes Python prerequisite and offers native installation | Adds freezing, signing credentials, certificate packaging, and platform installer toolchains |
| Hosted Word pane and browser storage | Removes the local companion | Changes persistence, availability, deployment, and sharing contracts; out of scope for packaging |

## Decision

Choose per-user setup scripts because they can install the current implementation without redesigning its runtime. Use Microsoft's pinned `office-addin-dev-certs` and `office-addin-dev-settings` utilities for explicit certificate trust and development manifest registration. Register login startup only for the current user. A small supervisor owns the server child and accepts a local stop-file request, avoiding termination by stale PID or broad process matching.

Use a macOS LaunchAgent and the Windows current-user Run key. A lock prevents duplicate supervisors. Startup checks HTTPS with certificate validation. Uninstall stops the owned server and removes startup registration while retaining vocabulary and shared development certificates.

Publish immutable, commit-specific preview releases from the exact main commit after CI succeeds. Run packaging/lifecycle checks on both OS runners before publication. Do not promote PR branches or silently overwrite release assets.

## Consequences

- Users can close the installer terminal after setup; the companion starts at sign-in.
- This remains development sideloading, not Microsoft Marketplace deployment. Real Word acceptance remains separate from installer tests.
- Release ZIPs include setup, start, stop, status, and uninstall entry points. Certificates and vocabulary never enter the archives.
- The repository remains private unless the user changes its visibility.

## Artifacts

- `tools/install_word.py`, `tools/build.py`
- `tests/test_word_install.py`, `.github/workflows/release.yml`
- `SETUP.md`, `ARCHITECTURE.md`

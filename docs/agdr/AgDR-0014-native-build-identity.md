---
id: AgDR-0014
timestamp: 2026-10-24T18:00:00Z
agent: codex
model: gpt-6.1-sol
trigger: user-prompt
status: executed
---

# Identify and replace native preview builds

> In the context of a user reinstalling a replacement PKG but still reporting the old permission error without the new picker, facing identical package versions and unversioned logs, I decided to stamp native artifacts with their source commit and explicitly replace the app at its documented path, accepting that this does not by itself prove which old process the other Mac launched.

## Context

- All previous PKGs used version 0.7.0, and PyInstaller's app metadata said 0.0.0 with no bundle build version.
- The companion log recorded only exception text, without time, source commit, executable or setup stage.
- The current frozen macOS install path always enters the folder picker before reading Word's container; absence of that picker suggests an older instance or a different executable path.

## Options considered

| Option | Benefit | Cost |
| --- | --- | --- |
| Ask the user to repeatedly reinstall the same-named package | No implementation change | Provides no evidence that the installed or running build changed |
| Stamp builds and logs, use explicit PKG overwrite rules | Makes diagnosis reviewable and upgrades deterministic at /Applications | Adds a small build metadata/packaging helper |
| Force-kill all matching processes in a privileged package script | Could close stale instances | Risks interrupting processes and obscures user ownership; rejected |

## Decision

Embed the exact checked-out commit in native resources, app metadata, dialogs and timestamped diagnostic records. Use a numeric build version derived from the commit time in minutes, split into valid CFBundleVersion components. Stage packages at their documented /Applications path with relocation disabled, version skipping disabled and atomic bundle replacement. Preserve signing, user vocabulary and existing per-user state. Do not terminate user processes from a privileged installer script.

Keep a build/session record before setup begins and include the failing step and original traceback in local logs. Treat missing folder-picker evidence as a diagnostic signal rather than asserting that the protected-folder fix failed or succeeded on the user's other Mac.

## Artifacts

- Native build metadata and macOS packaging helpers
- `tools/native_word.py`, tests and setup documentation

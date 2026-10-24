---
id: AgDR-0003
timestamp: 2026-10-17T14:20:07Z
agent: pi
model: unknown
trigger: user-prompt
status: executed
---

# Use native host UIs and one standard-library core

> In the context of implementing Open notebook for Word and LibreOffice, facing incompatible sidebar runtimes and a request for a small architecture, I decided to use a vanilla Office.js task pane and a native Python UNO sidebar sharing one Python dictionary/storage module, accepting different rendering code and a local HTTPS companion for Word.

## Context
- The existing files are design studies only. Concept 06 is selected.
- Word supports web task panes. LibreOffice's supported sidebar API hosts native UNO panels, not a portable HTML browser view.
- LOD's live JSON endpoints were inspected; its search does not return browser CORS headers. Dictionary access belongs in the Python core.
- The core uses only Python's standard library. Native controls and HTML forms provide the UI.

## Options Considered
| Option | Pros | Cons |
| --- | --- | --- |
| Native Python LibreOffice sidebar and vanilla Word pane, shared Python core | Real sidebar support; one dictionary parser and durable vocabulary store; no framework | Two small UIs; Word needs a local HTTPS process |
| Try to embed the same HTML in both hosts | One renderer | LibreOffice has no supported cross-platform embedded web task-pane API |
| Separate standalone implementations and storage per host | No Word-to-Python storage coupling | Duplicates parsing and validation and separates the user's vocabulary |

## Decision
Chosen: **Native host UIs with one Python core**, because this is the smallest supported route to both actual sidebar integrations. LibreOffice calls the core directly, without a server. Word uses a loopback-only HTTPS server that serves the UI and exposes the same functions. SQLite handles concurrent local saves without a custom locking or sync layer.

## Consequences
- No React, build pipeline, remote application backend, authentication, or sync.
- Word needs Python 3 and a trusted localhost certificate. Microsoft's certificate setup tool is used only during installation, not as an application dependency.
- LibreOffice installs a generated OXT containing the core and uses its bundled Python. Linux distributions may require their python3-uno package.
- Only selected lookup text is sent to LOD. Optional document sentences and personal notes remain local.
- Selection requests use debouncing/generation checks. Saving never changes document text or discards a draft on failure.
- Real Word runtime testing requires Word, which is not installed in this environment. Native test limits must remain explicit.

## Sources
- https://api.libreoffice.org/examples/python/toolpanel/
- https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XSidebarPanel.html
- https://learn.microsoft.com/en-us/office/dev/add-ins/testing/sideload-an-office-add-in-on-mac
- LOD endpoints inspected: https://lod.lu/api/lb/search?lang=lb&query=Wieder and https://lod.lu/api/lb/entry/WIEDER1

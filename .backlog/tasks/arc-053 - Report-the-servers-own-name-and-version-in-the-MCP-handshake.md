---
id: ARC-053
title: Report the server's own name and version in the MCP handshake
status: Done
assignee:
  - '@claude'
created_date: '2026-07-28 11:12'
updated_date: '2026-07-28 11:15'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
MCP clients display this server as "archimate-mcp 1.28.1". Both halves are wrong.

The name is the pre-rename string and no longer matches the package, the PyPI project, or the console script, all of which are mcp-archimate.

The version is worse: it is the MCP SDK version, not this project. FastMCP.__init__ accepts no `version` parameter, so the low-level Server keeps version=None, and create_initialization_options falls back to pkg_version("mcp"). Every release will therefore report whatever SDK version happens to be pinned. Confirmed against the published 0.7.0 over stdio.

Cosmetic — it is display metadata, not protocol behaviour — but it is the first thing a user sees in their client server list, and a version that tracks the SDK is actively misleading when diagnosing an issue.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 initialize reports serverInfo.name as mcp-archimate
- [x] #2 initialize reports serverInfo.version as the package version, and it changes when __version__ changes
- [x] #3 A test asserts both, so a future SDK upgrade cannot silently reintroduce the fallback
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root cause: FastMCP.__init__ has no version parameter (confirmed by inspecting its signature), so the low-level Server keeps version=None and create_initialization_options() falls back to pkg_version('mcp'). The reported version therefore tracked the SDK pin, not this project.

Fixed by assigning mcp._mcp_server.version = __version__ after construction. That reaches for a private attribute, which ruff SLF001 flags — noqa'd with a comment explaining why: it is the only seam the SDK offers, and the alternative is shipping a misleading version. Also renamed the server from 'archimate-mcp' to 'mcp-archimate' so it matches the distribution, the PyPI project and the console script.

Safe to rename: MCP clients key off the config block name the user chose, not serverInfo.name, which is display metadata. Doing it now while the package is one release old costs nothing.

Added tests/test_server_identity.py with three tests, and mutation-tested them — deleting the version assignment fails two of the three. The third deliberately compares against a freshly constructed bare FastMCP rather than hardcoding an SDK version, so it keeps working after an SDK upgrade instead of needing maintenance.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed the MCP handshake reporting 'archimate-mcp 1.28.1' — the pre-rename name and the MCP SDK's version rather than the package's. FastMCP exposes no version parameter, so the low-level Server fell back to pkg_version('mcp'); now set explicitly from __version__. Renamed the server to mcp-archimate to match the distribution. Added tests/test_server_identity.py pinning both fields, verified load-bearing by mutation (removing the assignment fails two of three tests). 179 tests pass, ruff and format clean.
<!-- SECTION:FINAL_SUMMARY:END -->

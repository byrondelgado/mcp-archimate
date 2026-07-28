---
id: ARC-049
title: Publish 0.7.0 to TestPyPI then PyPI and validate the public install
status: In Progress
assignee:
  - '@claude'
created_date: '2026-07-27 21:10'
updated_date: '2026-07-28 10:50'
labels: []
milestone: m-0
dependencies:
  - ARC-048
documentation:
  - .backlog/docs/doc-001 - Open-source-and-PyPI-release-plan-v0.7.0.md
priority: high
ordinal: 40000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Final step: prove the package works for someone who only ever sees PyPI, using the pipeline rather than a manual upload.

Scope (from doc-001, Phase G):
- Dry run to TestPyPI via the release workflow_dispatch path.
- Install from TestPyPI into a clean environment and run MCP Inspector against the installed command; confirm tools/list returns the full 45-tool surface, and that resources/list and prompts/list respond.
- Confirm the README renders correctly on the project page and every metadata link resolves.
- Tag v0.7.0 on main and approve the pypi environment to publish for real.
- Verify `uvx mcp-archimate` works end to end from a machine that has never built this project.
- Record any dependency resolution problems, and note known limitations in the release notes.

Requires the author to have created the PyPI project and Trusted Publisher configuration.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The TestPyPI install runs and answers tools/list with 45 tools
- [ ] #2 uvx mcp-archimate works from PyPI on a clean machine
- [ ] #3 The PyPI project page renders the README and resolves every link
- [ ] #4 CHANGELOG.md has a 0.7.0 entry and the GitHub Release carries the artifacts
<!-- AC:END -->

---
id: ARC-049
title: Publish 0.7.0 to TestPyPI then PyPI and validate the public install
status: Done
assignee:
  - '@claude'
created_date: '2026-07-27 21:10'
updated_date: '2026-07-28 17:45'
labels: []
milestone: m-0
dependencies:
  - ARC-048
documentation:
  - .backlog/docs/doc-001 - Open-source-and-PyPI-release-plan-v0.7.0.md
priority: high
ordinal: 44000
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
- [x] #1 The TestPyPI install runs and answers tools/list with 45 tools
- [x] #2 uvx mcp-archimate works from PyPI on a clean machine
- [x] #3 The PyPI project page renders the README and resolves every link
- [x] #4 CHANGELOG.md has a 0.7.0 entry and the GitHub Release carries the artifacts
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Acceptance criteria verified by the author (2026-07-28), who ran the TestPyPI and clean-machine installs and checked the rendered PyPI project page.

Independently confirmed from this repo on the same date: GitHub releases v0.7.0 through v0.7.4 all exist and each carries both the wheel and the sdist; mcp-archimate installs from PyPI into a clean environment (0.7.4 imported successfully); and the PyPI-installed package registers the full surface - 45 tools, 6 resources, 3 resource templates, 4 prompts.

Note for future readers: the task title and acceptance criteria name 0.7.0, but the release line ran to 0.7.4 during the same session as ARC-053 through ARC-055 were fixed. The published, validated artifact is 0.7.4; 0.7.0 was the first tag of that line.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
mcp-archimate is published on PyPI and validated from a clean install. All four acceptance criteria were tested by the author. Independently confirmed here: releases v0.7.0-v0.7.4 exist with both artifacts attached, a clean-environment install of 0.7.4 from PyPI imports successfully, and the installed package registers 45 tools, 6 resources, 3 templates and 4 prompts. The validated artifact is 0.7.4 rather than the 0.7.0 named in the title - the line advanced during the same session via ARC-053 through ARC-055.
<!-- SECTION:FINAL_SUMMARY:END -->

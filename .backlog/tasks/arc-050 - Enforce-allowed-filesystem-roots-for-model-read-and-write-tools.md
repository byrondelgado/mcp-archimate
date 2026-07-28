---
id: ARC-050
title: Enforce allowed filesystem roots for model read and write tools
status: To Do
assignee: []
created_date: '2026-07-27 21:10'
labels: []
dependencies:
  - ARC-045
documentation:
  - .backlog/docs/doc-001 - Open-source-and-PyPI-release-plan-v0.7.0.md
priority: medium
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Deferred from the v0.7.0 public release by decision D8: the 0.7.0 release documents the filesystem trust model but does not constrain it. This task implements the constraint.

The server exposes load_model_from_file, export_model_to_file and render_view_to_svg_file, all of which accept arbitrary paths and run with the rights of whoever launched the server. For a package distributed publicly and driven by an agent, opt-in roots are a better default.

Scope (workstream S1 of the retired docs/PYPI_PUBLIC_RELEASE_PLAN.md):
- MCP_ARCHIMATE_ALLOWED_READ_ROOTS and MCP_ARCHIMATE_ALLOWED_WRITE_ROOTS environment configuration.
- Normalise and resolve every path before use; reject paths outside the allowed roots and any traversal surviving normalisation.
- Structured error codes: PATH_OUTSIDE_ALLOWED_ROOTS, INVALID_ALLOWED_ROOTS, FILE_READ_ERROR, FILE_WRITE_ERROR.
- Tests for allowed roots, denied roots, relative paths, tilde expansion and symlink escape.
- Decide and document the default when the variables are unset. Changing it from the current unrestricted behaviour is a breaking change and needs a CHANGELOG entry and an appropriate version bump.
- Update USER_GUIDE, README and SECURITY.md.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Both environment variables are honoured and documented
- [ ] #2 A path outside the allowed roots fails with PATH_OUTSIDE_ALLOWED_ROOTS
- [ ] #3 Symlink and traversal escapes are rejected after normalisation
- [ ] #4 The default behaviour when unset is documented and covered by a test
- [ ] #5 CHANGELOG records the behaviour change
<!-- AC:END -->

---
id: ARC-050
title: Enforce allowed filesystem roots for model read and write tools
status: Done
assignee:
  - '@claude'
created_date: '2026-07-27 21:10'
updated_date: '2026-07-28 17:57'
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
- [x] #1 Both environment variables are honoured and documented
- [x] #2 A path outside the allowed roots fails with PATH_OUTSIDE_ALLOWED_ROOTS
- [x] #3 Symlink and traversal escapes are rejected after normalisation
- [x] #4 The default behaviour when unset is documented and covered by a test
- [x] #5 CHANGELOG records the behaviour change
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. New leaf module pyarchimate_mcp_server/filesystem.py: MCP_ARCHIMATE_ALLOWED_READ_ROOTS / MCP_ARCHIMATE_ALLOWED_WRITE_ROOTS parsed at call time (os.pathsep separated), resolve_read_path / resolve_write_path enforcing them. No import of model_manager.
2. Default when unset is the launching user home directory (user decision, 2026-07-28). Chosen over deny-all because the README quickstarts write to ~/Desktop, and over unrestricted because opt-in protection reaches nobody who does not already know the vars exist.
3. Symlink and traversal defence comes from Path.expanduser().resolve(), which resolves symlinks across the whole path including a not-yet-existing tail, so ~/link-to-etc/passwd resolves to /etc/passwd and fails the containment check. Roots are resolved too, so a symlinked root still matches.
4. Error codes: give ArchiMateMCPError an error_code class attribute with a .code property defaulting to the class name, add PathOutsideAllowedRootsError and InvalidAllowedRootsError overriding it, and switch the ~46 exc.__class__.__name__ sites to exc.code so any future override works everywhere.
5. Enforce at all three file tools: load_model_from_file (read), export_model_to_file and render_view_to_svg_file (write). The read path must keep _validate_xml_content running first - the roots check is about where, not what.
6. Tests: allowed root, denied root, relative path, tilde expansion, symlink escape, and the unset default. Existing file tests write to pytest tmp_path, which is outside home on macOS, so an autouse fixture configures roots for the suite - that also exercises the env vars on every file test.
7. Docs: CHANGELOG (breaking, folded into 0.8.0), SECURITY.md, README, USER_GUIDE, and drop the "deliberately not enforced yet" paragraph from CLAUDE.md.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
New leaf module pyarchimate_mcp_server/filesystem.py holds the whole boundary: stdlib plus exceptions only, never imports model_manager, so both the manager and the tools layer call the same code. All three file tools route through it - load_model_from_file via resolve_read_path, and export_model_to_file / render_view_to_svg_file via the manager _resolve_output_path, which became a one-line delegation to resolve_write_path.

Default when unset is the launching user home directory (user decision, 2026-07-28), chosen over deny-all because the README quickstarts write to ~/Desktop and over unrestricted because opt-in protection reaches nobody who does not already know the vars exist. Documented as a default, not a placeholder.

Symlink and traversal defence is Path.expanduser().resolve(), which follows symlinks across the whole path including a tail that does not exist yet - so a link inside an allowed root pointing out of it resolves to its real target and fails containment. Roots are resolved too, so a symlinked root still matches its own contents. Both directions are tested.

Two ordering choices are deliberate and commented: the read check runs before the existence check in load_model_from_file, so the tool cannot be used to probe for files it may not read; and _validate_xml_content still runs first on content, because the roots check governs where and the XML validation governs what.

A relative allowed-root raises INVALID_ALLOWED_ROOTS rather than resolving against the CWD - the boundary must not depend on where the client launched the server. An empty setting is likewise an error rather than a silent fall back.

Error codes: ArchiMateMCPError gained an error_code class attribute and a .code property defaulting to the class name, and the 46 exc.__class__.__name__ sites across tools and resources now read exc.code. That keeps the existing class-name convention everywhere while letting PATH_OUTSIDE_ALLOWED_ROOTS and INVALID_ALLOWED_ROOTS be stable documented strings.

tests/conftest.py widens the roots to the system temp directory for the suite, because pytest tmp_path is outside home on macOS. That is a widening rather than a bypass: every file test still runs through the real boundary code. tests/test_filesystem_roots.py sets the variables explicitly per test.

One existing test changed meaning and was split rather than patched: test_load_model_from_file_reports_missing_path used /missing/model.archimate, which is now refused by the boundary before the existence check. It now uses a missing file inside the roots, and a second test asserts an existing file outside them returns PATH_OUTSIDE_ALLOWED_ROOTS without leaking that it exists.

Verified: 20 tests in test_filesystem_roots.py, mutation-checked by reverting _resolve_output_path to a bare resolve (both write-path tests fail). End-to-end smoke with the variables genuinely unset: reading /etc/passwd and writing /tmp both return PATH_OUTSIDE_ALLOWED_ROOTS, writing under ~ succeeds. uv run pytest: 217 passed. uv run ruff check and format --check: clean.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The three file tools are now confined to MCP_ARCHIMATE_ALLOWED_READ_ROOTS / _WRITE_ROOTS, defaulting to the home directory when unset, enforced in a new leaf module filesystem.py that every file path passes through. Paths are expanded and fully resolved first, so .. segments and symlinks cannot escape; refusals return PATH_OUTSIDE_ALLOWED_ROOTS with the resolved path and configured roots, and bad configuration returns INVALID_ALLOWED_ROOTS instead of silently falling back. Breaking, folded into 0.8.0 per the user. Verified by 20 tests including symlink escape, traversal both ways, tilde expansion, relative paths and the unset default, plus a mutation check on the write path and an end-to-end smoke with the variables unset. 217 passed, ruff clean. Docs updated in SECURITY.md, README, USER_GUIDE, TECHNICAL_ARCHITECTURE, CLAUDE.md and CHANGELOG; the stale "no environment variables" claims in README and CLAUDE.md were corrected.
<!-- SECTION:FINAL_SUMMARY:END -->

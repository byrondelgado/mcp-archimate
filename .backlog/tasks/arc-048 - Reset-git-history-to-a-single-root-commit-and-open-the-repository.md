---
id: ARC-048
title: Reset git history to a single root commit and open the repository
status: Done
assignee:
  - '@claude'
created_date: '2026-07-27 21:09'
updated_date: '2026-07-28 09:38'
labels: []
milestone: m-0
dependencies:
  - ARC-040
  - ARC-041
  - ARC-042
  - ARC-043
  - ARC-044
  - ARC-045
  - ARC-046
  - ARC-047
documentation:
  - .backlog/docs/doc-001 - Open-source-and-PyPI-release-plan-v0.7.0.md
priority: high
ordinal: 39000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The pre-release commit history describes an architecture that no longer exists (FastAPI routes, a Graphviz layout engine, a different task workflow) and carries a year of accumulated local development tooling. It cannot go public as-is, and the author accepted losing it. See decision-010.

This task runs LAST, so the single root commit captures the finished tree.

Scope (from doc-001, Phase A and decisions D2, D10):
- Build one root commit from the cleaned worktree; point main and dev at it.
- Force-push both branches.
- Delete the tags and the stale branch carried over from private development.
- Expire the local reflog and run git gc --prune=now.
- Fix the project_name typo in .backlog/config.yml ("mcp-architmate" should be "mcp-archimate") if ARC-040 has not already.
- The author flips the repository to public.

v0.7.0 is tagged later, by the publication task, on main.

Sanitization (ARC-051) must be complete before this runs — once the root commit is written, anything left in the tree is what the public sees.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 git log shows exactly one commit on main and on dev
- [x] #2 Only main and dev exist on the remote; pre-release tags and the stale branch are gone
- [x] #3 The worktree at the root commit passes the ARC-051 sanitization scan
- [x] #4 .backlog/config.yml spells the project name correctly
- [x] #5 The full test suite and lint pass on the new root commit
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Back up the current worktree (files only, no .git) to the scratchpad, so the release work is recoverable if the reset goes wrong. The history is what we intend to lose; the tree is not.
2. Final pre-flight: tests, lint, format, build, hygiene gate, sanitization scan.
3. git checkout --orphan to create a parentless branch holding the current tree; commit once.
4. Rename it over main; point dev at the same commit.
5. Delete the local stale branch and the three pre-release tags.
6. Force-push main and dev; delete the remote tags and stale branch.
7. Expire the reflog and gc --prune=now.
8. Verify: one commit on each branch, remote refs correct, suite still green.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reset executed. Root commit a7ab4a5, zero parents, 83 files. main and dev both point at it on the remote; .git went from 18 MB to 520 KB.

Order mattered: backed up the worktree (files only, not .git) to the scratchpad first, because the history is what we intended to lose and the release work is not. Then ran the full pre-flight — 176 tests, ruff, format, build, hygiene gate, release-version gate and the eight-pattern sanitization scan, all green — before creating anything, so the root commit could only capture a verified tree.

Used git checkout --orphan rather than filter-repo or a fresh remote: it produces a genuinely parentless commit from the existing worktree without touching the remote until the explicit force-push.

One benign error worth recording: 'git push origin --delete fearure/fix-load_model_from_content' failed with 'remote ref does not exist'. The typo'd branch only ever existed locally — it was never pushed — so there was nothing to delete remotely. Deleted locally; git ls-remote confirms the remote now carries exactly refs/heads/main and refs/heads/dev and no tags.

Post-reset verification: 'git rev-list --all --objects' finds no .env, .taskmaster, .windsurfrules, .roomodes or PDF blob reachable from any ref; one commit total across all refs; git fsck reports no unreachable objects after reflog expiry and gc --prune=now.

The author revoked the three API keys before this ran, which is what actually closed the exposure — force-push leaves unreferenced objects reachable by SHA on GitHub until its own garbage collection runs.

v0.7.0 is deliberately NOT tagged here. ARC-049 cuts the tag, because pushing it triggers the release workflow and that must happen only once the PyPI Trusted Publisher and the protected pypi environment exist.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Reset the repository to a single root commit (a7ab4a5, no parents) built from the sanitized tree, and force-pushed main and dev. Deleted the three pre-release tags remotely and the stale typo'd branch locally — it had never been pushed. Expired the reflog and ran gc --prune=now, taking .git from 18 MB to 520 KB. Verified that no sensitive blob is reachable from any ref, that exactly one commit exists across all refs, and that git fsck finds no unreachable objects. The remote now carries only refs/heads/main and refs/heads/dev, with no tags. 176 tests and ruff pass on the new root commit, and the working tree is clean.
<!-- SECTION:FINAL_SUMMARY:END -->

---
id: ARC-051
title: Sanitize the repository for public release
status: Done
assignee:
  - '@claude'
created_date: '2026-07-28 09:13'
updated_date: '2026-07-28 09:22'
labels: []
milestone: m-0
dependencies: []
documentation:
  - .backlog/docs/doc-001 - Open-source-and-PyPI-release-plan-v0.7.0.md
priority: high
ordinal: 42000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Before the history reset makes the tree public, remove internal detail that the public does not need. Raised by the author while reviewing decision-010, which carried operational detail about the pre-release history that a public repository has no reason to publish.

Scope:
1. Extract any durable rationale still only present in the completed task history into decision records, so nothing worth keeping is lost. This must happen BEFORE deletion — the author was explicit about it.
2. Delete the completed pre-release task files (45 files, ~3,200 lines of internal development narrative).
3. Rewrite decision-010, doc-001 and ARC-048 so the history reset is stated neutrally and truthfully: the pre-release commits described an architecture that no longer exists and carried local development tooling, so a single root commit was cleaner than filtering.
4. Remove references to prior local development configuration from the CHANGELOG.
5. Redact any customer or engagement model name, local absolute paths, and measured contents of private models wherever they survive.
6. Re-scan the whole tree and confirm nothing internal remains.

Note: this is repository hygiene, not a product security disclosure. Nothing here is a vulnerability in the server that users would need told about, and no third party is affected.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 No decision or rationale worth keeping is lost when the completed task history is deleted
- [x] #2 No file in the public tree carries operational detail about the pre-release history
- [x] #3 No file names a customer or engagement model, or contains a local absolute path
- [x] #4 decision-010 still explains the history reset honestly, without that detail
- [x] #5 A full-tree scan for secrets, local paths, private identifiers and internal names comes back clean
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Extraction first, deletion second — the author was explicit and it was the right order. Auditing the 45 completed task files against the 10 existing decisions found five load-bearing choices whose rationale existed only in CLAUDE.md and docs, with no decision record:

- decision-011: routing is implemented here because upstream auto_route is unusable (RoutingConfig.node_clearance is 25px while auto_route's own anchors sit 13px off the node edge, so every corridor search starts on a blocked cell). Also absorbs why Graphviz was deleted and the two mutation-tested collinear-separation guards.
- decision-012: an explicit auto_layout_view call always lays out. The old _has_meaningful_existing_layout heuristic could not distinguish add_node_to_view's default slot placement from a human arrangement, so it inverted intent and caused the group-member duplication bug.
- decision-013: layout.py is a leaf module reaching the model via view.model and never importing model_manager. Also records that a parallel quality.py extraction was considered and rejected — quality code is interleaved with the adapter calls it validates and has no equivalent to view.model.
- decision-014: the native Archi connection-type repair. pyArchimate types every connection as archimate:Connection even when it omits archimateRelationship, so Archi's getArchimateConcept() returns null and the whole view fails to open with 'Failed to create the part's controls'. Invisible to every other check — the XML is well-formed and nothing dangles.
- decision-015: assess_togaf_readiness is frozen as advisory-only, so it cannot grow into something that looks authoritative without being authoritative.

Checked two further candidates and left them: the viewpoint round-trip mechanism is explained in code comments at model_manager.py:280, and the remaining 'rejected' items were per-task dispositions rather than durable constraints.

Deleted .backlog/completed/ (45 files) and the stale .backlog/archive/ entry. Rewrote decision-010, doc-001, ARC-048, the CHANGELOG history note and two CLAUDE.md bullets to describe the reset by what it actually removes — an architecture that no longer exists plus local development tooling — with no operational detail.

Caught two self-inflicted problems while sanitizing: ARC-051's own description named the engagement model it was meant to redact, and a regex renumbering pass corrupted an unrelated numbered list in doc-001 (1,2,2,3,4,6,7). Both fixed and re-verified.

Also corrected three CHANGELOG facts that had gone stale during the work: the decision count (10 -> 15), the sdist size (246 KB -> 199 KB after the docs consolidation), and the release date.

Recorded in CLAUDE.md that ARC numbers in decisions and code comments are provenance markers, not links — the task files they name are gone by design, so a future reader does not go looking for them.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Sanitized the repository ahead of the public release. Extracted five uncaptured load-bearing decisions into records (routing, always-lay-out, the layout.py module boundary, the Archi connection-type repair, and the TOGAF scope freeze) BEFORE deleting 45 completed task files, so nothing durable was lost — decisions went from 10 to 15. Rewrote decision-010, doc-001, ARC-048, the CHANGELOG and CLAUDE.md so the history reset is explained truthfully without operational detail. Verified with a five-part full-tree scan: no secret-shaped strings, no pre-release commit SHAs, no key variable names, no local absolute paths, no engagement model name, and the only email addresses remaining are the intended public author and security contact. 176 tests pass, ruff and format clean, sdist builds at 199 KB and passes the hygiene gate.
<!-- SECTION:FINAL_SUMMARY:END -->

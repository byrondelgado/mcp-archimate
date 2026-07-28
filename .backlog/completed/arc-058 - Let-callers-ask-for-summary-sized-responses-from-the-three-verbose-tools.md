---
id: ARC-058
title: Let callers ask for summary-sized responses from the three verbose tools
status: Done
assignee:
  - '@claude'
created_date: '2026-07-28 13:41'
updated_date: '2026-07-28 14:11'
labels: []
dependencies: []
priority: medium
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Three tools return far more than a caller needs to decide what to do next, and for an LLM caller that payload is the dominant cost of a build session. None of them offers a way to ask for less.

Measured on a reconstruction of the field report model (71 elements, 143 relationships, no views yet - the state any caller hits when it builds all elements before building views):

- validate_semantics returned 56,273 bytes (55.0 KB), large enough that the client spilled it to disk rather than put it in context. The report attributed this to 71 near-identical ELEMENT_NOT_IN_ANY_VIEW objects, but the real total was 214 issues: 71 ELEMENT_NOT_IN_ANY_VIEW plus 143 RELATIONSHIP_NOT_IN_ANY_VIEW, and the relationship issues are the larger half - seven fields each including source and target ids. Fixing only the element check addresses about a third of the payload. The same response reduced to is_valid + issues_count + issue_counts is 239 bytes, a 235x reduction, and issue_counts.by_code is already computed and returned today (model_manager.py:2377) - the full list simply rides along with no way to opt out.
- auto_layout_view returns the complete post-layout ViewDetail: every node with full geometry and every connection with resolved node ids (view_tools.py:441). The next action is almost always "lay out the next view" or "export"; coordinates matter only when placing notes, and then only the bounding box.
- connect_visible_relationships returns skipped_relationship_ids in full alongside skipped_count (model_manager.py:1562). On the report first view that was 112 ids, and every skip was expected - endpoints living in other views.

Both completeness-style checks are also loudest at the moment they are least actionable: mid-build, before views exist, when the caller already knows the elements are not placed yet.

build_quality_report is the model to follow. It already returns aggregate counts only (issues_count, issue_counts.by_code, elements_not_in_any_view_count) and is the right size.

Design decisions this needs a call on, both of which affect existing callers: whether a summary shape becomes the default (a smaller default is the useful change but is breaking for anyone reading data.issues today), and whether validate_semantics also gains a severity filter so a build loop can ask for errors only. Note that ELEMENT_NOT_IN_ANY_VIEW and RELATIONSHIP_NOT_IN_ANY_VIEW are warnings, so a severity filter alone would collapse most of the payload.

Source: field report 2026-07-28, finding 3 (severity medium), plus measurements taken while verifying it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A caller can request a summary-sized response from validate_semantics, auto_layout_view and connect_visible_relationships without losing access to the full response when it is wanted
- [x] #2 The summary form of validate_semantics preserves what is actionable: per-code counts and the ids needed to act, without repeating identical code, severity and message strings per issue
- [x] #3 The summary form of auto_layout_view still reports what the caller needs after a layout, including whatever is needed to place notes afterwards
- [x] #4 connect_visible_relationships can report skipped work by count without enumerating every skipped relationship id
- [x] #5 Any change of default response shape is called out as breaking in CHANGELOG.md, or the default is left unchanged by explicit decision recorded on this task
- [x] #6 A test asserts the summary response is materially smaller than the full one on a model with hundreds of issues, so the saving cannot silently regress
- [x] #7 docs/USER_GUIDE.md documents the new parameter and both response shapes for all three tools
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. RED: tests that a default validate_semantics response is materially smaller than detail="full" on a 214-issue model, that the summary groups by code with ids and no repeated message strings, that error-severity issues stay fully readable in the summary, and that auto_layout_view / connect_visible_relationships summaries drop their big lists.
2. Add SUPPORTED_DETAIL_LEVELS = {"full", "summary"} with a _normalize_detail_level validator reusing the existing _unsupported_layout_value_error suggestion shape.
3. validate_semantics(detail=...) in the manager: summary returns is_valid, issues_count, issue_counts, issues_by_code (count + severity + ids per code) and errors (full dicts for severity=error, so is_valid=false is always explainable). Deliberately no "issues" key in the summary so a stale caller breaks loudly instead of silently reading a shorter list.
4. connect_visible_relationships(detail=...): summary drops skipped_relationship_ids, keeps counts.
5. auto_layout_view: add ViewDetail.summary() in models.py returning everything but the node/connection lists, plus node_count, connection_count and a bounds box so a caller can still place notes in free space. Manager keeps returning ViewDetail so its internal callers are untouched; the tool picks the shape.
6. Default is "summary" on all three (user decision, 2026-07-28), so this is breaking: bump to 0.8.0 with an explicit CHANGELOG callout.
7. No severity_filter parameter: the summary already separates errors from grouped warnings, so a build loop can read data.errors directly. Recorded here rather than silently dropped.
8. Docs: docs/USER_GUIDE.md for all three tools, plus tool docstrings.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added SUPPORTED_DETAIL_LEVELS with a public normalize_detail_level validator (public because auto_layout_view is shaped in the tools layer - the manager returns a ViewDetail there and its internal callers need that object, not a response dict). Unknown levels get the same did-you-mean shape as the layout enums.

validate_semantics summary: issues_by_code maps code -> {count, severity, ids}, errors carries the error-severity issues in full, and there is deliberately no "issues" key. That last choice is the important one: had the summary kept a shorter "issues" list, a stale caller would have silently read fewer issues than it believed it asked for. Four existing tests plus workflow_tools._compact_issue_summary broke loudly on the missing key, which is the design working - each was updated to opt into detail="full" where it genuinely reads per-issue dicts (assess_togaf_readiness, repair_semantic_issues, inspect_active_model).

Subject ids come from an ordered SEMANTIC_ISSUE_IDENTITY_KEYS tuple rather than a blind sweep, because several issue shapes carry more than one id (a relationship issue also carries source and target element ids) and only the first is the subject. A fallback sweep keeps a future issue code from silently reporting no ids.

auto_layout_view: ViewDetail.summary() drops the node and connection lists and adds node_count, connection_count and a bounds box. bounds is what makes the summary usable rather than merely small - placing a note afterwards needs to know where the free canvas is, which was the one thing the report said coordinates were still needed for.

Measured through the tool envelope on the reconstructed 71-element/143-relationship model: validate_semantics 68,863 -> 8,866 bytes (8x), auto_layout_view 8,856 -> 377 bytes (23x). The 8x rather than the 235x quoted in the task description is deliberate: the summary keeps all 214 subject ids, per AC #2, and ids are the actionable part. A counts-only shape would be ~239 bytes but would not tell a caller which elements to place.

No severity_filter parameter. The summary already separates errors from grouped warnings, so a build loop reads data.errors directly; adding a filter as well would be a second way to say the same thing.

uv run pytest: 196 passed. uv run ruff check: clean. uv run ruff format --check: clean.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
validate_semantics, auto_layout_view and connect_visible_relationships now take detail="summary"|"full" and default to summary; this is breaking and ships as 0.8.0 with a CHANGELOG callout. Measured through the tool envelope on a 71-element/143-relationship model: validate_semantics 68,863 -> 8,866 bytes, auto_layout_view 8,856 -> 377 bytes. The semantic summary groups by code with subject ids and keeps error-severity issues in full, and omits the "issues" key so stale callers fail loudly - which five real call sites did, each updated to opt into full. Verified by four new tests confirmed failing first, including a ratio assertion that stops the saving regressing silently. 196 passed, ruff clean.
<!-- SECTION:FINAL_SUMMARY:END -->

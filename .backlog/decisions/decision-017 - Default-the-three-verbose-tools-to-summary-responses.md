---
id: decision-017
title: Default the three verbose tools to summary responses
date: '2026-07-28 15:26'
status: accepted
---
## Context

A field report from an agent that built two models end to end through the tool
surface found response size to be the dominant practical cost of driving this
server — no correctness impact, but enough volume to change how a session runs.

Reproduced on a 71-element, 143-relationship model with no views yet, which is
the state any caller reaches when it builds all elements before building views:

- `validate_semantics` returned **214 issues, ~55 KB** — large enough that the
  client spilled it to disk rather than keep it in context. 71
  `ELEMENT_NOT_IN_ANY_VIEW` plus 143 `RELATIONSHIP_NOT_IN_ANY_VIEW`, each
  carrying the same `code`, `severity` and `message` strings. The completeness
  checks fire once per element and once per relationship, so they are loudest
  exactly when they are least actionable: mid-build, before any view exists.
- `auto_layout_view` returned every node with full geometry and every
  connection, when the next action is nearly always "lay out the next view" or
  "export".
- `connect_visible_relationships` returned every skipped relationship id — 112
  on the report's first view — and every one of those skips was expected, since
  any relationship whose endpoints live in another view counts as a skip.

`build_quality_report` already did this correctly, returning aggregate counts
only, which is what made the contrast visible.

The open question was not whether to offer a smaller shape but whether it should
be the **default**. Opt-in leaves the cost in place for every caller that does
not know to ask — the same discoverability failure as the missing viewpoint
catalog (ARC-057). Defaulting to it breaks anyone reading `data.issues`,
`data.nodes` or `data.skipped_relationship_ids` today.

## Decision

**`detail="summary"` is the default** on `validate_semantics`,
`auto_layout_view` and `connect_visible_relationships`; `detail="full"` returns
the previous payload. Shipped as **0.8.0**, called out as breaking.

Two shaping rules are load-bearing and not stylistic:

- **The `validate_semantics` summary has no `issues` key at all** — not a
  truncated list. A shorter `issues` would let a caller written against `full`
  silently read fewer issues than it believed it asked for. A missing key fails
  loudly. When the default changed, five real call sites broke this way and were
  corrected to `detail="full"`: `assess_togaf_readiness`,
  `repair_semantic_issues`, `_compact_issue_summary` in `inspect_active_model`,
  and two tests.
- **Error-severity issues are never grouped away.** `issues_by_code` groups by
  code, but `errors` carries error-severity issues in full, so `is_valid: false`
  always arrives with its reason attached.

**No `severity_filter` parameter**, though the report suggested one. The summary
already separates errors from grouped warnings, so a build loop reads
`data.errors` directly; a filter would be a second way to say the same thing.

**The summary keeps subject ids.** A counts-only shape would be ~239 bytes
instead of ~8.9 KB, but "71 elements are not in any view" without saying *which*
leaves the caller to go find out. Measured through the tool envelope:
`validate_semantics` 68,863 → 8,866 bytes (8x), `auto_layout_view` 8,856 → 377
bytes (23x).

## Consequences

- Callers that need per-issue dicts, per-node geometry, or the skipped-id list
  must pass `detail="full"`. This is documented on each tool and in
  `docs/USER_GUIDE.md`.
- Do not "fix" the missing `issues` key by adding a truncated list back. Silent
  under-reporting is the failure mode the omission exists to prevent.
- The `auto_layout_view` summary must keep `bounds`. It is what makes the shape
  usable rather than merely small: placing a note afterwards requires knowing
  where the free canvas is, and that was the one thing the report said
  coordinates were still needed for.
- A test asserts the summary is at least 5x smaller than `full` on a
  hundreds-of-issues model, so the saving cannot regress silently.
- `detail` is validated by `ArchimateModelManager.normalize_detail_level`, which
  is public because `auto_layout_view` is shaped in the tools layer — the
  manager returns a `ViewDetail` there and its internal callers need that object
  rather than a response dict.

**Enforced by:** `SUPPORTED_DETAIL_LEVELS`, the ratio assertion in
`test_semantic_summary_is_far_smaller_than_the_full_response`, the
`"issues" not in summary` assertion in
`test_semantic_summary_groups_by_code_without_repeating_strings`, and this
record. Extracted from ARC-058.

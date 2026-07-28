---
id: decision-008
title: 'Recognize the coverage view by marker property, never by name'
date: '2026-07-27 21:38'
status: accepted
---
## Context

`ensure_all_relationships_in_views` generates a scaffolding view holding every
relationship, and several passes must treat that generated view differently from
a view a human authored: it skips `add_layer_bands`, its redundant
group-containment connectors are relocated, and it is laid out as a fixed
source/target pair grid rather than by the normal engine.

Recognition originally included a convenience fallback: `"coverage" in
name.lower()`. It silently captured authored views. A view called **"Data
Coverage Analysis"** — an entirely reasonable name for real architecture work —
was treated as generated scaffolding: it lost its layer bands, kept its redundant
containment connectors because
`_relocate_group_containment_connections_to_coverage` skipped it, and was laid out
as a pair grid. None of that was reported to the caller. The view simply came
back wrong.

## Decision

**Recognise the coverage view by explicit marker, never by name substring.**

`layout.is_coverage_view` accepts a view only if:

1. it carries the `COVERAGE_VIEW_PROPERTY_KEY` marker
   (`"mcp:relationship_coverage_view"`, `layout.py:112`), written by
   `_mark_coverage_view` on every view the MCP creates or adopts; or
2. its name is an **exact** match against the caller's `coverage_view_name`.

**There is deliberately no substring fallback.** Do not reintroduce it — three
tests fail if you do.

## Consequences

- A user may name a view anything containing "coverage" without it being hijacked.
- The marker is a view property, and `_strip_dangling_view_properties` drops every
  view property from `archimate` exchange output. So the marker **survives a
  native `archi` round trip but not an exchange one**. After reloading from
  exchange, recognition depends on the caller passing `coverage_view_name` again.
  That asymmetry is a real limitation, and it is the price of not guessing from
  names.
- Callers that rely on regeneration across an exchange round trip must pass
  `coverage_view_name` explicitly.
- Any new pass that needs to distinguish generated from authored views must use
  `is_coverage_view` rather than inventing its own name check.

**Enforced by:** `layout.is_coverage_view`, `_mark_coverage_view`,
`COVERAGE_VIEW_PROPERTY_KEY`, and the three tests that fail on a substring
fallback. Fixed in ARC-037.

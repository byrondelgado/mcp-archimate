---
id: ARC-060
title: >-
  Report the layer band outcome from auto_layout_view instead of leaving it
  inferable
status: Done
assignee:
  - '@claude'
created_date: '2026-07-28 13:42'
updated_date: '2026-07-28 14:11'
labels: []
dependencies: []
priority: low
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
auto_layout_view(layer_bands=true) on a single-layer view produces no bands. That is correct - bands are meaningless when there is one layer - but the response gives no direct signal, so a caller who asked for bands and got none cannot distinguish "not applicable" from "failed" without knowing the internal rule.

The behaviour is right and documented: layout.add_layer_bands returns early when fewer than two layers are occupied (layout.py:538), and the auto_layout_view docstring states the two-or-more-layers condition. This is a response-shape gap, not a documentation gap.

Today the only trace is indirect. auto_layout_view returns a ViewDetail whose properties dict is the raw view properties (model_manager.py:2020), so the outcome has to be read by diffing that dict against the request parameter - and it has three states, not two, which the field report table did not capture:

- key absent: bands were never created on this view
- key present with band ids: bands were created
- key present but empty: remove_layer_bands cleared a previous run and add_layer_bands then declined (layout.py:519)

A caller cannot tell the third case from the first without having seen the prior response.

The same gap applies to the other silent skip on this path: add_layer_bands also returns early for a coverage view (layout.py:529), and under layout_engine="pyarchimate" bands are never added at all. That last one is reported in the message string but not as data.

Source: field report 2026-07-28, finding 5 (severity low).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The auto_layout_view response states how many layer bands the call produced, without the caller inspecting view properties
- [x] #2 When bands were requested but not produced, the response says why in a machine-readable form that distinguishes at least: single-layer view, coverage view, and engine does not support bands
- [x] #3 The reported outcome is correct for a view that previously had bands and no longer qualifies for them, not only for a view that never had any
- [x] #4 Tests cover a multi-layer view, a single-layer view, and a view that loses its bands between two layout calls
- [x] #5 docs/USER_GUIDE.md documents the new response fields for auto_layout_view
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. RED: assert auto_layout_view reports bands created for a multi-layer view, zero with a single-layer reason, zero with a coverage-view reason, zero with an engine reason under pyarchimate, and the previously-had-bands transition.
2. Have layout.add_layer_bands report its outcome instead of returning None, and thread that through auto_layout_view into the response as layer_bands_created plus a machine-readable layer_bands_reason.
3. Cover the three skip paths that exist today: fewer than two occupied layers, coverage view, and the pyarchimate engine (reported in the message string but not as data).
4. Document the new fields in docs/USER_GUIDE.md and the tool docstring.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
layout.add_layer_bands now returns {"created": int, "reason": str | None} instead of None, with the reasons as named constants in layout.py. auto_layout_view threads that into two new optional ViewDetail fields, layer_bands_created and layer_bands_reason, present in both the summary and full response shapes.

All five outcomes are reported, not just the single-layer one the report noticed: single_layer_view, coverage_view, not_requested, strategy_does_not_use_bands, and engine_does_not_support_bands. The last was previously stated only in the human-readable message string and not as data.

The fields are optional on ViewDetail and default to None, so map_view_to_detail leaves them unset everywhere else - a create_view response reports None, meaning "no layout ran in this call", rather than a misleading zero.

The previously-had-bands case falls out correctly because the outcome is computed from the current call rather than read back from the mcp:layer_bands property, which remove_layer_bands leaves as an empty string. The test deletes the ApplicationComponent between two layout calls and asserts the second reports 0 / single_layer_view.

All four tests confirmed failing first; test_auto_layout_view_reports_the_bands_it_created was additionally mutation-checked (dropping layer_bands_created from ViewDetail.summary makes it fail) because it was not covered by the initial RED run filter.

uv run pytest: 196 passed. uv run ruff check: clean.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
auto_layout_view now returns layer_bands_created and layer_bands_reason in both response shapes, so a caller who asked for bands and got none can tell "not applicable" from "failed" without diffing view properties. Covers all five outcomes including the two the report did not reach (coverage view, and the pyarchimate engine, previously stated only in the message string), and reports the current call rather than reading back a property that remove_layer_bands leaves empty. Verified by four tests confirmed failing first, one of them mutation-checked. 196 passed, ruff clean.
<!-- SECTION:FINAL_SUMMARY:END -->

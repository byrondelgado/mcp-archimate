---
id: ARC-056
title: Validate the viewpoint before create_view and update_view mutate the model
status: Done
assignee:
  - '@claude'
created_date: '2026-07-28 12:26'
updated_date: '2026-07-28 12:34'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 47000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
create_view and update_view validate the viewpoint AFTER the view has already been created or renamed, so a call that returns an error envelope still leaves the model changed.

Reproduced on 0.7.0: create_view(name="1. Business Process View", view_id="id-view-business", viewpoint="business_process") returns {"status":"error","code":"ModelOperationError"} and the view is nonetheless present in model.views, carrying props {"viewpoint": "business_process"} - the rejected value, persisted. The natural agent recovery (retry with a corrected viewpoint) then fails with "View with ID ... already exists", and the caller is holding a view it does not believe it created.

update_view is worse: it applies name and description AND writes the rejected viewpoint property, then raises. A failed update call renames the view.

Cause: ArchimateModelManager.create_view (model_manager.py:1151) calls model.add(...), then _apply_properties, then _apply_view_metadata (model_manager.py:3454), and only the last of those validates. update_view (model_manager.py:1174) has the same ordering. The singular add_element/add_relationship paths already validate before mutating (model_manager.py:854, :980), so these two are the only validate-after-mutate tools; rollback_on_error exists only on the batch tools and is not the right fix here - reordering is.

Existing coverage (tests/test_model_manager.py:3373) asserts the raise and the error.details catalogs but never asserts the view is absent, which is why this went unnoticed.

Source: field report 2026-07-28, finding 1 (severity high).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 create_view with an invalid viewpoint leaves the model unchanged: the view is absent from model.views and from views_dict
- [x] #2 Retrying create_view with the same view_id and a valid viewpoint succeeds rather than failing with a duplicate-ID error
- [x] #3 update_view with an invalid viewpoint applies no part of the update: name, description and properties are all unchanged, and the rejected viewpoint value is not persisted
- [x] #4 The error envelope for an invalid viewpoint still carries supported_viewpoint_slugs and supported_archi_viewpoint_ids in error.details
- [x] #5 A valid viewpoint supplied as either a pyArchimate slug or a canonical Archi viewpoint id still works unchanged on both tools
- [x] #6 Tests cover the failed-create, retry-after-failure, and failed-update cases and fail against the current implementation
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. RED: add tests that fail today - failed create_view leaves no view, retry with corrected viewpoint succeeds, failed update_view leaves name/description/properties untouched.
2. Extract the viewpoint check out of _apply_view_metadata into a pure validator (_require_valid_viewpoint) that raises ModelOperationError with both catalogs in .details and touches nothing.
3. Call the validator at the top of create_view and update_view, before model.add / before any field assignment, reading the viewpoint out of the incoming properties mapping rather than off the view.
4. Keep _apply_view_metadata setting primary_viewpoint for the valid case (load path at model_manager.py:280 and :3455 still relies on it) but let it no longer be the validation gate for the tool paths.
5. GREEN + verify the existing viewpoint tests (test_model_manager.py:3209, :3358, :3373) still pass.
6. Run uv run pytest and uv run ruff check; update CHANGELOG.md under a new Unreleased Fixed entry.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fix: extracted the viewpoint check out of _apply_view_metadata into _require_valid_viewpoint(properties), a pure validator that mutates nothing, and called it before model.add() in create_view and before the first field assignment in update_view. _apply_view_metadata now only mirrors the property onto pyArchimate primary_viewpoint and deliberately never raises - matching the load path at model_manager.py:284-288, which already suppressed unknown slugs so a foreign file would not fail to load. That leaves exactly one validation gate instead of two half-gates.

Validation still delegates to pyArchimate: _require_valid_viewpoint calls viewpoint_registry.validate_viewpoint_slug, the same function set_primary_viewpoint called, then falls back to the ARCHI_VIEWPOINT_IDS membership check. No ArchiMate rule moved into this repo.

Verified RED before GREEN: all three manager tests failed for the right reasons (view present after failed create; duplicate-ID error on retry; name == "Renamed By Failed Call" after failed update). The tool-level envelope test was mutation-checked - removing the _require_valid_viewpoint call from create_view makes it fail, confirming it is load-bearing rather than passing incidentally.

Side effect worth noting: create_model_from_spec passes view_spec properties straight into create_view, so a spec carrying an invalid viewpoint now fails before creating the view and rolls the whole spec back cleanly, instead of creating it and raising mid-batch.

uv run pytest: 185 passed. uv run ruff check: clean. uv run ruff format --check: clean.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
create_view and update_view validated the viewpoint after mutating, so an error envelope still left a view behind (carrying the rejected value as a property) and the retry hit a duplicate-ID error; update_view also renamed the view before raising. Validation moved into _require_valid_viewpoint and now runs before any mutation, and _apply_view_metadata no longer raises. Verified by three manager tests and one tool-level envelope test that reproduce the field report sequence, all confirmed failing first; the envelope test was additionally mutation-checked. Full suite 185 passed, ruff check and format clean.
<!-- SECTION:FINAL_SUMMARY:END -->

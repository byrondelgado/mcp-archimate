---
id: ARC-057
title: Add the viewpoint catalog to list_supported_types
status: Done
assignee:
  - '@claude'
created_date: '2026-07-28 12:27'
updated_date: '2026-07-28 12:34'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 48000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The server instructions tell callers not to guess concept types and to call list_supported_types for the version-specific catalog. Viewpoints are the one string-typed enum in the API that the catalog does not contain, so the only way to discover the accepted values is to trigger the error in create_view - the error message is excellent and returns both full catalogs, but it is reachable only by failing.

list_supported_types (model_manager.py:2104) returns element_types_by_category, relationship_types, folder_roots, folder_aliases, access_types, influence_strengths, association_is_directed, semantic_validation_modes, quality_gates, relationship_rule_metadata, relationship_recommendation_intents, layout_strategies, layout_engines and summary. No viewpoints.

Two things make guessing likely rather than merely possible. The create_view docstring offers layered, capability and service_realization as examples, all three valid, which teaches that viewpoint names read as plain snake_case descriptions - the exact inference that produces business_process (invalid) instead of business_process_cooperation (valid). And the accepted set is the union of two overlapping namespaces: 13 pyArchimate slugs from STANDARD_VIEWPOINTS and 25 canonical Archi ids in ARCHI_VIEWPOINT_IDS, overlapping in exactly seven values (capability, migration, organization, physical, stakeholder, strategy, technology). A caller who assumes "slugs are short, ids are long" still gets it wrong, because the short form exists for some concepts and not others.

The two catalogs are already computed together in the error path (model_manager.py:3465-3479); this exposes the same data without requiring a failed call.

Note: an infrastructure -> technology alias is not needed - infrastructure is already a valid pyArchimate slug.

Source: field report 2026-07-28, finding 2 (severity high).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 list_supported_types returns a viewpoints key containing both accepted namespaces, keyed so a caller can tell a pyArchimate slug from a canonical Archi viewpoint id
- [x] #2 The values returned are exactly the values create_view accepts, derived from the same sources as the error path rather than hardcoded
- [x] #3 The catalog is derived at call time from pyArchimate STANDARD_VIEWPOINTS and ARCHI_VIEWPOINT_IDS, so a pyArchimate upgrade cannot silently desynchronise it
- [x] #4 A test asserts that every value advertised by list_supported_types is accepted by create_view
- [x] #5 docs/USER_GUIDE.md documents the new key in the list_supported_types response schema
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. RED: test that list_supported_types exposes a viewpoints key with both namespaces, and a stronger test that every advertised value is actually accepted by create_view.
2. Factor the two catalogs out of the _require_valid_viewpoint error path into a single _viewpoint_catalogs() helper reading STANDARD_VIEWPOINTS and ARCHI_VIEWPOINT_IDS at call time.
3. Have both the error details and list_supported_types read that helper, so the advertised catalog and the accepted catalog cannot drift.
4. GREEN, then document the new key in docs/USER_GUIDE.md and note the wart-free discovery path.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added a module-level viewpoint_catalogs() next to the ARCHI_VIEWPOINT_IDS constant it reads, returning {"pyarchimate_slugs": [...], "archi_viewpoint_ids": [...]} derived at call time from STANDARD_VIEWPOINTS and ARCHI_VIEWPOINT_IDS. Both list_supported_types and the _require_valid_viewpoint error details now read that one function, so the advertised catalog and the accepted catalog share a source and cannot drift.

test_every_advertised_viewpoint_is_accepted_by_create_view is the anti-drift guard: it walks every value the tool advertises and creates a view with it, so adding a name to one catalog without the other fails the suite. Both new tests were confirmed failing first (KeyError: viewpoint).

Also addressed the second half of the finding - the discoverability of the value, not just its availability. The create_view docstring previously offered three valid examples (layered, capability, service_realization) and nothing else, which teaches that viewpoint names read as plain snake_case descriptions - the exact inference that produces business_process. create_view, update_view, list_supported_types and the get_usage_guide checklist now all point at data.viewpoints and say the names are not guessable; the rejection message names the tool too. docs/USER_GUIDE.md documents the key with the response shape and spells out the seven-value overlap.

No alias map was added. infrastructure is already a valid pyArchimate slug, so the alias suggested in the field report is unnecessary, and aliasing business_process -> business_process_cooperation would invent a name ArchiMate does not define.

uv run pytest: 185 passed. uv run ruff check: clean. uv run ruff format --check: clean.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
list_supported_types now returns data.viewpoints with both accepted namespaces (13 pyArchimate slugs, 25 Archi ids), derived at call time from the same sources the rejection path uses so the two cannot drift. Docstrings for create_view, update_view and list_supported_types, the get_usage_guide checklist, the error message and docs/USER_GUIDE.md all now route callers to it and warn that viewpoint names are not inferable from their English names. Verified by two tests confirmed failing first, one of which asserts every advertised value is actually accepted by create_view. Full suite 185 passed, ruff check and format clean.
<!-- SECTION:FINAL_SUMMARY:END -->

---
id: ARC-061
title: 'Make client-supplied IDs unique across the whole model, not per concept type'
status: Done
assignee:
  - '@claude'
created_date: '2026-07-28 19:44'
updated_date: '2026-07-28 19:48'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 42000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A client-supplied id is checked only against its own concept namespace, so the same id can be given to an element, a relationship, a view, a node and a connection at once. Both exports then emit that identifier twice in one document.

Probed on 0.8.0-pre: creating an element with id-shared, then a relationship with id-shared, then a view with id-shared, is accepted at every step. The exchange export emits <element identifier="id-shared"> and <relationship identifier="id-shared"> in the same file; the native archi export emits two <element id="id-shared"> entries.

That is invalid output. In the exchange schema identifier is the xs:ID that relationshipRef points at as a required xs:IDREF (already documented in docs/TECHNICAL_ARCHITECTURE.md around the note-connector rewrite), and an xs:ID must be unique per document - so this is the same class of defect _sanitize_exchange_output already repairs twice, in the opposite direction: an identifier declared twice rather than referenced but never declared. In the native format two elements sharing an id means an archimateElement reference can resolve to the wrong concept.

Nothing currently catches it. The round trip through pyArchimate succeeds because pyArchimate also keys concepts in separate dicts (elems_dict, rels_dict, views_dict, nodes_dict, conns_dict) and the manager checks only the matching one (model_manager.py:910, :1049, :1202, :1278, :1323, :1407). quality_gate="strict" does not catch it either: build_quality_report covers visual, semantic and coverage checks, not id uniqueness.

Surfaced by a field report (2026-07-28) whose author hit the in-namespace case - the same id reused for two relationships across two add_relationships batches, which was correctly rejected - and asked for a docstring line stating the uniqueness scope. Writing that line accurately today would mean documenting the sharp edge; closing the gap makes the intuitive statement true instead.

Behaviour change: a model that reuses one id across concept types starts erroring where it previously succeeded. Such a model is already producing a schema-invalid export, so this is a defect being caught rather than a capability being removed. Folding into 0.8.0, which is already a breaking release.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 An id already used by any concept in the model is rejected for every other concept type: element, relationship, view, node, note and connection
- [x] #2 A collision within the same concept type keeps its existing error message, which the field report specifically called clear and actionable
- [x] #3 A cross-type collision says which concept kind already holds the id and states that ids are unique model-wide
- [x] #4 Neither export can emit the same identifier twice in one document, asserted directly against the generated XML for both formats
- [x] #5 Existing workflows that recreate concepts under their original ids still work, in particular repair_semantic_issues with preserve_relationship_ids
- [x] #6 The add_element / add_elements / add_relationship / add_relationships / create_view / add_node_to_view / add_connection_to_view docstrings state the uniqueness scope
- [x] #7 CHANGELOG records the behaviour change and docs/USER_GUIDE.md documents the scope
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. RED: cross-type collisions accepted today (element then relationship, view, node, connection), plus a direct assertion that neither export emits a duplicate identifier.
2. Add a single _require_unused_concept_id(model, concept_id, kind) in model_manager that scans all five pyArchimate namespaces (elems_dict, rels_dict, views_dict, nodes_dict, conns_dict) and replaces the five separate per-dict checks.
3. Same-kind collision keeps its exact current message so the clear error the field report praised is preserved and no existing test churns; cross-kind gets a distinct message naming the holding kind and the model-wide rule, with the holder in error.details.
4. Verify repair_semantic_issues with preserve_relationship_ids still works - it deletes before recreating, so the id should be free, but that ordering is now load-bearing and needs a test asserting it.
5. Docs: the seven creation docstrings, USER_GUIDE, CHANGELOG under the existing 0.8.0 section, and a CLAUDE.md note that the namespaces are pyArchimate-side but the boundary is model-wide.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Replaced the six per-dict checks with one _require_unused_concept_id(model, id, kind) that scans all five pyArchimate namespaces via a CONCEPT_ID_NAMESPACES table. Every creation path now goes through it: add_archimate_element, add_archimate_relationship, create_view, add_node_to_view, add_note_to_view, add_connection_to_view. Notes and nodes deliberately share the "node" kind because pyArchimate keys both in nodes_dict.

Message design: a same-kind collision keeps its exact previous wording, because the field report singled that message out as clear and immediately actionable and callers hit it far more often. A cross-kind collision gets a distinct message naming the holder, with requested_concept_kind and existing_concept_kind in error.details. Wording is "already identifies an existing {kind}" rather than "is already used by a {kind}" - the latter produced "a element".

Verified RED first: the two cross-type tests failed with DID NOT RAISE, while the three regression guards (same-kind message, export uniqueness, repair-preserving-ids) passed before and after, which is what they are for. Re-probed the original defect after the fix: element then relationship then view with a shared id are now all rejected, and both exports report zero duplicate identifiers.

Note on the export test: it guards the rich fixture against future regressions rather than proving this fix, since the fixture never had a collision. The proof is the two creation tests.

repair_semantic_issues(preserve_relationship_ids=True) still works because it deletes the old relationship before recreating it under the same id. That ordering was incidental before and is load-bearing now, so it has its own test.

Docs: the six id docstrings across element_tools, relationship_tools and view_tools state the scope, both batch docstrings call out that splitting a build across batches does not create separate id spaces (the exact mistake in the report), USER_GUIDE gained a Core Concepts subsection with the three collision cases and the reason cross-type matters, plus CHANGELOG and a CLAUDE.md invariant note.

uv run pytest: 222 passed. uv run ruff check and format --check: clean. check_release_version.py v0.8.0: passes.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Client-supplied ids are now unique across the whole model rather than per concept namespace. The previous per-dict checks let one id belong to an element, a relationship and a view simultaneously, and both writers then emitted that identifier twice in one XML document - an xs:ID collision in the exchange format and an ambiguous archimateElement reference in the native one - with nothing catching it, since pyArchimate reads back through the same separate dicts and quality_gate does not check id uniqueness. Same-kind collisions keep their original clear message; cross-kind ones name the holder. Verified by two tests confirmed failing first plus three regression guards, and by re-probing the original defect end to end. Breaking, folded into 0.8.0. 222 passed, ruff clean.
<!-- SECTION:FINAL_SUMMARY:END -->

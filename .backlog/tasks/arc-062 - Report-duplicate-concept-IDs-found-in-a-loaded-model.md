---
id: ARC-062
title: Report duplicate concept IDs found in a loaded model
status: To Do
assignee: []
created_date: '2026-07-28 20:14'
labels: []
milestone: m-1
dependencies: []
priority: high
type: bug
ordinal: 43000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ARC-061 closed the creation path: a client-supplied id can no longer be reused across concept types. The load path is still open, and it is now the only way such a model can exist.

Verified on 0.8.0 by forging an exchange file whose relationship carries the same identifier as an element, then loading it:

    loaded OK: 2 elements, 1 relationships
    id-a in elems_dict: True
    id-a in rels_dict : True
    validate_semantics is_valid: True codes: [ELEMENT_NOT_IN_ANY_VIEW, RELATIONSHIP_NOT_IN_ANY_VIEW]
    quality report semantic issues: 3

The file loads without complaint, both dicts hold the same key, and nothing reports it. pyArchimate keys concepts in five separate dicts so it has no reason to object, _validate_xml_content checks entities and the root element rather than id uniqueness, and validate_semantics has no id check at all. Because both writers re-emit whatever is loaded, that model then round-trips straight back out as a document with a duplicate xs:ID - the exact defect ARC-061 stopped this server from creating.

quality_gate="strict" does not catch it either, so an export can be gated and still be schema-invalid.

Adding the check to validate_semantics fits the existing split: pyArchimate owns hard ArchiMate validity, and this layer is additive enrichment on top (decision-005). This is not an ArchiMate rule - it is an XML document constraint the exchange schema imposes through xs:ID - so there is no upstream verdict to defer to.

Worth deciding as part of this task: whether a duplicate id is an error-severity issue (so quality_gate="strict" blocks the export, which is the behaviour that actually protects the user) or a warning. Error is the honest reading, since the resulting file fails schema validation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A model loaded with the same id on two different concept kinds is reported by validate_semantics with a dedicated issue code
- [ ] #2 The issue names every concept holding the duplicated id, not just that a duplicate exists
- [ ] #3 The chosen severity is justified in the task notes, and if error-severity then quality_gate="strict" blocks an export of such a model
- [ ] #4 A model with no duplicates gains no new issues, so the check cannot inflate normal validation output
- [ ] #5 A test loads a forged file carrying a cross-kind duplicate and asserts the issue is reported
- [ ] #6 docs/USER_GUIDE.md documents the new issue code alongside the existing semantic checks
<!-- AC:END -->

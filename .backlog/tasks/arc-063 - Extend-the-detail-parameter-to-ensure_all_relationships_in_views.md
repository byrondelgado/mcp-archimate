---
id: ARC-063
title: Extend the detail parameter to ensure_all_relationships_in_views
status: To Do
assignee: []
created_date: '2026-07-28 20:14'
labels: []
milestone: m-1
dependencies: []
priority: medium
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ARC-058 added detail="summary"|"full" to validate_semantics, auto_layout_view and connect_visible_relationships, which were the three tools the field report measured. ensure_all_relationships_in_views has the same shape of response and was left out, so it is now the only verbose tool without the parameter.

It still returns skipped_relationship_ids in full (model_manager.py:1732) alongside skipped_relationships_count, exactly the pairing connect_visible_relationships had before ARC-058. On a model where most relationships are already drawn, that list is close to the whole relationship set and every entry in it is expected.

Two details to settle rather than copy blindly:

- The field name is skipped_relationships_count here but skipped_count on connect_visible_relationships. Aligning them is additive if the new name is added and the old kept, breaking if the old is removed - decide which, and if breaking, note it belongs with the other renames in this milestone.
- The response also carries added node ids, added connection ids, relocated containment connection ids, created view ids and remaining unused relationship ids. Work out which of those a caller actually acts on before deciding what the summary keeps; coverage_view_id and the remaining-unused count are the fields the workflow depends on.

Source: noted while implementing ARC-058, which deliberately scoped itself to the three tools the field report measured rather than sweeping every response.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ensure_all_relationships_in_views accepts detail with the same values and default as the three tools ARC-058 covered
- [ ] #2 The summary keeps the fields a caller acts on next, in particular coverage_view_id and the remaining-unused-relationships count
- [ ] #3 Any field renamed for consistency with connect_visible_relationships is either additive, or recorded as breaking with a CHANGELOG entry
- [ ] #4 A test asserts the summary omits the full id lists and that detail="full" still returns them
- [ ] #5 docs/USER_GUIDE.md documents the parameter and both response shapes
<!-- AC:END -->

---
id: ARC-064
title: Settle the API-shape inconsistencies from field report section 6
status: To Do
assignee: []
created_date: '2026-07-28 20:14'
labels: []
milestone: m-1
dependencies: []
priority: low
ordinal: 45000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Three naming and shape inconsistencies the 2026-07-28 field report raised as low-severity observations rather than defects. Nothing is broken; each one costs a caller a moment of doubt.

1. strategy vs layout_strategy. auto_layout_view takes strategy; export_model_content and export_model_to_file take layout_strategy for the same values. The auto_layout_view docstring already flags this as a known wart, which is an argument for settling it rather than documenting it again.

2. update_view splits its arguments. name, description and properties go inside the updates dict; viewpoint is a top-level sibling. Documented and working, but it means "update the view metadata" has two argument shapes depending on which metadata.

3. is_valid alongside warning issues. validate_semantics returns is_valid: true with warning-severity issues present. Defensible - warnings should not invalidate - but a field named is_valid next to a populated issue set invites misreading. The report suggested has_errors: false.

Scope note, and the reason this is low priority: the additive half of all three is non-breaking and needs no particular release. Accepting layout_strategy as an alias on auto_layout_view, accepting viewpoint inside updates, or adding has_errors alongside is_valid can each ship in a patch. Only removing the old spellings is breaking, which is what puts this in a minor-bump milestone.

Point 3 is also partly mitigated already: the ARC-058 summary shape puts an explicit errors list next to is_valid, so the ambiguity the report described is much reduced there.

Deciding to do nothing is a legitimate outcome for any of the three. Growing two accepted names for one parameter is itself a cost, and the strongest case against point 1 is that a single name is better than two aliases plus a deprecation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each of the three items has an explicit decision recorded: aliased, changed, or deliberately left alone with the reason
- [ ] #2 Any accepted alias is additive, so existing callers keep working
- [ ] #3 Any removal of an existing parameter or response field is recorded as breaking in CHANGELOG.md
- [ ] #4 Docstrings and docs/USER_GUIDE.md reflect whatever is decided, including the docstring wart note on auto_layout_view if that item is resolved
<!-- AC:END -->

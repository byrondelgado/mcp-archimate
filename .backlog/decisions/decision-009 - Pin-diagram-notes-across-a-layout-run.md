---
id: decision-009
title: Pin diagram notes across a layout run
date: '2026-07-27 21:38'
status: accepted
---
## Context

`add_note_to_view` (ARC-033) creates an Archi Note: a visual `Label`-category
node with no element, no folder and no model-tree entry, plus optional
annotation-only connector lines that create no relationship.

A note is placed by a human because *where it sits* is the whole point — it
annotates a specific part of the diagram. An automatic layout pass that moves it
destroys its meaning. But `auto_layout_view` always lays out, by design, and
upstream `auto_layout` does place notes.

## Decision

**Notes are pinned across a layout run, on one path shared by both engines.**

`layout.note_positions` captures positions, `layout.restore_note_positions`
restores them before routing. The capture point is fixed and load-bearing:
**after the last reparenting step (`nest_grouped_nodes`) and before the first
placement step.**

- A **top-level** note is pinned absolutely.
- A **nested** note (import-only) is pinned as an offset from its parent, because
  Archi clips a child to its parent's rectangle.

The restore is what discards upstream's placement under the `pyarchimate` engine
— which is also why `oversized_nodes_for_pyarchimate` may skip notes without
weakening the suitability guard.

**Notes are routing obstacles; Container bands are not.**
`ROUTING_OBSTACLE_NODE_CATEGORIES = frozenset({"Element", "Label"})`
(`layout.py:76`). A band is decoration that must not deflect a route; a note is
ink that must.

**Note connectors are exempt from visual validation, narrowly.**
`_is_annotation_connector` requires both a missing relationship *and* a `Label`
endpoint. A `Container` endpoint, or a vanished endpoint, stays reportable.

## Consequences

- The capture/restore pair is a **pair**. `restore_note_positions` is the only
  thing pinning notes under `pyarchimate` — the `internal` branch is separately
  protected by `placeable_nodes`. Dropping the restore fails exactly one test
  while the internal engine keeps passing. This has already happened once, as
  dead code that captured the positions and threw them away.
- Every pass that moves nodes must skip notes: `placeable_nodes` in the internal
  branch, `layout_group_children` for a group's children, and
  `_layout_coverage_view_pairs` for the coverage view, which has no pin/restore
  around it.
- Notes cannot be auto-arranged. Asking for tidy note placement is a feature
  request, not a bug.
- Exchange export must retype note lines to `xsi:type="Line"`: the schema types
  `relationshipRef` as a required `xs:IDREF` on `Relationship`, so writing a note
  line as a `Relationship` — all pyArchimate's writer can do — produces a document
  that fails keyref validation and makes Archi fail to open the view (ARC-036).
  `_rewrite_note_connectors_as_lines` fixes the write;
  `_restore_exchange_note_connectors` rebuilds the lines on load, because
  pyArchimate's reader skips every `Line`. Both live on the exchange path only.
- Diagram-only Archi **Groups** (`Container`) remain out of scope: no tool creates
  one. The only Containers in a view are the layer bands `add_layer_bands` writes
  and whatever an imported file brought with it.

**Enforced by:** `layout.note_positions`, `layout.restore_note_positions`,
`ROUTING_OBSTACLE_NODE_CATEGORIES`, `_is_annotation_connector`, and the test that
fails when the restore is dropped.

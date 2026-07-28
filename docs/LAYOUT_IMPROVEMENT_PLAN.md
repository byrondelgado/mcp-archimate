# ArchiMate Layout Improvement Plan

> **Status update (2026-07-27):** Diagram-only notes (Archi Notes, added by
> `add_note_to_view`) entered the layout pipeline. `layout.py` gained named
> `node.cat` predicates for them (`is_note_node`, `is_routing_obstacle`,
> `placeable_nodes`) plus a pin/restore pair (`note_positions`,
> `restore_note_positions`), used in five places:
>
> - **Placement skips them.** The `internal` branch places
>   `layout.placeable_nodes(view.nodes)`, which drops `Label` nodes, so a note
>   keeps the coordinates it was given while the element nodes are laid out
>   around it. Nothing moves element nodes out from under a note, so notes
>   belong in free space — that is a documented instruction to callers, not a
>   guarantee the layout enforces.
> - **Group child layout skips them too.** `layout_group_children` lane-places
>   `placeable_nodes(group_node.nodes)` and sizes the group from that same
>   list. A nested note is neither lane-placed nor measured: its coordinates
>   are about to be rewritten by `restore_note_positions`, so sizing the group
>   against them would size it against a value that no longer holds.
> - **Notes are pinned across the whole placement block.**
>   `auto_layout_view` captures `note_positions(view)` right after the last
>   reparenting step (`nest_grouped_nodes`) and before the first placement
>   step, then calls `restore_note_positions` after placement and before
>   routing. This is one shared path outside the engine branch, and it is the
>   **only** thing pinning notes under `layout_engine="pyarchimate"` — see the
>   next bullet. A top-level note is pinned in absolute coordinates; a nested
>   one (import-only — `add_note_to_view` cannot create one) is pinned as an
>   offset from its parent, because Archi clips a child to its parent's
>   rectangle and an absolute pin would render the note invisible once
>   placement moved its group away.
> - **Routing treats them as obstacles.** The `ObstacleMap` is now built from
>   `ROUTING_OBSTACLE_NODE_CATEGORIES = {"Element", "Label"}`. Layer bands
>   (`Container`) are still excluded: a band is decoration that must not
>   deflect a route, whereas a note is ink on the diagram, and a line drawn
>   through one is as unreadable as a line drawn through an element.
> - **The upstream suitability guard ignores them.**
>   `oversized_nodes_for_pyarchimate` skips notes — but **not** because
>   upstream leaves them alone. Upstream *does* place notes: run
>   `layout.layout_nodes_pyarchimate` alone on a note pinned at (777, 333) and
>   it comes back at (20, 500). The skip is sound because
>   `restore_note_positions` then throws that placement away, so a note never
>   occupies the cell upstream chose, and because `assign_grid_cells` never
>   reads `w`/`h`, so an oversized note cannot displace anything else either.
>   Refusing a whole layout over a wide note would be a false refusal naming
>   the one node whose upstream placement is guaranteed to be discarded.
>
> Layer bands are unaffected in either direction: `add_layer_bands` only ever
> collected `cat == "Element"` nodes, so a note is never a band member.
>
> `ensure_all_relationships_in_views` is a separate path with no note
> save/restore around it, so `_layout_coverage_view_pairs` filters annotation
> connectors out of its pair enumeration and skips notes in its trailing
> reposition loop. Without that filter a note line is laid out as if it were a
> relationship: the note is hard-assigned into the source column, the element
> it annotates into the target column, and every genuine relationship row is
> pushed down one 140px slot.

> **Human review (2026-07-26):** Rendered output from both layout engines was
> reviewed side by side by a human. Verdict: **`internal` produces the better
> diagrams.** Both engines stay supported — `pyarchimate` is a deliberate
> alternative, not a deprecated one — but `internal` remains the default on
> visual-quality grounds, not merely by precedence. This is the one measure the
> ARC-030 numbers below do not capture: they compare canvas area, ink ratio,
> feature coverage and milliseconds, none of which is diagram legibility. Do not
> cite the performance table as grounds for switching the default without a new
> human review reaching the opposite conclusion.

> **Status update (2026-07-25, later):** The three pyArchimate routing
> post-processors this repo had never adopted were measured against the
> repo's own router (ARC-031). **One was adopted, two are rejected.** All
> figures below are medians of 5 self-paired trials on a dense 45-node /
> 50-connection multi-layer view built through `ArchimateModelManager` and
> laid out by `auto_layout_view`, measured end to end (build once, route
> twice, with and without the pass). Do not re-litigate these without new
> measurements.
>
> **Adopted — `displace_collinear_segments`, behind two guards**
> (`layout.separate_collinear_connection_segments`). The heavy-band
> hypothesis in the problem statement below is *confirmed*: the bands are
> literally collinear overlapping segments. Separating them cuts overlapping
> pairs **26 -> 9** and overlapping ink **3,235 -> 1,950 px** on the
> bendpoint polylines (as drawn, including the node stubs: 104 -> 91 pairs,
> 6,505 -> 5,340 px, -18%), while non-orthogonal drawn segments (9), segments
> crossing node interiors (25), U-turns (0) and anchors on their node
> centerline all stay exactly where they were; `ObstacleMap`-blocked segments
> even drop 38 -> 35.
>
> Dropped in raw, the helper is **not** an improvement, which is why the
> guards are the deliverable and the upstream call is four lines of it:
>
> 1. It moves the first and last waypoints — which in this repo *are* the
>    node anchors — off the node centerline, so the node-exit stub goes
>    diagonal: drawn non-orthogonal segments **9 -> 17**, i.e. it trades
>    "heavy horizontal line bands" for "diagonal crossings", the other
>    complaint in the same sentence of the problem statement. Guard A lets an
>    anchor slide only *along* its own stub axis, and only while it stays
>    outside the node by `RoutingConfig.node_clearance`.
> 2. It knows about other segments but nothing about obstacles, so it
>    evacuates a crowded corridor straight into a node: segments through node
>    interiors **25 -> 29** (measured case: a horizontal segment sitting in a
>    15 px gap at y=865 relocated to y=905, through two 160x80 nodes). Guard B
>    reverts any displacement whose segment newly offends, judged against the
>    same `ObstacleMap` the corridor search already built.
>
> Both guards are load-bearing and mutation-tested (disable either one and a
> test fails). Blanket endpoint *pinning* was measured as the obvious
> alternative and rejected: it keeps only 12-14% of the benefit (26 -> 22
> pairs), because ~19 of ~32 routed polylines are 3-point doglegs whose two
> segments both touch an endpoint. The separation gap is **10 px**, from a
> sweep of 8/10/12/15/20: a wider push is likelier to land on a node and be
> reverted, so upstream's own `RoutingConfig.min_segment_gap` default of 20
> leaves roughly twice the overlap (26 -> 14 pairs).
>
> **Rejected — `remove_uturn_waypoints`.** Not "no benefit measured" but
> *benefit impossible*. It removed 0 waypoints and changed 0 polylines in
> 5/5 trials, every metric byte-identical. A positive control (a hand-made
> U-turn polyline) proves the measurement works and the helper does what it
> says. This router structurally cannot emit a U-turn: over 150 anchor pairs,
> 66 A* corridor paths and 48 dogleg paths contained zero, because
> `dogleg_path` returns exactly 3 points whose two segments are perpendicular
> by construction and A* never doubles back. Adopting it would add a call
> that provably never changes a pixel.
>
> **Rejected — `compute_corner_clearance`.** It is a one-line
> `max(edge_length * pct, min_px)` whose only upstream call site is
> `_spread_positions`, the per-edge anchor-*spreading* allocator. This repo
> does no spreading — `layout.routing_anchor` returns a single point on the
> node centerline per (node, other) pair — so there is nothing for it to
> constrain and it changes zero pixels. The problem it belongs to is real and
> measured (58 of 100 connection endpoints land on an anchor point shared
> with another connection; 25 anchor points carry 2+ connections; max 4 on one
> point), but that needs the spreading feature, in which this formula would be
> four lines. Tracked as a candidate below, not as an adoption.
>
> **Scope caveat — the views this document names never reach any of this.**
> `should_simplify_connection_routing` strips every bendpoint at >=60
> connections, or >=36 connections with >=1.15 connections per node. Verified:
> a 57-connection variant of the benchmark view (density 1.19) receives zero
> bendpoints and all three helpers are exact no-ops on it. By the table in
> the problem statement, `Business Purchase Flow` (40/56), `Application
> Payment Flow` (36/50) and `Complete Model Coverage` (135/209) are all on
> that side of the gate, so the separation pass cannot improve them —
> **that threshold, not the routing post-processing, governs how those four
> sample views look today.** The separation pass helps the mid-density band
> that routes but still crowds corridors.
>
> **Two measured candidates for future work** (recorded here rather than
> guessed at later):
>
> 1. **Obstacle-check the dogleg fallback.** A* fails for 28 of 50
>    connections on the benchmark view and falls back to `dogleg_path`, with
>    the source anchor already inside a blocked cell for 15/50 endpoints and
>    the target for 14/50. Every one of the 25 baseline segments crossing a
>    node interior belongs to an unchecked dogleg; A* paths never cross a
>    node. Fixing that would remove more real damage than segment separation
>    does.
> 2. **Spread anchors along node edges** (see `compute_corner_clearance`
>    above), sized on the 58/100 shared-endpoint measurement.

> **Status update (2026-07-28):** `add_layer_bands` now returns
> `{"created": int, "reason": str | None}` instead of `None`, and
> `auto_layout_view` surfaces that as `layer_bands_created` /
> `layer_bands_reason` on the returned `ViewDetail` under both engines. Band
> *behaviour* is unchanged — members are still only `cat == "Element"` nodes,
> bands still need two or more occupied layers, and they are still never
> re-added under `pyarchimate`. What changed is that each declining path now
> names itself rather than leaving the caller to infer the outcome from the
> `mcp:layer_bands` view property, which cannot express it: an absent key looks
> the same as a legitimately unbanded single-layer view, and a view that used
> to have bands keeps the property as an empty string once `remove_layer_bands`
> clears it in the prologue (ARC-060).
>
> `auto_layout_view` also gained `detail` (`"summary"` default). The summary
> drops the per-node and per-connection lists but keeps a `bounds` box, because
> placing a note afterwards needs to know where the free canvas is — the one
> thing per-node coordinates were still being read for. See `decision-017`.

> **Status update (2026-07-04):** Major roadmap items are now implemented in
> `layout.py`: labeled visual layer bands for multi-layer views (diagram-only
> Archi Groups, `layer_bands=false` to disable), lane wrapping at 1,600px,
> barycenter alignment of connected nodes across lanes, single nesting of
> Grouping members with legacy-duplicate healing, orthogonal obstacle-map
> routing with a dogleg fallback (never straight diagonals), and first-class
> viewpoints. Measured on a real model: canvas widths down up to 53%, ink
> density up 1.5-2.2x, worst connection length halved.

> **Status update (2026-07-03):** The optional Graphviz adapter and the
> "preserve existing layout" heuristic were removed. `auto_layout_view` now
> always lays out; group members nest exactly once (legacy duplicates are
> healed); groups are sized before lane placement; connection routing
> delegates the corridor search to pyArchimate's `ObstacleMap` A* with
> MCP-computed anchors. Sections below describing the Graphviz adapter,
> the engine registry, or preserving existing coordinates are historical.

> **Status update (2026-07-24):** pyArchimate was upgraded to 1.12.0
> (ARC-028). **Layout behaviour is unchanged** — laying out the sample model
> on 1.11.3 and 1.12.0 produced identical node bounds and identical bendpoint
> polylines across all seven views. Nothing in this plan needed re-planning.
> One correction to the note above, which previously scoped the upstream
> routing defect to 1.11.2: `auto_route()` is **still unusable in 1.12.0**.
> Re-measured on the installed 1.12.0 — `RoutingConfig.node_clearance` is
> still 25 px while upstream anchors paths at a hardcoded 13 px outside the
> node edge, so every corridor search starts on a blocked cell; a three-node,
> three-connection view routes 0 of 3 with `no valid orthogonal path found`.
> `layout.route_connections_around_nodes` must keep computing its own
> clearance-aware anchors: there is no upstream replacement to migrate to.
> See TECHNICAL_ARCHITECTURE.md for the full measurement.

> **Status update (2026-07-25):** Layout is **no longer internal-only**
> (ARC-030). `layout_engine="pyarchimate"` selects upstream `auto_layout` for
> **node placement only**, per call, never persisted. Connection routing stays
> the MCP's own under both engines — upstream `auto_route()` is still never
> called by anything. Phase 5 below is therefore partially un-superseded: an
> engine option exists again, but as a thin per-call branch around the
> placement block, not as a `LayoutEngine` abstraction or a registry.
>
> Unlike `auto_route()`, upstream `auto_layout()` does what its docstring
> says: it repositions every node, never resizes, and never touches
> connection waypoints. What it does **not** say is that it has no collision
> detection at all — `assign_grid_cells` never reads node `w`/`h`, so it is
> overlap-free only while every node fits `LayoutConfig().grid_size` (240 px).
> Measured: with every node ≤240 px, 0 of 40 randomized views overlapped;
> with exactly one node at 241 px, 36 of 40 did — every time reported as
> `success=True, warnings=[]`. That is why the engine ships behind a
> mandatory pre-flight suitability guard that refuses unsuitable views before
> any coordinate is written. **Do not weaken the guard to a warning.**
>
> Two hazards to keep recorded next to the `auto_route` note above:
>
> 1. **Never run upstream `auto_layout` after a routing pass.** It preserves
>    waypoints byte-for-byte, so repositioning nodes underneath them strands
>    the connectors — measured, 20 of 21 routed connections ended with
>    waypoints more than 600 px from *both* endpoints, trailing into empty
>    canvas. `auto_layout_view` prevents this by construction (placement
>    always precedes routing, and routing clears bendpoints first); a future
>    helper calling upstream directly would not.
> 2. **Never re-add layer bands under the upstream engine.** Its four-bucket
>    substring layer classifier disagrees with `layer_band_label_for_node`'s
>    six-row ArchiMate classification, so band members are non-contiguous.
>    Measured on a 36-node view: 4 bands, 4 mutually overlapping rectangles,
>    worst 1,410,688 px², the first band swallowing the whole diagram — plus
>    wrong containment, because `add_layer_bands` reparents via `node.move`.
>
> Every pyArchimate 1.x minor bump must re-run the overlap proof, not just
> the test suite: `assign_grid_cells` could gain or lose collision handling
> with no API change at all.
>
> **Correction (2026-07-26): the "~200x faster" figure was wrong, and the
> direction can reverse.** It compared upstream `auto_layout` *in isolation*
> (0.13 ms) against a whole `auto_layout_view` call (26.1 ms) — placement
> against placement-plus-routing. Re-measured through the shipped tool path,
> medians of 9 runs after warmup, on Grouping-free Association chains:
>
> | Nodes / connections | `internal` | `pyarchimate` | Routed |
> | --- | --- | --- | --- |
> | 43 / 42 | 50.7 ms | 157.9 ms (3.1x **slower**) | 25 vs 30 |
> | 120 / 119 | 2.3 ms | 0.8 ms (3.0x faster) | 0 vs 0 |
> | 200 / 199 | 5.3 ms | 1.3 ms (4.2x faster) | 0 vs 0 |
>
> Like-for-like, placement alone is 0.073 ms vs 0.264 ms — a real but modest
> 3.6x. End to end the router dominates, and below
> `should_simplify_connection_routing`'s gate the airier upstream placement
> gives it *more* work (more connections routed, longer corridors), so the
> call gets slower. Past the gate bendpoints are stripped and the placement
> saving finally shows. **State which side of the gate any future timing was
> taken on.** Compactness is shape-dependent too: `internal` is tighter at 43
> nodes (3.24 vs 3.76 Mpx) but *looser* on a 200-node chain (21.4 vs
> 11.8 Mpx), where lane wrapping stacks rows the plain grid spreads sideways.
>
> One more correction, for the same reason: a guard refusal is **not**
> universally a no-op. It precedes the placement write but follows the shared
> prologue, so on a view with loose `Composition` members the refusal still
> leaves them nested and the `Grouping` grown (measured 160x80 -> 720x180).
> On a flat view it changes nothing. The regression test pins the flat case;
> do not restate it as "a refusal never modifies the view".


This document captures the layout direction for the MCP ArchiMate server. It is intentionally detailed so future Codex sessions can resume the work after context compaction without rediscovering the same facts.

## Current Problem Statement

Generated Archi-native `.archimate` files can open correctly in Archi but still be difficult to read. The specific regression sample is `sample-ecommerce-purchase-payment-flow.archimate`. Its screenshots show heavy horizontal line bands, diagonal crossings, labels overlapping relationship routes, and Grouping nodes that do not clearly communicate containment.

The root cause is not a single bug. The sample has several views that are too shallow for their relationship density:

| View | Nodes | Relationships | Approximate Size | Observed Risk |
| --- | ---: | ---: | --- | --- |
| `Business Purchase Flow` | 40 | 56 | `2800 x 500` | Too many relationships squeezed into a short process band. |
| `Application Payment Flow` | 36 | 50 | `2800 x 360` | Application structure, behavior, and data are mixed in a very shallow layout. |
| `Technology and Physical Fulfillment` | 35 | 42 | `2800 x 360` | Technology, physical, and implementation concerns are visually compressed. |
| `Complete Model Coverage` | 135 | 209 | `2800 x 2388` | Useful for validation coverage, but not suitable as a human-readable model view. |

The previous label-aware router adds two-bendpoint detours to many relationships. In compact dense views, those detours become worse than straight lines because many routed paths share the same horizontal bands. The layout must therefore be density-aware and semantic, not just label-aware.

> **Partly stale (2026-07-25, ARC-031).** The "heavy horizontal line bands"
> diagnosis is confirmed and now has a fix (see the status update at the top:
> collinear separation behind anchor and obstacle guards). But three of the
> four views in the table above are past the dense-routing gate, so they carry
> *no* bendpoints at all today — their appearance is governed by
> `should_simplify_connection_routing`, not by the router's post-processing.
> Re-measure before treating this table as the target of any routing work.

## Design Principles

1. Readable views and validator coverage are different goals. Main views should explain a concern such as business process, application services, or technology deployment. A dedicated coverage view can render otherwise-unused relationships so Archi Validator does not report `Unused Relation` warnings.
2. ArchiMate semantics should drive placement. Business concepts belong above application concepts, application data belongs below application behavior/services, and technology/physical/implementation concepts belong below application concepts.
3. Left-to-right flow is the primary visual path. `Triggering` and `Flow` relationships should define the main process or journey direction where possible.
4. Supporting relationships should route vertically when possible. `Assignment`, `Serving`, `Realization`, and `Access` should usually connect between semantic lanes rather than cross the whole diagram diagonally.
5. Group containment should be visual containment. If a `Grouping` element aggregates or composes members and the group is visible, its members should appear inside the group bounds or in a deliberate duplicate containment panel.
6. Junctions are routing symbols, not normal elements. `AndJunction`, `OrJunction`, and generic `Junction` nodes should be compact, around `32 x 32`, instead of using the default `160 x 80` size.
7. Dense views should avoid decorative bendpoint routing. Bendpoints are useful in small views for labels, but in dense views they create unreadable bands. Dense views should prefer simple routes unless a measured overlap reduction justifies a bendpoint.

## Adopted Internal Approach

The MCP should keep a deterministic built-in layout engine as the default. This preserves portability and avoids requiring Graphviz, Java, Node, or native build tools for normal MCP use.

The built-in engine should be organized around these phases:

1. Normalize visual sizes, including compact junction sizing.
2. Classify view density using relationship count and relationships-per-node.
3. ~~Decide whether to preserve existing coordinates. Existing coordinates are preserved only when they are meaningful and not compact-dense.~~ (removed 2026-07-03) An explicit `auto_layout_view` call now **always** lays the view out. The preserve-existing-coordinates heuristic inverted user intent and caused the group-member duplication bug, so there is deliberately no such branch in `auto_layout_view`.
4. Place nodes in semantic ArchiMate lanes for generated or compact-dense views.
5. Preserve left-to-right order for journey/process flow relationships when possible.
6. Lay out group children inside group bounds and resize group nodes after placement.
7. Simplify relationship routing for dense views.
8. Add bendpoint routing only for small or moderate views where label overlap reduction is measurable.
9. Keep validation-only relationships in a separate coverage view where possible.

## External Layout Engines Evaluated

Graphviz `dot` is a practical optional candidate for directed hierarchical layout. It supports rank direction, clusters, labels, and parseable output formats, but it requires the Graphviz executable and does not natively understand ArchiMate semantics. Relevant references:

- [Graphviz dot layout documentation](https://graphviz.org/docs/layouts/dot/)
- [Graphviz plain output documentation](https://graphviz.org/docs/outputs/plain/)

Eclipse Layout Kernel (ELK) is the stronger long-term candidate for complex compound diagrams. ELK Layered supports compound graphs, edge labels, ports, hierarchical placement, and advanced routing options. It is a better fit for Grouping nodes and label-aware routing, but it adds Java or JavaScript integration complexity. Relevant references:

- [ELK Layered algorithm reference](https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html)
- [ELK JSON graph format](https://eclipse.dev/elk/documentation/tooldevelopers/graphdatastructure/jsonformat.html)

PyGraphviz is not recommended as a required dependency because it needs Graphviz plus native build tooling. It may be useful as an optional adapter later, but the core MCP should not depend on it.

## Recommended Adoption Sequence

### Phase 1: Stabilize Built-In Layout

Status: implemented.

Tasks:

- Add density-aware routing so compact dense views remove bendpoints instead of adding more detours.
- Treat compact dense existing layouts as candidates for semantic lane reflow rather than preserving their shallow coordinates.
- Normalize junction node sizes to compact symbols before layout.
- Keep all existing tests passing.
- Add regression tests for dense routing and junction sizing.

Acceptance checks:

- `uv run pytest`
- `uv run ruff check`
- `uv run ruff format --check`
- Generated dense views should have no node overlaps and should not accumulate large numbers of bendpoints.

### Phase 2: Semantic Lane Ordering

Status: implemented.

Tasks:

- Improve lane ordering within each layer:
  - Motivation stakeholders and drivers.
  - Goals, outcomes, values, requirements, and constraints.
  - Strategy capabilities, value streams, courses of action, and resources.
  - Business actors/roles/collaborations.
  - Business process/event/interaction flow.
  - Business services/functions/products.
  - Business objects/contracts/representations.
  - Application components/collaborations/interfaces.
  - Application services/processes/functions/interactions/events.
  - Data objects.
  - Technology infrastructure, technology services, artifacts, physical concepts, and implementation concepts.
- Preserve process flow order using `Triggering` and `Flow` relationships before considering secondary relationship types.
- Keep data objects near the behavior that reads or writes them. Current behavior aligns `BusinessObject` and `DataObject` nodes under the rank column of visible `Access` relationship sources when the source and data object are in different semantic lanes.
- Reduce label noise in dense views. Current behavior keeps labels for primary `Triggering` and `Flow` relationships when present, keeps `Influence` labels for dense motivation/strategy views without flow relationships, and hides lower-value secondary labels through Archi's `nameVisible=false` connection feature.
- De-emphasize secondary relationships in dense views with a light gray line color when the connection does not already define a custom color.
- Preserve already-tall authored dense views instead of blindly reflowing them. A trial high-density reflow made application and technology diagrams much wider, so the adopted path is targeted label/line reduction plus semantic alignment for generated and compact-dense views.

Acceptance checks:

- Main business and application views read left-to-right.
- Data nodes appear below behavior/service rows.
- Technology/physical/implementation nodes do not intermix with business or application rows.
- Dense business/application/technology views show primary flow labels while secondary structural links remain visible but visually quieter.

### Phase 3: Group Containment

Status: implemented.

Tasks:

- Ensure visible `Grouping` nodes contain their Aggregation/Composition members.
- Resize groups after child layout.
- Avoid drawing redundant group-to-child relationship lines when containment already communicates the relation, unless a coverage view needs the relationship. Current behavior hides and lightens the connection during normal auto-layout, and `ensure_all_relationships_in_views` relocates those redundant containment connectors to the coverage view so the readable view relies on containment while Archi Validator still sees the relationship in a view.
- Keep duplicate child panels only when preserving an authored view would otherwise move important existing nodes. Current behavior moves members into the group for generated/unpositioned layouts, and creates contained duplicate member nodes for meaningful authored layouts so original authored placements remain intact.

Acceptance checks:

- Group children are inside the group bounds.
- Group bounds have consistent padding.
- Groups do not sit empty when member relationships exist.
- Redundant containment connectors are absent from readable views after `ensure_all_relationships_in_views` and present in coverage instead.
- Meaningful authored layouts keep their original top-level member nodes while adding contained duplicates inside the group panel.

### Phase 4: Coverage View Policy

Status: implemented.

Tasks:

- Keep `ensure_all_relationships_in_views` focused on unused relationship coverage.
- Prefer a dedicated `Relationship Coverage` view for relationships that do not naturally belong in an existing view.
- Avoid injecting large numbers of validation-only relationships into human-readable views.
- Treat custom `coverage_view_name` values as coverage views even when the name does not contain the word `coverage`.
- Mark created or reused coverage views with the `mcp:relationship_coverage_view=true` property so future operations can recognize them independent of display name.

Acceptance checks:

- Archi Validator should not show `Unused Relation` warnings after coverage generation.
- Human-readable views should not become visibly worse after coverage generation.
- If a readable view already contains both endpoint nodes but the relationship is not drawn, `ensure_all_relationships_in_views` adds the relationship to the coverage view instead of modifying the readable view.
- Existing custom coverage views are not treated as normal readable views during containment relocation.

### Phase 5: Optional External Engine Boundary

Status: partially superseded, then partially revisited. The `LayoutEngine` abstraction and the Graphviz adapter were removed in 2026-07-03 and are not coming back. A per-call `layout_engine` option returned in 2026-07-25 (ARC-030) as a plain branch around the placement block, with `pyarchimate` as the second value; see the 2026-07-25 status update at the top. ELK remains a possible future adapter.

Tasks:

- ~~Introduce a `LayoutEngine` abstraction with an internal deterministic engine as the default.~~ (implemented, then simplified away 2026-07-03: internal-only functions in `layout.py`)
- ~~Add an optional Graphviz adapter if the executable is available.~~ (removed 2026-07-03; internal-only)
- Consider ELK as a later optional adapter for compound/grouped views.
- Keep MCP tool parameters stable while adding optional layout engines behind the existing `layout_strategy` behavior or a new explicit `layout_engine` option.
- ~~Expose `layout_engine="internal"` as the default on `auto_layout_view`, `export_model_content`, and `export_model_to_file`.~~ (done; still the default everywhere)
- ~~Expose `layout_engine="pyarchimate"` for upstream coarse-grid placement.~~ (done 2026-07-25, ARC-030; placement only, per call, behind the suitability guard)
- ~~Expose `layout_engine="graphviz"` as an optional adapter that shells out to the `dot` executable only when explicitly requested.~~ (removed 2026-07-03)

Acceptance checks:

- No external dependency is required for default MCP operation.
- Optional engines degrade gracefully with actionable error messages when unavailable.
- `list_supported_types()` reports supported layout strategies and layout engines.
- Unknown layout engine names fail before mutating layout.

## Important Current Implementation Notes

- `pyarchimate_mcp_server/model_manager.py` owns layout behavior.
- `auto_layout_view` currently supports `layered_by_type`, `layered`, and `grid`.
- `layered_by_type` is the default strategy and should remain the recommended default.
- `ensure_all_relationships_in_views` should continue to use a coverage view instead of cluttering existing views.
- `ViewNode.parent_node_id` exists so MCP clients can inspect nested/grouped visual nodes.
- `ViewNode.note_text` exists so MCP clients can tell a diagram note apart from the other element-less visual nodes; it is `None` for everything but `Label`-cat nodes.
- The native Archi writer must continue to emit Influence relationship strength as `strength`, not `influenceStrength`.
- Do not restore deleted local example files unless explicitly asked. In the current workspace, generated `.archimate` examples may be user-managed artifacts.

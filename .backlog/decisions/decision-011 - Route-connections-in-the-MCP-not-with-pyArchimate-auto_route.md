---
id: decision-011
title: 'Route connections in the MCP, not with pyArchimate auto_route'
date: '2026-07-28 09:14'
status: accepted
---
## Context

pyArchimate ships `auto_route()`, and using it would be the obvious choice — one
call instead of a routing implementation to maintain. An early version of this
project did the opposite of obvious for a different reason: it carried a Graphviz
dependency to compute routes. Both were wrong.

**Graphviz was a system dependency for a diagram nicety.** It made the server
unusable for anyone who had not installed a native binary, which is an
unacceptable price for a public `uvx` install. Removed in ARC-015.

**Upstream `auto_route()` does not work.** Its own configuration contradicts
itself: `RoutingConfig.node_clearance` is 25px, while `auto_route`'s anchors sit
13px off the node edge. Every corridor search therefore begins on a cell the
obstacle map has already marked blocked, finds nothing, and routes nothing. This
is not a tuning issue — it fails on every connection. Confirmed against 1.11.2
and **re-verified on 1.12.0**.

## Decision

**Compute the anchors here, delegate the search upstream.**

`layout.route_connections_around_nodes` computes clearance-aware anchors — placed
outside `node_clearance` so the search starts on a free cell — and then hands the
corridor search to pyArchimate's `ObstacleMap` A*. The pathfinding is upstream's;
only the anchoring is ours. A dogleg fallback covers the cases A* cannot solve.

Routing is **engine-independent**: it runs in the shared epilogue of
`auto_layout_view` under both placement engines (see decision-003). No Graphviz,
no system dependency.

**Collinear separation** (`separate_collinear_connection_segments`) follows the
same pattern — use upstream, but guard it. Routes are collected first,
connections that ended up sharing a corridor are pulled apart with pyArchimate's
`displace_collinear_segments`, and only then are bendpoints written.

The bare upstream helper is a **regression**, not an improvement:

- It moves the first and last waypoints, which are this repo's node anchors, off
  the node centreline — so node-exit stubs go diagonal.
- It reasons about other segments but not about obstacles, so it pushes segments
  into nodes.

Two guards turn it into a win, and **both are mutation-tested**:

1. An anchor may only slide along its own stub axis, and must stay
   `node_clearance` outside the node.
2. Any displacement whose segment newly enters a node interior, or an
   `ObstacleMap`-blocked cell, is reverted.

The two criteria in guard 2 are tracked **separately on purpose**. Merging them
masks the case of a segment that was already inside a clearance zone and newly
enters an interior.

## Consequences

- A routing implementation to maintain, justified by upstream being unusable
  rather than by preference. If `auto_route` is ever fixed, this decision is
  worth revisiting — but verify the clearance/anchor contradiction is actually
  gone rather than trusting a changelog.
- `layout.py` imports pyArchimate's **internal** layout surface (`ObstacleMap`,
  `Rectangle`, `RoutingConfig` from `pyArchimate.view.layout`), which carries no
  stability guarantee. This is the direct cause of the tight `~=1.12.0` pin — see
  decision-006.
- Do not "simplify" collinear separation to a bare upstream call. The guards are
  the reason it helps.
- Never run upstream `auto_layout` **after** routing: it preserves waypoints
  byte-for-byte, so moving nodes underneath them strands every bendpoint in empty
  canvas.
- `remove_uturn_waypoints` and `compute_corner_clearance` were evaluated and
  **rejected as no-ops** against this router. Their measured numbers are in
  `docs/LAYOUT_IMPROVEMENT_PLAN.md`; do not re-adopt them without new
  measurements.
- No system dependency. `uvx mcp-archimate` needs nothing but Python.

**Enforced by:** `layout.route_connections_around_nodes`,
`separate_collinear_connection_segments` and its two guards, the mutation tests
covering them, and the measurements in `docs/LAYOUT_IMPROVEMENT_PLAN.md`.
Extracted from ARC-015, ARC-022 and ARC-031.

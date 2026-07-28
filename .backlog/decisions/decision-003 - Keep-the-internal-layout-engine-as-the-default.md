---
id: decision-003
title: Keep the internal layout engine as the default
date: '2026-07-27 21:38'
status: accepted
---
## Context

`auto_layout_view` can place nodes two ways, selected per call by
`layout_engine`: this repository's own engine (`"internal"`) or pyArchimate's
upstream `auto_layout` (`"pyarchimate"`, added in ARC-030).

The obvious reading of the benchmark table favours upstream — its placement step
is about 3.6x faster. That reading is wrong twice over.

**On speed**, `auto_layout_view` is dominated by the shared routing epilogue, not
by placement. Upstream's airier placement gives the router *more* work, so below
the dense-routing gate the whole call is slower end to end: **157.9 ms versus
50.7 ms** on 43 nodes and 42 connections. It only wins past the gate — 1.3 ms
versus 5.3 ms at 200 nodes.

**On correctness**, upstream `auto_layout` has **zero collision detection**.
`assign_grid_cells` never reads node `w`/`h`, so the result is overlap-free only
while every node fits `LayoutConfig().grid_size`. One node a pixel over produces
overlapping boxes and still reports `success=True, warnings=[]`.

It also applies no `strategy`, no layer bands, no lane wrapping, no barycenter
alignment and no ArchiMate lane order.

## Decision

**`internal` is the default everywhere, on visual-quality grounds** — confirmed by
human side-by-side review of rendered output on 2026-07-26, not merely because it
came first. Omitting `layout_engine` is bit-for-bit backward compatible.

`pyarchimate` remains supported and must keep working, but:

- do not promote it to the default;
- do not recommend it as an improvement;
- do not cite the speed table as a reason to switch without stating that it loses
  end to end below the dense-routing gate.

`_require_pyarchimate_layout_is_safe` refuses an unsuitable view **before any
placement write**, measuring each top-level node's *subtree* bounding box (an
imported Archi view can have a child sticking outside its parent) and reading
`grid_size` from the dataclass at call time — never hardcode 240; upstream's own
docstring wrongly says 120.

## Consequences

- Two placement paths to maintain, sharing a prologue (band removal, junction
  clamp, group nesting and duplicate healing, note-position capture, group
  sizing, label and containment policy) and an epilogue (note restore, routing).
  Only the placement block between them branches.
- The prologue split is load-bearing: it is repair, not aesthetics. Branching
  `nest_grouped_nodes` away would stop healing legacy duplicates and look like the
  ARC-017 bug returned.
- `remove_layer_bands` must run **before** upstream placement — bands are
  top-level containers far wider than a grid cell.
- Layer bands are never re-added under `pyarchimate`: upstream's 4-bucket
  substring layer classifier disagrees with this repo's 6-row band labels, so
  members come out non-contiguous and the rectangles interleave.
- Upstream swallows every exception into `LayoutResult(success=False)` and never
  raises, so always check `result.success`.
- Never run upstream `auto_layout` **after** a routing pass: it preserves
  waypoints byte-for-byte, stranding every bendpoint in empty canvas.
- `ensure_all_relationships_in_views` rejects any engine but `internal` — its
  coverage layout is a fixed source/target pair grid that cannot honour an
  engine choice.

**Enforced by:** `layout.py`, `_require_pyarchimate_layout_is_safe`, and the
measurements in `docs/LAYOUT_IMPROVEMENT_PLAN.md`.

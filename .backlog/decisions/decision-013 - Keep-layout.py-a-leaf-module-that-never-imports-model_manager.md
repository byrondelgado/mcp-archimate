---
id: decision-013
title: Keep layout.py a leaf module that never imports model_manager
date: '2026-07-28 09:14'
status: accepted
---
## Context

`model_manager.py` had grown to roughly 3,900 lines and was doing two unrelated
jobs: adapting pyArchimate for the MCP tools, and computing diagram layout. The
layout half — lane assignment, wrapping, barycenter alignment, group nesting,
layer bands, label policy, obstacle-map routing, collinear separation — is a
self-contained geometry problem with no need for the manager's model-lifecycle
concerns.

Large files are also a practical problem for the AI agents that do most of the
work in this repository: a file that does not fit in context produces less
reliable edits.

The obvious extraction had a trap. Layout needs the model, and the manager needs
layout, so a naive split creates a circular import.

## Decision

**`layout.py` is a leaf module. It never imports `model_manager`.**

- Layout lives in `pyarchimate_mcp_server/layout.py` (~1,600 lines) as
  **module-level functions**, not a class. There is no layout object to
  construct and no state to thread.
- It reaches the model through **`view.model`** — the view it was handed already
  knows its model, so no back-reference to the manager is needed and no cycle
  can form.
- The manager **orchestrates**: `auto_layout_view` sequences the prologue,
  placement and epilogue, and keeps thin `_`-prefixed delegation stubs for the
  handful of helpers shared with non-layout code (view traversal, coverage
  predicate, routing dispatch, label text, node sizing, geometry).

The extraction was performed as a **zero-behaviour-change** refactor and verified
as such, rather than mixed with improvements.

## Consequences

- `model_manager.py` dropped to ~3,000 lines and is now purely the adapter
  boundary around pyArchimate. Tool and resource modules still never call
  pyArchimate directly.
- The dependency direction is one-way and must stay that way. If layout ever
  appears to need something from the manager, the fix is to pass it in as an
  argument — not to import upward.
- The delegation stubs look like indirection for its own sake. They are the
  seam: they let non-layout code keep calling a shared helper without importing
  `layout` everywhere, and they are why the split holds.
- `layout.py` is where the pyArchimate **internal** layout imports live
  (`ObstacleMap`, `Rectangle`, `RoutingConfig`), which concentrates the
  version-fragile surface in one file. That is deliberate, and it is what makes
  the tight pin in decision-006 auditable.
- `model_manager.py` is still large. Splitting it further is reasonable future
  work; it was kept out of this change so the refactor could be verified as
  behaviour-preserving.
- **A parallel `quality.py` extraction was considered and rejected.** The
  validation and quality-report code was a candidate for the same treatment, but
  it does not have layout's property of being a self-contained geometry problem:
  it is interleaved with the pyArchimate adapter calls it validates, so pulling
  it out would have produced two modules that both needed the manager rather than
  one leaf. Layout was extractable because `view.model` gave it everything it
  needed; quality has no equivalent handle. Revisit only if that changes.

**Enforced by:** the absence of any `model_manager` import in `layout.py`, and
the `view.model` access pattern throughout it. Extracted from ARC-018.

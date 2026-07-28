---
id: decision-006
title: Pin pyArchimate to 1.12.x but give the MCP SDK a range
date: '2026-07-27 21:38'
status: accepted
---
## Context

The two main dependencies are pinned in deliberately different *shapes*, which
reads as inconsistency unless the reason is recorded.

**`mcp` was over-pinned once already.** A three-part `~=1.21.1` capped the SDK at
1.21.2 and froze it for **eight months**. Nothing in this project needed the cap;
the SDK import surface is two lines in `mcp_app.py` — `FastMCP` and
`ToolAnnotations` — so the tight pin bought no safety and cost every intervening
improvement.

**`pyArchimate` is the opposite case.** `layout.py` imports its *internal* layout
surface — `ObstacleMap`, `Rectangle` and `RoutingConfig` from
`pyArchimate.view.layout` — which carries no stability guarantee whatsoever, and
`model_manager.py` is written throughout against 1.1x adapter patterns. A minor
bump can and does move things this project reaches into.

## Decision

**Pin by blast radius, not by habit.**

- **`mcp>=1.28.1,<2.0.0`** — an explicit range, deliberately *not* `~=`. The `<2`
  ceiling follows upstream's own v1/v2 branch split at 1.25.0: v2 renames
  `FastMCP` to `MCPServer` and moves low-level `Server` handlers to constructor
  parameters. Do not reintroduce the three-part shape.
- **`pyArchimate~=1.12.0`** — three-part, 1.12.x only. Every minor bump earns an
  evaluation task (as 1.11.2 did in ARC-012 and 1.12.0 in ARC-028) rather than
  arriving silently.
- **`pydantic>=2.11.0,<3.0.0`** and **`lxml>=6.1.0,<7.0.0`** — ranges to the next
  major, the ordinary case.

The **`[cli]` extra is dev-only**, in `[dependency-groups].dev`, not a runtime
dependency. It pulls in 7 packages transitively (`typer`, `rich`, `pygments`,
`markdown-it-py`, `mdurl`, `shellingham`, `annotated-doc`) for a console script
no runtime user invokes.

## Consequences

- pyArchimate upgrades are deliberate work with a task attached, not a lockfile
  refresh. That is the price of using its internal layout API, and it is paid
  knowingly.
- SDK improvements arrive without intervention, bounded by the v2 ceiling.
- `uv run mcp dev` still works for contributors, because `uv` installs dev groups
  by default. In a runtime-only install the `mcp` console script exits with
  `Error: typer is required` — dev tooling only.
- Dropping the extra does **not** shrink the HTTP or crypto tree: `uvicorn`,
  `starlette`, `sse-starlette`, `httpx`, `jsonschema`, `pydantic-settings`,
  `pyjwt`/`cryptography` and `click` are unconditional base dependencies of
  `mcp` and ship either way.
- If `pyArchimate` ever stabilises a public layout API, the pin can loosen. Until
  then it stays tight.

**Enforced by:** the pin shapes and their explanatory comments in
`pyproject.toml`, which are load-bearing — do not tidy them away.

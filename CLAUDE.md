# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Model Context Protocol (MCP) server for ArchiMate enterprise-architecture modeling, built on FastMCP and backed by the `pyArchimate` library (pinned to `~=1.12.0`). The server manages **one in-memory ArchiMate model per process** (the "active model"); every tool and resource operates on it. Creating or loading a model replaces the current one.

## Commands

Everything runs through `uv`:

```bash
uv sync                                             # install/sync deps (incl. dev group: pytest, ruff, mcp[cli])
uv run pytest                                       # run all tests
uv run pytest tests/test_model_manager.py           # run one test file
uv run pytest tests/test_workflow_tools.py::test_inspect_active_model_requires_loaded_model  # run one test
uv run ruff check                                   # lint
uv run ruff format                                  # format
uv run python -m pyarchimate_mcp_server.server      # run the server (or: uv run mcp-archimate)
uv run mcp dev pyarchimate_mcp_server/server.py     # run with MCP Inspector
```

The `mcp` console script behind `mcp dev` / `mcp install` comes from the **dev-only** `mcp[cli]` extra (see Dependency pins); `uv sync` installs dev groups by default, so it works from a clone but is not a runtime dependency.

Pytest options live in `pyproject.toml` (`testpaths = tests`, `-v --tb=short`). Ruff uses line length 88, target py310, and a broad rule selection — always run `uv run ruff check` after changes. `[tool.ruff.format]` excludes `*.md` on purpose (ruff >=0.16 reformats Python blocks inside Markdown, including docs and Backlog task files) — do not remove that exclusion. Two lint settings are likewise deliberate: `COM812` is in `ignore` because ruff's own formatter warns the rule conflicts with it, so do not move it back into `select`; and `PLC0415` is per-file-ignored for `tests/*`, where imports sit inside test bodies on purpose, after monkeypatching module state.

## Architecture

### Registration by import side effect

`pyarchimate_mcp_server/mcp_app.py` owns the shared `FastMCP` instance (`mcp`) plus the lifespan that creates the single `ArchimateModelManager` and exposes it via `AppContext` (the dataclass itself lives in `dependencies.py`). Tool, resource, and prompt modules register themselves by importing `mcp` and using its decorators (`@mcp.tool()`, `@mcp.resource(...)`, `@mcp.prompt(...)`).

`pyarchimate_mcp_server/server.py` is the entrypoint: it imports every tool/resource/prompt module *solely for the registration side effect*. **A new tool or resource module must be added to the imports in `server.py` or it will silently not register.**

Tools obtain the manager via `mcp.get_context().request_context.lifespan_context.model_manager` (each tools module has a `_model_manager()` helper). Tests monkeypatch this helper to inject a fresh manager.

### Layers

- `model_manager.py` (~3,200 lines) — the **only** adapter boundary around pyArchimate. Tool/resource modules never call pyArchimate directly. It handles model lifecycle, element/relationship/view CRUD, batch operations with rollback (`_run_with_rollback`), query filters, XML import/export, SVG rendering of a single view, folder-path normalization, semantic validation, quality reports/gates, and view layout. There are two **placement** engines, selected per call by `layout_engine` (see the section below); connection routing is engine-independent and always the MCP's own, delegating the corridor search to pyArchimate's `ObstacleMap` A* (MCP computes the anchors — upstream `auto_route()` is still unusable **through 1.12.0**: `RoutingConfig.node_clearance` is 25px while `auto_route`'s own anchors sit 13px off the node edge, so every corridor search starts on a blocked cell and routes nothing. Re-verified on 1.12.0; keep the MCP-side clearance-aware anchoring in `layout.route_connections_around_nodes`). An explicit `auto_layout_view` call ALWAYS lays out — there is deliberately no "preserve existing layout" heuristic (it inverted user intent and caused the historical group-member duplication bug). Group members are nested exactly once; legacy duplicate copies are healed on layout. Multi-layer views get labeled visual layer bands (diagram-only Archi Groups, opt-out `layer_bands=false`); wide lanes wrap at 1,600px and connected nodes align via barycenter placement. It also owns model-level metadata (`update_model_metadata`) and diagram-only notes (`add_note_to_view`).
- `layout.py` (~1,600 lines) — module-level layout functions (lanes/wrapping/barycenter, group nesting + healing, layer bands, label policy, obstacle-map routing + dogleg fallback, collinear segment separation). Reaches the model via `view.model`; never imports model_manager. The manager orchestrates via `auto_layout_view` and keeps thin `_`-prefixed delegation stubs for the few helpers shared with non-layout code.
  - **Collinear separation** (`separate_collinear_connection_segments`): routes are collected first, then connections that ended up sharing a corridor are pulled apart with pyArchimate's `displace_collinear_segments`, then bendpoints are written. The upstream helper alone is a *regression* — it moves the first/last waypoints, which are this repo's node anchors, off the node centerline (node-exit stubs go diagonal) and it pushes segments into nodes, since it reasons about other segments but not obstacles. Two guards make it a win and both are mutation-tested: an anchor may only slide along its own stub axis and must stay `node_clearance` outside the node; any displacement whose segment newly enters a node interior or an `ObstacleMap`-blocked cell is reverted (the two criteria are tracked *separately* — merging them masks a segment that was already in a clearance zone and newly enters an interior). Do not "simplify" this to a bare upstream call. Measured numbers, plus the rejection of `remove_uturn_waypoints` and `compute_corner_clearance` as no-ops on this router, are in `docs/LAYOUT_IMPROVEMENT_PLAN.md`.
- `relationship_rules.py` — deterministic, versioned relationship rule helpers built on pyArchimate's `ALLOWED_RELATIONSHIPS` matrix (ArchiMate 3.2-compatible). Provides valid-type lookup, intent-based recommendations (`serves`, `reads_data`, `realizes`, …), alternatives for invalid pairs, and deterministic repairs. The MCP is intentionally a *constraint engine*, not an architect: it enforces hard ArchiMate validity while the calling agent owns intent (decision-005; see also `docs/MCP_Feedback_Improvements.md`).
- `tools/` — MCP tools split by concern (45 tools total): `model_tools` (incl. `build_quality_report`, `assess_togaf_readiness`, `update_model` — the only writer for model-level name/documentation/properties), `element_tools`, `relationship_tools` (incl. `get_relationship_compatibility`, `recommend_relationship`, `repair_semantic_issues`), `view_tools` (incl. `auto_layout_view`, `add_note_to_view` — the diagram-only note, see the Diagram notes section — and `render_view_to_svg_file` — writes one view to an SVG **file** for a human; it never returns markup, never lays out, and `"svg"` is deliberately absent from `SUPPORTED_FORMATS` so it can never be mistaken for a third export format), `query_tools`, `workflow_tools` (agent-facing: `get_usage_guide`, `load_model_from_file` — loads AND inspects by default, `inspect_active_model`). Every tool declares `ToolAnnotations` (read-only / additive / idempotent / destructive — shared constants in `mcp_app.py`); keep annotations accurate when adding tools, and note that a tool writing a file is *idempotent*, not read-only, even when it never mutates the model. Invalid element/relationship type errors include did-you-mean suggestions in `error.details.suggestions`.
- `resources/` — read-only counterparts under the `pyarchimate://activemodel/...` URI scheme.
- `prompts.py` — MCP prompts guiding agent workflows (load → inspect → edit → validate → export).
- `models.py` — Pydantic detail shapes (`ElementDetail`, `RelationshipDetail`, `ViewDetail`, …) returned by tools.
- `constants.py` — derives supported element/relationship type catalogs from pyArchimate's `ARCHI_CATEGORY` at import time. Type lists are version-specific; **never hardcode them**.
- `responses.py` — every tool/resource returns the standard envelope: success `{"status": "success", "message", "data"}`; error `{"status": "error", "message", "error": {"code"}}`. Errors may carry a structured `error.details` dict (e.g. valid alternatives for an invalid relationship). Tools catch `ArchiMateMCPError` subclasses (`exceptions.py`, which store `.details`) and use the exception class name as the error code.

### Layout engines — `internal` (default) and `pyarchimate`

> **Why:** decision-003. The rules below are the operational contract; the record holds the reasoning and the measurements.

`layout_engine` selects the **node placement** algorithm for one call. It is never persisted: not a model setting, not a session default, never written to a view property, so it cannot appear in an export or in Archi's Properties tab. `"internal"` is the default everywhere and its code path is untouched, so omitting the parameter is bit-for-bit backward compatible.

`internal` is the default on visual-quality grounds, confirmed by human side-by-side review of rendered output on 2026-07-26 — not merely because it came first. Both engines are supported and `pyarchimate` must keep working, but do not promote it to the default, do not recommend it as an improvement, and do not read the speed table in `docs/USER_GUIDE.md` as a reason to switch: past the dense-routing gate it is faster, and still the worse diagram.

`auto_layout_view` runs a **shared prologue** for both engines (band removal, junction size clamp, `nest_grouped_nodes` + duplicate healing, `layout.note_positions` pin capture, group sizing, label and containment policy) and a **shared epilogue** (`layout.restore_note_positions` then `_route_or_simplify_connections`, so note pinning and MCP routing both run under both engines). Only the placement block in between branches. That split is load-bearing:

- The prologue is correctness and repair, not aesthetics. Branching `nest_grouped_nodes` away would stop healing legacy duplicates and would look like the ARC-017 bug came back.
- The note pin/restore pair is a *pair*. `restore_note_positions` is the only thing pinning notes under `pyarchimate` (the `internal` branch is separately protected by `placeable_nodes`), and dropping it fails exactly one test while the internal engine keeps passing — this already happened once, as dead code that captured the positions and threw them away. Its capture point is also fixed: after the last reparenting step and before the first placement step. See the Diagram notes section.
- `remove_layer_bands` must run **before** upstream placement. Bands are top-level Containers far wider than a grid cell; leaving them in guarantees overlaps.
- Layer bands are never re-added under `pyarchimate`. Upstream's 4-bucket substring layer classifier disagrees with the repo's 6-row ArchiMate band labels, so band members come out non-contiguous, the band rectangles interleave, and `add_layer_bands` also reparents via `node.move(band)`. This is correctness, not style.
- Both arms produce a band outcome that the epilogue copies onto the returned `ViewDetail` as `layer_bands_created` / `layer_bands_reason`. `add_layer_bands` returns `{"created", "reason"}` rather than `None` for this. Every declining path names itself (`single_layer_view`, `coverage_view`, `not_requested`, `strategy_does_not_use_bands`, `engine_does_not_support_bands`) because the `mcp:layer_bands` view property structurally cannot answer the question: an absent key and a legitimately unbanded single-layer view look identical, and a view that *used* to have bands keeps the property as an empty string after `remove_layer_bands` clears it in the prologue. Compute the outcome from the current call; never read it back from the property.

`"pyarchimate"` delegates placement to upstream `auto_layout` (`layout.layout_nodes_pyarchimate`). It applies no `strategy` (validated, not applied), no layer bands, no lane wrapping, no barycenter alignment and no ArchiMate lane order. Do not sell it as "faster" without qualifying: the placement step is ~3.6x faster, but `auto_layout_view` is dominated by the shared routing epilogue, so below the dense-routing gate the airier placement gives the router more work and the call is *slower* end to end (measured 157.9 ms vs 50.7 ms on 43 nodes / 42 connections; it wins only past the gate, 1.3 ms vs 5.3 ms at 200 nodes). **It has zero collision detection** — `assign_grid_cells` never reads node `w`/`h` — so it is overlap-free only while every node fits `LayoutConfig().grid_size`. One node a pixel over produces overlaps and still reports `success=True, warnings=[]`. `_require_pyarchimate_layout_is_safe` therefore refuses such a view *before* any placement write, using each top-level node's **subtree** bounding box (an imported Archi view can have a child sticking outside its parent) and reading `grid_size` from the dataclass at call time — never hardcode 240 (upstream's own docstring wrongly says 120). Two more rules: upstream swallows every exception into `LayoutResult(success=False)` and never raises, so always check `result.success`; and never run upstream `auto_layout` **after** a routing pass — it preserves waypoints byte-for-byte, so moving nodes underneath them strands every bendpoint in empty canvas.

`ensure_all_relationships_in_views` rejects any engine other than `internal`: its coverage layout is a fixed source/target pair grid that structurally cannot honour an engine choice.

### Coverage-view recognition

> **Why:** decision-008.

`layout.is_coverage_view` recognizes the generated coverage view by the `COVERAGE_VIEW_PROPERTY_KEY` marker (written by `_mark_coverage_view` on every view the MCP creates or adopts) or by an **exact** match against the caller's `coverage_view_name`. There is deliberately **no** `"coverage" in name.lower()` substring fallback — it silently captured authored views like "Data Coverage Analysis", which then skipped `add_layer_bands`, kept their redundant group-containment connectors (`_relocate_group_containment_connections_to_coverage` skipped them), and were laid out as generated scaffolding, none of it reported to the caller. Do not reintroduce it; three tests fail if you do. The marker survives a native `archi` round trip but not an exchange one — `_strip_dangling_view_properties` drops every view property from `archimate` output — so after an exchange reload, recognition depends on the caller passing `coverage_view_name` again.

### Diagram notes (`Label` nodes)

> **Why:** decision-009.

`add_note_to_view` creates an Archi Note: a visual `Label`-cat node with no element, no folder and no model-tree entry, plus optional annotation-only connector lines (`view.connect_note`) that create no relationship. Diagram-only Archi **Groups** (`Container`) remain out of scope — there is no tool to create one; the only Containers in a view are the layer bands `add_layer_bands` writes and whatever an imported file brought with it.

- **Notes are pinned across a layout run.** Captured by `layout.note_positions` after the last reparenting step (`nest_grouped_nodes`) and before the first placement step, restored by `layout.restore_note_positions` before routing. One path, both engines. Upstream `auto_layout` *does* place notes; the restore is what discards that placement, which is also why `oversized_nodes_for_pyarchimate` can skip notes without weakening the suitability guard. A top-level note is pinned absolutely; a nested note (import-only) is pinned as an offset from its parent, because Archi clips a child to its parent's rectangle. Any pass that moves nodes must skip notes: `placeable_nodes` in the internal branch, `layout_group_children` for a group's children, `_layout_coverage_view_pairs` for the coverage view (which has no pin/restore around it).
- **Notes are routing obstacles; Container bands are not.** `ROUTING_OBSTACLE_NODE_CATEGORIES = {"Element", "Label"}` — a band is decoration that must not deflect a route, a note is ink that must.
- **Note connectors are exempt from visual validation, narrowly.** `_is_annotation_connector` requires both a missing relationship *and* a `Label` endpoint; a `Container` endpoint or a vanished endpoint stays reportable.
- **Exchange export retypes note lines to `xsi:type="Line"`.** The schema types `relationshipRef` as a required `xs:IDREF` on `Relationship`, so writing a note line as a `Relationship` (which is all pyArchimate's writer can do) produces a document that fails keyref validation. `_rewrite_note_connectors_as_lines` fixes that; `_restore_exchange_note_connectors` rebuilds the lines on load, because pyArchimate's reader skips every `Line`. Both live on the exchange path only — the native `archi` writer already emits the right shape.

### Semantic validation modes and quality gates

> **Why:** decision-005 (constraint engine vs architect) and decision-007 (the deliberate duplicate loop).

Three modes: `"off"`, `"warn"`, `"strict"`.

- `add_relationship` / `add_relationships` accept `semantic_validation` (default `"warn"`) — checked against the relationship-rules matrix; `warn` creates the relationship but returns `data.semantic_warning` with valid alternatives; `strict` raises `InvalidRelationshipCombinationError` (with valid alternatives in `error.details`). Never silently: only `"off"` skips the check.
- `export_model_content` / `export_model_to_file` accept `quality_gate` (default `"off"`) — runs `build_quality_report` (visual + semantic + coverage checks) before export; `strict` blocks the export on failures.

**The MCP owns zero ArchiMate rules.** Every hard-validity verdict is delegated to pyArchimate: `check_invalid_conn` / `check_invalid_nodes` in `validate_model`, `check_valid_relationship` and `ALLOWED_RELATIONSHIPS` in `relationship_rules.py` (which declares the upstream matrix as its `rule_source`), `STANDARD_VIEWPOINTS` from `viewpoint_registry`. The validation layer is additive — it enriches upstream verdicts, it does not re-derive them. Two consequences:

- **`validate_semantics` deliberately does not check for dangling view nodes.** `validate_model` already reports them via `check_invalid_nodes`, and `build_quality_report` aggregates visual and semantic validation side by side, so the old `MISSING_NODE_ELEMENT` issue counted one dangling node twice. Upstream is also the stronger check (it catches an `Element`-cat node with no `ref` at all). Do not re-add it.
- **The relationship loop in `validate_semantics` is a deliberate duplicate of `check_invalid_relationships` — do not collapse it.** The verdicts are identical, but upstream calls `check_valid_relationship` *without* `raise_flg=True` and therefore throws away the reason string, returning bare relationship ids. `_semantic_relationship_issue` passes `raise_flg=True` precisely to capture `str(exc)`, then enriches it through `relationship_issue_details` (source/target names and types, `valid_alternatives`, `suggested_repairs`, `requires_decision`) — one opaque id upstream versus a 15-field actionable issue here. Replacing it with the upstream call would silently starve `repair_semantic_issues` and the did-you-mean suggestions in `error.details`. The code carries a comment saying so; keep it.

Note also that despite its name, pyArchimate's `checker_rules.yml` is not a rule engine — it is a metadata and ARIS type-map file. There is no unused upstream checker being duplicated.

### Response detail levels

> **Why:** decision-017.

`validate_semantics`, `auto_layout_view` and `connect_visible_relationships` take `detail` (`"summary"` default, `"full"` for the pre-0.8.0 payload), validated by the **public** `normalize_detail_level` — public because `auto_layout_view` is shaped in the tools layer, where the manager returns a `ViewDetail` its internal callers still need.

Two shaping rules are load-bearing:

- **The `validate_semantics` summary has no `issues` key at all** — not a truncated list. A shorter list would let a caller written against `full` silently read fewer issues than it asked for; a missing key fails loudly, which is exactly what five real call sites did when the default changed (`assess_togaf_readiness`, `repair_semantic_issues`, `_compact_issue_summary`, two tests — all corrected to `detail="full"`). Do not add a truncated `issues` back.
- **Error-severity issues are never grouped away.** `issues_by_code` groups by code; `errors` carries the error-severity issues in full so `is_valid: false` always arrives with its reason. Subject ids come from the ordered `SEMANTIC_ISSUE_IDENTITY_KEYS` tuple, not a blind `*_id` sweep — several issue shapes carry more than one id and only the first is the subject.

`auto_layout_view`'s summary must keep `bounds`: it is what makes the shape usable rather than merely small, since placing a note afterwards needs to know where the free canvas is. There is deliberately no `severity_filter` — the summary already separates errors from grouped warnings.

### Client-supplied ids are unique model-wide, not per namespace

pyArchimate keys concepts in five separate dicts (`elems_dict`, `rels_dict`, `views_dict`, `nodes_dict`, `conns_dict`), but the exported XML has **one** id space. `_require_unused_concept_id` therefore scans all five on every creation path — do not "optimize" it back to checking only the matching dict. Checking one dict let the same id belong to an element, a relationship and a view at once, and both writers then emitted that identifier twice in a single document: an `xs:ID` collision in the exchange format (the same defect class `_sanitize_exchange_output` repairs, in the opposite direction) and an ambiguous `archimateElement` reference in the native one. Neither round trip complains, because pyArchimate reads back through the same separate dicts.

Same-kind collisions keep their original message (`Element with ID 'x' already exists.`); cross-kind ones name the holder and the model-wide rule, with `existing_concept_kind` in `error.details`. `repair_semantic_issues(preserve_relationship_ids=True)` still works because it deletes before recreating — that ordering is now load-bearing and has a test.

### View metadata is validated before the view is touched

`create_view` and `update_view` call `_require_valid_viewpoint(properties)` **before** `model.add()` and before the first field assignment. `_apply_view_metadata` only mirrors the property onto pyArchimate's `primary_viewpoint` and **never raises** — matching the load path, which suppresses unknown slugs so a foreign file cannot fail to load. That is one gate, not two half-gates: when the check lived in `_apply_view_metadata` (after the mutation), a rejected viewpoint still left the view behind carrying the rejected value, and the natural retry hit a duplicate-id error. Do not move validation back after the mutation, and do not make `_apply_view_metadata` raise again.

The accepted values come from `viewpoint_catalogs()`, which `list_supported_types` (`data.viewpoints`) and the rejection message both read, so the advertised catalog cannot drift from the accepted one. Both namespaces are published separately because they overlap without either containing the other.

### Dependency pins — read before changing any of them

> **Why:** decision-006.

The pin *shapes* in `pyproject.toml` are deliberate and differ per package:

- `mcp>=1.28.1,<2.0.0` — an explicit range, deliberately **not** a three-part `~=`. `~=1.21.1` silently capped the SDK for eight months; do not reintroduce that shape. The `<2` ceiling follows upstream's own v1/v2 branch split (v2 renames `FastMCP` to `MCPServer` and moves low-level `Server` handlers to constructor params).
- The `[cli]` extra is **dev-only** (`[dependency-groups].dev`), not a runtime dependency. The whole SDK import surface is two lines in `mcp_app.py` (`FastMCP`, `ToolAnnotations`), so dropping the extra keeps `uvx mcp-archimate` installs lean; nothing in the package or tests imports typer/rich/click.
- `pyArchimate~=1.12.0` — deliberately a three-part `~=` (1.12.x only), *unlike* `mcp`. `layout.py` imports pyArchimate's **internal** layout surface (`ObstacleMap`, `Rectangle`, `RoutingConfig` from `pyArchimate.view.layout`), which carries no stability guarantee, so every minor bump earns an evaluation task rather than arriving silently.

### pyArchimate 1.12.x API constraints

The manager is written against specific pyArchimate 1.12.x patterns — documented in detail in `docs/TECHNICAL_ARCHITECTURE.md`. Key points:

- Create concepts with `model.add(concept_type=..., name=...)` and `model.add_relationship(rel_type=..., source=..., target=...)`. Calls like `model.add_element()`, `model.get_elem()`, `model.add_view()` **do not exist** in this version.
- Relationship types use pyArchimate names *without* the `Relationship` suffix (`Serving`, `Assignment`, `Influence`).
- `model.read(path)` needs a filesystem path — a temp file is used for string content.
- Native Archi export works on a *copy* of the model so writer compatibility adjustments never mutate the active model; folder IDs are stabilized so repeated exports diff cleanly; `influenceStrength` is rewritten to Archi's native `strength` attribute; `AndJunction`/`OrJunction` are converted to Archi's single `Junction` concept with a `type="and"/"or"` attribute; pyArchimate viewpoint slugs are rewritten to Archi's canonical viewpoint ids (`ARCHI_VIEWPOINT_ID_BY_SLUG`); top-level folder labels match stock Archi ("Technology & Physical", "Implementation & Migration"). Exchange (`archimate`) exports are sanitized to drop dangling view-property references (pyArchimate's exchange writer — still true in 1.12.0 — emits `propertyDefinitionRef` for view properties without declaring them, which is schema-invalid). **Never write to stdout anywhere in the server**: stdio transport uses stdout as the JSON-RPC channel; stray prints corrupt framing and hang clients (use `logging`, which goes to stderr).
- `Model.check_invalid_conn()` only became functional in 1.12.0 (in 1.11.x it could return `[]` or raise `KeyError`), so `validate_model()` is no longer vacuously true — it reports real orphan visual connections. That result flows into `build_quality_report`, the `pyarchimate://activemodel/validation` resource, `inspect_active_model`, and the export `quality_gate`, so a model carrying orphan connectors that passed silently before can now block a `quality_gate="strict"` export. pyArchimate logs those orphans through `logging` (stderr), so the stdio channel stays clean.

### The untrusted-input boundary — `_validate_xml_content` runs first, always

> **Why:** `SECURITY.md`; the filesystem boundary was decision D8 in doc-001, deferred out of 0.7.0 and implemented in 0.8.0 by ARC-050.

Users load `.archimate` files they did not author, so the load path is where hostile input reaches this server. `load_model_from_string` calls `_validate_xml_content` **before** anything else touches the content: it rejects any `<!DOCTYPE` or `<!ENTITY` outright (killing XXE and billion-laughs in one step, independently of lxml's defaults), caps size at `MAX_MODEL_CONTENT_BYTES`, parses with `resolve_entities=False, no_network=True, recover=False, huge_tree=False`, and allow-lists the root tag. `load_model_from_file` reads the file and delegates to `load_model_from_string` — **never give a path straight to pyArchimate's `model.read()`**, which would skip all of it.

Two constraints follow, both load-bearing:

- **`_restore_exchange_note_connectors` re-parses the raw content with a bare `etree.fromstring`, and that is safe *only because* validation already ran.** Moving, skipping or reordering the validation reintroduces XXE. The other bare parses (`_svg_pixel_size`, `_finalize_archi_output`, `_sanitize_exchange_output`) only ever see content this server generated.
- **The tests in `tests/test_security.py` use payloads with a *valid* ArchiMate root on purpose.** With a junk root the allow-list rejects them first and the tests pass while proving nothing about entity handling. They also assert a canary file's contents never surface, and carry a control test proving the payload still leaks against a permissive parser — so the suite cannot decay into testing nothing. Verified load-bearing by mutation: deleting the DTD check fails four tests, and the external-DTD payload then *loads successfully*.

### The filesystem boundary — `filesystem.py` gates every path

`filesystem.py` is a leaf module (stdlib + `exceptions` only, never imports `model_manager`) so both the manager and the tools layer can call it. All three file tools go through it: `load_model_from_file` via `resolve_read_path`, and `export_model_to_file` / `render_view_to_svg_file` via the manager's `_resolve_output_path`, which is now a one-line delegation to `resolve_write_path`. Adding a fourth file tool means routing it through here too.

- **`MCP_ARCHIMATE_ALLOWED_READ_ROOTS` / `_WRITE_ROOTS` are read at call time, never cached.** A client may set them after import, and tests change them per case.
- **Unset defaults to `Path.home()`.** Deny-by-default would break the README quickstarts, which write to `~/Desktop`; unrestricted would leave the protection reachable only by someone who already knew the variables existed. This is a documented default, not a placeholder.
- **`Path.expanduser().resolve()` is what makes it a real check.** It expands `..` and follows symlinks across the whole path *including a tail that does not exist yet*, so a link inside an allowed root pointing out of it resolves to its true target and fails containment. Roots are resolved too, so a symlinked root still matches. Never replace this with string prefix matching.
- **A relative allowed-root is rejected (`INVALID_ALLOWED_ROOTS`), not resolved against the CWD.** The boundary must not depend on where the client happened to launch the server.
- **The read check runs before the existence check** in `load_model_from_file`, so the tool cannot be used to probe for files it may not read. Do not reorder them.
- **`_validate_xml_content` still runs first on content.** The roots check is about *where*, not *what*; neither substitutes for the other.

This is **not** a sandbox: enforcement is in-process and the server still runs as the launching account. Do not describe it as sandboxed. `tests/conftest.py` widens the roots to the temp directory for the suite, because pytest's `tmp_path` is outside home on macOS — that is a widening, not a bypass, so every file test still exercises the real boundary code.

### Two export formats — do not confuse them

> **Why:** decision-004.

- `output_format="archi"` → Archi's native `.archimate` XML (opens directly in Archi).
- `output_format="archimate"` (default) → Open Group exchange XML (must be *imported* into Archi, not opened).

There is no third format. SVG is a *rendering* produced by `render_view_to_svg_file` for a human to look at; it is not importable and must never be added to `SUPPORTED_FORMATS` or to the export tools.

Folder roots are normalized (`Business`, `/Business`, `business` → `/Business`; `Implementation` → `/Implementation & Migration`).

## Testing conventions

Tests call async tool functions directly with `asyncio.run(...)` (no MCP client involved), construct `ArchimateModelManager` instances directly, and monkeypatch each tools module's `_model_manager` to inject them. Assertions target the response envelope (`response["status"]`, `response["data"]`, `response["error"]["code"]`).

## Documentation to keep in sync

Tool-surface or behavior changes are expected to update the matching docs in the same change (recent commits follow this pattern):

- `CHANGELOG.md` — Keep a Changelog format, newest version first. Only user-visible changes go here (tool surface, behavior changes, dependency pins, fixes, known limitations) — not refactors, test-only work, or doc syncs. A release bump touches `pyarchimate_mcp_server/__init__.py` (the **single source** of the version — `pyproject.toml` reads it via `[tool.hatch.version]`) and `uv.lock` together; the `vX.Y.Z` tag on `main` then triggers the release workflow, which fails if the tag, `__version__` and the CHANGELOG disagree. Runbook in `CONTRIBUTING.md`, design in decision-016. **Verify an action tag resolves before pinning it** — reading the latest release name is not the same check, and that mistake broke every CI job once.
- `README.md` — public-facing: what it is, `uvx` install, client configuration, quickstarts, tool-surface summary, security, credits, license.
- `docs/USER_GUIDE.md` — the public, client-facing reference (tool parameters, response schemas, workflows). It owns the full tool and resource tables; do not restate them elsewhere.
- `docs/TECHNICAL_ARCHITECTURE.md` — implementation-level design, pyArchimate usage patterns, and the glossary. Absorbed the retired `SDD.md` and `IMPLEMENTATION_PLAN.md` in 0.7.0.
- `docs/LAYOUT_IMPROVEMENT_PLAN.md` — layout roadmap and the *measurements*; update when layout behavior changes.
- `docs/MCP_Feedback_Improvements.md` — PRD for the quality/validation tool suite (relationship rules, quality gates, TOGAF readiness).
- `.backlog/decisions/` — the decision records. **Rationale lives here**, not spread across design docs. When a decision changes, update the record; when a section of this file explains a *why*, it should link a record rather than restate it.
- `CONTRIBUTING.md` / `SECURITY.md` — contributor workflow and the trust model.

Retired in 0.7.0 and not to be recreated: `docs/SDD.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/UPGRADE_REPORT_2026-07-24.md`, `docs/PYPI_PUBLIC_RELEASE_PLAN.md`, `docs/mcp_documentation.md`. The first four were point-in-time plans and reports that drifted; the last was a vendored upstream snapshot. Historical Backlog tasks still reference them — that is accurate history, not a broken link to repair.

## Repository notes

- `AGENTS.md` is the Codex entrypoint and delegates here; keep this file the single canonical instruction body.
- Project agent skills live in `.agents/skills/` (canonical location). `.claude/skills` is a relative symlink to it — edit skills only under `.agents/skills/` and never replace the symlink with a real directory.
- Agent support is deliberately scoped to **Claude Code and Codex only**. Task Master and Windsurf tooling was removed in ARC-040; do not reintroduce it or build on it. **The server needs no API keys or secrets of any kind** — an env file in this repo is always a mistake, and `.gitignore` blocks the whole family. The only environment variables it reads are `MCP_ARCHIMATE_ALLOWED_READ_ROOTS` / `_WRITE_ROOTS` (see the filesystem boundary section); both are optional, neither is a credential.
- `.codex/config.toml` is a *portable example* for contributors, not a working local config. It must never contain an absolute user-specific path.
- **Decisions are the one exception to "manage tasks only through the CLI".** `backlog decision create <title> [-s status]` takes only a title and a status — no `--content` flag, no `update` subcommand, no MCP tool — so it scaffolds the frontmatter, id and `## Context` / `## Decision` / `## Consequences` headings, and the body is written into the file. Intended workflow, not a workaround; leave the frontmatter alone. Tasks, documents and milestones all have CLI paths for their content and must use them.
- Backlog: task prefix `ARC`, config in `.backlog/config.yml`. The board starts at the open work; completed pre-release task files were removed for the public release (ARC-051) after their durable rationale was extracted into `.backlog/decisions/`. **ARC numbers referenced in decisions and code comments are provenance markers, not links** — the task files they name are gone by design. Check the live board with `backlog task list --plain`; manage tasks only through the `backlog` CLI.

<!-- BACKLOG.MD GUIDELINES START -->
<CRITICAL_INSTRUCTION>

## Backlog.md Workflow

This project uses Backlog.md for task and project management.

**For every user request in this project, run `backlog instructions overview` before answering or taking action.**

Use the overview to decide whether to search, read, create, or update Backlog tasks.

Use the detailed guides when needed:
- `backlog instructions task-creation` for creating or splitting tasks
- `backlog instructions task-execution` for planning and implementation workflow
- `backlog instructions task-finalization` for completion and handoff

Use `backlog <command> --help` before running unfamiliar commands. Help shows options, fields, and examples.

Do not edit Backlog task, draft, document, decision, or milestone markdown files directly. Use the `backlog` CLI so metadata, relationships, and history stay consistent.

</CRITICAL_INSTRUCTION>
<!-- BACKLOG.MD GUIDELINES END -->

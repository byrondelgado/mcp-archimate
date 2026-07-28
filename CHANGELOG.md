# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.2] - 2026-07-28

Documentation only. No code or tool behaviour changed.

### Changed

- **README and User Guide no longer contradict each other on installation.**
  `docs/USER_GUIDE.md` predated the PyPI release and still opened with
  `git clone <repository-url>` while the README said "nothing to clone". The
  User Guide now leads with `uvx mcp-archimate` and treats the source checkout
  as the contributor path. Both documents now describe the same four MCP clients
  (Claude Code, Claude Desktop, Codex, MCP Inspector) with identical
  configuration and the same `archimate` server key, so prompts stay portable
  between them. (ARC-054)
- **The User Guide documents the security model.** It was previously silent on
  the filesystem trust boundary and on model content being untrusted input —
  the one thing worth knowing before pointing an agent at your disk. (ARC-054)

### Added

- **Worked example prompts in the README**, covering building a small model,
  exploring an existing one, editing it, improving it, validating and exporting,
  and one full end-to-end build. Editing and improving an existing model — the
  common case once a model exists — had no example at all before. (ARC-054)
- **Troubleshooting for two things that look like faults and are not**: an MCP
  client showing no tools (now with a way to tell a broken server from a broken
  config), and the server appearing to hang, which is correct stdio behaviour.
  (ARC-054)

### Fixed

- Stale references in the User Guide: the server was still described as
  `archimate-mcp` (renamed in 0.7.1), and the `mcp[cli]` section described
  Claude Desktop install workflows that no longer exist. (ARC-054)

## [0.7.1] - 2026-07-28

### Fixed

- **The server reported the MCP SDK's version as its own.** `initialize` returned
  `serverInfo` as `archimate-mcp 1.28.1` — the pre-rename name, and the SDK
  version rather than this package's. `FastMCP` accepts no `version` argument, so
  the low-level `Server` kept `version=None` and fell back to `pkg_version("mcp")`,
  meaning the reported version tracked whichever SDK release was pinned. Clients
  now show `mcp-archimate` and the real package version. Display metadata only —
  no protocol behaviour changed — but a version that follows the SDK is
  misleading when diagnosing a problem against a specific release. (ARC-053)

## [0.7.0] - 2026-07-28

**First public release.** The project is now open source on GitHub and published
to PyPI as `mcp-archimate`, installable with `uvx mcp-archimate`. No tool, resource
or prompt behaviour changed in this release — the surface is the same 45 tools,
9 resources and 4 prompts as 0.6.0.

### Changed

- **License is now GPL-3.0-or-later** (was a nominal MIT classifier with no
  `LICENSE` file). This is inherited, not chosen: `pyArchimate` is GPL-3.0-only
  and is a required runtime dependency, so the combined work users run is
  governed by the GPL. Using the server does **not** put your models under the
  GPL, and the license does not reach the agent or client calling the server
  across the stdio process boundary. See `LICENSE`, `NOTICE`, and
  `decision-001`. (ARC-041)
- **Package metadata is now accurate.** Real author and project URLs, keywords,
  corrected classifiers, and the version single-sourced from
  `pyarchimate_mcp_server/__init__.py` via `[tool.hatch.version]` — it is no
  longer duplicated in `pyproject.toml`. (ARC-042)
- **Documentation restructured for a public audience.** The README is now
  install-first; `docs/README.md` indexes what remains and names an owner for
  each document. (ARC-043)

### Added

- **`LICENSE`** (full GPL-3.0 text) and **`NOTICE`**, crediting pyArchimate and
  Xavier Mayeur, and recording the licenses of the other runtime dependencies.
  (ARC-041)
- **`SECURITY.md`** — vulnerability disclosure, supported versions, and a plain
  statement of the trust model: the server runs with the filesystem rights of
  whoever launches it, and model content is untrusted input that can carry prompt
  injection. A README "Security considerations" section covers the same ground.
  (ARC-045)
- **`CONTRIBUTING.md`** — setup, the `dev`/`main` branch model, the Backlog
  workflow, and how to write a decision record. (ARC-044)
- **Fifteen architecture decision records** in `.backlog/decisions/`, capturing
  the load-bearing choices that were previously only prose warnings in
  `CLAUDE.md` or buried in task history — including why connection routing is
  implemented here rather than delegated upstream, why an explicit layout call
  never preserves existing positions, and why native Archi export has to repair
  the connection type. (ARC-044, ARC-051)
- **`tests/test_security.py`** — nine adversarial tests of the untrusted-input
  boundary covering XXE via inline, external and parameter entities, entity
  expansion, and the same payloads through `load_model_from_file`. No
  vulnerability was found; the existing defences were verified rather than
  assumed. (ARC-045)
- **Continuous integration** — lint, format check, and the test suite on Python
  3.10 through 3.13, plus a build and an sdist hygiene gate on every pull
  request. (ARC-046)
- **Tag-triggered releases** via PyPI Trusted Publishing, with no long-lived
  credential stored anywhere. (ARC-047)

### Removed

- **Task Master and Windsurf tooling**, and the local configuration that came
  with them. Agent support is now scoped to Claude Code and Codex. The server
  itself needs no API keys or environment variables. (ARC-040)
- **A 5 MB third-party Archi user guide PDF** and a vendored snapshot of the MCP
  SDK documentation, neither of which was ours to redistribute or could stay
  current. (ARC-040)
- **Four superseded documents** — `docs/SDD.md`, `docs/IMPLEMENTATION_PLAN.md`,
  `docs/UPGRADE_REPORT_2026-07-24.md` and `docs/PYPI_PUBLIC_RELEASE_PLAN.md`.
  The SDD's glossary survives as an appendix to
  `docs/TECHNICAL_ARCHITECTURE.md`. (ARC-043)

### Fixed

- **The source distribution shipped internal files.** The 0.6.0 sdist was 4.8 MB
  and contained `.taskmaster/`, `.backlog/`, agent configuration and the Archi
  PDF. `[tool.hatch.build.targets.sdist]` now uses an explicit allow-list, so
  anything added to the repository is excluded by default. The sdist is **199 KB**
  and CI fails the build if a forbidden path reappears. (ARC-042, ARC-046)

### Known limitations

- **No filesystem sandboxing.** `load_model_from_file`, `export_model_to_file`
  and `render_view_to_svg_file` accept any path the launching user can reach, and
  exports overwrite without prompting. Configurable allowed roots are planned
  (ARC-050); until then the boundary is whatever you impose from outside, such as
  a container or a dedicated account. Documented in `SECURITY.md`.

### Note on history

The git history was reset to a single root commit for the public release. The
prior commits described an earlier architecture — FastAPI routes, a Graphviz
layout engine, a different task workflow — that no longer matches the code, so
keeping them would have been more misleading than useful. The decision records
in `.backlog/decisions/` are the project's memory from here. See `decision-010`.
(ARC-048)

## [0.6.0] - 2026-07-27

Tool surface grows from 43 to 45. Dependencies move to MCP SDK 1.28.1 and
pyArchimate 1.12.0.

### Added

- **`render_view_to_svg_file`** — render a single view to an SVG file so a
  human can look at the diagram without installing Archi. File-only on
  purpose: it returns a path plus small metadata and never the markup,
  because an agent cannot see an image and a 120-element view is ~32k
  tokens of SVG text. `"svg"` is deliberately absent from
  `SUPPORTED_FORMATS` — it is a rendering, not a third export format.
  (ARC-029)
- **Selectable `layout_engine`** — `"internal"` (default) or
  `"pyarchimate"`, choosing the node **placement** algorithm for one call.
  Never persisted: not a model setting, not a session default, never
  written to a view property, so it cannot appear in an export or in
  Archi's Properties tab. Omitting the parameter is bit-for-bit backward
  compatible. `"pyarchimate"` is guarded by
  `_require_pyarchimate_layout_is_safe`, which refuses a view whose nodes
  exceed `LayoutConfig().grid_size` *before* writing any coordinate —
  upstream `assign_grid_cells` never reads node width or height and still
  reports `success=True, warnings=[]` when it overlaps them. (ARC-030)
- **`add_note_to_view`** — diagram-only Archi Notes with optional
  annotation connector lines, in one call. Notes carry no element, no
  folder and no model-tree entry, so they stay out of `query_elements`,
  `count_by_type`, `list_orphan_elements` and coverage. `auto_layout_view`
  pins note coordinates across a layout run under both engines, and notes
  act as routing obstacles. (ARC-033)
- **`update_model`** — model-level name, documentation and properties are
  now writable on an already-loaded model, following the updates-dict
  convention of `update_element` / `update_relationship` / `update_view`.
  `create_empty_model` accepts an optional description, and
  `create_model_from_spec` accepts them in its model-level block.
  Previously model documentation was readable but nothing could write it,
  so it was always null for MCP-created models. (ARC-034)
- **Collinear connection-segment separation** — connections that end up
  sharing a corridor are pulled apart after routing. Measured on a dense
  45-node / 50-connection view: collinear overlap pairs 26 → 9, overlapping
  ink 3235 → 1950 px, at a cost of 3 ms in the routing pass, with
  non-orthogonal segments, segments through node interiors, U-turns and
  anchor centering all unchanged. Wrapped in two guards the upstream helper
  lacks, both mutation-tested. (ARC-031)

### Changed

- **MCP Python SDK `1.21.2` → `1.28.1`.** The pin shape changed from
  `mcp[cli]~=1.21.1` to `mcp>=1.28.1,<2.0.0` — an explicit range, because
  the three-part compatible-release operator had capped the project at
  1.21.2 and froze the framework for eight months and seven minor releases.
  The `<2` ceiling follows upstream's own v1/v2 branch split. (ARC-027)
- **The `[cli]` extra is no longer a runtime dependency.** It moved to
  `[dependency-groups].dev`, where `uv run mcp dev` and `uv run mcp install`
  still find it. The server imports only `FastMCP` and `ToolAnnotations`,
  so public installs stay lean. (ARC-027)
- **pyArchimate `~=1.11.2` → `~=1.12.0`** (lock 1.11.3 → 1.12.0). The pin
  stays a three-part `~=`, unlike `mcp`, because `layout.py` imports
  pyArchimate's *internal* layout surface, so every minor bump earns its
  own evaluation task. (ARC-028)
- **`validate_model` now reports real orphan visual connections.**
  `Model.check_invalid_conn()` only became functional in 1.12.0 — on 1.11.x
  it could return `[]` or raise `KeyError`, so the check was vacuously
  true. **This is a behaviour change for existing callers:** a model
  carrying orphan view connectors that previously passed
  `quality_gate="strict"` can now be blocked. The result also flows into
  `build_quality_report`, the `pyarchimate://activemodel/validation`
  resource, and `inspect_active_model`. (ARC-028)
- Development dependencies refreshed: ruff `0.11.13` → `0.16.0`, pytest
  `9.0.3` → `9.1.1`, pydantic `2.12.4` → `2.13.4`, lxml `6.1.0` → `6.1.1`.

### Fixed

- **Note connector lines made Archi refuse to open a view.** pyArchimate
  types every diagram connection as `archimate:Connection`
  (`DiagramModelArchimateConnection`) and only omits
  `archimateRelationship` for annotation lines, so Archi built a
  concept-backed connection with no concept, threw a `NullPointerException`
  and reported "Failed to create the part's controls" with the whole view
  unopenable. Native exports now retype those to
  `archimate:DiagramModelConnection`, keyed on the absence of
  `archimateRelationship` rather than on note knowledge. Confirmed by
  opening a real export in Archi 5.9. **Files already exported with note
  connector lines must be re-exported.** (ARC-036)
- **Annotation-only view connectors no longer fail visual validation.**
  Since the 1.12.0 upgrade a single note could block a
  `quality_gate="strict"` export for a reason the caller could not act on.
  The exemption is narrow — it requires an unresolvable relationship ref,
  both endpoints resolving, *and* at least one `Label` endpoint — so a
  dangling connector between two element-backed nodes, or a note connector
  whose other endpoint vanished, is still reported. Archi Group
  (`Container`) endpoints are deliberately not exempt. (ARC-032)
- **One dangling view node counted twice in quality reports.**
  `validate_semantics` no longer emits `MISSING_NODE_ELEMENT`;
  pyArchimate's `check_invalid_nodes` already reports the same node through
  `validate_model`, and `build_quality_report` shows visual and semantic
  validation side by side. Upstream is also the stronger check — it catches
  an `Element`-cat node carrying no ref at all. The quality gate is not
  weakened: such a node still fails `visual_validation`, which the gate
  tests independently of `allow_semantic_issues`. (ARC-035)
- **Any view named like "coverage" was treated as the generated coverage
  view.** `layout.is_coverage_view` ended in a
  `"coverage" in view_name.lower()` substring fallback, so an authored
  "Data Coverage Analysis" silently skipped `add_layer_bands`, kept its
  redundant group-containment connectors, and was laid out as generated
  scaffolding. Recognition is now the marker property or an exact
  `coverage_view_name` match. (ARC-037)
- `update_model_metadata` validated properties *after* writing name and
  documentation, so a rejected update left a partially mutated model.
  (ARC-034)
- Spec-level properties reached `_apply_properties` unchecked and raised a
  raw `AttributeError` past the response envelope. (ARC-034)
- Hardened `None`-concept handling across the manager after the 1.12.0
  adoption. (ARC-028)

### Known limitations

- **The coverage-view marker does not survive an exchange round trip.**
  `_strip_dangling_view_properties` drops every view property from
  `archimate` output, so after an exchange reload, recognition depends on
  the caller passing `coverage_view_name` again. A native `archi` round
  trip preserves it.
- **An `archi` export-then-reload keeps a note but drops its connector
  lines.** pyArchimate's native Archi reader discards connections that
  carry no `archimateRelationship`. The Open Group exchange format
  round-trips both the note and its connector lines.
- **`internal` remains the recommended layout engine.** A human compared
  rendered output from both engines side by side on 2026-07-26 and judged
  `internal` to produce the better diagrams. `pyarchimate` is supported as
  a deliberate alternative, not a drop-in improvement: it applies no
  `strategy`, no layer bands, no lane wrapping, no barycenter alignment,
  and it is *slower* end to end below the dense-routing gate because its
  airier placement gives the shared router more work.
- **pyArchimate's `auto_route()` is still unusable through 1.12.0.**
  `RoutingConfig.node_clearance` is 25px while `auto_route`'s own anchors
  sit 13px off the node edge, so every corridor search starts on a blocked
  cell and routes nothing. Connection routing stays MCP-side, delegating
  only the corridor search to `ObstacleMap` A*.

## [0.5.0] - 2026-07-04

Improved layout and tools utilisation. See the `v0.5.0` tag and the commit
history for detail; this file starts at 0.6.0.

## [0.4] - 2026-07-04

Stable and acceptable diagramation after the pyArchimate 1.11.2 upgrade.

[0.6.0]: https://github.com/byrondelgado/mcp-archimate/releases/tag/v0.6.0
[0.5.0]: https://github.com/byrondelgado/mcp-archimate/releases/tag/v0.5.0
[0.4]: https://github.com/byrondelgado/mcp-archimate/releases/tag/v0.4

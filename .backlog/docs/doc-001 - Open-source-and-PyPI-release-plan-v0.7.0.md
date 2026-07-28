---
id: doc-001
title: Open-source and PyPI release plan (v0.7.0)
type: specification
created_date: '2026-07-27 21:03'
updated_date: '2026-07-28 09:51'
---
## Purpose

Take `mcp-archimate` from a private, single-author repository carrying eight months of
tooling residue to a public, GPL-3.0-or-later project on GitHub and PyPI, installable
with `uvx mcp-archimate`, with a repeatable tag-driven release pipeline.

Decided with the author on 2026-07-27. This document is the durable record of *what*
and *why*; the executable steps live in the ARC tasks that reference it.

## Baseline (verified 2026-07-27)

- 167 tests pass, `ruff check` clean, `ruff format --check` clean.
- 54 commits, all authored by Byron Delgado — sole copyright holder, free to relicense.
- Remote `byrondelgado/mcp-archimate` exists and is **private**; 0 forks, 0 stars.
- Tags `v0.4`, `v0.5.0`, `v0.6.0`; branches `main`, `dev`, `fearure/fix-load_model_from_content`.
- `mcp-archimate` is unclaimed on PyPI (HTTP 404).
- 45 MCP tools, stdio transport only.

## Problems this release fixes

1. **A year of private development history.** The commit history describes an
   earlier architecture and carries local development tooling and configuration
   that has no place in a public repository.
2. **License conflict.** `pyproject.toml` declares the MIT classifier, but
   `pyArchimate` 1.12.0 is `GPL-3.0-only` and the server cannot run without it.
3. **The sdist ships everything.** The 0.6.0 sdist is 4.8 MB and contains
   `.taskmaster/`, `.windsurfrules`, `.roomodes`, `.env.example`, `.backlog/`,
   `.claude/`, `.codex/`, `.agents/`, and a 5 MB third-party
   `docs/inputs/Archi 5.9.0 - User Guide.pdf` that must not be redistributed.
4. **Placeholder metadata.** `authors = MCP ArchiMate Team <team@example.com>`,
   URLs point at `github.com/example/mcp-archimate`, no `LICENSE` file.
5. **No CI.** No `.github/` directory; nothing verifies a PR or automates a release.
6. **Version duplicated.** `pyproject.toml` and `pyarchimate_mcp_server/__init__.py`
   each hardcode the version independently.
7. **Undocumented filesystem reach.** `load_model_from_file`, `export_model_to_file`
   and `render_view_to_svg_file` operate on any path the launching user can reach,
   with no `SECURITY.md` and no disclosure path.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Relicense to **GPL-3.0-or-later** | `pyArchimate` is GPL-3.0-only and is a hard runtime dependency. Matching it is unambiguous and honest about what users run. MCP servers are separate processes speaking JSON-RPC over stdio, so copyleft attaches to distributing this server — not to the agent that calls it, nor to the ArchiMate models users produce. |
| D2 | **Squash to a single root commit** | The author accepted losing history. The pre-release commits describe an architecture that no longer exists, so filtering would pay the full cost of a rewrite while keeping a misleading narrative. See decision-010. |
| D4 | First public version is **0.7.0** | The open-sourcing work is itself user-visible (license, metadata, removals, docs, CI), so it earns a CHANGELOG entry. Leaves 0.6.0 as the last private version. |
| D5 | Keep `.backlog/`, `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.agents/`, `.codex/` **in the repo, out of the sdist** | The task history and agent instructions are genuine context for contributors; PyPI users have no use for them. |
| D6 | Drop Task Master residue and Windsurf support | `.taskmaster/`, `.windsurfrules`, `.roomodes`, `.env`, `.env.example`, `.windsurf/`. Agent support narrows to Claude Code and Codex. |
| D7 | Decisions recorded as **Backlog decisions** | `.backlog/decisions/` already exists and Backlog is the project's PM tool. Chosen over a separate `docs/adr/` tree. |
| D8 | **Document** filesystem reach now, **implement** allowed roots next | Normal for a local stdio MCP server launched under the user's own credentials. Blocking the release on it is disproportionate; leaving it undocumented is not. XML entity handling gets verified as part of this, since loading untrusted `.archimate` files is the sharper risk. |
| D9 | **Tag-triggered Trusted Publishing** | OIDC removes long-lived PyPI credentials from GitHub entirely. A protected `pypi` environment adds a human approval gate. |
| D10 | `dev` is the integration branch, `main` the release branch | Tags are cut on `main`; day-to-day work merges into `dev`. |

## Scope

### In scope

- History reset, branch and tag hygiene.
- Removal of Task Master and Windsurf residue, empty directories, and
  non-redistributable third-party files.
- `LICENSE` (GPL-3.0), SPDX metadata, and attribution to pyArchimate.
- Accurate packaging metadata, single-sourced version, sdist allow-list.
- Documentation consolidation and a public-first README.
- `SECURITY.md` and a README security section.
- Backlog decisions capturing the load-bearing choices already pinned in `CLAUDE.md`.
- `ci.yml` and `release.yml` GitHub Actions workflows.
- TestPyPI validation, then PyPI publication of 0.7.0.

### Out of scope

- Streamable HTTP or SSE transport; this package stays stdio-only.
- Allowed-root filesystem enforcement (documented now, separate task).
- Any change to the 45-tool MCP surface or to layout behaviour.
- Hosted or multi-tenant deployment; OAuth; cloud persistence.
- Bumping `pyArchimate` beyond `~=1.12.0`.

## Design

### Phase A — History reset

Build a single root
commit from the cleaned worktree, point `main` and `dev` at it, force-push both,
delete the remote tags `v0.4`/`v0.5.0`/`v0.6.0` and the stale
`fearure/fix-load_model_from_content` branch, and expire the local reflog before
`git gc --prune=now`.

`v0.7.0` is tagged later, at release time, on `main`.

### Phase B — Repository cleanup

Delete: `.taskmaster/`, `.windsurfrules`, `.roomodes`, `.env`, `.env.example`,
`.windsurf/`, `exports/`, `scripts/`, `docs/inputs/` and
`docs/mcp_documentation.md`.

Rewrite `.codex/config.toml`, which currently hardcodes
an absolute local path, as a portable example. Extend `.gitignore` with
`.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/` and an unconditional `.env` rule.
Fix the `project_name` typo in `.backlog/config.yml`, which reads
`mcp-architmate`.

### Phase C — Licensing and attribution

`LICENSE` carries the full GPL-3.0 text. `[project]` gains
`license = "GPL-3.0-or-later"`; the MIT classifier is removed and the GPL
classifier added.

`README.md` gains a licensing section explaining the pyArchimate relationship and
the process-boundary point from D1, plus a credits section naming
**pyArchimate by Xavier Mayeur** (<https://github.com/pyArchimate/pyArchimate>) as
the library this server is built on. A `NOTICE` section or file records the same
attribution alongside the license.

### Phase D — Packaging and build hygiene

- `authors = [{name = "Byron Delgado", email = "delgadobyron+mcparchimate@gmail.com"}]`.
- Project URLs point at the real repository, issues, and changelog.
- Version single-sourced: `dynamic = ["version"]` with
  `[tool.hatch.version] path = "pyarchimate_mcp_server/__init__.py"`.
- Explicit `[tool.hatch.build.targets.sdist]` allow-list: package, `tests/`,
  `docs/` (post-consolidation), `README.md`, `LICENSE`, `NOTICE`,
  `CHANGELOG.md`, `pyproject.toml`. Everything else is excluded by omission.
- Classifiers corrected: `Environment :: Console`,
  `Programming Language :: Python :: 3 :: Only`, `:: 3.13`,
  `Topic :: Software Development`, and the GPL classifier.

Target: sdist under 1 MB, wheel containing only the importable package plus metadata.

### Phase E — Documentation and decisions

- `README.md` rewritten public-first: what it is, install via `uvx`, MCP client
  configuration for Claude Code / Claude Desktop / Codex, three quickstarts
  (load a model, create from spec, validate and export), security note,
  license and credits.
- `docs/USER_GUIDE.md` remains the client-facing tool reference.
- `docs/SDD.md` and `docs/IMPLEMENTATION_PLAN.md` fold into
  `docs/TECHNICAL_ARCHITECTURE.md`.
- `docs/UPGRADE_REPORT_2026-07-24.md` and the rationale halves of
  `docs/LAYOUT_IMPROVEMENT_PLAN.md` and `docs/MCP_Feedback_Improvements.md`
  distil into Backlog decisions; the measured layout numbers stay in
  `LAYOUT_IMPROVEMENT_PLAN.md`.
- `docs/PYPI_PUBLIC_RELEASE_PLAN.md` retires once executed.
- `docs/README.md` indexes what remains.
- `SECURITY.md` states the filesystem-rights model, the supported-version policy,
  and a disclosure address.
- `CONTRIBUTING.md` covers the `dev`/`main` branch model, `uv` commands, and the
  Backlog workflow.

Decisions to record (D7): GPL relicensing, stdio-only transport, `internal` as the
default layout engine, the two export formats, the MCP-as-constraint-engine split,
the `pyArchimate~=1.12.0` pin versus the `mcp>=1.28.1,<2.0.0` range, the deliberate
`validate_semantics` relationship-loop duplication, coverage-view marker over
substring matching, note pinning across layout, and this history reset.

Workflow note: `backlog decision create <title> [-s status]` scaffolds an ADR with
`## Context`, `## Decision` and `## Consequences` headings and owns the frontmatter
and id; the body is then written into the generated file. That is the intended
usage — verified against upstream `CLI-INSTRUCTIONS.md`, which documents no other
decision subcommand and no content flag — and it does not conflict with the
CLAUDE.md rule against hand-editing Backlog files, which exists to protect
CLI-managed metadata.

### Phase F — CI and release pipeline

`.github/workflows/ci.yml`, on pull requests and pushes to `dev` and `main`:

1. `uv sync --all-groups`
2. `uv run ruff check` and `uv run ruff format --check`
3. `uv run pytest` on Python 3.10, 3.11, 3.12, 3.13
4. `uv build --no-sources`
5. sdist hygiene guard: fail if `.taskmaster`, `.env`, `.backlog`, `.claude`,
   `.codex`, `.agents` or any `*.pdf` appears in the archive
6. upload build artifacts

`.github/workflows/release.yml`, on `v*` tags:

1. verify the tag matches `pyarchimate_mcp_server.__version__`
2. rerun tests and build
3. publish to PyPI via Trusted Publishing (OIDC, `id-token: write`), gated on a
   protected `pypi` environment requiring manual approval
4. create the GitHub Release with artifacts and CHANGELOG-derived notes

A `workflow_dispatch` input targets TestPyPI for dry runs.

Releasing thereafter: update `CHANGELOG.md`, bump `__version__`, merge `dev` into
`main`, tag `vX.Y.Z`, approve the environment.

### Phase G — Publish and validate

TestPyPI first; install into a clean environment; run MCP Inspector against the
installed command and confirm `tools/list`, `resources/list` and `prompts/list`;
confirm README rendering and metadata links. Then PyPI, then verify
`uvx mcp-archimate` end to end and check the rendered project page.

## Author-only steps

These need the author's own credentials and cannot be automated here:

1. Flip the GitHub repository to public.
2. Create the PyPI project and configure the Trusted Publisher
   (owner `byrondelgado`, repo `mcp-archimate`, workflow `release.yml`,
   environment `pypi`); same on TestPyPI.
3. Create the protected `pypi` GitHub environment with a required reviewer.
4. Approve the environment when the first release runs.

## Acceptance

- The public remote carries a single root commit and no pre-release history.
- `LICENSE` exists, SPDX metadata says `GPL-3.0-or-later`, and pyArchimate is
  credited in README and NOTICE.
- `uv build --no-sources` produces an sdist under 1 MB with no internal or
  third-party files; the hygiene guard fails the build if that regresses.
- CI passes on Python 3.10–3.13.
- `uvx mcp-archimate` runs from PyPI and answers `tools/list` with 45 tools.
- Pushing a `vX.Y.Z` tag publishes that version after one manual approval.

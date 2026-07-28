# Contributing

Thanks for considering a contribution. This project is small and opinionated;
this document covers the parts that are not obvious from the code.

By contributing you agree your work is licensed under **GPL-3.0-or-later**, the
same terms as the project. See [decision-001](.backlog/decisions/) for why the
project is copyleft — it follows from pyArchimate, it was not a free choice.

## Getting set up

Everything runs through [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups
```

Common commands:

```bash
uv run pytest                                    # all tests
uv run pytest tests/test_model_manager.py        # one file
uv run ruff check                                # lint
uv run ruff format                               # format
uv run mcp-archimate                             # run the server over stdio
uv run mcp dev pyarchimate_mcp_server/server.py  # run with MCP Inspector
```

`uv run ruff check` and `uv run ruff format --check` must both pass. Ruff is
configured with a broad rule selection and a few deliberate exceptions that are
explained in comments in `pyproject.toml` — read the comment before changing a
lint setting.

The `mcp` console script behind `mcp dev` comes from the dev-only `mcp[cli]`
extra. `uv` installs dev groups by default, so it works from a clone, but it is
not a runtime dependency.

## Branch model

- **`dev`** is the integration branch. Feature branches start here and merge back
  here. Day-to-day work happens on `dev`.
- **`main`** is the release branch. Version tags are cut on `main` only.

So a change flows: `feature/…` → `dev` → `main` → `vX.Y.Z` tag → published.

CI runs on pull requests and on pushes to both branches.

## Before you open a pull request

- Tests pass, lint passes, format check passes.
- New behaviour has a test. Tests call the async tool functions directly with
  `asyncio.run(...)` — no MCP client involved — construct `ArchimateModelManager`
  instances directly, and monkeypatch each tools module's `_model_manager` to
  inject them. Assertions target the response envelope (`response["status"]`,
  `response["data"]`, `response["error"]["code"]`).
- Documentation is updated in the same change. See the "Documentation to keep in
  sync" section of `CLAUDE.md` for which file covers what.
- If you added a tool or resource module, it is imported in `server.py`.
  **Registration happens by import side effect — a module missing from
  `server.py` silently does not register.**

## Read CLAUDE.md first

`CLAUDE.md` is the canonical instruction file for this repository (`AGENTS.md` is
the Codex entrypoint and delegates to it). It is written for AI coding agents but
is equally the fastest orientation for a human.

It documents a number of things that **look** like mistakes and are not: a
duplicated validation loop, a layout engine that is slower on paper but kept as
the default, an asymmetric dependency-pin shape, a comment that must not be
tidied away. Each is marked, and each has a decision record. Please check before
"simplifying" something that looks redundant — if it is genuinely wrong, say so
in an issue and we will fix the record too.

## Task tracking with Backlog.md

Work is tracked with [Backlog.md](https://github.com/MrLesk/Backlog.md), in
`.backlog/`. The task prefix is `ARC`.

```bash
backlog task list --plain          # the live board
backlog task view ARC-123 --plain  # one task
backlog search "layout" --plain    # tasks, docs and decisions
```

Manage tasks through the CLI rather than editing the markdown by hand — it owns
the metadata, ids, filenames and relationships.

You do not need to file a task for a small fix. Use one when the work needs
planning, a decision, or handoff notes.

## Architecture decisions

Load-bearing decisions live in `.backlog/decisions/` as ADRs with Context,
Decision and Consequences. Read them before changing something they cover;
`CLAUDE.md` links the relevant record from each section.

Add one when a choice will be non-obvious later, especially when the obvious
reading of the code is wrong.

```bash
backlog decision create "Short imperative statement of the decision" -s accepted
```

**Then write the body into the generated file.** This is the intended workflow,
not a workaround: `backlog decision create` accepts only a title and a status —
there is no `--content` flag and no update subcommand — so the CLI scaffolds the
frontmatter, the id and the section headings, and the author fills in the prose.
Leave the frontmatter alone; the CLI owns it.

This is the one exception to "do not edit Backlog markdown directly". Tasks,
documents and milestones all have CLI paths for their content, and should use
them.

## Releasing

Maintainers only. Shipping a version is: bump, tag, approve.

```bash
# 1. On dev: update CHANGELOG.md with a "## [X.Y.Z] - YYYY-MM-DD" section,
#    and bump __version__ in pyarchimate_mcp_server/__init__.py.
#    That file is the ONLY place the version lives — pyproject.toml reads it
#    via [tool.hatch.version].

# 2. Check locally before pushing anything.
uv run python scripts/check_release_version.py vX.Y.Z
uv run pytest && uv run ruff check && uv run ruff format --check

# 3. Merge dev into main, then tag on main.
git checkout main && git merge --ff-only dev && git push origin main
git tag -a vX.Y.Z -m "Release vX.Y.Z" && git push origin vX.Y.Z

# 4. Approve the `pypi` environment when GitHub asks. That is the last
#    human checkpoint — after it, the version is permanent.
```

The workflow verifies that the tag, `__version__` and the CHANGELOG all agree
**before** building. A published version can be yanked but never reused, so a
mismatch stops the run rather than producing a wrong artefact.

### Rehearsing a release

Run the **Release** workflow manually from the Actions tab with a version input.
That path publishes to TestPyPI only and never touches PyPI, so it cannot consume
the production approval gate.

### One-time setup

This is configuration on GitHub and PyPI, not in the repository. It must exist
before the first release, and it is why no API token is stored anywhere.

1. **PyPI** — at <https://pypi.org/manage/account/publishing/>, add a *pending*
   Trusted Publisher:
   - PyPI project name: `mcp-archimate`
   - Owner: `byrondelgado`, repository: `mcp-archimate`
   - Workflow: `release.yml`
   - Environment: `pypi`
2. **TestPyPI** — the same at <https://test.pypi.org/manage/account/publishing/>,
   with environment `testpypi`.
3. **GitHub environments** — under Settings → Environments, create `pypi` with a
   **required reviewer** (yourself), and `testpypi` with none.

The `pypi` environment's required reviewer is what turns a pushed tag into a
prompt rather than an immediate publish. Without it the workflow still runs, but
nothing pauses for a human.

## Reporting security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).

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

Maintainers only. Shipping a version is **bump, rehearse, tag, approve**. The
pipeline is `.github/workflows/release.yml`; the design and its reasoning are in
`decision-016`.

### The runbook

```bash
# 1. On dev: add a "## [X.Y.Z] - YYYY-MM-DD" section to CHANGELOG.md and bump
#    __version__ in pyarchimate_mcp_server/__init__.py. That file is the ONLY
#    place the version lives — pyproject.toml reads it via [tool.hatch.version].

# 2. Check locally before pushing anything. The first command is the same one
#    CI runs, so a failure here is a failure there.
uv run python scripts/check_release_version.py vX.Y.Z
uv run pytest && uv run ruff check && uv run ruff format --check

# 3. Rehearse against TestPyPI. Optional for a patch, worth it for anything
#    touching packaging, dependencies or metadata.
gh workflow run release.yml -f version=vX.Y.Z --ref main

# 4. Merge to main and tag. Tags are cut on main only.
git checkout main && git merge --ff-only dev && git push origin main
git tag -a vX.Y.Z -m "Release vX.Y.Z" && git push origin vX.Y.Z

# 5. Approve the `pypi` environment when GitHub asks — you will get an email and
#    a "Review pending deployments" banner on the run page.
```

Pushing the tag is **not** the irreversible step; the approval in step 5 is.
Everything before it can be undone by deleting the tag.

### What the pipeline does

| Job | Checks |
| --- | --- |
| **Verify** | tag, `__version__` and CHANGELOG agree; lint; format; tests |
| **Build** | `uv build --no-sources`; sdist hygiene gate; installs the wheel into a clean venv and drives it over stdio JSON-RPC |
| **Publish** | Trusted Publishing (OIDC). PyPI on a tag push, TestPyPI on manual dispatch. Never both |
| **GitHub Release** | attaches both artefacts, notes extracted from the CHANGELOG section |

### Rehearsing

Run the **Release** workflow manually from the Actions tab, or with
`gh workflow run` as above. That path targets the `testpypi` environment and
cannot reach PyPI — the production job is gated on
`if: github.event_name == 'push'`. It also means a rehearsal never consumes the
production approval, so the gate stays meaningful.

To check a rehearsal actually works, install it somewhere clean:

```bash
uv venv /tmp/check
uv pip install --python /tmp/check/bin/python \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  --index-strategy unsafe-best-match \
  mcp-archimate
uv run python scripts/smoke_test_mcp.py /tmp/check/bin/mcp-archimate --expect-tools 45
```

The `--extra-index-url` and `--index-strategy` are needed because dependencies
live on real PyPI, not TestPyPI.

### A version number is permanent

PyPI never lets a version be reused, even after deletion. If a release is bad:

- **Yank it** — new installs skip it, but anyone who pinned `==X.Y.Z` keeps
  working. The polite retraction, and almost always the right one.
- **Delete it** — files are removed and every pinned install breaks. Rarely
  correct on a public index.

Either way the fix ships as the next patch version, never as a re-upload. This is
why `check_release_version.py` runs before the build rather than after.

### Editing a workflow

**Verify that an action tag actually resolves before pinning it.** Reading the
latest *release* name is not the same check — `astral-sh/setup-uv` publishes
releases up to `v9.0.0` but stopped publishing floating major tags after `v7`, so
`@v9` does not exist. Pinning it made every job fail at "Set up job" on the first
public push.

```bash
gh api repos/OWNER/REPO/git/ref/tags/TAG --silent -i | head -1   # want 200
```

Official `actions/*` do publish floating majors, so `@v7` is fine there.

### One-time setup — already done

Recorded for reference and for anyone forking this. No API token is stored
anywhere; publishing is entirely OIDC.

| Where | What |
| --- | --- |
| [PyPI](https://pypi.org/manage/account/publishing/) | Trusted Publisher: project `mcp-archimate`, owner `byrondelgado`, repo `mcp-archimate`, workflow `release.yml`, environment `pypi` |
| [TestPyPI](https://test.pypi.org/manage/account/publishing/) | identical, environment `testpypi` |
| GitHub → Settings → Environments | `pypi` with a **required reviewer**; `testpypi` with none |

Before the first release these are added as *pending* publishers, which allow
creating a project that does not exist yet. A pending publisher does **not**
reserve the name — publishing is what claims it. Once the project exists the
pending entry becomes an ordinary Trusted Publisher automatically.

The required reviewer on `pypi` is what turns a pushed tag into a prompt instead
of an immediate publish. Without it the workflow still runs, but nothing pauses.

## Reporting security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).

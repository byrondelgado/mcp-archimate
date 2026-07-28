---
id: decision-016
title: 'Release by tag, publish by OIDC, gate on one human approval'
date: '2026-07-28 11:14'
status: accepted
---
## Context

Publishing to PyPI is the one operation in this project that cannot be undone. A
version can be yanked, but the number is burned forever — there is no re-upload,
no overwrite, no correction in place. Every design choice below follows from
that single asymmetry.

The obvious approach — a maintainer running `uv build && uv publish` from a
laptop — fails on three counts. It publishes whatever happens to be in the
working directory rather than what is committed. It requires a long-lived PyPI
token sitting on a developer machine. And it has no checkpoint: the command
either works or has already published.

The equally obvious opposite — fully automated publish on every merge to `main` —
removes the human from a decision that is permanent.

## Decision

**Tag to trigger, OIDC to authenticate, one human approval to publish.**

Four jobs, in order, each of which must pass before the next:

1. **Verify** — the tag, `__version__` and the CHANGELOG section must agree, then
   lint, format and the full test suite. This runs *before* anything is built,
   because the cheapest failure is the one that happens before an artefact
   exists.
2. **Build** — `uv build --no-sources`, the sdist hygiene gate, then install the
   wheel into a clean venv and drive it over stdio JSON-RPC. What gets published
   is an artefact that has been proven to install and answer, not merely to
   compile.
3. **Publish** — PyPI via Trusted Publishing (OIDC). **No API token exists
   anywhere in this repository or its secrets.**
4. **GitHub Release** — both artefacts attached, notes extracted from the
   CHANGELOG section for that version.

Supporting choices, each load-bearing:

- **`pyarchimate_mcp_server/__init__.py` is the single source of the version.**
  `pyproject.toml` reads it via `[tool.hatch.version]`. Without one source there
  is nothing for the tag to be checked against.
- **The `pypi` environment carries a required reviewer.** That is what converts a
  pushed tag into a prompt rather than an immediate publish. It is the last
  reversible moment.
- **TestPyPI runs on a separate `testpypi` environment**, reachable only via
  `workflow_dispatch`, with the production job gated on
  `if: github.event_name == 'push'`. Sharing one environment would mean every
  rehearsal consumed the production approval, training the maintainer to click
  through the gate that exists to make them stop.
- **`id-token: write` is scoped to the two publish jobs only.** The workflow
  default stays `contents: read`.

## Consequences

- Releasing requires a GitHub round trip; it cannot be done offline or from a
  laptop. Accepted deliberately — that constraint is most of the value.
- A wrong tag is recoverable. Delete it, fix, re-tag. Nothing is permanent until
  the approval, and the verify job is positioned to catch the common mistake
  (bumping the CHANGELOG but forgetting `__version__`, or the reverse) before a
  build exists.
- **Credential compromise is not a failure mode this project has.** There is no
  token to leak, rotate, or accidentally commit. The trust relationship is
  pinned to owner, repository, workflow *filename* and environment name — so
  renaming `release.yml` breaks publishing until the Trusted Publisher entry is
  updated. That is a feature.
- Rehearsals cost a TestPyPI version. TestPyPI accumulates them, which is why
  `skip-existing: true` is set there and nowhere else.
- The pipeline is only as good as its gates, so the gates were each verified to
  **fail**, not merely to pass: a poisoned sdist, a mismatched tag, a malformed
  tag, a missing CHANGELOG section, and a wrong tool count all produce a non-zero
  exit. A gate never observed failing is decoration.
- Workflow edits carry a specific hazard: **an action tag must be verified to
  resolve, not inferred from a release name.** `astral-sh/setup-uv` publishes
  releases past `v9.0.0` but stopped publishing floating major tags after `v7`,
  so `@v9` does not exist and every job failed at "Set up job" on the first
  public push. Recorded in `CONTRIBUTING.md` with the one-line check.

**Enforced by:** `.github/workflows/release.yml`,
`scripts/check_release_version.py`, `scripts/check_sdist_hygiene.py`,
`scripts/smoke_test_mcp.py`, the `pypi` environment's required reviewer, and the
runbook in `CONTRIBUTING.md`. Established in ARC-047, proven end to end by the
0.7.0 release in ARC-049, documented in ARC-052.

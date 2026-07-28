---
id: decision-001
title: Relicense to GPL-3.0-or-later to match pyArchimate
date: '2026-07-27 21:08'
status: accepted
---
## Context

`pyproject.toml` declared `License :: OSI Approved :: MIT License` and there was
no `LICENSE` file in the repository. Preparing the first public release surfaced
the conflict behind that: **pyArchimate 1.12.0 is GPL-3.0-only.** Its metadata
declares `License-Expression: GPL-3.0-only` and it ships the full GPL text in its
`dist-info`.

pyArchimate is not an optional backend. `model_manager.py` is written entirely
against it, and `layout.py` imports its *internal* layout surface — `ObstacleMap`,
`Rectangle`, `RoutingConfig` from `pyArchimate.view.layout`. Every model this
server creates, reads, lays out, validates and exports passes through it. The
server has no function without it.

The relevant facts:

- The project has one copyright holder. All 54 commits in the pre-release history
  are authored by Byron Delgado, so relicensing needed no contributor agreement.
- pyArchimate is never redistributed by this project. It is declared as a
  dependency and installed separately by pip or uv, from its own maintainer,
  under its own license.
- MIT is one-way compatible with the GPL: MIT-licensed code may be incorporated
  into a GPL work. So an MIT wrapper around a GPL dependency is not undistributable.
- The FSF's position is that a program which requires a GPL library forms a
  combined work subject to the GPL when distributed. Whether a Python `import`
  constitutes linking for that purpose is genuinely debated, and this project
  is not the place to settle it.

So the question was not "is MIT permissible here" but "does MIT honestly describe
what a user receives". It does not: whatever this repository says, the software a
user installs and runs only works as a combination with GPL-3.0 code.

## Decision

**License mcp-archimate as GPL-3.0-or-later.**

- `LICENSE` carries the FSF canonical GPL-3.0 text, verified byte-identical to
  <https://www.gnu.org/licenses/gpl-3.0.txt>.
- `pyproject.toml` declares `license = "GPL-3.0-or-later"` as a PEP 639 SPDX
  expression with `license-files = ["LICENSE", "NOTICE"]`. No `License ::`
  classifier is present; PEP 639 treats those as mutually exclusive with an SPDX
  expression.
- `NOTICE` credits pyArchimate and Xavier Mayeur by name and repository, states
  that the GPL is inherited from it, and records the licenses of the other direct
  runtime dependencies.
- `README.md` carries a Credits section naming pyArchimate as the library doing
  the real work, and a License section explaining the inheritance and its limits.

`-or-later` rather than `-only`: the dependency is `GPL-3.0-only`, which the
combination satisfies, and the looser form keeps a future migration path open
without forcing another relicensing decision.

## Consequences

**Accepted:**

- Organisations with a blanket policy against copyleft dependencies will not
  adopt this server. That population was already excluded in substance by
  pyArchimate; the change makes it visible rather than creating it.
- Relicensing away from the GPL later would require replacing pyArchimate first.
  Given how deeply `model_manager.py` and `layout.py` depend on it, that is
  effectively a rewrite. This decision is close to irreversible in practice.

**Explicitly not consequences**, and stated in the README because users will ask:

- Models produced with this server are not GPL-encumbered. They are user
  documents, like files written in a GPL text editor.
- The GPL does not reach the agent or MCP client that calls this server. MCP
  servers run as separate processes speaking JSON-RPC over stdio; copyleft
  attaches to distributing *this program*, not to software communicating with it
  across that boundary.

**Obligations created:**

- Any modified version that is distributed, or any product shipping this server
  inside it, is subject to the GPL's source-availability terms.
- Adding a runtime dependency under a GPL-incompatible license (for example
  Apache-2.0 in a way that conflicts, or anything proprietary) is now a licensing
  decision, not just a dependency choice.

**Enforced by:** `LICENSE`, `NOTICE`, the `license` field in `pyproject.toml`,
and the README License section. Verified at build time — the wheel METADATA
reports `License-Expression: GPL-3.0-or-later` with both license files attached.

Recorded under ARC-041.

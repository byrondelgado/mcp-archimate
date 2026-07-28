# Documentation

Four documents, each with one job. If two of them ever say the same thing
differently, the one listed as the owner wins.

| Document | Audience | Owns |
| --- | --- | --- |
| [USER_GUIDE.md](USER_GUIDE.md) | Anyone using the server through an MCP client | The tool and resource reference: every parameter, response schema, workflow and troubleshooting entry. The full tool table lives here and nowhere else. |
| [TECHNICAL_ARCHITECTURE.md](TECHNICAL_ARCHITECTURE.md) | Contributors and maintainers | How the server is built: layers, the pyArchimate adapter boundary, export repairs, layout design, and the glossary. |
| [LAYOUT_IMPROVEMENT_PLAN.md](LAYOUT_IMPROVEMENT_PLAN.md) | Anyone touching layout | The layout roadmap and, importantly, the **measurements** — including the benchmarks behind the default-engine choice and the approaches that were tried and rejected as no-ops. |
| [MCP_Feedback_Improvements.md](MCP_Feedback_Improvements.md) | Anyone touching validation | The product requirements for the quality and validation suite: relationship rules, quality gates, TOGAF readiness. |

## Where the *why* lives

Not here. Design rationale is recorded as decision records in
[`.backlog/decisions/`](../.backlog/decisions/), in ADR form with Context,
Decision and Consequences.

Read those before changing something that looks redundant or suboptimal — several
choices in this codebase are counter-intuitive on purpose, and each has a record
explaining what breaks if it is undone. `CLAUDE.md` links the relevant record from
each of its sections.

## Elsewhere in the repository

| | |
| --- | --- |
| [../README.md](../README.md) | Start here. Install, client configuration, quickstarts |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Setup, branch model, conventions |
| [../SECURITY.md](../SECURITY.md) | Trust model and vulnerability disclosure |
| [../CHANGELOG.md](../CHANGELOG.md) | What changed, newest first |
| [../CLAUDE.md](../CLAUDE.md) | The repository's operating contract, for AI agents and humans alike |

## Retired

`SDD.md`, `IMPLEMENTATION_PLAN.md`, `UPGRADE_REPORT_2026-07-24.md`,
`PYPI_PUBLIC_RELEASE_PLAN.md` and `mcp_documentation.md` were removed during the
0.7.0 open-source preparation. The first four were point-in-time plans and reports
covering work long since finished; they had drifted from the code and duplicated
tables that `USER_GUIDE.md` maintains properly. The last was a vendored snapshot of
upstream MCP SDK documentation that would only ever go stale — read
[the real thing](https://modelcontextprotocol.io) instead.

The SDD's glossary survives as an appendix to `TECHNICAL_ARCHITECTURE.md`.
Historical Backlog tasks still reference the retired files; that is an accurate
record of what those tasks touched at the time, not a set of broken links.

# mcp-archimate

[![CI](https://github.com/byrondelgado/mcp-archimate/actions/workflows/ci.yml/badge.svg)](https://github.com/byrondelgado/mcp-archimate/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mcp-archimate)](https://pypi.org/project/mcp-archimate/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-archimate)](https://pypi.org/project/mcp-archimate/)
[![License: GPL v3](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

An [MCP](https://modelcontextprotocol.io/) server that lets an AI agent build,
validate and export real [ArchiMate](https://www.opengroup.org/archimate-forum/archimate-overview)
models — the kind that open in [Archi](https://www.archimatetool.com/) and survive
a round trip.

It exposes 45 tools, 9 resources and 4 guided prompts over stdio. The agent
describes architecture; the server enforces what ArchiMate actually permits,
lays out the diagrams, and writes the file.

```
"Model our order-to-cash flow, then export it so I can open it in Archi."
```

## Why this exists

Asking a model to emit ArchiMate XML directly produces files that look plausible
and fail to open. Relationship types are invented, ids do not resolve, diagrams
have no coordinates.

This server closes that gap. It holds the model in memory, refuses invalid
relationships with the valid alternatives attached, positions every node and
routes every connection, and serialises through
[pyArchimate](https://github.com/pyArchimate/pyArchimate) rather than string
templating. **It owns zero ArchiMate rules of its own** — every validity verdict
is delegated to pyArchimate's relationship matrix (ArchiMate 3.2-compatible), so
it cannot drift into a private dialect.

The division of labour is deliberate: the server is a *constraint engine*, the
agent is the architect. It will tell you a `BusinessProcess` cannot serve an
`ApplicationService` and what can; it will not decide what your architecture
should be.

## Install

Nothing to clone. With [uv](https://docs.astral.sh/uv/):

```bash
uvx mcp-archimate
```

That runs the server over stdio, which is what an MCP client wants. Running it in
a terminal by hand will just sit there waiting for JSON-RPC — that is correct.

Alternatives:

```bash
pipx run mcp-archimate
pip install mcp-archimate
```

Requires Python 3.10 or newer.

## Connect it to a client

**Claude Code:**

```bash
claude mcp add archimate -- uvx mcp-archimate
```

**Claude Desktop** — in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "archimate": {
      "command": "uvx",
      "args": ["mcp-archimate"]
    }
  }
}
```

**Codex** — in `~/.codex/config.toml`:

```toml
[mcp_servers.archimate]
command = "uvx"
args = ["mcp-archimate"]
```

**MCP Inspector:**

```bash
npx @modelcontextprotocol/inspector uvx mcp-archimate
```

No API keys, no environment variables, no configuration file. The server needs
none of them.

## Quickstart

Three things worth trying first. Ask your agent in plain language — the tool
names below are what it will reach for.

**Open an existing model.** `load_model_from_file` loads *and* inspects in one
call, so the agent immediately knows the element counts, validation state and
what to do next.

> "Load `~/models/enterprise.archimate` and tell me what's in it."

**Build one from a description.** `create_empty_model`, then elements and
relationships, then `auto_layout_view` to make the diagram readable.

> "Create a model of a customer onboarding process with the business, application
> and technology layers, and lay out a view showing how they connect."

**Validate and export.** `build_quality_report` first, then
`export_model_to_file` with `quality_gate="strict"` so a broken model cannot
reach disk.

> "Check the model for problems, fix what's safely fixable, then export it for
> Archi."

Agents should call `get_usage_guide` before anything else — it returns the
operating rules, common anti-patterns and recommended call sequences. It exists
so the agent does not go reading the server's source code to work out what to do.

## What's in the box

| | |
| --- | --- |
| **Model** (17 tools) | create, load, export, metadata, quality reports, TOGAF readiness |
| **Views** (12 tools) | create views, add nodes, auto-layout, layer bands, diagram notes, SVG rendering |
| **Relationships** (7 tools) | create, validate, compatibility lookup, intent-based recommendation, deterministic repair |
| **Elements** (4 tools) | add, update, delete, query |
| **Workflow** (3 tools) | usage guide, load-and-inspect, inspect active model |
| **Queries** (2 tools) | filtered search across the model |
| **Resources** (6 + 3 templates) | read-only views of the model under `pyarchimate://activemodel/...`; the three templated ones are returned by `resources/templates/list` |
| **Prompts** (4) | guided load → inspect → edit → validate → export workflows |

Full parameter and response documentation is in the
**[User Guide](docs/USER_GUIDE.md)**.

### Two export formats — they are not interchangeable

| `output_format` | Produces | In Archi |
| --- | --- | --- |
| `"archi"` | Archi's native `.archimate` | **Opens** directly |
| `"archimate"` *(default)* | Open Group exchange XML | Must be **imported** |

SVG is not a third format. `render_view_to_svg_file` writes a picture for a human
to look at; it carries no model semantics and cannot be loaded back.

### Layout

Diagrams are laid out, not just populated: nodes are placed in ArchiMate layer
order with lane wrapping and barycenter alignment, multi-layer views get labelled
layer bands, and connections are routed around obstacles rather than drawn as
diagonals through boxes.

## Security considerations

Two things are worth knowing before you point an agent at this server. The full
picture, including how to report a vulnerability, is in [SECURITY.md](SECURITY.md).

**It has your filesystem rights.** `load_model_from_file` reads any path you can
read; `export_model_to_file` and `render_view_to_svg_file` write any path you can
write, overwriting without prompting. There is no allowed-root restriction yet.
This is ordinary for a local MCP server, but the caller here is usually an LLM
agent rather than a person typing a path — so treat a path argument the way you
would treat a shell command an agent proposed, and point exports at a working
directory rather than somewhere irreplaceable. If you need a hard boundary now,
run the server in a container or under a dedicated account.

**Model files are untrusted input.** The loader rejects DTDs and entity
declarations outright, parses with external entity resolution and network access
disabled, caps content at 10 MB and allow-lists the root element — so XXE and
entity-expansion attacks are blocked, and this is verified adversarially in
`tests/test_security.py` rather than assumed. What it cannot block is prompt
injection: element names, documentation and properties are attacker-controllable
text that flows back to your agent. Treat model content as data, never as
instructions.

The server makes no network requests, collects no telemetry, and needs no
credentials of any kind.

## Documentation

| Document | For |
| --- | --- |
| [User Guide](docs/USER_GUIDE.md) | Everyone. Tool parameters, response schemas, workflows, troubleshooting |
| [Technical Architecture](docs/TECHNICAL_ARCHITECTURE.md) | Contributors. Design, layers, pyArchimate usage patterns |
| [Layout Improvement Plan](docs/LAYOUT_IMPROVEMENT_PLAN.md) | Layout work. Measurements and rejected approaches |
| [Quality & Validation PRD](docs/MCP_Feedback_Improvements.md) | The validation tool suite and the constraint-engine split |
| [CHANGELOG](CHANGELOG.md) | What changed, newest first |
| [CONTRIBUTING](CONTRIBUTING.md) | Setup, branch model, how to propose changes |
| [SECURITY](SECURITY.md) | Trust model and vulnerability disclosure |
| `.backlog/decisions/` | Architecture decision records — why things are the way they are |

## Development

```bash
git clone https://github.com/byrondelgado/mcp-archimate.git
cd mcp-archimate
uv sync --all-groups

uv run pytest
uv run ruff check
uv run mcp dev pyarchimate_mcp_server/server.py   # with MCP Inspector
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch model and conventions, and
`CLAUDE.md` for the repository's operating contract — it documents several things
that look like mistakes and are not.

## Credits

This server is built on **[pyArchimate](https://github.com/pyArchimate/pyArchimate)**
by **Xavier Mayeur**, which does the actual ArchiMate modelling work. Every model
this server creates, reads, lays out, validates and exports passes through it. If
this project is useful to you, pyArchimate is the reason.

## License

**GPL-3.0-or-later.** See [LICENSE](LICENSE) for the full text and
[NOTICE](NOTICE) for attribution.

This is inherited, not chosen. pyArchimate is GPL-3.0-only and is a required
runtime dependency — the server cannot function without it — so the combined work
you actually run is governed by the GPL. Releasing this server under permissive
terms would misrepresent that.

What this means in practice:

- **Using the server does not put your models under the GPL.** The `.archimate`
  and exchange files you produce are your own work, exactly as documents written
  in a GPL text editor are.
- **It does not reach the agent or client that calls it.** An MCP server is a
  separate process communicating over stdio JSON-RPC. Copyleft attaches to
  distributing *this program*, not to software that talks to it across that
  boundary.
- **It does apply if you distribute a modified version** of this server, or ship
  it inside something you distribute. Then the GPL's source-availability terms
  apply to that work.

This is a plain-language summary, not legal advice. Read the license, and take
your own advice if the distinction matters to your situation.

---

ArchiMate is a registered trademark of The Open Group. This project is an
independent implementation, not affiliated with or endorsed by The Open Group or
the Archi project.

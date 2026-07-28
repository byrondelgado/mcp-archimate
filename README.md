# mcp-archimate

[![CI](https://github.com/byrondelgado/mcp-archimate/actions/workflows/ci.yml/badge.svg)](https://github.com/byrondelgado/mcp-archimate/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mcp-archimate)](https://pypi.org/project/mcp-archimate/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-archimate)](https://pypi.org/project/mcp-archimate/)
[![License: GPL v3](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](https://github.com/byrondelgado/mcp-archimate/blob/main/LICENSE)

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

No API keys and no configuration file. The only environment variables it reads
are the two optional filesystem roots described under
[Security considerations](#security-considerations); unset, they default to your
home directory.

## Example prompts

You talk to your agent in plain language; it picks the tools. The tool names
below are just what it will reach for, so you can follow along.

Everything here is copy-pasteable. Start with the first one.

### Build something small

```
Create an ArchiMate model of a customer onboarding process. Cover the business
layer (the customer, the onboarding process, the identity check) and the
application layer (the onboarding portal and an identity verification service).
Connect them properly, put it in one view, lay it out, and export it so I can
open it in Archi.
```

*Uses `create_empty_model` → `add_element` → `add_relationship` →
`create_view` → `auto_layout_view` → `export_model_to_file`.*

### Explore a model you already have

```
Load ~/models/enterprise.archimate and tell me what's in it: how big it is,
what's in each layer, and whether anything is broken.
```

`load_model_from_file` loads **and** inspects in one call, so the agent gets
counts, validation state and view summaries immediately.

Follow-ups worth asking:

```
Which elements aren't used in any view?
```
```
Show me everything that depends on the payment service.
```

### Edit an existing model

The common case after the first build. Be specific about what to change and the
agent will make a focused edit rather than rebuilding.

```
Add a "Fraud Screening" application service to the model, have it serve the
checkout process, and host it on the same node as the payment service. Then
re-lay-out the views it appears in.
```

```
Rename "Cust Mgmt Svc" to "Customer Management Service" everywhere, and give it
a proper description explaining what it does.
```

```
The order service and the inventory service are connected with a Serving
relationship, but it should be asynchronous. Change it to a Flow relationship
and tell me if that's actually valid ArchiMate.
```

That last one is worth trying — the server will tell you which relationship
types are legal between those two element types, with alternatives, rather than
silently accepting something Archi will reject.

### Improve a model

```
Review this model for quality problems and fix the ones that are safely
fixable. Explain anything you can't fix automatically and why.
```

*Uses `build_quality_report` → `repair_semantic_issues`. The server only
auto-repairs deterministic cases; anything needing an architectural decision is
reported back to you rather than guessed at.*

```
Every view in this model is a wall of boxes. Add layer bands, lay everything
out again, and add notes explaining what each view is for.
```

```
Some of my relationships aren't shown in any view. Find them and add a coverage
view so nothing is hidden.
```

### Validate and export

```
Check the model for problems, then export it to ~/Desktop/architecture.archimate
in Archi's native format with a strict quality gate so it won't write a broken
file.
```

`quality_gate="strict"` blocks the export on visual, semantic or coverage
failures — useful when the file is going to someone else.

To *look* at a diagram without opening Archi:

```
Render the Application Cooperation view to an SVG on my Desktop.
```

### A full build

A single prompt that exercises most of the server. Expect it to take a few
minutes and make a lot of tool calls.

```
Create an ArchiMate model representing a realistic composite ecommerce
architecture (not tied to a real company). Use the archimate MCP tools. Scope:

- Business layer: Customer / Warehouse Staff / Support Rep actors with roles,
  core processes (browse, cart, checkout, payment, fulfillment, support),
  business services, and key business objects (order, customer account).
- Application layer: microservices — storefront web app, API gateway, and one
  component + service pair per capability (catalog, search, cart, checkout,
  payment, order management, inventory, shipping, notification, customer
  support), plus their data objects.
- Technology layer: cloud infrastructure — container orchestration, a database
  per service that needs one, a cache, a message broker for async events, a
  load balancer / CDN, and an external payment gateway node.
- Relationships: standard ArchiMate conventions (ApplicationService serves
  BusinessProcess, Component realizes Service, Node serves Component for
  hosting, Access for data reads/writes, Flow for async events). Validate with
  semantic_validation='strict' and fix any invalid combinations using the
  suggested repairs.
- Views: Business Process View, Application Cooperation View, Technology
  Deployment View, and a Layered Overview showing one cross-layer slice (the
  checkout journey end to end). Auto-layout each view with layer bands.
- Run ensure_all_relationships_in_views, build_quality_report and
  validate_model before exporting. Export with quality_gate='strict'.

Add descriptions and annotations throughout.

Skip the clarifying questions — go straight to building.
```

The last line matters. Without it a good agent will stop and ask you to narrow
the scope, which is usually the right instinct but not what you want here.

### A note for agents

Call `get_usage_guide` first. It returns the operating rules, common
anti-patterns and recommended call sequences — it exists so an agent does not
have to read this server's source code to work out how to use it.

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
**[User Guide](https://github.com/byrondelgado/mcp-archimate/blob/main/docs/USER_GUIDE.md)**.

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
picture, including how to report a vulnerability, is in [SECURITY.md](https://github.com/byrondelgado/mcp-archimate/blob/main/SECURITY.md).

**The file tools are confined to allowed roots.** `load_model_from_file` reads,
and `export_model_to_file` and `render_view_to_svg_file` write, only inside the
directories named by `MCP_ARCHIMATE_ALLOWED_READ_ROOTS` and
`MCP_ARCHIMATE_ALLOWED_WRITE_ROOTS`. Unset, both default to your home directory,
which keeps the quickstarts above working while putting `/etc`, system locations
and other users' files out of reach. Paths are fully resolved first, so `..` and
symlinks cannot escape. Set the variables to a dedicated models directory to
narrow it further — with the home default, `~/.ssh` is still readable. This is
not a sandbox: the server runs as the account that launched it, and exports still
overwrite without prompting inside an allowed root. It exists because the caller
here is usually an LLM agent rather than a person typing a path, so treat a path
argument the way you would treat a shell command an agent proposed. For a hard
boundary, run the server in a container or under a dedicated account.

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
| [User Guide](https://github.com/byrondelgado/mcp-archimate/blob/main/docs/USER_GUIDE.md) | Everyone. Tool parameters, response schemas, workflows, troubleshooting |
| [Technical Architecture](https://github.com/byrondelgado/mcp-archimate/blob/main/docs/TECHNICAL_ARCHITECTURE.md) | Contributors. Design, layers, pyArchimate usage patterns |
| [Layout Improvement Plan](https://github.com/byrondelgado/mcp-archimate/blob/main/docs/LAYOUT_IMPROVEMENT_PLAN.md) | Layout work. Measurements and rejected approaches |
| [Quality & Validation PRD](https://github.com/byrondelgado/mcp-archimate/blob/main/docs/MCP_Feedback_Improvements.md) | The validation tool suite and the constraint-engine split |
| [CHANGELOG](https://github.com/byrondelgado/mcp-archimate/blob/main/CHANGELOG.md) | What changed, newest first |
| [CONTRIBUTING](https://github.com/byrondelgado/mcp-archimate/blob/main/CONTRIBUTING.md) | Setup, branch model, how to propose changes |
| [SECURITY](https://github.com/byrondelgado/mcp-archimate/blob/main/SECURITY.md) | Trust model and vulnerability disclosure |
| [Decision records](https://github.com/byrondelgado/mcp-archimate/tree/main/.backlog/decisions) | Architecture decision records — why things are the way they are |

## Development

```bash
git clone https://github.com/byrondelgado/mcp-archimate.git
cd mcp-archimate
uv sync --all-groups

uv run pytest
uv run ruff check
uv run mcp dev pyarchimate_mcp_server/server.py   # with MCP Inspector
```

See [CONTRIBUTING.md](https://github.com/byrondelgado/mcp-archimate/blob/main/CONTRIBUTING.md) for the branch model and conventions, and
`CLAUDE.md` for the repository's operating contract — it documents several things
that look like mistakes and are not.

## Credits

This server is built on **[pyArchimate](https://github.com/pyArchimate/pyArchimate)**
by **Xavier Mayeur**, which does the actual ArchiMate modelling work. Every model
this server creates, reads, lays out, validates and exports passes through it. If
this project is useful to you, pyArchimate is the reason.

## License

**GPL-3.0-or-later.** See [LICENSE](https://github.com/byrondelgado/mcp-archimate/blob/main/LICENSE) for the full text and
[NOTICE](https://github.com/byrondelgado/mcp-archimate/blob/main/NOTICE) for attribution.

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

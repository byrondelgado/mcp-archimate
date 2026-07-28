# Security Policy

## Reporting a vulnerability

Email **delgadobyron+mcparchimate@gmail.com** with the details. Please do not
open a public issue for a suspected vulnerability.

Include what you need to make the problem reproducible: the MCP tool involved, the
input, what happened, and what you expected. A proof of concept helps. You should
get an acknowledgement within a week. If the report is valid I will fix it and
credit you in the release notes unless you would rather stay anonymous.

## Supported versions

Only the latest released version receives security fixes. This project is at
`0.x`, so there is no long-term support branch — upgrade to the newest release.

## What this server is, in security terms

`mcp-archimate` is a **local, stdio-only MCP server**. It has no network listener,
no HTTP or SSE transport, no authentication layer and no multi-tenancy, because it
is designed to be launched as a subprocess by an MCP client on your own machine.
Everything below follows from that.

### The file tools are confined to allowed roots

Three tools touch the filesystem:

| Tool | Access |
| --- | --- |
| `load_model_from_file` | reads inside the allowed **read** roots |
| `export_model_to_file` | writes inside the allowed **write** roots |
| `render_view_to_svg_file` | writes inside the allowed **write** roots |

Two environment variables configure the boundary. Each takes one or more
**absolute** paths, separated by the platform path separator (`:` on macOS and
Linux, `;` on Windows). `~` is expanded.

| Variable | Controls |
| --- | --- |
| `MCP_ARCHIMATE_ALLOWED_READ_ROOTS` | where `load_model_from_file` may read |
| `MCP_ARCHIMATE_ALLOWED_WRITE_ROOTS` | where the two writing tools may write |

**Unset, both default to your home directory.** That keeps the documented
workflows working — the quickstarts write to `~/Desktop` — while putting `/etc`,
`/usr`, system locations and other users' home directories out of reach. Set the
variables explicitly to narrow it further; a dedicated models directory is the
tightest useful setting:

```json
{
  "mcpServers": {
    "archimate": {
      "command": "uvx",
      "args": ["mcp-archimate"],
      "env": {
        "MCP_ARCHIMATE_ALLOWED_READ_ROOTS": "/Users/you/Models",
        "MCP_ARCHIMATE_ALLOWED_WRITE_ROOTS": "/Users/you/Models/exports"
      }
    }
  }
}
```

Every path is expanded and fully resolved before the check, so `..` segments and
symlinks cannot escape: a symlink inside an allowed root that points outside it
resolves to its real target and is refused. A refused path returns
`PATH_OUTSIDE_ALLOWED_ROOTS` with the resolved path and the configured roots in
`error.details`. An unusable configuration — an empty setting, or a relative
root — returns `INVALID_ALLOWED_ROOTS` rather than silently falling back.

**The read check runs before the existence check**, so a path outside the roots
cannot be used to probe for files: an existing file you may not read is
indistinguishable from a missing one.

What this does **not** do:

- **It is not a sandbox.** The server still runs as the account that launched it,
  and the roots are enforced in-process. It stops an agent from wandering; it does
  not contain a compromised process.
- **It does not protect the allowed roots from each other.** With the default of
  home, `~/.ssh` is still readable. Narrow the roots if that matters.
- **Exports still overwrite without prompting** inside an allowed root. Point them
  at a working directory, not at somewhere with irreplaceable files.

The reason this exists at all is that the *caller* is usually an LLM agent, not a
person typing a path, and that agent may be acting on content it read from a model
file, a web page, or a document. Treat a path argument the way you would treat a
shell command an agent proposed.

For a hard boundary, run the server in a container or under a dedicated user
account with access only to the directory holding your models.

### Model files are untrusted input

You will open `.archimate` files other people made. The loader is hardened
against the standard XML attacks:

- **DTDs and entity declarations are rejected outright.** Any content containing
  `<!DOCTYPE` or `<!ENTITY` is refused before it reaches a parser, which blocks
  XML external entity (XXE) attacks and entity-expansion denial of service
  ("billion laughs") in one step.
- **The parser is hardened as well**, with `resolve_entities=False`,
  `no_network=True`, `recover=False` and `huge_tree=False`, so external entity
  resolution and network fetches remain off even if the check above is bypassed.
- **Content is size-capped** at 10 MB.
- **The root element is allow-listed** to recognised ArchiMate roots.
- `load_model_from_file` reads the file and routes it through the same validation
  as `load_model_from_string`. There is no weaker path.

These are verified adversarially in `tests/test_security.py`, not merely asserted.
The tests use payloads with a *valid* ArchiMate root — so the root-element check
cannot mask a failure of the entity guard — and each payload points at a canary
file whose contents must never appear in the loaded model or in an error message.
The suite includes a control test proving the payload still leaks against a
deliberately permissive parser, so the tests cannot silently degrade into testing
nothing.

**Ordering invariant:** `_restore_exchange_note_connectors` re-parses the raw
content with a plain parser. That is safe *only because* validation has already
run and rejected DTDs. Anything that moves, skips or reorders that validation
reintroduces the risk.

### What the server does not protect against

- **Prompt injection through model content.** Element names, documentation and
  properties are attacker-controllable text that flows back to your agent. A
  model can contain text designed to steer the agent reading it. This server
  cannot filter that, and it does not try — treat model content as data, never as
  instructions.
- **Malicious paths chosen by a compromised or misled agent**, as above.
- **Anything about the model's own contents.** Semantic validation checks
  ArchiMate correctness, not safety.

### What the server never does

- No outbound network requests. It has no HTTP client and does not phone home.
- No telemetry, analytics or crash reporting.
- No credentials, tokens or API keys of any kind. It needs none, so a `.env` file
  in a checkout of this project is always a mistake.
- No writes to stdout. stdio is the JSON-RPC channel; all logging goes to stderr.

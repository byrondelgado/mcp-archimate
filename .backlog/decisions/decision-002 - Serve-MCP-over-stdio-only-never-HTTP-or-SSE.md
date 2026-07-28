---
id: decision-002
title: 'Serve MCP over stdio only, never HTTP or SSE'
date: '2026-07-27 21:38'
status: accepted
---
## Context

The MCP specification supports several transports. The Python SDK ships
Streamable HTTP and SSE alongside stdio, and their dependencies — `uvicorn`,
`starlette`, `sse-starlette`, `httpx` — arrive as unconditional base
dependencies of `mcp` whether or not they are used. Offering an HTTP mode would
therefore cost no extra packages, which makes it tempting.

It would cost everything else. A network-reachable server needs authentication,
authorization, transport security, multi-tenancy and a hosted operational story.
This server holds **one in-memory ArchiMate model per process** and has no
concept of a session or a user; exposing that over a port would mean any client
that reaches it shares — and can replace — the active model.

## Decision

**Serve stdio only.** `server.py:main()` calls `mcp.run()` with no transport
argument and no host/port configuration, and the package ships no HTTP mode.
Do not add `--transport streamable-http`, `--transport sse`, `--host` or
`--port` flags.

A consequence with teeth: **stdout is the JSON-RPC channel.** Anything written
to stdout corrupts the framing and hangs the client. All logging goes to stderr
via `logging`. There must be no `print()` anywhere in the server, which is why
ruff's `T201`/`T203` are enabled for the package.

## Consequences

- Remote and multi-user deployment are out of scope. The server is launched as a
  subprocess by a local MCP client and lives as long as that client does.
- The single-active-model design stays coherent — one process, one model, one
  caller.
- The security posture is simple enough to state in a paragraph: no listener, no
  auth surface, no network requests. See `SECURITY.md`.
- The HTTP dependency tree still ships, because `mcp` requires it. Dropping the
  `[cli]` extra does not shrink it, and there is nothing this project can do
  about that short of vendoring the SDK.
- If HTTP is ever wanted, it is a new decision requiring an auth story, not a
  flag.

**Enforced by:** `server.py`, the absence of transport configuration, and the
`T201`/`T203` lint rules. Documented in `SECURITY.md` and `CLAUDE.md`.

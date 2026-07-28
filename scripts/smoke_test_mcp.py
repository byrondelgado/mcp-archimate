#!/usr/bin/env python3
"""Drive an installed mcp-archimate over stdio and check it answers correctly.

Unit tests call the tool functions directly, with no MCP client and no process
boundary. That leaves two failure modes invisible:

1. A tool module missing from the imports in `server.py` silently does not
   register — the tests still pass because they import it themselves.
2. Anything written to stdout corrupts the JSON-RPC framing and hangs the
   client. stdout *is* the protocol channel under stdio transport.

Both only show up when you talk to the real process, which is what this does.

    uv run python scripts/smoke_test_mcp.py /path/to/bin/mcp-archimate
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time

PROTOCOL_VERSION = "2025-06-18"

# Not the full surface — these three are the ones an agent is told to call
# first, so their absence is the failure most likely to reach a user.
REQUIRED_TOOLS = frozenset(
    {"get_usage_guide", "load_model_from_file", "inspect_active_model"},
)

REQUEST_LINES = (
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "smoke-test", "version": "0"},
        },
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "prompts/list"},
    {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
    # Templated resources are NOT in resources/list — they have their own method.
    {"jsonrpc": "2.0", "id": 5, "method": "resources/templates/list"},
)


def run_server(command: str, timeout: float) -> tuple[str, str]:
    """Send every request, then read replies until all ids are answered.

    Deliberately does *not* use `communicate()`. Closing stdin immediately makes
    the server begin shutting down while it is still writing, and the last
    response can be lost — which showed up as a phantom "resources/list returned
    nothing" that was really a race. Read first, close after.
    """
    expected_ids = {line["id"] for line in REQUEST_LINES if "id" in line}
    process = subprocess.Popen(  # noqa: S603
        [command],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdin is not None
    assert process.stdout is not None

    deadline = time.monotonic() + timeout
    lines: list[str] = []
    seen: set[int] = set()

    def read_until_done() -> None:
        for line in process.stdout:  # type: ignore[union-attr]
            lines.append(line)
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and isinstance(message.get("id"), int):
                seen.add(message["id"])
            if seen >= expected_ids or time.monotonic() > deadline:
                return

    for request in REQUEST_LINES:
        process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()

    reader = threading.Thread(target=read_until_done, daemon=True)
    reader.start()
    reader.join(timeout)

    process.stdin.close()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)

    stderr = process.stderr.read() if process.stderr else ""
    return "".join(lines), stderr


def parse_stdout(stdout: str) -> tuple[dict[int, dict], list[str]]:
    """Split server stdout into id-keyed responses and anything that is not JSON."""
    responses: dict[int, dict] = {}
    noise: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            noise.append(stripped)
            continue
        if isinstance(message, dict) and isinstance(message.get("id"), int):
            responses[message["id"]] = message
    return responses, noise


def check_tools(responses: dict[int, dict], expect_tools: int | None) -> list[str]:
    tools = responses.get(2, {}).get("result", {}).get("tools")
    if not tools:
        return ["tools/list returned nothing"]

    failures = []
    missing = REQUIRED_TOOLS - {tool["name"] for tool in tools}
    if missing:
        failures.append(f"tools missing from tools/list: {sorted(missing)}")
    if expect_tools is not None and len(tools) != expect_tools:
        failures.append(
            f"expected {expect_tools} tools, got {len(tools)} — "
            "a module may be missing from the imports in server.py",
        )
    return failures


def collect_failures(
    responses: dict[int, dict],
    noise: list[str],
    expect_tools: int | None,
) -> list[str]:
    failures: list[str] = []

    # The framing check comes first: if stdout is polluted, nothing else is
    # trustworthy, and a real client would already have hung.
    if noise:
        failures.append(
            f"non-JSON output on stdout would corrupt stdio framing: {noise[:3]}",
        )

    init = responses.get(1, {}).get("result", {})
    if not init:
        failures.append("initialize returned no result")
    elif init.get("protocolVersion") != PROTOCOL_VERSION:
        failures.append(
            f"negotiated protocol {init.get('protocolVersion')!r}, "
            f"expected {PROTOCOL_VERSION!r}",
        )

    failures.extend(check_tools(responses, expect_tools))

    for request_id, method, key in (
        (3, "prompts/list", "prompts"),
        (4, "resources/list", "resources"),
        (5, "resources/templates/list", "resourceTemplates"),
    ):
        if not responses.get(request_id, {}).get("result", {}).get(key):
            failures.append(f"{method} returned nothing")

    return failures


def summarize(responses: dict[int, dict]) -> str:
    def count(request_id: int, key: str) -> int:
        return len(responses.get(request_id, {}).get("result", {}).get(key, []))

    protocol = responses.get(1, {}).get("result", {}).get("protocolVersion")
    return (
        f"MCP smoke test passed: protocol {protocol}, "
        f"{count(2, 'tools')} tools, {count(3, 'prompts')} prompts, "
        f"{count(4, 'resources')} resources, "
        f"{count(5, 'resourceTemplates')} resource templates\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", help="path to the mcp-archimate executable")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--expect-tools",
        type=int,
        default=None,
        help="fail unless exactly this many tools are returned",
    )
    args = parser.parse_args()

    stdout, stderr = run_server(args.command, args.timeout)
    responses, noise = parse_stdout(stdout)
    failures = collect_failures(responses, noise, args.expect_tools)

    if failures:
        sys.stderr.write("MCP smoke test FAILED\n")
        for failure in failures:
            sys.stderr.write(f"  - {failure}\n")
        if stderr.strip():
            sys.stderr.write(f"\nserver stderr:\n{stderr[-2000:]}\n")
        return 1

    sys.stderr.write(summarize(responses))
    return 0


if __name__ == "__main__":
    sys.exit(main())

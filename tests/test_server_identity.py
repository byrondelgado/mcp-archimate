"""The server must identify itself, not the SDK it is built on.

`FastMCP.__init__` accepts no `version` argument. Left alone, the low-level
`Server` keeps `version=None` and `create_initialization_options()` falls back to
`pkg_version("mcp")`, so every client displays this server as whatever MCP SDK
version happens to be pinned. That shipped in 0.7.0.

These tests pin both halves of `serverInfo`. They are cheap, and they are the
only thing standing between an SDK upgrade and a silent return of the fallback.
"""

from mcp.server.fastmcp import FastMCP

from pyarchimate_mcp_server import __version__
from pyarchimate_mcp_server.mcp_app import mcp


def _initialization_options():
    return mcp._mcp_server.create_initialization_options()  # noqa: SLF001


def test_server_reports_its_own_name():
    """The name clients display must match the distribution and console script."""
    assert _initialization_options().server_name == "mcp-archimate"


def test_server_reports_its_own_version():
    assert _initialization_options().server_version == __version__


def test_server_version_is_not_the_sdk_version():
    """The specific regression: reporting the MCP SDK's version as our own.

    A bare FastMCP falls back to the SDK version, so this asserts we differ from
    that fallback rather than hardcoding an SDK version that will change.
    """
    sdk_fallback = FastMCP(name="probe")._mcp_server.create_initialization_options()  # noqa: SLF001

    assert _initialization_options().server_version != sdk_fallback.server_version, (
        "server_version matches the MCP SDK fallback — the explicit version "
        "assignment in mcp_app.py has stopped working"
    )

"""MCP server entrypoint."""

import sys
from pathlib import Path

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

# Import prompts to register them with the shared FastMCP instance.
from pyarchimate_mcp_server import prompts  # noqa: F401
from pyarchimate_mcp_server.mcp_app import mcp

# Import resources and tools to register them with the shared FastMCP instance.
from pyarchimate_mcp_server.resources import (  # noqa: F401
    element_resources,
    model_resources,
    relationship_resources,
    view_resources,
)
from pyarchimate_mcp_server.tools import (  # noqa: F401
    element_tools,
    model_tools,
    query_tools,
    relationship_tools,
    view_tools,
    workflow_tools,
)


def main() -> None:
    """Run the MCP server using FastMCP's built-in runner."""
    mcp.run()


if __name__ == "__main__":
    main()

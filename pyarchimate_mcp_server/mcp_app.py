"""Shared FastMCP application instance."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from pyarchimate_mcp_server import __version__
from pyarchimate_mcp_server.dependencies import AppContext
from pyarchimate_mcp_server.model_manager import ArchimateModelManager

logger = logging.getLogger(__name__)

# Shared tool annotations so MCP clients can distinguish safe reads from
# mutations without guessing (used for permission UX by e.g. Claude Desktop).
READ_ONLY_TOOL = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
ADDITIVE_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    openWorldHint=False,
)
IDEMPOTENT_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
DESTRUCTIVE_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    openWorldHint=False,
)


@asynccontextmanager
async def app_lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage the server lifecycle.

    Never write to stdout here: with stdio transport, stdout is the
    JSON-RPC channel and stray text corrupts the protocol framing
    (clients hang waiting for a parseable response).
    """
    logger.info("Initializing ArchimateModelManager")
    model_manager_instance = ArchimateModelManager()
    logger.info("pyArchimate MCP server started")
    try:
        yield AppContext(model_manager=model_manager_instance)
    finally:
        logger.info("pyArchimate MCP server shutting down")


SERVER_INSTRUCTIONS = """\
ArchiMate MCP Server. Manages a single in-memory ArchiMate model (the
"active model") backed by pyArchimate. All tools and resources operate
on that active model.

Workflow:
1. Start a session with `create_empty_model`, `load_model_from_content`,
   or `load_model_from_file`. Loading or creating a model replaces the
   current active model.
2. Add elements with `add_element` or `add_elements`. The response
   `data.id` is the generated element ID; reuse it as `source_id` /
   `target_id` for relationships and as `element_id` for view nodes.
3. Add relationships with `add_relationship` or `add_relationships`.
4. Create views with `create_view`, then place nodes via
   `add_node_to_view` / `add_nodes_to_view` and connections via
   `add_connection_to_view` / `add_connections_to_view`. A relationship
   can only be drawn after both endpoint elements are visible nodes.
5. Lay out diagrams with `auto_layout_view` (default strategy
   `layered_by_type`) or run `ensure_all_relationships_in_views` to
   guarantee Archi Validator coverage.
6. Persist work with `export_model_to_file` (writes a `.archimate`
   file) or `export_model_content` (returns XML).

Tooling notes:
- Do not guess concept types: call `list_supported_types` for the
  version-specific catalog (element/relationship types, folder roots,
  access types, influence strengths, layout options). Relationship
  types drop the `Relationship` suffix (`Serving`, not
  `ServingRelationship`). Invalid-type errors include did-you-mean
  suggestions in `error.details.suggestions`.
- Every tool returns `{"status": "success", "message", "data"}` or
  `{"status": "error", "message", "error": {"code", "details?"}}`.
  Tool docstrings list their specific error codes.
- Call `get_usage_guide` for detailed workflows, anti-patterns, and
  validation guidance. Read-only inspection is also available as
  resources under `pyarchimate://activemodel/...`.
- Batch tools and `create_model_from_spec` roll back on failure by
  default (`rollback_on_error=true`).
"""


mcp = FastMCP(
    # Matches the distribution, the import package's project name and the console
    # script. Clients show this in their server list.
    name="mcp-archimate",
    instructions=SERVER_INSTRUCTIONS,
    lifespan=app_lifespan,
    dependencies=["pyArchimate", "lxml", "pydantic"],
)

# FastMCP exposes no `version` parameter, so the low-level Server keeps
# `version=None` and `create_initialization_options()` falls back to
# `pkg_version("mcp")` — which makes every client report this server as the MCP
# SDK's version (1.28.1 at time of writing) rather than its own. Set it directly.
# Reaching for the private attribute is deliberate: it is the only seam the SDK
# offers, and reporting the SDK's version is actively misleading when someone is
# diagnosing a bug against a specific release. `test_server_identity.py` fails if
# an SDK upgrade ever restores the fallback.
mcp._mcp_server.version = __version__  # noqa: SLF001


def get_model_manager() -> ArchimateModelManager:
    """Return the active model manager from the request lifespan context."""
    ctx = mcp.get_context()
    return ctx.request_context.lifespan_context.model_manager

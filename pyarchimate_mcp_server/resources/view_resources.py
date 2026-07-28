"""MCP resources for ArchiMate views."""

from typing import Any

from pyarchimate_mcp_server.mcp_app import get_model_manager as _model_manager
from pyarchimate_mcp_server.mcp_app import mcp
from pyarchimate_mcp_server.responses import error_response, success_response


@mcp.resource("pyarchimate://activemodel/views")
async def list_views() -> dict[str, Any]:
    """Return all views (diagrams) in the active model.

    Returns:
        Success envelope with `data.views` containing a list of
        `ViewDetail` objects (`id`, `name`, `nodes`, `connections`).
    """
    model_manager = _model_manager()
    views = [
        model_manager.map_view_to_detail(view).model_dump()
        for view in model_manager.list_views()
    ]
    return success_response({"views": views})


@mcp.resource("pyarchimate://activemodel/views/{view_id}")
async def get_view(view_id: str) -> dict[str, Any]:
    """Return detailed information about a single view by ID.

    Args:
        view_id: UUID of the view to retrieve.

    Returns:
        Success envelope with `data` shaped like a `ViewDetail`:
        - `id` (str)
        - `name` (str)
        - `nodes` (list of `ViewNode`: `id`, `element_id`,
          `element_name`, `element_type`, `parent_node_id`, `x`, `y`,
          `width`, `height`)
        - `connections` (list of `ViewConnection`: `id`,
          `relationship_id`, `relationship_type`, `source_node_id`,
          `target_node_id`)

    Errors:
        `ViewNotFoundError` when `view_id` is unknown.
    """
    model_manager = _model_manager()
    view = model_manager.get_view_by_id(view_id)
    if view is None:
        return error_response(
            f"View with ID '{view_id}' not found.",
            "ViewNotFoundError",
        )
    return success_response(model_manager.map_view_to_detail(view).model_dump())

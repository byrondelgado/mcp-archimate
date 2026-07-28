"""MCP resources for ArchiMate elements."""

from typing import Any

from pyarchimate_mcp_server.mcp_app import get_model_manager as _model_manager
from pyarchimate_mcp_server.mcp_app import mcp
from pyarchimate_mcp_server.responses import error_response, success_response


@mcp.resource("pyarchimate://activemodel/elements")
async def list_elements() -> dict[str, Any]:
    """Return all elements in the active model.

    Equivalent to calling `query_elements({})` but exposed as a
    read-only resource. Use `query_elements` for filtered lookups.

    Returns:
        Success envelope with `data.elements` containing a list of
        `ElementDetail` objects (`id`, `name`, `type`, `description`,
        `properties`, `folder`, `incoming_relationship_ids`,
        `outgoing_relationship_ids`).
    """
    model_manager = _model_manager()
    elements = [
        model_manager.map_element_to_detail(element).model_dump()
        for element in model_manager.list_elements()
    ]
    return success_response({"elements": elements})


@mcp.resource("pyarchimate://activemodel/elements/{element_id}")
async def get_element(element_id: str) -> dict[str, Any]:
    """Return detailed information about a single ArchiMate element by ID.

    Args:
        element_id: UUID of the element to retrieve.

    Returns:
        Success envelope with `data` shaped like an `ElementDetail`
        (`id`, `name`, `type`, `description`, `properties`, `folder`,
        `incoming_relationship_ids`, `outgoing_relationship_ids`).

    Errors:
        `ElementNotFoundError` when `element_id` is unknown.
    """
    model_manager = _model_manager()
    element = model_manager.get_element_by_id(element_id)
    if element is None:
        return error_response(
            f"Element with ID '{element_id}' not found.",
            "ElementNotFoundError",
        )
    return success_response(model_manager.map_element_to_detail(element).model_dump())

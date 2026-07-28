"""MCP resources for ArchiMate relationships."""

from typing import Any

from pyarchimate_mcp_server.mcp_app import get_model_manager as _model_manager
from pyarchimate_mcp_server.mcp_app import mcp
from pyarchimate_mcp_server.responses import error_response, success_response


@mcp.resource("pyarchimate://activemodel/relationships")
async def list_relationships() -> dict[str, Any]:
    """Return all relationships in the active model.

    Equivalent to calling `query_relationships({})` but exposed as a
    read-only resource. Use `query_relationships` for filtered lookups.

    Returns:
        Success envelope with `data.relationships` containing a list of
        `RelationshipDetail` objects (`id`, `name`, `type`,
        `description`, `properties`, `access_type`,
        `influence_strength`, `source_element_id`,
        `target_element_id`).
    """
    model_manager = _model_manager()
    relationships = [
        model_manager.map_relationship_to_detail(relationship).model_dump()
        for relationship in model_manager.list_relationships()
    ]
    return success_response({"relationships": relationships})


@mcp.resource("pyarchimate://activemodel/relationships/{relationship_id}")
async def get_relationship(relationship_id: str) -> dict[str, Any]:
    """Return detailed information about a single relationship by ID.

    Args:
        relationship_id: UUID of the relationship to retrieve.

    Returns:
        Success envelope with `data` shaped like a `RelationshipDetail`
        (`id`, `name`, `type`, `description`, `properties`,
        `access_type`, `influence_strength`, `source_element_id`,
        `target_element_id`).

    Errors:
        `RelationshipNotFoundError` when `relationship_id` is unknown.
    """
    model_manager = _model_manager()
    relationship = model_manager.get_relationship_by_id(relationship_id)
    if relationship is None:
        return error_response(
            f"Relationship with ID '{relationship_id}' not found.",
            "RelationshipNotFoundError",
        )
    return success_response(
        model_manager.map_relationship_to_detail(relationship).model_dump(),
    )

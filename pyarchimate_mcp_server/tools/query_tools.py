"""MCP tools for querying active ArchiMate model content."""

from typing import Any

from pyarchimate_mcp_server.exceptions import ArchiMateMCPError
from pyarchimate_mcp_server.mcp_app import (
    READ_ONLY_TOOL,
    mcp,
)
from pyarchimate_mcp_server.mcp_app import get_model_manager as _model_manager
from pyarchimate_mcp_server.responses import error_response, success_response


@mcp.tool(annotations=READ_ONLY_TOOL)
async def query_elements(filter_criteria: dict[str, Any]) -> dict[str, Any]:
    """Query elements in the active model with optional filters.

    All filters are AND-combined. Pass an empty `{}` to list every
    element (equivalent to the `pyarchimate://activemodel/elements`
    resource).

    Supported filter keys:
        - `type` (str): Match elements with this exact ArchiMate type,
          e.g. `BusinessActor`, `ApplicationComponent`.
        - `name_contains` (str): Case-insensitive substring match
          against element name.
        - `properties_contain` (dict[str, str]): Match elements whose
          custom properties contain every provided key/value pair.

    Args:
        filter_criteria: Dict containing zero or more of the keys
            above. Unknown keys are ignored.

    Returns:
        Success envelope with `data.elements`, a list of
        `ElementDetail` objects (`id`, `name`, `type`, `description`,
        `properties`, `folder`, `incoming_relationship_ids`,
        `outgoing_relationship_ids`).

    Errors:
        `ModelNotFoundError` if no model is active.
    """
    try:
        model_manager = _model_manager()
        elements = [
            model_manager.map_element_to_detail(element).model_dump()
            for element in model_manager.query_elements(filter_criteria)
        ]
        return success_response({"elements": elements}, "Elements queried.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.__class__.__name__, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def query_relationships(filter_criteria: dict[str, Any]) -> dict[str, Any]:
    """Query relationships in the active model with optional filters.

    All filters are AND-combined. Pass an empty `{}` to list every
    relationship (equivalent to the
    `pyarchimate://activemodel/relationships` resource).

    Supported filter keys:
        - `type` (str): Match relationships with this exact pyArchimate
          relationship type, e.g. `Serving`, `Composition`,
          `Assignment`. The `Relationship` suffix is not used.
        - `source_id` (str): Match relationships whose source element
          UUID equals this value.
        - `target_id` (str): Match relationships whose target element
          UUID equals this value.

    Args:
        filter_criteria: Dict containing zero or more of the keys
            above. Unknown keys are ignored.

    Returns:
        Success envelope with `data.relationships`, a list of
        `RelationshipDetail` objects (`id`, `name`, `type`,
        `description`, `properties`, `access_type`,
        `influence_strength`, `source_element_id`,
        `target_element_id`).

    Errors:
        `InvalidRelationshipTypeError` for an unknown `type`.
        `ModelNotFoundError` if no model is active.
    """
    try:
        model_manager = _model_manager()
        relationships = [
            model_manager.map_relationship_to_detail(relationship).model_dump()
            for relationship in model_manager.query_relationships(filter_criteria)
        ]
        return success_response(
            {"relationships": relationships},
            "Relationships queried.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.__class__.__name__, exc.details)

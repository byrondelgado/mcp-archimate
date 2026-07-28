"""MCP tools for ArchiMate element operations."""

from typing import Any

from pyarchimate_mcp_server.exceptions import ArchiMateMCPError
from pyarchimate_mcp_server.mcp_app import (
    ADDITIVE_TOOL,
    DESTRUCTIVE_TOOL,
    IDEMPOTENT_TOOL,
    mcp,
)
from pyarchimate_mcp_server.mcp_app import get_model_manager as _model_manager
from pyarchimate_mcp_server.responses import error_response, success_response


@mcp.tool(annotations=ADDITIVE_TOOL)
async def add_element(  # noqa: PLR0913, PLR0917
    element_type: str,
    name: str,
    description: str | None = None,
    folder_path: str | None = None,
    properties: dict[str, Any] | None = None,
    element_id: str | None = None,
) -> dict[str, Any]:
    """Add a new ArchiMate element to the active model.

    Call `list_supported_types` to discover valid `element_type` values
    if you are not certain. The response `data.id` is the canonical
    element ID; use it as `source_id`/`target_id` when adding
    relationships and as `element_id` when adding view nodes.

    Args:
        element_type: A supported ArchiMate element type, e.g.
            `BusinessActor`, `BusinessProcess`, `ApplicationComponent`,
            `ApplicationService`, `DataObject`, `Node`, `Artifact`,
            `Goal`, `Stakeholder`, `Grouping`, `AndJunction`,
            `OrJunction`. Use `list_supported_types` for the full list.
        name: Element name. Must be a non-empty string.
        description: Optional element documentation text.
        folder_path: Optional conceptual folder path. Roots are
            normalized: `Business`, `/Business`, and `business` resolve
            to `/Business`. Sub-folders such as `/Business/Actors` are
            preserved.
        properties: Optional custom property key-value pairs. Values are
            stored as strings.
        element_id: Optional stable element ID. When omitted a UUID is
            generated. Must be unique across the
            *entire* active model — not just within this call, this
            batch, or this concept type. An id already used by any
            element, relationship, view, node or connection is
            rejected. When generating ids across several batches,
            namespace them (`bp-`, `ac-`, `tech-`) so batches cannot
            collide.

    Returns:
        Success envelope with `data` shaped like an `ElementDetail`:
        `{id, name, type, description, properties, folder,
        incoming_relationship_ids, outgoing_relationship_ids}`.

    Errors:
        `INVALID_ELEMENT_NAME` when `name` is missing or blank.
        `InvalidElementTypeError` for an unknown `element_type`.
        `ModelNotFoundError` if no model is active.
        `ModelOperationError` for a duplicate `element_id` or invalid
        folder path.
    """
    if not isinstance(name, str) or not name.strip():
        return error_response("Invalid element name.", "INVALID_ELEMENT_NAME")

    try:
        model_manager = _model_manager()
        element = model_manager.add_archimate_element(
            name=name.strip(),
            element_type=element_type,
            description=description,
            folder_path=folder_path,
            properties=properties,
            element_id=element_id,
        )
        detail = model_manager.map_element_to_detail(element).model_dump()
        return success_response(detail, "Element added.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=ADDITIVE_TOOL)
async def add_elements(
    elements: list[dict[str, Any]],
    *,
    rollback_on_error: bool = True,
) -> dict[str, Any]:
    """Add multiple elements to the active model in one call.

    Each element item supports the same fields as `add_element`. Both
    short and long field names are accepted (`type` or `element_type`,
    `id` or `element_id`).

    IDs are unique across the **entire active model**, not per call,
    per batch, or per concept type. Splitting a build across several
    batches does not give each batch its own id space, so namespace
    generated ids (`bp-`, `ac-`, `tech-`) rather than restarting the
    same naming pattern in each one.

    Element item shape:
        ```
        {
          "id": "id-customer",        # optional stable ref
          "name": "Customer",          # required
          "type": "BusinessActor",     # required (alias: element_type)
          "description": "...",       # optional
          "folder_path": "/Business", # optional
          "properties": {"k": "v"}     # optional
        }
        ```

    Args:
        elements: List of element item objects.
        rollback_on_error: When true (default), restore the previous
            model state if any item fails. Set to false to keep partial
            results.

    Returns:
        Success envelope with `data.elements` (list of `ElementDetail`),
        `data.count`, and `data.rollback_on_error`.

    Errors:
        `ModelNotFoundError`, `InvalidElementTypeError`,
        `ModelOperationError` for the first failing item.
    """
    try:
        model_manager = _model_manager()
        added_elements = model_manager.add_archimate_elements(
            elements,
            rollback_on_error=rollback_on_error,
        )
        return success_response(
            {
                "elements": [
                    model_manager.map_element_to_detail(element).model_dump()
                    for element in added_elements
                ],
                "count": len(added_elements),
                "rollback_on_error": rollback_on_error,
            },
            "Elements added.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=IDEMPOTENT_TOOL)
async def update_element(
    element_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Update an existing ArchiMate element.

    Updates is a dict containing only the fields to change. Other fields
    are left untouched. Properties are merged into existing properties
    (use an empty value to clear a key on subsequent updates).

    Args:
        element_id: ID of the element to update.
        updates: Mapping of fields to update. Supported keys:
            - `name` (str): New element name.
            - `description` (str): New documentation text.
            - `folder_path` (str): New folder path; folder root must
              match the element's ArchiMate category.
            - `properties` (dict[str, str]): Property updates merged
              into existing properties.
            Element type cannot be changed; recreate the element to
            change its type.

    Returns:
        Success envelope with the updated `ElementDetail` in `data`.

    Errors:
        `ElementNotFoundError` when `element_id` is unknown.
        `ModelOperationError` for invalid folder paths.
    """
    try:
        model_manager = _model_manager()
        success = model_manager.update_element_properties(
            element_id=element_id,
            name=updates.get("name"),
            description=updates.get("description"),
            properties=updates.get("properties"),
            folder_path=updates.get("folder_path"),
        )
        if not success:
            return error_response(
                f"Element with ID '{element_id}' not found.",
                "ElementNotFoundError",
            )
        element = model_manager.get_element_by_id(element_id)
        return success_response(
            model_manager.map_element_to_detail(element).model_dump(),
            "Element updated.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=DESTRUCTIVE_TOOL)
async def delete_element(element_id: str) -> dict[str, Any]:
    """Delete an ArchiMate element from the active model.

    pyArchimate also removes dependent concepts such as relationships
    and visual nodes/connections referencing the deleted element.

    Args:
        element_id: ID of the element to delete.

    Returns:
        Success envelope with `data.deleted=true`.

    Errors:
        `ElementNotFoundError` when `element_id` is unknown.
    """
    try:
        success = _model_manager().delete_element(element_id)
        if not success:
            return error_response(
                f"Element with ID '{element_id}' not found.",
                "ElementNotFoundError",
            )
        return success_response({"deleted": True}, "Element deleted.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)

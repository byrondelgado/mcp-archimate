"""MCP tools for ArchiMate relationship operations."""

from typing import Any

from pyarchimate_mcp_server.exceptions import ArchiMateMCPError
from pyarchimate_mcp_server.mcp_app import (
    ADDITIVE_TOOL,
    DESTRUCTIVE_TOOL,
    IDEMPOTENT_TOOL,
    READ_ONLY_TOOL,
    mcp,
)
from pyarchimate_mcp_server.mcp_app import get_model_manager as _model_manager
from pyarchimate_mcp_server.responses import error_response, success_response


@mcp.tool(annotations=ADDITIVE_TOOL)
async def add_relationship(  # noqa: PLR0913
    relationship_type: str,
    source_id: str,
    target_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    properties: dict[str, Any] | None = None,
    access_type: str | None = None,
    influence_strength: str | None = None,
    is_directed: bool | None = None,
    relationship_id: str | None = None,
    semantic_validation: str = "warn",
) -> dict[str, Any]:
    """Add a new ArchiMate relationship between two elements.

    Both endpoints must already exist as elements in the active model.
    Use `list_supported_types` to discover valid `relationship_type`,
    `access_type`, and `influence_strength` values.

    Args:
        relationship_type: A supported pyArchimate relationship type,
            without the `Relationship` suffix. Examples: `Assignment`,
            `Serving`, `Composition`, `Aggregation`, `Realization`,
            `Triggering`, `Flow`, `Access`, `Influence`,
            `Specialization`, `Association`. Note: Archi's "Used By"
            concept maps to `Serving`.
        source_id: ID of the source element.
        target_id: ID of the target element.
        name: Optional relationship name.
        description: Optional documentation text.
        properties: Optional custom property key-value pairs (string
            values).
        access_type: Required only for `Access` relationships. One of
            `Access`, `Read`, `Write`, `ReadWrite`.
        influence_strength: Required only for `Influence` relationships.
            One of `+`, `++`, `-`, `--`, or `0`-`10`.
        relationship_id: Optional stable relationship ID. When omitted a
            UUID is generated. Must be unique across the
            *entire* active model — not just within this call, this
            batch, or this concept type. An id already used by any
            element, relationship, view, node or connection is
            rejected. When generating ids across several batches,
            namespace them (`bp-`, `ac-`, `tech-`) so batches cannot
            collide.

    Returns:
        Success envelope with `data` shaped like a `RelationshipDetail`:
        `{id, name, type, description, properties, access_type,
        influence_strength, source_element_id, target_element_id}`.

    Errors:
        `InvalidRelationshipTypeError` for an unknown
            `relationship_type`.
        `ElementNotFoundError` when `source_id` or `target_id` is
            unknown.
        `ModelNotFoundError` if no model is active.
        `ModelOperationError` for invalid relationship combinations,
            duplicate `relationship_id`, or unsupported access/influence
            values.
    """
    try:
        model_manager = _model_manager()
        relationship = model_manager.add_archimate_relationship(
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship_type,
            name=name,
            description=description,
            properties=properties,
            access_type=access_type,
            influence_strength=influence_strength,
            is_directed=is_directed,
            relationship_id=relationship_id,
            semantic_validation=semantic_validation,
        )
        detail = model_manager.map_relationship_to_detail(relationship).model_dump()
        message = "Relationship added."
        if semantic_validation == "warn":
            warning = model_manager.check_relationship_semantics(
                relationship_type,
                source_id,
                target_id,
                access_type,
            )
            if warning:
                detail["semantic_warning"] = warning
                message = (
                    "Relationship added with semantic warnings; see "
                    "data.semantic_warning for valid alternatives."
                )
        return success_response(detail, message)
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=ADDITIVE_TOOL)
async def add_relationships(
    relationships: list[dict[str, Any]],
    *,
    rollback_on_error: bool = True,
    semantic_validation: str = "warn",
) -> dict[str, Any]:
    """Add multiple relationships to the active model in one call.

    Each relationship item supports the same fields as `add_relationship`.
    Short and long field names are both accepted (`type` or
    `relationship_type`, `source` or `source_id`, `target` or
    `target_id`, `id` or `relationship_id`).

    IDs are unique across the **entire active model**, not per call,
    per batch, or per concept type. Splitting a build across several
    batches does not give each batch its own id space, so namespace
    generated ids (`bp-`, `ac-`, `tech-`) rather than restarting the
    same naming pattern in each one.

    Relationship item shape:
        ```
        {
          "id": "id-uses",                # optional stable ref
          "type": "Serving",                # required (alias: relationship_type)
          "source": "id-customer",          # required (alias: source_id)
          "target": "id-portal",            # required (alias: target_id)
          "name": "uses",                   # optional
          "description": "...",            # optional
          "properties": {"k": "v"},         # optional
          "access_type": "Read",            # for Access only
          "influence_strength": "+"         # for Influence only
        }
        ```

    Args:
        relationships: List of relationship item objects.
        rollback_on_error: When true (default), restore the previous
            model state if any item fails.

    Returns:
        Success envelope with `data.relationships` (list of
        `RelationshipDetail`), `data.count`, and
        `data.rollback_on_error`.

    Errors:
        `InvalidRelationshipTypeError`, `ElementNotFoundError`,
        `ModelNotFoundError`, `ModelOperationError` for the first
        failing item.
    """
    try:
        model_manager = _model_manager()
        relationship_specs = [
            {"semantic_validation": semantic_validation, **relationship}
            for relationship in relationships
        ]
        added_relationships = model_manager.add_archimate_relationships(
            relationship_specs,
            rollback_on_error=rollback_on_error,
        )
        details = [
            model_manager.map_relationship_to_detail(relationship).model_dump()
            for relationship in added_relationships
        ]
        message = "Relationships added."
        warning_count = 0
        if semantic_validation == "warn":
            for detail, relationship in zip(details, added_relationships, strict=True):
                warning = model_manager.check_relationship_semantics(
                    relationship.type,
                    relationship.source.uuid,
                    relationship.target.uuid,
                    getattr(relationship, "access_type", None),
                )
                if warning:
                    detail["semantic_warning"] = warning
                    warning_count += 1
            if warning_count:
                message = (
                    f"Relationships added with {warning_count} semantic "
                    "warning(s); see semantic_warning entries for valid "
                    "alternatives."
                )
        return success_response(
            {
                "relationships": details,
                "count": len(details),
                "rollback_on_error": rollback_on_error,
            },
            message,
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=IDEMPOTENT_TOOL)
async def update_relationship(
    relationship_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Update an existing ArchiMate relationship.

    Endpoints (source/target) and relationship type cannot be changed.
    Recreate the relationship to change those.

    Args:
        relationship_id: ID of the relationship to update.
        updates: Mapping of fields to update. Supported keys:
            - `name` (str)
            - `description` (str)
            - `properties` (dict[str, str]): merged into existing
              properties.
            - `access_type` (str): only meaningful for `Access`. One of
              `Access`, `Read`, `Write`, `ReadWrite`.
            - `influence_strength` (str): only meaningful for
              `Influence`. One of `+`, `++`, `-`, `--`, or `0`-`10`.

    Returns:
        Success envelope with the updated `RelationshipDetail` in
        `data`.

    Errors:
        `RelationshipNotFoundError` when `relationship_id` is unknown.
        `ModelOperationError` for unsupported access/influence values.
    """
    try:
        model_manager = _model_manager()
        success = model_manager.update_relationship_properties(
            relationship_id=relationship_id,
            name=updates.get("name"),
            description=updates.get("description"),
            properties=updates.get("properties"),
            access_type=updates.get("access_type"),
            influence_strength=updates.get("influence_strength"),
            is_directed=updates.get("is_directed"),
        )
        if not success:
            return error_response(
                f"Relationship with ID '{relationship_id}' not found.",
                "RelationshipNotFoundError",
            )
        relationship = model_manager.get_relationship_by_id(relationship_id)
        return success_response(
            model_manager.map_relationship_to_detail(relationship).model_dump(),
            "Relationship updated.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=DESTRUCTIVE_TOOL)
async def delete_relationship(relationship_id: str) -> dict[str, Any]:
    """Delete an ArchiMate relationship from the active model.

    pyArchimate also removes any visual connections that referenced the
    deleted relationship.

    Args:
        relationship_id: ID of the relationship to delete.

    Returns:
        Success envelope with `data.deleted=true`.

    Errors:
        `RelationshipNotFoundError` when `relationship_id` is unknown.
    """
    try:
        success = _model_manager().delete_relationship(relationship_id)
        if not success:
            return error_response(
                f"Relationship with ID '{relationship_id}' not found.",
                "RelationshipNotFoundError",
            )
        return success_response({"deleted": True}, "Relationship deleted.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def get_relationship_compatibility(
    source_type: str,
    target_type: str,
) -> dict[str, Any]:
    """Return valid ArchiMate relationship options for source and target types."""
    try:
        return success_response(
            _model_manager().get_relationship_compatibility(source_type, target_type),
            "Relationship compatibility returned.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def recommend_relationship(  # noqa: PLR0913
    source_id: str | None = None,
    target_id: str | None = None,
    *,
    source_type: str | None = None,
    target_type: str | None = None,
    intent: str | None = None,
    strict_archimate: bool = True,
) -> dict[str, Any]:
    """Recommend valid relationship types for source/target ids or types."""
    try:
        return success_response(
            _model_manager().recommend_relationship(
                source_id=source_id,
                target_id=target_id,
                source_type=source_type,
                target_type=target_type,
                intent=intent,
                strict_archimate=strict_archimate,
            ),
            "Relationship recommendations returned.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=DESTRUCTIVE_TOOL)
async def repair_semantic_issues(  # noqa: PLR0913
    repair_ids: list[str] | None = None,
    *,
    repair_all_deterministic: bool = False,
    preserve_relationship_ids: bool = True,
    rollback_on_error: bool = True,
    update_views: bool = True,
    auto_layout: bool = False,
) -> dict[str, Any]:
    """Apply selected deterministic semantic relationship repairs."""
    try:
        return success_response(
            _model_manager().repair_semantic_issues(
                repair_ids=repair_ids,
                repair_all_deterministic=repair_all_deterministic,
                preserve_relationship_ids=preserve_relationship_ids,
                rollback_on_error=rollback_on_error,
                update_views=update_views,
                auto_layout=auto_layout,
            ),
            "Semantic repairs applied.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)

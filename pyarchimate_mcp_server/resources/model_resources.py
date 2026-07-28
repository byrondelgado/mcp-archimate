"""MCP resources for active model data."""

from typing import Any

from pyarchimate_mcp_server.exceptions import ArchiMateMCPError
from pyarchimate_mcp_server.mcp_app import get_model_manager as _model_manager
from pyarchimate_mcp_server.mcp_app import mcp
from pyarchimate_mcp_server.responses import error_response, success_response


@mcp.resource("pyarchimate://activemodel/info")
async def get_model_info() -> dict[str, Any]:
    """Return high-level information about the active model.

    `data.is_loaded` is `false` and counts are zero when no model is
    active.

    Response shape:
        ```
        {
          "status": "success",
          "message": "OK",
          "data": {
            "name": str | None,
            "id": str | None,
            "documentation": str | None,
            "properties": dict[str, str],
            "elements_count": int,
            "relationships_count": int,
            "views_count": int,
            "is_loaded": bool
          }
        }
        ```
    """
    return success_response(_model_manager().get_model_info())


@mcp.resource("pyarchimate://activemodel/content")
async def get_model_content() -> dict[str, Any]:
    """Return the full content of the active model as Open Group exchange XML.

    Use the `export_model_content` tool when you need different output
    formats (e.g. Archi native `.archimate`) or want to run auto-layout
    before serialization.

    Returns:
        Success envelope with `data.content` (XML string).

    Errors:
        `ModelNotFoundError` if no model is active.
    """
    try:
        content = _model_manager().get_model_content_as_string()
        return success_response({"content": content})
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.__class__.__name__, exc.details)


@mcp.resource("pyarchimate://activemodel/validation")
async def get_model_validation() -> dict[str, Any]:
    """Return visual reference validation results for the active model.

    Equivalent to calling the `validate_model` tool. Use the
    `validate_semantics` tool for ArchiMate semantic checks beyond
    visual references.

    Returns:
        Success envelope with `data.is_valid` (bool),
        `data.invalid_connection_ids`, `data.invalid_node_ids`, and
        matching count fields.

    Errors:
        `ModelNotFoundError` if no model is active.
    """
    try:
        return success_response(_model_manager().validate_model())
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.__class__.__name__, exc.details)

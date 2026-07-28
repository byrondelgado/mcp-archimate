"""Response helpers for MCP tools and resources."""

from typing import Any


def success_response(
    data: dict[str, Any] | list[Any] | str | None = None,
    message: str = "OK",
) -> dict[str, Any]:
    """Return a standard success payload."""
    response: dict[str, Any] = {"status": "success", "message": message}
    if data is not None:
        response["data"] = data
    return response


def error_response(
    message: str,
    code: str = "ERROR",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a standard error payload."""
    response = {
        "status": "error",
        "message": message,
        "error": {"code": code},
    }
    if details:
        response["error"]["details"] = details
    return response

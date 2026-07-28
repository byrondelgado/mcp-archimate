"""Custom exceptions for ArchiMate MCP Server"""


class ArchiMateMCPError(Exception):
    """Base exception for ArchiMate MCP Server.

    `code` is what reaches `error.code` in the response envelope. It
    defaults to the class name, which is the long-standing convention
    here; `error_code` overrides it where a stable SCREAMING_SNAKE code
    is part of the documented contract rather than an implementation
    detail. Tools read `exc.code`, never `type(exc).__name__`, so an
    override works everywhere without touching call sites.
    """

    error_code: str | None = None

    def __init__(self, message: str = "", details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

    @property
    def code(self) -> str:
        """Return the envelope error code for this exception."""
        return self.error_code or type(self).__name__


class ModelNotFoundError(ArchiMateMCPError):
    """Raised when a requested model is not found"""


class ElementNotFoundError(ArchiMateMCPError):
    """Raised when a requested element is not found"""


class RelationshipNotFoundError(ArchiMateMCPError):
    """Raised when a requested relationship is not found"""


class ViewNotFoundError(ArchiMateMCPError):
    """Raised when a requested view is not found"""


class InvalidElementTypeError(ArchiMateMCPError):
    """Raised when an invalid ArchiMate element type is specified"""


class InvalidRelationshipTypeError(ArchiMateMCPError):
    """Raised when an invalid ArchiMate relationship type is specified"""


class InvalidRelationshipCombinationError(ArchiMateMCPError):
    """Raised when a relationship is invalid for source/target types"""


class UnsupportedFormatError(ArchiMateMCPError):
    """Raised when an unsupported file format is encountered"""


class ModelOperationError(ArchiMateMCPError):
    """Raised when a model operation fails"""


class PathOutsideAllowedRootsError(ArchiMateMCPError):
    """Raised when a file path resolves outside the configured roots"""

    error_code = "PATH_OUTSIDE_ALLOWED_ROOTS"


class InvalidAllowedRootsError(ArchiMateMCPError):
    """Raised when the allowed-roots environment configuration is unusable"""

    error_code = "INVALID_ALLOWED_ROOTS"

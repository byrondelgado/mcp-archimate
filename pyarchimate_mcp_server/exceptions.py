"""Custom exceptions for ArchiMate MCP Server"""


class ArchiMateMCPError(Exception):
    """Base exception for ArchiMate MCP Server"""

    def __init__(self, message: str = "", details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


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

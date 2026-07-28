"""Constants for ArchiMate MCP Server."""

from pyArchimate.constants import ARCHI_CATEGORY

# ArchiMate type names supported by the installed pyArchimate version.
ARCHIMATE_ELEMENT_TYPES = sorted(
    type_name
    for type_name, category in ARCHI_CATEGORY.items()
    if category not in {"Relationship", "View"}
)

ARCHIMATE_RELATIONSHIP_TYPES = sorted(
    type_name
    for type_name, category in ARCHI_CATEGORY.items()
    if category == "Relationship"
)

# File formats supported
SUPPORTED_FORMATS = [
    "archi",  # Archi native .archimate format
    "archimate",  # ArchiMate Exchange Format
    "xml",  # Generic XML
]

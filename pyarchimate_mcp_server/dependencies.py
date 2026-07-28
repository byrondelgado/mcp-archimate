from dataclasses import dataclass

from pyarchimate_mcp_server.model_manager import ArchimateModelManager


@dataclass
class AppContext:
    """Type-safe context for application resources."""

    model_manager: ArchimateModelManager

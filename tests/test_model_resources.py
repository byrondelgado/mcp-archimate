import asyncio

from pyarchimate_mcp_server.model_manager import ArchimateModelManager
from pyarchimate_mcp_server.resources import model_resources


def test_model_info_resource_reports_documentation_and_properties(monkeypatch):
    manager = ArchimateModelManager()
    manager.create_new_model(
        "Resource Metadata",
        description="Documentation exposed by the info resource.",
        properties={"owner": "EA"},
    )
    monkeypatch.setattr(model_resources, "_model_manager", lambda: manager)

    response = asyncio.run(model_resources.get_model_info())

    assert response["status"] == "success"
    assert response["data"]["name"] == "Resource Metadata"
    assert (
        response["data"]["documentation"]
        == "Documentation exposed by the info resource."
    )
    assert response["data"]["properties"] == {"owner": "EA"}

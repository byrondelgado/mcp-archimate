import asyncio

from pyarchimate_mcp_server.model_manager import ArchimateModelManager
from pyarchimate_mcp_server.tools import workflow_tools


def test_usage_guide_discourages_source_inspection():
    response = asyncio.run(workflow_tools.get_usage_guide())

    assert response["status"] == "success"
    rules = " ".join(response["data"]["agent_operating_rules"])
    assert "do not inspect the server source code" in rules
    assert "recommend_relationship" in rules
    assert response["data"]["standards_target"]["hard_validation"] == (
        "ArchiMate 3.2-compatible"
    )
    assert "BusinessProcess -> ApplicationService" in str(
        response["data"]["common_anti_patterns"],
    )
    assert (
        "build_quality_report" in response["data"]["validation_before_export_checklist"]
    )
    assert response["data"]["existing_model_workflow"][0]["tool"] == (
        "load_model_from_file"
    )


def test_load_model_from_file_returns_compact_inspection(tmp_path, monkeypatch):
    source_manager = ArchimateModelManager()
    source_manager.create_new_model("Workflow Load Test")
    source_manager.add_archimate_element("Customer", "BusinessActor")

    model_path = tmp_path / "workflow-load-test.archimate"
    model_path.write_text(
        source_manager.get_model_content_as_string("archi"),
        encoding="utf-8",
    )

    loaded_manager = ArchimateModelManager()
    monkeypatch.setattr(workflow_tools, "_model_manager", lambda: loaded_manager)

    response = asyncio.run(
        workflow_tools.load_model_from_file(str(model_path), sample_limit=2),
    )

    assert response["status"] == "success"
    assert response["data"]["model_info"]["name"] == "Workflow Load Test"
    assert response["data"]["inspection"]["model_info"]["elements_count"] == 1
    assert response["data"]["inspection"]["visual_validation"]["is_valid"] is True
    assert response["data"]["inspection"]["recommended_next_calls"][0]["tool"] == (
        "inspect_active_model"
    )


def test_inspect_active_model_requires_loaded_model(monkeypatch):
    empty_manager = ArchimateModelManager()
    monkeypatch.setattr(workflow_tools, "_model_manager", lambda: empty_manager)

    response = asyncio.run(workflow_tools.inspect_active_model())

    assert response["status"] == "error"
    assert response["error"]["code"] == "ModelNotFoundError"

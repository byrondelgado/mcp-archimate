import asyncio

from pyarchimate_mcp_server.model_manager import ArchimateModelManager
from pyarchimate_mcp_server.tools import model_tools, workflow_tools


def test_load_model_from_content_rejects_path_like_argument():
    response = asyncio.run(
        model_tools.load_model_from_content(
            "sample-ecommerce-purchase-payment.archimate",
        ),
    )

    assert response["status"] == "error"
    assert response["error"]["code"] == "INVALID_MODEL_CONTENT"
    assert "load_model_from_file" in response["message"]


def test_load_model_from_file_loads_local_archimate_file(tmp_path, monkeypatch):
    source_manager = ArchimateModelManager()
    source_manager.create_new_model("File Load Test")
    source_manager.add_archimate_element("Customer", "BusinessActor")

    model_path = tmp_path / "file-load-test.archimate"
    model_path.write_text(
        source_manager.get_model_content_as_string("archi"),
        encoding="utf-8",
    )

    loaded_manager = ArchimateModelManager()
    monkeypatch.setattr(workflow_tools, "_model_manager", lambda: loaded_manager)

    response = asyncio.run(workflow_tools.load_model_from_file(str(model_path)))

    assert response["status"] == "success"
    assert response["data"]["model_info"]["name"] == "File Load Test"
    assert response["data"]["model_info"]["elements_count"] == 1
    assert loaded_manager.get_active_model() is not None


def test_load_model_from_file_reports_missing_path(tmp_path):
    missing = tmp_path / "model.archimate"

    response = asyncio.run(workflow_tools.load_model_from_file(str(missing)))

    assert response["status"] == "error"
    assert response["error"]["code"] == "FILE_NOT_FOUND"
    assert response["message"] == f"File not found: {missing}"


def test_load_model_from_file_refuses_a_path_outside_the_allowed_roots():
    response = asyncio.run(
        workflow_tools.load_model_from_file("/etc/hosts"),
    )

    assert response["status"] == "error"
    assert response["error"]["code"] == "PATH_OUTSIDE_ALLOWED_ROOTS"
    # The boundary is checked before the existence check on purpose, so
    # the tool cannot be used to probe for files it may not read: an
    # existing file outside the roots is indistinguishable from a
    # missing one.
    assert "FILE_NOT_FOUND" not in response["error"]["code"]
    details = response["error"]["details"]
    assert details["path"] == "/etc/hosts"
    # Reported as resolved, not as given: on macOS /etc is a symlink to
    # /private/etc, and it is the resolved target that failed the check.
    assert details["resolved_path"].endswith("etc/hosts")
    assert details["environment_variable"] == "MCP_ARCHIMATE_ALLOWED_READ_ROOTS"
    assert details["allowed_roots"]


def test_create_empty_model_sets_documentation_and_properties(monkeypatch):
    manager = ArchimateModelManager()
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)

    response = asyncio.run(
        model_tools.create_empty_model(
            "Documented Model",
            description="Scope: payments platform.",
            properties={"owner": "EA"},
        ),
    )

    assert response["status"] == "success"
    model_info = response["data"]["model_info"]
    assert model_info["name"] == "Documented Model"
    assert model_info["documentation"] == "Scope: payments platform."
    assert model_info["properties"] == {"owner": "EA"}


def test_update_model_changes_metadata_on_a_loaded_model(monkeypatch):
    source_manager = ArchimateModelManager()
    source_manager.create_new_model("Loaded Model")
    content = source_manager.get_model_content_as_string("archi")

    manager = ArchimateModelManager()
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)
    load_response = asyncio.run(model_tools.load_model_from_content(content, "archi"))
    assert load_response["status"] == "success"
    assert load_response["data"]["model_info"]["documentation"] is None

    response = asyncio.run(
        model_tools.update_model(
            {
                "name": "Renamed Loaded Model",
                "description": "Documented after loading.",
                "properties": {"owner": "EA"},
            },
        ),
    )

    assert response["status"] == "success"
    model_info = response["data"]["model_info"]
    assert model_info["name"] == "Renamed Loaded Model"
    assert model_info["documentation"] == "Documented after loading."
    assert model_info["properties"] == {"owner": "EA"}


def test_update_model_accepts_documentation_alias_for_description(monkeypatch):
    manager = ArchimateModelManager()
    manager.create_new_model("Alias Model")
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)

    response = asyncio.run(
        model_tools.update_model({"documentation": "Written via the alias key."}),
    )

    assert response["status"] == "success"
    assert (
        response["data"]["model_info"]["documentation"] == "Written via the alias key."
    )


def test_update_model_rejects_unsupported_update_keys(monkeypatch):
    manager = ArchimateModelManager()
    manager.create_new_model("Strict Keys Model")
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)

    response = asyncio.run(model_tools.update_model({"desc": "Typo key."}))

    assert response["status"] == "error"
    assert response["error"]["code"] == "INVALID_MODEL_UPDATE"
    assert response["error"]["details"]["unsupported_keys"] == ["desc"]
    assert "description" in response["error"]["details"]["supported_keys"]
    assert manager.get_model_info()["documentation"] is None


def test_update_model_rejects_blank_name(monkeypatch):
    manager = ArchimateModelManager()
    manager.create_new_model("Blank Name Model")
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)

    response = asyncio.run(model_tools.update_model({"name": "   "}))

    assert response["status"] == "error"
    assert response["error"]["code"] == "INVALID_MODEL_NAME"
    assert manager.get_model_info()["name"] == "Blank Name Model"


def test_update_model_rejects_non_mapping_properties(monkeypatch):
    """A rejected update writes nothing at all — not even the valid fields.

    The other fields are sent alongside on purpose: validating `properties`
    after writing `name` and `description` would report an error on a model
    that had already been renamed and re-documented, which a caller reading
    `status: error` would never suspect.
    """
    manager = ArchimateModelManager()
    manager.create_new_model(
        "Properties Shape Model",
        description="Original doc",
    )
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)

    response = asyncio.run(
        model_tools.update_model(
            {
                "name": "Renamed",
                "description": "Rewritten doc",
                "properties": "owner=EA",
            },
        ),
    )

    assert response["status"] == "error"
    assert response["error"]["code"] == "ModelOperationError"
    model_info = manager.get_model_info()
    assert model_info["properties"] == {}
    assert model_info["name"] == "Properties Shape Model"
    assert model_info["documentation"] == "Original doc"


def test_update_model_without_active_model_reports_model_not_found(monkeypatch):
    manager = ArchimateModelManager()
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)

    response = asyncio.run(model_tools.update_model({"name": "No Active Model"}))

    assert response["status"] == "error"
    assert response["error"]["code"] == "ModelNotFoundError"


def test_model_metadata_round_trips_through_export_and_reload_tools(
    tmp_path,
    monkeypatch,
):
    manager = ArchimateModelManager()
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)

    asyncio.run(model_tools.create_empty_model("Round Trip Metadata"))
    asyncio.run(
        model_tools.update_model(
            {
                "description": "Documentation that must survive export.",
                "properties": {"owner": "EA"},
            },
        ),
    )

    model_path = tmp_path / "round-trip-metadata.archimate"
    export_response = asyncio.run(
        model_tools.export_model_to_file(str(model_path), "archi"),
    )
    assert export_response["status"] == "success"

    reloaded_manager = ArchimateModelManager()
    monkeypatch.setattr(workflow_tools, "_model_manager", lambda: reloaded_manager)
    load_response = asyncio.run(workflow_tools.load_model_from_file(str(model_path)))

    assert load_response["status"] == "success"
    model_info = load_response["data"]["model_info"]
    assert model_info["name"] == "Round Trip Metadata"
    assert model_info["documentation"] == "Documentation that must survive export."
    assert model_info["properties"] == {"owner": "EA"}


def test_export_tools_pass_strict_quality_gate_with_annotation_connectors(
    tmp_path,
    monkeypatch,
):
    manager = ArchimateModelManager()
    manager.create_new_model("Annotated Export Model")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    role = manager.add_archimate_element("Role", "BusinessRole")
    relationship = manager.add_archimate_relationship(
        actor.uuid,
        role.uuid,
        "Assignment",
    )
    view = manager.create_view("Annotated View")
    manager.add_node_to_view(view.uuid, actor.uuid)
    manager.add_node_to_view(view.uuid, role.uuid)
    manager.add_connection_to_view(view.uuid, relationship.uuid)
    note = view.add(
        ref=None,
        x=40,
        y=300,
        w=180,
        h=80,
        node_type="Label",
        label="Reminder",
    )
    view.connect_note(note, next(iter(view.nodes)))
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)

    content_response = asyncio.run(
        model_tools.export_model_content(quality_gate="strict"),
    )
    file_response = asyncio.run(
        model_tools.export_model_to_file(
            str(tmp_path / "notes.archimate"),
            quality_gate="strict",
        ),
    )

    # A regression surfaces here as ModelOperationError /
    # "Export quality gate failed: visual_validation".
    assert "error" not in content_response
    assert content_response["status"] == "success"
    assert file_response["status"] == "success"

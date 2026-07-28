import pytest

from pyarchimate_mcp_server.exceptions import InvalidRelationshipCombinationError
from pyarchimate_mcp_server.model_manager import ArchimateModelManager


def test_relationship_compatibility_uses_backend_matrix():
    manager = ArchimateModelManager()

    result = manager.get_relationship_compatibility(
        "ApplicationService",
        "BusinessProcess",
    )

    assert result["archimate_version"] == "3.2-compatible"
    assert "pyArchimate" in result["backend"]
    assert "Serving" in {
        relationship["type"] for relationship in result["valid_relationships"]
    }


def test_recommend_relationship_filters_by_intent_and_attributes():
    manager = ArchimateModelManager()

    result = manager.recommend_relationship(
        source_type="BusinessProcess",
        target_type="BusinessObject",
        intent="writes_data",
    )

    recommendations = result["recommendations"]
    assert recommendations[0]["type"] == "Access"
    assert recommendations[0]["attributes"]["access_type"] == "Write"


def test_strict_relationship_creation_rejects_invalid_combination():
    manager = ArchimateModelManager()
    manager.create_new_model("Strict Relationship Test")
    source = manager.add_archimate_element("Search Parking", "BusinessProcess")
    target = manager.add_archimate_element("Search Service", "ApplicationService")

    with pytest.raises(InvalidRelationshipCombinationError) as exc_info:
        manager.add_archimate_relationship(
            source.uuid,
            target.uuid,
            "Access",
            semantic_validation="strict",
            access_type="Read",
        )

    details = exc_info.value.details
    assert details["code"] == "INVALID_RELATIONSHIP_COMBINATION"
    assert details["source_type"] == "BusinessProcess"
    assert details["target_type"] == "ApplicationService"
    assert details["suggested_repairs"][0]["new_type"] == "Serving"


def test_warn_and_off_relationship_creation_preserve_backwards_compatibility():
    manager = ArchimateModelManager()
    manager.create_new_model("Warn Relationship Test")
    source = manager.add_archimate_element("Search Parking", "BusinessProcess")
    target = manager.add_archimate_element("Search Service", "ApplicationService")

    off_relationship = manager.add_archimate_relationship(
        source.uuid,
        target.uuid,
        "Access",
        access_type="Read",
    )
    warn_relationship = manager.add_archimate_relationship(
        source.uuid,
        target.uuid,
        "Access",
        access_type="Read",
        semantic_validation="warn",
    )

    assert off_relationship.type == "Access"
    assert warn_relationship.type == "Access"


def test_strict_batch_relationship_creation_rolls_back():
    manager = ArchimateModelManager()
    manager.create_new_model("Strict Batch Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor", element_id="actor")
    role = manager.add_archimate_element("Role", "BusinessRole", element_id="role")
    process = manager.add_archimate_element(
        "Search Parking",
        "BusinessProcess",
        element_id="process",
    )
    service = manager.add_archimate_element(
        "Search Service",
        "ApplicationService",
        element_id="service",
    )

    with pytest.raises(InvalidRelationshipCombinationError):
        manager.add_archimate_relationships(
            [
                {
                    "source": actor.uuid,
                    "target": role.uuid,
                    "type": "Assignment",
                    "semantic_validation": "strict",
                },
                {
                    "source": process.uuid,
                    "target": service.uuid,
                    "type": "Access",
                    "access_type": "Read",
                    "semantic_validation": "strict",
                },
            ],
            rollback_on_error=True,
        )

    assert manager.list_relationships() == []


def test_warn_mode_surfaces_semantic_warning_in_tool_response(monkeypatch):
    import asyncio

    from pyarchimate_mcp_server.tools import relationship_tools

    manager = ArchimateModelManager()
    monkeypatch.setattr(relationship_tools, "_model_manager", lambda: manager)
    manager.create_new_model("Warn Surface Test")
    node = manager.add_archimate_element("Server", "Node")
    component = manager.add_archimate_element("Platform", "ApplicationComponent")

    response = asyncio.run(
        relationship_tools.add_relationship(
            relationship_type="Assignment",
            source_id=node.uuid,
            target_id=component.uuid,
        ),
    )

    # Default mode is now "warn": creation succeeds but the response
    # carries the semantic warning with valid alternatives.
    assert response["status"] == "success"
    warning = response["data"]["semantic_warning"]
    assert warning["code"] == "INVALID_RELATIONSHIP_COMBINATION"
    assert "semantic warning" in response["message"]


def test_node_assignment_hosting_repairs_to_serving():
    manager = ArchimateModelManager()
    manager.create_new_model("Hosting Repair Test")
    node = manager.add_archimate_element("Server", "Node")
    component = manager.add_archimate_element("Platform", "ApplicationComponent")
    manager.add_archimate_relationship(
        node.uuid,
        component.uuid,
        "Assignment",
    )

    def combination_issues():
        return [
            issue
            for issue in manager.validate_semantics()["issues"]
            if issue["code"] == "INVALID_RELATIONSHIP_COMBINATION"
        ]

    assert len(combination_issues()) == 1

    result = manager.repair_semantic_issues(repair_all_deterministic=True)

    assert result["applied_count"] == 1
    assert combination_issues() == []
    repaired = manager.list_relationships()[0]
    assert repaired.type == "Serving"
    assert repaired.source.uuid == node.uuid
    assert repaired.target.uuid == component.uuid

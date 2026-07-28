import json
from itertools import pairwise
from types import SimpleNamespace

import pytest
from lxml import etree

from pyarchimate_mcp_server import layout as layout_module
from pyarchimate_mcp_server.constants import (
    ARCHIMATE_ELEMENT_TYPES,
    ARCHIMATE_RELATIONSHIP_TYPES,
)
from pyarchimate_mcp_server.exceptions import (
    InvalidElementTypeError,
    ModelNotFoundError,
    ModelOperationError,
    ViewNotFoundError,
)
from pyarchimate_mcp_server.model_manager import (
    ARCHI_PLAIN_CONNECTION_TYPE,
    COVERAGE_VIEW_PROPERTY_KEY,
    COVERAGE_VIEW_PROPERTY_VALUE,
    GROUP_CONTAINMENT_RELATIONSHIP_LINE_COLOR,
    JUNCTION_NODE_SIZE,
    SECONDARY_DENSE_RELATIONSHIP_LINE_COLOR,
    ArchimateModelManager,
)


def _nodes_overlap(first, second):
    return not (
        first.x + first.w <= second.x
        or second.x + second.w <= first.x
        or first.y + first.h <= second.y
        or second.y + second.h <= first.y
    )


def test_create_new_model_returns_active_model_info():
    manager = ArchimateModelManager()

    model = manager.create_new_model("Test Model")
    model_info = manager.get_model_info()

    assert model.name == "Test Model"
    assert manager.get_active_model() is model
    assert model_info["name"] == "Test Model"
    assert model_info["id"] == model.uuid
    assert model_info["elements_count"] == 0
    assert model_info["relationships_count"] == 0
    assert model_info["views_count"] == 0
    assert model_info["is_loaded"] is True


def test_get_model_info_without_active_model_returns_empty_state():
    manager = ArchimateModelManager()

    model_info = manager.get_model_info()

    assert model_info == {
        "name": None,
        "id": None,
        "documentation": None,
        "properties": {},
        "elements_count": 0,
        "relationships_count": 0,
        "views_count": 0,
        "is_loaded": False,
    }


def test_create_new_model_accepts_documentation_and_properties():
    manager = ArchimateModelManager()

    manager.create_new_model(
        "Documented Model",
        description="Target architecture for the payments platform.",
        properties={"owner": "EA", "revision": 3},
    )
    model_info = manager.get_model_info()

    assert model_info["name"] == "Documented Model"
    assert (
        model_info["documentation"] == "Target architecture for the payments platform."
    )
    assert model_info["properties"] == {"owner": "EA", "revision": "3"}


def test_update_model_metadata_updates_only_supplied_fields_and_merges_properties():
    manager = ArchimateModelManager()
    manager.create_new_model(
        "Original Name",
        description="Original documentation.",
        properties={"owner": "EA"},
    )

    after_rename = manager.update_model_metadata(name="Renamed Model")

    assert after_rename["name"] == "Renamed Model"
    assert after_rename["documentation"] == "Original documentation."
    assert after_rename["properties"] == {"owner": "EA"}

    after_merge = manager.update_model_metadata(
        description="Revised documentation.",
        properties={"reviewer": "Architecture Board"},
    )

    assert after_merge["name"] == "Renamed Model"
    assert after_merge["documentation"] == "Revised documentation."
    assert after_merge["properties"] == {
        "owner": "EA",
        "reviewer": "Architecture Board",
    }


def test_update_model_metadata_without_active_model_raises_model_not_found():
    manager = ArchimateModelManager()

    with pytest.raises(ModelNotFoundError):
        manager.update_model_metadata(name="No Model")


def test_add_update_list_and_delete_element():
    manager = ArchimateModelManager()
    manager.create_new_model("Element Test")

    element = manager.add_archimate_element(
        name="Customer",
        element_type="BusinessActor",
        description="External customer",
        folder_path="/Business",
        properties={"owner": "EA"},
    )

    assert element.type == "BusinessActor"
    assert element.desc == "External customer"
    assert element.folder == "/Business"
    assert element.prop("owner") == "EA"
    assert manager.get_element_by_id(element.uuid) is element
    assert manager.list_elements({"type": "BusinessActor"}) == [element]
    assert manager.list_elements({"name_contains": "cust"}) == [element]
    assert manager.list_elements({"properties_contain": {"owner": "EA"}}) == [element]

    assert manager.update_element_properties(
        element.uuid,
        name="Retail Customer",
        description="Updated",
        properties={"status": "approved"},
        folder_path="/Business/Actors",
    )
    detail = manager.map_element_to_detail(element)
    assert detail.name == "Retail Customer"
    assert detail.description == "Updated"
    assert detail.properties == {"owner": "EA", "status": "approved"}
    assert detail.folder == "/Business/Actors"

    assert manager.delete_element(element.uuid) is True
    assert manager.get_element_by_id(element.uuid) is None
    assert manager.delete_element(element.uuid) is False


def test_add_element_rejects_invalid_type():
    manager = ArchimateModelManager()
    manager.create_new_model("Invalid Type Test")

    with pytest.raises(InvalidElementTypeError):
        manager.add_archimate_element("Bad", "BogusElementType")


def test_interaction_elements_are_supported_by_pyarchimate_121():
    manager = ArchimateModelManager()
    manager.create_new_model("Interaction Element Test")

    application_interaction = manager.add_archimate_element(
        "Channel Session",
        "ApplicationInteraction",
        description="Interaction between application components.",
    )
    business_interaction = manager.add_archimate_element(
        "Customer Service Interaction",
        "BusinessInteraction",
        description="Interaction between business roles.",
    )
    application_detail = manager.map_element_to_detail(application_interaction)
    business_detail = manager.map_element_to_detail(business_interaction)

    assert "ApplicationInteraction" in ARCHIMATE_ELEMENT_TYPES
    assert "BusinessInteraction" in ARCHIMATE_ELEMENT_TYPES
    assert application_detail.type == "ApplicationInteraction"
    assert (
        application_detail.description == "Interaction between application components."
    )
    assert business_detail.type == "BusinessInteraction"
    assert business_detail.description == "Interaction between business roles."


def test_relationship_crud_accepts_pyarchimate_relationship_type():
    manager = ArchimateModelManager()
    manager.create_new_model("Relationship Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    role = manager.add_archimate_element("Role", "BusinessRole")

    relationship = manager.add_archimate_relationship(
        source_id=actor.uuid,
        target_id=role.uuid,
        relationship_type="Assignment",
        name="plays",
        description="Actor plays role",
        properties={"criticality": "high"},
    )

    assert relationship.type == "Assignment"
    assert relationship.source is actor
    assert relationship.target is role
    assert relationship.prop("criticality") == "high"
    assert manager.list_relationships({"type": "Assignment"}) == [
        relationship,
    ]
    assert manager.list_relationships({"source_id": actor.uuid}) == [relationship]
    assert manager.get_outgoing_relationships(actor.uuid) == [relationship]
    assert manager.get_incoming_relationships(role.uuid) == [relationship]

    assert manager.update_relationship_properties(
        relationship.uuid,
        name="assigned to",
        description="Updated relationship",
        properties={"reviewed": "true"},
    )
    detail = manager.map_relationship_to_detail(relationship)
    assert detail.name == "assigned to"
    assert detail.type == "Assignment"
    assert detail.description == "Updated relationship"
    assert detail.properties == {"criticality": "high", "reviewed": "true"}
    assert detail.source_element_id == actor.uuid
    assert detail.target_element_id == role.uuid

    assert manager.delete_relationship(relationship.uuid) is True
    assert manager.get_relationship_by_id(relationship.uuid) is None
    assert manager.delete_relationship(relationship.uuid) is False


def test_influence_strength_and_relationship_documentation_round_trip():
    manager = ArchimateModelManager()
    manager.create_new_model("Influence Metadata Test")
    driver = manager.add_archimate_element("Market Pressure", "Driver")
    goal = manager.add_archimate_element("Improve CX", "Goal")

    relationship = manager.add_archimate_relationship(
        source_id=driver.uuid,
        target_id=goal.uuid,
        relationship_type="Influence",
        description="Influence documentation survives XML round trip.",
        influence_strength="++",
    )
    detail = manager.map_relationship_to_detail(relationship)

    assert detail.influence_strength == "++"
    assert detail.description == "Influence documentation survives XML round trip."

    content = manager.get_model_content_as_string()
    loaded = ArchimateModelManager()
    loaded.load_model_from_string(content)
    loaded_relationship = loaded.list_relationships()[0]

    assert loaded_relationship.influence_strength == "++"
    assert (
        loaded_relationship.desc == "Influence documentation survives XML round trip."
    )


def test_access_relationship_metadata_is_exposed():
    manager = ArchimateModelManager()
    manager.create_new_model("Access Metadata Test")
    process = manager.add_archimate_element("Process", "BusinessProcess")
    business_object = manager.add_archimate_element("Object", "BusinessObject")

    relationship = manager.add_archimate_relationship(
        source_id=process.uuid,
        target_id=business_object.uuid,
        relationship_type="Access",
        access_type="ReadWrite",
    )
    detail = manager.map_relationship_to_detail(relationship)

    assert detail.access_type == "ReadWrite"
    assert manager.update_relationship_properties(
        relationship.uuid,
        access_type="Read",
    )
    assert manager.map_relationship_to_detail(relationship).access_type == "Read"


def test_association_directed_metadata_is_exposed_and_exported_to_csv():
    manager = ArchimateModelManager()
    manager.create_new_model("Association Metadata Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    role = manager.add_archimate_element("Role", "BusinessRole")

    relationship = manager.add_archimate_relationship(
        source_id=actor.uuid,
        target_id=role.uuid,
        relationship_type="Association",
        is_directed=True,
    )

    assert manager.map_relationship_to_detail(relationship).is_directed is True
    relationships_csv = manager.export_relationships_to_csv()
    assert "is_directed" in relationships_csv
    assert "true" in relationships_csv


def test_view_node_connection_and_view_detail():
    manager = ArchimateModelManager()
    manager.create_new_model("View Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    role = manager.add_archimate_element("Role", "BusinessRole")
    relationship = manager.add_archimate_relationship(
        actor.uuid,
        role.uuid,
        "Assignment",
    )
    view = manager.create_view(
        "Context View",
        description="A stakeholder context view.",
        properties={
            "purpose": "Communicate context",
            "stakeholders": "Architect, Product Owner",
            "concerns": "Scope, Dependencies",
        },
    )

    source_node = manager.add_node_to_view(view.uuid, actor.uuid, 10, 20, 120, 55)
    target_node = manager.add_node_to_view(view.uuid, role.uuid, 180, 20, 120, 55)
    connection = manager.add_connection_to_view(view.uuid, relationship.uuid)
    detail = manager.map_view_to_detail(view)

    assert manager.get_view_by_id(view.uuid) is view
    assert source_node.ref == actor.uuid
    assert target_node.ref == role.uuid
    assert connection.ref == relationship.uuid
    assert detail.name == "Context View"
    assert detail.description == "A stakeholder context view."
    assert detail.metadata["purpose"] == "Communicate context"
    assert detail.metadata["stakeholders"] == ["Architect", "Product Owner"]
    assert [node.element_id for node in detail.nodes] == [actor.uuid, role.uuid]
    assert detail.connections[0].relationship_id == relationship.uuid
    assert manager.delete_view(view.uuid) is True
    assert manager.get_view_by_id(view.uuid) is None


def test_add_node_to_view_avoids_overlap_for_reused_coordinates():
    manager = ArchimateModelManager()
    manager.create_new_model("Auto Placement Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    role = manager.add_archimate_element("Role", "BusinessRole")
    process = manager.add_archimate_element("Process", "BusinessProcess")
    view = manager.create_view("Crowded View")

    first_node = manager.add_node_to_view(view.uuid, actor.uuid, 0, 0)
    second_node = manager.add_node_to_view(view.uuid, role.uuid, 0, 0)
    third_node = manager.add_node_to_view(view.uuid, process.uuid)

    assert not _nodes_overlap(first_node, second_node)
    assert not _nodes_overlap(first_node, third_node)
    assert not _nodes_overlap(second_node, third_node)


def test_auto_layout_view_layered_by_type_separates_archimate_layers():
    manager = ArchimateModelManager()
    manager.create_new_model("Layered By Type Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    app = manager.add_archimate_element("App", "ApplicationComponent")
    tech_node = manager.add_archimate_element("Runtime", "Node")
    view = manager.create_view("Layered View")

    actor_node = manager.add_node_to_view(view.uuid, actor.uuid, 0, 0)
    app_node = manager.add_node_to_view(view.uuid, app.uuid, 0, 0)
    tech_node_view = manager.add_node_to_view(view.uuid, tech_node.uuid, 0, 0)

    detail = manager.auto_layout_view(view.uuid)

    assert actor_node.y < app_node.y < tech_node_view.y
    assert {node.element_id for node in detail.nodes if node.element_id} == {
        actor.uuid,
        app.uuid,
        tech_node.uuid,
    }
    assert not _nodes_overlap(actor_node, app_node)
    assert not _nodes_overlap(app_node, tech_node_view)


def test_auto_layout_nests_grouping_members_and_resizes_group():
    manager = ArchimateModelManager()
    manager.create_new_model("Grouping Layout Test")
    initial_group_width = 180
    initial_group_height = 70
    group = manager.add_archimate_element("Security Controls", "Grouping")
    requirement = manager.add_archimate_element("PCI DSS", "Requirement")
    component = manager.add_archimate_element("Fraud Service", "ApplicationComponent")
    manager.add_archimate_relationship(group.uuid, requirement.uuid, "Aggregation")
    manager.add_archimate_relationship(group.uuid, component.uuid, "Aggregation")
    view = manager.create_view("Grouped View")

    group_node = manager.add_node_to_view(
        view.uuid,
        group.uuid,
        width=initial_group_width,
        height=initial_group_height,
    )
    requirement_node = manager.add_node_to_view(view.uuid, requirement.uuid)
    component_node = manager.add_node_to_view(view.uuid, component.uuid)
    manager.connect_visible_relationships(view.uuid)

    detail = manager.auto_layout_view(view.uuid)
    child_node_details = [
        node for node in detail.nodes if node.parent_node_id == group_node.uuid
    ]

    assert requirement_node.parent is group_node
    assert component_node.parent is group_node
    assert {node.element_id for node in child_node_details} == {
        requirement.uuid,
        component.uuid,
    }
    assert group_node.w > initial_group_width
    assert group_node.h > initial_group_height
    assert group_node.x < requirement_node.x < group_node.x + group_node.w
    assert group_node.y < requirement_node.y < group_node.y + group_node.h
    assert all(not connection.show_label for connection in view.conns)
    assert all(
        connection.line_color == GROUP_CONTAINMENT_RELATIONSHIP_LINE_COLOR
        for connection in view.conns
    )


def test_auto_layout_nests_group_members_exactly_once():
    manager = ArchimateModelManager()
    manager.create_new_model("Authored Group Layout Test")
    group = manager.add_archimate_element("Payment Controls", "Grouping")
    control = manager.add_archimate_element("Tokenization Control", "Requirement")
    fillers = [
        manager.add_archimate_element(f"Filler {index}", "BusinessProcess")
        for index in range(4)
    ]
    manager.add_archimate_relationship(group.uuid, control.uuid, "Aggregation")
    view = manager.create_view("Authored View")

    group_node = manager.add_node_to_view(view.uuid, group.uuid, x=40, y=40)
    manager.add_node_to_view(view.uuid, control.uuid, x=360, y=40)
    for index, filler in enumerate(fillers):
        manager.add_node_to_view(
            view.uuid,
            filler.uuid,
            x=40 + (index * 220),
            y=220,
        )
    manager.connect_visible_relationships(view.uuid)

    detail = manager.auto_layout_view(view.uuid)

    control_node_details = [
        node for node in detail.nodes if node.element_id == control.uuid
    ]
    # The member is MOVED into its group: exactly one node, nested.
    assert len(control_node_details) == 1
    assert control_node_details[0].parent_node_id == group_node.uuid
    # No element appears twice anywhere in the view.
    element_ids = [node.element_id for node in detail.nodes if node.element_id]
    assert len(element_ids) == len(set(element_ids))


def test_auto_layout_lanes_do_not_overlap_grown_groups():
    manager = ArchimateModelManager()
    manager.create_new_model("Group Overlap Test")
    group = manager.add_archimate_element("Payment Domain", "Grouping")
    members = [
        manager.add_archimate_element(f"Service {index}", "ApplicationService")
        for index in range(3)
    ]
    tech_node = manager.add_archimate_element("Cluster", "Node")
    for member in members:
        manager.add_archimate_relationship(group.uuid, member.uuid, "Composition")
    view = manager.create_view("Overlap View")
    for element in [group, *members, tech_node]:
        manager.add_node_to_view(view.uuid, element.uuid)
    manager.connect_visible_relationships(view.uuid)

    manager.auto_layout_view(view.uuid)

    top_level = list(view.nodes)
    for first_index, first in enumerate(top_level):
        for second in top_level[first_index + 1 :]:
            assert not _nodes_overlap(first, second), (
                f"{first.concept.name} overlaps {second.concept.name}"
            )


def test_auto_layout_view_layered_uses_relationship_direction():
    manager = ArchimateModelManager()
    manager.create_new_model("Relationship Layout Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    role = manager.add_archimate_element("Role", "BusinessRole")
    manager.add_archimate_relationship(actor.uuid, role.uuid, "Assignment")
    view = manager.create_view("Relationship View")

    actor_node = manager.add_node_to_view(view.uuid, actor.uuid)
    role_node = manager.add_node_to_view(view.uuid, role.uuid)

    manager.auto_layout_view(view.uuid, strategy="layered")

    assert actor_node.x < role_node.x
    assert not _nodes_overlap(actor_node, role_node)


def _polyline(connection):
    return [
        (float(connection.source.cx), float(connection.source.cy)),
        *[
            (float(point.x), float(point.y))
            for point in connection.get_all_bendpoints()
        ],
        (float(connection.target.cx), float(connection.target.cy)),
    ]


def _is_orthogonal(points):
    return all(
        abs(first[0] - second[0]) < 1 or abs(first[1] - second[1]) < 1
        for first, second in pairwise(points)
    )


def _segment_crosses_rect(first, second, rect):
    x_min = min(first[0], second[0])
    y_min = min(first[1], second[1])
    x_max = max(first[0], second[0])
    y_max = max(first[1], second[1])
    rect_x, rect_y, rect_w, rect_h = rect
    return not (
        x_max < rect_x
        or x_min > rect_x + rect_w
        or y_max < rect_y
        or y_min > rect_y + rect_h
    )


def test_auto_layout_routes_connections_around_intermediate_nodes():
    manager = ArchimateModelManager()
    manager.create_new_model("Routing Test")
    elements = [
        manager.add_archimate_element(name, "BusinessProcess")
        for name in ["Source", "Middle", "Target", "Filler A", "Filler B"]
    ]
    view = manager.create_view("Routing View")
    nodes = [manager.add_node_to_view(view.uuid, element.uuid) for element in elements]
    relationship = manager.add_archimate_relationship(
        elements[0].uuid,
        elements[2].uuid,
        "Flow",
        name="source to target path label",
    )
    connection = manager.add_connection_to_view(view.uuid, relationship.uuid)

    manager.auto_layout_view(view.uuid, strategy="grid")

    points = _polyline(connection)
    assert list(connection.get_all_bendpoints()), "route should bend around Middle"
    assert _is_orthogonal(points)
    middle = nodes[1]
    middle_rect = (middle.x, middle.y, middle.w, middle.h)
    assert not any(
        _segment_crosses_rect(first, second, middle_rect)
        for first, second in pairwise(points)
    )


def test_auto_layout_routed_connections_are_orthogonal():
    manager = ArchimateModelManager()
    manager.create_new_model("Orthogonal Routing Test")
    source = manager.add_archimate_element("Source", "BusinessProcess")
    target = manager.add_archimate_element("Target", "ApplicationService")
    blocker = manager.add_archimate_element("Blocker", "BusinessProcess")
    view = manager.create_view("Orthogonal View")
    manager.add_node_to_view(view.uuid, source.uuid)
    manager.add_node_to_view(view.uuid, blocker.uuid)
    manager.add_node_to_view(view.uuid, target.uuid)
    relationship = manager.add_archimate_relationship(
        source.uuid,
        target.uuid,
        "Serving",
    )
    connection = manager.add_connection_to_view(view.uuid, relationship.uuid)

    manager.auto_layout_view(view.uuid)

    assert _is_orthogonal(_polyline(connection))


_AXIS_EPSILON = 0.5


def _segments(polylines):
    return [
        (index, first, second)
        for index, points in enumerate(polylines)
        for first, second in pairwise(points)
    ]


def _spans_overlap(first_start, first_end, second_start, second_end):
    return min(first_start, first_end) < max(second_start, second_end) and min(
        second_start,
        second_end,
    ) < max(first_start, first_end)


def _collinear_overlaps(polylines):
    """Pairs of segments from different connections drawn on top of each other."""
    overlaps = []
    segments = _segments(polylines)
    for position, (index, first_a, second_a) in enumerate(segments):
        for other_index, first_b, second_b in segments[position + 1 :]:
            if index == other_index:
                continue
            horizontal = (
                abs(first_a[1] - second_a[1]) < _AXIS_EPSILON
                and abs(first_b[1] - second_b[1]) < _AXIS_EPSILON
                and abs(first_a[1] - first_b[1]) < _AXIS_EPSILON
                and _spans_overlap(first_a[0], second_a[0], first_b[0], second_b[0])
            )
            vertical = (
                abs(first_a[0] - second_a[0]) < _AXIS_EPSILON
                and abs(first_b[0] - second_b[0]) < _AXIS_EPSILON
                and abs(first_a[0] - first_b[0]) < _AXIS_EPSILON
                and _spans_overlap(first_a[1], second_a[1], first_b[1], second_b[1])
            )
            if horizontal:
                overlaps.append(
                    min(second_a[0], second_b[0]) - max(first_a[0], first_b[0]),
                )
            elif vertical:
                overlaps.append(
                    min(second_a[1], second_b[1]) - max(first_a[1], first_b[1]),
                )
    return overlaps


def _overlap_span_total(polylines):
    return sum(abs(length) for length in _collinear_overlaps(polylines))


def _non_orthogonal_count(polylines):
    return sum(
        1
        for _index, first, second in _segments(polylines)
        if abs(first[0] - second[0]) >= 1 and abs(first[1] - second[1]) >= 1
    )


def _node_interior_crossings(view, polylines):
    rectangles = [
        (node.x + 2, node.y + 2, node.x + node.w - 2, node.y + node.h - 2)
        for node in layout_module.view_nodes_recursive(view)
        if getattr(node, "cat", "Element") == "Element"
    ]
    crossings = 0
    for _index, first, second in _segments(polylines):
        for left, top, right, bottom in rectangles:
            horizontal = (
                abs(first[1] - second[1]) < _AXIS_EPSILON
                and top < first[1] < bottom
                and _spans_overlap(first[0], second[0], left, right)
            )
            vertical = (
                abs(first[0] - second[0]) < _AXIS_EPSILON
                and left < first[0] < right
                and _spans_overlap(first[1], second[1], top, bottom)
            )
            if horizontal or vertical:
                crossings += 1
    return crossings


def _bendpoint_polylines(view):
    return [
        [(float(point.x), float(point.y)) for point in connection.get_all_bendpoints()]
        for connection in sorted(view.conns, key=lambda conn: conn.uuid)
    ]


def _drawn_polylines(view):
    return [
        _polyline(connection)
        for connection in sorted(view.conns, key=lambda conn: conn.uuid)
    ]


def _build_shared_corridor_model(stacks=6):
    """Three-layer model whose routes crowd into the same horizontal corridors.

    Sized to stay on the routed side of the dense-view gate (28 connections
    over 27 nodes is under both thresholds), because the collinear-separation
    pass only runs where connections get bendpoints at all.
    """
    manager = ArchimateModelManager()
    manager.create_new_model("Corridor Model")
    view = manager.create_view("Corridor View")
    processes, components, nodes = [], [], []
    for index in range(stacks):
        process = manager.add_archimate_element(f"Process {index}", "BusinessProcess")
        service = manager.add_archimate_element(
            f"App Service {index}",
            "ApplicationService",
        )
        component = manager.add_archimate_element(
            f"Component {index}",
            "ApplicationComponent",
        )
        node = manager.add_archimate_element(f"Node {index}", "Node")
        processes.append(process)
        components.append(component)
        nodes.append(node)
        manager.add_archimate_relationship(service.uuid, process.uuid, "Serving")
        manager.add_archimate_relationship(component.uuid, service.uuid, "Realization")
        manager.add_archimate_relationship(node.uuid, component.uuid, "Serving")
        for element in (process, service, component, node):
            manager.add_node_to_view(view.uuid, element.uuid)
    for index in range(stacks - 1):
        manager.add_archimate_relationship(
            processes[index].uuid,
            processes[index + 1].uuid,
            "Triggering",
        )
        manager.add_archimate_relationship(
            nodes[index].uuid,
            components[index + 1].uuid,
            "Serving",
        )
    for relationship in manager.list_relationships():
        manager.add_connection_to_view(view.uuid, relationship.uuid)
    return manager, view


def test_auto_layout_separates_connections_sharing_a_corridor(monkeypatch):
    manager, view = _build_shared_corridor_model()
    manager.auto_layout_view(view.uuid)
    assert not layout_module.should_simplify_connection_routing(view), (
        "fixture must be routed, otherwise the separation pass never runs"
    )

    separated = _bendpoint_polylines(view)
    separated_drawn = _drawn_polylines(view)
    separated_crossings = _node_interior_crossings(view, separated)

    # Re-route the exact same geometry with the separation pass disabled, so
    # before and after differ only by that pass.
    monkeypatch.setattr(
        layout_module,
        "separate_collinear_connection_segments",
        lambda routed, *_args: [list(path) for _connection, path in routed],
    )
    layout_module.route_or_simplify_connections(view)
    plain = _bendpoint_polylines(view)

    assert len(_collinear_overlaps(plain)) >= 10, (  # noqa: PLR2004
        "fixture must actually crowd its corridors"
    )
    # Benefit: connections stop being drawn on top of each other.
    assert len(_collinear_overlaps(separated)) * 2 <= len(_collinear_overlaps(plain))
    assert _overlap_span_total(separated) < _overlap_span_total(plain)
    # No regression: same routes, same orthogonality, same node clearance.
    assert [len(path) for path in separated] == [len(path) for path in plain]
    assert _non_orthogonal_count(separated_drawn) == _non_orthogonal_count(
        _drawn_polylines(view),
    )
    assert separated_crossings <= _node_interior_crossings(view, plain)


def _fake_node(x, y, width=160, height=80):
    return SimpleNamespace(x=x, y=y, w=width, h=height)


def _fake_connection(source, target):
    return SimpleNamespace(source=source, target=target)


def _obstacle_map(rectangles, resolution=10.0):
    return layout_module.ObstacleMap(
        rectangles,
        resolution=resolution,
        config=layout_module.RoutingConfig(),
    )


def _points(pairs):
    return [layout_module.Point(float(x), float(y)) for x, y in pairs]


def _coordinates(path):
    return [(point.x, point.y) for point in path]


def test_collinear_separation_reverts_a_displacement_that_enters_a_node():
    # Two horizontal segments share the corridor at y=300. Spreading them
    # pushes one down into a node whose interior starts at y=303.
    blocker = layout_module.Rectangle(200.0, 301.0, 160.0, 80.0)
    first = _points([(100, 400), (100, 300), (500, 300), (500, 400)])
    second = _points([(150, 200), (150, 300), (450, 300), (450, 200)])
    routed = [
        (_fake_connection(_fake_node(20, 360), _fake_node(420, 360)), first),
        (_fake_connection(_fake_node(70, 160), _fake_node(370, 160)), second),
    ]

    unguarded = layout_module.displace_collinear_segments(
        [list(first), list(second)],
        layout_module.COLLINEAR_SEPARATION_GAP,
    )
    assert any(
        layout_module.segment_enters_rectangle(path[1], path[2], blocker)
        for path in unguarded
    ), "without a guard the helper pushes a segment into the node"

    separated = layout_module.separate_collinear_connection_segments(
        routed,
        _obstacle_map([blocker]),
        layout_module.RoutingConfig(),
        [blocker],
    )

    assert not any(
        layout_module.segment_enters_rectangle(path[index], path[index + 1], blocker)
        for path in separated
        for index in range(len(path) - 1)
    )
    # Only the offending displacement is reverted; the other one survives.
    assert _coordinates(separated[1]) == _coordinates(second)
    assert _coordinates(separated[0]) != _coordinates(first)


def test_collinear_separation_keeps_node_anchors_on_their_centerlines():
    source = _fake_node(100, 100)  # centre (180, 140)
    anchor_path = _points([(305, 140), (700, 140), (700, 300)])
    interior_path = _points([(400, 60), (400, 140), (900, 140), (900, 60)])
    routed = [
        (_fake_connection(source, _fake_node(620, 260)), anchor_path),
        (_fake_connection(_fake_node(320, 20), _fake_node(820, 20)), interior_path),
    ]

    unguarded = layout_module.displace_collinear_segments(
        [list(anchor_path), list(interior_path)],
        layout_module.COLLINEAR_SEPARATION_GAP,
    )
    assert unguarded[0][0].y != anchor_path[0].y, (
        "without a guard the helper slides the anchor off the node centerline"
    )

    separated = layout_module.separate_collinear_connection_segments(
        routed,
        _obstacle_map([]),
        layout_module.RoutingConfig(),
        [],
    )

    assert _coordinates(separated[0]) == _coordinates(anchor_path)
    assert separated[0][0].y == source.y + (source.h / 2)
    assert _coordinates(separated[1]) != _coordinates(interior_path)


def test_anchor_displacement_is_allowed_only_along_the_stub_axis():
    node = _fake_node(100, 100)  # centre (180, 140)
    below = layout_module.Point(180.0, 225.0)  # exits the bottom edge
    clearance = float(layout_module.RoutingConfig().node_clearance)

    assert layout_module.anchor_displacement_allowed(node, below, "h", 20.0, clearance)
    assert not layout_module.anchor_displacement_allowed(
        node,
        below,
        "v",
        20.0,
        clearance,
    ), "a sideways shift takes the anchor off the centerline"
    # The anchor sits 45px below the edge, so it may come back 20px (leaving
    # exactly the 25px clearance) but not 30px.
    assert layout_module.anchor_displacement_allowed(node, below, "h", -20.0, clearance)
    assert not layout_module.anchor_displacement_allowed(
        node,
        below,
        "h",
        -30.0,
        clearance,
    ), "a shift back toward the node breaks its clearance"


def test_collinear_separation_leaves_untangled_routes_untouched():
    first = _points([(100, 100), (100, 200), (300, 200)])
    second = _points([(600, 600), (600, 800), (900, 800)])
    routed = [
        (_fake_connection(_fake_node(20, 60), _fake_node(220, 160)), first),
        (_fake_connection(_fake_node(520, 560), _fake_node(820, 760)), second),
    ]

    separated = layout_module.separate_collinear_connection_segments(
        routed,
        _obstacle_map([]),
        layout_module.RoutingConfig(),
        [],
    )

    assert [_coordinates(path) for path in separated] == [
        _coordinates(first),
        _coordinates(second),
    ]
    assert (
        layout_module.separate_collinear_connection_segments(
            [],
            _obstacle_map([]),
            layout_module.RoutingConfig(),
            [],
        )
        == []
    )


def test_auto_layout_simplifies_dense_view_relationship_routes():
    manager = ArchimateModelManager()
    manager.create_new_model("Dense Routing Test")
    elements = [
        manager.add_archimate_element(f"Step {index}", "BusinessProcess")
        for index in range(12)
    ]
    view = manager.create_view("Dense View")
    for index, element in enumerate(elements):
        manager.add_node_to_view(
            view.uuid,
            element.uuid,
            x=40 + ((index % 6) * 200),
            y=40 + ((index // 6) * 120),
        )

    expected_relationship_count = len(elements) * 3
    for source_index, source in enumerate(elements):
        for offset in range(1, 4):
            target = elements[(source_index + offset) % len(elements)]
            relationship = manager.add_archimate_relationship(
                source.uuid,
                target.uuid,
                "Flow",
                name=f"flow {source_index}-{offset}",
            )
            manager.add_connection_to_view(view.uuid, relationship.uuid)

    manager.auto_layout_view(view.uuid)

    assert len(view.conns) == expected_relationship_count
    assert all(not list(connection.get_all_bendpoints()) for connection in view.conns)


def test_auto_layout_reflows_compact_dense_existing_layout_into_lanes():
    manager = ArchimateModelManager()
    manager.create_new_model("Compact Dense Layout Test")
    element_specs = [
        ("Customer", "BusinessActor"),
        ("Browse", "BusinessProcess"),
        ("Purchase Service", "BusinessService"),
        ("Order", "BusinessObject"),
        ("Storefront", "ApplicationComponent"),
        ("Checkout API", "ApplicationService"),
        ("Order Data", "DataObject"),
        ("Runtime", "Node"),
        ("Hosting", "TechnologyService"),
        ("Container", "Artifact"),
        ("Go Live", "ImplementationEvent"),
        ("Target Plateau", "Plateau"),
    ]
    elements = [
        manager.add_archimate_element(name, element_type)
        for name, element_type in element_specs
    ]
    view = manager.create_view("Compact Dense View")
    nodes = [
        manager.add_node_to_view(
            view.uuid,
            element.uuid,
            x=40 + ((index % 6) * 190),
            y=40 + ((index // 6) * 110),
        )
        for index, element in enumerate(elements)
    ]
    original_y_span = max(node.y + node.h for node in nodes) - min(
        node.y for node in nodes
    )

    expected_relationship_count = len(elements) * 3
    relationship_count = 0
    for source_index, source in enumerate(elements):
        for offset in range(1, 4):
            target = elements[(source_index + offset) % len(elements)]
            relationship = manager.add_archimate_relationship(
                source.uuid,
                target.uuid,
                "Association",
                name=f"related {source_index}-{offset}",
            )
            manager.add_connection_to_view(view.uuid, relationship.uuid)
            relationship_count += 1

    manager.auto_layout_view(view.uuid)
    updated_y_span = max(node.y + node.h for node in nodes) - min(
        node.y for node in nodes
    )

    assert relationship_count == expected_relationship_count
    assert updated_y_span > original_y_span
    assert all(not list(connection.get_all_bendpoints()) for connection in view.conns)
    assert all(not connection.show_label for connection in view.conns)
    assert all(
        connection.line_color == SECONDARY_DENSE_RELATIONSHIP_LINE_COLOR
        for connection in view.conns
    )


def test_auto_layout_layered_by_type_prioritizes_visible_flow_order():
    manager = ArchimateModelManager()
    manager.create_new_model("Flow Order Test")
    browse = manager.add_archimate_element("Browse Products", "BusinessProcess")
    cart = manager.add_archimate_element("Manage Cart", "BusinessProcess")
    checkout = manager.add_archimate_element("Checkout", "BusinessProcess")
    view = manager.create_view("Flow Order View")

    checkout_node = manager.add_node_to_view(view.uuid, checkout.uuid, x=40, y=40)
    cart_node = manager.add_node_to_view(view.uuid, cart.uuid, x=260, y=40)
    browse_node = manager.add_node_to_view(view.uuid, browse.uuid, x=480, y=40)
    for source, target in [(browse, cart), (cart, checkout)]:
        relationship = manager.add_archimate_relationship(
            source.uuid,
            target.uuid,
            "Triggering",
            name="triggers",
        )
        manager.add_connection_to_view(view.uuid, relationship.uuid)

    manager.auto_layout_view(view.uuid)

    assert browse_node.x < cart_node.x < checkout_node.x


def test_auto_layout_aligns_data_below_accessing_behavior():
    manager = ArchimateModelManager()
    manager.create_new_model("Data Alignment Test")
    browse = manager.add_archimate_element("Browse", "BusinessProcess")
    checkout = manager.add_archimate_element("Checkout", "BusinessProcess")
    order = manager.add_archimate_element("Order", "BusinessObject")
    view = manager.create_view("Data Alignment View")

    order_node = manager.add_node_to_view(view.uuid, order.uuid, x=40, y=40)
    checkout_node = manager.add_node_to_view(view.uuid, checkout.uuid, x=260, y=40)
    browse_node = manager.add_node_to_view(view.uuid, browse.uuid, x=480, y=40)
    triggering = manager.add_archimate_relationship(
        browse.uuid,
        checkout.uuid,
        "Triggering",
    )
    access = manager.add_archimate_relationship(
        checkout.uuid,
        order.uuid,
        "Access",
        access_type="ReadWrite",
    )
    manager.add_connection_to_view(view.uuid, triggering.uuid)
    manager.add_connection_to_view(view.uuid, access.uuid)

    manager.auto_layout_view(view.uuid)

    assert browse_node.x < checkout_node.x
    assert order_node.x == checkout_node.x
    assert checkout_node.y < order_node.y


def test_auto_layout_uses_compact_junction_size():
    manager = ArchimateModelManager()
    manager.create_new_model("Junction Size Test")
    source = manager.add_archimate_element("Source", "BusinessProcess")
    junction = manager.add_archimate_element("Approval Split", "AndJunction")
    target = manager.add_archimate_element("Target", "BusinessProcess")
    view = manager.create_view("Junction View")

    manager.add_node_to_view(view.uuid, source.uuid)
    junction_node = manager.add_node_to_view(view.uuid, junction.uuid)
    manager.add_node_to_view(view.uuid, target.uuid)

    manager.auto_layout_view(view.uuid, strategy="grid")

    assert junction_node.w == JUNCTION_NODE_SIZE
    assert junction_node.h == JUNCTION_NODE_SIZE


def test_model_export_can_auto_layout_views_before_serialization():
    manager = ArchimateModelManager()
    manager.create_new_model("Export Layout Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    role = manager.add_archimate_element("Role", "BusinessRole")
    manager.add_archimate_relationship(actor.uuid, role.uuid, "Assignment")
    view = manager.create_view("Export Layout View")

    actor_node = manager.add_node_to_view(view.uuid, actor.uuid, 0, 0)
    role_node = manager.add_node_to_view(view.uuid, role.uuid, 300, 300)
    role_node.x = actor_node.x
    role_node.y = actor_node.y

    content = manager.get_model_content_as_string(
        "archi",
        auto_layout=True,
        layout_strategy="layered",
    )

    assert content.startswith("<archimate:model")
    assert actor_node.x < role_node.x
    assert not _nodes_overlap(actor_node, role_node)


def test_export_normalizes_folder_paths_and_writes_file(tmp_path):
    manager = ArchimateModelManager()
    manager.create_new_model("Folder Export Test")
    business_actor = manager.add_archimate_element(
        "Customer",
        "BusinessActor",
        folder_path="business",
    )
    manager.add_archimate_element(
        "Roadmap",
        "WorkPackage",
        folder_path="Implementation/Plans",
    )

    first_content = manager.get_model_content_as_string("archi")
    second_content = manager.get_model_content_as_string("archi")
    export_path = tmp_path / "folder-export.archimate"
    result = manager.export_model_to_file(str(export_path), output_format="archi")

    assert business_actor.folder == "/Business"
    assert first_content == second_content
    assert result["path"] == str(export_path)
    assert result["bytes_written"] == len(export_path.read_bytes())
    assert f'id="{manager.get_active_model().uuid}"' in first_content
    assert 'name="Implementation &amp; Migration"' in first_content


def test_export_reports_invalid_folder_path_with_element_context():
    manager = ArchimateModelManager()
    manager.create_new_model("Invalid Folder Export Test")
    element = manager.add_archimate_element("Customer", "BusinessActor")
    element.folder = "/Application"

    with pytest.raises(ModelOperationError) as exc_info:
        manager.get_model_content_as_string("archi")

    message = str(exc_info.value)
    assert "Customer" in message
    assert element.uuid in message
    assert 'expected "/Business" or empty' in message


def test_native_archi_export_handles_plain_junction_without_mutating_model():
    manager = ArchimateModelManager()
    manager.create_new_model("Junction Export Test")
    junction = manager.add_archimate_element("Decision", "Junction")
    junction.junction_type = None

    content = manager.get_model_content_as_string("archi")

    # pyArchimate >=1.11 writes Archi's canonical junction form:
    # xsi:type="archimate:Junction" with a type="and" attribute.
    assert 'xsi:type="archimate:Junction"' in content
    assert 'type="and"' in content
    assert junction.type == "Junction"
    assert junction.junction_type is None


def test_native_archi_export_uses_archi_influence_strength_attribute():
    manager = ArchimateModelManager()
    manager.create_new_model("Influence Native Export Test")
    driver = manager.add_archimate_element("Market Pressure", "Driver")
    goal = manager.add_archimate_element("Improve CX", "Goal")
    manager.add_archimate_relationship(
        source_id=driver.uuid,
        target_id=goal.uuid,
        relationship_type="Influence",
        influence_strength="++",
    )

    content = manager.get_model_content_as_string("archi")
    loaded = ArchimateModelManager()
    loaded.load_model_from_string(content, "archi")

    assert 'strength="++"' in content
    assert "influenceStrength" not in content
    assert loaded.list_relationships()[0].influence_strength == "++"


def test_batch_elements_roll_back_when_one_item_fails():
    manager = ArchimateModelManager()
    manager.create_new_model("Rollback Batch Test")

    with pytest.raises(InvalidElementTypeError):
        manager.add_archimate_elements(
            [
                {"name": "Valid", "element_type": "BusinessActor"},
                {"name": "Invalid", "element_type": "BogusElementType"},
            ],
            rollback_on_error=True,
        )

    assert manager.list_elements() == []


def test_create_model_from_spec_builds_view_and_connects_visible_relationships():
    manager = ArchimateModelManager()
    result = manager.create_model_from_spec(
        {
            "name": "Spec Model",
            "elements": [
                {
                    "id": "id-source-process",
                    "name": "Visit Site",
                    "type": "BusinessProcess",
                    "folder_path": "business",
                },
                {
                    "id": "id-target-process",
                    "name": "Purchase Products",
                    "type": "BusinessProcess",
                    "folder_path": "/Business",
                },
            ],
            "relationships": [
                {
                    "id": "id-flow",
                    "type": "Flow",
                    "source": "id-source-process",
                    "target": "id-target-process",
                    "name": "leads to",
                },
            ],
            "views": [
                {
                    "id": "id-main-view",
                    "name": "Main View",
                    "nodes": [
                        {"element": "id-source-process"},
                        {"element": "id-target-process"},
                    ],
                    "connect_visible_relationships": True,
                    "auto_layout": True,
                    "layout_strategy": "layered",
                },
            ],
        },
    )

    view = manager.get_view_by_id("id-main-view")
    assert result["model_info"]["name"] == "Spec Model"
    assert result["element_ids_by_ref"]["id-source-process"] == "id-source-process"
    assert view is not None
    assert {node.ref for node in view.nodes} == {
        "id-source-process",
        "id-target-process",
    }
    assert len(view.conns) == 1
    assert view.conns[0].ref == "id-flow"


def test_create_model_from_spec_applies_model_level_documentation_and_properties():
    manager = ArchimateModelManager()

    result = manager.create_model_from_spec(
        {
            "name": "Documented Spec Model",
            "description": "Baseline architecture assembled from a spec.",
            "properties": {"owner": "EA", "revision": 2},
        },
    )

    assert result["model_info"]["name"] == "Documented Spec Model"
    assert (
        result["model_info"]["documentation"]
        == "Baseline architecture assembled from a spec."
    )
    assert result["model_info"]["properties"] == {"owner": "EA", "revision": "2"}


def test_create_model_from_spec_accepts_documentation_alias_for_description():
    manager = ArchimateModelManager()

    manager.create_model_from_spec(
        {
            "name": "Alias Spec Model",
            "documentation": "Documented through the read-side field name.",
        },
    )

    assert (
        manager.get_model_info()["documentation"]
        == "Documented through the read-side field name."
    )


def test_ensure_all_relationships_in_views_creates_coverage_view():
    manager = ArchimateModelManager()
    manager.create_new_model("Relationship Coverage Test")
    expected_added_nodes = 2
    expected_added_connections = 1
    source = manager.add_archimate_element("Source Service", "ApplicationService")
    target = manager.add_archimate_element("Target Process", "BusinessProcess")
    relationship = manager.add_archimate_relationship(
        source.uuid,
        target.uuid,
        "Serving",
    )
    source_view = manager.create_view("Source Only")
    manager.add_node_to_view(source_view.uuid, source.uuid)

    result = manager.ensure_all_relationships_in_views()

    coverage_view = manager.get_view_by_id(result["coverage_view_id"])
    used_relationship_ids = {
        connection.ref
        for view in manager.get_active_model().views
        for connection in view.conns
    }
    assert coverage_view is not None
    assert (
        coverage_view.prop(COVERAGE_VIEW_PROPERTY_KEY) == COVERAGE_VIEW_PROPERTY_VALUE
    )
    assert coverage_view.prop("is_quality_assurance_view") == "true"
    assert coverage_view.prop("is_stakeholder_facing") == "false"
    assert relationship.uuid in used_relationship_ids
    assert result["remaining_unused_relationships_count"] == 0
    assert result["added_nodes_count"] == expected_added_nodes
    assert result["added_connections_count"] == expected_added_connections


def test_coverage_layout_leaves_notes_and_their_rows_alone():
    """A note line is not a relationship pair, so it must not claim a row.

    `ensure_all_relationships_in_views` never runs `auto_layout_view`, so
    there is no note save/restore around its layout. Enumerating a note
    connector as a pair would hard-assign the note into the source column,
    drag the element it annotates into the target column, and push every
    genuine relationship row down one 140px slot.
    """
    manager = ArchimateModelManager()
    manager.create_new_model("Coverage Note Test")
    first = manager.add_archimate_element("First", "ApplicationComponent")
    second = manager.add_archimate_element("Second", "ApplicationComponent")
    third = manager.add_archimate_element("Third", "ApplicationComponent")
    manager.add_archimate_relationship(first.uuid, second.uuid, "Serving")
    manager.add_archimate_relationship(first.uuid, third.uuid, "Serving")

    first_pass = manager.ensure_all_relationships_in_views()
    coverage_view = manager.get_view_by_id(first_pass["coverage_view_id"])
    annotated_node = next(node for node in coverage_view.nodes if node.ref)
    note_result = manager.add_note_to_view(
        coverage_view.uuid,
        "Reviewed 2026-07",
        x=1200,
        y=40,
        connect_to_node_ids=[annotated_node.uuid],
    )
    note = _view_node_by_id(coverage_view, note_result["node_id"])

    # A second pass with one more relationship re-runs the coverage layout.
    manager.add_archimate_relationship(second.uuid, third.uuid, "Serving")
    manager.ensure_all_relationships_in_views()

    assert (note.x, note.y) == (1200, 40)
    # Three relationships occupy exactly three 140px rows from the top
    # margin down. A note line claiming a row would add a fourth and
    # shift the first pair off y=40.
    expected_row_count = 3
    assert sorted(
        {node.y for node in coverage_view.nodes if node.ref},
    ) == [40 + (140 * row) for row in range(expected_row_count)]


def test_ensure_all_relationships_prefers_coverage_for_visible_unused_relationship():
    manager = ArchimateModelManager()
    manager.create_new_model("Coverage Policy Test")
    source = manager.add_archimate_element("Source Service", "ApplicationService")
    target = manager.add_archimate_element("Target Process", "BusinessProcess")
    relationship = manager.add_archimate_relationship(
        source.uuid,
        target.uuid,
        "Serving",
    )
    readable_view = manager.create_view("Readable View")
    manager.add_node_to_view(readable_view.uuid, source.uuid)
    manager.add_node_to_view(readable_view.uuid, target.uuid)

    result = manager.ensure_all_relationships_in_views()
    coverage_view = manager.get_view_by_id(result["coverage_view_id"])

    assert coverage_view is not None
    assert not readable_view.conns
    assert relationship.uuid in {connection.ref for connection in coverage_view.conns}
    assert result["remaining_unused_relationships_count"] == 0


def test_ensure_all_relationships_moves_group_containment_to_coverage():
    manager = ArchimateModelManager()
    manager.create_new_model("Group Containment Coverage Test")
    group = manager.add_archimate_element("Purchase Domain", "Grouping")
    service = manager.add_archimate_element("Checkout Service", "ApplicationService")
    relationship = manager.add_archimate_relationship(
        group.uuid,
        service.uuid,
        "Aggregation",
    )
    view = manager.create_view("Readable View")
    group_node = manager.add_node_to_view(view.uuid, group.uuid)
    service_node = manager.add_node_to_view(view.uuid, service.uuid)
    manager.add_connection_to_view(view.uuid, relationship.uuid)

    manager.auto_layout_view(view.uuid)
    assert service_node.parent is group_node
    assert view.conns

    result = manager.ensure_all_relationships_in_views()
    coverage_view = manager.get_view_by_id(result["coverage_view_id"])

    assert coverage_view is not None
    assert result["relocated_connections_count"] == 1
    assert result["relocated_relationship_ids"] == [relationship.uuid]
    assert relationship.uuid not in {connection.ref for connection in view.conns}
    assert relationship.uuid in {connection.ref for connection in coverage_view.conns}
    assert result["remaining_unused_relationships_count"] == 0


def test_custom_coverage_view_name_is_not_relocated_from_itself():
    manager = ArchimateModelManager()
    manager.create_new_model("Custom Coverage Name Test")
    group = manager.add_archimate_element("Purchase Domain", "Grouping")
    service = manager.add_archimate_element("Checkout Service", "ApplicationService")
    relationship = manager.add_archimate_relationship(
        group.uuid,
        service.uuid,
        "Aggregation",
    )
    coverage_view = manager.create_view("Validation Links")
    manager.add_node_to_view(coverage_view.uuid, group.uuid)
    manager.add_node_to_view(coverage_view.uuid, service.uuid)
    connection = manager.add_connection_to_view(coverage_view.uuid, relationship.uuid)
    manager.auto_layout_view(coverage_view.uuid)

    result = manager.ensure_all_relationships_in_views(
        coverage_view_name="Validation Links",
    )

    assert result["coverage_view_id"] is None
    assert result["relocated_connections_count"] == 0
    assert connection.uuid in {
        view_connection.uuid for view_connection in coverage_view.conns
    }
    assert relationship.uuid in {
        view_connection.ref for view_connection in coverage_view.conns
    }
    assert result["remaining_unused_relationships_count"] == 0


def test_view_named_like_coverage_is_not_the_generated_coverage_view():
    """The word "coverage" in a view name means nothing on its own.

    Recognition is by marker property or by an exact match against the
    caller's `coverage_view_name`. This test fails if the old
    `"coverage" in name.lower()` substring fallback is reintroduced.
    """
    manager = ArchimateModelManager()
    manager.create_new_model("Coverage Naming Test")
    authored = manager.create_view("Data Coverage Analysis")
    payments = manager.create_view("Coverage of Payments")
    default_name = manager.create_view("Relationship Coverage")
    marked = manager.create_view("Traceability Matrix")
    marked.prop(COVERAGE_VIEW_PROPERTY_KEY, COVERAGE_VIEW_PROPERTY_VALUE)

    assert layout_module.is_coverage_view(authored) is False
    assert layout_module.is_coverage_view(payments) is False
    # Not even the default name counts without the marker or the request.
    assert layout_module.is_coverage_view(default_name) is False
    # The marker is name-independent...
    assert layout_module.is_coverage_view(marked) is True
    # ...and an exact request still adopts a pre-existing view.
    assert (
        layout_module.is_coverage_view(
            authored,
            coverage_view_name="Data Coverage Analysis",
        )
        is True
    )
    assert (
        layout_module.is_coverage_view(
            payments,
            coverage_view_name="Data Coverage Analysis",
        )
        is False
    )


def test_authored_view_named_like_coverage_still_gets_layer_bands():
    manager = ArchimateModelManager()
    manager.create_new_model("Coverage Naming Bands Test")
    process = manager.add_archimate_element("Checkout", "BusinessProcess")
    component = manager.add_archimate_element("Portal", "ApplicationComponent")
    manager.add_archimate_relationship(component.uuid, process.uuid, "Serving")
    view = manager.create_view("Data Coverage Analysis")
    manager.add_node_to_view(view.uuid, process.uuid)
    manager.add_node_to_view(view.uuid, component.uuid)
    manager.connect_visible_relationships(view.uuid)

    manager.auto_layout_view(view.uuid)

    bands = [node for node in view.nodes if getattr(node, "cat", None) == "Container"]
    assert sorted(band.label for band in bands) == ["Application", "Business"]


def test_authored_view_named_like_coverage_still_relocates_containment():
    manager = ArchimateModelManager()
    manager.create_new_model("Coverage Naming Relocation Test")
    group = manager.add_archimate_element("Purchase Domain", "Grouping")
    service = manager.add_archimate_element("Checkout Service", "ApplicationService")
    relationship = manager.add_archimate_relationship(
        group.uuid,
        service.uuid,
        "Aggregation",
    )
    view = manager.create_view("Coverage of Payments")
    manager.add_node_to_view(view.uuid, group.uuid)
    manager.add_node_to_view(view.uuid, service.uuid)
    manager.add_connection_to_view(view.uuid, relationship.uuid)
    manager.auto_layout_view(view.uuid)

    result = manager.ensure_all_relationships_in_views()
    coverage_view = manager.get_view_by_id(result["coverage_view_id"])

    assert coverage_view is not None
    assert coverage_view.uuid != view.uuid
    assert result["relocated_connections_count"] == 1
    assert result["relocated_relationship_ids"] == [relationship.uuid]
    assert relationship.uuid not in {connection.ref for connection in view.conns}
    assert relationship.uuid in {connection.ref for connection in coverage_view.conns}


def test_coverage_view_is_recognised_after_export_and_reload_by_its_marker():
    manager = ArchimateModelManager()
    manager.create_new_model("Coverage Marker Round Trip")
    source = manager.add_archimate_element("Source Service", "ApplicationService")
    target = manager.add_archimate_element("Target Process", "BusinessProcess")
    manager.add_archimate_relationship(source.uuid, target.uuid, "Serving")

    result = manager.ensure_all_relationships_in_views(
        coverage_view_name="Traceability Matrix",
    )
    assert result["coverage_view_id"] is not None

    reloaded = ArchimateModelManager()
    reloaded.load_model_from_string(
        manager.get_model_content_as_string("archi"),
        "archi",
    )
    view = next(
        candidate
        for candidate in reloaded.get_active_model().views
        if candidate.name == "Traceability Matrix"
    )

    assert "coverage" not in view.name.lower()
    # No coverage_view_name is passed: recognition rides on the marker.
    assert layout_module.is_coverage_view(view) is True


def test_existing_view_with_requested_coverage_name_is_adopted_not_duplicated():
    manager = ArchimateModelManager()
    manager.create_new_model("Coverage Adoption Test")
    source = manager.add_archimate_element("Source Service", "ApplicationService")
    target = manager.add_archimate_element("Target Process", "BusinessProcess")
    relationship = manager.add_archimate_relationship(
        source.uuid,
        target.uuid,
        "Serving",
    )
    existing = manager.create_view("Relationship Coverage")

    result = manager.ensure_all_relationships_in_views()

    view_names = [view.name for view in manager.get_active_model().views]
    assert result["coverage_view_id"] == existing.uuid
    assert view_names.count("Relationship Coverage") == 1
    assert existing.prop(COVERAGE_VIEW_PROPERTY_KEY) == COVERAGE_VIEW_PROPERTY_VALUE
    assert relationship.uuid in {connection.ref for connection in existing.conns}


def test_supported_types_include_archimate_categories():
    manager = ArchimateModelManager()
    supported_types = manager.list_supported_types()

    assert supported_types["summary"]["element_type_count"] == len(
        ARCHIMATE_ELEMENT_TYPES,
    )
    assert supported_types["summary"]["relationship_type_count"] == len(
        ARCHIMATE_RELATIONSHIP_TYPES,
    )
    assert (
        "BusinessInteraction"
        in supported_types["element_types_by_category"]["Business"]
    )
    assert "Access" in supported_types["relationship_types"]
    assert supported_types["layout_engines"] == ["internal", "pyarchimate"]
    assert supported_types["layout_strategies"] == [
        "grid",
        "layered",
        "layered_by_type",
    ]


def test_model_export_rejects_invalid_auto_layout_strategy_without_views():
    manager = ArchimateModelManager()
    manager.create_new_model("Invalid Export Layout Test")

    with pytest.raises(ModelOperationError):
        manager.get_model_content_as_string(
            auto_layout=True,
            layout_strategy="unsupported",
        )


def test_auto_layout_view_accepts_internal_layout_engine():
    manager = ArchimateModelManager()
    manager.create_new_model("Internal Layout Engine Test")
    expected_nodes_count = 2
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    role = manager.add_archimate_element("Role", "BusinessRole")
    view = manager.create_view("Layout View")
    manager.add_node_to_view(view.uuid, actor.uuid)
    manager.add_node_to_view(view.uuid, role.uuid)

    detail = manager.auto_layout_view(view.uuid, layout_engine="internal")

    assert len(detail.nodes) == expected_nodes_count


def test_auto_layout_view_rejects_unknown_layout_engine():
    manager = ArchimateModelManager()
    manager.create_new_model("Unknown Layout Engine Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    view = manager.create_view("Layout View")
    manager.add_node_to_view(view.uuid, actor.uuid)

    with pytest.raises(ModelOperationError, match="Unsupported layout engine"):
        manager.auto_layout_view(view.uuid, layout_engine="unknown")


def test_graphviz_layout_engine_is_no_longer_supported():
    manager = ArchimateModelManager()
    manager.create_new_model("Graphviz Removed Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    view = manager.create_view("Layout View")
    manager.add_node_to_view(view.uuid, actor.uuid)

    with pytest.raises(ModelOperationError, match="Unsupported layout engine"):
        manager.auto_layout_view(view.uuid, layout_engine="graphviz")


def _all_view_nodes(container):
    """Yield every visual node in a view or node, nested members included."""
    for node in container.nodes:
        yield node
        yield from _all_view_nodes(node)


def _node_geometry(view):
    return [
        (node.uuid, node.x, node.y, node.w, node.h) for node in _all_view_nodes(view)
    ]


def _overlapping_node_pairs(view):
    """Return sibling node pairs whose rectangles intersect.

    Ancestor/descendant pairs are excluded: a Grouping is *meant* to
    contain its members.
    """
    nodes = list(_all_view_nodes(view))
    return [
        (first.uuid, second.uuid)
        for index, first in enumerate(nodes)
        for second in nodes[index + 1 :]
        if not layout_module.is_ancestor(first, second)
        and not layout_module.is_ancestor(second, first)
        and _nodes_overlap(first, second)
    ]


def _build_flat_pyarchimate_fixture(manager):
    """Flat view of default-sized nodes: suitable for the upstream engine."""
    actor = manager.add_archimate_element("Customer", "BusinessActor")
    process = manager.add_archimate_element("Handle Payment", "BusinessProcess")
    component = manager.add_archimate_element("Payment Engine", "ApplicationComponent")
    host = manager.add_archimate_element("Cluster", "Node")
    manager.add_archimate_relationship(actor.uuid, process.uuid, "Triggering")
    manager.add_archimate_relationship(component.uuid, process.uuid, "Serving")
    manager.add_archimate_relationship(host.uuid, component.uuid, "Serving")
    view = manager.create_view("Payment Overview")
    for element in (actor, process, component, host):
        manager.add_node_to_view(view.uuid, element.uuid)
    manager.connect_visible_relationships(view.uuid)
    return view


def test_default_and_explicit_internal_layout_engines_produce_identical_geometry():
    """The backward-compatibility guarantee, asserted on real coordinates."""
    default_manager = _build_rich_fixture_model()
    explicit_manager = _build_rich_fixture_model()

    default_manager.auto_layout_view(default_manager.list_views()[0].uuid)
    explicit_manager.auto_layout_view(
        explicit_manager.list_views()[0].uuid,
        layout_engine="internal",
    )

    default_view = default_manager.list_views()[0]
    explicit_view = explicit_manager.list_views()[0]
    # Node uuids are random per model, so compare geometry positionally.
    default_boxes = [box[1:] for box in _node_geometry(default_view)]
    explicit_boxes = [box[1:] for box in _node_geometry(explicit_view)]
    assert default_boxes == explicit_boxes
    assert default_boxes, "fixture must actually place nodes"
    default_bends = [
        [(point.x, point.y) for point in connection.bendpoints]
        for connection in default_view.conns
    ]
    explicit_bends = [
        [(point.x, point.y) for point in connection.bendpoints]
        for connection in explicit_view.conns
    ]
    assert default_bends == explicit_bends


def test_pyarchimate_layout_engine_places_nodes_without_overlap():
    """Golden overlap test: upstream placement has no collision detection."""
    manager = ArchimateModelManager()
    manager.create_new_model("Upstream Engine Test")
    view = _build_flat_pyarchimate_fixture(manager)
    expected_nodes = 4

    detail = manager.auto_layout_view(view.uuid, layout_engine="pyarchimate")

    assert len(detail.nodes) == expected_nodes
    assert _overlapping_node_pairs(view) == []
    # A different placement from the internal engine, not a silent no-op.
    internal_manager = ArchimateModelManager()
    internal_manager.create_new_model("Internal Engine Test")
    internal_view = _build_flat_pyarchimate_fixture(internal_manager)
    internal_manager.auto_layout_view(internal_view.uuid)
    assert [box[1:3] for box in _node_geometry(view)] != [
        box[1:3] for box in _node_geometry(internal_view)
    ]


def test_pyarchimate_layout_engine_is_case_insensitive_and_deterministic():
    manager = ArchimateModelManager()
    manager.create_new_model("Upstream Case Test")
    view = _build_flat_pyarchimate_fixture(manager)

    manager.auto_layout_view(view.uuid, layout_engine="PyArchimate")
    first_pass = _node_geometry(view)
    manager.auto_layout_view(view.uuid, layout_engine="pyarchimate")

    assert _node_geometry(view) == first_pass


def test_pyarchimate_layout_engine_still_routes_connections():
    """Routing is outside the engine branch and must run for both engines."""
    manager = ArchimateModelManager()
    manager.create_new_model("Upstream Routing Test")
    view = _build_flat_pyarchimate_fixture(manager)

    manager.auto_layout_view(view.uuid, layout_engine="pyarchimate")

    bendpoints = sum(len(connection.bendpoints) for connection in view.conns)
    assert bendpoints > 0, "MCP routing must still bend connections"


def test_pyarchimate_layout_engine_refuses_views_with_oversized_nodes():
    """The guard is the feature: upstream would overlap these silently."""
    manager = ArchimateModelManager()
    manager.create_new_model("Upstream Guard Test")
    wide = manager.add_archimate_element("Customer Relationship Mgmt", "Node")
    narrow = manager.add_archimate_element("Ledger", "ApplicationComponent")
    view = manager.create_view("Wide View")
    manager.add_node_to_view(view.uuid, wide.uuid, x=10, y=10, width=300, height=90)
    manager.add_node_to_view(view.uuid, narrow.uuid, x=400, y=10)
    geometry_before = _node_geometry(view)

    with pytest.raises(ModelOperationError) as excinfo:
        manager.auto_layout_view(view.uuid, layout_engine="pyarchimate")

    details = excinfo.value.details
    # Read from upstream, never hardcoded: an upstream default change
    # must retune the guard instead of silently invalidating it.
    assert details["grid_size"] == int(layout_module.pyarchimate_grid_size())
    assert [node["element_name"] for node in details["oversized_nodes"]] == [
        "Customer Relationship Mgmt",
    ]
    assert details["remedy"] == "internal"
    # Refused before any placement write: the view is left untouched.
    assert _node_geometry(view) == geometry_before
    # And the same view still lays out with the default engine.
    manager.auto_layout_view(view.uuid)
    assert _node_geometry(view) != geometry_before


def test_pyarchimate_guard_measures_the_whole_subtree_not_just_the_parent():
    """An Archi-imported child can stick out past its parent's rectangle."""
    manager = ArchimateModelManager()
    manager.create_new_model("Upstream Subtree Guard Test")
    group = manager.add_archimate_element("Domain", "Grouping")
    member = manager.add_archimate_element("Service", "ApplicationService")
    view = manager.create_view("Protruding View")
    group_node = manager.add_node_to_view(
        view.uuid,
        group.uuid,
        x=0,
        y=0,
        width=200,
        height=200,
    )
    # Child protrudes far past the parent box; the parent alone would pass.
    group_node.add(
        ref=manager.get_element_by_id(member.uuid),
        x=100,
        y=100,
        w=400,
        h=80,
    )

    with pytest.raises(ModelOperationError, match="exceed the upstream"):
        manager.auto_layout_view(view.uuid, layout_engine="pyarchimate")


def test_pyarchimate_layout_engine_never_adds_layer_bands():
    manager = ArchimateModelManager()
    manager.create_new_model("Upstream Band Test")
    view = _make_two_layer_view(manager)
    # Bands exist first, so this also pins that they are REMOVED.
    manager.auto_layout_view(view.uuid)
    assert [node for node in view.nodes if getattr(node, "cat", None) == "Container"]

    manager.auto_layout_view(view.uuid, layout_engine="pyarchimate")

    assert not [
        node for node in view.nodes if getattr(node, "cat", None) == "Container"
    ]
    assert not view.prop("mcp:layer_bands")


def test_group_nesting_is_identical_under_both_layout_engines():
    """ARC-017 regression: nesting and duplicate healing are engine-agnostic."""

    def build(manager):
        manager.create_new_model("Group Engine Parity Test")
        group = manager.add_archimate_element("Domain", "Grouping")
        service = manager.add_archimate_element("Service", "ApplicationService")
        manager.add_archimate_relationship(group.uuid, service.uuid, "Composition")
        view = manager.create_view("Group View")
        group_node = manager.add_node_to_view(view.uuid, group.uuid, x=40, y=300)
        # Legacy duplicate: a stray top-level copy plus a nested copy.
        manager.add_node_to_view(view.uuid, service.uuid, x=600, y=40)
        group_node.add(
            ref=manager.get_element_by_id(service.uuid),
            x=80,
            y=350,
            w=160,
            h=80,
        )
        return view

    internal_manager = ArchimateModelManager()
    internal_view = build(internal_manager)
    upstream_manager = ArchimateModelManager()
    upstream_view = build(upstream_manager)

    internal_manager.auto_layout_view(internal_view.uuid)
    upstream_manager.auto_layout_view(upstream_view.uuid, layout_engine="pyarchimate")

    for view in (internal_view, upstream_view):
        group_nodes = [
            node
            for node in _all_view_nodes(view)
            if getattr(node.concept, "type", None) == "Grouping"
        ]
        assert len(group_nodes) == 1
        assert len(group_nodes[0].nodes) == 1
        element_refs = [node.ref for node in _all_view_nodes(view)]
        assert len(element_refs) == len(set(element_refs)), "duplicate element nodes"


def test_auto_layout_all_views_accepts_the_pyarchimate_engine():
    manager = ArchimateModelManager()
    manager.create_new_model("Upstream All Views Test")
    first = _build_flat_pyarchimate_fixture(manager)
    second = manager.create_view("Second View")
    solo = manager.add_archimate_element("Standalone", "BusinessActor")
    manager.add_node_to_view(second.uuid, solo.uuid)
    expected_views = 2

    details = manager.auto_layout_all_views(layout_engine="pyarchimate")

    assert len(details) == expected_views
    for view in (first, second):
        assert _overlapping_node_pairs(view) == []


def test_create_model_from_spec_forwards_the_per_view_layout_engine():
    manager = ArchimateModelManager()

    result = manager.create_model_from_spec(
        {
            "name": "Spec Engine Test",
            "elements": [
                {"ref": "actor", "name": "Customer", "type": "BusinessActor"},
                {"ref": "proc", "name": "Checkout", "type": "BusinessProcess"},
            ],
            "relationships": [
                {"source": "actor", "target": "proc", "type": "Triggering"},
            ],
            "views": [
                {
                    "ref": "overview",
                    "name": "Spec View",
                    "auto_layout": True,
                    "layout_engine": "pyarchimate",
                    "nodes": [{"element": "actor"}, {"element": "proc"}],
                },
            ],
        },
    )

    view = manager.get_view_by_id(result["view_ids_by_ref"]["overview"])
    assert _overlapping_node_pairs(view) == []
    # Upstream places on its own coarse grid, starting at margin 20.
    assert sorted((node.x, node.y) for node in view.nodes) == [(20, 20), (260, 20)]


def test_create_model_from_spec_rejects_an_unknown_per_view_layout_engine():
    manager = ArchimateModelManager()

    with pytest.raises(ModelOperationError, match="Unsupported layout engine"):
        manager.create_model_from_spec(
            {
                "name": "Spec Bad Engine Test",
                "elements": [
                    {"ref": "actor", "name": "Customer", "type": "BusinessActor"},
                ],
                "views": [
                    {
                        "ref": "overview",
                        "name": "Spec View",
                        "auto_layout": True,
                        "layout_engine": "pyarchmate",
                        "nodes": [{"element": "actor"}],
                    },
                ],
            },
        )


def test_layout_engine_errors_carry_did_you_mean_suggestions():
    manager = ArchimateModelManager()
    manager.create_new_model("Suggestion Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    view = manager.create_view("Layout View")
    manager.add_node_to_view(view.uuid, actor.uuid)

    with pytest.raises(ModelOperationError) as excinfo:
        manager.auto_layout_view(view.uuid, layout_engine="pyarchmate")
    assert excinfo.value.details["suggestions"] == ["pyarchimate"]

    with pytest.raises(ModelOperationError) as excinfo:
        manager.auto_layout_view(view.uuid, strategy="layerd_by_type")
    assert excinfo.value.details["suggestions"] == ["layered_by_type", "layered"]

    # No close match still emits the key, so the caller can rely on it.
    with pytest.raises(ModelOperationError) as excinfo:
        manager.auto_layout_view(view.uuid, layout_engine="graphviz")
    assert excinfo.value.details == {"suggestions": []}


def test_export_rejects_invalid_layout_values_even_without_auto_layout(tmp_path):
    """A mistyped engine must never be silently swallowed and echoed as null."""
    manager = ArchimateModelManager()
    manager.create_new_model("Silent Ignore Test")

    with pytest.raises(ModelOperationError, match="Unsupported layout engine"):
        manager.get_model_content_as_string(auto_layout=False, layout_engine="nonsense")
    with pytest.raises(ModelOperationError, match="Unsupported layout strategy"):
        manager.get_model_content_as_string(
            auto_layout=False,
            layout_strategy="nonsense",
        )
    with pytest.raises(ModelOperationError, match="Unsupported layout engine"):
        manager.export_model_to_file(
            str(tmp_path / "model.archimate"),
            auto_layout=False,
            layout_engine="nonsense",
        )
    assert not (tmp_path / "model.archimate").exists()
    with pytest.raises(ModelOperationError, match="Unsupported layout engine"):
        manager.ensure_all_relationships_in_views(
            auto_layout=False,
            layout_engine="nonsense",
        )


def test_coverage_views_reject_a_non_internal_layout_engine():
    """The coverage layout is a fixed pair grid; it cannot honour an engine."""
    manager = ArchimateModelManager()
    manager.create_new_model("Coverage Engine Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    role = manager.add_archimate_element("Role", "BusinessRole")
    manager.add_archimate_relationship(actor.uuid, role.uuid, "Assignment")

    with pytest.raises(ModelOperationError, match="cannot be used for coverage views"):
        manager.ensure_all_relationships_in_views(layout_engine="pyarchimate")

    result = manager.ensure_all_relationships_in_views()
    assert result["added_connections_count"] == 1


def test_validate_model_returns_pyarchimate_reference_check_results():
    manager = ArchimateModelManager()
    manager.create_new_model("Validation Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    role = manager.add_archimate_element("Role", "BusinessRole")
    relationship = manager.add_archimate_relationship(
        actor.uuid,
        role.uuid,
        "Assignment",
    )
    view = manager.create_view("Validation View")
    manager.add_node_to_view(view.uuid, actor.uuid)
    manager.add_node_to_view(view.uuid, role.uuid)
    manager.add_connection_to_view(view.uuid, relationship.uuid)

    assert manager.validate_model() == {
        "is_valid": True,
        "invalid_connection_ids": [],
        "invalid_node_ids": [],
        "invalid_connections_count": 0,
        "invalid_nodes_count": 0,
    }


def _build_model_with_note_connector():
    """Valid model plus one diagram-only note connector.

    The model has no semantic issues and no orphan elements, so a strict
    quality gate can only ever fail on `visual_validation`.
    """
    manager = ArchimateModelManager()
    manager.create_new_model("Annotation Connector Fixture")
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
    connector = view.connect_note(note, next(iter(view.nodes)))
    return manager, view, note, connector


def test_validate_model_exempts_note_connector_and_keeps_response_shape():
    manager, _view, _note, connector = _build_model_with_note_connector()

    # Pin the scenario: an annotation connector has no backing Relationship
    # and one Label-cat (Archi Note) endpoint.
    assert connector.concept is None
    assert layout_module.connection_relationship_type(connector) is None
    assert connector.source.cat == "Label"
    assert manager._is_annotation_connector(connector) is True  # noqa: SLF001

    assert manager.validate_model() == {
        "is_valid": True,
        "invalid_connection_ids": [],
        "invalid_node_ids": [],
        "invalid_connections_count": 0,
        "invalid_nodes_count": 0,
    }
    assert manager.build_quality_report()["visual_validation"]["is_valid"] is True


def test_validate_model_still_reports_dangling_connector_between_element_nodes():
    manager, view, _note, connector = _build_model_with_note_connector()
    dangling = next(c for c in view.conns if c.uuid != connector.uuid)
    # The public ref setter refuses unknown ids, so simulate the corrupt state.
    dangling._ref = "id-relationship-that-no-longer-exists"  # noqa: SLF001

    assert dangling.source.cat == "Element"
    assert dangling.target.cat == "Element"
    assert manager._is_annotation_connector(dangling) is False  # noqa: SLF001

    validation = manager.validate_model()

    # Exactly one id: the note connector is exempt, the genuinely dangling
    # element-to-element connector is not.
    assert validation["invalid_connection_ids"] == [dangling.uuid]
    assert validation["invalid_connections_count"] == 1
    assert validation["is_valid"] is False


def test_validate_model_still_reports_connector_from_a_container_endpoint():
    """A Container (Archi Group) endpoint must NOT earn the exemption.

    `_is_annotation_connector` documents that only a `Label` endpoint is
    exempt, and ARC-033 puts diagram-only Groups out of scope. Without
    this test, widening the predicate to accept `Container` — which would
    also silently exempt every layer band — passes the whole suite.
    """
    manager, view, _note, connector = _build_model_with_note_connector()
    band = view.add(
        ref=None,
        x=400,
        y=300,
        w=200,
        h=120,
        node_type="Container",
        label="Business",
    )
    group_line = view.connect_note(band, next(iter(view.nodes)))

    assert group_line.source.cat == "Container"
    assert layout_module.connection_relationship_type(group_line) is None
    assert manager._is_annotation_connector(group_line) is False  # noqa: SLF001

    validation = manager.validate_model()

    # The note connector is exempt; the Container-anchored line is not.
    assert validation["invalid_connection_ids"] == [group_line.uuid]
    assert connector.uuid not in validation["invalid_connection_ids"]
    assert validation["is_valid"] is False


def test_validate_model_still_reports_note_connector_with_vanished_endpoint():
    manager, _view, _note, connector = _build_model_with_note_connector()
    # The public setter refuses unknown ids, so simulate the corrupt state.
    connector._target = "id-node-that-no-longer-exists"  # noqa: SLF001

    assert connector.source.cat == "Label"
    assert connector.target is None
    # A Label endpoint does not excuse a vanished one: this is a real defect.
    assert manager._is_annotation_connector(connector) is False  # noqa: SLF001

    validation = manager.validate_model()

    assert validation["invalid_connection_ids"] == [connector.uuid]
    assert validation["is_valid"] is False


def test_strict_quality_gate_export_succeeds_with_annotation_connectors(tmp_path):
    manager, _view, _note, _connector = _build_model_with_note_connector()

    content = manager.get_model_content_as_string(quality_gate="strict")
    assert content.startswith("<model")

    result = manager.export_model_to_file(
        str(tmp_path / "notes.archimate"),
        quality_gate="strict",
        include_quality_report=True,
    )

    assert result["quality_report"]["visual_validation"]["is_valid"] is True


EXCHANGE_MODEL_WITH_NOTE_CONNECTOR = """<?xml version="1.0" encoding="UTF-8"?>
<model xmlns="http://www.opengroup.org/xsd/archimate/3.0/"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       identifier="id-exchange-note-model">
  <name>Exchange Note Model</name>
  <elements>
    <element identifier="id-actor" xsi:type="BusinessActor"><name>Actor</name></element>
    <element identifier="id-role" xsi:type="BusinessRole"><name>Role</name></element>
  </elements>
  <relationships>
    <relationship identifier="id-assignment" source="id-actor" target="id-role"
                  xsi:type="Assignment"/>
  </relationships>
  <organizations>
    <item><label>Business</label>
      <item identifierRef="id-actor"/><item identifierRef="id-role"/>
    </item>
  </organizations>
  <views>
    <diagrams>
      <view identifier="id-view" xsi:type="Diagram">
        <name>Note View</name>
        <node identifier="id-node-actor" elementRef="id-actor" xsi:type="Element"
              x="40" y="40" w="160" h="80"/>
        <node identifier="id-node-role" elementRef="id-role" xsi:type="Element"
              x="280" y="40" w="160" h="80"/>
        <node identifier="id-node-note" xsi:type="Label"
              x="40" y="300" w="180" h="80"><label>Reminder</label></node>
        <connection identifier="id-conn-assignment" relationshipRef="id-assignment"
                    xsi:type="Relationship" source="id-node-actor"
                    target="id-node-role"/>
        <connection identifier="id-conn-note" relationshipRef="id-note-line"
                    xsi:type="Relationship" source="id-node-note"
                    target="id-node-actor"/>
      </view>
    </diagrams>
  </views>
</model>
"""


def test_exchange_import_with_note_connector_validates_clean():
    """Open Exchange keeps note connector lines, so the exemption must hold.

    This is the import path that actually reaches the false positive: this
    server's own `archimate` export writes a note line as
    `connection relationshipRef="<synthetic id>"`, and pyArchimate's exchange
    reader accepts it because `relationshipRef` is non-empty.
    """
    manager = ArchimateModelManager()
    manager.load_model_from_string(
        EXCHANGE_MODEL_WITH_NOTE_CONNECTOR,
        "archimate",
    )
    view = manager.get_active_model().views[0]

    # The connector must have survived the import, or the pass is vacuous.
    assert {c.uuid for c in view.conns} == {"id-conn-assignment", "id-conn-note"}
    note_connector = next(c for c in view.conns if c.uuid == "id-conn-note")
    assert note_connector.source.cat == "Label"
    assert layout_module.connection_relationship_type(note_connector) is None

    assert manager.validate_model()["is_valid"] is True
    assert manager.get_model_content_as_string(quality_gate="strict").startswith(
        "<model",
    )


ARCHI_MODEL_WITH_NOTE_CONNECTOR = """<?xml version="1.0" encoding="UTF-8"?>
<archimate:model xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xmlns:archimate="http://www.archimatetool.com/archimate"
                 name="Archi Note Model" id="id-archi-note-model" version="4.9.0">
  <folder name="Business" id="id-folder-business" type="business">
    <element xsi:type="archimate:BusinessActor" id="id-actor" name="Actor"/>
    <element xsi:type="archimate:BusinessRole" id="id-role" name="Role"/>
  </folder>
  <folder name="Relations" id="id-folder-relations" type="relations">
    <element xsi:type="archimate:AssignmentRelationship" id="id-assignment"
             source="id-actor" target="id-role"/>
  </folder>
  <folder name="Views" id="id-folder-views" type="diagrams">
    <element xsi:type="archimate:ArchimateDiagramModel" name="Note View" id="id-view">
      <child xsi:type="archimate:DiagramObject" id="id-node-actor"
             archimateElement="id-actor" targetConnections="id-conn-note">
        <bounds x="40" y="40" width="160" height="80"/>
        <sourceConnection xsi:type="archimate:Connection" id="id-conn-assignment"
                          source="id-node-actor" target="id-node-role"
                          archimateRelationship="id-assignment"/>
      </child>
      <child xsi:type="archimate:DiagramObject" id="id-node-role"
             archimateElement="id-role" targetConnections="id-conn-assignment">
        <bounds x="280" y="40" width="160" height="80"/>
      </child>
      <child xsi:type="archimate:Note" id="id-node-note">
        <content>Reminder</content>
        <bounds x="40" y="300" width="180" height="80"/>
        <sourceConnection xsi:type="archimate:Connection" id="id-conn-note"
                          source="id-node-note" target="id-node-actor"/>
      </child>
    </element>
  </folder>
</archimate:model>
"""


def test_native_archi_import_drops_note_connector_lines():
    """Honesty guard: the native Archi reader never yields a note connector.

    pyArchimate's Archi reader returns early from `_parse_connection` when a
    `sourceConnection` carries no `archimateRelationship`, which is exactly
    what Archi writes for a note line. Such a model therefore validates clean
    for a reason unrelated to the annotation-connector exemption, so nobody
    should read this test as proof of that exemption — the Open Exchange test
    above is the one that proves it.
    """
    manager = ArchimateModelManager()
    manager.load_model_from_string(ARCHI_MODEL_WITH_NOTE_CONNECTOR, "archi")
    view = manager.get_active_model().views[0]

    note_node = next(node for node in view.nodes if node.uuid == "id-node-note")
    assert note_node.cat == "Label"
    assert [c.uuid for c in view.conns] == ["id-conn-assignment"]

    assert manager.validate_model()["is_valid"] is True


XSI_TYPE_ATTRIBUTE = "{http://www.w3.org/2001/XMLSchema-instance}type"
EXCHANGE_NAMESPACE = "{http://www.opengroup.org/xsd/archimate/3.0/}"


def _build_annotated_view_fixture():
    """Two connected elements in one view, ready to be annotated."""
    manager = ArchimateModelManager()
    manager.create_new_model("Diagram Note Fixture")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    role = manager.add_archimate_element("Role", "BusinessRole")
    relationship = manager.add_archimate_relationship(
        actor.uuid,
        role.uuid,
        "Assignment",
    )
    view = manager.create_view("Annotated View")
    actor_node = manager.add_node_to_view(view.uuid, actor.uuid)
    role_node = manager.add_node_to_view(view.uuid, role.uuid)
    manager.add_connection_to_view(view.uuid, relationship.uuid)
    return manager, view, actor_node, role_node


def _view_node_by_id(view, node_id):
    return next(node for node in _all_view_nodes(view) if node.uuid == node_id)


def _note_nodes(view):
    return [node for node in _all_view_nodes(view) if node.cat == "Label"]


def _connections_by_id(view, connection_ids):
    connection_by_id = {connection.uuid: connection for connection in view.conns}
    return [connection_by_id[connection_id] for connection_id in connection_ids]


def _element_node_geometry(view):
    return [
        (node.uuid, node.x, node.y)
        for node in _all_view_nodes(view)
        if node.cat == "Element"
    ]


def test_add_note_to_view_creates_a_diagram_only_annotation():
    manager, view, actor_node, role_node = _build_annotated_view_fixture()
    model = manager.get_active_model()
    relationships_before = len(model.relationships)

    result = manager.add_note_to_view(
        view.uuid,
        "Legacy platform: retire in FY27",
        x=600,
        y=40,
        width=200,
        height=90,
        connect_to_node_ids=[actor_node.uuid, role_node.uuid],
        note_id="id-note-legacy",
    )

    assert result["node_id"] == "id-note-legacy"
    note = _view_node_by_id(view, "id-note-legacy")
    # Diagram-only: a Label node backed by no element and no concept.
    assert note.cat == "Label"
    assert note.ref is None
    assert note.concept is None
    assert note.label == "Legacy platform: retire in FY27"
    # Coordinates are written exactly as asked: a note annotates one spot.
    assert (note.x, note.y, note.w, note.h) == (600, 40, 200, 90)
    assert result["text"] == "Legacy platform: retire in FY27"
    assert (result["x"], result["y"]) == (600, 40)
    assert (result["width"], result["height"]) == (200, 90)
    assert result["connected_node_ids"] == [actor_node.uuid, role_node.uuid]

    connectors = _connections_by_id(view, result["connection_ids"])
    assert len(connectors) == 2  # noqa: PLR2004
    assert {connector.source.uuid for connector in connectors} == {"id-note-legacy"}
    assert {connector.target.uuid for connector in connectors} == {
        actor_node.uuid,
        role_node.uuid,
    }
    # Annotation-only lines: no ArchiMate relationship is created.
    assert all(connector.type is None for connector in connectors)
    assert all(connector.concept is None for connector in connectors)
    assert len(model.relationships) == relationships_before

    # A note describes itself when the view is read back.
    detail_nodes = {node.id: node for node in manager.map_view_to_detail(view).nodes}
    assert detail_nodes["id-note-legacy"].note_text == "Legacy platform: retire in FY27"
    assert detail_nodes[actor_node.uuid].note_text is None


def test_add_note_to_view_resolves_targets_by_node_id_and_element_id():
    manager, view, actor_node, role_node = _build_annotated_view_fixture()

    result = manager.add_note_to_view(
        view.uuid,
        "Both id kinds are accepted",
        x=40,
        y=400,
        connect_to_node_ids=[actor_node.uuid, role_node.ref],
    )

    connectors = _connections_by_id(view, result["connection_ids"])
    assert [connector.target.uuid for connector in connectors] == [
        actor_node.uuid,
        role_node.uuid,
    ]
    # The response always reports resolved *visual node* ids.
    assert result["connected_node_ids"] == [actor_node.uuid, role_node.uuid]


def test_add_note_to_view_rejects_unknown_view_and_targets():
    manager, view, actor_node, _role_node = _build_annotated_view_fixture()

    with pytest.raises(ViewNotFoundError):
        manager.add_note_to_view("id-not-a-view", "Nowhere", x=0, y=0)

    with pytest.raises(ModelOperationError) as excinfo:
        manager.add_note_to_view(
            view.uuid,
            "Bad targets",
            x=0,
            y=0,
            connect_to_node_ids=[actor_node.uuid, "id-ghost", "id-also-ghost"],
        )

    assert excinfo.value.details["unknown_ids"] == ["id-ghost", "id-also-ghost"]
    # Every target is resolved before anything is created, so a rejected
    # call leaves no half-built note behind.
    assert _note_nodes(view) == []


def test_add_note_to_view_rejects_blank_text_and_duplicate_note_ids():
    manager, view, _actor_node, _role_node = _build_annotated_view_fixture()

    with pytest.raises(ModelOperationError):
        manager.add_note_to_view(view.uuid, "   ", x=0, y=0)

    manager.add_note_to_view(view.uuid, "First", x=0, y=400, note_id="id-note")
    with pytest.raises(ModelOperationError):
        manager.add_note_to_view(view.uuid, "Second", x=0, y=600, note_id="id-note")

    assert [note.label for note in _note_nodes(view)] == ["First"]


def test_auto_layout_view_preserves_note_coordinates():
    """A note annotates one spot, so placement must never relocate it."""
    manager, view, actor_node, _role_node = _build_annotated_view_fixture()
    result = manager.add_note_to_view(
        view.uuid,
        "Pinned annotation",
        x=600,
        y=40,
        connect_to_node_ids=[actor_node.uuid],
    )
    note = _view_node_by_id(view, result["node_id"])
    elements_before = _element_node_geometry(view)

    manager.auto_layout_view(view.uuid)

    assert (note.x, note.y) == (600, 40)
    # ...while the element nodes are still laid out as usual.
    assert _element_node_geometry(view) != elements_before


def test_pyarchimate_layout_engine_preserves_note_coordinates():
    """One save/restore wraps the whole placement block, so both engines pin."""
    manager, view, actor_node, _role_node = _build_annotated_view_fixture()
    pinned = manager.add_note_to_view(
        view.uuid,
        "Pinned annotation",
        x=600,
        y=40,
        connect_to_node_ids=[actor_node.uuid],
    )
    # A wide note must not trip the upstream suitability guard. Upstream
    # does place notes, but their pinned coordinates are written back
    # afterwards, so the cell it chose is discarded — and since it never
    # reads w/h, an oversized note cannot displace anything else either.
    wide = manager.add_note_to_view(
        view.uuid,
        "A deliberately wide annotation",
        x=900,
        y=600,
        width=400,
    )
    note = _view_node_by_id(view, pinned["node_id"])
    wide_note = _view_node_by_id(view, wide["node_id"])

    manager.auto_layout_view(view.uuid, layout_engine="pyarchimate")

    assert (note.x, note.y) == (600, 40)
    assert (wide_note.x, wide_note.y) == (900, 600)
    assert sorted((node.x, node.y) for node in view.nodes if node.cat == "Element") == [
        (20, 20),
        (260, 20),
    ]


def _build_view_with_note_nested_in_a_group(
    note_width=100,
    note_height=40,
    *,
    with_note=True,
):
    """A Note dropped inside a Grouping — what Archi writes, and imports.

    Deliberately compact: with the default note size the whole group subtree
    stays inside the upstream 240px grid cell, so the `pyarchimate`
    suitability guard admits the view and both engines run on one fixture.
    """
    manager = ArchimateModelManager()
    manager.create_new_model("Nested Note Fixture")
    grouping = manager.add_archimate_element("Platform", "Grouping")
    member = manager.add_archimate_element("Member", "ApplicationComponent")
    manager.add_archimate_relationship(grouping.uuid, member.uuid, "Composition")
    view = manager.create_view("Nested Note View")
    group_node = manager.add_node_to_view(
        view.uuid,
        grouping.uuid,
        x=20,
        y=20,
        width=240,
        height=180,
    )
    manager.add_node_to_view(view.uuid, member.uuid, x=60, y=88)
    if not with_note:
        return manager, view, group_node, None
    note = view.add(
        node_type="Label",
        label="owner: platform team",
        x=60,
        y=120,
        w=note_width,
        h=note_height,
    )
    note.move(group_node)
    return manager, view, group_node, note


@pytest.mark.parametrize("layout_engine", ["internal", "pyarchimate"])
def test_auto_layout_view_pins_a_nested_note_to_its_group(layout_engine):
    """A note inside a group keeps its offset, so it travels with the group.

    The pin is captured before the prologue's `layout_group_children_for_view`,
    which lane-places a group's children; capturing after it would snapshot a
    position that pass had already destroyed. The offset (rather than absolute)
    form matters because Archi clips a child to its parent's rectangle, so a
    nested note held at absolute coordinates while its group moves away would
    be rendered invisible.
    """
    manager, view, group_node, note = _build_view_with_note_nested_in_a_group()
    offset_before = (note.x - group_node.x, note.y - group_node.y)
    assert offset_before == (40, 100)

    manager.auto_layout_view(view.uuid, layout_engine=layout_engine)

    assert note.parent is group_node
    assert (note.x - group_node.x, note.y - group_node.y) == offset_before
    # Still inside the group it annotates, so Archi will not clip it away.
    assert group_node.x <= note.x
    assert note.x + note.w <= group_node.x + group_node.w
    assert group_node.y <= note.y
    assert note.y + note.h <= group_node.y + group_node.h


def test_nested_note_never_influences_its_group_geometry():
    """Group bounds come from element children only.

    The note's coordinates are rewritten by `restore_note_positions` after
    placement, so sizing the group against them would size it against a
    value that is about to be overwritten. The note here is far larger than
    the group, so a group that grew or moved would prove it was measured.
    """
    # Two independent models: re-laying out one model cannot show this,
    # because `layout_group_children` only ever grows a group.
    annotated_manager, annotated_view, annotated_group, _note = (
        _build_view_with_note_nested_in_a_group(note_width=900, note_height=700)
    )
    bare_manager, bare_view, bare_group, _none = (
        _build_view_with_note_nested_in_a_group(with_note=False)
    )

    annotated_manager.auto_layout_view(annotated_view.uuid)
    bare_manager.auto_layout_view(bare_view.uuid)

    assert (
        annotated_group.x,
        annotated_group.y,
        annotated_group.w,
        annotated_group.h,
    ) == (bare_group.x, bare_group.y, bare_group.w, bare_group.h)


def test_routed_connections_avoid_note_nodes():
    """Notes are ink, not decoration: the router must see them as obstacles."""
    manager = ArchimateModelManager()
    manager.create_new_model("Note Routing Test")
    source = manager.add_archimate_element("Source", "BusinessProcess")
    target = manager.add_archimate_element("Target", "BusinessProcess")
    relationship = manager.add_archimate_relationship(
        source.uuid,
        target.uuid,
        "Flow",
    )
    view = manager.create_view("Note Routing View")
    manager.add_node_to_view(view.uuid, source.uuid, x=40, y=200)
    manager.add_node_to_view(view.uuid, target.uuid, x=800, y=200)
    connection = manager.add_connection_to_view(view.uuid, relationship.uuid)
    result = manager.add_note_to_view(
        view.uuid,
        "Sitting on the straight line",
        x=400,
        y=180,
        width=185,
        height=120,
    )
    note = _view_node_by_id(view, result["node_id"])

    layout_module.route_connections_around_nodes(view)

    points = _polyline(connection)
    assert list(connection.get_all_bendpoints()), "the note must bend the route"
    assert _is_orthogonal(points)
    note_rect = (note.x, note.y, note.w, note.h)
    assert not any(
        _segment_crosses_rect(first, second, note_rect)
        for first, second in pairwise(points)
    )


def test_notes_are_absent_from_element_queries_and_coverage():
    """Notes carry no element, no folder and no model-tree entry."""
    manager, view, actor_node, role_node = _build_annotated_view_fixture()
    queried_before = [element.uuid for element in manager.query_elements({})]
    counts_before = manager.count_by_type()
    orphans_before = manager.list_orphan_elements()
    coverage_before = manager.build_quality_report()["coverage"]

    manager.add_note_to_view(
        view.uuid,
        "Purely visual",
        x=600,
        y=40,
        connect_to_node_ids=[actor_node.uuid, role_node.uuid],
    )

    assert [element.uuid for element in manager.query_elements({})] == queried_before
    assert manager.count_by_type() == counts_before
    assert manager.list_orphan_elements() == orphans_before
    # The synthetic connector refs must not disturb relationship coverage.
    assert manager.build_quality_report()["coverage"] == coverage_before


def test_notes_and_note_connectors_validate_clean(tmp_path):
    """Depends on ARC-032: annotation connectors are exempt from validation."""
    manager, view, actor_node, role_node = _build_annotated_view_fixture()
    manager.add_note_to_view(
        view.uuid,
        "Reviewed 2026-07",
        x=600,
        y=40,
        connect_to_node_ids=[actor_node.uuid, role_node.uuid],
    )

    validation = manager.validate_model()
    assert validation["is_valid"] is True
    assert validation["invalid_connection_ids"] == []
    assert validation["invalid_node_ids"] == []
    assert manager.build_quality_report()["visual_validation"]["is_valid"] is True
    assert manager.get_model_content_as_string(quality_gate="strict").startswith(
        "<model",
    )
    manager.export_model_to_file(
        str(tmp_path / "annotated.archimate"),
        quality_gate="strict",
    )


def test_archi_export_never_pairs_concept_connection_type_with_missing_relationship():
    """The invariant that keeps Archi able to open a view at all.

    `archimate:Connection` is Archi's `DiagramModelArchimateConnection`,
    an `IDiagramModelArchimateComponent`. Writing one with no
    `archimateRelationship` makes `getArchimateConcept()` return null and
    Archi throws a NullPointerException building the diagram figures,
    surfacing as "Failed to create the part's controls" — the whole view
    becomes unopenable. pyArchimate's writer types every connection that
    way and merely omits the attribute for annotation lines, so the
    export pass has to retype them.
    """
    manager, view, actor_node, role_node = _build_annotated_view_fixture()
    manager.add_note_to_view(
        view.uuid,
        "Owner: payments squad",
        x=600,
        y=40,
        connect_to_node_ids=[actor_node.uuid, role_node.uuid],
    )
    manager.auto_layout_view(view.uuid)

    root = etree.fromstring(
        manager.get_model_content_as_string("archi").encode("utf-8"),
    )
    connectors = list(root.iter("sourceConnection"))
    assert connectors, "fixture must export some connections"
    offenders = [
        connector.get("id")
        for connector in connectors
        if connector.get("archimateRelationship") is None
        and connector.get(XSI_TYPE_ATTRIBUTE) != ARCHI_PLAIN_CONNECTION_TYPE
    ]
    assert offenders == [], (
        f"{len(offenders)} connector(s) would make Archi fail to open the view"
    )
    # The repair must be surgical: concept-backed connections keep both
    # the concept type and their relationship reference.
    concept_backed = [
        connector
        for connector in connectors
        if connector.get("archimateRelationship") is not None
    ]
    assert concept_backed, "fixture must export a real relationship connection"
    assert {connector.get(XSI_TYPE_ATTRIBUTE) for connector in concept_backed} == {
        "archimate:Connection",
    }


def test_note_survives_export_to_both_formats():
    manager, view, actor_node, _role_node = _build_annotated_view_fixture()
    result = manager.add_note_to_view(
        view.uuid,
        "Retire in FY27",
        x=600,
        y=40,
        connect_to_node_ids=[actor_node.uuid],
    )
    note_id = result["node_id"]

    # Archi native: the note becomes archimate:Note with a <content> child,
    # and its connector carries NO archimateRelationship, exactly as Archi
    # writes a note line.
    archi_content = manager.get_model_content_as_string("archi")
    archi_root = etree.fromstring(archi_content.encode("utf-8"))
    archi_note = next(
        child
        for child in archi_root.iter("child")
        if child.get(XSI_TYPE_ATTRIBUTE) == "archimate:Note"
    )
    assert archi_note.get("id") == note_id
    assert archi_note.find("content").text == "Retire in FY27"
    archi_connector = next(
        connector
        for connector in archi_root.iter("sourceConnection")
        if connector.get("source") == note_id
    )
    assert archi_connector.get("target") == actor_node.uuid
    assert archi_connector.get("archimateRelationship") is None
    # ...and it must NOT be archimate:Connection, which is Archi's
    # concept-backed DiagramModelArchimateConnection. See
    # test_archi_export_never_pairs_concept_connection_type_with_missing_relationship.
    assert archi_connector.get(XSI_TYPE_ATTRIBUTE) == ARCHI_PLAIN_CONNECTION_TYPE

    # Open Exchange: xsi:type="Label" with the text in a <label> child.
    exchange_content = manager.get_model_content_as_string("archimate")
    exchange_root = etree.fromstring(exchange_content.encode("utf-8"))
    exchange_note = next(
        node
        for node in exchange_root.iter(f"{EXCHANGE_NAMESPACE}node")
        if node.get(XSI_TYPE_ATTRIBUTE) == "Label"
    )
    assert exchange_note.get("identifier") == note_id
    assert exchange_note.find(f"{EXCHANGE_NAMESPACE}label").text == "Retire in FY27"
    note_lines = [
        connection
        for connection in exchange_root.iter(f"{EXCHANGE_NAMESPACE}connection")
        if connection.get("source") == note_id
    ]
    assert [connection.get("target") for connection in note_lines] == [
        actor_node.uuid,
    ]
    # A note line is a view-only connection, so it must be the schema's
    # `Line`, not a `Relationship` pointing at an id nothing declares.
    assert [connection.get(XSI_TYPE_ATTRIBUTE) for connection in note_lines] == [
        "Line",
    ]
    assert [connection.get("relationshipRef") for connection in note_lines] == [None]

    # Both formats survive a reload. The exchange reader skips every
    # `Line`, so `_restore_exchange_note_connectors` rebuilds the note
    # lines afterwards — identifier included. The native Archi reader
    # drops the connector line outright (pyArchimate's `_parse_connection`
    # discards a sourceConnection without an archimateRelationship), so an
    # MCP archi round trip loses the line even though Archi itself keeps it.
    reloaded = ArchimateModelManager()
    reloaded.load_model_from_string(exchange_content, "archimate")
    reloaded_view = reloaded.get_active_model().views[0]
    reloaded_note = _view_node_by_id(reloaded_view, note_id)
    assert reloaded_note.cat == "Label"
    assert reloaded_note.label == "Retire in FY27"
    assert [
        connection.uuid
        for connection in reloaded_view.conns
        if connection.source.uuid == note_id
    ] == list(result["connection_ids"])
    # The restored line must still be exempt from visual validation, and
    # re-exporting it must stay schema-valid rather than degrading on the
    # second lap.
    assert reloaded.validate_model()["is_valid"] is True
    assert (
        _dangling_exchange_idrefs(
            reloaded.get_model_content_as_string("archimate"),
        )
        == {}
    )

    # Pin the native-archi asymmetry rather than leaving it to a comment:
    # the note node comes back, the connector line does not, because
    # pyArchimate's reader keys on archimateRelationship. That predates
    # the connection retype (the attribute was already absent), so this
    # asserts the loss is unchanged, not newly introduced.
    archi_reloaded = ArchimateModelManager()
    archi_reloaded.load_model_from_string(archi_content, "archi")
    archi_view = archi_reloaded.get_active_model().views[0]
    assert _view_node_by_id(archi_view, note_id).cat == "Label"
    assert [
        connection.uuid
        for connection in archi_view.conns
        if connection.source.uuid == note_id
    ] == []


def _dangling_exchange_idrefs(content):
    """Every IDREF attribute in exchange XML that resolves to nothing.

    The Open Exchange schema types `relationshipRef`, `elementRef` and
    `propertyDefinitionRef` as `xs:IDREF`, so an unresolvable value fails
    keyref validation for the whole document — Archi's validating import
    included. Checking resolution here is the schema check without
    shipping (or downloading) the XSDs.
    """
    root = etree.fromstring(content.encode("utf-8"))
    declared = {
        element.get("identifier")
        for element in root.iter()
        if element.get("identifier")
    }
    dangling = {}
    for attribute in ("relationshipRef", "elementRef", "propertyDefinitionRef"):
        unresolved = sorted(
            {
                element.get(attribute)
                for element in root.iter()
                if element.get(attribute) and element.get(attribute) not in declared
            },
        )
        if unresolved:
            dangling[attribute] = unresolved
    return dangling


def test_exchange_export_declares_every_idref_it_references():
    """The default export format must not carry an unresolvable IDREF.

    pyArchimate's exchange writer types every connection `Relationship`
    and copies `c.ref` into the required `relationshipRef`. A note line's
    `ref` is synthetic and deliberately absent from `model.rels_dict`, so
    without the `Line` rewrite this document fails keyref validation.
    """
    manager, view, actor_node, _role_node = _build_annotated_view_fixture()
    without_note = manager.get_model_content_as_string("archimate")
    manager.add_note_to_view(
        view.uuid,
        "Retire in FY27",
        x=600,
        y=40,
        connect_to_node_ids=[actor_node.uuid],
    )

    assert _dangling_exchange_idrefs(without_note) == {}
    assert (
        _dangling_exchange_idrefs(manager.get_model_content_as_string("archimate"))
        == {}
    )


def test_validate_semantics_enriches_invalid_relationship_and_groups_counts():
    manager = ArchimateModelManager()
    manager.create_new_model("Semantic Validation Test")
    process = manager.add_archimate_element("Search Parking", "BusinessProcess")
    service = manager.add_archimate_element("Search Service", "ApplicationService")
    relationship = manager.add_archimate_relationship(
        process.uuid,
        service.uuid,
        "Access",
        access_type="Read",
    )

    result = manager.validate_semantics()

    issue = next(
        issue
        for issue in result["issues"]
        if issue["code"] == "INVALID_RELATIONSHIP_COMBINATION"
    )
    assert result["is_valid"] is False
    assert issue["relationship_id"] == relationship.uuid
    assert issue["source_name"] == "Search Parking"
    assert issue["target_type"] == "ApplicationService"
    assert issue["suggested_repairs"][0]["new_type"] == "Serving"
    assert result["issue_counts"]["by_code"]["INVALID_RELATIONSHIP_COMBINATION"] == 1


def test_dangling_view_node_is_reported_once_by_visual_validation():
    """A node whose element vanished is a visual verdict, not a semantic one.

    pyArchimate's `check_invalid_nodes` already owns it, and
    `build_quality_report` puts visual and semantic validation side by
    side — so the old `MISSING_NODE_ELEMENT` semantic issue counted one
    dangling node twice.
    """
    manager = ArchimateModelManager()
    manager.create_new_model("Dangling Node Test")
    actor = manager.add_archimate_element("Actor", "BusinessActor")
    stranded = manager.add_archimate_element("Stranded", "ApplicationComponent")
    view = manager.create_view("Dangling View")
    manager.add_node_to_view(view.uuid, actor.uuid)
    node = manager.add_node_to_view(view.uuid, stranded.uuid)
    # Drop the element without cascading into its view node, which is the
    # shape an imported file with a dangling reference arrives in.
    del manager.get_active_model().elems_dict[stranded.uuid]

    validation = manager.validate_model()

    assert set(validation) == {
        "is_valid",
        "invalid_connection_ids",
        "invalid_node_ids",
        "invalid_connections_count",
        "invalid_nodes_count",
    }
    assert validation["is_valid"] is False
    assert validation["invalid_node_ids"] == [node.uuid]
    assert validation["invalid_nodes_count"] == 1

    semantics = manager.validate_semantics()
    assert not [
        issue
        for issue in semantics["issues"]
        if issue["code"] == "MISSING_NODE_ELEMENT"
    ]

    report = manager.build_quality_report()
    assert report["visual_validation"]["invalid_node_ids"] == [node.uuid]
    assert (
        "MISSING_NODE_ELEMENT"
        not in report["semantic_validation"]["issue_counts"]["by_code"]
    )
    assert json.dumps(report).count(node.uuid) == 1


def test_repair_semantic_issues_preserves_relationship_id_and_reconnects_view():
    manager = ArchimateModelManager()
    manager.create_new_model("Repair Test")
    process = manager.add_archimate_element("Search Parking", "BusinessProcess")
    service = manager.add_archimate_element("Search Service", "ApplicationService")
    relationship = manager.add_archimate_relationship(
        process.uuid,
        service.uuid,
        "Access",
        access_type="Read",
        relationship_id="id-invalid",
    )
    view = manager.create_view("Repair View")
    manager.add_node_to_view(view.uuid, process.uuid)
    manager.add_node_to_view(view.uuid, service.uuid)
    manager.add_connection_to_view(view.uuid, relationship.uuid)
    repair_id = manager.validate_semantics()["issues"][0]["suggested_repairs"][0][
        "repair_id"
    ]

    result = manager.repair_semantic_issues(repair_ids=[repair_id])
    repaired = manager.get_relationship_by_id("id-invalid")

    assert result["applied_count"] == 1
    assert repaired is not None
    assert repaired.type == "Serving"
    assert repaired.source.uuid == service.uuid
    assert repaired.target.uuid == process.uuid
    assert {connection.ref for connection in view.conns} == {"id-invalid"}


def test_export_quality_gate_warn_and_strict_modes(tmp_path):
    manager = ArchimateModelManager()
    manager.create_new_model("Quality Gate Test")
    process = manager.add_archimate_element("Search Parking", "BusinessProcess")
    service = manager.add_archimate_element("Search Service", "ApplicationService")
    manager.add_archimate_relationship(
        process.uuid,
        service.uuid,
        "Access",
        access_type="Read",
    )

    warn_content = manager.get_model_content_as_string(quality_gate="warn")
    assert warn_content.startswith("<model")

    export_path = tmp_path / "quality-gate.archimate"
    result = manager.export_model_to_file(
        str(export_path),
        quality_gate="warn",
        include_quality_report=True,
    )
    assert result["quality_report"]["semantic_validation"]["is_valid"] is False

    with pytest.raises(ModelOperationError):
        manager.get_model_content_as_string(quality_gate="strict")


def test_assess_togaf_readiness_is_advisory_and_excludes_qa_views():
    manager = ArchimateModelManager()
    manager.create_new_model("TOGAF Readiness Test")
    manager.create_view(
        "Relationship Coverage",
        properties={
            "mcp:relationship_coverage_view": "true",
            "is_quality_assurance_view": "true",
            "purpose": "QA only",
        },
    )

    result = manager.assess_togaf_readiness()

    assert result["compliance_claim"] is False
    assert result["status"] in {"limited", "partial"}
    assert any(
        finding["code"] == "NO_STAKEHOLDER_FACING_VIEWS"
        for finding in result["advisory_findings"]
    )


def test_model_export_and_load_round_trip_from_string():
    manager = ArchimateModelManager()
    manager.create_new_model("Round Trip")
    manager.add_archimate_element("Actor", "BusinessActor", properties={"k": "v"})

    content = manager.get_model_content_as_string()
    loaded = ArchimateModelManager()
    loaded.load_model_from_string(content)
    loaded_info = loaded.get_model_info()

    assert content.startswith("<model")
    assert loaded_info["name"] == "Round Trip"
    assert loaded_info["elements_count"] == 1
    assert loaded.list_elements()[0].props == {"k": "v"}


def test_model_metadata_survives_native_archi_round_trip():
    manager = ArchimateModelManager()
    manager.create_new_model("Archi Metadata")
    manager.update_model_metadata(
        description="Model documentation written by the MCP.",
        properties={"owner": "EA", "status": "draft"},
    )

    content = manager.get_model_content_as_string("archi")
    loaded = ArchimateModelManager()
    loaded.load_model_from_string(content, "archi")
    loaded_info = loaded.get_model_info()

    assert loaded_info["name"] == "Archi Metadata"
    assert loaded_info["documentation"] == "Model documentation written by the MCP."
    assert loaded_info["properties"] == {"owner": "EA", "status": "draft"}


def test_model_metadata_survives_exchange_format_round_trip():
    manager = ArchimateModelManager()
    manager.create_new_model(
        "Exchange Metadata",
        description="Model documentation written by the MCP.",
        properties={"owner": "EA", "status": "draft"},
    )

    content = manager.get_model_content_as_string("archimate")
    loaded = ArchimateModelManager()
    loaded.load_model_from_string(content, "archimate")
    loaded_info = loaded.get_model_info()

    assert loaded_info["name"] == "Exchange Metadata"
    assert loaded_info["documentation"] == "Model documentation written by the MCP."
    assert loaded_info["properties"] == {"owner": "EA", "status": "draft"}


def test_model_export_supports_native_archi_format():
    manager = ArchimateModelManager()
    manager.create_new_model("Archi Native")
    manager.add_archimate_element("Actor", "BusinessActor")

    content = manager.get_model_content_as_string("archi")
    loaded = ArchimateModelManager()
    loaded.load_model_from_string(content, "archi")

    assert content.startswith("<archimate:model")
    assert 'xmlns:archimate="http://www.archimatetool.com/archimate"' in content
    assert 'xsi:type="archimate:BusinessActor"' in content
    assert loaded.get_model_info()["name"] == "Archi Native"
    assert loaded.list_elements()[0].type == "BusinessActor"


def test_native_archi_load_preserves_element_documentation():
    manager = ArchimateModelManager()
    manager.create_new_model("Archi Native Documentation")
    manager.add_archimate_element(
        "Actor",
        "BusinessActor",
        description="Documentation imported from Archi XML.",
    )

    content = manager.get_model_content_as_string("archi")
    loaded = ArchimateModelManager()
    loaded.load_model_from_string(content, "archi")

    assert loaded.list_elements()[0].desc == "Documentation imported from Archi XML."


def test_load_model_from_string_rejects_dtd_entities():
    manager = ArchimateModelManager()
    malicious_content = """<?xml version="1.0"?>
<!DOCTYPE model [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<model>&xxe;</model>
"""

    with pytest.raises(ModelOperationError):
        manager.load_model_from_string(malicious_content)


def test_exports_include_properties():
    manager = ArchimateModelManager()
    manager.create_new_model("CSV Test")
    actor = manager.add_archimate_element(
        "Actor",
        "BusinessActor",
        properties={"owner": "EA"},
    )
    role = manager.add_archimate_element("Role", "BusinessRole")
    manager.add_archimate_relationship(
        actor.uuid,
        role.uuid,
        "Assignment",
        properties={"priority": "1"},
    )

    elements_csv = manager.export_elements_to_csv()
    relationships_csv = manager.export_relationships_to_csv()

    assert "Property:owner" in elements_csv
    assert "EA" in elements_csv
    assert "Property:priority" in relationships_csv
    assert "Assignment" in relationships_csv


def test_action_requiring_active_model_raises_model_not_found():
    manager = ArchimateModelManager()

    with pytest.raises(ModelNotFoundError):
        manager.get_model_content_as_string()


def test_native_archi_export_converts_and_or_junctions_without_mutating_model():
    manager = ArchimateModelManager()
    manager.create_new_model("Typed Junction Export Test")
    and_junction = manager.add_archimate_element("All Of", "AndJunction")
    or_junction = manager.add_archimate_element("Any Of", "OrJunction")
    junction_count = 2

    content = manager.get_model_content_as_string("archi")

    # Archi's native format has a single Junction concept with a type
    # attribute; archimate:AndJunction / archimate:OrJunction are invalid.
    assert 'xsi:type="archimate:AndJunction"' not in content
    assert 'xsi:type="archimate:OrJunction"' not in content
    assert content.count('xsi:type="archimate:Junction"') == junction_count
    assert 'type="and"' in content
    assert 'type="or"' in content
    assert and_junction.type == "AndJunction"
    assert or_junction.type == "OrJunction"


def test_viewpoint_survives_native_export_load_and_reexport():
    manager = ArchimateModelManager()
    manager.create_new_model("Viewpoint Round Trip Test")
    manager.create_view("Service View", properties={"viewpoint": "service"})

    first_content = manager.get_model_content_as_string("archi")
    assert 'viewpoint="service_realization"' in first_content

    reloaded = ArchimateModelManager()
    reloaded.load_model_from_string(first_content, "archi")
    second_content = reloaded.get_model_content_as_string("archi")

    assert 'viewpoint="service_realization"' in second_content


def _build_rich_fixture_model():
    manager = ArchimateModelManager()
    manager.create_new_model("Fixture Model")
    actor = manager.add_archimate_element("Customer", "BusinessActor")
    process = manager.add_archimate_element("Checkout", "BusinessProcess")
    service = manager.add_archimate_element("Sales Service", "BusinessService")
    group = manager.add_archimate_element("Commerce Domain", "Grouping")
    component = manager.add_archimate_element("Portal", "ApplicationComponent")
    app_service = manager.add_archimate_element("Cart API", "ApplicationService")
    data = manager.add_archimate_element("Order", "DataObject")
    node = manager.add_archimate_element("Cluster", "Node")
    junction = manager.add_archimate_element("Split", "AndJunction")
    driver = manager.add_archimate_element("Market", "Driver")
    goal = manager.add_archimate_element("Growth", "Goal")
    manager.add_archimate_relationship(actor.uuid, process.uuid, "Assignment")
    manager.add_archimate_relationship(service.uuid, actor.uuid, "Serving")
    manager.add_archimate_relationship(process.uuid, service.uuid, "Realization")
    manager.add_archimate_relationship(group.uuid, component.uuid, "Composition")
    manager.add_archimate_relationship(group.uuid, app_service.uuid, "Aggregation")
    manager.add_archimate_relationship(component.uuid, app_service.uuid, "Realization")
    manager.add_archimate_relationship(app_service.uuid, process.uuid, "Serving")
    manager.add_archimate_relationship(
        app_service.uuid,
        data.uuid,
        "Access",
        access_type="ReadWrite",
    )
    manager.add_archimate_relationship(node.uuid, component.uuid, "Serving")
    manager.add_archimate_relationship(process.uuid, junction.uuid, "Triggering")
    manager.add_archimate_relationship(
        driver.uuid,
        goal.uuid,
        "Influence",
        influence_strength="++",
    )
    view = manager.create_view("Overview", properties={"viewpoint": "layered"})
    for element in [
        actor,
        process,
        service,
        group,
        component,
        app_service,
        data,
        node,
        junction,
        driver,
        goal,
    ]:
        manager.add_node_to_view(view.uuid, element.uuid)
    manager.connect_visible_relationships(view.uuid)
    return manager


def test_fixture_model_round_trips_in_both_formats():
    manager = _build_rich_fixture_model()
    manager.auto_layout_all_views()
    info = manager.get_model_info()

    for output_format in ("archi", "archimate"):
        content = manager.get_model_content_as_string(output_format)
        reloaded = ArchimateModelManager()
        reloaded.load_model_from_string(content, output_format)
        reloaded_info = reloaded.get_model_info()
        assert reloaded_info["elements_count"] == info["elements_count"]
        assert reloaded_info["relationships_count"] == info["relationships_count"]
        assert reloaded_info["views_count"] == info["views_count"]


def test_repair_semantic_issues_repairs_all_deterministic_issues():
    manager = ArchimateModelManager()
    manager.create_new_model("Repair All Test")
    process = manager.add_archimate_element("Search Parking", "BusinessProcess")
    service = manager.add_archimate_element("Search Service", "ApplicationService")
    business_object = manager.add_archimate_element("Booking", "BusinessObject")
    manager.add_archimate_relationship(
        process.uuid,
        service.uuid,
        "Access",
        access_type="Read",
    )
    manager.add_archimate_relationship(process.uuid, business_object.uuid, "Flow")
    expected_repairs = 2
    issues_before = manager.validate_semantics()["issues_count"]
    assert issues_before >= expected_repairs

    result = manager.repair_semantic_issues(repair_all_deterministic=True)

    assert result["applied_count"] >= expected_repairs
    assert manager.validate_semantics()["issues_count"] < issues_before


def test_auto_layout_heals_legacy_duplicate_group_member_nodes():
    manager = ArchimateModelManager()
    manager.create_new_model("Legacy Heal Test")
    group = manager.add_archimate_element("Domain", "Grouping")
    service = manager.add_archimate_element("Service", "ApplicationService")
    process = manager.add_archimate_element("Process", "BusinessProcess")
    manager.add_archimate_relationship(group.uuid, service.uuid, "Composition")
    serving = manager.add_archimate_relationship(service.uuid, process.uuid, "Serving")
    view = manager.create_view("Legacy View")
    group_node = manager.add_node_to_view(view.uuid, group.uuid, x=40, y=300)
    stray_node = manager.add_node_to_view(view.uuid, service.uuid, x=600, y=40)
    process_node = manager.add_node_to_view(view.uuid, process.uuid, x=900, y=40)
    # Simulate the pre-fix duplication: a second copy nested in the group.
    group_node.add(
        ref=manager.get_element_by_id(service.uuid),
        x=80,
        y=350,
        w=160,
        h=60,
    )
    view.add_connection(
        ref=manager.get_relationship_by_id(serving.uuid),
        source=stray_node,
        target=process_node,
    )

    manager.auto_layout_view(view.uuid)

    service_nodes = [
        node
        for node in manager.map_view_to_detail(view).nodes
        if node.element_id == service.uuid
    ]
    assert len(service_nodes) == 1
    assert service_nodes[0].parent_node_id == group_node.uuid
    surviving_connections = [
        connection for connection in view.conns if connection.ref == serving.uuid
    ]
    assert len(surviving_connections) == 1
    assert surviving_connections[0].source.ref == service.uuid


def test_archi_viewpoint_ids_are_accepted_and_exported():
    manager = ArchimateModelManager()
    manager.create_new_model("Archi Viewpoint Test")
    manager.create_view("Layered View", properties={"viewpoint": "layered"})

    content = manager.get_model_content_as_string("archi")

    assert 'viewpoint="layered"' in content

    reloaded = ArchimateModelManager()
    reloaded.load_model_from_string(content, "archi")
    second_content = reloaded.get_model_content_as_string("archi")
    assert 'viewpoint="layered"' in second_content


def test_unknown_viewpoint_rejected_with_both_catalogs():
    manager = ArchimateModelManager()
    manager.create_new_model("Bad Viewpoint Test")

    with pytest.raises(ModelOperationError) as exc_info:
        manager.create_view("Bad", properties={"viewpoint": "bogus"})

    assert "supported_archi_viewpoint_ids" in exc_info.value.details
    assert "layered" in exc_info.value.details["supported_archi_viewpoint_ids"]


def test_auto_layout_fixture_model_meets_compactness_floor():
    manager = _build_rich_fixture_model()
    manager.auto_layout_all_views()
    for view in manager.list_views():
        nodes = manager._view_nodes_recursive(view)  # noqa: SLF001
        if len(nodes) < 3:  # noqa: PLR2004
            continue
        x_span = max(n.x + n.w for n in nodes) - min(n.x for n in nodes)
        y_span = max(n.y + n.h for n in nodes) - min(n.y for n in nodes)
        ink = sum(n.w * n.h for n in nodes) / (x_span * y_span)
        top_level = list(view.nodes)
        overlaps = [
            (a.uuid, b.uuid)
            for i, a in enumerate(top_level)
            for b in top_level[i + 1 :]
            if _nodes_overlap(a, b)
        ]
        assert overlaps == [], f"{view.name}: overlapping nodes"
        assert x_span <= 2000, f"{view.name}: lane failed to wrap ({x_span}px)"  # noqa: PLR2004
        assert ink >= 0.10, f"{view.name}: ink density {ink:.0%} below floor"  # noqa: PLR2004


def _make_two_layer_view(manager):
    process = manager.add_archimate_element("Checkout", "BusinessProcess")
    component = manager.add_archimate_element("Portal", "ApplicationComponent")
    manager.add_archimate_relationship(component.uuid, process.uuid, "Serving")
    view = manager.create_view("Banded View")
    manager.add_node_to_view(view.uuid, process.uuid)
    manager.add_node_to_view(view.uuid, component.uuid)
    manager.connect_visible_relationships(view.uuid)
    return view


def test_auto_layout_adds_layer_bands_for_multi_layer_views():
    manager = ArchimateModelManager()
    manager.create_new_model("Layer Band Test")
    elements_before_view = manager.get_model_info()["elements_count"]
    view = _make_two_layer_view(manager)

    manager.auto_layout_view(view.uuid)

    bands = [node for node in view.nodes if getattr(node, "cat", None) == "Container"]
    assert sorted(band.label for band in bands) == ["Application", "Business"]
    # Bands are diagram-only: the semantic model gains no elements.
    assert manager.get_model_info()["elements_count"] == elements_before_view + 2
    # Members are nested inside their band.
    for band in bands:
        assert band.nodes
    # Idempotent: repeated layout does not stack bands.
    manager.auto_layout_view(view.uuid)
    bands_after = [
        node for node in view.nodes if getattr(node, "cat", None) == "Container"
    ]
    assert len(bands_after) == len(bands)
    # Native export writes visual groups.
    content = manager.get_model_content_as_string("archi")
    assert content.count('xsi:type="archimate:Group"') >= 2  # noqa: PLR2004


def test_auto_layout_layer_bands_can_be_disabled_and_skip_single_layer():
    manager = ArchimateModelManager()
    manager.create_new_model("No Band Test")
    view = _make_two_layer_view(manager)

    manager.auto_layout_view(view.uuid, layer_bands=False)
    assert not [
        node for node in view.nodes if getattr(node, "cat", None) == "Container"
    ]

    single = manager.create_view("Single Layer")
    only = manager.add_archimate_element("Only", "BusinessActor")
    manager.add_node_to_view(single.uuid, only.uuid)
    manager.auto_layout_view(single.uuid)
    assert not [
        node for node in single.nodes if getattr(node, "cat", None) == "Container"
    ]


def test_failed_corridor_search_falls_back_to_orthogonal_dogleg(monkeypatch):
    manager = ArchimateModelManager()
    manager.create_new_model("Dogleg Test")
    source = manager.add_archimate_element("Source", "ApplicationComponent")
    target = manager.add_archimate_element("Target", "Node")
    relationship = manager.add_archimate_relationship(
        source.uuid,
        target.uuid,
        "Serving",
    )
    view = manager.create_view("Dogleg View")
    manager.add_node_to_view(view.uuid, source.uuid, x=40, y=40)
    manager.add_node_to_view(view.uuid, target.uuid, x=900, y=700)
    connection = manager.add_connection_to_view(view.uuid, relationship.uuid)

    # Simulate corridor-search exhaustion (the tall-canvas failure mode).
    from pyarchimate_mcp_server import layout as layout_module

    monkeypatch.setattr(
        layout_module.ObstacleMap,
        "find_corridor",
        lambda *_args, **_kwargs: None,
    )
    manager._route_connections_around_nodes(view)  # noqa: SLF001

    points = _polyline(connection)
    assert len(connection.get_all_bendpoints()) >= 3  # noqa: PLR2004
    assert _is_orthogonal(points), "fallback must never be a straight diagonal"


def _build_large_fixture_model(stacks=20):
    """Deterministic multi-layer model big enough to cross dense thresholds.

    Each stack: actor -> process -> service, component/app-service support,
    node hosting, data access, plus a process chain across stacks. With 20
    stacks this yields ~120 elements and ~139 relationships, so the full
    view exceeds both dense-routing gates (>=36 connections at >=1.15 per
    node) and forces lane wrapping (20 same-lane nodes would otherwise
    span ~6,600px).
    """
    manager = ArchimateModelManager()
    manager.create_new_model("Large Fixture")
    processes = []
    for index in range(stacks):
        actor = manager.add_archimate_element(f"Actor {index}", "BusinessActor")
        process = manager.add_archimate_element(
            f"Process {index}",
            "BusinessProcess",
        )
        service = manager.add_archimate_element(
            f"Business Service {index}",
            "BusinessService",
        )
        component = manager.add_archimate_element(
            f"Component {index}",
            "ApplicationComponent",
        )
        app_service = manager.add_archimate_element(
            f"App Service {index}",
            "ApplicationService",
        )
        data = manager.add_archimate_element(f"Data {index}", "DataObject")
        node = manager.add_archimate_element(f"Node {index}", "Node")
        manager.add_archimate_relationship(actor.uuid, process.uuid, "Assignment")
        manager.add_archimate_relationship(process.uuid, service.uuid, "Realization")
        manager.add_archimate_relationship(
            component.uuid,
            app_service.uuid,
            "Realization",
        )
        manager.add_archimate_relationship(app_service.uuid, process.uuid, "Serving")
        manager.add_archimate_relationship(
            app_service.uuid,
            data.uuid,
            "Access",
            access_type="ReadWrite",
        )
        manager.add_archimate_relationship(node.uuid, component.uuid, "Serving")
        processes.append(process)
    for previous, current in pairwise(processes):
        manager.add_archimate_relationship(
            previous.uuid,
            current.uuid,
            "Triggering",
        )
    view = manager.create_view("Everything", properties={"viewpoint": "layered"})
    for element in manager.list_elements():
        manager.add_node_to_view(view.uuid, element.uuid)
    manager.connect_visible_relationships(view.uuid)
    return manager, view


def test_large_fixture_round_trips_and_lays_out_at_scale():
    manager, view = _build_large_fixture_model()
    info = manager.get_model_info()
    assert info["elements_count"] >= 120  # noqa: PLR2004
    assert len(view.conns) >= 60  # noqa: PLR2004

    manager.auto_layout_all_views()

    nodes = manager._view_nodes_recursive(view)  # noqa: SLF001
    element_nodes = [n for n in nodes if getattr(n, "cat", "Element") == "Element"]
    x_span = max(n.x + n.w for n in element_nodes) - min(n.x for n in element_nodes)
    y_span = max(n.y + n.h for n in element_nodes) - min(n.y for n in element_nodes)
    ink = sum(n.w * n.h for n in element_nodes) / (x_span * y_span)
    assert x_span <= 2000, f"lanes failed to wrap at scale ({x_span}px)"  # noqa: PLR2004
    assert ink >= 0.10, f"ink density {ink:.0%} below floor at scale"  # noqa: PLR2004
    top_level = list(view.nodes)
    overlaps = [
        (a.uuid, b.uuid)
        for i, a in enumerate(top_level)
        for b in top_level[i + 1 :]
        if _nodes_overlap(a, b)
    ]
    assert overlaps == []
    bands = [n for n in view.nodes if getattr(n, "cat", None) == "Container"]
    assert len(bands) >= 3  # noqa: PLR2004

    for output_format in ("archi", "archimate"):
        content = manager.get_model_content_as_string(output_format)
        reloaded = ArchimateModelManager()
        reloaded.load_model_from_string(content, output_format)
        reloaded_info = reloaded.get_model_info()
        assert reloaded_info["elements_count"] == info["elements_count"]
        assert reloaded_info["relationships_count"] == info["relationships_count"]
        assert reloaded_info["views_count"] == info["views_count"]


def test_large_fixture_engages_dense_view_policies():
    manager, view = _build_large_fixture_model()
    manager.auto_layout_view(view.uuid)

    from pyarchimate_mcp_server import layout as layout_module

    assert layout_module.should_simplify_connection_routing(view) is True
    # Dense simplification: straight lines only, no bendpoints anywhere.
    assert all(not list(c.get_all_bendpoints()) for c in view.conns)
    # Dense label policy: only primary flow labels stay, secondaries muted.
    hidden = [c for c in view.conns if c.show_label is False]
    assert hidden, "dense label policy should hide secondary labels"
    muted = [
        c for c in hidden if c.line_color == SECONDARY_DENSE_RELATIONSHIP_LINE_COLOR
    ]
    assert muted, "secondary connections should be de-emphasized"


def test_auto_layout_survives_view_node_whose_element_is_gone():
    # pyArchimate reports Node.concept as None when the ref does not resolve to
    # an element (e.g. a model loaded with a dangling reference). node_layer_name
    # used to dereference it, which crashed the entire layout pass.
    from pyarchimate_mcp_server import layout as layout_module

    manager = ArchimateModelManager()
    manager.create_new_model("Dangling Node Ref Test")
    actor = manager.add_archimate_element("Customer", "BusinessActor")
    process = manager.add_archimate_element("Checkout", "BusinessProcess")
    manager.add_archimate_relationship(actor.uuid, process.uuid, "Assignment")
    view = manager.create_view("Overview")
    manager.add_node_to_view(view.uuid, actor.uuid, x=40, y=40)
    manager.add_node_to_view(view.uuid, process.uuid, x=40, y=300)
    manager.connect_visible_relationships(view.uuid)
    stale_node = list(view.nodes)[-1]
    # The public ref setter refuses unknown ids, so simulate the corrupt state.
    stale_node._ref = "id-element-that-no-longer-exists"  # noqa: SLF001
    assert stale_node.concept is None

    assert layout_module.node_layer_name(stale_node) == "Other"
    assert layout_module.node_layout_row_name(stale_node) == "Other"

    detail = manager.auto_layout_view(view.uuid)

    assert len(detail.nodes) == len(view.nodes)


def test_dense_label_policy_leaves_annotation_connectors_untouched():
    # Since pyArchimate 1.12.0 a connector whose ref is not a Relationship
    # reports concept/type/name as None instead of raising KeyError. Such
    # connectors carry no ArchiMate semantics, so the dense-view label policy
    # must skip them rather than mute them as secondary relationships.
    from pyarchimate_mcp_server import layout as layout_module

    manager, view = _build_large_fixture_model()
    note = view.add(ref=None, x=40, y=40, w=180, h=80, node_type="Label", label="Note")
    connector = view.connect_note(note, next(iter(view.nodes)))
    assert connector.concept is None
    assert connector.type is None
    assert layout_module.connection_relationship_type(connector) is None
    assert manager._is_group_containment_connection(connector) is False  # noqa: SLF001

    assert layout_module.should_simplify_connection_labels(view) is True
    layout_module.apply_relationship_label_policy(view)

    assert connector.show_label is not False
    assert connector.line_color != SECONDARY_DENSE_RELATIONSHIP_LINE_COLOR
    muted = [
        c for c in view.conns if c.line_color == SECONDARY_DENSE_RELATIONSHIP_LINE_COLOR
    ]
    assert muted, "real secondary relationships should still be de-emphasized"

    # Read paths describe the connector without a relationship type.
    detail_connections = manager.map_view_to_detail(view).connections
    annotation = next(c for c in detail_connections if c.id == connector.uuid)
    assert annotation.relationship_type is None
    summary = manager.summarize_view(view.uuid)
    assert summary["connection_counts_by_type"]["Unknown"] == 1

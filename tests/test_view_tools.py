import asyncio

from lxml import etree

from pyarchimate_mcp_server.constants import SUPPORTED_FORMATS
from pyarchimate_mcp_server.model_manager import (
    DEFAULT_NOTE_HEIGHT,
    DEFAULT_NOTE_WIDTH,
    ArchimateModelManager,
)
from pyarchimate_mcp_server.tools import model_tools, view_tools
from tests.test_model_manager import _build_rich_fixture_model

SVG_NS = "{http://www.w3.org/2000/svg}"


def _laid_out_fixture(monkeypatch):
    """Rich fixture model, laid out, wired into the view tools module."""
    manager = _build_rich_fixture_model()
    manager.auto_layout_all_views()
    monkeypatch.setattr(view_tools, "_model_manager", lambda: manager)
    return manager


def _view_nodes(container):
    """Yield every visual node in a view, including nested group members."""
    for node in container.nodes:
        yield node
        yield from _view_nodes(node)


def _geometry_snapshot(model):
    return [
        (view.uuid, node.uuid, node.x, node.y, node.w, node.h)
        for view in model.views
        for node in _view_nodes(view)
    ]


def _connection_snapshot(model):
    return [
        (
            view.uuid,
            connection.uuid,
            tuple((point.x, point.y) for point in connection.bendpoints),
        )
        for view in model.views
        for connection in view.conns
    ]


def _svg_root(path):
    return etree.fromstring(path.read_bytes())


def test_render_view_to_svg_file_writes_file_and_returns_path(tmp_path, monkeypatch):
    manager = _laid_out_fixture(monkeypatch)
    view = manager.list_views()[0]
    # Nested directory: parents must be created like export_model_to_file does.
    target = tmp_path / "diagrams" / "overview.svg"

    response = asyncio.run(view_tools.render_view_to_svg_file(view.uuid, str(target)))

    assert response["status"] == "success"
    data = response["data"]
    assert data["path"] == str(target)
    assert data["view_id"] == view.uuid
    assert data["view_name"] == "Overview"
    assert data["model_name"] == "Fixture Model"
    assert target.exists()
    assert data["bytes_written"] == target.stat().st_size
    assert data["node_count"] == len(list(_view_nodes(view)))
    assert data["connection_count"] == len(view.conns)
    assert data["width"] > 0
    assert data["height"] > 0


def test_render_view_to_svg_file_never_returns_markup_inline(tmp_path, monkeypatch):
    manager = _laid_out_fixture(monkeypatch)
    view = manager.list_views()[0]
    target = tmp_path / "overview.svg"

    response = asyncio.run(view_tools.render_view_to_svg_file(view.uuid, str(target)))

    # The markup goes to disk...
    assert "<svg" in target.read_text(encoding="utf-8")
    # ...and never into the envelope: SVG is thousands of tokens of text an
    # agent cannot see anyway.
    assert all(
        "<" not in value
        for value in response["data"].values()
        if isinstance(value, str)
    )
    assert not {"content", "svg", "markup"} & set(response["data"])


def test_svg_is_not_a_model_export_format(tmp_path, monkeypatch):
    manager = ArchimateModelManager()
    manager.create_new_model("Format Guard")
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)

    assert "svg" not in SUPPORTED_FORMATS

    guard_path = tmp_path / "guard.svg"
    for response in (
        asyncio.run(model_tools.export_model_content("svg")),
        asyncio.run(model_tools.export_model_to_file(str(guard_path), "svg")),
    ):
        assert response["status"] == "error"
        assert response["error"]["code"] == "UnsupportedFormatError"


def test_render_view_to_svg_file_reports_unknown_view_id(tmp_path, monkeypatch):
    _laid_out_fixture(monkeypatch)
    target = tmp_path / "missing.svg"

    response = asyncio.run(view_tools.render_view_to_svg_file("id-nope", str(target)))

    assert response["status"] == "error"
    assert response["error"]["code"] == "ViewNotFoundError"
    assert "id-nope" in response["message"]
    assert not target.exists()


def test_render_view_to_svg_file_requires_loaded_model(tmp_path, monkeypatch):
    empty_manager = ArchimateModelManager()
    monkeypatch.setattr(view_tools, "_model_manager", lambda: empty_manager)
    target = tmp_path / "no-model.svg"

    response = asyncio.run(view_tools.render_view_to_svg_file("id-any", str(target)))

    assert response["status"] == "error"
    assert response["error"]["code"] == "ModelNotFoundError"
    assert not target.exists()


def test_render_view_to_svg_file_rejects_blank_path(monkeypatch):
    manager = _laid_out_fixture(monkeypatch)
    view = manager.list_views()[0]

    response = asyncio.run(view_tools.render_view_to_svg_file(view.uuid, "   "))

    assert response["status"] == "error"
    assert response["error"]["code"] == "ModelOperationError"


def test_render_view_to_svg_file_leaves_the_model_untouched(tmp_path, monkeypatch):
    manager = _laid_out_fixture(monkeypatch)
    model = manager.get_active_model()
    view = manager.list_views()[0]
    info_before = manager.get_model_info()
    geometry_before = _geometry_snapshot(model)
    connections_before = _connection_snapshot(model)

    response = asyncio.run(
        view_tools.render_view_to_svg_file(view.uuid, str(tmp_path / "overview.svg")),
    )

    assert response["status"] == "success"
    # Element/relationship/view counts, every node coordinate and size, and
    # every routed bendpoint survive the render untouched. Rendering must
    # never trigger a layout pass as a side effect.
    assert manager.get_model_info() == info_before
    assert _geometry_snapshot(model) == geometry_before
    assert _connection_snapshot(model) == connections_before


def test_rendered_svg_is_well_formed_and_labels_every_element_node(
    tmp_path,
    monkeypatch,
):
    manager = _laid_out_fixture(monkeypatch)
    view = manager.list_views()[0]
    target = tmp_path / "overview.svg"

    asyncio.run(view_tools.render_view_to_svg_file(view.uuid, str(target)))

    root = _svg_root(target)
    assert root.tag == f"{SVG_NS}svg"
    labels = {text.text for text in root.iter(f"{SVG_NS}text") if text.text}

    element_nodes = [node for node in _view_nodes(view) if node.ref is not None]
    # ArchiMate notation draws junctions as bare circles, so pyArchimate's
    # renderer emits no text for them (Archi behaves the same way).
    junctions = [
        node for node in element_nodes if node.concept.type.endswith("Junction")
    ]
    assert junctions, "fixture should exercise the unlabelled junction case"

    named_nodes = [node for node in element_nodes if node not in junctions]
    assert {node.name for node in named_nodes} == {
        "Customer",
        "Checkout",
        "Sales Service",
        "Commerce Domain",
        "Portal",
        "Cart API",
        "Order",
        "Cluster",
        "Market",
        "Growth",
    }
    assert {node.name for node in named_nodes} <= labels

    # The server's own layer bands and relationship labels reach the render.
    assert {"Motivation", "Business", "Application", "Technology & Physical"} <= labels
    assert "Influence (++)" in labels


def test_rendered_svg_carries_layout_engine_bendpoints(tmp_path, monkeypatch):
    manager = _laid_out_fixture(monkeypatch)
    view = manager.list_views()[0]
    target = tmp_path / "overview.svg"

    asyncio.run(view_tools.render_view_to_svg_file(view.uuid, str(target)))

    bendpoints = {
        (float(point.x), float(point.y))
        for connection in view.conns
        for point in connection.bendpoints
    }
    assert bendpoints, "obstacle-map routing should bend some connections"

    intermediate_vertices = set()
    for polyline in _svg_root(target).iter(f"{SVG_NS}polyline"):
        vertices = polyline.get("points").split()
        for vertex in vertices[1:-1]:
            x, y = vertex.split(",")
            intermediate_vertices.add((float(x), float(y)))

    assert bendpoints <= intermediate_vertices


def _annotated_view_fixture(monkeypatch):
    """Two connected elements in one view, wired into the view tools module."""
    manager = ArchimateModelManager()
    manager.create_new_model("Note Tool Test")
    actor = manager.add_archimate_element("Customer", "BusinessActor")
    process = manager.add_archimate_element("Handle Payment", "BusinessProcess")
    relationship = manager.add_archimate_relationship(
        actor.uuid,
        process.uuid,
        "Triggering",
    )
    view = manager.create_view("Payment Overview")
    actor_node = manager.add_node_to_view(view.uuid, actor.uuid)
    manager.add_node_to_view(view.uuid, process.uuid)
    manager.add_connection_to_view(view.uuid, relationship.uuid)
    monkeypatch.setattr(view_tools, "_model_manager", lambda: manager)
    return manager, view, actor_node


def test_add_note_to_view_tool_returns_the_note_node_id(monkeypatch):
    _manager, view, actor_node = _annotated_view_fixture(monkeypatch)

    response = asyncio.run(
        view_tools.add_note_to_view(
            view.uuid,
            "Owned by the payments squad",
            x=600,
            y=40,
            connect_to_node_ids=[actor_node.uuid],
        ),
    )

    assert response["status"] == "success"
    data = response["data"]
    note = next(node for node in _view_nodes(view) if node.uuid == data["node_id"])
    assert note.cat == "Label"
    assert note.label == "Owned by the payments squad"
    assert len(data["connection_ids"]) == 1
    assert data["connected_node_ids"] == [actor_node.uuid]
    assert (data["x"], data["y"]) == (600, 40)
    # Pin the defaults themselves, not data against the node it came from:
    # comparing the response to note.w/note.h can never fail and leaves the
    # tool's size forwarding unverified.
    assert (data["width"], data["height"]) == (
        DEFAULT_NOTE_WIDTH,
        DEFAULT_NOTE_HEIGHT,
    )
    assert (note.w, note.h) == (DEFAULT_NOTE_WIDTH, DEFAULT_NOTE_HEIGHT)


def test_add_note_to_view_tool_forwards_an_explicit_size(monkeypatch):
    """An explicit width/height must reach the note, not the defaults."""
    _manager, view, _actor_node = _annotated_view_fixture(monkeypatch)

    response = asyncio.run(
        view_tools.add_note_to_view(
            view.uuid,
            "A wide caveat",
            x=700,
            y=120,
            width=320,
            height=140,
        ),
    )

    assert response["status"] == "success"
    data = response["data"]
    note = next(node for node in _view_nodes(view) if node.uuid == data["node_id"])
    assert (data["width"], data["height"]) == (320, 140)
    assert (note.w, note.h) == (320, 140)
    assert (note.w, note.h) != (DEFAULT_NOTE_WIDTH, DEFAULT_NOTE_HEIGHT)


def test_add_note_to_view_tool_rejects_blank_text(monkeypatch):
    _manager, view, _actor_node = _annotated_view_fixture(monkeypatch)

    response = asyncio.run(view_tools.add_note_to_view(view.uuid, "   ", x=0, y=0))

    assert response["status"] == "error"
    assert response["error"]["code"] == "INVALID_NOTE_TEXT"
    assert [node for node in _view_nodes(view) if node.cat == "Label"] == []


def test_add_note_to_view_tool_reports_unknown_connect_targets(monkeypatch):
    _manager, view, actor_node = _annotated_view_fixture(monkeypatch)

    response = asyncio.run(
        view_tools.add_note_to_view(
            view.uuid,
            "Points at a ghost",
            x=0,
            y=400,
            connect_to_node_ids=[actor_node.uuid, "id-ghost"],
        ),
    )

    assert response["status"] == "error"
    assert response["error"]["code"] == "ModelOperationError"
    assert response["error"]["details"]["unknown_ids"] == ["id-ghost"]
    assert [node for node in _view_nodes(view) if node.cat == "Label"] == []


def test_rendered_svg_includes_note_text(tmp_path, monkeypatch):
    _manager, view, actor_node = _annotated_view_fixture(monkeypatch)
    asyncio.run(
        view_tools.add_note_to_view(
            view.uuid,
            "Retire in FY27",
            x=600,
            y=40,
            connect_to_node_ids=[actor_node.uuid],
        ),
    )
    target = tmp_path / "annotated.svg"

    response = asyncio.run(view_tools.render_view_to_svg_file(view.uuid, str(target)))

    assert response["status"] == "success"
    labels = {
        text.text for text in _svg_root(target).iter(f"{SVG_NS}text") if text.text
    }
    assert "Retire in FY27" in labels


def _flat_engine_fixture(monkeypatch):
    """Flat view of default-sized nodes wired into the view tools module."""
    manager = ArchimateModelManager()
    manager.create_new_model("Engine Envelope Test")
    actor = manager.add_archimate_element("Customer", "BusinessActor")
    process = manager.add_archimate_element("Handle Payment", "BusinessProcess")
    component = manager.add_archimate_element("Payment Engine", "ApplicationComponent")
    manager.add_archimate_relationship(actor.uuid, process.uuid, "Triggering")
    manager.add_archimate_relationship(component.uuid, process.uuid, "Serving")
    view = manager.create_view("Payment Overview")
    for element in (actor, process, component):
        manager.add_node_to_view(view.uuid, element.uuid)
    manager.connect_visible_relationships(view.uuid)
    monkeypatch.setattr(view_tools, "_model_manager", lambda: manager)
    return manager, view


def test_auto_layout_view_tool_accepts_the_pyarchimate_engine(monkeypatch):
    _, view = _flat_engine_fixture(monkeypatch)

    response = asyncio.run(
        view_tools.auto_layout_view(view.uuid, layout_engine="pyarchimate"),
    )

    assert response["status"] == "success"
    nodes = response["data"]["nodes"]
    assert sorted((node["x"], node["y"]) for node in nodes) == [
        (20, 20),
        (20, 500),
        (260, 20),
    ]
    # No layer bands: every node still maps to a real element.
    assert all(node["element_id"] for node in nodes)


def test_auto_layout_view_tool_reports_engine_suggestions(monkeypatch):
    _, view = _flat_engine_fixture(monkeypatch)

    response = asyncio.run(
        view_tools.auto_layout_view(view.uuid, layout_engine="pyarchmate"),
    )

    assert response["status"] == "error"
    assert response["error"]["code"] == "ModelOperationError"
    assert response["error"]["details"]["suggestions"] == ["pyarchimate"]
    assert "Supported engines: internal, pyarchimate" in response["message"]


def test_auto_layout_view_tool_surfaces_the_suitability_guard(monkeypatch):
    manager, _ = _flat_engine_fixture(monkeypatch)
    wide = manager.add_archimate_element("Wide Platform", "Node")
    view = manager.create_view("Wide View")
    manager.add_node_to_view(view.uuid, wide.uuid, width=400, height=90)

    response = asyncio.run(
        view_tools.auto_layout_view(view.uuid, layout_engine="pyarchimate"),
    )

    assert response["status"] == "error"
    assert response["error"]["code"] == "ModelOperationError"
    details = response["error"]["details"]
    assert details["grid_size"] > 0
    assert details["remedy"] == "internal"
    assert [node["element_name"] for node in details["oversized_nodes"]] == [
        "Wide Platform",
    ]


def test_export_tools_reject_a_bad_engine_even_without_auto_layout(monkeypatch):
    manager, _ = _flat_engine_fixture(monkeypatch)
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)

    response = asyncio.run(
        model_tools.export_model_content(auto_layout=False, layout_engine="nonsense"),
    )

    assert response["status"] == "error"
    assert response["error"]["code"] == "ModelOperationError"
    assert "Unsupported layout engine" in response["message"]


def test_export_tools_apply_the_pyarchimate_engine_to_every_view(monkeypatch):
    manager, view = _flat_engine_fixture(monkeypatch)
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)

    response = asyncio.run(
        model_tools.export_model_content(
            auto_layout=True,
            layout_engine="pyarchimate",
        ),
    )

    assert response["status"] == "success"
    assert response["data"]["layout_engine"] == "pyarchimate"
    assert sorted((node.x, node.y) for node in view.nodes) == [
        (20, 20),
        (20, 500),
        (260, 20),
    ]


def test_export_model_to_file_applies_the_pyarchimate_engine(tmp_path, monkeypatch):
    manager, view = _flat_engine_fixture(monkeypatch)
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)
    target = tmp_path / "payments.archimate"

    response = asyncio.run(
        model_tools.export_model_to_file(
            str(target),
            auto_layout=True,
            layout_engine="pyarchimate",
        ),
    )

    assert response["status"] == "success"
    assert response["data"]["layout_engine"] == "pyarchimate"
    assert target.exists()
    assert sorted((node.x, node.y) for node in view.nodes) == [
        (20, 20),
        (20, 500),
        (260, 20),
    ]
    # The engine is a per-call choice: it must not reach the written file.
    assert "pyarchimate" not in target.read_text(encoding="utf-8").lower()

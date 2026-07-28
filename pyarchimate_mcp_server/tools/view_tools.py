"""MCP tools for ArchiMate view operations."""

from typing import Any

from pyarchimate_mcp_server.exceptions import ArchiMateMCPError
from pyarchimate_mcp_server.mcp_app import (
    ADDITIVE_TOOL,
    DESTRUCTIVE_TOOL,
    IDEMPOTENT_TOOL,
    mcp,
)
from pyarchimate_mcp_server.mcp_app import get_model_manager as _model_manager
from pyarchimate_mcp_server.model_manager import (
    DEFAULT_NODE_HEIGHT,
    DEFAULT_NODE_WIDTH,
    DEFAULT_NOTE_HEIGHT,
    DEFAULT_NOTE_WIDTH,
)
from pyarchimate_mcp_server.responses import error_response, success_response


@mcp.tool(annotations=ADDITIVE_TOOL)
async def create_view(  # noqa: PLR0913, PLR0917
    name: str,
    view_id: str | None = None,
    folder_path: str | None = None,
    description: str | None = None,
    properties: dict[str, Any] | None = None,
    viewpoint: str | None = None,
) -> dict[str, Any]:
    """Create a new ArchiMate view (diagram) in the active model.

    Views are containers for visual nodes and connections. Add nodes
    with `add_node_to_view` and connections with
    `add_connection_to_view` once both endpoint elements are visible.
    Set a `viewpoint` so the view opens with the right Archi viewpoint
    (e.g. `layered` for mixed-layer overviews, `capability` for
    capability maps, `service_realization` for service views). Take the
    value from `list_supported_types` (`data.viewpoints`) rather than
    inferring it from the viewpoint's English name — a plausible
    `business_process` is not accepted, `business_process_cooperation`
    is.

    Args:
        name: View name. Must be a non-empty string.
        view_id: Optional stable view ID. When omitted a UUID is
            generated. Must be unique across the
            *entire* active model — not just within this call, this
            batch, or this concept type. An id already used by any
            element, relationship, view, node or connection is
            rejected. When generating ids across several batches,
            namespace them (`bp-`, `ac-`, `tech-`) so batches cannot
            collide.
        folder_path: Optional folder path. The `Views` root is
            normalized: `Views`, `/Views`, and `views` resolve to
            `/Views`.
        viewpoint: Optional viewpoint: any canonical Archi viewpoint id
            (e.g. `layered`, `application_cooperation`) or pyArchimate
            slug. Both catalogs are in `list_supported_types` under
            `data.viewpoints`. Invalid values are rejected before the
            view is created — nothing is left behind, so the same
            `view_id` can be reused on the retry — and the error
            carries both accepted catalogs in `error.details`.

    Returns:
        Success envelope with `data` shaped like a `ViewDetail`:
        `{id, name, nodes: [], connections: []}`.

    Errors:
        `INVALID_VIEW_NAME` when `name` is missing or blank.
        `ModelNotFoundError` if no model is active.
        `ModelOperationError` for a duplicate `view_id`, an unknown
        `viewpoint`, or an invalid folder path.
    """
    if not isinstance(name, str) or not name.strip():
        return error_response("Invalid view name.", "INVALID_VIEW_NAME")

    merged_properties = dict(properties or {})
    if viewpoint is not None:
        merged_properties["viewpoint"] = viewpoint
    try:
        model_manager = _model_manager()
        view = model_manager.create_view(
            name.strip(),
            view_id=view_id,
            folder_path=folder_path,
            description=description,
            properties=merged_properties or None,
        )
        return success_response(
            model_manager.map_view_to_detail(view).model_dump(),
            "View created.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=IDEMPOTENT_TOOL)
async def update_view(
    view_id: str,
    updates: dict[str, Any],
    viewpoint: str | None = None,
) -> dict[str, Any]:
    """Update an existing ArchiMate view.

    Only metadata fields can be updated; nodes and connections are
    managed by `add_node_to_view`, `add_connection_to_view`, and the
    layout tools.

    Args:
        view_id: ID of the view to update.
        updates: Mapping of fields to update. Supported keys:
            - `name` (str): New view name.
            - `description` (str): New documentation text.
            - `properties` (dict[str, str]): Property updates merged
              into existing properties.
        viewpoint: Optional viewpoint, as on `create_view`. Validated
            before anything is applied: an unknown value leaves the
            view completely untouched, `name` and `description`
            included.

    Returns:
        Success envelope with the updated `ViewDetail` in `data`.

    Errors:
        `ViewNotFoundError` when `view_id` is unknown.
        `ModelOperationError` for an unknown `viewpoint`, with both
        accepted catalogs in `error.details`.
    """
    try:
        merged_properties = dict(updates.get("properties") or {})
        if viewpoint is not None:
            merged_properties["viewpoint"] = viewpoint
        model_manager = _model_manager()
        success = model_manager.update_view(
            view_id=view_id,
            name=updates.get("name"),
            description=updates.get("description"),
            properties=merged_properties or None,
        )
        if not success:
            return error_response(
                f"View with ID '{view_id}' not found.",
                "ViewNotFoundError",
            )
        view = model_manager.get_view_by_id(view_id)
        return success_response(
            model_manager.map_view_to_detail(view).model_dump(),
            "View updated.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=DESTRUCTIVE_TOOL)
async def delete_view(view_id: str) -> dict[str, Any]:
    """Delete an ArchiMate view from the active model.

    Removes the view and its visual nodes/connections. Underlying
    elements and relationships are NOT removed.

    Args:
        view_id: ID of the view to delete.

    Returns:
        Success envelope with `data.deleted=true`.

    Errors:
        `ViewNotFoundError` when `view_id` is unknown.
    """
    try:
        success = _model_manager().delete_view(view_id)
        if not success:
            return error_response(
                f"View with ID '{view_id}' not found.",
                "ViewNotFoundError",
            )
        return success_response({"deleted": True}, "View deleted.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=ADDITIVE_TOOL)
async def add_node_to_view(  # noqa: PLR0913, PLR0917
    view_id: str,
    element_id: str,
    x: int | None = None,
    y: int | None = None,
    width: int = DEFAULT_NODE_WIDTH,
    height: int = DEFAULT_NODE_HEIGHT,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Add an ArchiMate element as a visual node in a view.

    If `x`/`y` are omitted, or the requested rectangle would overlap an
    existing node, the server places the node in the next free slot.
    Default node size is 160x80 (junctions are normalized to 32x32 by
    `auto_layout_view`).

    Args:
        view_id: ID of the target view.
        element_id: ID of the element to render in the view.
        x: Optional preferred X coordinate (top-left, integer pixels).
        y: Optional preferred Y coordinate (top-left, integer pixels).
        width: Node width in pixels. Defaults to 160.
        height: Node height in pixels. Defaults to 80.
        node_id: Optional stable visual node ID. When omitted a UUID is
            generated. Must be unique across the
            *entire* active model — not just within this call, this
            batch, or this concept type. An id already used by any
            element, relationship, view, node or connection is
            rejected. When generating ids across several batches,
            namespace them (`bp-`, `ac-`, `tech-`) so batches cannot
            collide.

    Returns:
        Success envelope with `data.node_id` containing the visual
        node's UUID.

    Errors:
        `ViewNotFoundError` (returned as `ModelOperationError` from the
            manager) when `view_id` is unknown.
        `ElementNotFoundError` when `element_id` is unknown.
        `ModelOperationError` for a duplicate `node_id`.
    """
    try:
        model_manager = _model_manager()
        node = model_manager.add_node_to_view(
            view_id,
            element_id,
            x,
            y,
            width,
            height,
            node_id,
        )
        return success_response({"node_id": node.uuid}, "Node added.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=ADDITIVE_TOOL)
async def add_note_to_view(  # noqa: PLR0913, PLR0917
    view_id: str,
    text: str,
    x: int,
    y: int,
    width: int = DEFAULT_NOTE_WIDTH,
    height: int = DEFAULT_NOTE_HEIGHT,
    connect_to_node_ids: list[str] | None = None,
    note_id: str | None = None,
) -> dict[str, Any]:
    """Add a diagram-only note (sticky annotation) to a view.

    Use this to comment on a diagram — a caveat, an owner, a "retire in
    FY27". Do NOT create a `Grouping` element just to write a comment:
    that pollutes the model tree and participates in validation, while a
    note does not.

    Notes are visual only. A note has no ArchiMate element, no folder
    and no model-tree entry, so it never shows up in `query_elements`,
    `count_by_type`, `list_orphan_elements` or the coverage section of
    `build_quality_report`. `connect_to_node_ids` draws annotation-only
    connector lines that create NO ArchiMate relationship.

    `x`/`y` are kept exactly as given, including across
    `auto_layout_view` (both layout engines), because a note annotates
    one specific spot. Layout will not move element nodes out from under
    a note, so place notes in free space — off to the side of the
    diagram, or below it. Routed connections are drawn around notes.

    Args:
        view_id: ID of the target view.
        text: Note text. Must be non-empty; kept verbatim, so multi-line
            text keeps its line breaks and indentation. Verbatim also
            means escape sequences are NOT interpreted: pass real line
            breaks for a multi-line note, because a literal backslash-n
            is stored and rendered as those two characters.
        x: X coordinate (top-left, integer pixels). Used exactly.
        y: Y coordinate (top-left, integer pixels). Used exactly.
        width: Note width in pixels. Defaults to 185 (Archi's default).
        height: Note height in pixels. Defaults to 80.
        connect_to_node_ids: Optional list of things to point at. Each
            entry may be a visual node ID or an element ID that is
            already visible in this view.
        note_id: Optional stable visual node ID. When omitted a UUID is
            generated. Must be unique across the
            *entire* active model — not just within this call, this
            batch, or this concept type. An id already used by any
            element, relationship, view, node or connection is
            rejected. When generating ids across several batches,
            namespace them (`bp-`, `ac-`, `tech-`) so batches cannot
            collide.

    Returns:
        Success envelope with `data.node_id`, `data.connection_ids`,
        `data.connected_node_ids` (resolved visual node IDs),
        `data.text`, and the geometry `data.x`, `data.y`,
        `data.width`, `data.height`.

    Errors:
        `INVALID_NOTE_TEXT` when `text` is missing or blank.
        `ViewNotFoundError` when `view_id` is unknown.
        `ModelOperationError` for a duplicate `note_id`, or for connect
            targets that are not visible in the view — the unresolved
            IDs are listed in `error.details.unknown_ids` and nothing is
            created.

    Notes are not updatable or deletable yet: recreate the view (or the
    note) if the text or placement needs to change.
    """
    if not isinstance(text, str) or not text.strip():
        return error_response(
            "Note text must be a non-empty string.", "INVALID_NOTE_TEXT"
        )

    try:
        return success_response(
            _model_manager().add_note_to_view(
                view_id,
                text,
                x,
                y,
                width,
                height,
                connect_to_node_ids,
                note_id,
            ),
            "Note added.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=ADDITIVE_TOOL)
async def add_nodes_to_view(
    view_id: str,
    nodes: list[dict[str, Any]],
    *,
    rollback_on_error: bool = True,
) -> dict[str, Any]:
    """Add multiple visual nodes to a view in one call.

    Each node item supports the same fields as `add_node_to_view`. Both
    short and long field names are accepted (`element` or `element_id`,
    `id` or `node_id`).

    Node item shape:
        ```
        {
          "id": "id-customer-node",   # optional stable ref
          "element": "id-customer",   # required (alias: element_id)
          "x": 40, "y": 40,            # optional, auto-placed if absent
          "width": 160, "height": 80   # optional, defaults shown
        }
        ```

    Args:
        view_id: ID of the target view.
        nodes: List of node item objects.
        rollback_on_error: When true (default), restore the previous
            view state if any item fails.

    Returns:
        Success envelope with `data.node_ids`, `data.count`, and
        `data.rollback_on_error`.

    Errors:
        `ModelOperationError` (view not found / duplicate node_id) and
        `ElementNotFoundError` for the first failing item.
    """
    try:
        added_nodes = _model_manager().add_nodes_to_view(
            view_id,
            nodes,
            rollback_on_error=rollback_on_error,
        )
        return success_response(
            {
                "node_ids": [node.uuid for node in added_nodes],
                "count": len(added_nodes),
                "rollback_on_error": rollback_on_error,
            },
            "Nodes added.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=IDEMPOTENT_TOOL)
async def auto_layout_view(
    view_id: str,
    strategy: str = "layered_by_type",
    layout_engine: str = "internal",
    detail: str = "summary",
    *,
    layer_bands: bool = True,
) -> dict[str, Any]:
    """Automatically reposition all nodes in a view to avoid overlap.

    The default `internal` layout nests Aggregation/Composition members
    inside visible Grouping nodes, wraps wide lanes into multiple rows,
    aligns connected nodes vertically across lanes, and routes
    connections orthogonally around nodes. With `layer_bands` (default
    true) and the `layered_by_type` strategy, views spanning two or
    more ArchiMate layers get labeled visual bands (diagram-only Archi
    Groups — the semantic model is never modified; set
    `layer_bands=false` to disable).

    The engine choice applies to this call only. It is never stored on
    the model or the view, so it cannot appear in an export or in
    Archi's Properties tab.

    Note: parameter is `strategy` (matches `auto_layout_view`) but the
    equivalent parameter on `export_model_content` and
    `export_model_to_file` is named `layout_strategy`.

    Args:
        view_id: ID of the view to lay out.
        strategy: One of:
            - `layered_by_type` (default): ArchiMate semantic lanes
              (Motivation/Strategy on top, then Business, Application,
              Application Data, Technology/Physical/Implementation).
            - `layered`: relationship-direction layered, source nodes
              before target nodes.
            - `grid`: compact non-overlapping grid, no semantic
              ordering.
            Ignored (but still validated) by the `pyarchimate` engine,
            which has a single fixed algorithm.
        layout_engine: One of:
            - `internal` (default): everything described above.
            - `pyarchimate`: pyArchimate's own coarse-grid placement.
              Much faster on large views, but it applies no `strategy`,
              no layer bands, no lane wrapping, no barycenter
              alignment, and no ArchiMate lane ordering (its own layer
              classification misplaces SystemSoftware, Artifact, Path,
              Equipment, Facility, Material, Contract, Representation
              and ImplementationEvent). Best for flat views of
              default-sized nodes. It has no collision detection, so a
              view whose nodes do not fit its grid cell is refused
              rather than silently overlapped — see Errors.

    Returns:
        Success envelope with the laid-out view in `data`. Under
        `pyarchimate` the message says which options were not applied.

        `detail="summary"` (default) returns the view's identity,
        `properties`, `metadata`, `node_count`, `connection_count`, and
        a `bounds` box (`{x, y, width, height}`, or null for an empty
        view) giving the canvas the layout consumed — enough to place a
        note in free space afterwards.

        `detail="full"` adds `nodes` (each with x/y/width/height) and
        `connections`. Ask for it when you need per-node geometry; it
        is several thousand tokens on a mid-sized view.

        Both shapes report the band outcome directly:
        `layer_bands_created` (int) and `layer_bands_reason`, which is
        null when bands were created and otherwise one of
        `single_layer_view`, `coverage_view`, `not_requested`,
        `strategy_does_not_use_bands`, or
        `engine_does_not_support_bands`. Zero bands on a single-layer
        view is correct, not a failure.

    Errors:
        `ViewNotFoundError` (returned as `ModelOperationError`) when
            `view_id` is unknown.
        `ModelOperationError` for an unknown strategy, engine, or
            `detail` level, with close matches in
            `error.details.suggestions`.
        `ModelOperationError` when `layout_engine="pyarchimate"` cannot
            lay the view out safely, with `error.details.grid_size` and
            `error.details.oversized_nodes`. No placement is written, so
            the view is never left half laid out, but the shared
            prologue (Grouping nesting, group sizing) may already have
            repaired it. Retry with `layout_engine="internal"`.
    """
    try:
        model_manager = _model_manager()
        # Validated before the layout runs: a typo in `detail` should
        # not cost a full layout pass before it is reported.
        detail_level = model_manager.normalize_detail_level(detail)
        view_detail = model_manager.auto_layout_view(
            view_id=view_id,
            strategy=strategy,
            layout_engine=layout_engine,
            layer_bands=layer_bands,
        )
        message = "View layout updated."
        if layout_engine.lower() == "pyarchimate":
            message = (
                "View layout updated (engine: pyarchimate; strategy and "
                "layer bands not applied by this engine)."
            )
        payload = (
            view_detail.model_dump()
            if detail_level == "full"
            else view_detail.summary()
        )
        return success_response(payload, message)
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=IDEMPOTENT_TOOL)
async def render_view_to_svg_file(view_id: str, path: str) -> dict[str, Any]:
    """Render one view to an SVG file so a human can look at the diagram.

    Use this when someone wants to *see* a view without opening Archi —
    to check that a layout reads well, or to drop a picture into a
    document or chat. Lay the view out first with `auto_layout_view` if
    the geometry needs work: rendering never moves anything.

    SVG is a rendering, NOT a third model format. It cannot be imported
    back into Archi and it is not a substitute for
    `export_model_to_file` (`archi` = Archi native `.archimate`,
    `archimate` = Open Group exchange XML). Use those to persist a
    model; use this to look at one view.

    The markup is written to disk and never returned: an 11-element view
    is already ~3.2k tokens of SVG text, and reading it back would not
    tell you anything you cannot get from `summarize_view` or
    `build_quality_report`. Hand the returned path to the user.

    Args:
        view_id: ID of the view to render.
        path: Output path on the MCP server's filesystem (`.svg`
            conventionally). `~` is expanded, relative paths resolve
            against the server's CWD, and parent directories are
            created if missing.

    Returns:
        Success envelope with `data.path`, `data.view_id`,
        `data.view_name`, `data.model_name`, `data.bytes_written`,
        `data.node_count`, `data.connection_count`, and the rendered
        canvas size in `data.width` / `data.height`. Never the markup.

    Errors:
        `ModelNotFoundError` if no model is active.
        `ViewNotFoundError` when `view_id` is unknown.
        `ModelOperationError` for a blank path or a write failure.
    """
    try:
        return success_response(
            _model_manager().render_view_to_svg_file(view_id, path),
            "View rendered to SVG file.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=ADDITIVE_TOOL)
async def add_connection_to_view(
    view_id: str,
    relationship_id: str,
    connection_id: str | None = None,
) -> dict[str, Any]:
    """Add a visual connection for a relationship in a view.

    Both endpoint elements of the relationship must already be visible
    as nodes in the view. Use `add_node_to_view` to add missing
    endpoints first, or call `connect_visible_relationships` to draw
    every relationship whose endpoints are already visible.

    Args:
        view_id: ID of the target view.
        relationship_id: ID of the relationship to render.
        connection_id: Optional stable visual connection ID. When
            omitted a UUID is generated. Must be unique across the
            *entire* active model — not just within this call, this
            batch, or this concept type. An id already used by any
            element, relationship, view, node or connection is
            rejected. When generating ids across several batches,
            namespace them (`bp-`, `ac-`, `tech-`) so batches cannot
            collide.

    Returns:
        Success envelope with `data.connection_id` containing the
        visual connection UUID.

    Errors:
        `ModelOperationError` when `view_id` is unknown, when either
            endpoint node is not present in the view, or when
            `connection_id` is duplicated.
        `RelationshipNotFoundError` when `relationship_id` is unknown.
    """
    try:
        connection = _model_manager().add_connection_to_view(
            view_id,
            relationship_id,
            connection_id,
        )
        return success_response(
            {"connection_id": connection.uuid},
            "Connection added.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=ADDITIVE_TOOL)
async def add_connections_to_view(
    view_id: str,
    connections: list[dict[str, Any]],
    *,
    rollback_on_error: bool = True,
) -> dict[str, Any]:
    """Add multiple visual connections to a view in one call.

    Each connection item supports the same fields as
    `add_connection_to_view`. Both short and long field names are
    accepted (`relationship` or `relationship_id`, `id` or
    `connection_id`).

    Connection item shape:
        ```
        {
          "id": "id-uses-conn",          # optional stable ref
          "relationship": "id-uses"      # required (alias: relationship_id)
        }
        ```

    Args:
        view_id: ID of the target view.
        connections: List of connection item objects.
        rollback_on_error: When true (default), restore the previous
            view state if any item fails.

    Returns:
        Success envelope with `data.connection_ids`, `data.count`, and
        `data.rollback_on_error`.

    Errors:
        `ModelOperationError` and `RelationshipNotFoundError` for the
        first failing item.
    """
    try:
        added_connections = _model_manager().add_connections_to_view(
            view_id,
            connections,
            rollback_on_error=rollback_on_error,
        )
        return success_response(
            {
                "connection_ids": [connection.uuid for connection in added_connections],
                "count": len(added_connections),
                "rollback_on_error": rollback_on_error,
            },
            "Connections added.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=IDEMPOTENT_TOOL)
async def connect_visible_relationships(
    view_id: str,
    detail: str = "summary",
    *,
    rollback_on_error: bool = True,
) -> dict[str, Any]:
    """Add visual connections for every relationship whose endpoints are visible.

    Iterates over every relationship in the active model and, when both
    its source and target elements are already visible nodes in the
    view, adds the missing visual connection. Existing connections are
    skipped.

    Args:
        view_id: ID of the target view.
        detail: `summary` (default) or `full`. Every relationship that
            is not drawable in this view counts as a skip, so on a
            multi-view model the skip list is close to the whole
            relationship set and every entry is expected. `full` adds
            `data.skipped_relationship_ids`.
        rollback_on_error: When true (default), restore the previous
            view state if any connection fails.

    Returns:
        Success envelope with `data.connection_ids` (newly added),
        `data.added_count`, `data.skipped_count`, and `data.detail`.
        Under `full`, also `data.skipped_relationship_ids`.

    Errors:
        `ModelOperationError` when `view_id` is unknown, or for an
        unknown `detail` level.
    """
    try:
        return success_response(
            _model_manager().connect_visible_relationships(
                view_id,
                rollback_on_error=rollback_on_error,
                detail=detail,
            ),
            "Visible relationships connected.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=IDEMPOTENT_TOOL)
async def ensure_all_relationships_in_views(
    coverage_view_name: str = "Relationship Coverage",
    *,
    auto_layout: bool = True,
    layout_strategy: str = "layered_by_type",
    layout_engine: str = "internal",
    rollback_on_error: bool = True,
) -> dict[str, Any]:
    """Ensure every model relationship is rendered in at least one view.

    Useful when Archi Validator reports `Unused Relation` or
    `'Serving relation' is not used in a View`. The tool creates or
    reuses a coverage view, adds the missing endpoint nodes, and adds
    the missing connections. It also relocates redundant
    Grouping-to-contained-child Aggregation/Composition connections out
    of readable views into the coverage view (containment communicates
    the meaning visually instead).

    Coverage views are marked with the `mcp:relationship_coverage_view`
    property, so future invocations recognize them regardless of the
    display name.

    Args:
        coverage_view_name: Name of the coverage view. If a view with
            this name exists, it is reused; otherwise it is created.
        auto_layout: When true (default), lay out the affected views
            after adding nodes and connections.
        layout_strategy: Validated for consistency with other layout
            tools but not applied — the coverage view layout is a fixed
            source/target pair grid.
        layout_engine: Must be `internal` (the default). The coverage
            layout is a fixed pair grid, so no other engine can be
            honoured here and passing one is an error rather than a
            silently ignored hint.
        rollback_on_error: When true (default), restore the previous
            model state if coverage creation fails.

    Returns:
        Success envelope with `data` containing the coverage view ID,
        added node and connection counts, relocated containment
        connection counts, skipped relationship IDs, and remaining
        unused relationship IDs.

    Errors:
        `ModelNotFoundError` if no model is active.
        `ModelOperationError` for an unknown layout strategy/engine
            (with `error.details.suggestions`), or for any engine other
            than `internal`. Both are validated whether or not
            `auto_layout` is true.
    """
    try:
        return success_response(
            _model_manager().ensure_all_relationships_in_views(
                coverage_view_name=coverage_view_name,
                auto_layout=auto_layout,
                layout_strategy=layout_strategy,
                layout_engine=layout_engine,
                rollback_on_error=rollback_on_error,
            ),
            "Relationships rendered in views.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)

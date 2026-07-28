"""View layout for the ArchiMate MCP server.

Module-level layout functions extracted from ArchimateModelManager:
lane placement (`layered_by_type` semantic lanes with wrapping and
barycenter alignment, `layered`, `grid`), Grouping-member nesting and
legacy-duplicate healing, visual layer bands (diagram-only Archi
Groups), relationship label policy, and orthogonal connection routing
(pyArchimate ObstacleMap A* with clearance-aware anchors and a dogleg
fallback).

`layout_nodes_pyarchimate` is the opt-in alternative *placement*
engine, delegating to pyArchimate's own coarse-grid `auto_layout`. It
is only safe behind `oversized_nodes_for_pyarchimate`, which is why
that guard lives here next to it.

Functions operate on pyArchimate view/node/connection objects directly
and reach the model through `view.model` where needed; nothing here
imports from model_manager.
"""

import math
from collections import defaultdict
from itertools import pairwise
from typing import Any, cast

from pyArchimate.constants import ARCHI_CATEGORY
from pyArchimate.view import Point
from pyArchimate.view.layout import (
    LayoutConfig,
    ObstacleMap,
    Rectangle,
    RoutingConfig,
    auto_layout,
    displace_collinear_segments,
)

PyArchimateView = Any

DEFAULT_NODE_WIDTH = 160

DEFAULT_X_GAP = 80

DEFAULT_Y_GAP = 60

DEFAULT_LABEL_PADDING = 24

DEFAULT_LABEL_CHAR_WIDTH = 7

DEFAULT_LABEL_HEIGHT = 24

GROUP_PADDING_X = 40

GROUP_PADDING_TOP = 68

GROUP_PADDING_BOTTOM = 32

GROUP_CHILD_X_GAP = 80

GROUP_CHILD_Y_GAP = 52

DENSE_VIEW_CONNECTION_THRESHOLD = 60

DENSE_VIEW_MIN_CONNECTIONS_FOR_SIMPLIFIED_ROUTING = 36

DENSE_VIEW_CONNECTIONS_PER_NODE_THRESHOLD = 1.15

DENSE_VIEW_LABEL_THRESHOLD = 30

JUNCTION_NODE_SIZE = 32

# pyArchimate's node category for a diagram-only note (Archi's Note).
NOTE_NODE_CATEGORY = "Label"

# Layer bands ("Container") are decoration and must not deflect a route;
# notes are ink on the diagram and must be routed around like elements.
ROUTING_OBSTACLE_NODE_CATEGORIES = frozenset({"Element", NOTE_NODE_CATEGORY})

PRIMARY_FLOW_RELATIONSHIP_TYPES = {"Flow", "Triggering"}

PRIMARY_MOTIVATION_RELATIONSHIP_TYPES = {"Influence"}

SECONDARY_DENSE_RELATIONSHIP_LINE_COLOR = "#b8b8b8"

GROUP_CONTAINMENT_RELATIONSHIP_LINE_COLOR = "#d0d0d0"

DATA_ACCESS_ELEMENT_TYPES = {"BusinessObject", "DataObject"}

ROUTING_CANVAS_MARGIN = 200

MAX_LANE_WIDTH = 1600

LAYER_BAND_PROPERTY_KEY = "mcp:layer_bands"

# Why a requested set of layer bands was not produced. Reported as
# data rather than left to be inferred from a view property, which
# cannot distinguish "not applicable" from "failed".
LAYER_BAND_SKIP_SINGLE_LAYER = "single_layer_view"
LAYER_BAND_SKIP_COVERAGE_VIEW = "coverage_view"
LAYER_BAND_SKIP_NOT_REQUESTED = "not_requested"
LAYER_BAND_SKIP_STRATEGY = "strategy_does_not_use_bands"
LAYER_BAND_SKIP_ENGINE = "engine_does_not_support_bands"

LAYER_BAND_PADDING_X = 24

LAYER_BAND_PADDING_TOP = 36

LAYER_BAND_PADDING_BOTTOM = 20

LAYER_BAND_LABEL_BY_ROW_PREFIX = (
    ("Motivation", "Motivation"),
    ("Strategy", "Strategy"),
    ("Business", "Business"),
    ("Application", "Application"),
    ("Technology", "Technology & Physical"),
    ("Physical", "Technology & Physical"),
    ("Implementation", "Implementation & Migration"),
)

ROUTING_COARSE_CANVAS_SIZE = 2000

COVERAGE_VIEW_PROPERTY_KEY = "mcp:relationship_coverage_view"

COVERAGE_VIEW_PROPERTY_VALUE = "true"

# Gap used when pulling apart routed segments that share a corridor.
# Measured over 8/10/12/15/20px on a dense 45-node/50-connection view: 10px
# keeps the most displacements alive through the anchor and obstacle guards
# (a wider push is likelier to land on a node and be reverted) while still
# reading as two separate lines. pyArchimate's own RoutingConfig
# .min_segment_gap default of 20px leaves roughly twice the overlapping ink.
COLLINEAR_SEPARATION_GAP = 10.0

COLLINEAR_SEPARATION_MAX_PASSES = 4

MIN_PATHS_FOR_SEPARATION = 2

# A segment grazing a node border (an edge anchor legitimately does) is not
# a crossing; only the interior counts.
NODE_INTERIOR_INSET = 2.0

SEGMENT_AXIS_EPSILON = 0.5

# Bare layer names are fallback rows for types without a specific row
# mapping; they must sit adjacent to their layer's rows so foreign lanes
# never interleave inside another layer's vertical range.
ARCHIMATE_LAYOUT_ROW_ORDER = [
    "Motivation Stakeholders",
    "Motivation Outcomes",
    "Motivation Constraints",
    "Motivation",
    "Strategy Capabilities",
    "Strategy Resources",
    "Strategy",
    "Business Actors",
    "Business Journey",
    "Business Services",
    "Business Information",
    "Business",
    "Application Structure",
    "Application Behavior",
    "Application Data",
    "Application",
    "Technology Infrastructure",
    "Technology Services",
    "Technology Artifacts",
    "Technology",
    "Physical",
    "Implementation",
    "Implementation & Migration",
    "Grouping",
    "Other",
    "Junction",
]

ARCHIMATE_LAYOUT_ROW_BY_TYPE = {
    "Stakeholder": "Motivation Stakeholders",
    "Driver": "Motivation Stakeholders",
    "Assessment": "Motivation Stakeholders",
    "Goal": "Motivation Outcomes",
    "Outcome": "Motivation Outcomes",
    "Value": "Motivation Outcomes",
    "Meaning": "Motivation Outcomes",
    "Requirement": "Motivation Constraints",
    "Constraint": "Motivation Constraints",
    "Principle": "Motivation Constraints",
    "Capability": "Strategy Capabilities",
    "ValueStream": "Strategy Capabilities",
    "CourseOfAction": "Strategy Capabilities",
    "Resource": "Strategy Resources",
    "BusinessActor": "Business Actors",
    "BusinessRole": "Business Actors",
    "BusinessCollaboration": "Business Actors",
    "BusinessInterface": "Business Actors",
    "BusinessProcess": "Business Journey",
    "BusinessEvent": "Business Journey",
    "BusinessInteraction": "Business Journey",
    "BusinessFunction": "Business Services",
    "BusinessService": "Business Services",
    "Product": "Business Services",
    "BusinessObject": "Business Information",
    "Contract": "Business Information",
    "Representation": "Business Information",
    "ApplicationComponent": "Application Structure",
    "ApplicationCollaboration": "Application Structure",
    "ApplicationInterface": "Application Structure",
    "ApplicationProcess": "Application Behavior",
    "ApplicationFunction": "Application Behavior",
    "ApplicationInteraction": "Application Behavior",
    "ApplicationEvent": "Application Behavior",
    "ApplicationService": "Application Behavior",
    "DataObject": "Application Data",
    "Node": "Technology Infrastructure",
    "Device": "Technology Infrastructure",
    "SystemSoftware": "Technology Infrastructure",
    "CommunicationNetwork": "Technology Infrastructure",
    "Path": "Technology Infrastructure",
    "TechnologyCollaboration": "Technology Infrastructure",
    "TechnologyInterface": "Technology Infrastructure",
    "TechnologyService": "Technology Services",
    "TechnologyProcess": "Technology Services",
    "TechnologyFunction": "Technology Services",
    "TechnologyEvent": "Technology Services",
    "Artifact": "Technology Artifacts",
    "Facility": "Physical",
    "Equipment": "Physical",
    "Material": "Physical",
    "DistributionNetwork": "Physical",
    "Plateau": "Implementation",
    "Gap": "Implementation",
    "WorkPackage": "Implementation",
    "Deliverable": "Implementation",
    "ImplementationEvent": "Implementation",
    "Grouping": "Grouping",
    "AndJunction": "Junction",
    "OrJunction": "Junction",
    "Junction": "Junction",
}


def default_node_size_for_element(element: Any) -> tuple[int, int]:
    name = getattr(element, "name", "") or ""
    element_type = getattr(element, "type", "")
    if is_junction_type(element_type):
        return JUNCTION_NODE_SIZE, JUNCTION_NODE_SIZE
    width = min(320, max(DEFAULT_NODE_WIDTH, (len(name) * 7) + 72))
    height = 55 if element_type in {"DataObject", "BusinessObject"} else 60
    if element_type in {"Grouping", "Product", "Contract", "Representation"}:
        height = 70
    return width, height


def normalize_view_node_sizes(view: PyArchimateView) -> None:
    for node in view_nodes_recursive(view):
        concept = getattr(node, "concept", None)
        if is_junction_type(getattr(concept, "type", "")):
            node.w = min(node.w, JUNCTION_NODE_SIZE)
            node.h = min(node.h, JUNCTION_NODE_SIZE)


def is_junction_type(element_type: str | None) -> bool:
    return element_type in {"AndJunction", "OrJunction", "Junction"}


def is_note_node(node: Any) -> bool:
    """True for a diagram-only note node (Archi's Note)."""
    return getattr(node, "cat", "Element") == NOTE_NODE_CATEGORY


def is_routing_obstacle(node: Any) -> bool:
    """True for a node a routed connection must be drawn around."""
    return getattr(node, "cat", "Element") in ROUTING_OBSTACLE_NODE_CATEGORIES


def placeable_nodes(nodes: list[Any]) -> list[Any]:
    """Return the nodes a placement pass may move: everything but notes.

    A note annotates one specific thing on the diagram — a caveat on
    *that* component, an owner for *that* process — so relocating it
    destroys its meaning. Placement must never move one.
    """
    return [node for node in nodes if not is_note_node(node)]


def note_positions(
    view: PyArchimateView,
) -> dict[str, tuple[int, int, str | None]]:
    """Snapshot every note's pinned position before a placement pass.

    A top-level note is pinned in absolute view coordinates (parent id
    `None`), which is the only case `add_note_to_view` can produce. A
    note nested inside another node — only reachable by importing an
    Archi file where the user dropped a Note into a Group or Grouping —
    is pinned as an offset from that parent instead.

    The offset form is load-bearing, not a refinement. Node coordinates
    are absolute in memory, but Archi clips a child to its parent's
    rectangle, so holding a nested note at absolute coordinates while
    placement moves its parent away would render the note invisible.
    Pinning the offset keeps the note exactly where its author put it
    *relative to the thing it annotates*, which is what a note means.
    """
    positions: dict[str, tuple[int, int, str | None]] = {}
    for node in view_nodes_recursive(view):
        if not is_note_node(node):
            continue
        parent = getattr(node, "parent", None)
        if parent is None or parent is getattr(node, "view", None):
            positions[node.uuid] = (node.x, node.y, None)
        else:
            positions[node.uuid] = (
                node.x - parent.x,
                node.y - parent.y,
                getattr(parent, "uuid", None),
            )
    return positions


def restore_note_positions(
    view: PyArchimateView,
    positions: dict[str, tuple[int, int, str | None]],
) -> None:
    """Write pinned note positions back after a placement pass.

    A nested note is re-anchored against its parent's *final* position,
    so it travels with the node it annotates. If the parent recorded at
    capture time is no longer this note's parent the offset is
    meaningless, so the note is left where placement put it rather than
    being thrown to a coordinate derived from a stale anchor.
    """
    if not positions:
        return
    for node in view_nodes_recursive(view):
        position = positions.get(node.uuid)
        if position is None:
            continue
        x, y, parent_id = position
        if parent_id is None:
            node.x, node.y = x, y
            continue
        parent = getattr(node, "parent", None)
        if parent is not None and getattr(parent, "uuid", None) == parent_id:
            node.x, node.y = parent.x + x, parent.y + y


def view_nodes_recursive(view: PyArchimateView) -> list[Any]:
    nodes = []
    stack = list(reversed(view.nodes))
    while stack:
        node = stack.pop()
        nodes.append(node)
        stack.extend(reversed(node.nodes))
    return nodes


def node_parent_id(node: Any) -> str | None:
    parent = getattr(node, "parent", None)
    view = getattr(node, "view", None)
    if parent is None or parent is view:
        return None
    return getattr(parent, "uuid", None)


def nest_grouped_nodes(view: PyArchimateView) -> None:
    all_nodes = view_nodes_recursive(view)
    node_by_element_id = {node.ref: node for node in all_nodes if node.ref}
    group_nodes = [
        node for node in all_nodes if getattr(node.concept, "type", None) == "Grouping"
    ]
    for group_node in group_nodes:
        for member_node in group_member_nodes(
            group_node,
            node_by_element_id,
        ):
            if (
                member_node is group_node
                or is_ancestor(member_node, group_node)
                or node_parent_id(member_node) == group_node.uuid
            ):
                continue
            member_node.move(group_node)
    remove_redundant_ungrouped_member_nodes(view)


def remove_redundant_ungrouped_member_nodes(view: PyArchimateView) -> None:
    """Heal duplicate member nodes left behind by older layouts.

    Earlier releases duplicated group members: one copy nested in the
    Grouping node plus the original stray at top level. When an element
    has a node inside a Grouping AND further nodes outside any
    Grouping, the ungrouped strays are removed after re-pointing their
    connections at the surviving grouped node.
    """
    grouped_node_by_element: dict[str, Any] = {}
    for node in view_nodes_recursive(view):
        parent_concept = getattr(
            getattr(node, "parent", None),
            "concept",
            None,
        )
        if getattr(parent_concept, "type", None) == "Grouping" and node.ref:
            grouped_node_by_element.setdefault(node.ref, node)
    if not grouped_node_by_element:
        return
    strays = [
        node
        for node in view_nodes_recursive(view)
        if node.ref in grouped_node_by_element
        and node is not grouped_node_by_element[node.ref]
        and not has_grouping_ancestor(node)
    ]
    for stray in strays:
        survivor = grouped_node_by_element[stray.ref]
        for connection in list(view.conns):
            if connection.source is stray:
                connection.source = survivor
            if connection.target is stray:
                connection.target = survivor
        stray.delete(recurse=False)


def has_grouping_ancestor(node: Any) -> bool:
    parent = getattr(node, "parent", None)
    view = getattr(node, "view", None)
    while parent is not None and parent is not view:
        if getattr(getattr(parent, "concept", None), "type", None) == "Grouping":
            return True
        parent = getattr(parent, "parent", None)
    return False


def existing_group_child(group_node: Any, element_id: str) -> Any | None:
    return next((node for node in group_node.nodes if node.ref == element_id), None)


def group_has_connection_to_member(
    group_node: Any,
    member_node: Any,
    relationship_id: str,
) -> bool:
    return any(
        conn.ref == relationship_id
        and conn.source is not None
        and conn.target is not None
        and conn.source.uuid == group_node.uuid
        and conn.target.uuid == member_node.uuid
        for conn in group_node.view.conns
    )


def create_group_child_node(group_node: Any, member_element: Any) -> Any:
    width, height = default_node_size_for_element(member_element)
    return group_node.add(
        ref=member_element,
        x=group_node.x + GROUP_PADDING_X,
        y=group_node.y + GROUP_PADDING_TOP,
        w=width,
        h=height,
    )


def group_member_node(
    group_node: Any,
    node_by_element_id: dict[str, Any],
    member_element: Any,
) -> Any:
    existing_child = existing_group_child(group_node, member_element.uuid)
    if existing_child is not None:
        return existing_child
    member_node = node_by_element_id.get(member_element.uuid)
    if member_node is None:
        member_node = create_group_child_node(group_node, member_element)
        node_by_element_id[member_element.uuid] = member_node
    return member_node


def group_member_nodes(
    group_node: Any,
    node_by_element_id: dict[str, Any],
) -> list[Any]:
    model = group_node.view.model
    group_element_id = group_node.ref
    members = []
    for relationship in model.relationships:
        if relationship.type not in {"Aggregation", "Composition"}:
            continue
        if relationship.source.uuid != group_element_id:
            continue
        member_element = model.elems_dict.get(relationship.target.uuid)
        if member_element is None:
            continue
        member_node = group_member_node(
            group_node,
            node_by_element_id,
            member_element,
        )
        if not group_has_connection_to_member(
            group_node,
            member_node,
            relationship.uuid,
        ):
            group_node.view.add_connection(
                ref=relationship,
                source=group_node,
                target=member_node,
            )
        members.append(member_node)
    return sorted(members, key=lambda node: (node_sort_name(node), node.uuid))


def layer_band_label_for_node(node: Any) -> str | None:
    row_name = node_layout_row_name(node)
    for prefix, label in LAYER_BAND_LABEL_BY_ROW_PREFIX:
        if row_name.startswith(prefix):
            return label
    return None


def remove_layer_bands(view: PyArchimateView) -> None:
    """Delete bands created by a previous layout (children are kept)."""
    marker = view.prop(LAYER_BAND_PROPERTY_KEY)
    if not marker:
        return
    band_ids = {band_id for band_id in str(marker).split(",") if band_id}
    for node in list(view.nodes):
        if node.uuid in band_ids and getattr(node, "cat", "Element") == "Container":
            # recurse=False moves children back up to the view.
            node.delete(recurse=False)
    view.prop(LAYER_BAND_PROPERTY_KEY, "")


def add_layer_bands(view: PyArchimateView) -> dict[str, Any]:
    """Wrap each occupied ArchiMate layer in a labeled visual band.

    Bands are diagram-only Container nodes (Archi's visual Group):
    they never touch the semantic model. Band node ids are recorded
    in a view property so the next layout can remove them first.

    Returns `{"created": int, "reason": str | None}`. The reason is the
    caller's only way to tell "not applicable" from "failed": the view
    property alone cannot, because `remove_layer_bands` leaves it as an
    empty string on a view that used to have bands and no longer
    qualifies.
    """
    if is_coverage_view(view):
        return {"created": 0, "reason": LAYER_BAND_SKIP_COVERAGE_VIEW}
    nodes_by_label: dict[str, list[Any]] = defaultdict(list)
    for node in list(view.nodes):
        if getattr(node, "cat", "Element") != "Element":
            continue
        label = layer_band_label_for_node(node)
        if label:
            nodes_by_label[label].append(node)
    if len(nodes_by_label) < 2:  # noqa: PLR2004
        return {"created": 0, "reason": LAYER_BAND_SKIP_SINGLE_LAYER}
    band_ids = []
    for label, members in sorted(
        nodes_by_label.items(),
        key=lambda item: min(node.y for node in item[1]),
    ):
        min_x = min(node.x for node in members)
        min_y = min(node.y for node in members)
        max_x = max(node.x + node.w for node in members)
        max_y = max(node.y + node.h for node in members)
        band = view.add(
            node_type="Container",
            label=label,
            x=min_x - LAYER_BAND_PADDING_X,
            y=min_y - LAYER_BAND_PADDING_TOP,
            w=(max_x - min_x) + (2 * LAYER_BAND_PADDING_X),
            h=(max_y - min_y) + LAYER_BAND_PADDING_TOP + LAYER_BAND_PADDING_BOTTOM,
        )
        for node in members:
            node.move(band)
        band_ids.append(band.uuid)
    view.prop(LAYER_BAND_PROPERTY_KEY, ",".join(band_ids))
    return {"created": len(band_ids), "reason": None}


def layout_group_children_for_view(view: PyArchimateView) -> None:
    group_nodes = [
        node
        for node in view_nodes_recursive(view)
        if getattr(node.concept, "type", None) == "Grouping" and node.nodes
    ]
    for group_node in sorted(
        group_nodes,
        key=node_depth,
        reverse=True,
    ):
        layout_group_children(group_node)


def layout_group_children(group_node: Any) -> None:
    # A note nested in this group is neither lane-placed nor allowed to
    # influence the group's bounds. It is re-anchored to the group's
    # final position by `restore_note_positions`, so letting it into the
    # bounds computation here would size the group against a coordinate
    # that is about to be overwritten.
    children = placeable_nodes(list(group_node.nodes))
    if not children:
        return

    row_index_by_name = {
        row_name: index for index, row_name in enumerate(ARCHIMATE_LAYOUT_ROW_ORDER)
    }
    layout_nodes_in_lanes(
        group_node.view,
        children,
        row_by_node_id={
            node.uuid: row_index_by_name.get(
                node_layout_row_name(node),
                len(ARCHIMATE_LAYOUT_ROW_ORDER),
            )
            for node in children
        },
        rank_by_node_id=relationship_ranks(group_node.view, children),
        origin_x=group_node.x + GROUP_PADDING_X,
        origin_y=group_node.y + GROUP_PADDING_TOP,
        x_gap=GROUP_CHILD_X_GAP,
        y_gap=GROUP_CHILD_Y_GAP,
    )
    min_x = min(node.x for node in children)
    min_y = min(node.y for node in children)
    max_x = max(node.x + node.w for node in children)
    max_y = max(node.y + node.h for node in children)
    if min_x < group_node.x + GROUP_PADDING_X:
        group_node.x -= (group_node.x + GROUP_PADDING_X) - min_x
    if min_y < group_node.y + GROUP_PADDING_TOP:
        group_node.y -= (group_node.y + GROUP_PADDING_TOP) - min_y
    group_node.w = max(group_node.w, int(max_x - group_node.x + GROUP_PADDING_X))
    group_node.h = max(
        group_node.h,
        int(max_y - group_node.y + GROUP_PADDING_BOTTOM),
    )


def node_depth(node: Any) -> int:
    depth = 0
    parent = getattr(node, "parent", None)
    view = getattr(node, "view", None)
    while parent is not None and parent is not view:
        depth += 1
        parent = getattr(parent, "parent", None)
    return depth


def is_ancestor(node: Any, possible_child: Any) -> bool:
    parent = getattr(possible_child, "parent", None)
    view = getattr(possible_child, "view", None)
    while parent is not None and parent is not view:
        if parent is node:
            return True
        parent = getattr(parent, "parent", None)
    return False


def layout_nodes_grid(
    nodes: list[Any],
    margin_x: int,
    margin_y: int,
    x_gap: int,
    y_gap: int,
) -> None:
    if not nodes:
        return

    max_width = max(node.w for node in nodes)
    max_height = max(node.h for node in nodes)
    columns = ceil_sqrt(len(nodes))
    for index, node in enumerate(nodes):
        row_index = index // columns
        column_index = index % columns
        node.x = margin_x + (column_index * (max_width + x_gap))
        node.y = margin_y + (row_index * (max_height + y_gap))


def layout_nodes_layered(  # noqa: PLR0913, PLR0917
    view: PyArchimateView,
    nodes: list[Any],
    margin_x: int,
    margin_y: int,
    x_gap: int,
    y_gap: int,
) -> None:
    if not nodes:
        return

    rank_by_node_id = relationship_ranks(view, nodes)
    nodes_by_rank: dict[int, list[Any]] = {}
    for node in nodes:
        rank = rank_by_node_id.get(node.uuid, 0)
        nodes_by_rank.setdefault(rank, []).append(node)

    layout_grouped_nodes(nodes_by_rank, margin_x, margin_y, x_gap, y_gap)


def layout_nodes_by_type(  # noqa: PLR0913, PLR0917
    view: PyArchimateView,
    nodes: list[Any],
    margin_x: int,
    margin_y: int,
    x_gap: int,
    y_gap: int,
) -> None:
    if not nodes:
        return

    row_index_by_name = {
        row_name: index for index, row_name in enumerate(ARCHIMATE_LAYOUT_ROW_ORDER)
    }
    row_by_node_id = {
        node.uuid: row_index_by_name.get(
            node_layout_row_name(node),
            len(ARCHIMATE_LAYOUT_ROW_ORDER),
        )
        for node in nodes
    }
    rank_by_node_id = semantic_relationship_ranks(
        view,
        nodes,
        row_by_node_id,
    )
    layout_nodes_in_lanes(
        view,
        nodes,
        row_by_node_id=row_by_node_id,
        rank_by_node_id=rank_by_node_id,
        origin_x=margin_x,
        origin_y=margin_y,
        x_gap=max(x_gap, DEFAULT_X_GAP + 90),
        y_gap=max(y_gap, DEFAULT_Y_GAP),
    )


def pyarchimate_grid_size() -> float:
    """Return the upstream grid cell size, read at call time.

    Never hardcode 240 here. `assign_grid_cells` places nodes one
    `grid_size` apart without ever reading node width/height, so this
    value is the exact overlap budget the suitability guard checks
    against. Reading the dataclass keeps the guard correct if upstream
    retunes the default. (Upstream's own `auto_layout` docstring claims
    120 while the dataclass says 240.0 — the dataclass is the truth.)
    """
    return float(LayoutConfig().grid_size)


def node_subtree_bounds(node: Any) -> tuple[float, float, float, float]:
    """Return (x, y, width, height) covering a node and all descendants.

    An imported Archi view can carry a child node sticking outside its
    parent's rectangle, so the parent's own box understates how much
    canvas the subtree really occupies.
    """
    left = float(node.x)
    top = float(node.y)
    right = left + float(node.w)
    bottom = top + float(node.h)
    for child in node.nodes:
        child_x, child_y, child_w, child_h = node_subtree_bounds(child)
        left = min(left, child_x)
        top = min(top, child_y)
        right = max(right, child_x + child_w)
        bottom = max(bottom, child_y + child_h)
    return left, top, right - left, bottom - top


def oversized_nodes_for_pyarchimate(view: PyArchimateView) -> list[dict[str, Any]]:
    """Return top-level nodes whose subtree cannot fit an upstream grid cell.

    The upstream engine has no collision detection whatsoever: cells are
    unique and adjacent cells are exactly `grid_size` apart, so two
    nodes overlap if and only if some node is wider or taller than
    `grid_size`. That makes the check exact rather than heuristic — and
    cheap enough to run before any placement write.

    Notes are excluded, but NOT because upstream leaves them alone — it
    does place them, and `restore_note_positions` then discards that
    placement and writes the pinned coordinates back. So a note never
    occupies the grid cell upstream chose for it, and since
    `assign_grid_cells` never reads `w`/`h`, an oversized note cannot
    displace any other node either. Refusing a layout over a wide note
    would therefore be a false refusal naming the one node whose
    upstream placement is guaranteed to be thrown away.

    A pinned note may still visually overlap a placed element, but that
    is the caller's chosen coordinate, not a collision this guard exists
    to catch.
    """
    grid_size = pyarchimate_grid_size()
    oversized = []
    for node in view.nodes:
        if is_note_node(node):
            continue
        _, _, width, height = node_subtree_bounds(node)
        if width > grid_size or height > grid_size:
            concept = node.concept if node.ref else None
            oversized.append(
                {
                    "node_id": node.uuid,
                    "element_id": node.ref,
                    "element_name": getattr(concept, "name", None),
                    "width": width,
                    "height": height,
                },
            )
    return oversized


def layout_nodes_pyarchimate(view: PyArchimateView) -> None:
    """Place nodes with pyArchimate's own coarse-grid `auto_layout`.

    Placement only: upstream writes `node.x`/`node.y` and nothing else —
    it never resizes, never reparents, and never touches connection
    waypoints (`connections_processed` is a hardcoded 0). MCP routing
    therefore still runs afterwards, unchanged.

    Call the suitability guard before this: upstream reports
    `success=True, warnings=[]` even when it has stacked nodes on top of
    each other.

    Never run upstream placement *after* a routing pass. Because it
    preserves waypoints byte-for-byte, moving the nodes underneath them
    strands every bendpoint in empty canvas.
    """
    result = auto_layout(view, LayoutConfig())
    if not result.success:
        # Upstream swallows every exception into LayoutResult(success=False)
        # and never raises, so an unchecked call would hand back an
        # unlaid-out view as a success.
        detail = result.error_message or "unknown error"
        msg = f"pyArchimate auto_layout failed for view '{view.name}': {detail}"
        raise RuntimeError(msg)


def view_connection_density(view: PyArchimateView) -> float:
    node_count = max(1, len(view_nodes_recursive(view)))
    return len(view.conns) / node_count


def apply_relationship_label_policy(view: PyArchimateView) -> None:
    if not should_simplify_connection_labels(view):
        for connection in view.conns:
            connection.show_label = True
        return

    visible_relationship_types = {
        connection_relationship_type(connection) for connection in view.conns
    }
    if visible_relationship_types & PRIMARY_FLOW_RELATIONSHIP_TYPES:
        relationship_types_to_label = PRIMARY_FLOW_RELATIONSHIP_TYPES
    elif visible_relationship_types & PRIMARY_MOTIVATION_RELATIONSHIP_TYPES:
        relationship_types_to_label = PRIMARY_MOTIVATION_RELATIONSHIP_TYPES
    else:
        relationship_types_to_label = set()

    for connection in view.conns:
        relationship_type = connection_relationship_type(connection)
        if relationship_type is None:
            # Annotation-only connector: no relationship semantics to mute.
            continue
        is_primary = relationship_type in relationship_types_to_label
        connection.show_label = is_primary
        if not is_primary and connection.line_color is None:
            connection.line_color = SECONDARY_DENSE_RELATIONSHIP_LINE_COLOR


def apply_group_containment_connection_policy(
    view: PyArchimateView,
) -> None:
    for connection in view.conns:
        relationship_type = connection_relationship_type(connection)
        if relationship_type not in {"Aggregation", "Composition"}:
            continue
        source = connection.source
        target = connection.target
        if source is None or target is None:
            continue
        if getattr(source.concept, "type", None) != "Grouping":
            continue
        if not is_ancestor(source, target):
            continue
        connection.show_label = False
        if connection.line_color is None:
            connection.line_color = GROUP_CONTAINMENT_RELATIONSHIP_LINE_COLOR


def should_simplify_connection_labels(view: PyArchimateView) -> bool:
    return not is_coverage_view(view) and (
        should_simplify_connection_routing(view)
        or len(view.conns) >= DENSE_VIEW_LABEL_THRESHOLD
    )


def layout_nodes_in_lanes(  # noqa: PLR0913, PLR0917
    view: PyArchimateView,
    nodes: list[Any],
    row_by_node_id: dict[str, int],
    rank_by_node_id: dict[str, int],
    origin_x: int,
    origin_y: int,
    x_gap: int,
    y_gap: int,
    max_lane_width: int = MAX_LANE_WIDTH,
) -> None:
    nodes_by_row: dict[int, list[Any]] = defaultdict(list)
    for node in nodes:
        row = row_by_node_id.get(node.uuid, len(ARCHIMATE_LAYOUT_ROW_ORDER))
        nodes_by_row[row].append(node)

    neighbor_ids = connected_node_ids(view)
    placed_center_x: dict[str, float] = {}
    y_cursor = origin_y
    for row in sorted(nodes_by_row):
        barycenters = lane_barycenters(
            nodes_by_row[row],
            neighbor_ids,
            placed_center_x,
        )
        ordered = order_lane_nodes(
            nodes_by_row[row],
            rank_by_node_id,
            barycenters,
        )
        y_cursor = place_lane_with_wrapping(
            ordered,
            barycenters,
            origin_x=origin_x,
            lane_y=y_cursor,
            x_gap=x_gap,
            y_gap=y_gap,
            max_lane_width=max_lane_width,
        )
        for node in ordered:
            placed_center_x[node.uuid] = node.x + (node.w / 2)


def connected_node_ids(view: PyArchimateView) -> dict[str, set[str]]:
    """Map each view node id to the node ids it connects to."""
    neighbors: dict[str, set[str]] = defaultdict(set)
    for connection in getattr(view, "conns", []):
        source = connection.source
        target = connection.target
        if source is None or target is None:
            continue
        neighbors[source.uuid].add(target.uuid)
        neighbors[target.uuid].add(source.uuid)
    return neighbors


def lane_barycenters(
    lane_nodes: list[Any],
    neighbor_ids: dict[str, set[str]],
    placed_center_x: dict[str, float],
) -> dict[str, float]:
    """Mean x-center of each node's already-placed neighbors."""
    barycenters: dict[str, float] = {}
    for node in lane_nodes:
        neighbor_positions = [
            placed_center_x[neighbor_id]
            for neighbor_id in neighbor_ids.get(node.uuid, ())
            if neighbor_id in placed_center_x
        ]
        if neighbor_positions:
            barycenters[node.uuid] = sum(neighbor_positions) / len(
                neighbor_positions,
            )
    return barycenters


def order_lane_nodes(
    lane_nodes: list[Any],
    rank_by_node_id: dict[str, int],
    barycenters: dict[str, float],
) -> list[Any]:
    """Order a lane by barycenter of already-placed neighbors.

    Nodes connected to nodes in earlier lanes sort under the mean x of
    those neighbors so verticals stay short; unconnected nodes keep the
    semantic rank order and fill in afterwards.
    """

    def sort_key(node: Any) -> tuple[float, int, str, str]:
        return (
            barycenters.get(node.uuid, float("inf")),
            rank_by_node_id.get(node.uuid, 0),
            node_sort_name(node),
            node.uuid,
        )

    return sorted(lane_nodes, key=sort_key)


def place_lane_with_wrapping(  # noqa: PLR0913
    ordered: list[Any],
    barycenters: dict[str, float],
    *,
    origin_x: int,
    lane_y: int,
    x_gap: int,
    y_gap: int,
    max_lane_width: int,
) -> int:
    """Place one lane left-to-right, wrapping past max_lane_width.

    Nodes with a barycenter are pulled toward it (never left of the
    packing cursor) so connected nodes align vertically across lanes.
    Returns the y coordinate where the next lane starts.
    """
    x_cursor = origin_x
    sub_row_y = lane_y
    sub_row_height = 0
    intra_gap = max(DEFAULT_Y_GAP, y_gap // 2)
    for node in ordered:
        desired_center = barycenters.get(node.uuid)
        target_x = x_cursor
        if desired_center is not None:
            target_x = max(x_cursor, int(desired_center - (node.w / 2)))
        if x_cursor > origin_x and target_x + node.w > origin_x + max_lane_width:
            sub_row_y += sub_row_height + intra_gap
            sub_row_height = 0
            x_cursor = origin_x
            target_x = origin_x
            if desired_center is not None:
                target_x = max(
                    origin_x,
                    min(
                        int(desired_center - (node.w / 2)),
                        origin_x + max_lane_width - node.w,
                    ),
                )
        node.x = target_x
        node.y = sub_row_y
        x_cursor = target_x + node.w + x_gap
        sub_row_height = max(sub_row_height, node.h)
    return sub_row_y + sub_row_height + y_gap


def layout_grouped_nodes(
    nodes_by_group: dict[int, list[Any]],
    margin_x: int,
    margin_y: int,
    x_gap: int,
    y_gap: int,
) -> None:
    occupied_groups = sorted(nodes_by_group)
    max_width = max(
        node.w for group_nodes in nodes_by_group.values() for node in group_nodes
    )
    max_height = max(
        node.h for group_nodes in nodes_by_group.values() for node in group_nodes
    )

    for column_index, group in enumerate(occupied_groups):
        group_nodes = sorted(
            nodes_by_group[group],
            key=lambda node: (getattr(node.concept, "name", "") or "", node.uuid),
        )
        for row_index, node in enumerate(group_nodes):
            node.x = margin_x + (column_index * (max_width + x_gap))
            node.y = margin_y + (row_index * (max_height + y_gap))


def label_aware_gaps(
    view: PyArchimateView,
    nodes: list[Any],
    x_gap: int,
    y_gap: int,
) -> tuple[int, int]:
    node_ids = {node.uuid for node in nodes}
    label_sizes = [
        connection_label_size(connection)
        for connection in view.conns
        if connection.source is not None
        and connection.target is not None
        and connection.source.uuid in node_ids
        and connection.target.uuid in node_ids
        and connection_label_text(connection)
    ]
    if not label_sizes:
        return x_gap, y_gap

    max_label_width = max(width for width, _height in label_sizes)
    max_label_height = max(height for _width, height in label_sizes)
    return (
        max(x_gap, max_label_width + (2 * DEFAULT_LABEL_PADDING)),
        max(y_gap, max_label_height + (2 * DEFAULT_LABEL_PADDING)),
    )


def route_or_simplify_connections(view: PyArchimateView) -> None:
    for connection in view.conns:
        if hasattr(connection, "remove_all_bendpoints"):
            connection.remove_all_bendpoints()
    if should_simplify_connection_routing(view):
        # Dense views keep straight lines instead of adding bendpoints.
        return
    route_connections_around_nodes(view)


def route_connections_around_nodes(view: PyArchimateView) -> None:
    """Route connections orthogonally around nodes.

    Uses pyArchimate's ObstacleMap A* corridor search directly.
    The library's own auto_route() wrapper is unusable through
    1.12.0 (re-measured on 1.12.0, not inherited from the 1.11.x
    note this replaces): RoutingConfig.node_clearance is 25px and
    ObstacleMap inflates every node by it, while auto_route's own
    _spread_positions anchors paths at a hardcoded 13px outside the
    node edge. Every search therefore starts from a blocked cell and
    routes nothing. Pushing anchors past the clearance zone (done
    here) makes the search succeed; there is no upstream replacement
    to migrate to, so this anchoring is load-bearing.
    """
    nodes = view_nodes_recursive(view)
    if not nodes or not view.conns:
        return
    config = RoutingConfig()
    obstacles = [
        Rectangle(float(node.x), float(node.y), float(node.w), float(node.h))
        for node in nodes
        # Layer bands (Container) are decoration and are skipped; notes
        # (Label) are ink on the diagram, so a route drawn through one is
        # as unreadable as a route drawn through an element.
        if is_routing_obstacle(node)
    ]
    max_x = max(node.x + node.w for node in nodes) + ROUTING_CANVAS_MARGIN
    max_y = max(node.y + node.h for node in nodes) + ROUTING_CANVAS_MARGIN
    resolution = 10.0 if max(max_x, max_y) < ROUTING_COARSE_CANVAS_SIZE else 20.0
    obstacle_map = ObstacleMap(obstacles, resolution=resolution, config=config)
    obstacle_map._canvas_w = int(max_x / resolution) + 5  # noqa: SLF001
    obstacle_map._canvas_h = int(max_y / resolution) + 5  # noqa: SLF001
    clearance = config.node_clearance + resolution
    routed: list[tuple[Any, list[Point]]] = []
    for connection in sorted(view.conns, key=lambda conn: conn.uuid):
        path = route_single_connection(
            connection,
            obstacle_map,
            config,
            clearance,
        )
        if path is not None:
            routed.append((connection, path))
    # Routes are collected first: pulling apart connections that ended up
    # sharing a corridor needs every path at once.
    separated = separate_collinear_connection_segments(
        routed,
        obstacle_map,
        config,
        obstacles,
    )
    for (connection, _path), waypoints in zip(routed, separated, strict=True):
        for waypoint in waypoints:
            connection.add_bendpoint(Point(int(waypoint.x), int(waypoint.y)))


def route_single_connection(
    connection: Any,
    obstacle_map: Any,
    config: Any,
    clearance: float,
) -> list[Point] | None:
    """Return the orthogonal waypoints for one connection, or None.

    None means "leave it as a straight line": no route is possible or
    none is needed. Bendpoints are written by the caller, after the
    collinear-separation pass has seen every route.
    """
    source = connection.source
    target = connection.target
    if source is None or target is None:
        return None
    # Containment connections (group to nested member) stay straight.
    if is_ancestor(source, target) or is_ancestor(target, source):
        return None
    source_anchor = routing_anchor(source, target, clearance)
    target_anchor = routing_anchor(target, source, clearance)
    path = obstacle_map.find_corridor(
        source_anchor,
        target_anchor,
        config.crossing_penalty,
    )
    if path is None:
        # Corridor search failed (budget exhaustion on large canvases,
        # or blocked start/end cells). Fall back to an orthogonal
        # dogleg instead of a straight diagonal.
        path = dogleg_path(source, source_anchor, target_anchor)
        if path is None:
            return None
    if len(path) < 3:  # noqa: PLR2004
        return None  # already straight: keep the direct line
    for first, second in pairwise(path):
        obstacle_map.mark_routed_segment(first, second)
    # The anchors are turn points on the node centerlines, so keeping
    # the full path (anchors included) yields an orthogonal polyline
    # from edge to edge.
    return list(path)


def dogleg_path(
    source_node: Any,
    source_anchor: Point,
    target_anchor: Point,
) -> list[Point] | None:
    """Single-elbow orthogonal path between two anchors.

    Returns None when the anchors already share an axis (a straight
    segment is orthogonal by itself).
    """
    if (
        abs(source_anchor.x - target_anchor.x) < 1
        or abs(source_anchor.y - target_anchor.y) < 1
    ):
        return None
    source_cy = source_node.y + (source_node.h / 2)
    exits_horizontally = abs(source_anchor.y - source_cy) < 1
    if exits_horizontally:
        elbow = Point(target_anchor.x, source_anchor.y)
    else:
        elbow = Point(source_anchor.x, target_anchor.y)
    return [source_anchor, elbow, target_anchor]


def routing_anchor(node: Any, other: Any, clearance: float) -> Point:
    """Return the node edge-facing anchor pushed outside the clearance zone."""
    node_cx = node.x + (node.w / 2)
    node_cy = node.y + (node.h / 2)
    other_cx = other.x + (other.w / 2)
    other_cy = other.y + (other.h / 2)
    dx = other_cx - node_cx
    dy = other_cy - node_cy
    if abs(dx) * node.h >= abs(dy) * node.w:
        # Leave through the left/right edge.
        edge_x = node.x + node.w if dx >= 0 else node.x
        anchor_x = edge_x + clearance if dx >= 0 else edge_x - clearance
        return Point(anchor_x, node_cy)
    # Leave through the top/bottom edge.
    edge_y = node.y + node.h if dy >= 0 else node.y
    anchor_y = edge_y + clearance if dy >= 0 else edge_y - clearance
    return Point(node_cx, anchor_y)


def separate_collinear_connection_segments(
    routed: list[tuple[Any, list[Point]]],
    obstacle_map: Any,
    config: Any,
    obstacles: list[Any],
) -> list[list[Point]]:
    """Pull apart routed segments that ended up sharing a corridor.

    Delegates the spreading itself to pyArchimate's
    `displace_collinear_segments`, which is exactly the heavy-band
    problem, and then wraps it in the two guards it lacks:

    * anchors — this router writes the node anchors as the first and
      last waypoints, so an unguarded displacement slides them off the
      node centerline and the node-exit stub stops being axis-aligned
      (i.e. it trades line bands for diagonals). An offset touching an
      anchor survives only when it moves along that anchor's own stub
      axis and leaves it outside the node.
    * obstacles — the helper reasons about other segments and knows
      nothing about nodes, so it will happily evacuate a crowded
      corridor straight into one. Any displacement whose segment newly
      offends is reverted, judged against the same `ObstacleMap` the
      corridor search already used.
    """
    paths = [path for _connection, path in routed]
    if len(paths) < MIN_PATHS_FOR_SEPARATION:
        return [list(path) for path in paths]
    offsets = collinear_displacement_offsets(paths, COLLINEAR_SEPARATION_GAP)
    drop_anchor_breaking_offsets(routed, offsets, float(config.node_clearance))
    if not offsets:
        return [list(path) for path in paths]
    baseline_offences = segment_offences(paths, obstacle_map, obstacles)
    separated = apply_segment_offsets(paths, offsets)
    for _pass in range(COLLINEAR_SEPARATION_MAX_PASSES):
        introduced = sorted(
            (path_index, segment_index)
            for _criterion, path_index, segment_index in segment_offences(
                separated,
                obstacle_map,
                obstacles,
            )
            - baseline_offences
        )
        if not introduced or not revert_offending_offsets(offsets, introduced):
            break
        separated = apply_segment_offsets(paths, offsets)
    return [
        candidate if path_axes_preserved(path, candidate) else list(path)
        for path, candidate in zip(paths, separated, strict=True)
    ]


def segment_axis(first: Point, second: Point) -> str | None:
    """Return "h" for a horizontal segment, "v" for vertical, None for neither."""
    if abs(first.y - second.y) < SEGMENT_AXIS_EPSILON:
        return "h"
    if abs(first.x - second.x) < SEGMENT_AXIS_EPSILON:
        return "v"
    return None


def collinear_displacement_offsets(
    paths: list[list[Point]],
    min_gap: float,
) -> dict[tuple[int, int], tuple[str, float]]:
    """Recover the per-segment displacement upstream proposes, by diffing it.

    A horizontal segment can only be displaced in y and a vertical one
    in x, and a neighbouring segment's displacement only moves the
    *other* coordinate of the waypoint they share, so the diff isolates
    each segment's own offset. Working in offsets (rather than in the
    displaced points) is what lets the guards below reject one
    displacement without disturbing the rest of the polyline.
    """
    displaced = displace_collinear_segments([list(path) for path in paths], min_gap)
    offsets: dict[tuple[int, int], tuple[str, float]] = {}
    for path_index, path in enumerate(paths):
        axes = [segment_axis(first, second) for first, second in pairwise(path)]
        for segment_index, axis in enumerate(axes):
            if axis is None:
                continue
            previous_axis = axes[segment_index - 1] if segment_index else None
            next_axis = (
                axes[segment_index + 1] if segment_index + 1 < len(axes) else None
            )
            if axis in (previous_axis, next_axis):
                # Two same-axis segments in a row would move the waypoint
                # they share twice, bending the polyline.
                continue
            moved = displaced[path_index][segment_index]
            origin = path[segment_index]
            delta = moved.y - origin.y if axis == "h" else moved.x - origin.x
            if abs(delta) > SEGMENT_AXIS_EPSILON:
                offsets[path_index, segment_index] = (axis, delta)
    return offsets


def drop_anchor_breaking_offsets(
    routed: list[tuple[Any, list[Point]]],
    offsets: dict[tuple[int, int], tuple[str, float]],
    min_clearance: float,
) -> None:
    """Remove displacements that would slide a node anchor off its centerline."""
    for key in list(offsets):
        path_index, segment_index = key
        axis, delta = offsets[key]
        connection, path = routed[path_index]
        anchors = []
        if segment_index == 0:
            anchors.append((connection.source, path[0]))
        if segment_index == len(path) - 2:
            anchors.append((connection.target, path[-1]))
        if not all(
            anchor_displacement_allowed(node, anchor, axis, delta, min_clearance)
            for node, anchor in anchors
        ):
            del offsets[key]


def anchor_displacement_allowed(
    node: Any,
    anchor: Point,
    axis: str,
    delta: float,
    min_clearance: float,
) -> bool:
    """True when a displaced anchor stays on its centerline, outside the node."""
    if node is None:
        return False
    if abs(anchor.x - (node.x + (node.w / 2))) < 1:
        # Anchor leaves through the top/bottom edge: its stub runs in y,
        # so only a vertical shift keeps it on the centerline.
        if axis != "h":
            return False
        moved_y = anchor.y + delta
        return (
            moved_y <= node.y - min_clearance
            if anchor.y <= node.y
            else moved_y >= node.y + node.h + min_clearance
        )
    if abs(anchor.y - (node.y + (node.h / 2))) < 1:
        # Anchor leaves through the left/right edge: its stub runs in x.
        if axis != "v":
            return False
        moved_x = anchor.x + delta
        return (
            moved_x <= node.x - min_clearance
            if anchor.x <= node.x
            else moved_x >= node.x + node.w + min_clearance
        )
    return False


def apply_segment_offsets(
    paths: list[list[Point]],
    offsets: dict[tuple[int, int], tuple[str, float]],
) -> list[list[Point]]:
    """Return the paths with every surviving displacement applied."""
    separated = [list(path) for path in paths]
    for (path_index, segment_index), (axis, delta) in offsets.items():
        for point_index in (segment_index, segment_index + 1):
            point = separated[path_index][point_index]
            separated[path_index][point_index] = (
                Point(point.x, point.y + delta)
                if axis == "h"
                else Point(point.x + delta, point.y)
            )
    return separated


def segment_offences(
    paths: list[list[Point]],
    obstacle_map: Any,
    obstacles: list[Any],
) -> set[tuple[str, int, int]]:
    """Segments sitting on an obstacle, tagged by criterion.

    "blocked" and "interior" are kept apart on purpose: a segment
    already inside a node's clearance zone must still be caught when a
    displacement newly drives it through a node *interior*, which one
    merged set would mask.
    """
    offences: set[tuple[str, int, int]] = set()
    for path_index, path in enumerate(paths):
        for segment_index, (first, second) in enumerate(pairwise(path)):
            if (
                abs(first.x - second.x) < SEGMENT_AXIS_EPSILON
                and abs(first.y - second.y) < SEGMENT_AXIS_EPSILON
            ):
                continue
            if obstacle_map.segment_blocked(first, second):
                offences.add(("blocked", path_index, segment_index))
            if any(
                segment_enters_rectangle(first, second, obstacle)
                for obstacle in obstacles
            ):
                offences.add(("interior", path_index, segment_index))
    return offences


def segment_enters_rectangle(first: Point, second: Point, rectangle: Any) -> bool:
    """True when an axis-aligned segment crosses a node's interior."""
    left = rectangle.x + NODE_INTERIOR_INSET
    top = rectangle.y + NODE_INTERIOR_INSET
    right = rectangle.x + rectangle.width - NODE_INTERIOR_INSET
    bottom = rectangle.y + rectangle.height - NODE_INTERIOR_INSET
    if right <= left or bottom <= top:
        return False
    axis = segment_axis(first, second)
    if axis == "h":
        return top < first.y < bottom and ranges_overlap(
            first.x,
            second.x,
            left,
            right,
        )
    if axis == "v":
        return left < first.x < right and ranges_overlap(
            first.y,
            second.y,
            top,
            bottom,
        )
    return False


def ranges_overlap(
    first_start: float,
    first_end: float,
    second_start: float,
    second_end: float,
) -> bool:
    return min(first_start, first_end) < max(second_start, second_end) and min(
        second_start,
        second_end,
    ) < max(first_start, first_end)


def revert_offending_offsets(
    offsets: dict[tuple[int, int], tuple[str, float]],
    introduced: list[tuple[int, int]],
) -> bool:
    """Drop the displacement behind each newly offending segment.

    A segment carrying no offset of its own can only have moved because
    a neighbour's displacement stretched it, so the neighbour's offset
    is the one to drop.
    """
    reverted = False
    for path_index, segment_index in introduced:
        for key in (
            (path_index, segment_index),
            (path_index, segment_index - 1),
            (path_index, segment_index + 1),
        ):
            if key in offsets:
                del offsets[key]
                reverted = True
                break
    return reverted


def path_axes_preserved(path: list[Point], candidate: list[Point]) -> bool:
    """True when the candidate bends exactly where the original path bends."""
    return [segment_axis(first, second) for first, second in pairwise(path)] == [
        segment_axis(first, second) for first, second in pairwise(candidate)
    ]


def should_simplify_connection_routing(view: PyArchimateView) -> bool:
    if is_coverage_view(view):
        return True
    if len(view.conns) >= DENSE_VIEW_CONNECTION_THRESHOLD:
        return True
    return (
        len(view.conns) >= DENSE_VIEW_MIN_CONNECTIONS_FOR_SIMPLIFIED_ROUTING
        and view_connection_density(view) >= DENSE_VIEW_CONNECTIONS_PER_NODE_THRESHOLD
    )


def is_coverage_view(
    view: PyArchimateView,
    *,
    coverage_view_name: str | None = None,
) -> bool:
    """True only for the generated relationship-coverage view.

    Recognition is by marker property first — `_mark_coverage_view`
    writes it on every view the MCP creates or adopts for coverage — and
    then by an exact match against the caller's `coverage_view_name`,
    which is how a pre-existing view is adopted on the first pass.

    There is deliberately no `"coverage" in name.lower()` fallback. It
    silently captured authored views ("Data Coverage Analysis"), which
    then lost their layer bands, kept their redundant group-containment
    connectors, and were laid out as generated scaffolding — none of it
    reported to the caller. The exact-name comparison already covers the
    only case the substring was there for.
    """
    if view.prop(COVERAGE_VIEW_PROPERTY_KEY) == COVERAGE_VIEW_PROPERTY_VALUE:
        return True
    view_name = getattr(view, "name", "") or ""
    return coverage_view_name is not None and view_name == coverage_view_name


def connection_relationship_type(connection: Any) -> str | None:
    """Relationship type behind a view connection, or None if it has none.

    A connection whose ``ref`` does not resolve to a Relationship is an
    annotation-only connector (e.g. a note-to-element line). Since pyArchimate
    1.12.0 those report ``concept``/``type``/``name`` as None instead of raising
    KeyError, so callers must treat None as "not an ArchiMate relationship" and
    leave the connector alone rather than styling or classifying it.
    """
    return cast("str | None", connection.type)


def connection_label_text(connection: Any) -> str | None:
    label_text = getattr(connection, "name", None)
    if label_text:
        return str(label_text)
    concept = getattr(connection, "concept", None)
    concept_name = getattr(concept, "name", None)
    return None if not concept_name else str(concept_name)


def connection_label_size(connection: Any) -> tuple[int, int]:
    label_text = connection_label_text(connection) or ""
    font_size = int(getattr(connection, "font_size", 9) or 9)
    char_width = max(DEFAULT_LABEL_CHAR_WIDTH, int(font_size * 0.75))
    label_width = max(48, (len(label_text) * char_width) + 16)
    label_height = max(DEFAULT_LABEL_HEIGHT, int(font_size * 2.2))
    return label_width, label_height


def semantic_relationship_ranks(
    view: PyArchimateView,
    nodes: list[Any],
    row_by_node_id: dict[str, int],
) -> dict[str, int]:
    rank_by_node_id = original_position_ranks(nodes, row_by_node_id)
    flow_ranks, flow_node_ids = visible_relationship_ranks(
        view,
        nodes,
        relationship_types=PRIMARY_FLOW_RELATIONSHIP_TYPES,
        row_by_node_id=row_by_node_id,
        same_row_only=True,
    )
    for node_id in flow_node_ids:
        rank_by_node_id[node_id] = flow_ranks[node_id]
    align_data_nodes_to_access_sources(
        view,
        nodes,
        rank_by_node_id,
        row_by_node_id,
    )
    return rank_by_node_id


def align_data_nodes_to_access_sources(
    view: PyArchimateView,
    nodes: list[Any],
    rank_by_node_id: dict[str, int],
    row_by_node_id: dict[str, int],
) -> None:
    node_by_element_id = {node.ref: node for node in nodes if node.ref is not None}
    candidate_source_ranks_by_data_node_id: dict[str, list[int]] = defaultdict(list)
    for connection in view.conns:
        relationship = connection.concept
        if getattr(relationship, "type", None) != "Access":
            continue
        source_node = node_by_element_id.get(relationship.source.uuid)
        target_node = node_by_element_id.get(relationship.target.uuid)
        if source_node is None or target_node is None:
            continue
        target_type = getattr(target_node.concept, "type", None)
        if target_type not in DATA_ACCESS_ELEMENT_TYPES:
            continue
        if row_by_node_id.get(source_node.uuid) == row_by_node_id.get(
            target_node.uuid,
        ):
            continue
        candidate_source_ranks_by_data_node_id[target_node.uuid].append(
            rank_by_node_id.get(source_node.uuid, 0),
        )

    for (
        data_node_id,
        source_ranks,
    ) in candidate_source_ranks_by_data_node_id.items():
        rank_by_node_id[data_node_id] = round(sum(source_ranks) / len(source_ranks))


def original_position_ranks(
    nodes: list[Any],
    row_by_node_id: dict[str, int],
) -> dict[str, int]:
    nodes_by_row: dict[int, list[Any]] = defaultdict(list)
    for node in nodes:
        row_index = row_by_node_id.get(node.uuid, len(ARCHIMATE_LAYOUT_ROW_ORDER))
        nodes_by_row[row_index].append(node)
    rank_by_node_id = {}
    for row_nodes in nodes_by_row.values():
        ordered_nodes = sorted(
            row_nodes,
            key=lambda node: (
                node.x,
                node.y,
                node_sort_name(node),
                node.uuid,
            ),
        )
        rank_by_node_id.update(
            {node.uuid: index for index, node in enumerate(ordered_nodes)},
        )
    return rank_by_node_id


def visible_relationship_ranks(
    view: PyArchimateView,
    nodes: list[Any],
    *,
    relationship_types: set[str],
    row_by_node_id: dict[str, int] | None = None,
    same_row_only: bool = False,
) -> tuple[dict[str, int], set[str]]:
    node_by_element_id = {node.ref: node for node in nodes if node.ref is not None}
    node_ids = {node.uuid for node in nodes}
    rank_by_node_id = {node.uuid: 0 for node in nodes}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    incoming_count = dict.fromkeys(node_ids, 0)
    participating_node_ids: set[str] = set()

    for connection in view.conns:
        relationship = connection.concept
        if getattr(relationship, "type", None) not in relationship_types:
            continue
        source_node = node_by_element_id.get(relationship.source.uuid)
        target_node = node_by_element_id.get(relationship.target.uuid)
        if source_node is None or target_node is None:
            continue
        if (
            same_row_only
            and row_by_node_id is not None
            and row_by_node_id.get(source_node.uuid)
            != row_by_node_id.get(target_node.uuid)
        ):
            continue
        if (
            source_node.uuid == target_node.uuid
            or target_node.uuid in outgoing[source_node.uuid]
        ):
            continue
        outgoing[source_node.uuid].add(target_node.uuid)
        incoming_count[target_node.uuid] += 1
        participating_node_ids.update({source_node.uuid, target_node.uuid})

    assign_topological_ranks(
        view,
        participating_node_ids or node_ids,
        outgoing,
        incoming_count,
        rank_by_node_id,
    )
    return rank_by_node_id, participating_node_ids


def relationship_ranks(
    view: PyArchimateView,
    nodes: list[Any],
) -> dict[str, int]:
    node_by_element_id = {node.ref: node for node in nodes if node.ref is not None}
    rank_by_node_id = {node.uuid: 0 for node in nodes}
    node_ids = {node.uuid for node in nodes}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    incoming_count = dict.fromkeys(node_ids, 0)
    for relationship in view.model.relationships:
        source_node = node_by_element_id.get(relationship.source.uuid)
        target_node = node_by_element_id.get(relationship.target.uuid)
        if (
            source_node is None
            or target_node is None
            or source_node.uuid == target_node.uuid
            or target_node.uuid in outgoing[source_node.uuid]
        ):
            continue
        outgoing[source_node.uuid].add(target_node.uuid)
        incoming_count[target_node.uuid] += 1

    assign_topological_ranks(
        view,
        node_ids,
        outgoing,
        incoming_count,
        rank_by_node_id,
    )
    return rank_by_node_id


def assign_topological_ranks(
    view: PyArchimateView,
    node_ids: set[str],
    outgoing: dict[str, set[str]],
    incoming_count: dict[str, int],
    rank_by_node_id: dict[str, int],
) -> None:
    unprocessed = set(node_ids)
    ready = sorted(
        (node_id for node_id, count in incoming_count.items() if count == 0),
        key=lambda node_id: node_sort_name(view.model.nodes_dict[node_id]),
    )
    while unprocessed:
        if not ready:
            ready.append(
                min(
                    unprocessed,
                    key=lambda node_id: (
                        rank_by_node_id[node_id],
                        node_sort_name(view.model.nodes_dict[node_id]),
                    ),
                ),
            )
        node_id = ready.pop(0)
        if node_id not in unprocessed:
            continue
        unprocessed.remove(node_id)
        for target_node_id in sorted(outgoing[node_id]):
            rank_by_node_id[target_node_id] = max(
                rank_by_node_id[target_node_id],
                rank_by_node_id[node_id] + 1,
            )
            incoming_count[target_node_id] -= 1
            if incoming_count[target_node_id] <= 0:
                ready.append(target_node_id)
        ready.sort(
            key=lambda queued_id: node_sort_name(
                view.model.nodes_dict[queued_id],
            ),
        )


def node_layout_row_name(node: Any) -> str:
    element_type = getattr(node.concept, "type", None) if node.ref else None
    if element_type == "Grouping" and node.nodes:
        row_index_by_name = {
            row_name: index for index, row_name in enumerate(ARCHIMATE_LAYOUT_ROW_ORDER)
        }
        child_row_names = [node_layout_row_name(child) for child in node.nodes]
        return min(
            child_row_names,
            key=lambda row_name: row_index_by_name.get(
                row_name,
                len(ARCHIMATE_LAYOUT_ROW_ORDER),
            ),
        )
    if element_type in ARCHIMATE_LAYOUT_ROW_BY_TYPE:
        return ARCHIMATE_LAYOUT_ROW_BY_TYPE[element_type]
    return node_layer_name(node)


def node_sort_name(node: Any) -> str:
    concept = getattr(node, "concept", None)
    return (getattr(concept, "name", "") or "").lower()


def node_layer_name(node: Any) -> str:
    # `concept` is None for a diagram-only node (no ref) and for a node whose
    # ref no longer resolves to an element; ARCHI_CATEGORY.get(None) -> "Other".
    element_type = getattr(node.concept, "type", None) if node.ref else None
    return ARCHI_CATEGORY.get(element_type, "Other")


def intersects_any(
    rect: tuple[int, int, int, int],
    existing_rects: list[tuple[int, int, int, int]],
) -> bool:
    return any(rects_overlap(rect, existing_rect) for existing_rect in existing_rects)


def rects_overlap(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
    padding: int = 20,
) -> bool:
    first_x, first_y, first_width, first_height = first
    second_x, second_y, second_width, second_height = second
    return not (
        first_x + first_width + padding <= second_x
        or second_x + second_width + padding <= first_x
        or first_y + first_height + padding <= second_y
        or second_y + second_height + padding <= first_y
    )


def ceil_sqrt(value: int) -> int:
    if value <= 1:
        return 1
    return math.isqrt(value - 1) + 1

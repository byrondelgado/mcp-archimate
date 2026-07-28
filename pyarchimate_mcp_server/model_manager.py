"""Core ArchiMate model management backed by pyArchimate."""

import contextlib
import copy
import csv
import difflib
import hashlib
import io
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from lxml import etree
from pyArchimate.constants import ARCHI_CATEGORY
from pyArchimate.enums import Writers
from pyArchimate.exceptions import ArchimateConceptTypeError, ArchimateRelationshipError
from pyArchimate.model import Model
from pyArchimate.relationship import check_valid_relationship
from pyArchimate.viewpoint_registry import (
    STANDARD_VIEWPOINTS,
    validate_viewpoint_slug,
)

from pyarchimate_mcp_server import filesystem, layout
from pyarchimate_mcp_server.constants import (
    ARCHIMATE_ELEMENT_TYPES,
    ARCHIMATE_RELATIONSHIP_TYPES,
    SUPPORTED_FORMATS,
)
from pyarchimate_mcp_server.exceptions import (
    ElementNotFoundError,
    InvalidElementTypeError,
    InvalidRelationshipCombinationError,
    InvalidRelationshipTypeError,
    ModelNotFoundError,
    ModelOperationError,
    RelationshipNotFoundError,
    UnsupportedFormatError,
    ViewNotFoundError,
)
from pyarchimate_mcp_server.layout import (  # noqa: F401  (re-exported for API/test stability)
    COVERAGE_VIEW_PROPERTY_KEY,
    COVERAGE_VIEW_PROPERTY_VALUE,
    DEFAULT_NODE_WIDTH,
    DEFAULT_X_GAP,
    DEFAULT_Y_GAP,
    GROUP_CONTAINMENT_RELATIONSHIP_LINE_COLOR,
    JUNCTION_NODE_SIZE,
    SECONDARY_DENSE_RELATIONSHIP_LINE_COLOR,
)
from pyarchimate_mcp_server.models import (
    ElementDetail,
    RelationshipDetail,
    ViewConnection,
    ViewDetail,
    ViewNode,
)
from pyarchimate_mcp_server.relationship_rules import (
    SUPPORTED_INTENTS,
    backend_metadata,
    compatibility,
    is_valid_relationship,
    recommendations,
    relationship_issue_details,
)

MAX_MODEL_CONTENT_BYTES = 10 * 1024 * 1024
XSI_TYPE_ATTRIBUTE = "{http://www.w3.org/2001/XMLSchema-instance}type"

# Archi has TWO diagram connection classes and the distinction is not
# cosmetic. `archimate:Connection` is `DiagramModelArchimateConnection`,
# an `IDiagramModelArchimateComponent`: Archi calls `getArchimateConcept()`
# on it while building figures, so one written without an
# `archimateRelationship` yields null and Archi throws a
# NullPointerException — reported in its log as being unable to invoke
# eClass on the null return of getArchimateConcept, and shown to the user
# as "Failed to create the part's controls", with the entire view
# refusing to open. `archimate:DiagramModelConnection` is the
# concept-less line Archi uses for note and group connectors.
# pyArchimate's archi writer types *every* connection as
# `archimate:Connection` and only omits the attribute for annotation
# lines; its comment claiming Archi does the same is half right (Archi
# omits the attribute AND writes a different type), so the export pass
# below has to retype them.
ARCHI_CONCEPT_CONNECTION_TYPE = "archimate:Connection"
ARCHI_PLAIN_CONNECTION_TYPE = "archimate:DiagramModelConnection"
DEFAULT_NODE_HEIGHT = 80
# Archi's own default note size.
DEFAULT_NOTE_WIDTH = 185
DEFAULT_NOTE_HEIGHT = 80
DEFAULT_MARGIN_X = 40
DEFAULT_MARGIN_Y = 40
PARALLEL_LABEL_ROUTE_GAP = 44
TOGAF_PARTIAL_SCORE_THRESHOLD = 3
SUPPORTED_LAYOUT_STRATEGIES = {"grid", "layered", "layered_by_type"}
SUPPORTED_LAYOUT_ENGINES = {"internal", "pyarchimate"}
SUPPORTED_DETAIL_LEVELS = {"full", "summary"}

# Every pyArchimate namespace a client-supplied id can land in, paired
# with the concept kind that owns it. These are five separate dicts
# upstream, but one id space in the exported XML — see
# `_require_unused_concept_id`. Order fixes which kind a collision
# reports when a model already contains cross-kind duplicates from an
# imported file.
CONCEPT_ID_NAMESPACES = (
    ("elems_dict", "element"),
    ("rels_dict", "relationship"),
    ("views_dict", "view"),
    ("nodes_dict", "node"),
    ("conns_dict", "connection"),
)

# The field that identifies what a semantic issue is *about*, in
# priority order. Used to group a summary by code without repeating the
# code, severity and message string once per issue. Ordered because
# several issue shapes carry more than one of these (a relationship
# issue also carries source and target element ids) and the first match
# is the subject.
SEMANTIC_ISSUE_IDENTITY_KEYS = (
    "element_ids",
    "element_id",
    "relationship_id",
    "junction_element_id",
    "child_node_id",
    "view_id",
)
SUPPORTED_SEMANTIC_VALIDATION_MODES = {"off", "warn", "strict"}
SUPPORTED_QUALITY_GATES = {"off", "warn", "strict"}
QA_VIEW_PROPERTY_KEY = "is_quality_assurance_view"
STAKEHOLDER_FACING_PROPERTY_KEY = "is_stakeholder_facing"
ARCHI_ROOT_FOLDERS = (
    "/Strategy",
    "/Business",
    "/Application",
    "/Technology",
    "/Motivation",
    "/Implementation & Migration",
    "/Other",
    "/Relations",
    "/Views",
)
ARCHI_ROOT_ALIASES = {
    "strategy": "/Strategy",
    "business": "/Business",
    "application": "/Application",
    "technology": "/Technology",
    "physical": "/Technology",
    "motivation": "/Motivation",
    "implementation": "/Implementation & Migration",
    "implementation & migration": "/Implementation & Migration",
    "implementation and migration": "/Implementation & Migration",
    "other": "/Other",
    "junction": "/Other",
    "relations": "/Relations",
    "relationships": "/Relations",
    "views": "/Views",
    "diagrams": "/Views",
    "technology & physical": "/Technology",
    "technology and physical": "/Technology",
}

# Stock Archi 5.x model-tree labels, keyed by native folder type attribute.
ARCHI_FOLDER_DISPLAY_NAMES = {
    "technology": "Technology & Physical",
    "implementation_migration": "Implementation & Migration",
}

# pyArchimate viewpoint slugs -> Archi's canonical viewpoint identifiers
# (from Archi's com.archimatetool.model/model/viewpoints.xml). Identity
# slugs (stakeholder, capability, organization, technology, physical,
# migration, strategy) are already valid Archi ids and need no rewrite.
# "actor" (ArchiMate 2 Actor Co-operation) has no Archi 5.x equivalent.
ARCHI_VIEWPOINT_ID_BY_SLUG = {
    "service": "service_realization",
    "business": "business_process_cooperation",
    "application": "application_cooperation",
    "implementation": "implementation_deployment",
    "infrastructure": "technology",
}

# All canonical Archi 5.x viewpoint identifiers
# (from Archi's com.archimatetool.model/model/viewpoints.xml).
ARCHI_VIEWPOINT_IDS = frozenset(
    {
        "application_cooperation",
        "application_structure",
        "application_usage",
        "business_process_cooperation",
        "capability",
        "goal_realization",
        "implementation_deployment",
        "implementation_migration",
        "information_structure",
        "layered",
        "migration",
        "motivation",
        "organization",
        "outcome_realization",
        "physical",
        "product",
        "project",
        "requirements_realization",
        "resource",
        "service_realization",
        "stakeholder",
        "strategy",
        "technology",
        "technology_usage",
        "value_stream",
    }
)


def viewpoint_catalogs() -> dict[str, list[str]]:
    """Return the two namespaces a `viewpoint` value may come from.

    Sole source for both the `list_supported_types` catalog and the
    `error.details` of a rejected viewpoint, so what the server
    advertises and what it accepts cannot drift apart. Derived at call
    time: the slug list is version-specific to the running pyArchimate.

    The two namespaces overlap (`capability`, `migration`,
    `organization`, `physical`, `stakeholder`, `strategy`,
    `technology`) without either containing the other, which is why
    both have to be published rather than merged.
    """
    return {
        "pyarchimate_slugs": sorted(
            viewpoint_def.id for viewpoint_def in STANDARD_VIEWPOINTS
        ),
        "archi_viewpoint_ids": sorted(ARCHI_VIEWPOINT_IDS),
    }


ARCHI_FOLDER_ROOT_BY_CATEGORY = {
    "Strategy": "/Strategy",
    "Business": "/Business",
    "Application": "/Application",
    "Technology": "/Technology",
    "Physical": "/Technology",
    "Motivation": "/Motivation",
    "Implementation & Migration": "/Implementation & Migration",
    "Other": "/Other",
    "Junction": "/Other",
    "Relationship": "/Relations",
    "View": "/Views",
}
SUPPORTED_ACCESS_TYPES = {"Access", "Read", "ReadWrite", "Write"}
SUPPORTED_INFLUENCE_STRENGTHS = {
    "+",
    "++",
    "+++",
    "-",
    "--",
    "---",
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
}

PyArchimateElement = Any
PyArchimateRelationship = Any
PyArchimateView = Any


class ArchimateModelManager:
    """Manage a single active pyArchimate model instance."""

    def __init__(self) -> None:
        self._active_model: Model | None = None

    def get_active_model(self) -> Model | None:
        """Return the active pyArchimate model, if one exists."""
        return self._active_model

    def create_new_model(
        self,
        model_name: str = "Untitled Model",
        *,
        description: str | None = None,
        properties: dict[str, str] | None = None,
    ) -> Model:
        """Create a new empty model, replacing any currently active model."""
        self._active_model = Model(
            name=model_name,
            desc=str(description) if description is not None else None,
        )
        self._apply_properties(self._active_model, properties)
        return self._active_model

    def load_model_from_string(
        self,
        model_content: str,
        content_format: str = "archimate",
    ) -> None:
        """Load a model from XML string content, replacing the active model."""
        self._ensure_supported_format(content_format)
        self._validate_xml_content(model_content)

        model = Model()
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                suffix=".archimate",
                delete=False,
            ) as temp_file:
                temp_file.write(model_content)
                temp_path = Path(temp_file.name)

            model.read(str(temp_path))
        except (
            ArchimateConceptTypeError,
            ArchimateRelationshipError,
            OSError,
            ValueError,
        ) as exc:
            self._active_model = None
            msg = f"Failed to load model from string: {exc}"
            raise ModelOperationError(msg) from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

        self._active_model = model
        # Restore primary viewpoints from the persisted "viewpoint" user
        # property so a load -> re-export round trip keeps the native
        # viewpoint attribute. Foreign files with unknown slugs must not
        # fail the load, so suppress instead of raising here.
        for view in model.views:
            viewpoint = view.prop("viewpoint")
            if viewpoint and hasattr(view, "set_primary_viewpoint"):
                with contextlib.suppress(ValueError):
                    view.set_primary_viewpoint(str(viewpoint))
        self._restore_exchange_note_connectors(model, model_content, content_format)

    def _restore_exchange_note_connectors(
        self,
        model: Model,
        content: str,
        content_format: str,
    ) -> None:
        """Re-create the note lines pyArchimate's exchange reader drops.

        `_rewrite_note_connectors_as_lines` writes a note line as the
        schema's `xsi:type="Line"` — the only valid way to express a
        view-only connection, since `Relationship` requires a resolvable
        `relationshipRef`. pyArchimate's exchange reader then skips
        every `Line` (`_read_view_connection` returns early when there
        is no `relationshipRef`), so without this pass the note node
        would come back but the line pointing at what it annotates
        would not.

        As narrow as the write side: only a `Line` with a note endpoint
        is restored. A `Line` between two element nodes comes from some
        other tool's drawing layer, is not something this server models,
        and is left alone rather than invented into a note connector.
        """
        if content_format.lower() != "archimate":
            return
        root = etree.fromstring(content.encode("utf-8"))
        namespace = root.tag.split("}")[0].lstrip("{")
        view_by_id = {view.uuid: view for view in model.views}
        for view_element in root.iter(f"{{{namespace}}}view"):
            view = view_by_id.get(view_element.get("identifier"))
            if view is None:
                continue
            node_by_id = {node.uuid: node for node in layout.view_nodes_recursive(view)}
            existing_ids = {connection.uuid for connection in view.conns}
            for connection in view_element.iter(f"{{{namespace}}}connection"):
                if connection.get(XSI_TYPE_ATTRIBUTE) != "Line":
                    continue
                connection_id = connection.get("identifier")
                if connection_id in existing_ids:
                    continue
                source = node_by_id.get(connection.get("source"))
                target = node_by_id.get(connection.get("target"))
                if source is None or target is None:
                    continue
                if not (layout.is_note_node(source) or layout.is_note_node(target)):
                    continue
                # Endpoints are passed in file order, not note-first, so
                # the restored line keeps the direction it was drawn in.
                view.connect_note(source, target, uuid=connection_id)

    def get_model_content_as_string(  # noqa: PLR0913
        self,
        output_format: str = "archimate",
        *,
        auto_layout: bool = False,
        layout_strategy: str = "layered_by_type",
        layout_engine: str = "internal",
        quality_gate: str = "off",
        allow_semantic_issues: bool = False,
        allow_visual_issues: bool = False,
        allow_orphans: bool = True,
    ) -> str:
        """Serialize the active model to XML string content."""
        model = self._require_model()
        self._ensure_supported_format(output_format)
        # Validated unconditionally: silently dropping a mistyped engine
        # when auto_layout is false reads as "the engine ran and had
        # nothing to report".
        self._normalize_layout_strategy(layout_strategy)
        self._normalize_layout_engine(layout_engine)
        self._enforce_quality_gate(
            quality_gate,
            allow_semantic_issues=allow_semantic_issues,
            allow_visual_issues=allow_visual_issues,
            allow_orphans=allow_orphans,
        )
        self._normalize_model_folder_paths()
        if auto_layout:
            self.auto_layout_all_views(
                strategy=layout_strategy,
                layout_engine=layout_engine,
            )
        try:
            if output_format.lower() == "archi":
                return self._finalize_archi_output(
                    self._model_copy_for_archi_export(model).write(
                        writer=Writers.archi,
                    ),
                )
            return self._sanitize_exchange_output(model, model.write())
        except (AttributeError, KeyError) as exc:
            msg = (
                f"Unable to export model as {output_format!r}: {exc}. "
                "Check folder paths and Junction elements before retrying."
            )
            raise ModelOperationError(msg) from exc

    def export_model_to_file(  # noqa: PLR0913
        self,
        path: str,
        output_format: str = "archi",
        *,
        auto_layout: bool = False,
        layout_strategy: str = "layered_by_type",
        layout_engine: str = "internal",
        quality_gate: str = "off",
        allow_semantic_issues: bool = False,
        allow_visual_issues: bool = False,
        allow_orphans: bool = True,
        include_quality_report: bool = False,
    ) -> dict[str, Any]:
        """Serialize the active model and write it to a local file."""
        if not isinstance(path, str) or not path.strip():
            msg = "Export path must be a non-empty string."
            raise ModelOperationError(msg)
        # Reject a bad strategy/engine before writing anything, whether
        # or not auto_layout is on.
        self._normalize_layout_strategy(layout_strategy)
        self._normalize_layout_engine(layout_engine)

        output_path = self._resolve_output_path(path)
        # Run the gate here (once) so its report — including warnings — can
        # be reused in the result instead of rebuilding it after export.
        gate_report = self._enforce_quality_gate(
            quality_gate,
            allow_semantic_issues=allow_semantic_issues,
            allow_visual_issues=allow_visual_issues,
            allow_orphans=allow_orphans,
        )
        content = self.get_model_content_as_string(
            output_format=output_format,
            auto_layout=auto_layout,
            layout_strategy=layout_strategy,
            layout_engine=layout_engine,
        )
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            msg = f"Failed to write exported model to '{output_path}': {exc}"
            raise ModelOperationError(msg) from exc
        result = {
            "path": str(output_path),
            "output_format": output_format,
            "bytes_written": len(content.encode("utf-8")),
            "auto_layout": auto_layout,
            "layout_strategy": layout_strategy if auto_layout else None,
            "layout_engine": layout_engine if auto_layout else None,
        }
        if include_quality_report or quality_gate != "off":
            result["quality_report"] = gate_report or self.build_quality_report()
        return result

    def render_view_to_svg_file(self, view_id: str, path: str) -> dict[str, Any]:
        """Render one view to a standalone SVG file and return its metadata.

        SVG is a *rendering* for a human reviewer, not a third model
        format: it cannot be imported back into Archi, and the markup is
        never returned to the caller (a small view already costs
        thousands of tokens as text, and an agent cannot see an image).

        Read-only with respect to the model: no layout pass is triggered
        and no node coordinate, element, relationship, or view is
        touched. Render what is there; call `auto_layout_view` first if
        the geometry needs work.
        """
        model = self._require_model()
        if not isinstance(view_id, str) or not view_id.strip():
            msg = "View ID must be a non-empty string."
            raise ViewNotFoundError(msg)

        view = self.get_view_by_id(view_id.strip())
        if view is None:
            msg = f"View with ID '{view_id}' not found."
            raise ViewNotFoundError(msg)

        if not isinstance(path, str) or not path.strip():
            msg = "SVG output path must be a non-empty string."
            raise ModelOperationError(msg)
        output_path = self._resolve_output_path(path)

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            svg_content = view.to_svg(str(output_path))
        except (OSError, AttributeError, KeyError, ValueError) as exc:
            msg = f"Failed to render view '{view_id}' to SVG at '{output_path}': {exc}"
            raise ModelOperationError(msg) from exc

        width, height = self._svg_pixel_size(svg_content)
        return {
            "path": str(output_path),
            "view_id": view.uuid,
            "view_name": view.name,
            "model_name": model.name,
            "bytes_written": output_path.stat().st_size,
            "node_count": len(self._view_nodes_recursive(view)),
            "connection_count": len(view.conns),
            "width": width,
            "height": height,
        }

    @staticmethod
    def _svg_pixel_size(svg_content: str) -> tuple[int | None, int | None]:
        """Read the rendered canvas size off the SVG root element."""
        try:
            root = etree.fromstring(svg_content.encode("utf-8"))
        except etree.XMLSyntaxError:
            return None, None

        def as_int(value: str | None) -> int | None:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None

        return as_int(root.get("width")), as_int(root.get("height"))

    @staticmethod
    def _resolve_output_path(path: str) -> Path:
        """Resolve an output path and refuse one outside the allowed roots.

        Every write this server performs goes through here. See
        `filesystem.resolve_write_path` for the boundary itself.
        """
        return filesystem.resolve_write_path(path)

    def get_model_info(self) -> dict[str, Any]:
        """Return metadata about the active model."""
        if self._active_model is None:
            return {
                "name": None,
                "id": None,
                "documentation": None,
                "properties": {},
                "elements_count": 0,
                "relationships_count": 0,
                "views_count": 0,
                "is_loaded": False,
            }

        return {
            "name": self._active_model.name,
            "id": self._active_model.uuid,
            "documentation": self._active_model.desc,
            "properties": dict(self._active_model.props),
            "elements_count": len(self._active_model.elements),
            "relationships_count": len(self._active_model.relationships),
            "views_count": len(self._active_model.views),
            "is_loaded": True,
        }

    def update_model_metadata(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        properties: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Update name, documentation, and properties of the active model.

        Only supplied fields are written, matching the merge semantics of
        `update_element` and `update_view`; nothing is cleared. There is
        no "missing model" case here (only "no active model"), so this
        raises `ModelNotFoundError` instead of returning a bool.

        Every argument is validated BEFORE the first write. Without that
        ordering an invalid `properties` value returns an error envelope
        on a model whose name and documentation have already been
        rewritten — the caller reads "error" and reasonably concludes
        nothing changed. This path has no `_run_with_rollback` around
        it, so validate-then-write is what makes it atomic.
        """
        model = self._require_model()
        if properties is not None:
            self._require_spec_mapping(properties, "properties")
        if name is not None:
            model.name = name
        if description is not None:
            model.desc = str(description)
        if properties is not None:
            self._apply_properties(model, properties)
        return self.get_model_info()

    @staticmethod
    def _is_annotation_connector(connection: Any) -> bool:
        """True for a diagram-only note line, which has no relationship.

        `Model.check_invalid_conn()` flags every connection whose `ref` does
        not resolve to a Relationship, which includes the connector Archi
        draws from a Note to an element. That connector is purely visual and
        carries no ArchiMate semantics, so reporting it is a false positive.

        The narrowing is load-bearing: an unresolvable ref alone is NOT
        enough. A connector between two element-backed nodes whose
        relationship really is missing is a genuine defect and must keep
        being reported, as is one whose endpoint has vanished entirely.
        Only a `Label`-cat (Archi Note) endpoint earns the exemption;
        `Container` (Archi Group) endpoints are deliberately not exempted.
        """
        if connection is None:
            return False
        if layout.connection_relationship_type(connection) is not None:
            return False
        source = connection.source
        target = connection.target
        if source is None or target is None:
            return False
        return "Label" in {
            getattr(source, "cat", "Element"),
            getattr(target, "cat", "Element"),
        }

    def validate_model(self) -> dict[str, Any]:
        """Validate visual references using pyArchimate's model checks.

        Diagram-only annotation connectors (note lines) are filtered out of
        pyArchimate's invalid-connection result; see
        `_is_annotation_connector` for why the exemption is narrow.
        """
        model = self._require_model()
        invalid_connection_ids = [
            connection_id
            for connection_id in model.check_invalid_conn()
            if not self._is_annotation_connector(model.conns_dict.get(connection_id))
        ]
        invalid_node_ids = list(model.check_invalid_nodes())
        return {
            "is_valid": not invalid_connection_ids and not invalid_node_ids,
            "invalid_connection_ids": invalid_connection_ids,
            "invalid_node_ids": invalid_node_ids,
            "invalid_connections_count": len(invalid_connection_ids),
            "invalid_nodes_count": len(invalid_node_ids),
        }

    def get_relationship_compatibility(
        self,
        source_type: str,
        target_type: str,
    ) -> dict[str, Any]:
        """Return valid relationship options for a source/target type pair."""
        self._require_element_type(source_type)
        self._require_element_type(target_type)
        return compatibility(source_type, target_type)

    def recommend_relationship(  # noqa: PLR0913
        self,
        *,
        source_id: str | None = None,
        target_id: str | None = None,
        source_type: str | None = None,
        target_type: str | None = None,
        intent: str | None = None,
        strict_archimate: bool = True,
    ) -> dict[str, Any]:
        """Return valid relationship recommendations for ids or types."""
        resolved_source_type = self._resolve_element_type(source_id, source_type)
        resolved_target_type = self._resolve_element_type(target_id, target_type)
        result = recommendations(
            resolved_source_type,
            resolved_target_type,
            intent=intent,
            strict_archimate=strict_archimate,
        )
        if source_id is not None:
            result["source_id"] = source_id
        if target_id is not None:
            result["target_id"] = target_id
        return result

    def build_quality_report(
        self,
        *,
        include_togaf: bool = False,
        include_quality_assurance_views: bool = False,
    ) -> dict[str, Any]:
        """Build a structured quality report for export gating."""
        semantic_validation = self.validate_semantics()
        visual_validation = self.validate_model()
        orphan_data = self.list_orphan_elements()
        used_relationship_ids = self._relationship_ids_used_in_views()
        model = self._require_model()
        remaining_unused_relationship_ids = [
            relationship.uuid
            for relationship in model.relationships
            if relationship.uuid not in used_relationship_ids
        ]
        report = {
            "visual_validation": visual_validation,
            "semantic_validation": {
                "is_valid": semantic_validation["is_valid"],
                "issues_count": semantic_validation["issues_count"],
                "issue_counts": semantic_validation.get("issue_counts", {}),
            },
            "coverage": {
                "elements_not_in_any_view_count": orphan_data["not_in_any_view_count"],
                "remaining_unused_relationships_count": len(
                    remaining_unused_relationship_ids,
                ),
                "remaining_unused_relationship_ids": remaining_unused_relationship_ids,
            },
        }
        if include_togaf:
            togaf = self.assess_togaf_readiness(
                include_quality_assurance_views=include_quality_assurance_views,
                include_hard_validation=True,
            )
            # Carry the findings and the scale, not just the tallies. A
            # bare {"status": "limited", "score": 0, "count": 7} is not
            # interpretable: it cannot distinguish "this assessment
            # does not apply to your model" from "your model has seven
            # real problems", and 0 out of an unstated maximum says
            # nothing. Everything here is already computed, and the
            # whole report is under 3 KB.
            report["togaf_readiness"] = {
                "status": togaf["status"],
                "score": togaf["score"],
                "max_score": togaf["max_score"],
                "advisory_findings": togaf["advisory_findings"],
                "advisory_findings_count": togaf["advisory_findings_count"],
                "hard_failures_count": togaf["hard_failures_count"],
                "compliance_claim": togaf["compliance_claim"],
            }
        return report

    def assess_togaf_readiness(
        self,
        *,
        include_quality_assurance_views: bool = False,
        include_hard_validation: bool = True,
    ) -> dict[str, Any]:
        """Return advisory TOGAF-oriented model readiness findings."""
        model = self._require_model()
        findings = []
        element_types = {element.type for element in model.elements}
        stakeholder_views = [
            view
            for view in model.views
            if include_quality_assurance_views
            or not self._is_quality_assurance_view(view)
        ]

        def add_finding(code: str, message: str, severity: str = "medium") -> None:
            findings.append(
                {"code": code, "severity": severity, "message": message},
            )

        if "Stakeholder" not in element_types:
            add_finding("MISSING_STAKEHOLDER", "No Stakeholder elements found.")
        if not any(
            self._property_has_value(view, "concerns") for view in stakeholder_views
        ):
            add_finding(
                "MISSING_STAKEHOLDER_CONCERNS",
                "Stakeholder-facing views do not document concerns.",
            )
        motivation_types = {
            "Goal",
            "Driver",
            "Requirement",
            "Constraint",
            "Principle",
        }
        if not element_types & motivation_types:
            add_finding(
                "MISSING_MOTIVATION",
                "No goal, driver, requirement, constraint, or principle found.",
            )
        if not any(
            self._property_has_value(entity, "architecture_state")
            for entity in [*model.elements, *stakeholder_views]
        ):
            add_finding(
                "NO_BASELINE_TARGET_CLASSIFICATION",
                "Architecture content is not marked baseline, target, or transition.",
            )
        if "Gap" not in element_types:
            add_finding("NO_GAPS", "No Gap elements are represented.")
        if "WorkPackage" not in element_types:
            add_finding(
                "NO_WORK_PACKAGES",
                "No WorkPackage elements are represented for implementation planning.",
            )
        if not stakeholder_views:
            add_finding(
                "NO_STAKEHOLDER_FACING_VIEWS",
                "No stakeholder-facing architecture views found.",
            )
        elif not all(
            self._property_has_value(view, "purpose") for view in stakeholder_views
        ):
            add_finding(
                "MISSING_VIEW_PURPOSE",
                "One or more stakeholder-facing views lack purpose metadata.",
            )

        hard_failures = []
        if include_hard_validation:
            hard_failures = [
                issue
                for issue in self.validate_semantics(detail="full")["issues"]
                if issue.get("severity", "error") == "error"
            ]

        max_score = 7
        score = max(0, max_score - len(findings))
        status = (
            "ready"
            if not findings
            else "partial"
            if score >= TOGAF_PARTIAL_SCORE_THRESHOLD
            else "limited"
        )
        return {
            "status": status,
            "score": score,
            "max_score": max_score,
            "hard_failures": hard_failures,
            "hard_failures_count": len(hard_failures),
            "advisory_findings": findings,
            "advisory_findings_count": len(findings),
            "include_quality_assurance_views": include_quality_assurance_views,
            "compliance_claim": False,
        }

    def is_valid_element_type(self, element_type: str) -> bool:
        """Return whether an element type is supported by pyArchimate."""
        return element_type in ARCHIMATE_ELEMENT_TYPES

    def _type_suggestions(self, value: str, catalog: list[str]) -> list[str]:
        """Return close-match suggestions for a mistyped concept type."""
        matches = difflib.get_close_matches(value, catalog, n=3, cutoff=0.5)
        if matches:
            return matches
        lowered = value.lower()
        return [name for name in catalog if lowered in name.lower()][:3]

    def _invalid_element_type_error(
        self,
        element_type: str,
    ) -> InvalidElementTypeError:
        suggestions = self._type_suggestions(element_type, ARCHIMATE_ELEMENT_TYPES)
        msg = f"Invalid ArchiMate element type: {element_type}."
        if suggestions:
            msg += f" Did you mean: {', '.join(suggestions)}?"
        msg += " Call list_supported_types for the full catalog."
        return InvalidElementTypeError(msg, {"suggestions": suggestions})

    def _require_element_type(self, element_type: str) -> str:
        if element_type not in ARCHIMATE_ELEMENT_TYPES:
            raise self._invalid_element_type_error(element_type)
        return element_type

    def _require_relationship_type(self, relationship_type: str) -> str:
        if relationship_type not in ARCHIMATE_RELATIONSHIP_TYPES:
            suggestions = self._type_suggestions(
                relationship_type,
                ARCHIMATE_RELATIONSHIP_TYPES,
            )
            msg = f"Invalid ArchiMate relationship type: {relationship_type}."
            if suggestions:
                msg += f" Did you mean: {', '.join(suggestions)}?"
            msg += " Call list_supported_types for the full catalog."
            raise InvalidRelationshipTypeError(msg, {"suggestions": suggestions})
        return relationship_type

    def add_archimate_element(  # noqa: PLR0913, PLR0917
        self,
        name: str,
        element_type: str,
        description: str | None = None,
        folder_path: str | None = None,
        properties: dict[str, str] | None = None,
        element_id: str | None = None,
    ) -> PyArchimateElement:
        """Add a new ArchiMate element to the active model."""
        model = self._require_model()
        if not self.is_valid_element_type(element_type):
            raise self._invalid_element_type_error(element_type)
        self._require_unused_concept_id(model, element_id, "element")

        element = model.add(
            concept_type=element_type,
            name=name,
            uuid=element_id,
            desc=description,
            folder=self._normalize_folder_path_for_type(folder_path, element_type),
        )
        self._apply_properties(element, properties)
        return element

    def get_element_by_id(self, element_id: str) -> PyArchimateElement | None:
        """Return an element by ID, or None when absent."""
        if self._active_model is None:
            return None
        return self._active_model.elems_dict.get(element_id)

    def list_elements(
        self,
        filter_criteria: dict[str, Any] | None = None,
    ) -> list[PyArchimateElement]:
        """List all elements in the active model, optionally filtered."""
        if self._active_model is None:
            return []

        elements = list(self._active_model.elements)
        if filter_criteria is None:
            return elements

        element_type = filter_criteria.get("type")
        if element_type is not None:
            elements = [element for element in elements if element.type == element_type]

        name_contains = filter_criteria.get("name_contains")
        if name_contains is not None:
            needle = str(name_contains).lower()
            elements = [
                element
                for element in elements
                if needle in (element.name or "").lower()
            ]

        properties_contain = filter_criteria.get("properties_contain")
        if properties_contain:
            elements = [
                element
                for element in elements
                if self._properties_match(element.props, properties_contain)
            ]

        return elements

    def update_element_properties(
        self,
        element_id: str,
        name: str | None = None,
        description: str | None = None,
        properties: dict[str, str] | None = None,
        folder_path: str | None = None,
    ) -> bool:
        """Update an existing element."""
        element = self.get_element_by_id(element_id)
        if element is None:
            return False

        if name is not None:
            element.name = name
        if description is not None:
            element.desc = description
        if folder_path is not None:
            element.folder = self._normalize_folder_path_for_type(
                folder_path,
                element.type,
            )
        self._apply_properties(element, properties)
        return True

    def delete_element(self, element_id: str) -> bool:
        """Delete an element and pyArchimate-managed dependent concepts."""
        element = self.get_element_by_id(element_id)
        if element is None:
            return False
        element.delete()
        return True

    def map_element_to_detail(self, element: PyArchimateElement) -> ElementDetail:
        """Map a pyArchimate element to an API detail model."""
        return ElementDetail(
            id=element.uuid,
            name=element.name,
            type=element.type,
            description=element.desc,
            properties=dict(element.props),
            folder=element.folder,
            incoming_relationship_ids=[
                rel.uuid for rel in self.get_incoming_relationships(element.uuid)
            ],
            outgoing_relationship_ids=[
                rel.uuid for rel in self.get_outgoing_relationships(element.uuid)
            ],
        )

    def add_archimate_relationship(  # noqa: PLR0913
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        *,
        name: str | None = None,
        description: str | None = None,
        properties: dict[str, str] | None = None,
        access_type: str | None = None,
        influence_strength: str | None = None,
        is_directed: bool | None = None,
        relationship_id: str | None = None,
        semantic_validation: str = "off",
    ) -> PyArchimateRelationship:
        """Add a relationship between two model elements."""
        model = self._require_model()
        source_element = self.get_element_by_id(source_id)
        target_element = self.get_element_by_id(target_id)
        if source_element is None or target_element is None:
            msg = "Source or target element not found for relationship."
            raise ElementNotFoundError(msg)

        relationship_type = self._require_relationship_type(relationship_type)
        semantic_validation = self._normalize_semantic_validation_mode(
            semantic_validation,
        )
        self._validate_relationship_for_creation(
            relationship_type=relationship_type,
            source_element=source_element,
            target_element=target_element,
            access_type=access_type,
            semantic_validation=semantic_validation,
        )
        self._require_unused_concept_id(model, relationship_id, "relationship")
        try:
            relationship = model.add_relationship(
                rel_type=relationship_type,
                source=source_element,
                target=target_element,
                uuid=relationship_id,
                name=name,
                desc=description,
                access_type=self._normalize_access_type(
                    relationship_type,
                    access_type,
                ),
                influence_strength=self._normalize_influence_strength(
                    relationship_type,
                    influence_strength,
                ),
                is_directed=self._normalize_is_directed(
                    relationship_type,
                    is_directed=is_directed,
                ),
            )
        except (ArchimateRelationshipError, ValueError) as exc:
            msg = f"Failed to create relationship: {exc}"
            raise ModelOperationError(msg) from exc

        self._apply_properties(relationship, properties)
        return relationship

    def get_relationship_by_id(
        self,
        relationship_id: str,
    ) -> PyArchimateRelationship | None:
        """Return a relationship by ID, or None when absent."""
        if self._active_model is None:
            return None
        return self._active_model.rels_dict.get(relationship_id)

    def list_relationships(
        self,
        filter_criteria: dict[str, Any] | None = None,
    ) -> list[PyArchimateRelationship]:
        """List all relationships in the active model, optionally filtered."""
        if self._active_model is None:
            return []

        relationships = list(self._active_model.relationships)
        if filter_criteria is None:
            return relationships

        relationship_type = filter_criteria.get("type")
        if relationship_type is not None:
            relationship_type = self._require_relationship_type(relationship_type)
            relationships = [
                relationship
                for relationship in relationships
                if relationship.type == relationship_type
            ]

        source_id = filter_criteria.get("source_id")
        if source_id is not None:
            relationships = [
                relationship
                for relationship in relationships
                if relationship.source.uuid == source_id
            ]

        target_id = filter_criteria.get("target_id")
        if target_id is not None:
            relationships = [
                relationship
                for relationship in relationships
                if relationship.target.uuid == target_id
            ]

        return relationships

    def update_relationship_properties(  # noqa: PLR0913
        self,
        relationship_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        properties: dict[str, str] | None = None,
        access_type: str | None = None,
        influence_strength: str | None = None,
        is_directed: bool | None = None,
    ) -> bool:
        """Update an existing relationship."""
        relationship = self.get_relationship_by_id(relationship_id)
        if relationship is None:
            return False

        if name is not None:
            relationship.name = name
        if description is not None:
            relationship.desc = description
        if access_type is not None:
            relationship.access_type = self._normalize_access_type(
                relationship.type,
                access_type,
            )
        if influence_strength is not None:
            relationship.influence_strength = self._normalize_influence_strength(
                relationship.type,
                influence_strength,
            )
        if is_directed is not None:
            relationship.is_directed = self._normalize_is_directed(
                relationship.type,
                is_directed=is_directed,
            )
        self._apply_properties(relationship, properties)
        return True

    def delete_relationship(self, relationship_id: str) -> bool:
        """Delete a relationship and pyArchimate-managed visual connections."""
        relationship = self.get_relationship_by_id(relationship_id)
        if relationship is None:
            return False
        relationship.delete()
        return True

    def map_relationship_to_detail(
        self,
        relationship: PyArchimateRelationship,
    ) -> RelationshipDetail:
        """Map a pyArchimate relationship to an API detail model."""
        return RelationshipDetail(
            id=relationship.uuid,
            name=relationship.name,
            type=relationship.type,
            description=relationship.desc,
            properties=dict(relationship.props),
            access_type=self._relationship_access_type(relationship),
            influence_strength=self._relationship_influence_strength(relationship),
            is_directed=self._relationship_is_directed(relationship),
            source_element_id=relationship.source.uuid,
            target_element_id=relationship.target.uuid,
        )

    def create_view(
        self,
        view_name: str,
        view_id: str | None = None,
        folder_path: str | None = None,
        description: str | None = None,
        properties: dict[str, str] | None = None,
    ) -> PyArchimateView:
        """Create a new view in the active model."""
        model = self._require_model()
        self._require_unused_concept_id(model, view_id, "view")
        self._require_valid_viewpoint(properties)
        view = model.add(
            concept_type="View",
            name=view_name,
            uuid=view_id,
            desc=description,
            folder=self._normalize_folder_path(folder_path, "/Views", "view"),
        )
        self._apply_properties(view, properties)
        self._apply_view_metadata(view)
        return view

    def get_view_by_id(self, view_id: str) -> PyArchimateView | None:
        """Return a view by ID, or None when absent."""
        if self._active_model is None:
            return None
        return self._active_model.views_dict.get(view_id)

    def list_views(self) -> list[PyArchimateView]:
        """List all views in the active model."""
        if self._active_model is None:
            return []
        return list(self._active_model.views)

    def update_view(
        self,
        view_id: str,
        name: str | None = None,
        description: str | None = None,
        properties: dict[str, str] | None = None,
    ) -> bool:
        """Update an existing view."""
        view = self.get_view_by_id(view_id)
        if view is None:
            return False
        self._require_valid_viewpoint(properties)

        if name is not None:
            view.name = name
        if description is not None:
            view.desc = description
        self._apply_properties(view, properties)
        self._apply_view_metadata(view)
        return True

    def delete_view(self, view_id: str) -> bool:
        """Delete a view from the active model."""
        view = self.get_view_by_id(view_id)
        if view is None:
            return False
        view.delete()
        return True

    def add_node_to_view(  # noqa: PLR0913, PLR0917
        self,
        view_id: str,
        element_id: str,
        x: int | None = None,
        y: int | None = None,
        width: int = DEFAULT_NODE_WIDTH,
        height: int = DEFAULT_NODE_HEIGHT,
        node_id: str | None = None,
    ) -> Any:
        """Add an element as a visual node to a view without overlapping nodes."""
        model = self._require_model()
        view = self.get_view_by_id(view_id)
        element = self.get_element_by_id(element_id)
        if view is None:
            msg = f"View with ID '{view_id}' not found."
            raise ViewNotFoundError(msg)
        if element is None:
            msg = f"Element with ID '{element_id}' not found."
            raise ElementNotFoundError(msg)
        self._require_unused_concept_id(model, node_id, "node")

        x, y = self._next_free_position(
            view,
            width,
            height,
            preferred_x=x,
            preferred_y=y,
        )
        return view.add(ref=element, x=x, y=y, w=width, h=height, uuid=node_id)

    def add_note_to_view(  # noqa: PLR0913, PLR0917
        self,
        view_id: str,
        text: str,
        x: int,
        y: int,
        width: int = DEFAULT_NOTE_WIDTH,
        height: int = DEFAULT_NOTE_HEIGHT,
        connect_to_node_ids: list[str] | None = None,
        note_id: str | None = None,
    ) -> dict[str, Any]:
        """Add a diagram-only note (Archi Note) to a view.

        The note is a visual `Label` node: no ArchiMate element, no
        folder, no model-tree entry, so it stays out of element queries,
        type counts and coverage. Optional connector lines are
        annotation-only and create no relationship.

        Coordinates are written exactly as given — `_next_free_position`
        is deliberately not used here, because a note annotates one
        specific spot and relocating it destroys its meaning.
        """
        model = self._require_model()
        view = self.get_view_by_id(view_id)
        if view is None:
            msg = f"View with ID '{view_id}' not found."
            raise ViewNotFoundError(msg)
        # Text is kept verbatim (multi-line notes are indented on purpose);
        # only an entirely blank note is refused.
        if not isinstance(text, str) or not text.strip():
            msg = "Note text must be a non-empty string."
            raise ModelOperationError(msg)
        self._require_unused_concept_id(model, note_id, "node")

        target_nodes = self._resolve_note_connection_targets(
            view,
            connect_to_node_ids,
        )
        note = view.add(
            node_type="Label",
            label=text,
            x=x,
            y=y,
            w=width,
            h=height,
            uuid=note_id,
        )
        connections = [
            view.connect_note(note, target_node) for target_node in target_nodes
        ]
        return {
            "node_id": note.uuid,
            "connection_ids": [connection.uuid for connection in connections],
            "connected_node_ids": [target.uuid for target in target_nodes],
            "text": text,
            "x": note.x,
            "y": note.y,
            "width": note.w,
            "height": note.h,
        }

    def _resolve_note_connection_targets(
        self,
        view: PyArchimateView,
        connect_to_node_ids: list[str] | None,
    ) -> list[Any]:
        """Resolve every note connector target before anything is created.

        Ids may be visual node ids or element ids. Resolving the whole
        list up front is what makes `add_note_to_view` atomic without a
        deepcopy rollback: an unknown id is reported while the note node
        still does not exist.
        """
        if connect_to_node_ids is None:
            return []
        if isinstance(connect_to_node_ids, str):
            msg = "connect_to_node_ids must be a list of IDs, not a single string."
            raise ModelOperationError(msg)
        node_by_id = {node.uuid: node for node in self._view_nodes_recursive(view)}
        target_nodes = []
        unknown_ids = []
        for target_id in connect_to_node_ids:
            target_node = node_by_id.get(target_id) or self._find_node_for_element(
                view,
                target_id,
            )
            if target_node is None:
                unknown_ids.append(target_id)
            else:
                target_nodes.append(target_node)
        if unknown_ids:
            msg = (
                f"Note connector targets are not visible in view '{view.name}': "
                f"{', '.join(unknown_ids)}."
            )
            raise ModelOperationError(msg, {"unknown_ids": unknown_ids})
        return target_nodes

    def add_connection_to_view(
        self,
        view_id: str,
        relationship_id: str,
        connection_id: str | None = None,
    ) -> Any:
        """Add a relationship as a visual connection to a view."""
        model = self._require_model()
        view = self.get_view_by_id(view_id)
        relationship = self.get_relationship_by_id(relationship_id)
        if view is None:
            msg = f"View with ID '{view_id}' not found."
            raise ViewNotFoundError(msg)
        if relationship is None:
            msg = f"Relationship with ID '{relationship_id}' not found."
            raise RelationshipNotFoundError(msg)
        self._require_unused_concept_id(model, connection_id, "connection")

        view_nodes = self._view_nodes_recursive(view)
        source_node = next(
            (node for node in view_nodes if node.ref == relationship.source.uuid),
            None,
        )
        target_node = next(
            (node for node in view_nodes if node.ref == relationship.target.uuid),
            None,
        )
        if source_node is None or target_node is None:
            msg = "Source or target node for relationship is not present in view."
            raise ModelOperationError(msg)

        return view.add_connection(
            ref=relationship,
            source=source_node,
            target=target_node,
            uuid=connection_id,
        )

    def add_archimate_elements(
        self,
        element_specs: list[dict[str, Any]],
        *,
        rollback_on_error: bool = True,
    ) -> list[PyArchimateElement]:
        """Add multiple elements, optionally rolling back the whole batch."""
        self._require_model()

        def operation() -> list[PyArchimateElement]:
            elements = []
            for index, spec in enumerate(element_specs):
                self._require_spec_mapping(spec, f"elements[{index}]")
                elements.append(
                    self.add_archimate_element(
                        name=self._required_spec_value(
                            spec,
                            "name",
                            f"elements[{index}]",
                        ),
                        element_type=self._required_spec_value(
                            spec,
                            "element_type",
                            f"elements[{index}]",
                            fallback_key="type",
                        ),
                        description=spec.get("description"),
                        folder_path=spec.get("folder_path"),
                        properties=spec.get("properties"),
                        element_id=spec.get("element_id") or spec.get("id"),
                    ),
                )
            return elements

        return self._run_with_rollback(operation, rollback_on_error=rollback_on_error)

    def add_archimate_relationships(
        self,
        relationship_specs: list[dict[str, Any]],
        *,
        rollback_on_error: bool = True,
    ) -> list[PyArchimateRelationship]:
        """Add multiple relationships, optionally rolling back the whole batch."""
        self._require_model()

        def operation() -> list[PyArchimateRelationship]:
            relationships = []
            for index, spec in enumerate(relationship_specs):
                self._require_spec_mapping(spec, f"relationships[{index}]")
                relationships.append(
                    self.add_archimate_relationship(
                        source_id=self._required_spec_value(
                            spec,
                            "source_id",
                            f"relationships[{index}]",
                            fallback_key="source",
                        ),
                        target_id=self._required_spec_value(
                            spec,
                            "target_id",
                            f"relationships[{index}]",
                            fallback_key="target",
                        ),
                        relationship_type=self._required_spec_value(
                            spec,
                            "relationship_type",
                            f"relationships[{index}]",
                            fallback_key="type",
                        ),
                        name=spec.get("name"),
                        description=spec.get("description"),
                        properties=spec.get("properties"),
                        access_type=spec.get("access_type"),
                        influence_strength=spec.get("influence_strength"),
                        is_directed=spec.get("is_directed"),
                        relationship_id=spec.get("relationship_id") or spec.get("id"),
                        semantic_validation=spec.get(
                            "semantic_validation",
                            "off",
                        ),
                    ),
                )
            return relationships

        return self._run_with_rollback(operation, rollback_on_error=rollback_on_error)

    def add_nodes_to_view(
        self,
        view_id: str,
        node_specs: list[dict[str, Any]],
        *,
        rollback_on_error: bool = True,
    ) -> list[Any]:
        """Add multiple visual nodes to a view."""
        self._require_model()

        def operation() -> list[Any]:
            nodes = []
            for index, spec in enumerate(node_specs):
                self._require_spec_mapping(spec, f"nodes[{index}]")
                nodes.append(
                    self.add_node_to_view(
                        view_id=view_id,
                        element_id=self._required_spec_value(
                            spec,
                            "element_id",
                            f"nodes[{index}]",
                            fallback_key="element",
                        ),
                        x=spec.get("x"),
                        y=spec.get("y"),
                        width=spec.get("width", DEFAULT_NODE_WIDTH),
                        height=spec.get("height", DEFAULT_NODE_HEIGHT),
                        node_id=spec.get("node_id") or spec.get("id"),
                    ),
                )
            return nodes

        return self._run_with_rollback(operation, rollback_on_error=rollback_on_error)

    def add_connections_to_view(
        self,
        view_id: str,
        connection_specs: list[dict[str, Any]],
        *,
        rollback_on_error: bool = True,
    ) -> list[Any]:
        """Add multiple visual relationship connections to a view."""
        self._require_model()

        def operation() -> list[Any]:
            connections = []
            for index, spec in enumerate(connection_specs):
                self._require_spec_mapping(spec, f"connections[{index}]")
                connections.append(
                    self.add_connection_to_view(
                        view_id=view_id,
                        relationship_id=self._required_spec_value(
                            spec,
                            "relationship_id",
                            f"connections[{index}]",
                            fallback_key="relationship",
                        ),
                        connection_id=spec.get("connection_id") or spec.get("id"),
                    ),
                )
            return connections

        return self._run_with_rollback(operation, rollback_on_error=rollback_on_error)

    def connect_visible_relationships(
        self,
        view_id: str,
        *,
        rollback_on_error: bool = True,
        detail: str = "summary",
    ) -> dict[str, Any]:
        """Add connections for all relationships whose endpoints are visible.

        `detail="summary"` (the default) reports the skips by count
        only. Every relationship in the model that is not drawable here
        is skipped, so on a multi-view model the id list is nearly the
        whole relationship set — 112 ids on the first view of a
        143-relationship model — and every one of those skips is
        expected.
        """
        detail_level = self.normalize_detail_level(detail)
        self._require_model()
        view = self.get_view_by_id(view_id)
        if view is None:
            msg = f"View with ID '{view_id}' not found."
            raise ViewNotFoundError(msg)

        def operation() -> dict[str, Any]:
            visible_element_ids = {
                node.ref for node in self._view_nodes_recursive(view) if node.ref
            }
            existing_relationship_ids = {conn.ref for conn in view.conns if conn.ref}
            added_connections = []
            skipped_relationship_ids = []
            for relationship in self.list_relationships():
                source_id = relationship.source.uuid
                target_id = relationship.target.uuid
                if (
                    source_id not in visible_element_ids
                    or target_id not in visible_element_ids
                    or relationship.uuid in existing_relationship_ids
                ):
                    skipped_relationship_ids.append(relationship.uuid)
                    continue
                added_connections.append(
                    self.add_connection_to_view(view_id, relationship.uuid),
                )
                existing_relationship_ids.add(relationship.uuid)
            result = {
                "detail": detail_level,
                "connection_ids": [connection.uuid for connection in added_connections],
                "added_count": len(added_connections),
                "skipped_count": len(skipped_relationship_ids),
            }
            if detail_level == "full":
                result["skipped_relationship_ids"] = skipped_relationship_ids
            return result

        return self._run_with_rollback(operation, rollback_on_error=rollback_on_error)

    def ensure_all_relationships_in_views(
        self,
        *,
        coverage_view_name: str = "Relationship Coverage",
        auto_layout: bool = True,
        layout_strategy: str = "layered_by_type",
        layout_engine: str = "internal",
        rollback_on_error: bool = True,
    ) -> dict[str, Any]:
        """Render every relationship in at least one view."""
        model = self._require_model()
        # Validated unconditionally so a typo is never swallowed on the
        # auto_layout=False path.
        self._normalize_layout_strategy(layout_strategy)
        normalized_engine = self._normalize_layout_engine(layout_engine)
        if normalized_engine != "internal":
            msg = (
                f"Layout engine '{layout_engine}' cannot be used for coverage "
                f"views: the coverage layout is a fixed source/target pair "
                f'grid. Use layout_engine="internal" (the default) here.'
            )
            raise ModelOperationError(
                msg,
                {"remedy": "internal", "supported_engines": ["internal"]},
            )

        def operation() -> dict[str, Any]:
            coverage_view = None
            relocated = self._relocate_group_containment_connections_to_coverage(
                coverage_view_name,
            )
            if relocated["coverage_view_id"] is not None:
                coverage_view = self.get_view_by_id(relocated["coverage_view_id"])

            used_relationship_ids = self._relationship_ids_used_in_views()
            added_connection_ids = []
            added_node_ids = []
            skipped_relationship_ids = []
            coverage_index = (
                len(coverage_view.conns) if coverage_view is not None else 0
            )

            for relationship in model.relationships:
                if relationship.uuid in used_relationship_ids:
                    continue
                source_id = relationship.source.uuid
                target_id = relationship.target.uuid
                if (
                    source_id not in model.elems_dict
                    or target_id not in model.elems_dict
                ):
                    skipped_relationship_ids.append(relationship.uuid)
                    continue

                if coverage_view is None:
                    coverage_view = self._get_or_create_coverage_view(
                        coverage_view_name,
                    )
                source_node, target_node, connection = (
                    self._add_relationship_pair_to_coverage_view(
                        coverage_view,
                        relationship,
                        coverage_index,
                    )
                )
                coverage_index += 1
                added_node_ids.extend([source_node.uuid, target_node.uuid])
                added_connection_ids.append(connection.uuid)
                used_relationship_ids.add(relationship.uuid)

            if auto_layout and coverage_view is not None:
                self._layout_coverage_view_pairs(coverage_view)
                self._route_or_simplify_connections(coverage_view)

            final_used_relationship_ids = self._relationship_ids_used_in_views()
            remaining_unused_relationship_ids = [
                relationship.uuid
                for relationship in model.relationships
                if relationship.uuid not in final_used_relationship_ids
            ]
            return {
                "coverage_view_id": getattr(coverage_view, "uuid", None),
                "coverage_view_name": getattr(coverage_view, "name", None),
                "added_node_ids": added_node_ids,
                "added_nodes_count": len(added_node_ids),
                "added_connection_ids": added_connection_ids,
                "added_connections_count": len(added_connection_ids),
                "relocated_connection_ids": relocated["connection_ids"],
                "relocated_connections_count": relocated["connections_count"],
                "relocated_relationship_ids": relocated["relationship_ids"],
                "relocated_relationships_count": len(
                    relocated["relationship_ids"],
                ),
                "skipped_relationship_ids": skipped_relationship_ids,
                "skipped_relationships_count": len(skipped_relationship_ids),
                "remaining_unused_relationship_ids": remaining_unused_relationship_ids,
                "remaining_unused_relationships_count": len(
                    remaining_unused_relationship_ids,
                ),
            }

        return self._run_with_rollback(operation, rollback_on_error=rollback_on_error)

    def create_model_from_spec(
        self,
        spec: dict[str, Any],
        *,
        rollback_on_error: bool = True,
    ) -> dict[str, Any]:
        """Create a complete model from a structured specification."""
        self._require_spec_mapping(spec, "spec")

        def operation() -> dict[str, Any]:
            model_name = self._required_spec_value(spec, "name", "spec")
            # Element/relationship/view entries all name this field
            # "description", while the read side (get_model_info) calls
            # it "documentation"; accept both at model level.
            model_description = spec.get("description")
            if model_description is None:
                model_description = spec.get("documentation")
            model_properties = spec.get("properties")
            if model_properties is not None:
                # Same guard as update_model_metadata: without it a
                # non-mapping reaches _apply_properties and raises a raw
                # AttributeError straight through the response envelope.
                self._require_spec_mapping(model_properties, "spec.properties")
            self.create_new_model(
                model_name,
                description=model_description,
                properties=model_properties,
            )
            element_id_by_ref: dict[str, str] = {}
            relationship_id_by_ref: dict[str, str] = {}
            view_id_by_ref: dict[str, str] = {}

            for index, element_spec in enumerate(spec.get("elements", [])):
                self._require_spec_mapping(element_spec, f"elements[{index}]")
                element = self.add_archimate_element(
                    name=self._required_spec_value(
                        element_spec,
                        "name",
                        f"elements[{index}]",
                    ),
                    element_type=self._required_spec_value(
                        element_spec,
                        "element_type",
                        f"elements[{index}]",
                        fallback_key="type",
                    ),
                    description=element_spec.get("description"),
                    folder_path=element_spec.get("folder_path"),
                    properties=element_spec.get("properties"),
                    element_id=element_spec.get("element_id") or element_spec.get("id"),
                )
                self._register_ref(element_id_by_ref, element_spec, element.uuid)

            for index, relationship_spec in enumerate(spec.get("relationships", [])):
                self._require_spec_mapping(
                    relationship_spec,
                    f"relationships[{index}]",
                )
                source_ref = self._required_spec_value(
                    relationship_spec,
                    "source_id",
                    f"relationships[{index}]",
                    fallback_key="source",
                )
                target_ref = self._required_spec_value(
                    relationship_spec,
                    "target_id",
                    f"relationships[{index}]",
                    fallback_key="target",
                )
                relationship = self.add_archimate_relationship(
                    source_id=element_id_by_ref.get(source_ref, source_ref),
                    target_id=element_id_by_ref.get(target_ref, target_ref),
                    relationship_type=self._required_spec_value(
                        relationship_spec,
                        "relationship_type",
                        f"relationships[{index}]",
                        fallback_key="type",
                    ),
                    name=relationship_spec.get("name"),
                    description=relationship_spec.get("description"),
                    properties=relationship_spec.get("properties"),
                    access_type=relationship_spec.get("access_type"),
                    influence_strength=relationship_spec.get("influence_strength"),
                    is_directed=relationship_spec.get("is_directed"),
                    relationship_id=relationship_spec.get("relationship_id")
                    or relationship_spec.get("id"),
                    semantic_validation=relationship_spec.get(
                        "semantic_validation",
                        "off",
                    ),
                )
                self._register_ref(
                    relationship_id_by_ref,
                    relationship_spec,
                    relationship.uuid,
                )

            created_view_ids = []
            for index, view_spec in enumerate(spec.get("views", [])):
                self._require_spec_mapping(view_spec, f"views[{index}]")
                view = self.create_view(
                    self._required_spec_value(
                        view_spec,
                        "name",
                        f"views[{index}]",
                        fallback_key="view_name",
                    ),
                    view_id=view_spec.get("view_id") or view_spec.get("id"),
                    folder_path=view_spec.get("folder_path"),
                    description=view_spec.get("description"),
                    properties=view_spec.get("properties"),
                )
                created_view_ids.append(view.uuid)
                self._register_ref(view_id_by_ref, view_spec, view.uuid)

                node_specs = []
                for node_spec in view_spec.get("nodes", []):
                    self._require_spec_mapping(node_spec, "view node")
                    element_ref = self._required_spec_value(
                        node_spec,
                        "element_id",
                        "view node",
                        fallback_key="element",
                    )
                    node_specs.append(
                        {
                            **node_spec,
                            "element_id": element_id_by_ref.get(
                                element_ref,
                                element_ref,
                            ),
                        },
                    )
                self.add_nodes_to_view(view.uuid, node_specs, rollback_on_error=False)

                if view_spec.get("connect_visible_relationships"):
                    self.connect_visible_relationships(
                        view.uuid,
                        rollback_on_error=False,
                    )
                else:
                    connection_specs = []
                    for connection_spec in view_spec.get("connections", []):
                        self._require_spec_mapping(connection_spec, "view connection")
                        relationship_ref = self._required_spec_value(
                            connection_spec,
                            "relationship_id",
                            "view connection",
                            fallback_key="relationship",
                        )
                        connection_specs.append(
                            {
                                **connection_spec,
                                "relationship_id": relationship_id_by_ref.get(
                                    relationship_ref,
                                    relationship_ref,
                                ),
                            },
                        )
                    self.add_connections_to_view(
                        view.uuid,
                        connection_specs,
                        rollback_on_error=False,
                    )

                if view_spec.get("auto_layout"):
                    self.auto_layout_view(
                        view.uuid,
                        strategy=view_spec.get("layout_strategy", "layered_by_type"),
                        layout_engine=view_spec.get("layout_engine", "internal"),
                    )

            return {
                "model_info": self.get_model_info(),
                "element_ids_by_ref": element_id_by_ref,
                "relationship_ids_by_ref": relationship_id_by_ref,
                "view_ids_by_ref": view_id_by_ref,
                "created_view_ids": created_view_ids,
            }

        return self._run_with_rollback(operation, rollback_on_error=rollback_on_error)

    def auto_layout_view(  # noqa: PLR0913, PLR0917
        self,
        view_id: str,
        strategy: str = "layered_by_type",
        layout_engine: str = "internal",
        margin_x: int = DEFAULT_MARGIN_X,
        margin_y: int = DEFAULT_MARGIN_Y,
        x_gap: int = DEFAULT_X_GAP,
        y_gap: int = DEFAULT_Y_GAP,
        *,
        layer_bands: bool = True,
    ) -> ViewDetail:
        """Reposition all nodes in a view using a simple non-overlapping layout."""
        view = self.get_view_by_id(view_id)
        if view is None:
            msg = f"View with ID '{view_id}' not found."
            raise ViewNotFoundError(msg)

        normalized_strategy = self._normalize_layout_strategy(strategy)
        normalized_engine = self._normalize_layout_engine(layout_engine)

        # Shared prologue — runs for BOTH engines. Every step here is
        # correctness or repair rather than placement aesthetics, so
        # branching any of it away would regress the model. Removing
        # layer bands first is load-bearing for the upstream engine in
        # particular: bands are top-level Containers far wider than a
        # grid cell, so leaving them would guarantee overlaps.
        layout.remove_layer_bands(view)
        layout.normalize_view_node_sizes(view)
        layout.nest_grouped_nodes(view)

        # Notes are pinned across every pass that can move a node:
        # captured once here and restored once below, deliberately
        # outside the engine branch so both engines behave identically.
        # A note annotates one specific spot, so no placement pass may
        # relocate it. This capture MUST sit after the last reparenting
        # step (`nest_grouped_nodes`) so a nested note's offset is taken
        # against its final parent, and before the first placement step
        # (`layout_group_children_for_view`, which lane-places a group's
        # children) so the pinned position is the caller's, not one a
        # prologue pass already overwrote.
        pinned_notes = layout.note_positions(view)

        # Size groups to their members BEFORE lane placement so lanes
        # account for the grown group bounds instead of overlapping them.
        layout.layout_group_children_for_view(view)
        layout.apply_relationship_label_policy(view)
        layout.apply_group_containment_connection_policy(view)

        if normalized_engine == "pyarchimate":
            # Guard before any placement write, so a refusal leaves the
            # view exactly as the prologue left it — never half laid out.
            self._require_pyarchimate_layout_is_safe(view)
            try:
                layout.layout_nodes_pyarchimate(view)
            except RuntimeError as exc:
                raise ModelOperationError(str(exc)) from exc
            # Re-pin group children to their group's final position.
            layout.layout_group_children_for_view(view)
            # No layer bands: upstream's own layer buckets disagree with
            # the MCP band labels, so band members come out
            # non-contiguous and the band rectangles interleave.
            band_outcome = {
                "created": 0,
                "reason": layout.LAYER_BAND_SKIP_ENGINE,
            }
        else:
            nodes = layout.placeable_nodes(view.nodes)
            x_gap, y_gap = layout.label_aware_gaps(
                view,
                self._view_nodes_recursive(view),
                x_gap,
                y_gap,
            )
            if normalized_strategy == "grid":
                layout.layout_nodes_grid(nodes, margin_x, margin_y, x_gap, y_gap)
            elif normalized_strategy == "layered":
                layout.layout_nodes_layered(
                    view,
                    nodes,
                    margin_x,
                    margin_y,
                    x_gap,
                    y_gap,
                )
            else:
                layout.layout_nodes_by_type(
                    view,
                    nodes,
                    margin_x,
                    margin_y,
                    x_gap,
                    y_gap,
                )
            # Re-pin group children to their group's final position.
            layout.layout_group_children_for_view(view)
            if not layer_bands:
                band_outcome = {
                    "created": 0,
                    "reason": layout.LAYER_BAND_SKIP_NOT_REQUESTED,
                }
            elif normalized_strategy != "layered_by_type":
                band_outcome = {
                    "created": 0,
                    "reason": layout.LAYER_BAND_SKIP_STRATEGY,
                }
            else:
                band_outcome = layout.add_layer_bands(view)

        # Restore before routing, so the obstacle map sees notes where
        # they will actually be drawn rather than where a placement pass
        # briefly moved them.
        layout.restore_note_positions(view, pinned_notes)

        # Shared epilogue — MCP routing runs under both engines. It
        # consumes only final node geometry, and it clears bendpoints
        # before re-routing, so placement can never strand a waypoint.
        self._route_or_simplify_connections(view)
        detail = self.map_view_to_detail(view)
        detail.layer_bands_created = band_outcome["created"]
        detail.layer_bands_reason = band_outcome["reason"]
        return detail

    def auto_layout_all_views(
        self,
        strategy: str = "layered_by_type",
        layout_engine: str = "internal",
        *,
        layer_bands: bool = True,
    ) -> list[ViewDetail]:
        """Reposition nodes in every view using a simple non-overlapping layout."""
        model = self._require_model()
        normalized_strategy = self._normalize_layout_strategy(strategy)
        normalized_engine = self._normalize_layout_engine(layout_engine)
        return [
            self.auto_layout_view(
                view.uuid,
                strategy=normalized_strategy,
                layout_engine=normalized_engine,
                layer_bands=layer_bands,
            )
            for view in model.views
        ]

    def map_view_to_detail(self, view: PyArchimateView) -> ViewDetail:
        """Map a pyArchimate view to an API detail model."""
        nodes = []
        for node in self._view_nodes_recursive(view):
            concept = node.concept if node.ref else None
            nodes.append(
                ViewNode(
                    id=node.uuid,
                    element_id=node.ref,
                    element_name=getattr(concept, "name", None),
                    element_type=getattr(concept, "type", None),
                    parent_node_id=self._node_parent_id(node),
                    # Without this a note reads back as an anonymous node
                    # with no element and no text at all.
                    note_text=node.label if layout.is_note_node(node) else None,
                    x=node.x,
                    y=node.y,
                    width=node.w,
                    height=node.h,
                ),
            )

        connections = []
        for connection in view.conns:
            concept = connection.concept if connection.ref else None
            connections.append(
                ViewConnection(
                    id=connection.uuid,
                    relationship_id=connection.ref,
                    relationship_type=getattr(concept, "type", None),
                    source_node_id=connection.source.uuid,
                    target_node_id=connection.target.uuid,
                ),
            )

        return ViewDetail(
            id=view.uuid,
            name=view.name,
            description=getattr(view, "desc", None),
            properties=dict(getattr(view, "props", {})),
            metadata=self._view_metadata(view),
            primary_viewpoint=getattr(view, "primary_viewpoint", None),
            nodes=nodes,
            connections=connections,
        )

    def query_elements(
        self,
        query_criteria: dict[str, Any],
    ) -> list[PyArchimateElement]:
        """Query elements using supported list filters."""
        return self.list_elements(filter_criteria=query_criteria)

    def query_relationships(
        self,
        query_criteria: dict[str, Any],
    ) -> list[PyArchimateRelationship]:
        """Query relationships using supported list filters."""
        return self.list_relationships(filter_criteria=query_criteria)

    def export_elements_to_csv(self) -> str:
        """Export all elements in the active model to CSV."""
        model = self._require_model()
        rows: list[list[str]] = []
        property_keys = self._get_all_property_keys("element")
        rows.append(
            ["id", "name", "type", "description"]
            + [f"Property:{key}" for key in property_keys],
        )

        rows.extend(
            [
                element.uuid,
                element.name or "",
                element.type,
                element.desc or "",
                *[element.prop(key) or "" for key in property_keys],
            ]
            for element in model.elements
        )

        return self._rows_to_csv(rows)

    def export_relationships_to_csv(self) -> str:
        """Export all relationships in the active model to CSV."""
        model = self._require_model()
        rows: list[list[str]] = []
        property_keys = self._get_all_property_keys("relationship")
        rows.append(
            [
                "id",
                "name",
                "type",
                "source_id",
                "target_id",
                "access_type",
                "influence_strength",
                "is_directed",
            ]
            + [f"Property:{key}" for key in property_keys],
        )

        rows.extend(
            [
                relationship.uuid,
                relationship.name or "",
                relationship.type,
                relationship.source.uuid,
                relationship.target.uuid,
                self._relationship_access_type(relationship) or "",
                self._relationship_influence_strength(relationship) or "",
                (
                    ""
                    if self._relationship_is_directed(relationship) is None
                    else str(self._relationship_is_directed(relationship)).lower()
                ),
                *[relationship.prop(key) or "" for key in property_keys],
            ]
            for relationship in model.relationships
        )

        return self._rows_to_csv(rows)

    def list_supported_types(self) -> dict[str, Any]:
        """Return ArchiMate concept types supported by this MCP instance."""
        element_types_by_category: dict[str, list[str]] = defaultdict(list)
        for element_type in ARCHIMATE_ELEMENT_TYPES:
            element_types_by_category[ARCHI_CATEGORY[element_type]].append(element_type)

        rule_metadata = backend_metadata()
        return {
            "element_types_by_category": {
                category: sorted(types)
                for category, types in sorted(element_types_by_category.items())
            },
            "relationship_types": ARCHIMATE_RELATIONSHIP_TYPES,
            "viewpoints": viewpoint_catalogs(),
            "folder_roots": list(ARCHI_ROOT_FOLDERS),
            "folder_aliases": dict(sorted(ARCHI_ROOT_ALIASES.items())),
            "access_types": sorted(SUPPORTED_ACCESS_TYPES),
            "influence_strengths": sorted(SUPPORTED_INFLUENCE_STRENGTHS),
            "association_is_directed": [True, False],
            "semantic_validation_modes": sorted(SUPPORTED_SEMANTIC_VALIDATION_MODES),
            "quality_gates": sorted(SUPPORTED_QUALITY_GATES),
            "relationship_rule_metadata": rule_metadata,
            "relationship_recommendation_intents": sorted(SUPPORTED_INTENTS),
            "layout_strategies": sorted(SUPPORTED_LAYOUT_STRATEGIES),
            "layout_engines": sorted(SUPPORTED_LAYOUT_ENGINES),
            "summary": {
                "element_type_count": len(ARCHIMATE_ELEMENT_TYPES),
                "relationship_type_count": len(ARCHIMATE_RELATIONSHIP_TYPES),
                "supports_views": True,
                "source": f"{rule_metadata['backend']} ARCHI_CATEGORY",
            },
        }

    def count_by_type(self) -> dict[str, Any]:
        """Return active model counts grouped by ArchiMate type."""
        model = self._require_model()
        return {
            "elements": dict(
                sorted(Counter(element.type for element in model.elements).items()),
            ),
            "relationships": dict(
                sorted(
                    Counter(
                        relationship.type for relationship in model.relationships
                    ).items(),
                ),
            ),
            "views": len(model.views),
        }

    def summarize_model(self) -> dict[str, Any]:
        """Return a compact active model summary."""
        model = self._require_model()
        element_counts_by_type = Counter(element.type for element in model.elements)
        element_counts_by_category = Counter(
            ARCHI_CATEGORY.get(element.type, "Other") for element in model.elements
        )
        relationship_counts_by_type = Counter(
            relationship.type for relationship in model.relationships
        )
        elements_in_views = {
            node.ref
            for view in model.views
            for node in self._view_nodes_recursive(view)
            if node.ref
        }
        return {
            "model_info": self.get_model_info(),
            "element_counts_by_type": dict(sorted(element_counts_by_type.items())),
            "element_counts_by_category": dict(
                sorted(element_counts_by_category.items()),
            ),
            "relationship_counts_by_type": dict(
                sorted(relationship_counts_by_type.items()),
            ),
            "view_summaries": [
                {
                    "id": view.uuid,
                    "name": view.name,
                    "nodes_count": len(self._view_nodes_recursive(view)),
                    "connections_count": len(view.conns),
                }
                for view in model.views
            ],
            "elements_not_in_any_view_count": len(
                [
                    element
                    for element in model.elements
                    if element.uuid not in elements_in_views
                ],
            ),
        }

    def summarize_view(self, view_id: str) -> dict[str, Any]:
        """Return a compact summary of a view."""
        view = self.get_view_by_id(view_id)
        if view is None:
            msg = f"View with ID '{view_id}' not found."
            raise ViewNotFoundError(msg)
        view_nodes = self._view_nodes_recursive(view)
        node_type_counts = Counter(
            getattr(node.concept, "type", None) or "Unknown" for node in view_nodes
        )
        connection_type_counts = Counter(
            getattr(connection.concept, "type", None) or "Unknown"
            for connection in view.conns
        )
        visible_element_ids = {node.ref for node in view_nodes if node.ref}
        visible_relationship_ids = {conn.ref for conn in view.conns if conn.ref}
        connectable_relationship_ids = [
            relationship.uuid
            for relationship in self.list_relationships()
            if relationship.source.uuid in visible_element_ids
            and relationship.target.uuid in visible_element_ids
            and relationship.uuid not in visible_relationship_ids
        ]
        return {
            "id": view.uuid,
            "name": view.name,
            "nodes_count": len(view_nodes),
            "connections_count": len(view.conns),
            "node_counts_by_type": dict(sorted(node_type_counts.items())),
            "connection_counts_by_type": dict(sorted(connection_type_counts.items())),
            "connectable_relationship_ids": connectable_relationship_ids,
            "connectable_relationships_count": len(connectable_relationship_ids),
        }

    def list_orphan_elements(self) -> dict[str, Any]:
        """List elements with no relationships or no view placement."""
        model = self._require_model()
        related_element_ids = {
            relationship.source.uuid for relationship in model.relationships
        } | {relationship.target.uuid for relationship in model.relationships}
        visible_element_ids = {
            node.ref
            for view in model.views
            for node in self._view_nodes_recursive(view)
            if node.ref
        }
        without_relationships = [
            self.map_element_to_detail(element).model_dump()
            for element in model.elements
            if element.uuid not in related_element_ids
        ]
        not_in_any_view = [
            self.map_element_to_detail(element).model_dump()
            for element in model.elements
            if element.uuid not in visible_element_ids
        ]
        fully_orphaned = [
            element
            for element in without_relationships
            if element["id"] not in visible_element_ids
        ]
        return {
            "without_relationships": without_relationships,
            "without_relationships_count": len(without_relationships),
            "not_in_any_view": not_in_any_view,
            "not_in_any_view_count": len(not_in_any_view),
            "fully_orphaned": fully_orphaned,
            "fully_orphaned_count": len(fully_orphaned),
        }

    def validate_semantics(self, *, detail: str = "summary") -> dict[str, Any]:
        """Run semantic checks beyond pyArchimate visual reference validation.

        `detail="summary"` (the default) groups the issues by code
        instead of returning one dict per issue. The completeness
        checks fire once per element and once per relationship, so a
        mid-build model of 71 elements and 143 relationships produced
        214 near-identical issue dicts — ~55 KB, of which the repeated
        `code`, `severity` and `message` strings were most of the
        weight. Error-severity issues are never grouped away: they are
        returned in full under `errors`, so `is_valid=false` always
        arrives with its reason attached.
        """
        detail_level = self.normalize_detail_level(detail)
        model = self._require_model()
        issues = []

        # Deliberately NOT replaced by pyArchimate's own
        # `check_invalid_relationships`. The verdicts are identical, but
        # upstream calls `check_valid_relationship` *without*
        # `raise_flg=True`, so it throws away the reason string and
        # returns bare relationship ids. `_semantic_relationship_issue`
        # passes `raise_flg=True` precisely to capture `str(exc)`, then
        # enriches it through `relationship_issue_details` with source
        # and target names/types, `valid_alternatives`,
        # `suggested_repairs` and `requires_decision`. Collapsing this
        # into the upstream call would silently starve
        # `repair_semantic_issues` and the did-you-mean suggestions in
        # `error.details`.
        issues.extend(
            issue
            for relationship in model.relationships
            if (issue := self._semantic_relationship_issue(relationship)) is not None
        )

        issues.extend(
            {
                "code": "EMPTY_VIEW",
                "severity": "warning",
                "message": "View has no diagram objects.",
                "view_id": view.uuid,
                "view_name": view.name,
            }
            for view in model.views
            if not self._view_nodes_recursive(view) and not view.conns
        )

        # A view node whose backing element is gone is NOT checked here.
        # `validate_model` already reports it through pyArchimate's
        # `check_invalid_nodes`, which is the stronger of the two (it
        # also catches an `Element`-cat node carrying no ref at all).
        # `build_quality_report` puts visual and semantic validation side
        # by side, so emitting it in both counted one dangling node
        # twice.
        issues.extend(self._invalid_nested_element_issues())
        issues.extend(self._junction_consistency_issues())

        # Archi's Validator flags duplicate names per element type across
        # the whole model, not per folder — match that scope.
        names_by_type: dict[tuple[str, str], list[str]] = defaultdict(list)
        for element in model.elements:
            names_by_type[(element.type, element.name or "")].append(element.uuid)
        for (element_type, name), ids in names_by_type.items():
            if name and len(ids) > 1:
                issues.append(
                    {
                        "code": "DUPLICATE_ELEMENT_NAME",
                        "message": (f'Duplicate {element_type} name "{name}" in model'),
                        "element_ids": ids,
                        "element_type": element_type,
                        "name": name,
                    },
                )

        orphan_data = self.list_orphan_elements()
        issues.extend(
            {
                "code": "ELEMENT_NOT_IN_ANY_VIEW",
                "severity": "warning",
                "message": "Element is not included in any view.",
                "element_id": element["id"],
                "element_name": element["name"],
                "element_type": element["type"],
            }
            for element in orphan_data["not_in_any_view"]
        )

        used_relationship_ids = self._relationship_ids_used_in_views()
        issues.extend(
            {
                "code": "RELATIONSHIP_NOT_IN_ANY_VIEW",
                "severity": "warning",
                "message": "Relationship is not included in any view.",
                "relationship_id": relationship.uuid,
                "relationship_name": relationship.name,
                "relationship_type": relationship.type,
                "source_element_id": relationship.source.uuid,
                "target_element_id": relationship.target.uuid,
            }
            for relationship in model.relationships
            if relationship.uuid not in used_relationship_ids
        )

        issues.extend(
            {
                "code": "ORPHAN_SERVICE_OR_DATA",
                "severity": "warning",
                "message": "Service or data element has no relationships.",
                "element_id": element["id"],
                "element_name": element["name"],
                "element_type": element["type"],
            }
            for element in orphan_data["without_relationships"]
            if element["type"].endswith(("Service", "Object"))
            or element["type"] in {"DataObject", "BusinessObject"}
        )

        errors = [
            issue for issue in issues if issue.get("severity", "error") == "error"
        ]
        result: dict[str, Any] = {
            "detail": detail_level,
            "is_valid": not errors,
            "issues_count": len(issues),
            "issue_counts": self._semantic_issue_counts(issues),
        }
        if detail_level == "full":
            result["issues"] = issues
            return result
        # No "issues" key in the summary on purpose: a caller that
        # still reads it must break loudly rather than silently read a
        # shorter list than it believes it asked for.
        result["issues_by_code"] = self._semantic_issues_by_code(issues)
        result["errors"] = errors
        return result

    def repair_semantic_issues(  # noqa: PLR0913
        self,
        *,
        repair_ids: list[str] | None = None,
        repair_all_deterministic: bool = False,
        preserve_relationship_ids: bool = True,
        rollback_on_error: bool = True,
        update_views: bool = True,
        auto_layout: bool = False,
    ) -> dict[str, Any]:
        """Apply selected deterministic semantic repairs."""
        selected_repair_ids = set(repair_ids or [])
        if not selected_repair_ids and not repair_all_deterministic:
            msg = "Provide repair_ids or set repair_all_deterministic=true."
            raise ModelOperationError(msg)

        def operation() -> dict[str, Any]:
            applied = []
            skipped = []
            issues = self.validate_semantics(detail="full")["issues"]
            repairs = [
                (issue, repair)
                for issue in issues
                for repair in issue.get("suggested_repairs", [])
                if repair.get("deterministic")
                and (
                    repair_all_deterministic
                    or repair.get("repair_id") in selected_repair_ids
                )
            ]
            for issue, repair in repairs:
                relationship = self.get_relationship_by_id(
                    issue.get("relationship_id"),
                )
                if relationship is None:
                    skipped.append(
                        {
                            "repair_id": repair.get("repair_id"),
                            "reason": "relationship_not_found",
                        },
                    )
                    continue
                view_ids = [
                    view.uuid
                    for view in self._require_model().views
                    if any(conn.ref == relationship.uuid for conn in view.conns)
                ]
                old_id = relationship.uuid
                old_detail = self.map_relationship_to_detail(relationship).model_dump()
                new_relationship_id = old_id if preserve_relationship_ids else None
                relationship.delete()
                new_access_type = (
                    repair.get("access_type") or old_detail.get("access_type")
                    if repair["new_type"] == "Access"
                    else None
                )
                new_influence_strength = (
                    repair.get("influence_strength")
                    or old_detail.get("influence_strength")
                    if repair["new_type"] == "Influence"
                    else None
                )
                new_is_directed = (
                    repair.get("is_directed")
                    if "is_directed" in repair
                    else old_detail.get("is_directed")
                )
                if repair["new_type"] != "Association":
                    new_is_directed = None
                new_relationship = self.add_archimate_relationship(
                    source_id=repair["new_source_id"],
                    target_id=repair["new_target_id"],
                    relationship_type=repair["new_type"],
                    name=old_detail.get("name"),
                    description=old_detail.get("description"),
                    properties=old_detail.get("properties"),
                    access_type=new_access_type,
                    influence_strength=new_influence_strength,
                    is_directed=new_is_directed,
                    relationship_id=new_relationship_id,
                    semantic_validation="strict",
                )
                reconnected_view_ids = []
                if update_views:
                    for view_id in view_ids:
                        try:
                            self.add_connection_to_view(view_id, new_relationship.uuid)
                            reconnected_view_ids.append(view_id)
                        except ModelOperationError:  # noqa: PERF203
                            continue
                applied.append(
                    {
                        "repair_id": repair.get("repair_id"),
                        "old_relationship_id": old_id,
                        "new_relationship_id": new_relationship.uuid,
                        "new_type": new_relationship.type,
                        "reconnected_view_ids": reconnected_view_ids,
                    },
                )
            if auto_layout:
                self.auto_layout_all_views()
            return {
                "applied_repairs": applied,
                "applied_count": len(applied),
                "skipped_repairs": skipped,
                "skipped_count": len(skipped),
            }

        return self._run_with_rollback(operation, rollback_on_error=rollback_on_error)

    def _semantic_relationship_issue(
        self,
        relationship: PyArchimateRelationship,
    ) -> dict[str, Any] | None:
        try:
            check_valid_relationship(
                relationship.type,
                relationship.source.type,
                relationship.target.type,
                raise_flg=True,
            )
        except (ArchimateConceptTypeError, ArchimateRelationshipError) as exc:
            issue = relationship_issue_details(
                relationship.type,
                relationship.source.type,
                relationship.target.type,
                source_id=relationship.source.uuid,
                target_id=relationship.target.uuid,
                source_name=relationship.source.name,
                target_name=relationship.target.name,
                relationship_id=relationship.uuid,
                relationship_name=relationship.name,
            )
            issue["message"] = str(exc)
            return issue
        return None

    def _invalid_nested_element_issues(self) -> list[dict[str, Any]]:
        issues = []
        for view in self._require_model().views:
            for node in self._view_nodes_recursive(view):
                parent_id = self._node_parent_id(node)
                if parent_id is None or not node.ref:
                    continue
                parent = self._active_model.nodes_dict.get(parent_id)
                if parent is None or not getattr(parent, "ref", None):
                    continue
                if self._has_nesting_relationship(parent.ref, node.ref):
                    continue
                issues.append(
                    {
                        "code": "INVALID_NESTED_ELEMENTS",
                        "severity": "warning",
                        "message": (
                            "Nested visual elements do not have a Composition, "
                            "Aggregation, Association, or valid Grouping relationship."
                        ),
                        "view_id": view.uuid,
                        "parent_node_id": parent_id,
                        "child_node_id": node.uuid,
                        "parent_element_id": parent.ref,
                        "child_element_id": node.ref,
                    },
                )
        return issues

    def _has_nesting_relationship(
        self,
        parent_element_id: str,
        child_element_id: str,
    ) -> bool:
        for relationship in self.list_relationships():
            if (
                relationship.source.uuid == parent_element_id
                and relationship.target.uuid == child_element_id
                and relationship.type in {"Composition", "Aggregation", "Association"}
            ):
                return True
            if (
                relationship.source.uuid == parent_element_id
                and relationship.target.uuid == child_element_id
                and relationship.source.type == "Grouping"
            ):
                return True
        return False

    def _junction_consistency_issues(self) -> list[dict[str, Any]]:
        types_by_junction: dict[str, set[str]] = defaultdict(set)
        for relationship in self.list_relationships():
            if "Junction" in relationship.source.type:
                types_by_junction[relationship.source.uuid].add(
                    relationship.type,
                )
            if "Junction" in relationship.target.type:
                types_by_junction[relationship.target.uuid].add(
                    relationship.type,
                )
        return [
            {
                "code": "INCONSISTENT_JUNCTION_RELATIONSHIPS",
                "severity": "warning",
                "message": "Junction connects relationships of multiple types.",
                "junction_element_id": junction_id,
                "relationship_types": sorted(relationship_types),
            }
            for junction_id, relationship_types in types_by_junction.items()
            if len(relationship_types) > 1
        ]

    def _semantic_issue_subject_ids(self, issue: dict[str, Any]) -> list[str]:
        """Return the ids a single issue is about, most specific first."""
        for key in SEMANTIC_ISSUE_IDENTITY_KEYS:
            value = issue.get(key)
            if isinstance(value, list):
                return [str(item) for item in value]
            if value:
                return [str(value)]
        # A new issue code that carries none of the known subject keys
        # still contributes its ids rather than silently reporting none.
        return [
            str(value) for key, value in issue.items() if key.endswith("_id") and value
        ]

    def _semantic_issues_by_code(
        self,
        issues: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Group issues by code, keeping the ids and dropping the prose.

        The ids are what a caller acts on; `code`, `severity` and
        `message` are identical across a group and only need saying
        once.
        """
        grouped: dict[str, dict[str, Any]] = {}
        for issue in issues:
            code = str(issue.get("code", "UNKNOWN"))
            severity = str(issue.get("severity", "error"))
            group = grouped.setdefault(
                code,
                {"count": 0, "severity": severity, "ids": []},
            )
            group["count"] += 1
            # A mixed-severity group reports the worse of the two, so a
            # summary can never read as less serious than the issues.
            if severity == "error":
                group["severity"] = "error"
            group["ids"].extend(self._semantic_issue_subject_ids(issue))
        return dict(sorted(grouped.items()))

    def _semantic_issue_counts(
        self,
        issues: list[dict[str, Any]],
    ) -> dict[str, dict[str, int]]:
        by_code = Counter(str(issue.get("code", "UNKNOWN")) for issue in issues)
        by_pattern = Counter(
            "|".join(
                [
                    str(issue.get("code", "UNKNOWN")),
                    str(issue.get("relationship_type", "")),
                    str(issue.get("source_type", "")),
                    str(issue.get("target_type", "")),
                ],
            )
            for issue in issues
        )
        return {
            "by_code": dict(sorted(by_code.items())),
            "by_pattern": dict(sorted(by_pattern.items())),
        }

    def _get_all_property_keys(self, entity_type: str) -> list[str]:
        """Return all unique property keys for elements or relationships."""
        if self._active_model is None:
            return []

        if entity_type == "element":
            entities = self._active_model.elements
        else:
            entities = self._active_model.relationships

        keys = {key for entity in entities for key in entity.props}
        return sorted(keys)

    def get_incoming_relationships(
        self,
        element_id: str,
    ) -> list[PyArchimateRelationship]:
        """Return relationships where the given element is the target."""
        if self._active_model is None:
            return []
        return [
            relationship
            for relationship in self._active_model.relationships
            if relationship.target.uuid == element_id
        ]

    def get_outgoing_relationships(
        self,
        element_id: str,
    ) -> list[PyArchimateRelationship]:
        """Return relationships where the given element is the source."""
        if self._active_model is None:
            return []
        return [
            relationship
            for relationship in self._active_model.relationships
            if relationship.source.uuid == element_id
        ]

    def _normalize_folder_path_for_type(
        self,
        folder_path: str | None,
        concept_type: str,
    ) -> str | None:
        category = ARCHI_CATEGORY.get(concept_type)
        expected_root = ARCHI_FOLDER_ROOT_BY_CATEGORY.get(category or "")
        if expected_root is None:
            msg = f"Cannot resolve folder root for concept type '{concept_type}'."
            raise ModelOperationError(msg)
        return self._normalize_folder_path(
            folder_path,
            expected_root,
            f"{concept_type} element",
        )

    def _normalize_folder_path(
        self,
        folder_path: str | None,
        expected_root: str,
        entity_label: str,
    ) -> str | None:
        if folder_path is None:
            return None
        if not isinstance(folder_path, str):
            msg = f"Invalid folder path for {entity_label}; expected a string or empty."
            raise ModelOperationError(msg)
        stripped_path = folder_path.strip()
        if stripped_path in {"", "/"}:
            return None

        is_absolute = stripped_path.startswith("/")
        path_parts = [part.strip() for part in stripped_path.split("/") if part.strip()]
        if not path_parts:
            return None

        root_alias = ARCHI_ROOT_ALIASES.get(path_parts[0].casefold())
        if root_alias is None:
            if is_absolute:
                msg = (
                    f'Invalid folder path "{folder_path}" for {entity_label}; '
                    f'expected "{expected_root}" or empty.'
                )
                raise ModelOperationError(msg)
            return "/".join([expected_root, *path_parts])

        if root_alias != expected_root:
            msg = (
                f'Invalid folder path "{folder_path}" for {entity_label}; '
                f'expected "{expected_root}" or empty.'
            )
            raise ModelOperationError(msg)
        return "/".join([root_alias, *path_parts[1:]])

    def _normalize_model_folder_paths(self) -> None:
        model = self._require_model()
        issues = [
            issue
            for element in model.elements
            if (issue := self._normalize_element_folder(element)) is not None
        ]
        issues.extend(
            issue
            for relationship in model.relationships
            if (issue := self._normalize_relationship_folder(relationship)) is not None
        )
        issues.extend(
            issue
            for view in model.views
            if (issue := self._normalize_view_folder(view)) is not None
        )
        if issues:
            msg = "Invalid folder paths before export: " + "; ".join(issues)
            raise ModelOperationError(msg)

    def _normalize_element_folder(self, element: PyArchimateElement) -> str | None:
        try:
            element.folder = self._normalize_folder_path_for_type(
                element.folder,
                element.type,
            )
        except ModelOperationError as exc:
            return f'{element.type} "{element.name}" ({element.uuid}): {exc}'
        return None

    def _normalize_relationship_folder(
        self,
        relationship: PyArchimateRelationship,
    ) -> str | None:
        try:
            relationship.folder = self._normalize_folder_path(
                relationship.folder,
                "/Relations",
                "relationship",
            )
        except ModelOperationError as exc:
            return (
                f'{relationship.type} relationship "{relationship.name}" '
                f"({relationship.uuid}): {exc}"
            )
        return None

    def _normalize_view_folder(self, view: PyArchimateView) -> str | None:
        try:
            view.folder = self._normalize_folder_path(
                view.folder,
                "/Views",
                "view",
            )
        except ModelOperationError as exc:
            return f'view "{view.name}" ({view.uuid}): {exc}'
        return None

    def _finalize_archi_output(self, content: str) -> str:
        """Apply the Archi compatibility repairs to native `.archimate` XML.

        Stabilizes folder ids so repeated exports diff cleanly, aligns
        top-level folder labels with stock Archi, rewrites
        `influenceStrength` to Archi's native `strength`, writes canonical
        viewpoint ids, and retypes annotation-only connectors to
        `ARCHI_PLAIN_CONNECTION_TYPE` (see that constant for the
        NullPointerException the wrong type causes).
        """
        # Trusted input: this parses XML the pyArchimate writer just
        # generated in-process, never external content.
        root = etree.fromstring(content.encode("utf-8"))
        model = self._require_model()
        root.set("id", model.uuid)
        model_id = model.uuid
        desired_viewpoint_by_view_id: dict[str, str] = {}
        for view in model.views:
            raw_viewpoint = view.prop("viewpoint")
            if not raw_viewpoint:
                continue
            archi_id = ARCHI_VIEWPOINT_ID_BY_SLUG.get(
                str(raw_viewpoint),
                str(raw_viewpoint),
            )
            if archi_id in ARCHI_VIEWPOINT_IDS:
                desired_viewpoint_by_view_id[view.uuid] = archi_id
        xsi_type = XSI_TYPE_ATTRIBUTE

        def stable_id(path: str) -> str:
            digest = hashlib.sha256(f"{model_id}:folder:{path}".encode()).hexdigest()
            return f"id-{digest[:32]}"

        def update_folder(folder: etree._Element, parent_path: str) -> None:
            folder_name = folder.get("name") or folder.get("type") or "Folder"
            folder_path = (
                f"{parent_path}/{folder_name}" if parent_path else f"/{folder_name}"
            )
            folder.set("id", stable_id(folder_path))
            for child in folder.findall("folder"):
                update_folder(child, folder_path)

        for top_level_folder in root.findall("folder"):
            # Match stock Archi 5.x model-tree labels; the type attribute
            # stays authoritative, this is display-name alignment only.
            display_name = ARCHI_FOLDER_DISPLAY_NAMES.get(
                top_level_folder.get("type") or "",
            )
            if display_name:
                top_level_folder.set("name", display_name)
            update_folder(top_level_folder, "")
        for node in root.iter():
            # Keyed on the ABSENCE of archimateRelationship rather than on
            # any note/Label knowledge, so it repairs exactly the set Archi
            # would mis-instantiate and leaves concept-backed connections
            # (which carry the attribute) untouched.
            if (
                node.tag == "sourceConnection"
                and node.get(xsi_type) == ARCHI_CONCEPT_CONNECTION_TYPE
                and node.get("archimateRelationship") is None
            ):
                node.set(xsi_type, ARCHI_PLAIN_CONNECTION_TYPE)
            if (
                node.get(xsi_type) == "archimate:InfluenceRelationship"
                and "influenceStrength" in node.attrib
            ):
                node.set(
                    "strength",
                    node.attrib.pop("influenceStrength"),
                )
            # Write Archi's canonical viewpoint identifier, derived from
            # the view's "viewpoint" property (pyArchimate slugs are mapped;
            # canonical Archi ids pass through even when pyArchimate's
            # registry rejected them at set time).
            if node.get(xsi_type) == "archimate:ArchimateDiagramModel":
                desired = desired_viewpoint_by_view_id.get(node.get("id"))
                viewpoint = node.get("viewpoint")
                if desired:
                    node.set("viewpoint", desired)
                elif viewpoint in ARCHI_VIEWPOINT_ID_BY_SLUG:
                    node.set("viewpoint", ARCHI_VIEWPOINT_ID_BY_SLUG[viewpoint])
        return etree.tostring(root, encoding="unicode", pretty_print=True)

    def _sanitize_exchange_output(self, model: Model, content: str) -> str:
        """Repair the schema-invalid shapes pyArchimate's exchange writer emits.

        Two separate defects, both still present in 1.12.0, both of the
        same class — an IDREF pointing at an identifier the document
        never declares:

        1. View-level properties are written as `propertyDefinitionRef`
           without a matching `<propertyDefinition>`.
        2. Every view connection is written as
           `xsi:type="Relationship" relationshipRef="…"`, including a
           diagram-only note line, whose `ref` is a synthetic id that is
           deliberately not in `model.rels_dict`.

        See `_strip_dangling_view_properties` and
        `_rewrite_note_connectors_as_lines` for what each repair does.
        """
        # Trusted input: parses XML this process just generated.
        root = etree.fromstring(content.encode("utf-8"))
        namespace = root.tag.split("}")[0].lstrip("{")
        properties_changed = self._strip_dangling_view_properties(root, namespace)
        connectors_changed = self._rewrite_note_connectors_as_lines(
            root,
            namespace,
            model,
        )
        if not (properties_changed or connectors_changed):
            return content
        return etree.tostring(
            root,
            encoding="unicode",
            pretty_print=True,
        )

    @staticmethod
    def _strip_dangling_view_properties(root: Any, namespace: str) -> bool:
        """Drop dangling view-property references from exchange XML.

        pyArchimate's exchange writer (still true in 1.12.0) emits
        `propertyDefinitionRef` entries for view-level properties but
        never declares them in `<propertyDefinitions>`, producing
        schema-invalid XML that no reader (including pyArchimate's own)
        accepts. Until fixed upstream, strip the dangling references so
        exchange exports stay valid; view properties remain fully
        preserved in the native `archi` format.
        """
        defined = {
            definition.get("identifier")
            for definition in root.iter(f"{{{namespace}}}propertyDefinition")
        }
        changed = False
        for prop in list(root.iter(f"{{{namespace}}}property")):
            ref = prop.get("propertyDefinitionRef")
            if ref and ref not in defined:
                parent = prop.getparent()
                parent.remove(prop)
                changed = True
                if len(parent) == 0:
                    parent.getparent().remove(parent)
        return changed

    def _rewrite_note_connectors_as_lines(
        self,
        root: Any,
        namespace: str,
        model: Model,
    ) -> bool:
        """Write diagram-only note lines as `xsi:type="Line"`.

        pyArchimate's exchange writer types every connection
        `Relationship` and copies `c.ref` into `relationshipRef`. For a
        note line that `ref` is a synthetic id `view.connect_note` never
        registered as a relationship, so the export carries an IDREF
        resolving to nothing. The exchange schema declares
        `relationshipRef` as `xs:IDREF use="required"` on `Relationship`
        (archimate3_Diagram.xsd), so the whole document fails keyref
        validation — including in Archi's validating import.

        The schema has a purpose-built type for a view-only connection:
        `Line`, which extends `ConnectionType` and takes no
        `relationshipRef` while keeping `source`/`target`. Retyping is
        therefore lossless in the file.

        The rewrite is deliberately as narrow as the validation
        exemption in `_is_annotation_connector`: only note lines are
        retyped. A connector between two element-backed nodes whose
        relationship is genuinely missing is a model defect that
        `validate_model` and the export quality gate must keep
        reporting, not something the writer quietly papers over.

        Caveat: pyArchimate's own exchange reader skips `Line`
        connections, so an MCP -> exchange -> MCP round trip keeps the
        note node but drops the connector line. That is the same trade
        already accepted for view properties: a valid interchange file
        beats a lossless invalid one, and the native `archi` format is
        the lossless path.
        """
        annotation_connector_ids = {
            connection.uuid
            for view in model.views
            for connection in view.conns
            if self._is_annotation_connector(connection)
        }
        if not annotation_connector_ids:
            return False
        changed = False
        for connection in root.iter(f"{{{namespace}}}connection"):
            if connection.get("identifier") not in annotation_connector_ids:
                continue
            connection.attrib.pop("relationshipRef", None)
            connection.set(XSI_TYPE_ATTRIBUTE, "Line")
            changed = True
        return changed

    def _model_copy_for_archi_export(self, model: Model) -> Model:
        model_copy = copy.deepcopy(model)
        for element in model_copy.elements:
            # Archi's native format has a single Junction concept with a
            # type attribute ("and"/"or"); archimate:AndJunction and
            # archimate:OrJunction are not valid native classes, so map the
            # typed variants onto Junction before the native writer runs.
            if element.type == "AndJunction":
                element.type = "Junction"
                element.junction_type = "and"
            elif element.type == "OrJunction":
                element.type = "Junction"
                element.junction_type = "or"
            elif element.type == "Junction" and not getattr(
                element,
                "junction_type",
                None,
            ):
                element.junction_type = "and"
        return model_copy

    # ---- layout delegation (implementation lives in layout.py) ----

    def _view_nodes_recursive(self, view: PyArchimateView) -> list[Any]:
        return layout.view_nodes_recursive(view)

    def _node_parent_id(self, node: Any) -> str | None:
        return layout.node_parent_id(node)

    def _is_ancestor(self, node: Any, possible_child: Any) -> bool:
        return layout.is_ancestor(node, possible_child)

    def _intersects_any(
        self,
        rect: tuple[int, int, int, int],
        rects: list[tuple[int, int, int, int]],
    ) -> bool:
        return layout.intersects_any(rect, rects)

    def _default_node_size_for_element(self, element: Any) -> tuple[int, int]:
        return layout.default_node_size_for_element(element)

    def _connection_label_text(self, connection: Any) -> str | None:
        return layout.connection_label_text(connection)

    def _route_or_simplify_connections(self, view: PyArchimateView) -> None:
        layout.route_or_simplify_connections(view)

    def _route_connections_around_nodes(self, view: PyArchimateView) -> None:
        layout.route_connections_around_nodes(view)

    def _is_coverage_view(
        self,
        view: PyArchimateView,
        *,
        coverage_view_name: str | None = None,
    ) -> bool:
        return layout.is_coverage_view(view, coverage_view_name=coverage_view_name)

    def _run_with_rollback(
        self,
        operation: Any,
        *,
        rollback_on_error: bool,
    ) -> Any:
        snapshot = copy.deepcopy(self._active_model) if rollback_on_error else None
        try:
            return operation()
        except Exception:
            if rollback_on_error:
                self._active_model = snapshot
            raise

    def _require_spec_mapping(self, spec: Any, label: str) -> None:
        if not isinstance(spec, dict):
            msg = f"{label} must be an object."
            raise ModelOperationError(msg)

    def _required_spec_value(
        self,
        spec: dict[str, Any],
        key: str,
        label: str,
        *,
        fallback_key: str | None = None,
    ) -> str:
        value = spec.get(key)
        if value is None and fallback_key is not None:
            value = spec.get(fallback_key)
        if not isinstance(value, str) or not value.strip():
            expected_key = key if fallback_key is None else f"{key} or {fallback_key}"
            msg = f"{label} requires {expected_key}."
            raise ModelOperationError(msg)
        return value.strip()

    def _register_ref(
        self,
        ref_map: dict[str, str],
        spec: dict[str, Any],
        generated_id: str,
    ) -> None:
        ref_candidates = [
            spec.get("ref"),
            spec.get("key"),
            spec.get("id"),
            spec.get("element_id"),
            spec.get("relationship_id"),
            spec.get("view_id"),
            spec.get("name"),
        ]
        for ref in ref_candidates:
            if isinstance(ref, str) and ref.strip():
                ref_map.setdefault(ref.strip(), generated_id)

    def _next_free_position(
        self,
        view: PyArchimateView,
        width: int,
        height: int,
        preferred_x: int | None = None,
        preferred_y: int | None = None,
    ) -> tuple[int, int]:
        existing_rects = [
            (node.x, node.y, node.w, node.h)
            for node in self._view_nodes_recursive(view)
        ]
        if preferred_x is not None and preferred_y is not None:
            preferred_rect = (preferred_x, preferred_y, width, height)
            if not self._intersects_any(preferred_rect, existing_rects):
                return preferred_x, preferred_y

        slot_width = width + DEFAULT_X_GAP
        slot_height = height + DEFAULT_Y_GAP
        for row_index in range(len(existing_rects) + 100):
            for column_index in range(12):
                x = DEFAULT_MARGIN_X + (column_index * slot_width)
                y = DEFAULT_MARGIN_Y + (row_index * slot_height)
                candidate_rect = (x, y, width, height)
                if not self._intersects_any(candidate_rect, existing_rects):
                    return x, y

        fallback_y = DEFAULT_MARGIN_Y + ((len(existing_rects) + 1) * slot_height)
        return DEFAULT_MARGIN_X, fallback_y

    def _relationship_ids_used_in_views(self) -> set[str]:
        model = self._require_model()
        return {
            connection.ref
            for view in model.views
            for connection in view.conns
            if connection.ref
        }

    def _relocate_group_containment_connections_to_coverage(
        self,
        coverage_view_name: str,
    ) -> dict[str, Any]:
        model = self._require_model()
        coverage_view = None
        relocated_connection_ids: list[str] = []
        relocated_relationship_ids: list[str] = []

        for view in list(model.views):
            if self._is_coverage_view(view, coverage_view_name=coverage_view_name):
                continue
            for connection in list(view.conns):
                if not self._is_group_containment_connection(connection):
                    continue
                relationship = connection.concept
                if coverage_view is None:
                    coverage_view = self._get_or_create_coverage_view(
                        coverage_view_name,
                    )
                if not self._view_has_relationship(coverage_view, relationship.uuid):
                    self._add_relationship_pair_to_coverage_view(
                        coverage_view,
                        relationship,
                        len(coverage_view.conns),
                    )
                    relocated_relationship_ids.append(relationship.uuid)
                relocated_connection_ids.append(connection.uuid)
                connection.delete()

        if coverage_view is not None:
            self._layout_coverage_view_pairs(coverage_view)
            self._route_or_simplify_connections(coverage_view)

        return {
            "coverage_view_id": getattr(coverage_view, "uuid", None),
            "connection_ids": relocated_connection_ids,
            "connections_count": len(relocated_connection_ids),
            "relationship_ids": relocated_relationship_ids,
        }

    def _view_has_relationship(
        self,
        view: PyArchimateView,
        relationship_id: str,
    ) -> bool:
        return any(connection.ref == relationship_id for connection in view.conns)

    def _is_group_containment_connection(self, connection: Any) -> bool:
        relationship_type = layout.connection_relationship_type(connection)
        if relationship_type not in {"Aggregation", "Composition"}:
            return False
        source = connection.source
        target = connection.target
        if source is None or target is None:
            return False
        source_type = getattr(source.concept, "type", None)
        return source_type == "Grouping" and self._is_ancestor(source, target)

    def _get_or_create_coverage_view(self, name: str) -> Any:
        model = self._require_model()
        existing_view = next((view for view in model.views if view.name == name), None)
        if existing_view is not None:
            self._mark_coverage_view(existing_view)
            return existing_view
        view = self.create_view(name, folder_path="/Views")
        self._mark_coverage_view(view)
        return view

    def _mark_coverage_view(self, view: Any) -> None:
        view.prop(COVERAGE_VIEW_PROPERTY_KEY, COVERAGE_VIEW_PROPERTY_VALUE)
        view.prop(QA_VIEW_PROPERTY_KEY, "true")
        view.prop(STAKEHOLDER_FACING_PROPERTY_KEY, "false")

    def _add_relationship_pair_to_coverage_view(
        self,
        view: PyArchimateView,
        relationship: PyArchimateRelationship,
        index: int,
    ) -> tuple[Any, Any, Any]:
        row_y = DEFAULT_MARGIN_Y + (index * 140)
        source_width, source_height = self._default_node_size_for_element(
            relationship.source,
        )
        target_width, target_height = self._default_node_size_for_element(
            relationship.target,
        )
        source_node = view.add(
            ref=relationship.source,
            x=DEFAULT_MARGIN_X,
            y=row_y,
            w=source_width,
            h=source_height,
        )
        target_node = view.add(
            ref=relationship.target,
            x=DEFAULT_MARGIN_X + max(source_width, DEFAULT_NODE_WIDTH) + 280,
            y=row_y,
            w=target_width,
            h=target_height,
        )
        connection = view.add_connection(
            ref=relationship,
            source=source_node,
            target=target_node,
        )
        return source_node, target_node, connection

    def _layout_coverage_view_pairs(self, view: PyArchimateView) -> None:
        # A note line is NOT a relationship pair. It has no backing
        # relationship and one of its endpoints is a note, so laying it
        # out as a pair drags the note into the source column, drags the
        # thing it annotates into the target column, and pushes every
        # genuine relationship row down by one 140px slot. This layout
        # has no note save/restore around it (it is not
        # `auto_layout_view`), so skipping the annotation connectors is
        # what keeps a note where its author put it.
        pair_connections = [
            connection
            for connection in view.conns
            if connection.source is not None
            and connection.target is not None
            and not layout.is_note_node(connection.source)
            and not layout.is_note_node(connection.target)
        ]
        paired_node_ids = {
            endpoint.uuid
            for connection in pair_connections
            for endpoint in (connection.source, connection.target)
        }
        ordered_connections = sorted(
            pair_connections,
            key=lambda connection: (
                layout.connection_relationship_type(connection) or "",
                self._connection_label_text(connection) or "",
                connection.uuid,
            ),
        )
        for index, connection in enumerate(ordered_connections):
            row_y = DEFAULT_MARGIN_Y + (index * 140)
            connection.source.x = DEFAULT_MARGIN_X
            connection.source.y = row_y
            connection.target.x = (
                DEFAULT_MARGIN_X + max(connection.source.w, DEFAULT_NODE_WIDTH) + 280
            )
            connection.target.y = row_y
        for node in view.nodes:
            if layout.is_note_node(node):
                continue
            if node.uuid not in paired_node_ids:
                node.y = DEFAULT_MARGIN_Y + (len(ordered_connections) * 140)

    def _find_node_for_element(
        self,
        view: PyArchimateView,
        element_id: str,
    ) -> Any | None:
        return next(
            (
                node
                for node in self._view_nodes_recursive(view)
                if node.ref == element_id
            ),
            None,
        )

    def _normalize_existing_layout(
        self,
        nodes: list[Any],
        origin_x: int,
        origin_y: int,
    ) -> None:
        if not nodes:
            return
        min_x = min(node.x for node in nodes)
        min_y = min(node.y for node in nodes)
        for node in nodes:
            node.x = origin_x + max(0, node.x - min_x)
            node.y = origin_y + max(0, node.y - min_y)

    def _is_quality_assurance_view(self, view: PyArchimateView) -> bool:
        if self._is_coverage_view(view):
            return True
        return str(view.prop(QA_VIEW_PROPERTY_KEY)).lower() == "true"

    def _property_has_value(self, entity: Any, key: str) -> bool:
        value = entity.prop(key) if hasattr(entity, "prop") else None
        return value is not None and str(value).strip() != ""

    def _rect_overlap_area(
        self,
        first: tuple[float, float, float, float],
        second: tuple[float, float, float, float],
    ) -> float:
        first_x, first_y, first_width, first_height = first
        second_x, second_y, second_width, second_height = second
        overlap_width = max(
            0,
            min(first_x + first_width, second_x + second_width)
            - max(first_x, second_x),
        )
        overlap_height = max(
            0,
            min(first_y + first_height, second_y + second_height)
            - max(first_y, second_y),
        )
        return overlap_width * overlap_height

    def _require_model(self) -> Model:
        if self._active_model is None:
            msg = "No active model found."
            raise ModelNotFoundError(msg)
        return self._active_model

    def _ensure_supported_format(self, content_format: str) -> None:
        if content_format.lower() not in SUPPORTED_FORMATS:
            msg = f"Unsupported model format: {content_format}"
            raise UnsupportedFormatError(msg)

    def _unsupported_layout_value_error(
        self,
        *,
        singular: str,
        plural: str,
        value: str,
        catalog: list[str],
    ) -> ModelOperationError:
        """Build a did-you-mean error for a mistyped layout enum value.

        Same shape as `_invalid_element_type_error`, so an agent gets
        `error.details.suggestions` here too. The "Unsupported layout
        <singular>: " prefix is load-bearing — callers and the ARC-015
        regression guards match on it, so only append to it.
        """
        suggestions = self._type_suggestions(value, catalog)
        msg = (
            f"Unsupported layout {singular}: {value}. "
            f"Supported {plural}: {', '.join(catalog)}."
        )
        if suggestions:
            msg += f" Did you mean: {', '.join(suggestions)}?"
        msg += " Call list_supported_types for the full catalog."
        return ModelOperationError(msg, {"suggestions": suggestions})

    def _normalize_layout_strategy(self, strategy: str) -> str:
        normalized_strategy = strategy.lower()
        if normalized_strategy not in SUPPORTED_LAYOUT_STRATEGIES:
            error = self._unsupported_layout_value_error(
                singular="strategy",
                plural="strategies",
                value=strategy,
                catalog=sorted(SUPPORTED_LAYOUT_STRATEGIES),
            )
            raise error
        return normalized_strategy

    def normalize_detail_level(self, detail: str) -> str:
        """Validate a `detail` level.

        Public because `auto_layout_view` is shaped in the tools layer
        — the manager returns a `ViewDetail` there, and its internal
        callers need that object rather than a response dict.
        """
        normalized_detail = str(detail).lower()
        if normalized_detail in SUPPORTED_DETAIL_LEVELS:
            return normalized_detail
        catalog = sorted(SUPPORTED_DETAIL_LEVELS)
        suggestions = self._type_suggestions(str(detail), catalog)
        msg = (
            f"Unsupported detail level: {detail}. "
            f"Supported levels: {', '.join(catalog)}."
        )
        if suggestions:
            msg += f" Did you mean: {', '.join(suggestions)}?"
        raise ModelOperationError(msg, {"suggestions": suggestions})

    def _normalize_layout_engine(self, layout_engine: str) -> str:
        normalized_engine = layout_engine.lower()
        if normalized_engine not in SUPPORTED_LAYOUT_ENGINES:
            error = self._unsupported_layout_value_error(
                singular="engine",
                plural="engines",
                value=layout_engine,
                catalog=sorted(SUPPORTED_LAYOUT_ENGINES),
            )
            raise error
        return normalized_engine

    def _require_pyarchimate_layout_is_safe(self, view: PyArchimateView) -> None:
        """Refuse an upstream layout that would silently overlap nodes.

        pyArchimate's `assign_grid_cells` never reads node width or
        height: it hands out unique cells `grid_size` apart and trusts
        every node to fit. One node a single pixel over that budget
        produces overlapping rectangles, reported as success with no
        warnings. An agent caller cannot see the diagram, so the only
        honest option is to refuse before touching any coordinate.

        Overlaps would also break routing: an anchor landing inside a
        neighbour makes the corridor search fail, silently degrading
        every connection to a dogleg.
        """
        oversized = layout.oversized_nodes_for_pyarchimate(view)
        if not oversized:
            return
        grid_size = int(layout.pyarchimate_grid_size())
        msg = (
            f"Layout engine 'pyarchimate' cannot lay out view '{view.name}': "
            f"{len(oversized)} node(s) exceed the upstream {grid_size}px grid "
            f"cell. The upstream engine has no collision detection and would "
            f'overlap them. Use layout_engine="internal" (the default) for '
            f"this view."
        )
        raise ModelOperationError(
            msg,
            {
                "grid_size": grid_size,
                "oversized_nodes": oversized,
                "remedy": "internal",
            },
        )

    def _validate_xml_content(self, model_content: str) -> None:
        encoded = model_content.encode("utf-8")
        if len(encoded) > MAX_MODEL_CONTENT_BYTES:
            msg = "Model content exceeds the maximum supported size."
            raise ModelOperationError(msg)

        upper_content = model_content.upper()
        if "<!DOCTYPE" in upper_content or "<!ENTITY" in upper_content:
            msg = "Model XML must not contain DTD or entity declarations."
            raise ModelOperationError(msg)

        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            recover=False,
            huge_tree=False,
        )
        try:
            # Hardened parser: entities/DTD rejected above, resolve_entities
            # disabled, no_network enforced.
            root = etree.fromstring(encoded, parser=parser)
        except etree.XMLSyntaxError as exc:
            msg = f"Invalid XML content: {exc}"
            raise ModelOperationError(msg) from exc

        root_tag = root.tag.lower()
        if not any(token in root_tag for token in ("opengroup", "archimate", "aml")):
            msg = "Unsupported ArchiMate XML root element."
            raise UnsupportedFormatError(msg)

    def _apply_properties(
        self,
        entity: Any,
        properties: dict[str, str] | None,
    ) -> None:
        if properties is None:
            return
        for key, value in properties.items():
            entity.prop(str(key), str(value))

    def _require_unused_concept_id(
        self,
        model: Model,
        concept_id: str | None,
        kind: str,
    ) -> None:
        """Reject a client-supplied id already used anywhere in the model.

        pyArchimate keys concepts in five separate dicts, so checking
        only the matching one let the same id belong to an element, a
        relationship, a view, a node and a connection at once. Both
        writers then emitted that identifier twice in one document: in
        the exchange format `identifier` is the `xs:ID` that
        `relationshipRef` points at as an `xs:IDREF`, so a duplicate is
        the same class of defect `_sanitize_exchange_output` already
        repairs — an identifier declared twice rather than referenced
        but never declared — and in the native format two concepts
        sharing an id let an `archimateElement` reference resolve to the
        wrong one. Neither round trip complains, because pyArchimate
        keys by the same separate dicts on the way back in.
        """
        if concept_id is None:
            return
        for namespace, existing_kind in CONCEPT_ID_NAMESPACES:
            if concept_id in getattr(model, namespace, {}):
                if existing_kind == kind:
                    # Unchanged wording: this message is already clear,
                    # and callers hit it far more often than the
                    # cross-kind case.
                    msg = f"{kind.capitalize()} with ID '{concept_id}' already exists."
                else:
                    # "an existing <kind>" reads correctly for all five
                    # kinds; "a {kind}" would produce "a element".
                    msg = (
                        f"ID '{concept_id}' already identifies an existing "
                        f"{existing_kind} in this model. IDs must be unique "
                        f"across the entire model, not per concept type."
                    )
                raise ModelOperationError(
                    msg,
                    {
                        "concept_id": concept_id,
                        "requested_concept_kind": kind,
                        "existing_concept_kind": existing_kind,
                    },
                )

    def _require_valid_viewpoint(self, properties: dict[str, str] | None) -> None:
        """Reject an unknown viewpoint BEFORE any view is created or changed.

        This must stay ahead of every mutation. When the check lived in
        `_apply_view_metadata` — after `model.add()` — a rejected
        viewpoint still left the view behind, so the natural agent
        recovery (retry with a corrected viewpoint) hit a duplicate-id
        error on a view the caller did not believe existed, and the
        rejected value stayed on the view as a property.
        """
        viewpoint = (properties or {}).get("viewpoint")
        if not viewpoint:
            return
        try:
            validate_viewpoint_slug(str(viewpoint))
        except ValueError as exc:
            # Canonical Archi viewpoint ids are also accepted; they are
            # carried by the "viewpoint" property and written as the
            # native viewpoint attribute during Archi export.
            if str(viewpoint) in ARCHI_VIEWPOINT_IDS:
                return
            catalogs = viewpoint_catalogs()
            valid_slugs = catalogs["pyarchimate_slugs"]
            valid_ids = catalogs["archi_viewpoint_ids"]
            msg = (
                f"Invalid viewpoint {viewpoint!r}. Accepted values: "
                f"pyArchimate slugs ({', '.join(valid_slugs)}) or Archi "
                f"viewpoint ids ({', '.join(valid_ids)}). The same catalog "
                f"is available up front from `list_supported_types` under "
                f"`viewpoints`."
            )
            raise ModelOperationError(
                msg,
                {
                    "supported_viewpoint_slugs": valid_slugs,
                    "supported_archi_viewpoint_ids": valid_ids,
                },
            ) from exc

    def _apply_view_metadata(self, view: Any) -> None:
        """Mirror the "viewpoint" property onto pyArchimate's own field.

        Deliberately never raises. `_require_valid_viewpoint` already
        gates the tool paths, and a view loaded from a foreign file may
        carry a slug this pyArchimate build does not know — the load
        path suppresses that too rather than failing the load.
        """
        viewpoint = view.prop("viewpoint")
        if viewpoint and hasattr(view, "set_primary_viewpoint"):
            with contextlib.suppress(ValueError):
                view.set_primary_viewpoint(str(viewpoint))

    def _view_metadata(self, view: Any) -> dict[str, str | bool | list[str]]:
        properties = dict(getattr(view, "props", {}))
        metadata_keys = {
            "viewpoint",
            "purpose",
            "stakeholders",
            "concerns",
            "architecture_layer",
            "architecture_state",
            QA_VIEW_PROPERTY_KEY,
            STAKEHOLDER_FACING_PROPERTY_KEY,
            COVERAGE_VIEW_PROPERTY_KEY,
        }
        metadata: dict[str, str | bool | list[str]] = {}
        for key in metadata_keys:
            if key not in properties:
                continue
            value = properties[key]
            if key in {QA_VIEW_PROPERTY_KEY, STAKEHOLDER_FACING_PROPERTY_KEY}:
                metadata[key] = str(value).lower() == "true"
            elif key in {"stakeholders", "concerns"}:
                metadata[key] = [
                    part.strip() for part in str(value).split(",") if part.strip()
                ]
            else:
                metadata[key] = str(value)
        return metadata

    def _resolve_element_type(
        self,
        element_id: str | None,
        element_type: str | None,
    ) -> str:
        if element_id is not None:
            element = self.get_element_by_id(element_id)
            if element is None:
                msg = f"Element with ID '{element_id}' not found."
                raise ElementNotFoundError(msg)
            return element.type
        if element_type is None:
            msg = "Provide either element ID or element type."
            raise ModelOperationError(msg)
        return self._require_element_type(element_type)

    def _normalize_semantic_validation_mode(self, mode: str) -> str:
        normalized = str(mode).lower()
        if normalized not in SUPPORTED_SEMANTIC_VALIDATION_MODES:
            msg = f"Invalid semantic_validation mode: {mode}"
            raise ModelOperationError(msg)
        return normalized

    def _normalize_quality_gate(self, quality_gate: str) -> str:
        normalized = str(quality_gate).lower()
        if normalized not in SUPPORTED_QUALITY_GATES:
            msg = f"Invalid quality_gate: {quality_gate}"
            raise ModelOperationError(msg)
        return normalized

    def check_relationship_semantics(
        self,
        relationship_type: str,
        source_id: str,
        target_id: str,
        access_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Return semantic issue details for a combination, or None if valid."""
        source = self.get_element_by_id(source_id)
        target = self.get_element_by_id(target_id)
        if source is None or target is None:
            return None
        valid, _message = is_valid_relationship(
            relationship_type,
            source.type,
            target.type,
        )
        missing_access_type = relationship_type == "Access" and access_type is None
        if valid and not missing_access_type:
            return None
        details = relationship_issue_details(
            relationship_type,
            source.type,
            target.type,
            source_id=source.uuid,
            target_id=target.uuid,
            source_name=source.name,
            target_name=target.name,
        )
        if missing_access_type:
            details.setdefault("attribute_issues", []).append(
                {
                    "code": "MISSING_ACCESS_TYPE",
                    "message": "access_type is recommended for Access relationships.",
                },
            )
        return details

    def _validate_relationship_for_creation(
        self,
        *,
        relationship_type: str,
        source_element: Any,
        target_element: Any,
        access_type: str | None,
        semantic_validation: str,
    ) -> None:
        if semantic_validation == "off":
            return
        valid, _message = is_valid_relationship(
            relationship_type,
            source_element.type,
            target_element.type,
        )
        missing_access_type = relationship_type == "Access" and access_type is None
        if valid and not missing_access_type:
            return
        details = relationship_issue_details(
            relationship_type,
            source_element.type,
            target_element.type,
            source_id=source_element.uuid,
            target_id=target_element.uuid,
            source_name=source_element.name,
            target_name=target_element.name,
        )
        if missing_access_type:
            details.setdefault("attribute_issues", []).append(
                {
                    "code": "MISSING_ACCESS_TYPE",
                    "message": "access_type is required for Access in strict mode.",
                },
            )
        if semantic_validation == "strict":
            msg = details["message"]
            if missing_access_type and valid:
                msg = "access_type is required for Access relationships."
            raise InvalidRelationshipCombinationError(msg, details)

    def _enforce_quality_gate(
        self,
        quality_gate: str,
        *,
        allow_semantic_issues: bool,
        allow_visual_issues: bool,
        allow_orphans: bool,
    ) -> dict[str, Any] | None:
        normalized = self._normalize_quality_gate(quality_gate)
        if normalized == "off":
            return None
        report = self.build_quality_report()
        failures = []
        if not allow_visual_issues and not report["visual_validation"]["is_valid"]:
            failures.append("visual_validation")
        if not allow_semantic_issues and not report["semantic_validation"]["is_valid"]:
            failures.append("semantic_validation")
        if (
            not allow_orphans
            and report["coverage"]["elements_not_in_any_view_count"] > 0
        ):
            failures.append("orphans")
        report["warnings"] = failures
        if normalized == "strict" and failures:
            msg = "Export quality gate failed: " + ", ".join(failures)
            raise ModelOperationError(msg, {"quality_report": report})
        return report

    def _normalize_access_type(
        self,
        relationship_type: str,
        access_type: str | None,
    ) -> str | None:
        if access_type is None:
            return None
        if relationship_type != "Access":
            msg = "access_type can only be set on Access relationships."
            raise InvalidRelationshipTypeError(msg)
        normalized = str(access_type)
        if normalized not in SUPPORTED_ACCESS_TYPES:
            msg = f"Invalid access_type: {access_type}"
            raise InvalidRelationshipTypeError(msg)
        return normalized

    def _normalize_influence_strength(
        self,
        relationship_type: str,
        influence_strength: str | None,
    ) -> str | None:
        if influence_strength is None:
            return None
        if relationship_type != "Influence":
            msg = "influence_strength can only be set on Influence relationships."
            raise InvalidRelationshipTypeError(msg)
        normalized = str(influence_strength)
        if normalized not in SUPPORTED_INFLUENCE_STRENGTHS:
            msg = f"Invalid influence_strength: {influence_strength}"
            raise InvalidRelationshipTypeError(msg)
        return normalized

    def _normalize_is_directed(
        self,
        relationship_type: str,
        *,
        is_directed: bool | None,
    ) -> bool | None:
        if is_directed is None:
            return None
        if relationship_type != "Association":
            msg = "is_directed can only be set on Association relationships."
            raise InvalidRelationshipTypeError(msg)
        return bool(is_directed)

    def _relationship_access_type(
        self,
        relationship: PyArchimateRelationship,
    ) -> str | None:
        if relationship.type != "Access":
            return None
        return self._enum_or_string_value(getattr(relationship, "access_type", None))

    def _relationship_influence_strength(
        self,
        relationship: PyArchimateRelationship,
    ) -> str | None:
        if relationship.type != "Influence":
            return None
        return self._enum_or_string_value(
            getattr(relationship, "influence_strength", None),
        )

    def _relationship_is_directed(
        self,
        relationship: PyArchimateRelationship,
    ) -> bool | None:
        if relationship.type != "Association":
            return None
        value = getattr(relationship, "is_directed", None)
        return None if value is None else bool(value)

    def _enum_or_string_value(self, value: Any) -> str | None:
        if value is None:
            return None
        enum_value = getattr(value, "value", value)
        return str(enum_value)

    def _properties_match(
        self,
        existing_properties: dict[str, str],
        expected_properties: dict[str, Any],
    ) -> bool:
        return all(
            existing_properties.get(str(key)) == str(value)
            for key, value in expected_properties.items()
        )

    def _rows_to_csv(self, rows: list[list[str]]) -> str:
        buffer = io.StringIO(newline="")
        csv.writer(buffer).writerows(rows)
        return buffer.getvalue()

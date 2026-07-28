"""MCP tools for model-level operations."""

from typing import Any

from pyarchimate_mcp_server.exceptions import ArchiMateMCPError
from pyarchimate_mcp_server.mcp_app import (
    DESTRUCTIVE_TOOL,
    IDEMPOTENT_TOOL,
    READ_ONLY_TOOL,
    mcp,
)
from pyarchimate_mcp_server.mcp_app import get_model_manager as _model_manager
from pyarchimate_mcp_server.responses import error_response, success_response

MODEL_UPDATE_KEYS = ("name", "description", "documentation", "properties")


@mcp.tool(annotations=DESTRUCTIVE_TOOL)
async def create_empty_model(
    name: str,
    description: str | None = None,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new empty ArchiMate model and make it the active model.

    Replaces any currently active model. Call this (or one of the
    `load_model_*` tools) before any element/relationship/view tool.
    Use `update_model` to change this metadata later, including on a
    model that was loaded rather than created.

    Args:
        name: Human-readable model name. Must be a non-empty string.
        description: Optional model-level documentation. Comes back as
            `data.model_info.documentation` and survives both export
            formats.
        properties: Optional model-level properties. Keys and values are
            coerced to strings.

    Returns:
        Success envelope with `data.model_id` (the new model UUID) and
        `data.model_info` (same shape as `pyarchimate://activemodel/info`:
        name, id, documentation, properties, elements_count,
        relationships_count, views_count, is_loaded).

    Errors:
        `INVALID_MODEL_NAME` when `name` is missing or blank.
    """
    if not isinstance(name, str) or not name.strip():
        return error_response("Invalid model name.", "INVALID_MODEL_NAME")

    try:
        model_manager = _model_manager()
        model = model_manager.create_new_model(
            name.strip(),
            description=description,
            properties=properties,
        )
        return success_response(
            {"model_id": model.uuid, "model_info": model_manager.get_model_info()},
            "Model created.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=IDEMPOTENT_TOOL)
async def update_model(updates: dict[str, Any]) -> dict[str, Any]:
    """Update the active model's name, documentation, and properties.

    Updates is a dict containing only the fields to change; other fields
    are left untouched and properties are merged into the existing ones.
    There is no `model_id` parameter because exactly one model is active.
    Works on a loaded model, not only on one created by this server.

    Unlike `update_element`, unknown keys are rejected rather than
    ignored: a mis-keyed update would silently leave model metadata
    unwritten while still reporting success.

    Args:
        updates: Mapping of fields to update. Supported keys:
            - `name` (str): New model name. Must be non-blank; it is
              stripped, exactly as in `create_empty_model`.
            - `description` (str): New model documentation. Reported
              back as `documentation`.
            - `documentation` (str): Accepted alias for `description`.
            - `properties` (dict[str, str]): Property updates merged
              into the existing model properties.

    Returns:
        Success envelope with `data.model_info` (same shape as
        `pyarchimate://activemodel/info`).

    Errors:
        `INVALID_MODEL_UPDATE` when `updates` is not an object or
            contains unsupported keys (`error.details.unsupported_keys`
            and `error.details.supported_keys` list which).
        `INVALID_MODEL_NAME` when `name` is present but not a non-blank
            string.
        `ModelNotFoundError` if no model is active.
    """
    if not isinstance(updates, dict):
        return error_response("updates must be an object.", "INVALID_MODEL_UPDATE")

    unsupported_keys = [key for key in updates if key not in MODEL_UPDATE_KEYS]
    if unsupported_keys:
        return error_response(
            f"Unsupported model update keys: {', '.join(unsupported_keys)}.",
            "INVALID_MODEL_UPDATE",
            {
                "unsupported_keys": unsupported_keys,
                "supported_keys": list(MODEL_UPDATE_KEYS),
            },
        )

    name = updates.get("name")
    if "name" in updates and (not isinstance(name, str) or not name.strip()):
        return error_response("Invalid model name.", "INVALID_MODEL_NAME")

    description = updates.get("description")
    if description is None:
        description = updates.get("documentation")

    try:
        model_info = _model_manager().update_model_metadata(
            name=name.strip() if isinstance(name, str) else None,
            description=description,
            properties=updates.get("properties"),
        )
        return success_response({"model_info": model_info}, "Model updated.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=DESTRUCTIVE_TOOL)
async def load_model_from_content(
    model_content: str,
    content_format: str = "archimate",
) -> dict[str, Any]:
    """Load an ArchiMate model from XML string content (replaces active model).

    For loading large files or paths use `load_model_from_file` instead;
    this tool expects the actual XML payload, not a path.

    Args:
        model_content: XML content. Must start with `<` and be 10 MiB or
            smaller. DTD and entity declarations are rejected for safety.
        content_format: One of `archimate` (Open Group exchange XML,
            default), `archi` (Archi native `.archimate` XML), or `xml`.

    Returns:
        Success envelope with `data.model_info` describing the loaded
        model (see `pyarchimate://activemodel/info`).

    Errors:
        `INVALID_MODEL_CONTENT` when `model_content` is not XML.
        `UnsupportedFormatError` when `content_format` is not recognized.
        `ModelOperationError` when pyArchimate fails to parse the XML.
    """
    if not isinstance(model_content, str) or not model_content.lstrip().startswith("<"):
        return error_response(
            "model_content must be XML content. To load a file, use "
            "load_model_from_file.",
            "INVALID_MODEL_CONTENT",
        )

    try:
        model_manager = _model_manager()
        model_manager.load_model_from_string(model_content, content_format)
        return success_response(
            {"model_info": model_manager.get_model_info()},
            "Model loaded.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=IDEMPOTENT_TOOL)
async def export_model_content(  # noqa: PLR0913
    output_format: str = "archimate",
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
    """Serialize the active model as XML string content.

    Use this when the caller wants the XML in the response payload. Use
    `export_model_to_file` to write directly to disk.

    Args:
        output_format: One of `archimate` (default, Open Group exchange
            XML), `archi` (Archi native `.archimate` XML, opens directly
            in Archi), or `xml`.
        auto_layout: When true, run layout on every view before
            serialization. Defaults to false.
        layout_strategy: Layout strategy used when `auto_layout=true`.
            One of `layered_by_type` (default, ArchiMate semantic
            lanes), `layered` (relationship-direction layered), or
            `grid`.
        layout_engine: Layout engine applied to every view when
            `auto_layout=true`. One of `internal` (default) or
            `pyarchimate` (see `auto_layout_view` for what the latter
            gives up). Per-call only: nothing about the engine is
            written into the exported file. Validated even when
            `auto_layout=false`, so a typo is never swallowed.

    Returns:
        Success envelope with `data.content` (XML string),
        `data.auto_layout`, and (when `auto_layout=true`)
        `data.layout_strategy` and `data.layout_engine`.

    Errors:
        `ModelNotFoundError` if no model is active.
        `UnsupportedFormatError` for an unknown `output_format`.
        `ModelOperationError` for layout or serialization failures,
            including an unknown strategy/engine (with
            `error.details.suggestions`) and a view the `pyarchimate`
            engine cannot lay out safely — one such view fails the
            whole export.
    """
    try:
        model_manager = _model_manager()
        content = model_manager.get_model_content_as_string(
            output_format=output_format,
            auto_layout=auto_layout,
            layout_strategy=layout_strategy,
            layout_engine=layout_engine,
            quality_gate=quality_gate,
            allow_semantic_issues=allow_semantic_issues,
            allow_visual_issues=allow_visual_issues,
            allow_orphans=allow_orphans,
        )
        data = {
            "content": content,
            "auto_layout": auto_layout,
            "layout_strategy": layout_strategy if auto_layout else None,
            "layout_engine": layout_engine if auto_layout else None,
        }
        if include_quality_report or quality_gate != "off":
            data["quality_report"] = model_manager.build_quality_report()
        return success_response(data, "Model exported.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=IDEMPOTENT_TOOL)
async def export_model_to_file(  # noqa: PLR0913
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
    """Serialize the active model and write it to a local file.

    Preferred when the user wants a `.archimate` file Archi can open
    directly. Parent directories are created if missing.

    Args:
        path: Output path on the MCP server's filesystem. `~` is
            expanded; relative paths resolve against the server's CWD.
        output_format: One of `archi` (default, Archi native), `archimate`
            (Open Group exchange), or `xml`.
        auto_layout: When true, lay out every view before serialization.
        layout_strategy: One of `layered_by_type` (default), `layered`,
            or `grid`. Only applied when `auto_layout=true`.
        layout_engine: One of `internal` (default) or `pyarchimate`
            (see `auto_layout_view` for what the latter gives up).
            Only applied when `auto_layout=true`, but always
            validated. Per-call only: the engine is never recorded in
            the written file.

    Returns:
        Success envelope with `data.path`, `data.output_format`,
        `data.bytes_written`, `data.auto_layout`, and (when
        `auto_layout=true`) `data.layout_strategy` and
        `data.layout_engine`.

    Errors:
        `ModelNotFoundError` if no model is active.
        `UnsupportedFormatError`, `ModelOperationError` for invalid
        path/format, an unknown strategy/engine (with
        `error.details.suggestions`), a view the `pyarchimate` engine
        cannot lay out safely, or serialization failure.
    """
    try:
        result = _model_manager().export_model_to_file(
            path=path,
            output_format=output_format,
            auto_layout=auto_layout,
            layout_strategy=layout_strategy,
            layout_engine=layout_engine,
            quality_gate=quality_gate,
            allow_semantic_issues=allow_semantic_issues,
            allow_visual_issues=allow_visual_issues,
            allow_orphans=allow_orphans,
            include_quality_report=include_quality_report,
        )
        return success_response(result, "Model exported to file.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=DESTRUCTIVE_TOOL)
async def create_model_from_spec(
    spec: dict[str, Any],
    *,
    rollback_on_error: bool = True,
) -> dict[str, Any]:
    """Create a complete ArchiMate model from a structured JSON spec.

    The spec is applied transactionally by default. Element, relationship,
    and view objects accept either short field names (`type`, `source`,
    `target`, `id`, `element`, `relationship`) or the long forms used by
    individual tools (`element_type`, `relationship_type`, `source_id`,
    `target_id`, `element_id`, `relationship_id`, `view_id`).

    Spec shape:
        ```
        {
          "name": "Model Name",                    # required
          "elements": [                              # optional list
            {
              "id": "id-customer",                # optional stable ref
              "name": "Customer",                  # required
              "type": "BusinessActor",             # required
              "description": "...",               # optional
              "folder_path": "/Business",         # optional
              "properties": {"owner": "EA"}        # optional
            }
          ],
          "relationships": [
            {
              "id": "id-uses",                    # optional stable ref
              "type": "Serving",                   # required
              "source": "id-customer",             # required ref or UUID
              "target": "id-portal",               # required ref or UUID
              "name": "uses",                      # optional
              "description": "...",               # optional
              "properties": {...},                  # optional
              "access_type": "Read",                # for Access only
              "influence_strength": "+"             # for Influence only
            }
          ],
          "views": [
            {
              "id": "id-context",                  # optional stable ref
              "name": "Context",                   # required
              "folder_path": "/Views",            # optional
              "nodes": [                            # optional
                {"element": "id-customer",
                 "x": 40, "y": 40,                  # x/y optional
                 "width": 160, "height": 80}        # width/height optional
              ],
              "connections": [                       # optional
                {"relationship": "id-uses"}
              ],
              "connect_visible_relationships": true, # optional
              "auto_layout": true,                  # optional
              "layout_strategy": "layered_by_type", # optional
              "layout_engine": "internal"           # optional; or
                                                    # "pyarchimate"
            }
          ]
        }
        ```

    Args:
        spec: Specification object as described above.
        rollback_on_error: When true (default), restore the previous
            active model on any failure. Set to false to keep partial
            results.

    Returns:
        Success envelope with `data` containing summary IDs of created
        model, elements, relationships, and views.

    Errors:
        `INVALID_SPEC` for missing required keys.
        `InvalidElementTypeError`, `InvalidRelationshipTypeError`,
        `ElementNotFoundError`, `ModelOperationError` for validation or
        creation failures.
    """
    try:
        result = _model_manager().create_model_from_spec(
            spec,
            rollback_on_error=rollback_on_error,
        )
        return success_response(result, "Model created from spec.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def build_quality_report(
    *,
    include_togaf: bool = False,
    include_quality_assurance_views: bool = False,
) -> dict[str, Any]:
    """Build a structured visual, semantic, coverage, and optional TOGAF report.

    Aggregate counts throughout — this is the tool to poll during a
    build without paying for full issue lists.

    Args:
        include_togaf: Add `data.togaf_readiness`. Advisory only; see
            `assess_togaf_readiness` for the scoring scale and the
            standing `compliance_claim: false` disclaimer.
        include_quality_assurance_views: Count QA-marked views as
            stakeholder-facing in the TOGAF checks.

    Returns:
        Success envelope with `data.visual_validation`,
        `data.semantic_validation` (`is_valid`, `issues_count`,
        `issue_counts`), and `data.coverage`. With `include_togaf`,
        `data.togaf_readiness` carries `status`, `score`, `max_score`,
        `advisory_findings`, `advisory_findings_count`,
        `hard_failures_count`, and `compliance_claim`.

    Errors:
        `ModelNotFoundError` if no model is active.
    """
    try:
        return success_response(
            _model_manager().build_quality_report(
                include_togaf=include_togaf,
                include_quality_assurance_views=include_quality_assurance_views,
            ),
            "Quality report built.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def assess_togaf_readiness(
    *,
    include_quality_assurance_views: bool = False,
    include_hard_validation: bool = True,
) -> dict[str, Any]:
    """Return advisory TOGAF-oriented readiness findings.

    Advisory only. `data.compliance_claim` is always `false`: this is a
    prompt for your own review, not a conformance result, and the
    checklist is deliberately fixed.

    Scoring: seven checks, one point lost per finding, so
    `data.score` runs 0-7 against `data.max_score`. `data.status` is
    `ready` when nothing fired, `partial` at a score of 3 or more, and
    `limited` below that — so `limited` is the floor, and a model with
    no Motivation or Strategy content scores 0 legitimately rather than
    because something went wrong.

    Returns:
        Success envelope with `data.status`, `data.score`,
        `data.max_score`, `data.advisory_findings` (each with `code`,
        `severity`, `message`), `data.advisory_findings_count`,
        `data.hard_failures`, `data.hard_failures_count`, and
        `data.compliance_claim`.

    Errors:
        `ModelNotFoundError` if no model is active.
    """
    try:
        return success_response(
            _model_manager().assess_togaf_readiness(
                include_quality_assurance_views=include_quality_assurance_views,
                include_hard_validation=include_hard_validation,
            ),
            "TOGAF readiness assessed.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def export_elements_to_csv() -> dict[str, Any]:
    """Export all active model elements as a CSV string.

    The CSV includes base columns `id`, `name`, `type`, `description`.
    Custom properties are emitted as `Property:<name>` columns.

    Returns:
        Success envelope with `data.csv_data` containing the CSV string.

    Errors:
        `ModelNotFoundError` if no model is active.
    """
    try:
        csv_data = _model_manager().export_elements_to_csv()
        return success_response({"csv_data": csv_data}, "Elements exported.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def export_relationships_to_csv() -> dict[str, Any]:
    """Export all active model relationships as a CSV string.

    The CSV includes base columns `id`, `name`, `type`, `source_id`,
    `target_id`. Custom properties are emitted as `Property:<name>`
    columns.

    Returns:
        Success envelope with `data.csv_data` containing the CSV string.

    Errors:
        `ModelNotFoundError` if no model is active.
    """
    try:
        csv_data = _model_manager().export_relationships_to_csv()
        return success_response({"csv_data": csv_data}, "Relationships exported.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def validate_model() -> dict[str, Any]:
    """Validate visual references in the active model.

    Delegates to pyArchimate's `check_invalid_conn` and
    `check_invalid_nodes` helpers. Diagram-only annotation connectors
    (a note line joining an Archi Note to an element) are excluded: they
    have no backing relationship by design, so they are not defects. A
    connector between two element-backed nodes whose relationship is
    genuinely missing is still reported. Use `validate_semantics` for
    ArchiMate semantic checks beyond visual references.

    Returns:
        Success envelope with `data.is_valid` (bool),
        `data.invalid_connection_ids`, `data.invalid_node_ids`,
        `data.invalid_connections_count`, and
        `data.invalid_nodes_count`.

    Errors:
        `ModelNotFoundError` if no model is active.
    """
    try:
        return success_response(_model_manager().validate_model(), "Model validated.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def validate_semantics(detail: str = "summary") -> dict[str, Any]:
    """Run ArchiMate semantic checks beyond visual reference validation.

    Checks include invalid relationship combinations, missing node
    references, duplicate element names within the same folder/type,
    elements not placed in any view, and orphan service/data elements.

    Args:
        detail: `summary` (default) or `full`. The completeness checks
            fire once per element and once per relationship, so a
            mid-build model with no views yet produces one issue per
            concept — 214 issues, ~55 KB, on a 71-element model — of
            which the repeated `code`, `severity` and `message` strings
            are most of the weight. Ask for `full` only when you need
            to read individual issue dicts.

    Returns:
        Success envelope with `data.is_valid` (bool),
        `data.issues_count`, `data.issue_counts`, and `data.detail`.

        Under `summary`: `data.issues_by_code` maps each code to
        `{count, severity, ids}`, and `data.errors` carries the
        error-severity issues in full, so `is_valid: false` always
        arrives with its reason. There is deliberately no `data.issues`
        key — read `full` if you want that list.

        Under `full`: `data.issues`, one dict per issue.

    Errors:
        `ModelNotFoundError` if no model is active.
        `ModelOperationError` for an unknown `detail` level, with close
        matches in `error.details.suggestions`.
    """
    try:
        return success_response(
            _model_manager().validate_semantics(detail=detail),
            "Model semantics validated.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def list_supported_types() -> dict[str, Any]:
    """List supported ArchiMate types and configuration values.

    Always call this before generating model content if you are not
    certain which names the running pyArchimate build accepts. The
    catalog is version-specific.

    Returns:
        Success envelope with `data` containing element types grouped by
        category, relationship types, view `viewpoints` (split into
        `pyarchimate_slugs` and `archi_viewpoint_ids` — both accepted,
        and they overlap without either containing the other), folder
        roots, valid `access_type` values, valid `influence_strength`
        values, supported layout strategies, supported layout engines,
        and summary counts.

    Does not require an active model.
    """
    try:
        return success_response(
            _model_manager().list_supported_types(),
            "Supported types listed.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def summarize_model() -> dict[str, Any]:
    """Summarize the active model: counts, view summaries, totals.

    Useful for verifying generation results without dumping full XML.

    Returns:
        Success envelope with `data` containing model name, total
        element/relationship/view counts, and per-view node and
        connection counts.

    Errors:
        `ModelNotFoundError` if no model is active.
    """
    try:
        return success_response(_model_manager().summarize_model(), "Model summarized.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def summarize_view(view_id: str) -> dict[str, Any]:
    """Summarize a single view: node count, connection count, gaps.

    Args:
        view_id: ID of the view to summarize.

    Returns:
        Success envelope with `data` containing the view name, node
        count, connection count, and relationships that could still be
        connected (both endpoints visible) but are not yet drawn.

    Errors:
        `ModelNotFoundError` if no model is active.
        `ViewNotFoundError` when `view_id` is unknown.
    """
    try:
        return success_response(
            _model_manager().summarize_view(view_id),
            "View summarized.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def count_by_type() -> dict[str, Any]:
    """Count active model content grouped by ArchiMate type.

    Returns:
        Success envelope with `data.elements_by_type` and
        `data.relationships_by_type`, each a dict of type name to count.

    Errors:
        `ModelNotFoundError` if no model is active.
    """
    try:
        return success_response(_model_manager().count_by_type(), "Types counted.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def list_orphan_elements() -> dict[str, Any]:
    """List elements with no relationships and/or no view placement.

    Useful for finding gaps before completing a model.

    Returns:
        Success envelope with `data.elements_without_relationships`,
        `data.elements_not_in_any_view`, and `data.fully_orphan_elements`
        (each a list of element IDs), plus matching count fields.

    Errors:
        `ModelNotFoundError` if no model is active.
    """
    try:
        return success_response(
            _model_manager().list_orphan_elements(),
            "Orphan elements listed.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)

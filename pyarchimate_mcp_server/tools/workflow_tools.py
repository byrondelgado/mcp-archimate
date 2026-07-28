"""Workflow-oriented MCP tools for agent discoverability."""

from collections import Counter
from typing import Any

from pyarchimate_mcp_server import filesystem
from pyarchimate_mcp_server.exceptions import ArchiMateMCPError
from pyarchimate_mcp_server.mcp_app import (
    DESTRUCTIVE_TOOL,
    READ_ONLY_TOOL,
    mcp,
)
from pyarchimate_mcp_server.mcp_app import get_model_manager as _model_manager
from pyarchimate_mcp_server.relationship_rules import backend_metadata
from pyarchimate_mcp_server.responses import error_response, success_response


def _sample_limit(value: int) -> int:
    return max(0, min(value, 50))


def _recommended_next_calls() -> list[dict[str, Any]]:
    return [
        {
            "tool": "inspect_active_model",
            "args": {"include_semantic_validation": True},
            "reason": "Build a compact understanding of the loaded model.",
        },
        {
            "tool": "query_elements",
            "args": {"filter_criteria": {}},
            "reason": "List elements when you need concrete IDs before editing.",
        },
        {
            "tool": "query_relationships",
            "args": {"filter_criteria": {}},
            "reason": "List relationships when you need source/target context.",
        },
        {
            "tool": "summarize_view",
            "args": {"view_id": "<view id from inspect_active_model>"},
            "reason": "Inspect one diagram before adding nodes or connections.",
        },
        {
            "tool": "validate_model",
            "args": {},
            "reason": "Check visual references after edits.",
        },
        {
            "tool": "validate_semantics",
            "args": {},
            "reason": "Check ArchiMate semantics after structural edits.",
        },
        {
            "tool": "build_quality_report",
            "args": {},
            "reason": "Check visual, semantic, and coverage quality before export.",
        },
    ]


def _compact_issue_summary(
    semantic_validation: dict[str, Any],
    sample_limit: int,
) -> dict[str, Any]:
    issues = semantic_validation.get("issues", [])
    issue_counts = Counter(
        str(issue.get("code", "UNKNOWN")) for issue in issues if isinstance(issue, dict)
    )
    return {
        "is_valid": semantic_validation.get("is_valid", False),
        "issues_count": semantic_validation.get("issues_count", len(issues)),
        "issue_counts_by_code": dict(sorted(issue_counts.items())),
        "sample_issues": issues[:sample_limit],
        "truncated": len(issues) > sample_limit,
    }


def _compact_orphan_summary(
    orphan_data: dict[str, Any],
    sample_limit: int,
) -> dict[str, Any]:
    def sample(key: str) -> list[dict[str, Any]]:
        return [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "type": item.get("type"),
            }
            for item in orphan_data.get(key, [])[:sample_limit]
            if isinstance(item, dict)
        ]

    return {
        "without_relationships_count": orphan_data.get(
            "without_relationships_count",
            0,
        ),
        "not_in_any_view_count": orphan_data.get("not_in_any_view_count", 0),
        "fully_orphaned_count": orphan_data.get("fully_orphaned_count", 0),
        "sample_without_relationships": sample("without_relationships"),
        "sample_not_in_any_view": sample("not_in_any_view"),
        "sample_fully_orphaned": sample("fully_orphaned"),
    }


def _inspect_active_model_data(
    *,
    include_semantic_validation: bool,
    include_orphans: bool,
    sample_limit: int,
) -> dict[str, Any]:
    model_manager = _model_manager()
    limit = _sample_limit(sample_limit)

    data: dict[str, Any] = {
        "model_info": model_manager.get_model_info(),
        "summary": model_manager.summarize_model(),
        "counts_by_type": model_manager.count_by_type(),
        "visual_validation": model_manager.validate_model(),
        "recommended_next_calls": _recommended_next_calls(),
        "agent_guidance": [
            (
                "Use MCP tools and resources to inspect this server; do not inspect "
                "the MCP implementation source code to learn normal usage."
            ),
            (
                "For local files, call load_model_from_file. "
                "Do not pass file paths to load_model_from_content."
            ),
            (
                "Use returned IDs exactly as source_id, target_id, element_id, "
                "relationship_id, and view_id in later calls."
            ),
        ],
    }

    if include_semantic_validation:
        data["semantic_validation"] = _compact_issue_summary(
            # This builds its own sample-based summary, so it needs the
            # per-issue dicts rather than the grouped default.
            model_manager.validate_semantics(detail="full"),
            limit,
        )

    if include_orphans:
        data["orphans"] = _compact_orphan_summary(
            model_manager.list_orphan_elements(),
            limit,
        )

    return data


@mcp.tool(annotations=READ_ONLY_TOOL)
async def get_usage_guide() -> dict[str, Any]:
    """Return the client-facing usage guide for this ArchiMate MCP server.

    Call this tool when you are unsure how to operate the server. It is
    intended to prevent source-code inspection: do not inspect the MCP
    server source code to learn normal usage. Use this guide, prompts,
    tools/list, and resources/list instead.

    Returns:
        Success envelope with recommended workflows, anti-patterns,
        response conventions, and important tools.
    """
    return success_response(
        {
            "purpose": (
                "Create, load, inspect, edit, validate, and export one active "
                "in-memory ArchiMate model."
            ),
            "agent_operating_rules": [
                (
                    "Use MCP tools, prompts, and resources for usage information; "
                    "do not inspect the server source code to learn normal usage."
                ),
                (
                    "Start by loading or creating a model, then inspect it before "
                    "editing."
                ),
                (
                    "Call list_supported_types before creating new ArchiMate "
                    "elements or relationships if exact type names are uncertain."
                ),
                (
                    "Call recommend_relationship or get_relationship_compatibility "
                    "before creating relationships from generated intent."
                ),
                (
                    "Use semantic_validation='strict' for final model generation "
                    "relationships and quality_gate='strict' for final exports."
                ),
                "Use IDs returned in tool responses for later calls.",
                (
                    "Set a viewpoint when creating views (create_view "
                    "viewpoint=...): layered for mixed-layer overviews, "
                    "capability for capability maps. Take the exact value "
                    "from list_supported_types (data.viewpoints) — viewpoint "
                    "names are not guessable from their English names."
                ),
                "After edits, call validate_model and validate_semantics.",
            ],
            "standards_target": {
                "hard_validation": "ArchiMate 3.2-compatible",
                "backend": f"{backend_metadata()['backend']} relationship matrix",
                "future_note": (
                    "ArchiMate 4 requires a future versioned rule provider."
                ),
            },
            "existing_model_workflow": [
                {
                    "step": 1,
                    "tool": "load_model_from_file",
                    "args": {
                        "path": "/path/to/model.archimate",
                        "content_format": "archi",
                        "inspect_after_load": True,
                    },
                },
                {
                    "step": 2,
                    "tool": "inspect_active_model",
                    "args": {"include_semantic_validation": True},
                },
                {
                    "step": 3,
                    "tool": "query_elements",
                    "args": {"filter_criteria": {}},
                },
                {
                    "step": 4,
                    "tool": "summarize_view",
                    "args": {"view_id": "<view id>"},
                },
            ],
            "common_anti_patterns": [
                {
                    "avoid": "Passing a filesystem path to load_model_from_content.",
                    "use_instead": "load_model_from_file.",
                },
                {
                    "avoid": "Guessing element or relationship type names.",
                    "use_instead": "list_supported_types.",
                },
                {
                    "avoid": (
                        "Modeling BusinessProcess -> ApplicationService as Access."
                    ),
                    "use_instead": (
                        "recommend_relationship; commonly ApplicationService "
                        "serves BusinessProcess."
                    ),
                },
                {
                    "avoid": "Using Flow for BusinessProcess data usage.",
                    "use_instead": "Access with an access_type such as Read or Write.",
                },
                {
                    "avoid": (
                        "Treating relationship coverage views as stakeholder views."
                    ),
                    "use_instead": (
                        "Mark coverage views as QA and create separate "
                        "stakeholder-facing views with purpose/concerns metadata."
                    ),
                },
                {
                    "avoid": "Creating view connections before both endpoint "
                    "elements are visible in the view.",
                    "use_instead": (
                        "add_nodes_to_view, then connect_visible_relationships."
                    ),
                },
                {
                    "avoid": "Reading implementation files to discover how tools work.",
                    "use_instead": (
                        "get_usage_guide, MCP prompts, tools/list, and resources/list."
                    ),
                },
            ],
            "relationship_workflow": [
                "Resolve source and target IDs.",
                "Call recommend_relationship with the intended meaning.",
                "Create using add_relationship with semantic_validation='strict'.",
                "Run validate_semantics and repair_semantic_issues only when explicit.",
            ],
            "validation_before_export_checklist": [
                "validate_model",
                "validate_semantics",
                "list_orphan_elements",
                "ensure_all_relationships_in_views",
                "build_quality_report",
                "export_model_to_file with quality_gate='strict'",
            ],
            "togaf_readiness_guidance": (
                "assess_togaf_readiness is advisory and does not certify "
                "TOGAF compliance."
            ),
            "response_format": {
                "success": {"status": "success", "message": "str", "data": "object"},
                "error": {
                    "status": "error",
                    "message": "str",
                    "error": {"code": "str"},
                },
            },
            "recommended_next_calls": _recommended_next_calls(),
        },
        "Usage guide returned.",
    )


@mcp.tool(annotations=DESTRUCTIVE_TOOL)
async def load_model_from_file(
    path: str,
    content_format: str = "archi",
    *,
    inspect_after_load: bool = True,
    include_semantic_validation: bool = True,
    sample_limit: int = 10,
) -> dict[str, Any]:
    """Load an ArchiMate model from a local file (replaces active model).

    The preferred entry point when the user gives a local `.archimate`
    or XML file path. Expects a filesystem path readable by the MCP
    server process; for raw XML text use `load_model_from_content`.
    By default the response includes a compact inspection (summary,
    type counts, validation status, recommended next calls) so a
    separate `inspect_active_model` round trip is unnecessary.

    Args:
        path: Local filesystem path readable by the MCP server process.
            `~` is expanded; relative paths resolve against the server CWD.
        content_format: One of `archi` (default, Archi native
            `.archimate`), `archimate` (Open Group exchange XML), or
            `xml`.
        inspect_after_load: When true (default), include a compact model
            summary, type counts, validation status, and recommended next
            calls in the response.
        include_semantic_validation: When true (default), include a
            compact semantic validation summary when inspecting.
        sample_limit: Maximum number of issue/orphan examples to include
            in compact summaries. Clamped to 0-50.

    Returns:
        Success envelope with `data.model_info`, `data.loaded_from`, and
        optionally `data.inspection`.

    Errors:
        `INVALID_PATH`, `FILE_NOT_FOUND`, `FILE_READ_ERROR`,
        `UnsupportedFormatError`, or `ModelOperationError`.
    """
    if not isinstance(path, str) or not path.strip():
        return error_response("File path must be a non-empty string.", "INVALID_PATH")

    try:
        # Boundary first: a path outside the allowed roots must be
        # refused before this reports whether a file is there, so the
        # tool cannot be used to probe for files it may not read.
        model_path = filesystem.resolve_read_path(path)
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)

    if not model_path.is_file():
        return error_response(f"File not found: {path}", "FILE_NOT_FOUND")

    try:
        model_content = model_path.read_text(encoding="utf-8")
        model_manager = _model_manager()
        model_manager.load_model_from_string(model_content, content_format)
        data: dict[str, Any] = {
            "loaded_from": str(model_path),
            "content_format": content_format,
            "model_info": model_manager.get_model_info(),
            "recommended_next_calls": _recommended_next_calls(),
        }
        if inspect_after_load:
            data["inspection"] = _inspect_active_model_data(
                include_semantic_validation=include_semantic_validation,
                include_orphans=True,
                sample_limit=sample_limit,
            )
        return success_response(data, "Model loaded.")
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)
    except OSError as exc:
        return error_response(str(exc), "FILE_READ_ERROR")


@mcp.tool(annotations=READ_ONLY_TOOL)
async def inspect_active_model(
    *,
    include_semantic_validation: bool = True,
    include_orphans: bool = True,
    sample_limit: int = 10,
) -> dict[str, Any]:
    """Inspect the active model without dumping full XML or source code.

    Use this immediately after loading an existing model and before
    editing. It combines model info, summaries, type counts, visual
    validation, compact semantic validation, compact orphan summaries,
    and recommended next calls.

    Args:
        include_semantic_validation: Include compact semantic validation
            summary. Defaults to true.
        include_orphans: Include compact orphan element summary.
            Defaults to true.
        sample_limit: Maximum number of issue/orphan examples to include.
            Clamped to 0-50.

    Returns:
        Success envelope with compact inspection data.

    Errors:
        `ModelNotFoundError` if no model is active.
    """
    try:
        return success_response(
            _inspect_active_model_data(
                include_semantic_validation=include_semantic_validation,
                include_orphans=include_orphans,
                sample_limit=sample_limit,
            ),
            "Active model inspected.",
        )
    except ArchiMateMCPError as exc:
        return error_response(str(exc), exc.code, exc.details)

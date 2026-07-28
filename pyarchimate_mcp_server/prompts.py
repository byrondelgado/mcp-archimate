"""MCP prompts for common ArchiMate workflows."""

from pyarchimate_mcp_server.mcp_app import mcp


@mcp.prompt(
    title="Load Existing ArchiMate Model",
    description=(
        "Guide an agent to load a local ArchiMate file through tools instead "
        "of inspecting server source code."
    ),
)
def load_existing_model_prompt(path: str, content_format: str = "archi") -> str:
    """Prompt for loading and inspecting an existing model."""
    return f"""\
Load the existing ArchiMate model at `{path}` using MCP tools.

Rules:
- Do not inspect the MCP server source code to learn usage.
- Call `get_usage_guide` if you need workflow guidance.
- Use `load_model_from_file`, not `load_model_from_content`, because the
  user gave a file path.
- Use `content_format="{content_format}"` unless the file format is clearly different.
- After loading, inspect the returned `data.inspection` before editing.
- Use IDs returned by the server exactly in later calls.

Recommended call:
`load_model_from_file(path="{path}", content_format="{content_format}",
inspect_after_load=true)`
"""


@mcp.prompt(
    title="Inspect Active ArchiMate Model",
    description="Guide an agent to understand the active model before editing it.",
)
def inspect_active_model_prompt() -> str:
    """Prompt for compact active model inspection."""
    return """\
Inspect the active ArchiMate model using MCP tools.

Rules:
- Do not inspect the MCP server source code for normal usage.
- Call `inspect_active_model(include_semantic_validation=true, include_orphans=true)`.
- Use the returned model info, summary, type counts, validation results,
  and recommended next calls.
- Query concrete IDs with `query_elements({})`, `query_relationships({})`,
  or `summarize_view(view_id=...)` only when needed.
- Avoid dumping full XML unless the user explicitly asks for export or raw content.
"""


@mcp.prompt(
    title="Improve ArchiMate Model",
    description="Guide an agent through safe model improvement using MCP tools.",
)
def improve_model_prompt(goal: str = "Improve the active model") -> str:
    """Prompt for safe model improvement."""
    return f"""\
Improve the active ArchiMate model for this goal: {goal}

Workflow:
1. Call `inspect_active_model(include_semantic_validation=true, include_orphans=true)`.
2. Use `list_supported_types` before adding new concepts if exact types are uncertain.
3. Use `query_elements` and `query_relationships` to get IDs before editing.
4. Apply focused edits with element, relationship, and view tools.
   Give each view a viewpoint (create_view/update_view viewpoint=...).
5. Call `validate_model` and `validate_semantics`.
6. If relationships are missing from diagrams, call `ensure_all_relationships_in_views`.
7. Export with `export_model_to_file` only after validation.

Rules:
- Do not inspect the MCP server source code to learn usage.
- Do not guess IDs; use IDs returned by MCP tools.
- Do not pass local file paths to `load_model_from_content`.
"""


@mcp.prompt(
    title="Validate And Export ArchiMate Model",
    description="Guide an agent to validate and export the active model.",
)
def validate_and_export_model_prompt(
    output_path: str,
    output_format: str = "archi",
) -> str:
    """Prompt for model validation and export."""
    return f"""\
Validate and export the active ArchiMate model.

Workflow:
1. Call `inspect_active_model(include_semantic_validation=true, include_orphans=true)`.
2. Call `validate_model`.
3. Call `validate_semantics`.
4. If the user wants Archi Validator relationship coverage, call
   `ensure_all_relationships_in_views`.
5. Export with `export_model_to_file(path="{output_path}",
   output_format="{output_format}", auto_layout=true)`.

Rules:
- Do not inspect the MCP server source code to learn normal usage.
- Use `output_format="archi"` for files that should open directly in Archi.
- Use `output_format="archimate"` for Open Group exchange XML.
"""

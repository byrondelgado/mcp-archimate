import asyncio

import pyarchimate_mcp_server.server  # noqa: F401
from pyarchimate_mcp_server.mcp_app import mcp


def test_workflow_tools_are_discoverable():
    tools = asyncio.run(mcp.list_tools())
    tools_by_name = {tool.name: tool for tool in tools}

    assert "get_usage_guide" in tools_by_name
    assert "load_model_from_file" in tools_by_name
    assert "inspect_active_model" in tools_by_name
    assert "get_relationship_compatibility" in tools_by_name
    assert "recommend_relationship" in tools_by_name
    assert "repair_semantic_issues" in tools_by_name
    assert "build_quality_report" in tools_by_name
    assert "assess_togaf_readiness" in tools_by_name
    assert "render_view_to_svg_file" in tools_by_name
    assert "update_model" in tools_by_name
    assert "add_note_to_view" in tools_by_name
    assert "do not inspect" in tools_by_name["get_usage_guide"].description.lower()
    assert (
        "load_model_from_content" in tools_by_name["load_model_from_file"].description
    )


def test_workflow_prompts_are_discoverable():
    prompts = asyncio.run(mcp.list_prompts())
    prompt_names = {prompt.name for prompt in prompts}

    assert "load_existing_model_prompt" in prompt_names
    assert "inspect_active_model_prompt" in prompt_names
    assert "improve_model_prompt" in prompt_names
    assert "validate_and_export_model_prompt" in prompt_names


def test_all_tools_declare_annotations():
    tools = asyncio.run(mcp.list_tools())

    missing = [tool.name for tool in tools if tool.annotations is None]
    assert missing == []

    tools_by_name = {tool.name: tool for tool in tools}
    assert tools_by_name["query_elements"].annotations.readOnlyHint is True
    assert tools_by_name["delete_element"].annotations.destructiveHint is True
    assert tools_by_name["load_model_from_file"].annotations.destructiveHint is True
    assert tools_by_name["update_element"].annotations.idempotentHint is True
    assert tools_by_name["add_element"].annotations.destructiveHint is False
    # Editing model metadata re-applies the same values on a repeat call,
    # so it is idempotent rather than destructive like create_empty_model.
    assert tools_by_name["update_model"].annotations.idempotentHint is True
    assert tools_by_name["update_model"].annotations.destructiveHint is False
    # Rendering never touches the model, but it does write a file to a
    # caller-supplied path, so it is annotated exactly like
    # export_model_to_file rather than claiming readOnlyHint.
    svg_annotations = tools_by_name["render_view_to_svg_file"].annotations
    assert svg_annotations.destructiveHint is False
    assert svg_annotations.idempotentHint is True
    assert svg_annotations == tools_by_name["export_model_to_file"].annotations
    # Adding a note creates a visual node and never destroys anything, so it
    # is annotated exactly like add_node_to_view.
    note_annotations = tools_by_name["add_note_to_view"].annotations
    assert note_annotations.readOnlyHint is False
    assert note_annotations.destructiveHint is False
    assert note_annotations == tools_by_name["add_node_to_view"].annotations


def test_invalid_type_errors_include_suggestions():
    import pytest

    from pyarchimate_mcp_server.exceptions import InvalidElementTypeError
    from pyarchimate_mcp_server.model_manager import ArchimateModelManager

    manager = ArchimateModelManager()
    manager.create_new_model("Suggestion Test")

    with pytest.raises(InvalidElementTypeError) as exc_info:
        manager.add_archimate_element("X", "Actor")

    assert "BusinessActor" in str(exc_info.value)
    assert "BusinessActor" in exc_info.value.details["suggestions"]

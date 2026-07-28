# ArchiMate MCP Server User Guide

This guide explains how to install, run, and use the ArchiMate MCP server from an MCP client such as Claude Desktop, the MCP Inspector, or another agent runtime that supports the Model Context Protocol.

The server provides an in-memory ArchiMate model workspace backed by `pyArchimate`. MCP clients can create models, load ArchiMate XML content, add elements and relationships, create views, lay out diagrams, inspect resources, and export model content or CSV data.

## Contents

- [What This Server Provides](#what-this-server-provides)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running The Server](#running-the-server)
- [Connecting From MCP Clients](#connecting-from-mcp-clients)
- [Core Concepts](#core-concepts)
- [Response Format](#response-format)
- [Resources](#resources)
- [Tools](#tools)
- [Common Workflows](#common-workflows)
- [Supported Model Formats](#supported-model-formats)
- [Supported ArchiMate Types](#supported-archimate-types)
- [Troubleshooting](#troubleshooting)

## What This Server Provides

The ArchiMate MCP server exposes ArchiMate model operations over MCP:

- Model lifecycle: create an empty model, load model XML, export model XML/content, write a model file, and inspect active model metadata.
- Model metadata: set the model name, documentation, and properties at creation time, and edit them afterwards with `update_model` — including on a model that was loaded from a file rather than created here.
- Element operations: create, batch-create, update, delete, list, and query ArchiMate elements.
- Relationship operations: create, batch-create, update, delete, list, and query relationships between elements.
- View operations: create views, add nodes, add relationship connections, connect visible or missing relationships, annotate a diagram with notes, and auto-layout nodes.
- Higher-level generation: create a full model from a structured JSON specification with rollback on failure.
- Validation and summaries: validate visual references, validate semantics, summarize model/view contents, count by type, and list orphan elements.
- Data export: export a native `.archimate` file, return XML content, or export elements and relationships as CSV strings.
- Visual review: render one view to an SVG file (`render_view_to_svg_file`) so a person can see the diagram without Archi. SVG is a rendering, not a model format — it is not importable into Archi and does not replace the two export formats.

The server currently manages one active model per server process. Creating or loading a model replaces the current active model. Model state is kept in memory until a client exports it with `export_model_to_file` or `export_model_content`.

## Requirements

- Python 3.10 or newer.
- `uv` for dependency management.
- An MCP client, such as Claude Desktop, MCP Inspector, or a custom MCP client.

The project's runtime dependencies are:

- `mcp` (>= 1.28.1, < 2.0.0)
- `pyArchimate` (1.12.x)
- `pydantic`
- `lxml`

The `mcp[cli]` extra, which provides the `mcp` command used by the Inspector and
Claude Desktop install workflows below, is a **development** dependency rather
than a runtime one. `uv sync` installs it by default, so the commands in
[Connecting From MCP Clients](#connecting-from-mcp-clients) work from a clone.
The server itself never needs it.

## Installation

Clone the repository and install dependencies:

```bash
git clone <repository-url>
cd mcp-archimate
uv sync
```

If your environment does not support `uv sync`, create the virtual environment and sync from the project metadata:

```bash
uv venv
uv sync
```

Verify that the server starts:

```bash
uv run python -m pyarchimate_mcp_server.server
```

The command starts the MCP server using stdio. Stop it with `Ctrl+C` when testing from a terminal.

## Running The Server

From the repository root, run either entrypoint:

```bash
uv run python -m pyarchimate_mcp_server.server
```

or:

```bash
uv run mcp-archimate
```

Both commands run the FastMCP application named `archimate-mcp`.

## Connecting From MCP Clients

### MCP Inspector

Use the Inspector during local development to browse resources, inspect tool schemas, and run test calls:

```bash
uv run mcp dev pyarchimate_mcp_server/server.py
```

If you want the Inspector to mount the local package in editable mode:

```bash
uv run mcp dev pyarchimate_mcp_server/server.py --with-editable .
```

### Claude Desktop With MCP CLI

Install the server into Claude Desktop with:

```bash
uv run mcp install pyarchimate_mcp_server/server.py --name "ArchiMate MCP Server"
```

You can pass environment variables during install:

```bash
uv run mcp install pyarchimate_mcp_server/server.py \
  --name "ArchiMate MCP Server" \
  -v LOG_LEVEL=INFO
```

### Claude Desktop Manual Configuration

You can also add the server manually to `claude_desktop_config.json`. Replace `/absolute/path/to/mcp-archimate` with your local repository path.

```json
{
  "mcpServers": {
    "archimate-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/mcp-archimate",
        "run",
        "python",
        "-m",
        "pyarchimate_mcp_server.server"
      ]
    }
  }
}
```

Restart Claude Desktop after editing the configuration.

### Custom MCP Clients

Custom clients should launch the server as a stdio MCP process. The command should run from the repository root or use `uv --directory` to set it:

```bash
uv --directory /absolute/path/to/mcp-archimate run python -m pyarchimate_mcp_server.server
```

The server does not require a network port for stdio clients.

## Recommended Agent Workflows

Some local MCP clients do not consistently read long server instructions before
choosing tools. This server therefore exposes workflow tools and prompts that
make the intended usage visible through normal MCP discovery.

Agents should use these MCP tools and prompts instead of inspecting the server
source code to learn normal usage.

### First Calls For Existing Models

When the user gives a local `.archimate` or XML file path, start with:

```json
{
  "tool": "load_model_from_file",
  "arguments": {
    "path": "/absolute/path/to/model.archimate",
    "content_format": "archi",
    "inspect_after_load": true
  }
}
```

`load_model_from_file` loads the file, returns `model_info`, and includes a
compact inspection with summaries, type counts, validation status, view
summaries, and recommended next calls.

Use `load_model_from_content` only when the caller provides raw XML content.
Do not pass filesystem paths to `load_model_from_content`.

### Understanding A Loaded Model

After loading, call:

```json
{
  "tool": "inspect_active_model",
  "arguments": {
    "include_semantic_validation": true,
    "include_orphans": true
  }
}
```

Use the returned view IDs with `summarize_view`, and use `query_elements` or
`query_relationships` when concrete IDs are needed before edits.

### Usage Guidance And Prompts

Call `get_usage_guide` when the tool workflow is unclear. It returns operating
rules, common anti-patterns, response conventions, and recommended next calls.

The server also registers MCP prompts for common workflows:

| Prompt | Purpose |
| --- | --- |
| `load_existing_model_prompt` | Load a local model file through tools. |
| `inspect_active_model_prompt` | Understand the active model before editing. |
| `improve_model_prompt` | Make safe, focused model improvements. |
| `validate_and_export_model_prompt` | Validate and export the active model. |

### Local Inspector URLs

When using `uv run mcp dev pyarchimate_mcp_server/server.py`, the URL printed
by MCP Inspector, such as `http://localhost:6274/`, is the Inspector UI. The
ArchiMate MCP server itself is launched behind that UI over stdio. Most local
agent clients should use the stdio command:

```bash
uv --directory /absolute/path/to/mcp-archimate run python -m pyarchimate_mcp_server.server
```

## Core Concepts

### Active Model

Most tools operate on the active model. Before adding elements, relationships, or views, call `create_empty_model`, `load_model_from_content`, or `load_model_from_file`.

If no active model exists, model-dependent tools return an error response with a code such as `ModelNotFoundError`.

### IDs

The server returns generated IDs for models, elements, relationships, views, nodes, and connections. Use those IDs in later calls. For example:

1. Call `add_element`.
2. Save the returned `data.id`.
3. Use that ID as `source_id`, `target_id`, or `element_id` in later relationship and view calls.

### Resources Versus Tools

Resources are read-only views of the active model. Tools perform actions and may change the active model.

### Persistence

The server keeps the active model in memory. To load an existing local file, call `load_model_from_file`. To persist work directly to disk, call `export_model_to_file`. To retrieve XML without writing a file, call `export_model_content`.

For Archi, use `output_format="archi"` and a `.archimate` path. For Open Group exchange XML, use `output_format="archimate"`.

### Folder Paths

Folder roots are normalized before storage and export. For element folders, the root must match the element's ArchiMate category. For example, a `BusinessActor` accepts `Business`, `/Business`, `business`, or `/Business/Actors`, and those are normalized under `/Business`.

Recognized roots are `/Strategy`, `/Business`, `/Application`, `/Technology`, `/Motivation`, `/Implementation & Migration`, `/Other`, `/Relations`, and `/Views`. The aliases `Implementation`, `Implementation and Migration`, `Physical`, `Junction`, `Relationships`, and `Diagrams` are accepted where they map to Archi's native model tree. Invalid absolute roots return a `ModelOperationError` with the affected element, relationship, or view ID/name.

## Response Format

Tools and resources return a consistent JSON envelope.

Successful response:

```json
{
  "status": "success",
  "message": "Operation completed.",
  "data": {}
}
```

Error response:

```json
{
  "status": "error",
  "message": "Failure reason.",
  "error": {
    "code": "ErrorCode"
  }
}
```

Common error codes include:

- `ModelNotFoundError`
- `ElementNotFoundError`
- `RelationshipNotFoundError`
- `ViewNotFoundError`
- `InvalidElementTypeError`
- `InvalidRelationshipTypeError`
- `UnsupportedFormatError`
- `ModelOperationError`
- `INVALID_MODEL_NAME`
- `INVALID_ELEMENT_NAME`
- `INVALID_VIEW_NAME`
- `INVALID_MODEL_CONTENT`
- `INVALID_PATH`
- `INVALID_SPEC`
- `FILE_NOT_FOUND`
- `FILE_READ_ERROR`

## Resources

The server registers the following MCP resources.

| Resource URI | Description |
| --- | --- |
| `pyarchimate://activemodel/info` | Returns model name, ID, documentation, properties, element count, relationship count, view count, and loaded state. |
| `pyarchimate://activemodel/content` | Returns the active model serialized as XML content. |
| `pyarchimate://activemodel/validation` | Returns pyArchimate validation results for broken visual connection and node references. |
| `pyarchimate://activemodel/elements` | Returns all elements in the active model. |
| `pyarchimate://activemodel/elements/{element_id}` | Returns one element by ID. |
| `pyarchimate://activemodel/relationships` | Returns all relationships in the active model. |
| `pyarchimate://activemodel/relationships/{relationship_id}` | Returns one relationship by ID. |
| `pyarchimate://activemodel/views` | Returns all views in the active model. |
| `pyarchimate://activemodel/views/{view_id}` | Returns one view by ID, including nodes and connections. |

### Model Info Shape

`pyarchimate://activemodel/info` returns:

```json
{
  "status": "success",
  "message": "OK",
  "data": {
    "name": "Example Model",
    "id": "generated-model-id",
    "documentation": null,
    "properties": {},
    "elements_count": 2,
    "relationships_count": 1,
    "views_count": 1,
    "is_loaded": true
  }
}
```

When no model is active, `is_loaded` is `false` and the counts are zero.

`documentation` and `properties` are the model's own metadata. They come from the loaded file, or from `create_empty_model` / `create_model_from_spec`, and are edited with [`update_model`](#update_model). The same payload is returned as `data.model_info` by those tools.

### Element Shape

Elements are returned as:

```json
{
  "id": "element-id",
  "name": "Customer",
  "type": "BusinessActor",
  "description": "External customer",
  "properties": {
    "owner": "EA"
  },
  "folder": "/Business",
  "incoming_relationship_ids": [],
  "outgoing_relationship_ids": ["relationship-id"]
}
```

### Relationship Shape

Relationships are returned as:

```json
{
  "id": "relationship-id",
  "name": "uses",
  "type": "Serving",
  "description": "Application serves business process",
  "properties": {},
  "access_type": null,
  "influence_strength": null,
  "is_directed": null,
  "source_element_id": "source-element-id",
  "target_element_id": "target-element-id"
}
```

### View Shape

Views are returned as:

```json
{
  "id": "view-id",
  "name": "Context View",
  "description": null,
  "properties": {},
  "metadata": {},
  "primary_viewpoint": null,
  "nodes": [
    {
      "id": "node-id",
      "element_id": "element-id",
      "element_name": "Customer",
      "element_type": "BusinessActor",
      "parent_node_id": null,
      "note_text": null,
      "x": 40,
      "y": 40,
      "width": 160,
      "height": 80
    },
    {
      "id": "note-node-id",
      "element_id": null,
      "element_name": null,
      "element_type": null,
      "parent_node_id": null,
      "note_text": "Retire in FY27",
      "x": 600,
      "y": 40,
      "width": 185,
      "height": 80
    }
  ],
  "connections": [
    {
      "id": "connection-id",
      "relationship_id": "relationship-id",
      "relationship_type": "Serving",
      "source_node_id": "source-node-id",
      "target_node_id": "target-node-id"
    }
  ]
}
```

Not every node carries an element. `note_text` holds the text of a diagram-only note added by [`add_note_to_view`](#add_note_to_view), and is `null` on every other node — including the layer bands `auto_layout_view` adds, which are element-less as well. `note_text` is therefore how a note is told apart from a band.

A note connector line also appears in `connections`, with `relationship_type: null` because it stands for no ArchiMate relationship. `relationship_id` on such a connection is an internal visual reference and resolves to no relationship in the model — do not pass it to `update_relationship` or `delete_relationship`.

## Tools

### Model Tools

#### `create_empty_model`

Create a new empty ArchiMate model and make it active.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `name` | string | yes | none | Model name. Must not be blank. Leading and trailing whitespace is stripped. |
| `description` | string or null | no | `null` | Model-level documentation. Read back as `data.model_info.documentation`. |
| `properties` | object or null | no | `null` | Model-level properties. Keys and values are stored as strings. |

Example:

```json
{
  "name": "Customer Portal Architecture",
  "description": "Target architecture for the payments platform.",
  "properties": {
    "owner": "Enterprise Architecture"
  }
}
```

Returns `data.model_id` and `data.model_info`.

Errors: `INVALID_MODEL_NAME`.

Calling this tool replaces the current active model. Use [`update_model`](#update_model) to change this metadata later.

#### `update_model`

Update the active model's own name, documentation, and properties. This works on any active model, including one loaded from a file, so metadata is not a create-time-only decision.

There is no `model_id` parameter: exactly one model is active at a time.

Parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `updates` | object | yes | Fields to change. Only the supplied keys are written; everything else is left alone. |

Supported `updates` keys:

| Key | Type | Description |
| --- | --- | --- |
| `name` | string | New model name. Must be a non-blank string; it is stripped, exactly as in `create_empty_model`. |
| `description` | string | New model documentation. Read back as `documentation`. |
| `documentation` | string | Accepted alias for `description`, matching the read-side field name. |
| `properties` | object | Property updates **merged** into the existing model properties. Existing keys are overwritten, absent keys are kept. Nothing is ever cleared. |

Example:

```json
{
  "updates": {
    "name": "Customer Portal Architecture (Target)",
    "description": "Documented after loading the baseline file.",
    "properties": {
      "reviewer": "Architecture Board"
    }
  }
}
```

Returns `data.model_info`, the same shape as the `pyarchimate://activemodel/info` resource.

Unlike `update_element`, an unrecognized key is an error rather than a silent no-op, because a mis-keyed update would otherwise report success while leaving the metadata unwritten. The error lists both sides:

```json
{
  "status": "error",
  "message": "Unsupported model update keys: desc.",
  "error": {
    "code": "INVALID_MODEL_UPDATE",
    "details": {
      "unsupported_keys": ["desc"],
      "supported_keys": ["name", "description", "documentation", "properties"]
    }
  }
}
```

Errors: `INVALID_MODEL_UPDATE` (`updates` carries unsupported keys), `INVALID_MODEL_NAME` (`name` present but not a non-blank string), `ModelOperationError` (`properties` is not an object), `ModelNotFoundError` (no active model).

Passing a non-object `updates` does not produce an error envelope at all: `updates` is typed `dict[str, Any]`, so the MCP layer rejects it during schema validation and the client receives a protocol-level tool error (`Input should be a valid dictionary`) before this tool runs.

Every check runs before anything is written, so `update_model` is all-or-nothing: an error envelope means no field was applied, not even the valid ones sent alongside the bad one. A rejected `properties` shape leaves the name and documentation exactly as they were.

Model name, documentation, and properties survive both export formats and are restored on load. In a native `.archimate` export the documentation is written as the model's `<purpose>` element — Archi's model Purpose field — and properties as `<property key="..." value="..."/>`.

#### `load_model_from_content`

Load an ArchiMate model from XML string content and make it active.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `model_content` | string | yes | none | XML content to load. |
| `content_format` | string | no | `archimate` | One of `archimate`, `archi`, or `xml`. |

Example:

```json
{
  "model_content": "<model ...>...</model>",
  "content_format": "archimate"
}
```

The XML content must be 10 MiB or smaller. DTD and entity declarations are rejected.

Errors: `INVALID_MODEL_CONTENT`, `UnsupportedFormatError`, `ModelOperationError`.

Calling this tool replaces the current active model.

#### `load_model_from_file`

Load an ArchiMate model from a local `.archimate` or XML file and make it active.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `path` | string | yes | none | Local input path visible to the MCP server process. |
| `content_format` | string | no | `archi` | One of `archi`, `archimate`, or `xml`. |
| `inspect_after_load` | boolean | no | `true` | Include a compact inspection (`data.inspection`: summary, type counts, validation status, recommended next calls) so a separate `inspect_active_model` round trip is unnecessary. |
| `include_semantic_validation` | boolean | no | `true` | Include a compact semantic validation summary in the inspection. |
| `sample_limit` | integer | no | `10` | Maximum issue/orphan examples in compact summaries (0-50). |

Example:

```json
{
  "path": "/tmp/customer-portal.archimate",
  "content_format": "archi"
}
```

Use this tool instead of `load_model_from_content` whenever the caller has a file path. Returns `data.model_info`, `data.loaded_from`, `data.recommended_next_calls`, and (by default) `data.inspection`.

Errors: `INVALID_PATH`, `FILE_NOT_FOUND`, `FILE_READ_ERROR`, `UnsupportedFormatError`, `ModelOperationError`.

Calling this tool replaces the current active model.

#### `export_model_content`

Export the active model as XML string content. Optionally lay out all views before serialization.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `output_format` | string | no | `archimate` | One of `archimate`, `archi`, or `xml`. Use `archi` for Archi native `.archimate` content. |
| `auto_layout` | boolean | no | `false` | When `true`, runs layout on all views before export. |
| `layout_strategy` | string | no | `layered_by_type` | Layout strategy used when `auto_layout` is `true`. One of `layered_by_type`, `layered`, or `grid`. |
| `layout_engine` | string | no | `internal` | Node placement engine applied to every view when `auto_layout` is `true`. One of `internal` or `pyarchimate` — see [Layout engines](#layout-engines). Validated even when `auto_layout` is `false`, so a typo is never silently ignored. |
| `quality_gate` | string | no | `off` | One of `off`, `warn`, or `strict`. Runs a quality report (visual + semantic + coverage checks) before export. `strict` blocks the export when checks fail; `warn` exports and reports the failures. |
| `allow_semantic_issues` | boolean | no | `false` | With an active gate, tolerate semantic validation failures. |
| `allow_visual_issues` | boolean | no | `false` | With an active gate, tolerate visual reference failures. |
| `allow_orphans` | boolean | no | `true` | With an active gate, tolerate elements not placed in any view. |
| `include_quality_report` | boolean | no | `false` | Include `data.quality_report` in the response even when the gate is `off`. |

Example:

```json
{
  "output_format": "archi",
  "auto_layout": true,
  "layout_strategy": "layered_by_type",
  "layout_engine": "internal"
}
```

Returns `data.content`, `data.auto_layout`, `data.layout_strategy`, and `data.layout_engine`.

Errors: `ModelNotFoundError`, `UnsupportedFormatError`, `ModelOperationError`.

#### `export_model_to_file`

Export the active model directly to a local file. This is the preferred tool when the user wants a `.archimate` file that Archi can open directly.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `path` | string | yes | none | Local output path. Parent directories are created if needed. |
| `output_format` | string | no | `archi` | One of `archi`, `archimate`, or `xml`. |
| `auto_layout` | boolean | no | `false` | When `true`, runs layout on all views before export. |
| `layout_strategy` | string | no | `layered_by_type` | Layout strategy used when `auto_layout` is `true`. |
| `layout_engine` | string | no | `internal` | Node placement engine applied to every view when `auto_layout` is `true`. One of `internal` or `pyarchimate` — see [Layout engines](#layout-engines). Validated even when `auto_layout` is `false`. Never written into the exported file. |
| `quality_gate` | string | no | `off` | One of `off`, `warn`, or `strict`. Runs a quality report before export; `strict` blocks the export when checks fail. |
| `allow_semantic_issues` | boolean | no | `false` | With an active gate, tolerate semantic validation failures. |
| `allow_visual_issues` | boolean | no | `false` | With an active gate, tolerate visual reference failures. |
| `allow_orphans` | boolean | no | `true` | With an active gate, tolerate elements not placed in any view. |
| `include_quality_report` | boolean | no | `false` | Include `data.quality_report` in the response even when the gate is `off`. |

Example:

```json
{
  "path": "/tmp/customer-portal.archimate",
  "output_format": "archi",
  "auto_layout": true,
  "layout_strategy": "layered",
  "layout_engine": "internal"
}
```

Returns `data.path`, `data.bytes_written`, `data.output_format`, `data.auto_layout`, `data.layout_strategy`, and `data.layout_engine`.

Errors: `ModelNotFoundError`, `UnsupportedFormatError`, `ModelOperationError`.

#### `export_elements_to_csv`

Export all active model elements as CSV.

Parameters: none.

Errors: `ModelNotFoundError`.

Returns `data.csv_data`.

The CSV includes base columns `id`, `name`, `type`, and `description`. Custom properties are emitted as `Property:<property-name>` columns.

#### `export_relationships_to_csv`

Export all active model relationships as CSV.

Parameters: none.

Errors: `ModelNotFoundError`.

Returns `data.csv_data`.

The CSV includes base columns `id`, `name`, `type`, `source_id`, and `target_id`. Custom properties are emitted as `Property:<property-name>` columns.

#### `validate_model`

Validate visual references in the active model using pyArchimate's model checks. A view connection whose relationship is no longer in the model, or a view node whose element is no longer in the model, is reported as invalid.

Diagram-only annotation connectors are excluded from the invalid-connection list. A note line — a connector with a note ([`add_note_to_view`](#add_note_to_view), or an Archi Note in an imported model) at one end — has no backing relationship by design, so reporting it would be a false positive that a strict export gate would then block on. The exemption is deliberately narrow, and these are still reported:

- a connector between two element-backed nodes whose relationship is genuinely missing;
- a note connector whose node at the other end has vanished from the view.

Parameters: none.

Returns `data.is_valid`, `data.invalid_connection_ids`, `data.invalid_node_ids`, `data.invalid_connections_count`, and `data.invalid_nodes_count`.

Errors: `ModelNotFoundError`.

Note for existing users: with the pinned pyArchimate 1.12.x, the underlying orphan-connection check actually reports results. Earlier 1.11.x releases could not, so `validate_model` was effectively always valid on that dimension. A model that carries orphan visual connections — typically hand-edited or produced by another tool — may now report `is_valid: false` where it previously reported `true`. The same result feeds `build_quality_report`, `inspect_active_model`, the `pyarchimate://activemodel/validation` resource, and the export quality gate, so such a model can now be blocked by `quality_gate="strict"`. Models built through this server's own tools are unaffected: deleting an element or relationship also removes its view nodes and connections.

#### `validate_semantics`

Run optional semantic checks beyond visual reference validation. The checks include invalid relationship combinations, missing node references, duplicate element names per element type across the model (matching Archi's Validator), elements not included in any view, and orphan service/data elements.

Parameters: none.

Returns `data.is_valid`, `data.issues`, and `data.issues_count`.

Errors: `ModelNotFoundError`.

#### `repair_semantic_issues`

Apply deterministic repairs for invalid relationship combinations reported by `validate_semantics`. Each issue may carry `suggested_repairs` with stable `repair_id` values; pass those IDs, or set `repair_all_deterministic` to apply every unambiguous repair.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `repair_ids` | array of strings or null | no | `null` | Specific repair IDs from `validate_semantics` output. |
| `repair_all_deterministic` | boolean | no | `false` | Apply every deterministic repair candidate in one call. |
| `preserve_relationship_ids` | boolean | no | `true` | Recreate repaired relationships under their original IDs. |
| `rollback_on_error` | boolean | no | `true` | Roll back the whole batch when any repair fails. |
| `update_views` | boolean | no | `true` | Re-point view connections at the repaired relationships. |
| `auto_layout` | boolean | no | `false` | Re-run layout on affected views afterwards. |

Returns `data.applied_count`, `data.applied_repairs`, `data.skipped_count`, and `data.skipped_repairs`.

Errors: `ModelNotFoundError`, `ModelOperationError`.

#### `build_quality_report`

Build a structured quality report combining visual validation, semantic validation, and view-coverage checks. Use before export or as the programmatic equivalent of a pre-flight checklist.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `include_togaf` | boolean | no | `false` | Append the advisory TOGAF readiness findings. |
| `include_quality_assurance_views` | boolean | no | `false` | Include QA/coverage views in coverage counts. |

Returns `data.visual_validation`, `data.semantic_validation`, and `data.coverage` (plus `data.togaf_readiness` when requested).

Errors: `ModelNotFoundError`.

#### `assess_togaf_readiness`

Return advisory TOGAF-oriented readiness findings (stakeholders, motivation coverage, implementation elements, view metadata conventions). Advisory only: the response carries `compliance_claim: false` and never blocks any operation.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `include_quality_assurance_views` | boolean | no | `false` | Include QA/coverage views in the assessment. |
| `include_hard_validation` | boolean | no | `true` | Include visual/semantic validation results in the findings. |

Returns `data.advisory_findings`, `data.advisory_findings_count`, `data.hard_failures`, `data.score`, `data.max_score`, `data.status`, and `data.compliance_claim` (always `false`).

Errors: `ModelNotFoundError`.

#### `list_supported_types`

List the ArchiMate types and Archi folder roots supported by the installed pyArchimate version.

Parameters: none.

Returns `data.element_types_by_category`, `data.relationship_types`, `data.folder_roots`, `data.folder_aliases`, `data.access_types`, `data.influence_strengths`, `data.association_is_directed`, `data.layout_strategies`, `data.layout_engines`, `data.semantic_validation_modes`, `data.quality_gates`, `data.relationship_recommendation_intents`, `data.relationship_rule_metadata`, and `data.summary`. The summary carries `element_type_count`, `relationship_type_count`, `supports_views`, and a `source` string naming the pyArchimate version the catalogue was derived from.

The catalogue exposed by the MCP with the currently pinned pyArchimate 1.12.x contains 63 element types and 11 relationship types. It covers ArchiMate concepts used in Archi's Strategy, Business, Application, Technology, Motivation, Implementation, Other, Relations, and Views model tree folders. Diagram-only Archi annotations are not ArchiMate model concepts and are not in this catalogue: Notes are supported as *visual* view annotations through [`add_note_to_view`](#add_note_to_view) rather than as a type you can pass to `add_element`, and Legends are not supported. Because the catalogue is derived from the installed library rather than hardcoded, call this tool rather than assuming the lists below never change.

#### `summarize_model`, `summarize_view`, `count_by_type`, and `list_orphan_elements`

Use these verification tools after generation:

- `summarize_model` returns model-wide counts and view summaries.
  Errors: `ModelNotFoundError`.
- `summarize_view(view_id)` returns node/connection counts and relationships that can still be connected in that view.
  Errors: `ModelNotFoundError`, `ViewNotFoundError`.
- `count_by_type` returns element and relationship counts by type.
  Errors: `ModelNotFoundError`.
- `list_orphan_elements` returns elements without relationships, elements not placed in any view, and elements that are fully orphaned.
  Errors: `ModelNotFoundError`.

#### `create_model_from_spec`

Create a complete model from one structured JSON object. The operation is transactional by default.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `spec` | object | yes | none | Model specification containing `name`, optional model-level `description` (or `documentation`) and `properties`, optional `elements`, optional `relationships`, and optional `views`. |
| `rollback_on_error` | boolean | no | `true` | Restore the previous active model if the spec fails. |

The model-level `description` and `properties` keys behave exactly as in `create_empty_model`. `documentation` is accepted as an alias for `description`, so the spec can use either the write-side name used by element/relationship/view entries or the read-side name reported by `model_info`.

Example:

```json
{
  "spec": {
    "name": "Small Journey Model",
    "description": "Baseline customer journey.",
    "properties": {"owner": "Enterprise Architecture"},
    "elements": [
      {"id": "id-visit", "name": "Visit Site", "type": "BusinessProcess", "folder_path": "business"},
      {"id": "id-buy", "name": "Purchase", "type": "BusinessProcess", "folder_path": "/Business"}
    ],
    "relationships": [
      {"id": "id-flow", "type": "Flow", "source": "id-visit", "target": "id-buy", "name": "leads to"}
    ],
    "views": [
      {
        "id": "id-main-view",
        "name": "Journey",
        "nodes": [{"element": "id-visit"}, {"element": "id-buy"}],
        "connect_visible_relationships": true,
        "auto_layout": true,
        "layout_strategy": "layered",
        "layout_engine": "internal"
      }
    ]
  }
}
```

Errors: `INVALID_SPEC`, `InvalidElementTypeError`, `InvalidRelationshipTypeError`, `ElementNotFoundError`, `ModelOperationError`.

### Element Tools

#### `add_element`

Add a new ArchiMate element to the active model.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `element_type` | string | yes | none | A supported ArchiMate element type, such as `BusinessActor` or `ApplicationComponent`. |
| `name` | string | yes | none | Element name. Must not be blank. |
| `description` | string or null | no | `null` | Element documentation text. |
| `folder_path` | string or null | no | `null` | Conceptual folder path, such as `/Business/Actors`. Folder roots are normalized, so `Business`, `/Business`, and `business` are accepted. |
| `properties` | object or null | no | `null` | Custom property key-value pairs. Values are stored as strings. |
| `element_id` | string or null | no | `null` | Optional stable element ID. |

Example:

```json
{
  "element_type": "BusinessActor",
  "name": "Customer",
  "description": "External customer using the portal",
  "folder_path": "/Business",
  "properties": {
    "owner": "Enterprise Architecture",
    "status": "approved"
  }
}
```

Returns the created element detail.

Errors: `INVALID_ELEMENT_NAME`, `InvalidElementTypeError`, `ModelNotFoundError`, `ModelOperationError`.

#### `add_elements`

Add multiple elements in one call. By default, if any item fails, the whole batch is rolled back.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `elements` | array | yes | none | Element objects using the same fields as `add_element`. `type` may be used instead of `element_type`. |
| `rollback_on_error` | boolean | no | `true` | Restore the previous model state if any element fails. |

Example:

```json
{
  "elements": [
    {"id": "id-customer", "name": "Customer", "type": "BusinessActor", "folder_path": "business"},
    {"id": "id-portal", "name": "Portal", "type": "ApplicationComponent", "folder_path": "/Application"}
  ]
}
```

Errors: `ModelNotFoundError`, `InvalidElementTypeError`, `ModelOperationError`.

#### `update_element`

Update an existing element.

Parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `element_id` | string | yes | ID of the element to update. |
| `updates` | object | yes | Fields to update. Supports `name`, `description`, `folder_path`, and `properties`. |

Example:

```json
{
  "element_id": "element-id",
  "updates": {
    "name": "Retail Customer",
    "description": "Updated description",
    "properties": {
      "reviewed": "true"
    }
  }
}
```

Property updates are merged into existing properties.

Errors: `ElementNotFoundError`, `ModelOperationError`.

#### `delete_element`

Delete an element from the active model.

Parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `element_id` | string | yes | ID of the element to delete. |

Example:

```json
{
  "element_id": "element-id"
}
```

Dependent concepts managed by `pyArchimate` may also be removed.

Errors: `ElementNotFoundError`.

### Relationship Tools

#### `add_relationship`

Add a relationship between two elements in the active model.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `relationship_type` | string | yes | none | A supported pyArchimate relationship type, such as `Assignment`, `Serving`, or `Influence`. |
| `source_id` | string | yes | none | Source element ID. |
| `target_id` | string | yes | none | Target element ID. |
| `name` | string or null | no | `null` | Relationship name. |
| `description` | string or null | no | `null` | Relationship documentation text. |
| `properties` | object or null | no | `null` | Custom property key-value pairs. Values are stored as strings. |
| `access_type` | string or null | no | `null` | Access relationship modifier. One of `Access`, `Read`, `Write`, or `ReadWrite`. |
| `influence_strength` | string or null | no | `null` | Influence relationship strength. One of `+`, `++`, `+++`, `-`, `--`, `---`, or `0` through `10`. |
| `relationship_id` | string or null | no | `null` | Optional stable relationship ID. |
| `semantic_validation` | string | no | `warn` | One of `off`, `warn`, or `strict`. Checks the source/target/type combination against the ArchiMate relationship matrix. `warn` (default) creates the relationship but returns `data.semantic_warning` with valid alternatives; `strict` rejects invalid combinations with `InvalidRelationshipCombinationError`. |

Example:

```json
{
  "relationship_type": "Assignment",
  "source_id": "business-actor-id",
  "target_id": "business-role-id",
  "name": "plays",
  "description": "Actor plays this role",
  "properties": {
    "criticality": "high"
  }
}
```

Returns the created relationship detail.

Errors: `InvalidRelationshipTypeError` (message includes did-you-mean suggestions), `InvalidRelationshipCombinationError` (strict mode), `ElementNotFoundError`, `ModelNotFoundError`, `ModelOperationError`.

#### `add_relationships`

Accepts the same `semantic_validation` mode as `add_relationship`, applied to every entry in the batch.

Add multiple relationships in one call. By default, if any item fails, the whole batch is rolled back.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `relationships` | array | yes | none | Relationship objects using the same fields as `add_relationship`. `type`, `source`, and `target` may be used as aliases. |
| `rollback_on_error` | boolean | no | `true` | Restore the previous model state if any relationship fails. |

Errors: `InvalidRelationshipTypeError`, `ElementNotFoundError`, `ModelNotFoundError`, `ModelOperationError`.

#### `update_relationship`

Update an existing relationship.

Parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `relationship_id` | string | yes | ID of the relationship to update. |
| `updates` | object | yes | Fields to update. Supports `name`, `description`, `properties`, `access_type`, and `influence_strength`. |

Example:

```json
{
  "relationship_id": "relationship-id",
  "updates": {
    "name": "assigned to",
    "properties": {
      "reviewed": "true"
    }
  }
}
```

Property updates are merged into existing properties.

Errors: `RelationshipNotFoundError`, `ModelOperationError`.

#### `delete_relationship`

Delete a relationship from the active model.

Parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `relationship_id` | string | yes | ID of the relationship to delete. |

Example:

```json
{
  "relationship_id": "relationship-id"
}
```

Visual connections managed by `pyArchimate` may also be removed.

Errors: `RelationshipNotFoundError`.

#### `get_relationship_compatibility`

Return the valid ArchiMate relationship types for a source/target element type pair, with required attributes per option.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `source_type` | string | yes | none | Source element type, such as `ApplicationService`. |
| `target_type` | string | yes | none | Target element type, such as `BusinessProcess`. |

Returns `data.valid_relationships` (each with `relationship_type` and required attributes) plus rule-source metadata (`archimate_version`, `backend`, `rule_source`, `supported_intents`).

Errors: `InvalidElementTypeError` (message includes did-you-mean suggestions).

#### `recommend_relationship`

Recommend relationship options between two elements (by ID) or two element types, optionally guided by an intent keyword such as `serves`, `reads_data`, `writes_data`, `realizes`, `assigned_to`, `flows_to`, `influences`, or `associated_with`. Call this before `add_relationship` when translating generated architectural intent into exact ArchiMate types.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `source_id` | string or null | no | `null` | Source element ID (preferred over `source_type`). |
| `target_id` | string or null | no | `null` | Target element ID. |
| `source_type` | string or null | no | `null` | Source element type when no ID exists yet. |
| `target_type` | string or null | no | `null` | Target element type when no ID exists yet. |
| `intent` | string or null | no | `null` | Optional intent keyword narrowing the recommendation. |

Returns `data.recommendations` ordered best-first (each with `relationship_type`, direction, and reason), `data.requires_judgment`, and rule-source metadata.

Errors: `ElementNotFoundError`, `InvalidElementTypeError`, `ModelOperationError` (unknown intent).

### View Tools

#### `create_view`

Create a new view in the active model.

Parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | View name. Must not be blank. |
| `viewpoint` | string or null | no | Viewpoint for the view: any canonical Archi viewpoint id (`layered`, `application_cooperation`, `capability`, ...) or pyArchimate slug. Invalid values return both accepted catalogs in `error.details`. |
| `view_id` | string or null | no | Optional stable view ID. |
| `folder_path` | string or null | no | Optional view folder path. `Views`, `/Views`, and `views` are accepted. |

Example:

```json
{
  "name": "Customer Portal Context"
}
```

Returns the created view detail.

Errors: `INVALID_VIEW_NAME`, `ModelNotFoundError`, `ModelOperationError`.

#### `update_view`

Update an existing view.

Parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `view_id` | string | yes | ID of the view to update. |
| `updates` | object | yes | Fields to update. Supports `name`, `description`, and `properties`. |
| `viewpoint` | string or null | no | Optional viewpoint (canonical Archi viewpoint id or pyArchimate slug); merged into the view's `viewpoint` property with validation. |

Example:

```json
{
  "view_id": "view-id",
  "updates": {
    "name": "Customer Portal Current State"
  }
}
```

Errors: `ViewNotFoundError`.

#### `delete_view`

Delete a view from the active model.

Parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `view_id` | string | yes | ID of the view to delete. |

Example:

```json
{
  "view_id": "view-id"
}
```

Errors: `ViewNotFoundError`.

#### `add_node_to_view`

Add an element as a visual node in a view.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `view_id` | string | yes | none | ID of the target view. |
| `element_id` | string | yes | none | ID of the element to show in the view. |
| `x` | integer or null | no | `null` | Preferred X coordinate. |
| `y` | integer or null | no | `null` | Preferred Y coordinate. |
| `width` | integer | no | `160` | Node width. |
| `height` | integer | no | `80` | Node height. |
| `node_id` | string or null | no | `null` | Optional stable visual node ID. |

Example:

```json
{
  "view_id": "view-id",
  "element_id": "element-id",
  "x": 40,
  "y": 40,
  "width": 180,
  "height": 90
}
```

If coordinates are omitted or would overlap an existing node, the server picks the next available slot.

Errors: `ViewNotFoundError`, `ElementNotFoundError`, `ModelOperationError`.

#### `add_nodes_to_view`

Add multiple nodes to a view. By default, if any node fails, the whole batch is rolled back.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `view_id` | string | yes | none | ID of the target view. |
| `nodes` | array | yes | none | Node objects using the same fields as `add_node_to_view`. `element` may be used instead of `element_id`. |
| `rollback_on_error` | boolean | no | `true` | Restore the previous model state if any node fails. |

Errors: `ModelOperationError`, `ElementNotFoundError`.

#### `add_note_to_view`

Add a diagram-only note — Archi's sticky Note — to a view, optionally with connector lines pointing at nodes already in that view.

Use this to comment on a diagram: a caveat, an owner, a "retire in FY27". Do **not** create a `Grouping` element just to write a comment. A note is purely visual: it has no ArchiMate element, no folder, and no model-tree entry, so it never appears in `query_elements`, `count_by_type`, `list_orphan_elements`, or the coverage section of `build_quality_report`. The connector lines are annotation-only and create no ArchiMate relationship.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `view_id` | string | yes | none | ID of the target view. |
| `text` | string | yes | none | Note text. Must not be blank. Kept verbatim, so multi-line text keeps its line breaks and indentation. |
| `x` | integer | yes | none | X coordinate of the top-left corner, in pixels. Used exactly. |
| `y` | integer | yes | none | Y coordinate of the top-left corner, in pixels. Used exactly. |
| `width` | integer | no | `185` | Note width in pixels (Archi's default note width). |
| `height` | integer | no | `80` | Note height in pixels. |
| `connect_to_node_ids` | array of strings or null | no | `null` | Things to point at. Each entry may be a visual node ID or the ID of an element that is already visible in this view. |
| `note_id` | string or null | no | `null` | Optional stable visual node ID. A UUID is generated when omitted. |

Example:

```json
{
  "view_id": "view-id",
  "text": "Legacy platform: retire in FY27",
  "x": 600,
  "y": 40,
  "connect_to_node_ids": ["element-id-or-node-id"]
}
```

Returns `data.node_id`, `data.connection_ids`, `data.connected_node_ids` (the resolved *visual node* IDs, in the order given), `data.text`, and the geometry `data.x`, `data.y`, `data.width`, `data.height`.

Unlike `add_node_to_view`, `x` and `y` are used exactly as supplied — there is no next-free-slot fallback and no overlap check, because a note annotates one specific spot. For the same reason `auto_layout_view` never repositions a note under either layout engine: it moves the element nodes around the note and leaves the note where you put it. Place notes in free space (to the side of the diagram, or below it), since layout will not move element nodes out from under one. Routed connections are drawn around notes, exactly as they are around element nodes.

The one nuance is a note nested inside a group, which only ever arrives by importing an Archi file where someone dropped a Note into a Group — `add_note_to_view` always creates a top-level note. Such a note is pinned to its group rather than to the canvas: layout keeps its offset within the group, so it travels with the group instead of being left behind where Archi would clip it out of sight.

Errors: `INVALID_NOTE_TEXT` (missing or blank `text`), `ViewNotFoundError`, `ModelOperationError` (duplicate `note_id`, or a connect target that is not visible in the view). Connect targets are all resolved before anything is created, so a rejected call leaves no half-built note behind; the unresolved IDs come back in `error.details.unknown_ids`.

Notes cannot be updated or deleted yet. To change the text or the placement, rebuild the view.

Reading a note back: it appears in the view detail as a node with `element_id: null` and its text in `note_text` (see [View Shape](#view-shape)), and its text is rendered by `render_view_to_svg_file`. `summarize_view` counts a note in `nodes_count` and its connector lines in `connections_count`, both under the `Unknown` bucket of the per-type counts, because neither carries an ArchiMate type.

#### `add_connection_to_view`

Add a visual connection for an existing relationship in a view.

Parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `view_id` | string | yes | ID of the target view. |
| `relationship_id` | string | yes | ID of the relationship to show. |
| `connection_id` | string or null | no | Optional stable visual connection ID. |

Example:

```json
{
  "view_id": "view-id",
  "relationship_id": "relationship-id"
}
```

Both the relationship source element and target element must already be present as nodes in the view.

Errors: `ModelOperationError`, `RelationshipNotFoundError`.

#### `add_connections_to_view`

Add multiple relationship connections to a view. By default, if any connection fails, the whole batch is rolled back.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `view_id` | string | yes | none | ID of the target view. |
| `connections` | array | yes | none | Connection objects using the same fields as `add_connection_to_view`. `relationship` may be used instead of `relationship_id`. |
| `rollback_on_error` | boolean | no | `true` | Restore the previous model state if any connection fails. |

Errors: `ModelOperationError`, `RelationshipNotFoundError`.

#### `connect_visible_relationships`

Add every relationship whose source and target elements are both already visible as nodes in a view. Existing connections are skipped.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `view_id` | string | yes | none | ID of the target view. |
| `rollback_on_error` | boolean | no | `true` | Restore the previous model state if connection creation fails. |

Errors: `ModelOperationError`.

#### `ensure_all_relationships_in_views`

Ensure every model relationship is rendered in at least one view. The tool creates or reuses a coverage view and adds missing endpoint node pairs before adding otherwise-unplaced connections. It also relocates redundant Grouping-to-contained-child Aggregation/Composition connections out of readable views and into the coverage view. This preserves Archi Validator coverage while letting visual containment carry the meaning in the readable view. This is useful when Archi's Validator reports warnings such as `Unused Relation` or `'Serving relation' is not used in a View`.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `coverage_view_name` | string | no | `Relationship Coverage` | Name of the view used for otherwise unplaced relationships. |
| `auto_layout` | boolean | no | `true` | Lay out affected views after adding missing nodes and connections. |
| `layout_strategy` | string | no | `layered_by_type` | Validated for consistency with the other layout tools, but not applied: the coverage view layout is a fixed source/target pair grid. |
| `layout_engine` | string | no | `internal` | Must be `internal`. The coverage layout is a fixed pair grid, so no other engine can be honoured here — passing one is an error rather than a silently ignored hint. |
| `rollback_on_error` | boolean | no | `true` | Restore the previous model state if coverage creation fails. |

Returns counts for added nodes, added connections, relocated containment connections, skipped relationships, and remaining unused relationships. Coverage views created or reused by the tool are marked with the `mcp:relationship_coverage_view=true` property.

A view is recognized as the generated coverage view by that marker property, or by an exact match against the `coverage_view_name` you passed on this call — never by its name merely containing the word `coverage`. Your own "Data Coverage Analysis" view is laid out, banded, and validated exactly like any other authored view. The marker survives a native `archi` round trip; the Open Group exchange format (`archimate`) does not preserve view properties at all, so after an exchange reload pass the same `coverage_view_name` to have the view re-adopted and re-marked.

Notes in a coverage view are left where they are, and a note connector never consumes a pair row — only real relationships do.

Errors: `ModelNotFoundError`, `ModelOperationError`.

#### `auto_layout_view`

With the default `layered_by_type` strategy, views spanning two or more ArchiMate layers get labeled visual layer bands (diagram-only Archi Groups such as "Business", "Application", "Technology & Physical"). Bands never modify the semantic model and are replaced, not stacked, on repeated layouts. Pass `layer_bands=false` to disable. Wide lanes wrap into multiple rows (max ~1,600px) and connected nodes align vertically across lanes.

Reposition all existing nodes in a view using a non-overlapping layout. The layout also nests Aggregation/Composition members inside visible Grouping nodes, creates missing group member nodes when a group is visible, estimates relationship label bounds, increases spacing for long labels, and adds bendpoints to reduce label overlap with nodes and other labels.

Where several routed connections end up running along the same horizontal or vertical corridor, the layout separates them by ~10px so they read as distinct lines instead of one heavy band. The separation never moves a line onto a node it was routed around, and never takes a connection off its node's centerline, so routes stay orthogonal and keep their clearance.

Diagram notes ([`add_note_to_view`](#add_note_to_view)) are annotations of one specific spot, so both engines treat them as fixed: layout places the element nodes around them and leaves note coordinates alone, and never wraps a note in a layer band. A note nested inside a group keeps its offset within that group, so it travels with the group. Routing does treat a note as an obstacle — a line is drawn around a note rather than through it — because a route crossing a note is as unreadable as one crossing an element. Since layout will not move element nodes out from under a note, place notes in free space.

For dense diagrams, the layout intentionally simplifies relationship routing instead of adding many detour bendpoints. This avoids unreadable horizontal line bands in Archi. Dense views keep labels on primary flow relationships, keep Influence labels in dense motivation/strategy views, hide secondary labels, and draw secondary relationships in light gray when no custom line color is set. Semantic lane layout also aligns business/application data under the behavior or service that reads or writes it when visible `Access` relationships provide that context. Group containment moves members inside the group for generated layouts. In meaningful authored layouts, the original top-level member node is preserved and a contained duplicate is added inside the group panel. Group containment relationships in a readable view are label-hidden and light gray when the member is visually nested inside the group; `ensure_all_relationships_in_views` can then relocate those redundant containment connectors to coverage. Junction elements are normalized to compact visual symbols before layout. The detailed layout roadmap and implementation context are documented in [LAYOUT_IMPROVEMENT_PLAN.md](LAYOUT_IMPROVEMENT_PLAN.md).

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `view_id` | string | yes | none | ID of the view to lay out. |
| `strategy` | string | no | `layered_by_type` | One of `layered_by_type`, `layered`, or `grid`. Validated but **not applied** when `layout_engine` is `pyarchimate`. |
| `layout_engine` | string | no | `internal` | Node placement engine for this one call. One of `internal` or `pyarchimate` — see [Layout engines](#layout-engines). Unknown names fail with `error.details.suggestions`. |
| `layer_bands` | boolean | no | `true` | With `layered_by_type` and two or more ArchiMate layers, wrap each layer in a labeled visual band (diagram-only Archi Group). Set `false` to disable. Never applied when `layout_engine` is `pyarchimate`. |

Example:

```json
{
  "view_id": "view-id",
  "strategy": "layered",
  "layout_engine": "internal"
}
```

Layout strategies:

- `layered_by_type`: Places nodes in ArchiMate-specific horizontal lanes. Business concepts are placed above application concepts, application data is placed below behavior/services, and technology, physical, and implementation concepts are placed below that. This is the default.
- `layered`: Uses relationship direction so source nodes appear before target nodes when possible.
- `grid`: Places nodes in a compact grid.

Returns the updated view detail. Under `layout_engine="pyarchimate"` the success message names what was not applied.

Errors: `ViewNotFoundError`, `ModelOperationError`.

##### Layout engines

**Which should you use? `internal`, unless you have a specific reason not to.** Beyond the mechanical differences tabulated below, a human reviewed rendered output from both engines side by side on 2026-07-26 and judged `internal` to produce the better diagrams. That is a visual-quality judgment, not something the measurements below capture — read the performance and compactness numbers as characteristics of each engine, not as an argument for switching. `pyarchimate` is supported as a deliberate alternative for callers who want upstream's placement; it is not a recommended default and is not a drop-in improvement.

`layout_engine` selects the **node placement** algorithm for that one call. It is not a model setting and not a session default: it is never stored on the model or the view, never serialized, and therefore never appears in an `archi` or `archimate` export or in Archi's Properties tab. Two calls on the same view with different engines are independent, and the second fully overwrites the first.

Connection routing is **not** part of the choice. The MCP's own routing — obstacle-map A* with clearance-aware anchors, dogleg fallback, dense-view straight-line simplification — runs after placement under both engines.

- **`internal`** (default): the MCP's deterministic ArchiMate-aware layout. Requires no external tools. Everything described above applies.
- **`pyarchimate`**: pyArchimate's own coarse-grid placement — one fixed algorithm, deliberately much simpler. It places nodes on a fixed grid and does nothing else.

Both engines are deterministic and idempotent: laying the same view out twice with the same engine reproduces the same coordinates, so the comparison workflow below is stable.

The following also run for **both** engines, because they are correctness and repair rather than placement style: Grouping-member nesting and legacy-duplicate healing, the compact junction size clamp, sizing Groupings to their members, the dense-view relationship label policy, and the group-containment connection policy.

What `pyarchimate` gives up:

| Feature | `internal` | `pyarchimate` |
| --- | --- | --- |
| `strategy` (`layered_by_type` / `layered` / `grid`) | applied | validated, **not applied** (one fixed algorithm) |
| `layer_bands` | applied | **never applied** |
| ArchiMate semantic lane order | applied | **lost** — see the misclassified types below |
| Lane wrapping at 1,600px | applied | **lost** (upstream has a fixed 8-column cap) |
| Barycenter alignment of connected nodes | applied | **lost** (insertion order, no connectivity awareness) |
| Label-aware gap widening | applied | **lost** — connection labels can collide with nodes |
| Data-node alignment to `Access` sources | applied | **lost** |
| Connection routing | applied | **applied** (identical) |
| Grouping nesting + duplicate healing | applied | **applied** (identical) |
| Compactness (43 nodes, no Grouping) | 3.24 Mpx canvas, 17.0% ink | 3.76 Mpx canvas, 14.6% ink |

Upstream's layer classifier is naive substring matching and puts nine of the 63 supported element types in the wrong band: `SystemSoftware`, `Artifact`, `Path`, `Equipment`, `Facility` and `Material` fall into a catch-all bucket instead of Technology; `Contract` and `Representation` instead of Business; and `ImplementationEvent` is treated as Business. It also collapses Motivation, Strategy, Implementation, Physical, Grouping and Junction into a single bucket — four bands total, not one per layer.

**The suitability guard.** Upstream places nodes on a fixed grid without ever reading their width or height, so it has no collision detection: it is overlap-free only while every node fits inside one grid cell (240 px today). A node one pixel over that budget produces overlapping rectangles, and upstream still reports success with no warnings. Because an agent caller cannot see the diagram, the server checks first and **refuses** rather than returning a corrupt view as a success. The check uses each top-level node's full subtree bounding box.

*What a refusal leaves behind.* The guard runs before any **placement** is written, so the view is never left half laid out — no node is ever moved to a grid position and then abandoned. It does **not** run before the shared prologue. On a view that needs repair, the prologue has already nested Grouping members and grown the Grouping to fit them, and those are real coordinate changes that survive the refusal. Measured: on a flat view the refusal changes nothing at all; on a view with a Grouping whose three members were still loose, the refusal left the members nested and the Grouping resized from 160x80 to 720x180. The prologue is idempotent, so an immediately repeated call changes nothing further. If you need the view untouched, do not call `auto_layout_view` at all.

**Performance — measure before you choose it.** The placement step itself is a few times faster (0.073 ms vs 0.264 ms on a 43-node view), but a call to `auto_layout_view` is dominated by the shared routing epilogue, which runs under both engines. The end-to-end result therefore depends on how much work the resulting geometry gives the router, and it can go either way:

| View (chain of Associations, no Grouping) | `internal` | `pyarchimate` |
| --- | --- | --- |
| 43 nodes / 42 connections — below the dense gate, so routing really runs | 50.7 ms | 157.9 ms (**3.1x slower**) |
| 120 nodes / 119 connections — past the dense gate | 2.3 ms | 0.8 ms (3.0x faster) |
| 200 nodes / 199 connections — past the dense gate | 5.3 ms | 1.3 ms (4.2x faster) |

Below the dense-routing threshold, `pyarchimate`'s airier placement gives the router *more* work, not less (30 of 42 connections routed instead of 25, over longer corridors), so the call gets slower overall. Past the threshold bendpoints are stripped, routing is nearly free, and the placement difference finally shows through. Treat speed as a property of your view, not of the engine.

Use `pyarchimate` for: flat views whose nodes all fit a 240x240 cell (the default 160x80 node size qualifies), with no Groupings and no need for layer bands; very large generated views past the dense-routing threshold, where the placement cost dominates; and as a fast second-opinion placement to eyeball with `render_view_to_svg_file`. For anything with a Grouping, anything wanting ArchiMate lanes or bands, and anything with wide nodes, `internal` is better — and on a mid-density view it is also faster.

The former optional `graphviz` engine was removed in an earlier release and is not coming back; requesting it returns an error naming the supported engines.

##### Worked examples

**1. Default call — unchanged behaviour.** Omitting `layout_engine` is identical to passing `"internal"`, down to the coordinates.

```json
{ "view_id": "id-94e76f8f8c6546d58d992f4f08abd784" }
```

```json
{
  "status": "success",
  "message": "View layout updated.",
  "data": {
    "id": "id-94e76f8f8c6546d58d992f4f08abd784",
    "name": "Payment Overview",
    "nodes": [
      { "id": "id-a582aaa4dc93", "element_id": null, "element_type": null,
        "parent_node_id": null, "x": 16, "y": 4, "width": 208, "height": 276 },
      { "id": "id-8350052305dc", "element_name": "Customer",
        "element_type": "BusinessActor", "parent_node_id": "id-a582aaa4dc93",
        "x": 40, "y": 40, "width": 160, "height": 80 }
    ]
  }
}
```

Nodes with `element_id: null` are diagram-only: here, the layer bands, with real elements nested inside them through `parent_node_id`. A diagram note is element-less too, and is told apart by its `note_text`.

**2. Explicit `pyarchimate` on a suitable view.** Same three elements, no Grouping, all nodes 160x80.

```json
{
  "view_id": "id-55a49bf4b9a94f8bbb82f027f698626f",
  "layout_engine": "pyarchimate"
}
```

```json
{
  "status": "success",
  "message": "View layout updated (engine: pyarchimate; strategy and layer bands not applied by this engine).",
  "data": {
    "name": "Payment Overview",
    "nodes": [
      { "element_name": "Customer", "element_type": "BusinessActor",
        "parent_node_id": null, "x": 20, "y": 20, "width": 160, "height": 80 },
      { "element_name": "Handle Payment", "element_type": "BusinessProcess",
        "parent_node_id": null, "x": 260, "y": 20, "width": 160, "height": 80 },
      { "element_name": "Payment Engine", "element_type": "ApplicationComponent",
        "parent_node_id": null, "x": 20, "y": 500, "width": 160, "height": 80 }
    ]
  }
}
```

No band nodes, nothing nested, and coordinates snapped to the 240 px grid — the row pitch is 240 for an 80 px node, so the diagram is airier than `internal`. Connections are still routed by the MCP.

**3. The guard — a valid engine on an unsuitable view.** Two things commonly trip it: a node added with an explicit oversize, and a `Grouping` that the layout has grown to hold its members.

The simplest reproduction is a single wide node. Add one with `add_node_to_view(view_id, element_id, width=300, height=90)`, then:

```json
{
  "view_id": "id-7c2f4a1e88b04d0e9a3c5f61d2e07b44",
  "layout_engine": "pyarchimate"
}
```

```json
{
  "status": "error",
  "message": "Layout engine 'pyarchimate' cannot lay out view 'Payments Domain': 1 node(s) exceed the upstream 240px grid cell. The upstream engine has no collision detection and would overlap them. Use layout_engine=\"internal\" (the default) for this view.",
  "error": {
    "code": "ModelOperationError",
    "details": {
      "grid_size": 240,
      "oversized_nodes": [
        { "node_id": "id-667bc25df45a46a3b2ef63c51cd5defe",
          "element_id": "id-557ad8b999e9498c8097c319e02cf418",
          "element_name": "Customer Relationship Mgmt",
          "width": 300.0, "height": 90.0 }
      ],
      "remedy": "internal"
    }
  }
}
```

A `Grouping` trips it without anyone asking for an odd size. A Grouping with three `Composition` members is grown to 720x180 by the shared prologue, which is already three cells wide:

```json
{
  "status": "error",
  "message": "Layout engine 'pyarchimate' cannot lay out view 'Payments Domain': 2 node(s) exceed the upstream 240px grid cell. The upstream engine has no collision detection and would overlap them. Use layout_engine=\"internal\" (the default) for this view.",
  "error": {
    "code": "ModelOperationError",
    "details": {
      "grid_size": 240,
      "oversized_nodes": [
        { "node_id": "id-b1ab5bbf63db4f2586ce6d2c42c2879e",
          "element_id": "id-f2f7e173deb54d2c8f03de3227beee85",
          "element_name": "Payments Domain", "width": 720.0, "height": 180.0 },
        { "node_id": "id-1fc9a839075247449224d10b0a6b783e",
          "element_id": "id-124cd581a4684b94a256d1370f2e1a1a",
          "element_name": "Customer Relationship Mgmt",
          "width": 300.0, "height": 90.0 }
      ],
      "remedy": "internal"
    }
  }
}
```

The exact width scales with the member count, so expect a different number, not these literal pixels. In practice **a view with any non-trivial Grouping is refused**, which is the honest summary of when this engine is usable at all. Retry the same call with `"layout_engine": "internal"` and it lays out normally — no placement was written, though see *What a refusal leaves behind* above for what the prologue may already have repaired.

**4. An invalid engine name — did-you-mean suggestions.**

```json
{ "view_id": "id-94e76f8f8c6546d58d992f4f08abd784", "layout_engine": "pyarchmate" }
```

```json
{
  "status": "error",
  "message": "Unsupported layout engine: pyarchmate. Supported engines: internal, pyarchimate. Did you mean: pyarchimate? Call list_supported_types for the full catalog.",
  "error": {
    "code": "ModelOperationError",
    "details": { "suggestions": ["pyarchimate"] }
  }
}
```

When nothing is close enough, `details.suggestions` is still present as an empty list and the message carries the full catalogue:

```json
{
  "status": "error",
  "message": "Unsupported layout engine: graphviz. Supported engines: internal, pyarchimate. Call list_supported_types for the full catalog.",
  "error": { "code": "ModelOperationError", "details": { "suggestions": [] } }
}
```

`layout_strategy` behaves the same way. Engine names are case-insensitive, so `"PyArchimate"` is accepted.

**5. Export — the engine applies to every view.**

```json
{
  "path": "/Users/me/models/payments.archimate",
  "output_format": "archi",
  "auto_layout": true,
  "layout_strategy": "layered_by_type",
  "layout_engine": "pyarchimate"
}
```

The guard applies per view, so one unsuitable view fails the whole export. With `auto_layout` omitted or false the engine is still validated (an invalid name errors) but not applied, and `data.layout_engine` comes back `null` because no layout ran.

**6. Per-view engine in `create_model_from_spec`.**

```json
{
  "spec": {
    "name": "Payments Platform",
    "elements": [
      { "ref": "cust", "name": "Customer", "type": "BusinessActor" },
      { "ref": "proc", "name": "Handle Payment", "type": "BusinessProcess" },
      { "ref": "app", "name": "Payment Engine", "type": "ApplicationComponent" }
    ],
    "relationships": [
      { "ref": "r1", "type": "Triggering", "source": "cust", "target": "proc" }
    ],
    "views": [
      { "ref": "overview", "name": "Payment Overview",
        "nodes": [{ "element": "cust" }, { "element": "proc" }, { "element": "app" }],
        "connect_visible_relationships": true,
        "auto_layout": true, "layout_strategy": "layered_by_type",
        "layout_engine": "internal" },
      { "ref": "scratch", "name": "Generated Scratch View",
        "nodes": [{ "element": "cust" }, { "element": "proc" }, { "element": "app" }],
        "connect_visible_relationships": true,
        "auto_layout": true, "layout_engine": "pyarchimate" }
    ]
  }
}
```

Both views hold the same three elements and come out placed differently in one call: `Payment Overview` gets layer bands and lane placement (`Customer` at 40,40 inside a band at 16,4), while `Generated Scratch View` gets the bare grid (`Customer` at 20,20, no bands). The per-view key is only read when that view sets `auto_layout: true`. Note the node key is `nodes` with `element` refs — a view spec without `nodes` is legal and creates an *empty* view, which then has nothing to lay out.

**7. Comparing the two engines.** Lay the view out with one engine, render it, lay it out with the other, render again, then look at both files:

```json
{ "view_id": "id-55a49bf4", "layout_engine": "pyarchimate" }
```
```json
{ "view_id": "id-55a49bf4", "path": "/Users/me/Desktop/pyarchimate.svg" }
```

Layout is deterministic and idempotent under both engines, so the comparison is stable and repeatable.

#### `render_view_to_svg_file`

Render one view to an SVG file so a **human** can look at the diagram without installing Archi. The rendering reproduces the layout the server already produced: labeled layer bands, wrapped lanes, per-type arrowheads, relationship labels (including `Influence (++)`), and the routed bendpoints — whichever layout engine placed the nodes.

SVG is a **rendering, not a model format**:

- It **cannot be imported back into Archi**. It is a picture of one view, not a model.
- It is **not one of the two model export formats**. `archi` (Archi native `.archimate`) and `archimate` (Open Group exchange XML) remain the only ways to persist a model — see [Supported Model Formats](#supported-model-formats). `export_model_content` and `export_model_to_file` reject `"svg"` with `UnsupportedFormatError`.
- The **markup is never returned inline**. Only the file path and small metadata come back. An 11-element view is already about 3.2k tokens of SVG text and a 120-element view about 32k, and an agent cannot see an image. Hand the path to the user.

Rendering is read-only with respect to the model: it never runs a layout pass and never moves a node. Call `auto_layout_view` first when the geometry needs work.

Parameters:

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `view_id` | string | yes | none | ID of the view to render. |
| `path` | string | yes | none | Output path on the server's filesystem, conventionally ending in `.svg`. `~` is expanded, relative paths resolve against the server's working directory, and missing parent directories are created. |

Example:

```json
{
  "view_id": "view-id",
  "path": "~/diagrams/overview.svg"
}
```

Response `data`:

| Field | Type | Description |
| --- | --- | --- |
| `path` | string | Absolute path of the written SVG file. |
| `view_id` | string | ID of the rendered view. |
| `view_name` | string | Name of the rendered view. |
| `model_name` | string | Name of the active model. |
| `bytes_written` | integer | Size of the written file in bytes. |
| `node_count` | integer | Visual nodes rendered, including nodes nested inside groups and layer bands. |
| `connection_count` | integer | Visual connections in the view. |
| `width` | integer | Rendered canvas width in pixels. |
| `height` | integer | Rendered canvas height in pixels. |

Errors: `ModelNotFoundError`, `ViewNotFoundError`, `ModelOperationError` (blank path or write failure).

### Query Tools

#### `query_elements`

Query elements in the active model.

Parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `filter_criteria` | object | yes | Supported filters are `type`, `name_contains`, and `properties_contain`. |

Example:

```json
{
  "filter_criteria": {
    "type": "BusinessActor",
    "name_contains": "customer",
    "properties_contain": {
      "owner": "EA"
    }
  }
}
```

Filter behavior:

- `type`: exact element type match.
- `name_contains`: case-insensitive substring match against the element name.
- `properties_contain`: all specified key-value pairs must match. Values are compared as strings.

Returns `data.elements`.

Errors: `ModelNotFoundError`.

#### `query_relationships`

Query relationships in the active model.

Parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `filter_criteria` | object | yes | Supported filters are `type`, `source_id`, and `target_id`. |

Example:

```json
{
  "filter_criteria": {
    "type": "Assignment",
    "source_id": "source-element-id"
  }
}
```

Filter behavior:

- `type`: exact relationship type match.
- `source_id`: exact source element ID match.
- `target_id`: exact target element ID match.

Returns `data.relationships`.

Errors: `InvalidRelationshipTypeError`, `ModelNotFoundError`.

## Common Workflows

### Create A Small Model

1. Create a model.

```json
{
  "tool": "create_empty_model",
  "arguments": {
    "name": "Customer Portal Architecture"
  }
}
```

2. Add a business actor.

```json
{
  "tool": "add_element",
  "arguments": {
    "element_type": "BusinessActor",
    "name": "Customer"
  }
}
```

3. Add an application component.

```json
{
  "tool": "add_element",
  "arguments": {
    "element_type": "ApplicationComponent",
    "name": "Customer Portal"
  }
}
```

4. Add a serving relationship using the returned element IDs.

```json
{
  "tool": "add_relationship",
  "arguments": {
    "relationship_type": "Serving",
    "source_id": "customer-portal-element-id",
    "target_id": "customer-element-id",
    "name": "serves"
  }
}
```

5. Export to an Archi native file.

```json
{
  "tool": "export_model_to_file",
  "arguments": {
    "path": "/tmp/customer-portal.archimate",
    "output_format": "archi",
    "auto_layout": true,
    "layout_strategy": "layered_by_type",
    "layout_engine": "internal"
  }
}
```

Open `data.path` in Archi.

### Create A View

1. Create a view.

```json
{
  "tool": "create_view",
  "arguments": {
    "name": "Customer Portal Context"
  }
}
```

2. Add nodes for the source and target elements.

```json
{
  "tool": "add_node_to_view",
  "arguments": {
    "view_id": "view-id",
    "element_id": "source-element-id"
  }
}
```

```json
{
  "tool": "add_node_to_view",
  "arguments": {
    "view_id": "view-id",
    "element_id": "target-element-id"
  }
}
```

3. Add the relationship connection.

```json
{
  "tool": "add_connection_to_view",
  "arguments": {
    "view_id": "view-id",
    "relationship_id": "relationship-id"
  }
}
```

4. Lay out the view.

```json
{
  "tool": "auto_layout_view",
  "arguments": {
    "view_id": "view-id",
    "strategy": "layered"
  }
}
```

5. Optionally annotate the finished diagram. Lay out first, then place the note in free space beside the result, because layout will not move element nodes out from under it.

```json
{
  "tool": "add_note_to_view",
  "arguments": {
    "view_id": "view-id",
    "text": "Awaiting sign-off from the Architecture Board",
    "x": 800,
    "y": 40,
    "connect_to_node_ids": ["target-element-id"]
  }
}
```

### Load An Existing Model

Use `load_model_from_file` when the ArchiMate XML is already available on the MCP server filesystem.

```json
{
  "tool": "load_model_from_file",
  "arguments": {
    "path": "/tmp/customer-portal.archimate",
    "content_format": "archi"
  }
}
```

Use `load_model_from_content` only when passing XML content directly as the tool argument.

After loading, inspect:

- `pyarchimate://activemodel/info`
- `pyarchimate://activemodel/elements`
- `pyarchimate://activemodel/relationships`
- `pyarchimate://activemodel/views`

### Ask An LLM Client To Use The Server

In a connected MCP client, natural-language requests can drive tool use. For example:

```text
Create a new ArchiMate model named "Claims Platform". Add a BusinessActor named "Policyholder", an ApplicationComponent named "Claims Portal", and a Serving relationship from the portal to the policyholder. Create a context view, add both elements to it, connect the relationship, lay it out, and export the model in Archi native format.
```

For existing models:

```text
Load this Archi .archimate XML content, summarize the model inventory, list all BusinessActor elements, and export the relationships as CSV.
```

## Supported Model Formats

The server accepts the following format names for import and export:

| Format | Description |
| --- | --- |
| `archimate` | Open Group ArchiMate exchange XML. This is the default. |
| `archi` | Archi native `.archimate` XML. Use this for files opened directly by Archi. |
| `xml` | Generic XML format name accepted by the server. Content must still be ArchiMate-compatible XML that `pyArchimate` can parse. |

SVG is deliberately absent from this table. `render_view_to_svg_file` produces a picture of one view for a human reviewer; it is not a model format, cannot be imported into Archi, and is not accepted by `export_model_content` or `export_model_to_file`.

What survives a round trip through this server:

- Model name, documentation, and properties: both formats.
- Diagram notes: both formats. `archi` writes `<child xsi:type="archimate:Note">` with the text in `<content>`; `archimate` writes `<node xsi:type="Label">` with the text in `<label>`.
- Note connector lines: both formats export them and **both open correctly in Archi**, but only `archimate` survives a round trip back into this server. pyArchimate's native Archi reader skips connections carrying no relationship — which is exactly how a note line is written — so re-loading an exported `.archimate` file keeps the note and loses its connector lines. Export as `archimate` when the note lines have to come back. (Each format needs its own connection type for a view-only line, and the server writes the right one for each: `archimate:DiagramModelConnection` natively, `Line` in the exchange format. Getting this wrong makes Archi refuse to open the view with "Failed to create the part's controls", so do not hand-edit these.)
  - In `archimate` a note line is written as the exchange schema's view-only connection, `<connection xsi:type="Line">`, with no `relationshipRef`. That is the only schema-valid way to express a connection with no backing relationship: the schema makes `relationshipRef` a required `xs:IDREF` on `xsi:type="Relationship"`, so writing a note line as a `Relationship` would leave a reference resolving to nothing and fail validation for the whole file — including in Archi's validating import. This server rebuilds those lines when it loads the file back, so the round trip stays lossless.

Import safeguards:

- Maximum XML content size is 10 MiB.
- DTD declarations are rejected.
- Entity declarations are rejected.
- XML parsing disables external entity resolution and network access.
- The XML root must look like ArchiMate content.

## Supported ArchiMate Types

Element and relationship support follows the installed `pyArchimate` version.

### Element Types

The following element type names are accepted by `add_element`:

```text
AndJunction
ApplicationCollaboration
ApplicationComponent
ApplicationEvent
ApplicationFunction
ApplicationInteraction
ApplicationInterface
ApplicationProcess
ApplicationService
Artifact
Assessment
BusinessActor
BusinessCollaboration
BusinessEvent
BusinessFunction
BusinessInteraction
BusinessInterface
BusinessObject
BusinessProcess
BusinessRole
BusinessService
Capability
CommunicationNetwork
Constraint
Contract
CourseOfAction
DataObject
Deliverable
Device
DistributionNetwork
Driver
Equipment
Facility
Gap
Goal
Grouping
ImplementationEvent
Junction
Location
Material
Meaning
Node
OrJunction
Outcome
Path
Plateau
Principle
Product
Representation
Requirement
Resource
Stakeholder
SystemSoftware
TechnologyCollaboration
TechnologyEvent
TechnologyFunction
TechnologyInteraction
TechnologyInterface
TechnologyProcess
TechnologyService
Value
ValueStream
WorkPackage
```

### Relationship Types

The following relationship type names are accepted by `add_relationship` and `query_relationships`:

```text
Access
Aggregation
Assignment
Association
Composition
Flow
Influence
Realization
Serving
Specialization
Triggering
```

## Troubleshooting

### The MCP Client Shows No Tools

Check that the client command runs from the repository root or uses `uv --directory /absolute/path/to/mcp-archimate`. Then restart the MCP client.

Use the Inspector to confirm the server registers tools:

```bash
uv run mcp dev pyarchimate_mcp_server/server.py
```

### `ModelNotFoundError`

Call `create_empty_model`, `load_model_from_content`, or `load_model_from_file` before using element, relationship, view, export, or query tools.

### `InvalidElementTypeError`

Use one of the supported element type names exactly as listed in [Element Types](#element-types). Type names are case-sensitive.

### `InvalidRelationshipTypeError`

Use one of the supported relationship type names listed in [Relationship Types](#relationship-types). Type names are case-sensitive.

### `UnsupportedFormatError`

Use `archimate`, `archi`, or `xml` as the format name. The content must be valid ArchiMate XML.

### `ModelOperationError` During Import

The XML may be malformed, larger than 10 MiB, include DTD/entity declarations, or use a structure that `pyArchimate` cannot parse.

### Connection Or Startup Problems

Run the server command directly:

```bash
uv --directory /absolute/path/to/mcp-archimate run python -m pyarchimate_mcp_server.server
```

If imports fail, reinstall dependencies:

```bash
uv sync
```

If you are using the console script and it is missing, reinstall the project:

```bash
uv run pip install .
```

### Archi Cannot Open Exported Content

If Archi reports an error such as `Package with uri 'http://www.opengroup.org/xsd/archimate/3.0/' not found` or `Class 'model' is not found or is abstract`, the file is Open Group exchange XML being opened as if it were Archi's native `.archimate` format.

If you want to open the file directly in Archi, use `export_model_to_file` with `output_format="archi"`:

```json
{
  "path": "/tmp/model.archimate",
  "output_format": "archi"
}
```

For `export_model_content`, set `output_format="archi"` and write the returned `data.content` to a `.archimate` file in your client.

Do not switch to Open Group exchange XML just to preserve a generic `Junction`. The native exporter preserves `Junction` in the active model and writes a valid native representation for Archi. Use exchange XML only when you intentionally want the Open Group interchange format.

If Archi reports `Feature 'influenceStrength' not found`, the file was produced by an older native export path that wrote Open Group-style Influence metadata into Archi's native XML. Re-export the model with `output_format="archi"` using the current MCP. The native exporter writes Influence strength as Archi's `strength` attribute while preserving `influence_strength` in the active model and MCP responses.

The default `archimate` export is Open Group exchange XML. Import that through Archi's Open Group exchange import workflow instead of opening it as a native Archi model file.

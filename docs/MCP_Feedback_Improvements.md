Date: 11 May 2026

> **Implementation status (2026-07-04, v0.5.0):** Delivered — relationship
> compatibility/recommendation tools, semantic validation modes, deterministic
> repairs, quality reports and export gates, TOGAF readiness (advisory,
> scope-frozen), QA/coverage view metadata, and did-you-mean type errors.
> One deliberate deviation from this PRD: `semantic_validation` now defaults
> to `warn` (not `off`) on relationship creation — warn mode returns
> `data.semantic_warning` with valid alternatives, which better serves goal 1
> ("prevent invalid relationships from being created silently") while
> preserving non-goal 5 (drafts are never blocked; `off` remains available).

> **Update (2026-07-24) — FR6 got stricter without a code change.** The
> pyArchimate 1.12.0 upgrade (ARC-028) repaired `check_invalid_conn()`, which
> `validate_model()` delegates to and `build_quality_report()` consumes as its
> `visual_validation` section. On 1.11.3 that helper could only return `[]` or
> raise `KeyError` on the first orphan connection, so the quality gate could
> never actually fail on one; on 1.12.0 it returns the offending ids and the
> gate sees them. Consequence for FR6's acceptance criteria: a model carrying
> orphan view connectors that previously passed `quality_gate="strict"` can
> now be blocked. This is the intended behaviour — it is the gate finally
> enforcing a criterion it always claimed — but it is a real behaviour change
> for existing callers, not a no-op upgrade.

> **Update (2026-07-27) — the validation layer is additive, and one check
> was not.** An audit against the pyArchimate SDK confirmed the split this
> PRD assumes: the MCP owns zero ArchiMate rules, delegating every
> hard-validity verdict upstream (`check_invalid_conn` / `check_invalid_nodes`
> in `validate_model`, `check_valid_relationship` and `ALLOWED_RELATIONSHIPS`
> in `relationship_rules`, `STANDARD_VIEWPOINTS` from the viewpoint registry).
> The one genuine duplicate has been removed: `validate_semantics` no longer
> emits `MISSING_NODE_ELEMENT`, because `check_invalid_nodes` already reports
> the same dangling node and `build_quality_report` shows visual and semantic
> validation side by side, so FR6 reports counted one defect twice. The gate
> is not weakened — the dangling node still fails `visual_validation`, which
> the gate checks independently of `allow_semantic_issues`. The relationship
> loop, which looks like the same kind of duplicate, deliberately stays:
> upstream's `check_invalid_relationships` discards the reason string and
> returns bare ids, while this loop captures it and enriches it into the
> `valid_alternatives` / `suggested_repairs` payload that FR3 and FR5 depend
> on (ARC-035).


# PRD: ArchiMate MCP Model Quality, Validation, and Agent Guidance

## 1. Purpose

Improve the ArchiMate MCP server so that models generated or edited through an MCP client agent are semantically valid, easier for agents to use correctly, and better aligned with TOGAF-style architecture practice.

The MCP server should not require its own LLM. It should act as a deterministic domain API, validator, and constraint engine. The client agent remains responsible for architectural intent and user-facing judgment, while the MCP enforces hard ArchiMate correctness and exposes metadata that helps the agent make better choices.

## 2. Problem Statement

During validation of an Interparking booking process ArchiMate model, the model had:

- Valid visual references.
- No orphan elements.
- Complete relationship coverage across views.
- 29 semantic validation failures caused by invalid ArchiMate relationship combinations.

The failures were not layout problems. They were metamodel and relationship inference problems. Examples included:

- `BusinessProcess -> ApplicationService` modeled as `Access`.
- `BusinessRole -> ApplicationComponent` modeled as `Assignment`.
- `Goal -> BusinessProcess` modeled as `Realization`.
- `Driver -> BusinessProcess` modeled as `Influence`.
- `ApplicationComponent -> Node` modeled as `Realization`.
- `BusinessProcess -> BusinessObject` modeled as `Flow`.
- `ApplicationInterface -> ApplicationService` modeled as `Access`.

These errors are deterministic and should be caught or prevented by the MCP. Relying on every calling agent to infer all ArchiMate rules correctly will produce inconsistent model quality.

## 3. Core Product Position

The MCP should not become an architecture decision-maker. It should become a reliable ArchiMate domain service.

Recommended split:

```text
Agent = planner / interpreter / architect
MCP = domain API / validator / constraint engine
```

The MCP should enforce what is objectively invalid. The agent should decide what the user means when multiple valid modeling choices exist.

## 4. Goals

1. Prevent invalid ArchiMate relationships from being created silently.
2. Expose machine-readable metadata so client agents can choose correct element and relationship types.
3. Provide deterministic validation and repair guidance.
4. Support TOGAF-oriented model quality checks without pretending to replace architecture judgment.
5. Improve generated model quality before export.
6. Keep technical QA views separate from stakeholder-facing architecture views.

## 5. Non-Goals

1. Do not embed an independent LLM in the MCP.
2. Do not make the MCP decide business architecture intent without user or agent context.
3. Do not enforce full TOGAF compliance as a binary pass/fail condition.
4. Do not auto-correct ambiguous modeling choices without explicit caller approval.
5. Do not block all exports by default if the caller deliberately requests a draft or invalid diagnostic model.

## 6. User Personas

### 6.1 MCP Client Agent

An AI agent that creates or edits ArchiMate models by calling MCP tools.

Needs:
- Clear type metadata.
- Valid relationship options.
- Structured validation errors.
- Repair suggestions.
- Predictable tool behavior.

### 6.2 Enterprise Architect

A human reviewing generated architecture models.

Needs:
- Semantically valid ArchiMate models.
- Views that communicate stakeholder concerns.
- Confidence that generated models can be opened and reviewed in Archi.
- Clear distinction between architecture views and QA/coverage views.

### 6.3 MCP Developer

The developer maintaining the ArchiMate MCP server.

Needs:
- Deterministic requirements.
- Acceptance criteria.
- Concrete API/tool changes.
- Clear boundary between MCP logic and client-agent judgment.

## 7. Functional Requirements

### FR1: Relationship Compatibility Matrix

The MCP must maintain a compatibility matrix for ArchiMate relationship types by source element type and target element type.

The matrix must support:
- Source element type.
- Target element type.
- Valid relationship types.
- Valid direction.
- Required relationship attributes, such as `access_type` for `Access`.
- Optional warning severity for weak but valid relationships.

Example response:

```json
{
  "source_type": "ApplicationService",
  "target_type": "BusinessProcess",
  "valid_relationships": [
    {
      "type": "Serving",
      "direction": "source_to_target",
      "recommended": true,
      "reason": "Application service serves business behavior."
    }
  ]
}
```

Acceptance criteria:
- Invalid relationship combinations are detectable before creation.
- The matrix is accessible through a public MCP tool.
- The matrix is versioned or tied to the supported ArchiMate implementation.

### FR2: Validate Relationship Before Create

`add_relationship` and `add_relationships` must validate source type, target type, relationship type, direction, and required attributes before committing.

Acceptance criteria:
- Invalid relationships are rejected by default.
- Batch creation rolls back by default if any invalid relationship is found.
- Error response includes source/target names and types.
- Error response includes valid alternatives when possible.

Example error:

```json
{
  "status": "error",
  "code": "INVALID_RELATIONSHIP_COMBINATION",
  "message": "Access is invalid from BusinessProcess to ApplicationService.",
  "relationship": {
    "source": "Search Parking",
    "source_type": "BusinessProcess",
    "target": "Search Service",
    "target_type": "ApplicationService",
    "requested_type": "Access"
  },
  "suggestions": [
    {
      "type": "Serving",
      "source": "Search Service",
      "target": "Search Parking",
      "confidence": "high",
      "reason": "ApplicationService commonly serves BusinessProcess."
    }
  ]
}
```

### FR3: Relationship Recommendation Tool

Add a tool that recommends valid relationship types based on source, target, and optional intent.

Proposed tool:

```text
recommend_relationship
```

Inputs:
- `source_id` or `source_type`
- `target_id` or `target_type`
- optional `intent`
- optional `strict_archimate`

Supported intents:
- `serves`
- `uses_data`
- `writes_data`
- `reads_data`
- `realizes`
- `assigned_to`
- `flows_to`
- `influences`
- `associated_with`
- `deployed_on`
- `technology_supports_application`
- `application_supports_business`

Acceptance criteria:
- Returns only valid ArchiMate relationship options.
- Includes direction.
- Includes confidence and explanation.
- Indicates when user/agent judgment is required.

### FR4: Deterministic Auto-Repair Suggestions

Add validation output that groups semantic issues by repair pattern.

Example repair patterns:

- Invalid `Access` from `BusinessProcess` to `ApplicationService`:
  - Suggest `Serving` from `ApplicationService` to `BusinessProcess`.
- Invalid `Flow` from `BusinessProcess` to `BusinessObject`:
  - Suggest `Access` from `BusinessProcess` to `BusinessObject`.
- Invalid `Realization` from `ApplicationService` to `ApplicationComponent`:
  - Suggest reversing direction: `ApplicationComponent` realizes `ApplicationService`.
- Invalid `Realization` from `ApplicationComponent` to `Node`:
  - Suggest `Serving` from `Node` to `ApplicationComponent`, unless explicit deployment modeling is available.

Acceptance criteria:
- Validation output includes grouped issue counts.
- Each issue includes at least one suggested fix when deterministic.
- Ambiguous cases are marked as requiring agent/user decision.

### FR5: Optional Apply Repairs Tool

Add an explicit tool to apply deterministic repairs.

Proposed tool:

```text
repair_semantic_issues
```

Inputs:
- `repair_ids`
- `repair_all_deterministic`
- `preserve_relationship_ids`
- `rollback_on_error`
- `update_views`
- `auto_layout`

Acceptance criteria:
- Does not run implicitly unless called.
- Preserves relationship IDs when possible.
- Deletes/recreates relationships only when necessary.
- Reconnects affected view connections.
- Produces a change report.
- Does not apply ambiguous repairs without explicit selection.

### FR6: Export Quality Gate

`export_model_to_file` and `export_model_content` should support quality-gate options.

Proposed parameters:

```json
{
  "quality_gate": "off | warn | strict",
  "allow_semantic_issues": false,
  "allow_visual_issues": false,
  "allow_orphans": true,
  "include_quality_report": true
}
```

Behavior:
- `off`: current behavior.
- `warn`: export succeeds with structured warnings.
- `strict`: export fails if selected criteria fail.

Recommended default:
- Existing behavior can remain for backward compatibility.
- New model-generation workflows should use `quality_gate: "strict"`.

Acceptance criteria:
- Strict export fails on semantic validation errors.
- Warnings are structured and machine-readable.
- Caller can intentionally override for draft workflows.

### FR7: TOGAF-Oriented Completeness Check

Add a TOGAF-oriented quality check that is advisory, not a hard semantic validator.

Proposed tool:

```text
assess_togaf_readiness
```

Checks:
- Stakeholders present.
- Concerns documented.
- Goals, drivers, requirements, constraints, or principles represented.
- Baseline/target/transition status identified.
- Gaps represented when comparing baseline and target.
- Work packages or implementation roadmap present for implementation planning.
- Views have purpose metadata.
- Views are mapped to stakeholder concerns.

Acceptance criteria:
- Produces a score or checklist, not a binary compliance claim.
- Clearly separates hard ArchiMate validity from TOGAF architecture completeness.
- Provides recommended additions.

Example:

```json
{
  "togaf_readiness": "partial",
  "hard_failures": [],
  "advisory_findings": [
    {
      "code": "MISSING_STAKEHOLDER_CONCERNS",
      "severity": "medium",
      "message": "No explicit stakeholder concern metadata found on views."
    },
    {
      "code": "NO_BASELINE_TARGET_CLASSIFICATION",
      "severity": "medium",
      "message": "Architecture elements are not marked as baseline, target, or transition."
    }
  ]
}
```

### FR8: View Metadata Support

Views should support structured metadata to guide agents and reviewers.

Recommended view properties:
- `viewpoint`
- `purpose`
- `stakeholders`
- `concerns`
- `architecture_layer`
- `architecture_state`
- `is_quality_assurance_view`
- `is_stakeholder_facing`

Acceptance criteria:
- MCP can create/update these properties.
- Inspection output summarizes missing metadata.
- Coverage views are explicitly marked as QA views.

### FR9: Distinguish QA Views From Architecture Views

Relationship coverage views are useful but should not be confused with stakeholder-facing architecture views.

Acceptance criteria:
- `ensure_all_relationships_in_views` marks coverage views with metadata such as:
  - `mcp:relationship_coverage_view = true`
  - `is_quality_assurance_view = true`
  - `is_stakeholder_facing = false`
- TOGAF readiness assessment excludes QA views from stakeholder-view completeness unless requested.

### FR10: Agent Guidance Metadata

The MCP should expose concise, machine-readable usage guidance for agents.

Enhance existing guidance with:
- Common relationship patterns.
- Anti-patterns.
- Recommended workflow.
- Validation-before-export checklist.

Example anti-patterns:
- Do not model business process to application service as `Access`.
- Do not use `Flow` for business process to business object data usage.
- Do not use `Realization` from technology node to application component unless the metamodel allows it in the intended direction.
- Do not use coverage views as primary communication views.

Acceptance criteria:
- Guidance is returned by a stable tool.
- Guidance is compact enough for agents to consume regularly.
- Guidance links to supported MCP tools.

## 8. Recommended Agent Workflow

The MCP should document this workflow for client agents:

1. Load or create model.
2. Query supported types and relationship rules.
3. Create elements.
4. For each intended relationship, call relationship recommendation or validation.
5. Create relationships.
6. Create stakeholder-facing views.
7. Connect visible relationships.
8. Ensure all relationships are covered by at least one view.
9. Run visual validation.
10. Run semantic validation.
11. Run orphan detection.
12. Run TOGAF readiness assessment when relevant.
13. Repair deterministic semantic issues.
14. Export with `quality_gate: "strict"` for final deliverables.

## 9. Data Model Changes

### 9.1 Relationship Rule Schema

```json
{
  "id": "application_service_serves_business_process",
  "source_type": "ApplicationService",
  "target_type": "BusinessProcess",
  "relationship_type": "Serving",
  "valid": true,
  "recommended_intents": ["application_supports_business", "serves"],
  "direction": "source_to_target",
  "confidence": "high",
  "notes": "Application services commonly serve business behavior."
}
```

### 9.2 Validation Issue Schema

```json
{
  "code": "INVALID_RELATIONSHIP_COMBINATION",
  "severity": "error",
  "relationship_id": "id-...",
  "relationship_type": "Access",
  "source_element_id": "search_parking",
  "source_name": "Search Parking",
  "source_type": "BusinessProcess",
  "target_element_id": "search_service",
  "target_name": "Search Service",
  "target_type": "ApplicationService",
  "suggested_repairs": [
    {
      "repair_id": "repair-...",
      "action": "replace_relationship",
      "new_type": "Serving",
      "new_source_id": "search_service",
      "new_target_id": "search_parking",
      "confidence": "high",
      "deterministic": true
    }
  ]
}
```

### 9.3 Quality Report Schema

```json
{
  "visual_validation": {
    "is_valid": true,
    "invalid_nodes_count": 0,
    "invalid_connections_count": 0
  },
  "semantic_validation": {
    "is_valid": true,
    "issues_count": 0
  },
  "coverage": {
    "elements_not_in_any_view_count": 0,
    "remaining_unused_relationships_count": 0
  },
  "togaf_readiness": {
    "status": "partial",
    "advisory_findings_count": 4
  }
}
```

## 10. Success Metrics

### Model Validity Metrics

- 0 invalid visual references after generation.
- 0 invalid ArchiMate relationship combinations after generation.
- 0 relationships unused in all views.
- 0 elements missing from all views unless explicitly marked as library/reference elements.

### Agent Usability Metrics

- Agents can discover valid relationship options without external ArchiMate knowledge.
- Validation errors include actionable repair suggestions.
- Batch generation workflows can fail early before export.

### TOGAF Readiness Metrics

- Stakeholder-facing views have purpose, stakeholder, and concern metadata.
- QA/coverage views are marked separately.
- Generated models can report missing TOGAF architecture-package elements without claiming false compliance.

## 11. Acceptance Test Scenarios

### Scenario 1: Invalid Business Process to Application Service Access

Input:
- Source: `BusinessProcess`
- Target: `ApplicationService`
- Relationship: `Access`

Expected:
- Creation rejected in strict mode.
- Suggested fix: `ApplicationService -> BusinessProcess` using `Serving`.

### Scenario 2: Business Process Writes Business Object

Input:
- Source: `BusinessProcess`
- Target: `BusinessObject`
- Intent: `writes_data`

Expected:
- Recommended relationship: `Access` with `access_type: "Write"`.
- `Flow` is not recommended.

### Scenario 3: Application Component Provides Application Service

Input:
- Source: `ApplicationComponent`
- Target: `ApplicationService`
- Intent: `realizes`

Expected:
- Recommended relationship: `Realization` from component to service.
- Reverse direction is rejected or warned.

### Scenario 4: Technology Node Supports Application Component

Input:
- Source: `Node`
- Target: `ApplicationComponent`
- Intent: `technology_supports_application`

Expected:
- Recommended relationship: valid support relationship, such as `Serving`, based on supported metamodel.
- Invalid application-to-node realization is rejected.

### Scenario 5: Export With Semantic Issues

Input:
- Model has one invalid relationship.
- Export called with `quality_gate: "strict"`.

Expected:
- Export fails.
- Response includes semantic validation report and suggested repair.

### Scenario 6: TOGAF Readiness Assessment

Input:
- Semantically valid model with no stakeholders or view metadata.

Expected:
- ArchiMate semantic validation passes.
- TOGAF readiness returns advisory findings.
- Result does not claim the model is fully TOGAF-compliant.

## 12. Implementation Phases

### Phase 1: Hard Validation

- Add relationship compatibility matrix.
- Enforce validation in `add_relationship` and `add_relationships`.
- Improve validation error payloads.
- Add valid alternatives to semantic validation output.

### Phase 2: Agent Guidance

- Add relationship recommendation tool.
- Expand usage guide with common patterns and anti-patterns.
- Add view metadata recommendations.

### Phase 3: Quality Gate

- Add export quality-gate options.
- Add structured quality report.
- Add strict/warn/off modes.

### Phase 4: Repair and TOGAF Readiness

- Add deterministic semantic repair suggestions.
- Add explicit repair tool.
- Add TOGAF readiness assessment.
- Add QA-view classification.

## 13. Standards References

This PRD is based on official Open Group sources available as of 2026-05-10. The MCP developer should treat these as the authoritative starting points and verify the exact ArchiMate metamodel rules against the version implemented by the underlying modeling library.

### 13.1 Primary TOGAF References

1. TOGAF Standard, 10th Edition downloads  
   URL: https://www.opengroup.org/togaf-standard-10th-edition-downloads  
   Relevance: establishes TOGAF Standard, 10th Edition as the current standard package to reference for TOGAF-oriented model quality, licensing, and documentation access.

2. TOGAF Standard, 10th Edition launch announcement  
   URL: https://www.opengroup.org/open-group-announces-launch-togaf-standard-10th-edition  
   Relevance: confirms the April 25, 2022 release and the modular structure of the 10th Edition, including expanded guidance for applying the framework across different architecture contexts.

3. TOGAF framework overview  
   URL: https://www.opengroup.org/togaf  
   Relevance: describes TOGAF as an enterprise architecture methodology and framework and notes that the 10th Edition is designed around common universal concepts plus configurable guidance. This supports the PRD position that TOGAF readiness should be advisory and context-sensitive, not a simplistic binary pass/fail test.

4. TOGAF Library  
   URL: https://www.opengroup.org/togaf%C2%AE-library  
   Relevance: points developers to official TOGAF Series Guides and related Open Group publications. This is the right reference family for future MCP guidance around ADM phases, governance, business architecture, agile, digital, and other specialized concerns.

5. TOGAF Standard, 10th Edition template deliverables  
   URL: https://help.opengroup.org/hc/en-us/articles/21726647171730-Are-There-Any-Template-Deliverables-for-the-TOGAF-Standard  
   Relevance: supports the PRD recommendation to add optional TOGAF architecture-package metadata and checks, such as stakeholders, concerns, requirements, constraints, baseline/target state, gaps, work packages, and roadmap-oriented views.

### 13.2 ArchiMate References

1. ArchiMate standards publication page  
   URL: https://publications.opengroup.org/standards/archimate  
   Relevance: official Open Group publication entry point for ArchiMate standards. The MCP should align its relationship compatibility matrix with the ArchiMate version actually supported by its modeling backend.

2. ArchiMate certification page  
   URL: https://www.opengroup.org/certifications/archimate  
   Relevance: states that the ArchiMate certification program covers the ArchiMate 3.2 release of the specification. This is useful for confirming the practical conformance baseline used by tools and training.

3. ArchiMate overview  
   URL: https://www.opengroup.org/archimate-forum/archimate-overview  
   Relevance: describes ArchiMate as an open and independent modeling language for describing, analyzing, and visualizing relationships across business domains. This supports the PRD requirement that the MCP enforce valid model relationships instead of treating them as free-form diagram links.

4. ArchiMate and TOGAF complementarity  
   URL: https://help.opengroup.org/hc/en-us/articles/32115987894930-How-the-ArchiMate-Language-and-the-TOGAF-Standard-Complement-Each-Other  
   Relevance: explains the division of purpose: TOGAF provides the method, governance, and architecture practice structure; ArchiMate provides the modeling language and visual representation. This directly supports the PRD responsibility split: MCP enforces ArchiMate correctness, while the agent/user applies TOGAF architecture judgment.

### 13.3 Licensing and Usage References

1. Open Group standards licensing  
   URL: https://www.opengroup.org/licensing-commercial-and-non-commercial  
   Relevance: confirms that both TOGAF and ArchiMate are licensed Open Group standards. The MCP documentation should link to official sources instead of embedding large portions of the standards text.

2. TOGAF licensed downloads  
   URL: https://www.opengroup.org/togaf-licensed-downloads  
   Relevance: directs users to current TOGAF licensing and download paths.

### 13.4 How These References Map to the PRD

- Relationship compatibility matrix: based on the ArchiMate specification and the ArchiMate version implemented by the MCP backend.
- Relationship recommendation tool: based on ArchiMate relationship rules, enriched with MCP-specific intent labels for agent usability.
- Export quality gate: based on deterministic ArchiMate model validity, not subjective TOGAF completeness.
- TOGAF readiness assessment: based on TOGAF architecture-work expectations such as stakeholders, concerns, architecture views/viewpoints, requirements, constraints, gaps, and implementation planning.
- QA view classification: derived from the distinction between stakeholder-facing architecture descriptions and internal validation/coverage views.
- Agent guidance: based on the Open Group distinction that TOGAF defines architecture method and governance while ArchiMate defines visual modeling language.

### 13.5 Documentation Caution

The MCP documentation should reference and link to official Open Group material, but it should avoid copying large sections of TOGAF or ArchiMate content into the MCP repository. Recommended implementation:

- Store concise summaries and links in MCP documentation.
- Store machine-readable metamodel constraints generated or curated for the supported ArchiMate version.
- Clearly state which ArchiMate version the MCP validates against.
- Clearly state that TOGAF readiness checks are advisory and do not certify TOGAF compliance.

## 14. Open Questions

1. Which ArchiMate version should the MCP explicitly target?
2. Should invalid relationship creation be rejected by default, or should strict validation be opt-in for backward compatibility?
3. Should deterministic repair preserve original relationship IDs by default?
4. Should TOGAF readiness be implemented as a separate tool or folded into `inspect_active_model`?
5. Should QA/coverage views be hidden from normal view summaries unless requested?

## 15. Final Recommendation

The MCP should own deterministic correctness. The agent should own architectural intent.

The most important product change is to stop treating ArchiMate semantic validation as an after-the-fact diagnostic only. The MCP should expose relationship rules before creation, reject invalid structures during creation in strict workflows, provide repair suggestions during validation, and gate final export when requested.

TOGAF alignment should be implemented as advisory readiness checks and model metadata guidance, not as a hard compliance claim. This gives client agents enough structure to generate better models while preserving the human and agent judgment required for real enterprise architecture work.

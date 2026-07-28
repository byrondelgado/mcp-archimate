---
id: decision-005
title: 'Constrain ArchiMate validity in the MCP, leave intent to the agent'
date: '2026-07-27 21:38'
status: accepted
---
## Context

An MCP server for architecture modelling could plausibly try to *be* the
architect: infer intent, pick relationship types, restructure models toward some
notion of good practice. That is the wrong division of labour.

The calling agent has the conversation, the requirements and the user's intent.
The server has none of that — it sees one tool call at a time. What the server
does have that the agent lacks is a deterministic, versioned view of what
ArchiMate actually permits.

There is also a hard rule about where verdicts come from. Reimplementing
ArchiMate's relationship matrix here would create a second, divergent source of
truth that silently disagrees with the library doing the real work.

## Decision

**The MCP is a constraint engine. The agent is the architect.**

The server enforces hard ArchiMate validity and offers deterministic help; it
never decides what the model should mean.

**It owns zero ArchiMate rules.** Every hard-validity verdict is delegated to
pyArchimate: `check_invalid_conn` / `check_invalid_nodes` in `validate_model`,
`check_valid_relationship` and `ALLOWED_RELATIONSHIPS` in
`relationship_rules.py` (which declares
`"rule_source": "pyArchimate.relationship.ALLOWED_RELATIONSHIPS"`), and
`STANDARD_VIEWPOINTS` from `viewpoint_registry`.

The validation layer is **additive**: it enriches upstream verdicts with names,
types, valid alternatives, suggested repairs and a `requires_decision` flag. It
does not re-derive them.

Where the agent must choose, the server surfaces options rather than picking:
`get_relationship_compatibility`, `recommend_relationship` (intent-based —
`serves`, `reads_data`, `realizes`), and `repair_semantic_issues` for the
deterministic cases only.

Validation is never silent. `add_relationship` defaults to
`semantic_validation="warn"`, which creates the relationship but returns
`data.semantic_warning` with valid alternatives; `"strict"` raises with the
alternatives in `error.details`; only `"off"` skips the check.

## Consequences

- Upgrading pyArchimate can change validity verdicts. That is correct — it means
  the matrix moved — and it is why the pin is tight (see the dependency-pin
  decision).
- Agents get actionable errors instead of bare rejections, which is what makes
  an LLM caller able to self-correct.
- The server will not stop a user from building a semantically valid but
  architecturally poor model. That is the agent's job, and the split is
  deliberate.
- `checker_rules.yml` in pyArchimate is *not* a rule engine despite the name —
  it is a metadata and ARIS type-map file. There is no unused upstream checker
  being duplicated here.

**Enforced by:** `relationship_rules.py` and its `rule_source` declaration, the
delegation in `validate_model`, and `docs/MCP_Feedback_Improvements.md`.

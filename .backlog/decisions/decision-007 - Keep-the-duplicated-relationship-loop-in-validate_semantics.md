---
id: decision-007
title: Keep the duplicated relationship loop in validate_semantics
date: '2026-07-27 21:38'
status: accepted
---
## Context

`validate_semantics` loops over relationships and checks each one, which looks
like a plain duplicate of pyArchimate's own `check_invalid_relationships`. It
reads as dead weight, and a reasonable reviewer will try to delete it.

The verdicts really are identical. The difference is what survives the call.

Upstream calls `check_valid_relationship` **without** `raise_flg=True`. That
discards the reason string and returns bare relationship ids — an opaque list of
identifiers with no explanation of what was wrong.

`_semantic_relationship_issue` passes `raise_flg=True` precisely so it can catch
the exception and capture `str(exc)`, then enriches it through
`relationship_issue_details`: source and target names and types,
`valid_alternatives`, `suggested_repairs`, and a `requires_decision` flag.

One opaque id upstream versus a fifteen-field actionable issue here.

## Decision

**Keep the loop. Do not collapse it into the upstream call.**

This is not a re-implementation of the rules — the verdict still comes from
`check_valid_relationship`, so the constraint-engine decision holds. It is a
re-invocation that keeps the diagnostic upstream throws away.

The code carries a comment saying so. Keep it.

## Consequences

- A structural duplicate stays in the codebase permanently and will keep looking
  like an oversight. This decision is the answer to that.
- Replacing it with the upstream call would silently starve two features:
  `repair_semantic_issues` loses the material it works from, and the did-you-mean
  suggestions in `error.details` lose their alternatives. Nothing would fail
  loudly — the responses would just get less useful.
- The loop costs one extra pass over relationships during validation. Immaterial
  at model scale.
- A related non-duplicate, for contrast: `validate_semantics` deliberately does
  **not** check for dangling view nodes. `validate_model` already reports them via
  `check_invalid_nodes`, and `build_quality_report` aggregates visual and semantic
  validation side by side, so the old `MISSING_NODE_ELEMENT` issue counted one
  dangling node twice. Upstream is also the stronger check — it catches an
  `Element`-cat node with no `ref` at all. That one was removed in ARC-035 and
  must not come back.

**Enforced by:** `_semantic_relationship_issue`, `relationship_issue_details`, the
explanatory comment at the loop, and ARC-035.

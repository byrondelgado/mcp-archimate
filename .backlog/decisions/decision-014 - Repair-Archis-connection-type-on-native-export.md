---
id: decision-014
title: Repair Archi's connection type on native export
date: '2026-07-28 09:14'
status: accepted
---
## Context

A user exported a five-view model to Archi's native `.archimate` format. Four
views opened. One refused, with **"Failed to create the part's controls"** — an
error that names nothing useful and points at no element.

The cause is a type distinction pyArchimate's writer does not make. Archi has
**two** diagram connection classes:

- **`archimate:Connection`** is `DiagramModelArchimateConnection`, an
  `IDiagramModelArchimateComponent`. Archi calls `getArchimateConcept()` on it
  while building diagram figures.
- **`archimate:DiagramModelConnection`** is the concept-less line Archi uses for
  note and group connectors.

pyArchimate's `archiWriter` types **every** connection as `archimate:Connection`
and merely omits `archimateRelationship` for annotation lines. Its own code
comment claims Archi does the same; that is half right. Archi omits the
attribute **and** writes the other type.

The result is a concept-backed connection with no concept.
`getArchimateConcept()` returns null, Archi throws a `NullPointerException` while
creating the editor part, and the entire view refuses to open. In the reported
model the only affected view was the one holding the single connector lacking
`archimateRelationship`.

Nothing in this server's validation could catch it. The XML is well-formed, every
id is unique, and no reference dangles. `validate_model` and `validate_semantics`
both pass. It is only wrong relative to Archi's runtime type expectations.

## Decision

**Repair the connection type in `_finalize_archi_output` on every native export.**

The repair keys on the **absence of `archimateRelationship`**, not on any
knowledge of notes or `Label` nodes. That choice is the point: it repairs exactly
the set Archi would mis-instantiate, and leaves concept-backed connections alone,
without needing to know why a given connection has no relationship.

This is correctness, not cosmetics. The alternative is a file that silently fails
to open.

## Consequences

- Native `.archimate` export cannot be a straight `model.write(writer=Writers.archi)`.
  It is that call plus a post-processing pass, which also stabilises folder ids
  for diff-friendly re-exports, rewrites `influenceStrength` to Archi's native
  `strength`, converts `AndJunction`/`OrJunction` to Archi's single `Junction`
  with a `type` attribute, and maps viewpoint slugs to Archi's canonical ids.
- The export runs on a **copy** of the model, so these writer-compatibility
  adjustments never mutate the active model.
- `test_archi_export_never_pairs_concept_connection_type_with_missing_relationship`
  asserts the invariant across every connection in an export. Keep it: this
  defect is invisible to every other check in the suite.
- The exchange format has a *different* defect with the same root cause —
  annotation lines must be retyped to `xsi:type="Line"` there, because the schema
  types `relationshipRef` as a required `xs:IDREF`. Two formats, two repairs; do
  not assume a fix on one path covers the other. See decision-009.
- If pyArchimate's writer is ever corrected upstream, this repair becomes a
  no-op rather than a conflict — it only rewrites connections that are already
  missing `archimateRelationship`.

**Enforced by:** `_finalize_archi_output`, the invariant test named above, and
the detailed write-up in `docs/TECHNICAL_ARCHITECTURE.md`. Extracted from
ARC-036.

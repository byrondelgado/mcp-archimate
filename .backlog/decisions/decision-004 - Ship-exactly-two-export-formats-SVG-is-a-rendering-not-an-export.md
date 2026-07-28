---
id: decision-004
title: 'Ship exactly two export formats; SVG is a rendering, not an export'
date: '2026-07-27 21:38'
status: accepted
---
## Context

Archi reads two different XML dialects, and confusing them wastes a user's time
in a way that is hard to diagnose:

- **`archi`** — Archi's native `.archimate` format. Opens directly in Archi.
- **`archimate`** — Open Group exchange format. Must be *imported* into Archi,
  not opened. This is the default.

Separately, `render_view_to_svg_file` (ARC-029) writes a view as SVG so a human
can look at the diagram. SVG is superficially "another output format", and an
agent scanning the tool list will read it as one.

It is not. SVG is a picture. It carries no model semantics, cannot be loaded
back, and importing it into Archi is impossible. Listing it beside the two real
formats would invite agents to offer it as an export and users to expect a round
trip that cannot exist.

## Decision

**There are exactly two export formats**, both in `SUPPORTED_FORMATS`
(`constants.py:19`): `archi` and `archimate`.

**`"svg"` is deliberately absent from `SUPPORTED_FORMATS`** and must never be
added to it or to the export tools. `render_view_to_svg_file` is a separate,
narrower tool: it writes one view to a file for a human, never returns markup,
and never triggers a layout pass.

Its `ToolAnnotations` say *idempotent*, not read-only — a tool that writes a file
is not read-only even when it never mutates the model.

## Consequences

- Users must be told which format they want, and the docs must keep saying
  "opens directly" versus "must be imported". The default (`archimate`) is the
  one that needs importing, which is the more surprising of the two.
- Each format carries its own writer compatibility work: native export runs on a
  *copy* of the model so adjustments never mutate the active one, stabilises
  folder ids, rewrites `influenceStrength` to Archi's `strength`, converts
  `AndJunction`/`OrJunction` to Archi's single `Junction` with a `type`
  attribute, and maps viewpoint slugs to Archi's canonical ids. Exchange export
  is sanitised to drop dangling view-property references and to retype note
  connectors as `xsi:type="Line"`.
- A side effect worth knowing: because `_strip_dangling_view_properties` drops
  every view property from exchange output, the coverage-view marker survives a
  native round trip but not an exchange one. See the coverage-view decision.
- Adding a third format is a real decision with writer and round-trip
  consequences, not a config entry.

**Enforced by:** `SUPPORTED_FORMATS` in `constants.py`, the format check at
`model_manager.py:3327`, and the separation of `render_view_to_svg_file` from the
export tools.

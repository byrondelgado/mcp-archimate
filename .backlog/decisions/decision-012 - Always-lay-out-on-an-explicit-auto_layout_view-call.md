---
id: decision-012
title: Always lay out on an explicit auto_layout_view call
date: '2026-07-28 09:14'
status: accepted
---
## Context

`auto_layout_view` once tried to be clever. A helper called
`_has_meaningful_existing_layout` inspected the view and skipped layout when the
nodes looked deliberately positioned, on the theory that a user who had arranged
a diagram by hand would not want it rearranged.

It could not tell the difference between a human's arrangement and the server's
own. `add_node_to_view` places nodes in default left-to-right slots, and that
placement scored as "meaningful". So the common case — build a view with the
tools, then ask for it to be laid out — hit the skip path.

The result inverted user intent exactly: the caller explicitly asked for layout
and got none. Worse, the skip path interacted with group nesting to duplicate
group members, so views came back both unlaid-out and visibly corrupted. Reported
as models that were "not laid out nicely and grouping was missing or broken".

The underlying error is a category error: the heuristic tried to infer intent
from geometry, when the intent was already stated in the call itself.

## Decision

**An explicit `auto_layout_view` call ALWAYS lays out.** There is deliberately no
"preserve existing layout" heuristic, and none should be added.

The caller asked. That is the whole signal, and it is unambiguous. Guessing
against it is not caution — it is overriding an explicit instruction with a
guess.

Group members are nested exactly once, and legacy duplicate copies left behind by
the old behaviour are **healed** on layout rather than merely avoided, so a model
damaged by the bug repairs itself the next time it is laid out.

## Consequences

- A hand-arranged diagram will be rearranged if layout is requested on it. That
  is correct behaviour, and the remedy is not to call `auto_layout_view` — not to
  make the tool second-guess the caller.
- Notes are the one exception, and a deliberate one: they are pinned across a
  layout run because their position carries meaning that placement cannot infer.
  See decision-009. Note that this exception is justified by *what a note is*,
  not by guessing at intent.
- The duplicate-healing path must stay in the shared prologue of
  `auto_layout_view`, running under both placement engines. Branching
  `nest_grouped_nodes` away from one engine would stop the healing and would
  present as this bug returning. See decision-003.
- If per-node position locking is ever wanted, it should be an **explicit
  parameter** the caller sets, never an inference from coordinates.

**Enforced by:** the absence of `_has_meaningful_existing_layout`, the
duplicate-healing step in `nest_grouped_nodes`, and the regression tests added
with ARC-017.

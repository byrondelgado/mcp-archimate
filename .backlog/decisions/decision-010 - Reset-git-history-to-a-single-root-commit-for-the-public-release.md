---
id: decision-010
title: Reset git history to a single root commit for the public release
date: '2026-07-27 21:38'
status: accepted
---
## Context

This project was developed privately for about a year before being opened, and
the repository showed it.

The commit history described an architecture that no longer exists — FastAPI
routes, a Graphviz layout engine, a different task-management workflow — none of
which matches the current design. It also carried a year of accumulated local
development tooling and configuration that had no place in a public repository,
along with tags from private releases and a stale feature branch.

The author is the sole copyright holder across the entire pre-release history, so
there was no contributor coordination to consider, and he confirmed he was
willing to lose that history given the current state is stable.

Three options were weighed: filter the history to remove the unwanted files and
keep the commits; squash everything into a single root commit; or start a new
repository and abandon the old one.

## Decision

**Squash to a single root commit on `main`, then force-push.**

- One root commit built from the finished, cleaned tree, with `main` and `dev`
  both pointing at it.
- Remove the tags and the stale branch carried over from private development.
- Expire the reflog and garbage-collect.

`dev` is the integration branch; `main` is the release branch and where version
tags are cut.

Filtering was rejected because it rewrites every commit hash anyway, so it pays
the full disruption cost of a rewrite while still leaving a year of narrative
about an architecture that no longer exists. Starting a new repository was
rejected as unnecessary.

## Consequences

**Accepted losses:**

- `git blame` and `git log` carry nothing before the public release. Anyone
  asking why a line exists gets the decision records instead — which is a large
  part of why they were written, and why they were reviewed for completeness
  before the pre-release task history was removed.
- Contributors with an existing clone must re-clone.

**Accepted because:**

- The old history documented a design that has since been replaced, so its
  archaeological value was low and its potential to mislead was not.
- A single honest root commit is a better starting point for a public project
  than a year of private-project churn.
- The decision records in this directory preserve the reasoning that actually
  matters, in a form a newcomer can read in an afternoon.

**Obligation created:** because there is no history to consult, the decision
records *are* the project's memory. A decision that gets undone without its
record being updated leaves nothing behind to explain what was lost. Keep them
current.

**Enforced by:** ARC-048.

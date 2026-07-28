---
id: ARC-052
title: Document the verified release process
status: Done
assignee:
  - '@claude'
created_date: '2026-07-28 11:11'
updated_date: '2026-07-28 11:15'
labels: []
milestone: m-0
dependencies: []
priority: medium
ordinal: 43000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The v0.7.0 release is done and the pipeline is proven end to end, but CONTRIBUTING.md still describes the one-time PyPI and GitHub setup as work to be done, and nothing records what was actually learned running it. The next release may be months away, by which time the details will be gone.

Capture two different things, in two different places:
- CONTRIBUTING.md gets the RUNBOOK — the steps someone follows to ship a version, with the one-time setup recorded as complete rather than pending.
- A decision record gets the DESIGN — why the pipeline is shaped this way (tag-triggered, Trusted Publishing, a single human gate, TestPyPI on a separate environment), so a future change knows what it would be giving up.

Also worth recording: verify a GitHub Action tag actually resolves before pinning it. Reading the latest release name is not the same check, and that mistake made every CI job fail on the first public push.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 CONTRIBUTING.md gives a complete release runbook that works without this conversation
- [x] #2 The one-time PyPI and GitHub setup is recorded as done, with the exact values configured
- [x] #3 A decision record explains the pipeline design and what each gate protects
- [x] #4 The action-pinning lesson is recorded where someone editing a workflow will see it
- [x] #5 Yank versus delete, and the fact that a version number is never reusable, are documented
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Documented the release process in two places for two audiences. CONTRIBUTING.md carries the runbook: the five-step sequence, what each pipeline job checks, how to rehearse against TestPyPI including the --extra-index-url and --index-strategy flags that TestPyPI installs need, yank versus delete, and the one-time PyPI and GitHub setup recorded as complete with the exact values configured. decision-016 carries the design: why tag-triggered, why OIDC, why a single human gate, why TestPyPI runs on a separate environment, and the note that every gate was verified to fail rather than only to pass. Both record the action-pinning hazard that broke CI on the first public push, with the one-line check that would have caught it. CLAUDE.md links to both.
<!-- SECTION:FINAL_SUMMARY:END -->

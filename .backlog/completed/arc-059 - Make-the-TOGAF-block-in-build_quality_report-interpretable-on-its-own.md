---
id: ARC-059
title: Make the TOGAF block in build_quality_report interpretable on its own
status: Done
assignee:
  - '@claude'
created_date: '2026-07-28 13:41'
updated_date: '2026-07-28 14:11'
labels: []
dependencies: []
priority: medium
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
build_quality_report(include_togaf=true) reports a finding count with no findings and a score with no scale:

    "togaf_readiness": {"status": "limited", "score": 0, "advisory_findings_count": 7}

Seven findings exist and none of them is reachable from this response. A caller cannot tell the difference between "the model is fine, this assessment just does not apply to it" and "the model has seven real problems".

Everything missing is already computed. assess_togaf_readiness returns max_score (7), the seven finding dicts, hard_failures, and compliance_claim; build_quality_report projects that down to three fields at model_manager.py:695-699 and drops the rest. Reproduced against a model with no Motivation or Strategy layer: score 0 of 7, status limited, findings MISSING_STAKEHOLDER, MISSING_STAKEHOLDER_CONCERNS, MISSING_MOTIVATION, NO_BASELINE_TARGET_CLASSIFICATION, NO_GAPS, NO_WORK_PACKAGES, NO_STAKEHOLDER_FACING_VIEWS. The whole report is 2,639 bytes, so size is not the reason the findings were dropped.

The status enum is also undocumented. Its thresholds are in the code (model_manager.py:783-789): ready when there are no findings, partial when score >= TOGAF_PARTIAL_SCORE_THRESHOLD (3), limited otherwise. assess_togaf_readiness has a one-line docstring that documents none of this, so a caller cannot tell whether limited is the floor or the middle.

Scope constraint - read decision-015 first. That record freezes the checklist: assess_togaf_readiness is advisory only, its checks are not to be extended, and compliance_claim: false is load-bearing rather than decoration. This task is about surfacing what is already computed and documenting the scale that already exists. Adding checks, changing thresholds, or anything that makes the output look more authoritative is out of scope and would need that decision revisited.

Source: field report 2026-07-28, finding 4 (severity medium), plus measurements taken while verifying it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A caller reading only build_quality_report can tell which TOGAF findings fired, not just how many
- [x] #2 The score is interpretable without reading the source: the response carries its scale rather than a bare integer
- [x] #3 The status values and the thresholds that produce them are documented in the tool docstring and docs/USER_GUIDE.md
- [x] #4 compliance_claim: false remains present and advisory framing is unchanged, per decision-015
- [x] #5 No TOGAF check is added, removed or reweighted
- [x] #6 A test asserts the findings reachable from build_quality_report match those from assess_togaf_readiness on the same model
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. RED: assert build_quality_report(include_togaf=True) exposes the same finding codes as assess_togaf_readiness on the same model, and that the score arrives with its scale.
2. Widen the projection at model_manager.py:695-699 to carry advisory_findings, max_score, hard_failures_count and compliance_claim through, instead of dropping them.
3. Document the status thresholds (ready = no findings, partial = score >= 3, limited otherwise) and the 0-7 scale on assess_togaf_readiness and in docs/USER_GUIDE.md.
4. Add no checks and change no thresholds - decision-015 freezes the checklist.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The projection at model_manager.py:695 now carries advisory_findings, max_score, hard_failures_count and compliance_claim through instead of dropping them. Everything was already computed by assess_togaf_readiness; the whole report with findings included measures 6,731 bytes, so size was never the reason they were dropped.

Documented the scale rather than only exposing it: seven checks, one point per finding, ready at zero findings, partial at score >= 3, limited below. Added to the assess_togaf_readiness and build_quality_report docstrings and to docs/USER_GUIDE.md, with the specific point the field report raised - a model with no Motivation or Strategy content scores 0 legitimately, because the checklist looks for stakeholders, goals, gaps, work packages and baseline/target markers. That is a statement about what the checklist looks for, not a defect in the model.

decision-015 respected: no check added, removed or reweighted, TOGAF_PARTIAL_SCORE_THRESHOLD untouched, compliance_claim: false carried through and asserted by the test.

Verified RED first (KeyError: advisory_findings). The test compares finding codes from build_quality_report against assess_togaf_readiness on the same model, so the two cannot drift.

uv run pytest: 196 passed. uv run ruff check: clean.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
build_quality_report(include_togaf=true) now returns advisory_findings, max_score, hard_failures_count and compliance_claim alongside the tallies, so a score of 0 can be read for what it is; the 0-7 scale and the ready/partial/limited thresholds are documented on the tool and in the User Guide. Checklist untouched per decision-015. Verified by a test confirmed failing first that asserts the findings reachable from build_quality_report match assess_togaf_readiness on the same model. 196 passed, ruff clean.
<!-- SECTION:FINAL_SUMMARY:END -->

---
id: decision-015
title: Freeze assess_togaf_readiness as advisory only
date: '2026-07-28 09:14'
status: accepted
---
## Context

`assess_togaf_readiness` returns advisory findings about how ready a model looks
against a TOGAF-oriented checklist. A code-quality review flagged it as
mission-scope drift and proposed either extending it into something serious or
deleting it.

Both directions are worse than leaving it alone.

**Extending it** would mean this server making conformance claims about a
framework it does not implement. TOGAF readiness is an assessment a person makes
with organisational context; a checklist run against an ArchiMate file cannot
substitute for that, and a tool that appears to say otherwise misleads its user.
It would also contradict the split in decision-005 — the server constrains
validity, the agent and the human own judgement.

**Deleting it** would remove something that is isolated, tested, self-disclaiming
and cheap to keep, and that users find useful as a prompt for their own review.

## Decision

**Keep it, frozen.** `assess_togaf_readiness` is advisory only, returns
`compliance_claim: false`, and its checklist is **not to be extended**.

Adding checks is not a small improvement here. Each one makes the output look
more authoritative without making it more authoritative, which is the specific
failure mode being avoided.

## Consequences

- Requests to "add TOGAF check X" are declined by default. Reopening the scope is
  a decision to revisit this record, not a routine enhancement.
- The `compliance_claim: false` field is load-bearing, not decoration. It is the
  machine-readable disclaimer, and removing it would let a caller present the
  output as a conformance result.
- The tool stays documented as advisory in `docs/TECHNICAL_ARCHITECTURE.md` and
  `docs/USER_GUIDE.md`. If those descriptions ever drift toward implying
  conformance, that is a defect.
- If genuine TOGAF conformance checking is ever wanted, it belongs in a separate
  tool with its own explicit scope — not as growth in this one.

**Enforced by:** the `compliance_claim: false` field, the advisory framing in
`docs/TECHNICAL_ARCHITECTURE.md`, and this record. Extracted from ARC-016, which
dispositioned it as "FROZEN, KEPT".

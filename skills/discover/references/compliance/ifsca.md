# IFSCA Guidelines on Cyber Security and Cyber Resilience

**Source:** circular IFSCA-CSD0MSC/13/2025-DCS, 10 March 2025 —
<https://ifsca.gov.in/Document/Legal/guidelines-on-cyber-security-and-cyber-resilience-for-regulated-entities-in-ifscs-1-10032025064412.pdf>

**Obligations:** `../../scripts/compliance_controls.json`, regime `ifsca`.

## Who it binds

Regulated entities in an International Financial Services Centre — in practice GIFT
IFSC — across banking, capital markets, fund management, insurance and pensions.
Whether the client is a regulated entity in an IFSC is a question for the client. An
entity with a GIFT City presence is not automatically inside; an entity registered
there for a regulated activity generally is.

## What actually changes the architecture

**Incident reporting with two hard deadlines.** An interim report to the Authority
within 3 days, and a detailed root cause analysis within 30 days. These are the most
architecturally consequential lines in the guidelines, because meeting them requires:

- detection that notices the incident well inside 3 days, which means monitoring
  that is actually watched — cross-check domain 14
- logs retained and queryable long enough to reconstruct a root cause 30 days later,
  which is a retention decision in domain 10
- a runbook where both deadlines exist as tasks with owners rather than as
  intentions, because a 3-day clock started at 6pm on a Friday is unforgiving

Put both deadlines in the runbook and in `open-questions.md` with an owner if no
responder is named yet.

**Third-party and external-partner security.** A collaborative approach with shared
expectations for data security, incident reporting and adherence to security
standards, plus risk-based periodic review. The deliverable is a register with the
expectations recorded per party and a review date — and every cloud service in the
data path is a third party.

Note the second-order requirement: if a third party's incident must be reported by
the client within 3 days, the contractual expectation has to require the third party
to notify *faster than that*. Registers frequently miss this and the deadline becomes
unmeetable through no fault of the client's own detection.

**Staff training with records.** Phishing, social engineering, password hygiene and
incident reporting, on a schedule, with completion tracked. Cheap, and it is evidence
somebody will ask for.

**Cyber resilience proportionate to the activities.** Maps to the DR tier, backup
testing and monitoring already decided in domains 10 and 12; the work is producing
the mapping with evidence per control rather than adding new controls.

## Traps

- Missing that the reporting clock is on the *entity*, so upstream notification
  expectations have to be tighter. This is the trap worth catching in the interview.
- Assuming a GIFT City address means the guidelines apply, or that it does not. Ask.
- Treating training as an HR matter outside the specification. The records are
  evidence, so name who owns them.

## What to record

Per obligation: control, evidence, owner. Plus the incident runbook with the 3-day
and 30-day deadlines as explicit steps, and the third-party register with each
party's notification expectation stated in time terms.

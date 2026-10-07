# SOC 2 — not sourced in this build

**Status: stub.** This skill cannot produce a criteria mapping for SOC 2.

**Source to read:** AICPA Trust Services Criteria —
<https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2>

## Why there is nothing here

The Trust Services Criteria were not fetched during the build at all. This is
recorded honestly because the build plan listed SOC 2 among the sourced regimes
while `LIMITATIONS.md` L1 already said it had not been read. The plan was wrong and
the limitation was right, so SOC 2 joins the other two stubs.

## What to do when a client names SOC 2

1. Say plainly that this skill has no criteria mapping. Then ask the two questions
   that matter more than a control list anyway:
   - **Which trust services categories are in scope?** Security is mandatory;
     availability, confidentiality, processing integrity and privacy are each opted
     into. A client who says "SOC 2" usually means Security alone, and scoping the
     others in by assumption creates work nobody asked for.
   - **Type I or Type II?** Type I is a point-in-time design opinion. Type II covers
     operating effectiveness over a period, typically three to twelve months, which
     means evidence has to be *collected continuously from the start of that window*.
     That is the architecturally consequential answer: it turns logging retention,
     access review cadence and change records into things that must exist before the
     window opens rather than before the audit.
2. Record the gap in `open-questions.md` with a named owner.
3. Continue. A well-built estate with the secure defaults, access reviews, logging,
   change control and backup testing already covers most of what a Security-category
   Type II examination looks at. The gap is the mapping and the evidence discipline,
   not usually the controls.

`check_compliance.py` exits non-zero when this regime is named.

## To close this out

Populate the `soc2` entry in `../../scripts/compliance_controls.json` from the Trust
Services Criteria, per category, with the evidence each criterion needs and the
observation window. Set `"sourced": true` and update `LIMITATIONS.md` L1.

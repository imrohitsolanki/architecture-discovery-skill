# HIPAA Security Rule — not sourced in this build

**Status: stub.** This skill cannot produce a control mapping for HIPAA.

**Source to read:** 45 CFR Part 164 Subpart C, via
<https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html>

## Why there is nothing here

The primary text could not be read during the build. The HHS page returned HTTP 403
to a scripted request, which is bot protection rather than a dead link — the URL is
correct and a person can open it. Recorded as `LIMITATIONS.md` L1.

Writing a control list for a health-data regime from memory, or from a secondary
summary, is exactly the failure the non-negotiables exist to prevent. A plausible
list of HIPAA safeguards is worse than no list, because it will be believed and
acted on, and the consequence of a gap in this particular regime falls on patients.

## What to do when a client names HIPAA

1. Say plainly that this skill has no HIPAA control mapping and why. Do not
   improvise one, and do not paraphrase the Security Rule from memory.
2. Record it in `open-questions.md` with a named owner and a date — the owner being
   whoever will read the Security Rule and produce the mapping.
3. Continue the interview. HIPAA does not block the other thirteen domains, and the
   architecture work is still worth doing.
4. Note in the specification which domains will need revisiting once the mapping
   exists. On current understanding those are data classification in domain 3, audit
   logging in domain 10, and the business-associate-agreement question in domain 14 —
   stated as *where to look*, not as a control list.

`check_compliance.py` exits non-zero when this regime is named, rather than passing
quietly. An empty control list would otherwise render as zero obligations
unaddressed, which reads exactly like a clean bill of health.

## To close this out

Read the Security Rule, populate the `hipaa` entry in
`../../scripts/compliance_controls.json` with obligation, proposed control and
evidence per safeguard, set `"sourced": true`, replace this file with the real
reference, and remove the entry from `LIMITATIONS.md` L1. Bump the minor version:
adding a regime is a new capability.

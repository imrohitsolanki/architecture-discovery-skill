# Compliance references

One file per regime. Read only the ones domain 3 named.

These files carry the reasoning, the applicability question and the traps. The
machine-checkable obligation list lives in `../../scripts/compliance_controls.json`,
which `check_compliance.py` reads — so the two are complementary and neither
duplicates the other. If you change an obligation, change both: a regime in the
JSON with no file here has reasoning nobody can read, and a file here with no JSON
entry is a regime the gate silently ignores.

## The rule that governs all of them

Never write that something is compliant. Write:

- **obligation** — what the instrument requires, cited
- **proposed control** — what this architecture does about it
- **evidence required** — what an assessor would ask to see
- **owner** — the named person who verifies it, who is not you

The skill advises. It does not certify, and it is not qualified to. Where a
determination is needed — whether a regime binds this entity, whether a control is
sufficient — that is a question for the client and, where required, for an auditor or
counsel.

## Applicability is never inferred from a sector

Several of these bind only certain entity classes. The RBI Master Direction is
addressed to a named list of entity types. The SEBI framework sets different
requirements per classification, and the classification decides whether assessment is
third-party or self-assessment. A fintech is not automatically RBI-regulated, and a
company handling payments is not automatically in PCI scope if it never touches a
card number.

So ask, record the answer, and where the client does not know, make it an open
question with a named owner. A guess here propagates into every control below it.

## Three regimes are stubs in this build

HIPAA, ISO/IEC 27001 and SOC 2 have no control list, because their primary texts
could not be read during the build. See `LIMITATIONS.md` L1 and the stub files
themselves. `check_compliance.py` fails rather than passing quietly when one is
named, because an empty control list renders as zero obligations unaddressed — which
reads exactly like a clean bill of health.

If one of them is named: say plainly that this skill cannot produce a control mapping
for it, record it as an open question with an owner, and continue with the rest of the
interview. Do not improvise a control list for a health-data regime or a certification
standard. It will be believed.

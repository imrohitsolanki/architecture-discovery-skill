# Domain 3 — Compliance and data governance

**Blocks a final specification.** A regime discovered after the design is a
redesign: segmentation, key custody and log retention all change the topology.

Nothing here is detectable from a repository. Ask, and never infer applicability
from the client's sector.

## The one thing to get right

You are not determining whether a regime applies. You are asking, recording the
answer, and mapping obligations to proposed controls. Several regimes bind only
certain entity classes — the RBI Master Direction is addressed to a named list of
entity types, and the SEBI framework sets different requirements per classification.
Whether the client falls inside is a question for the client, and where they do not
know it becomes an open question with a named owner, not a guess.

Never write that something is compliant. Write obligation, proposed control, evidence
required, and who verifies. `check_compliance.py` enforces the shape;
`references/compliance/<regime>.md` holds the material per regime.

## Questions

**1. Does the system handle personal data? Whose, and from where?** Location of the
data subject, not of the company, is what generally decides which regime attaches.

**2. Which of these has anyone mentioned?** Read the list — people recognise a name
they would never volunteer.

| Regime | Ask when | Sourced in this build |
|---|---|---|
| India DPDP Act 2023 + Rules 2025 | Personal data of people in India | yes |
| GDPR | Personal data of people in the EU or EEA | yes |
| PCI-DSS v4.0.1 | Card numbers touch any system you build or operate | yes |
| RBI Master Direction (IT Governance) | Bank, NBFC, payments bank, credit information company | yes |
| SEBI CSCRF | A SEBI-regulated entity | yes |
| IFSCA cyber guidelines | A regulated entity in an IFSC, e.g. GIFT City | yes |
| HIPAA | Protected health information in the United States | **stub — see below** |
| ISO/IEC 27001 | Certification is sought or contractually required | **stub** |
| SOC 2 | Customers require a report, common in B2B SaaS | **stub** |

The three stubs have no control list in this build, because their primary texts
could not be read (`LIMITATIONS.md` L1). If one is named, say plainly that this skill
cannot produce a control mapping for it, record it as an open question with an owner,
and continue. Do not improvise one — for a health-data regime or a certification
standard, an invented control list is worse than none, because it will be believed.

**Where it goes:** `regimes_unmapped`, not `regimes`. The same applies to a regime
that is real but has no control file here at all — a national privacy act, a
sector code this build never read. The compliance gate reports everything in
`regimes_unmapped` prominently on every run and does not block on it, provided an
open question names it with an owner and a date. In `regimes` it fails the gate
permanently with no waiver path, and the only way to a green run is deleting a real
obligation from the record, which leaves the generation stage with nothing to
implement for it.

**3. Where must data physically stay?** Distinguish a legal requirement from a
latency preference; they lead to different answers when they conflict. Record which
it is in `residency_is_legal_requirement`: the contradiction gate blocks on an
obligation and only warns on a preference, and an absent flag is read as an
obligation, which is the safe direction.

Record the **country** where the obligation is a country's — `"australia"`,
`"canada"`, `"japan"` — not the continent it sits in. A continent permits every
country in it: `"apac"` allows Singapore, Tokyo and Mumbai, which is not what an
Australian residency contract says. Where the obligation is already written as a
list of regions in a contract, record exactly that list —
`"residency": ["ap-southeast-2", "ap-southeast-4"]` — which needs no geography table
and cannot be misread.

**4. What classes of data are there, and how long must each be kept?** Push for
classes rather than fields: "identity documents", "transaction records", "session
logs". Retention often has a floor from a regulator and a ceiling from a privacy
regime, and those can conflict — surface it rather than picking one.

**5. Who is accountable for this internally?** A named person, for
`open-questions.md`. Every compliance obligation needs an owner who is not you.

## Gating consequences

- **PCI-DSS** opens cardholder-data-environment segmentation in 7, key custody and
  rotation in 8, twelve-month log retention with three months immediately available
  in 10, penetration-test cadence in 11, and change control in 9. Namespace or
  tag-based isolation in domain 5 becomes a contradiction.
- **GDPR or DPDP** opens residency in 4, retention and erasure in 12 including
  backups and logs, data-subject access in 8, and a processor register in 9.
- **RBI, SEBI or IFSCA** opens incident-reporting deadlines — IFSCA is explicit at an
  interim report within 3 days and root-cause analysis within 30 — third-party and
  outsourcing review in 11, and DR drill cadence in 12. Establish the entity
  classification first or no control list means anything.
- **HIPAA** opens PHI classification here, audit logging in 10, and the
  business-associate-agreement question in 14.
- **Any residency obligation** makes region choice in domain 4 a constraint rather
  than a preference, and the contradiction gate will block a mismatch, including on
  the DR region — a disaster-recovery copy is still a copy.

## What to write

```json
"03-compliance": {
  "status": "complete",
  "answers": {
    "regimes": ["dpdp", "pci-dss"],
    "regimes_unmapped": ["soc2"],
    "residency": "india",
    "residency_is_legal_requirement": true,
    "data_classes": [
      {"class": "identity documents", "retention": "7 years", "basis": "RBI KYC"}
    ],
    "accountable_owner": "named person"
  }
}
```

`regimes` must use the slugs from `scripts/compliance_controls.json` —
`dpdp`, `gdpr`, `pci-dss`, `rbi`, `sebi`, `ifsca`, `hipaa`, `iso-27001`, `soc2`.
Common aliases are normalised, but the slugs are what the gate reads. If none apply,
record `"regimes": []` explicitly rather than leaving the domain unanswered, so a
reviewer can see the question was asked.

`regimes_unmapped` takes anything this build cannot map — a stub slug, or a regime's
name written out in full. Every entry needs a matching open question with an owner
and a date, or the gate fails: an unmappable obligation with nobody accountable is a
note, not a deferral.

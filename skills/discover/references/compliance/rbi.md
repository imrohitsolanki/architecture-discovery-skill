# RBI Master Direction on IT Governance, Risk, Controls and Assurance Practices

**Source:** RBI/2023-24/107, dated 7 November 2023 —
<https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12562>

**Obligations:** `../../scripts/compliance_controls.json`, regime `rbi`.

## Who it binds — ask, do not infer

The Master Direction is addressed to a named list of entity types: scheduled
commercial banks excluding regional rural banks, small finance banks, payments banks,
non-banking financial companies, credit information companies, and All India
Financial Institutions (EXIM Bank, NABARD, NaBFID, NHB and SIDBI).

A fintech is not automatically inside. A lending app may be an NBFC, may be a
technology service provider *to* an NBFC, or may be neither — and those three have
very different obligations. Establish which, record it, and where the client does not
know, make it an open question with a named owner. Getting this wrong in either
direction is expensive: assuming it applies gold-plates the build, and assuming it
does not can invalidate the design.

Note that a technology service provider to a regulated entity typically inherits
obligations through the regulated entity's own third-party risk management, so "we
are not regulated" rarely means "none of this matters".

## What actually changes the architecture

**Board-level IT governance.** Roles defined, an IT strategy committee, and a path by
which architecture decisions reach it. For this skill, that means the specification
itself is evidence, and it should be written so somebody non-technical can present it.

**Business continuity and DR with periodic testing.** A DR tier matched to a stated
recovery time and point, with drills at a defined cadence. The word that matters is
*testing*: an untested DR plan does not satisfy this, and "when was the last restore
test" in domain 12 becomes a compliance question rather than only an engineering one.

**Information systems audit as an independent function.** The architectural
consequence is that change records and access records have to be sampleable — an
auditor will ask to see who changed what and who could read what, for a period. That
is a retention and audit-trail decision made in domains 9 and 10.

**Third-party and service-provider risk.** A register of every third party in the data
path, cloud providers included, with a review cadence. Cloud is outsourcing.

**Cyber incident response, reporting and root cause analysis.** A named responder, a
reporting path to the regulator, and root cause analysis as a required step rather
than a good intention.

**Data localisation for payment and customer data.** Primary and DR in Indian
regions, with any processing outside India recorded and justified. The contradiction
gate blocks a non-India region when this regime is named, DR included.

## Traps

- Treating this as a security standard. It is largely a governance and assurance
  instrument, so the deliverables are records, roles and cadences as much as
  controls.
- Confusing it with the payment-data circulars. Localisation for payment system data
  has its own history and its own instruments; if payments are involved, that needs
  checking separately rather than assumed covered here.
- Assuming a managed cloud service removes the outsourcing obligation. It relocates
  the work; the register and the review still exist.

## What to record

Per obligation: control, evidence, owner, and cadence — cadence matters more here than
in most regimes, because much of what is required is periodic rather than static.

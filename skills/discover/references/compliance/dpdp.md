# India DPDP Act 2023, and the DPDP Rules 2025

**Sources:**
- Act (No. 22 of 2023): <https://www.indiacode.nic.in/handle/123456789/22037>
- MeitY text: <https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf>
- Rules 2025: <https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa>

**Obligations:** `../../scripts/compliance_controls.json`, regime `dpdp`.

## Who it binds

Processing of digital personal data of people in India. The Act uses *data fiduciary*
for what GDPR calls a controller, and *data principal* for the individual. Some
obligations attach only to a *significant data fiduciary*, notified as such by the
government — establish whether the client expects to be one, and record the answer
rather than assuming.

## What actually changes the architecture

**Consent, and withdrawal as a first-class path.** Notice and consent per purpose,
with withdrawal handled as an operation the system supports rather than a support
ticket. Architecturally this means a consent record that is versioned and queryable,
and a withdrawal that propagates. Most systems bolt this on and discover the
propagation problem later.

**Transfer restrictions.** The Act permits transfer outside India except to countries
the government restricts by notification. This is a moving list, so the defensible
default is an Indian region for primary and DR, and treating any transfer as a
decision with a recorded basis. The contradiction gate blocks a non-India region when
DPDP is named, including the DR region.

**Erasure once the purpose is served or consent is withdrawn.** Retention per data
class, enforced by lifecycle policy rather than intent. The same backup-and-log
problem as GDPR applies, with the same answer: retention expiry, written down.

**Breach intimation.** To the Data Protection Board and to affected data principals.
Again the architectural requirement is detection that can scope the affected set.

**Grievance redressal.** A published contact route and a tracked queue with a
response target. Cheap to build, routinely forgotten, and visible to anyone looking.

## Interaction with the financial regulators

For a lending, payments or capital-markets client, DPDP will sit alongside RBI, SEBI
or IFSCA obligations, and the retention requirements can conflict: a KYC record with
a seven-year regulatory floor cannot be erased on request. That conflict is real and
it is resolved by the client's counsel, not by this skill. Name it, record both
requirements, and let the owner decide.

## Traps

- Treating DPDP as GDPR with different words. Consent is more central, the transfer
  mechanism is a government list rather than an adequacy-and-safeguards framework,
  and the enforcement body differs.
- Assuming `ap-south-1` settles residency. It settles where the data rests; support
  access, monitoring vendors and backup destinations still need checking.
- Missing that the Rules 2025 fill in much of the operational detail the Act leaves
  open. Read them, not only the Act.

## What to record

Per obligation: control, location, evidence, owner. Plus a data-flow statement and a
retention table by data class, with the basis for each retention period — because the
regulatory floors and the erasure obligation both have to be visible in one place for
the conflict above to be manageable.

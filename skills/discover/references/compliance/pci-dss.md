# PCI DSS v4.0.1

**Sources:**
- Document library: <https://www.pcisecuritystandards.org/document_library/>
- v4.0.1 release note: <https://blog.pcisecuritystandards.org/just-published-pci-dss-v4-0-1>
- Future-dated requirements, mandatory in assessments since 31 March 2025:
  <https://blog.pcisecuritystandards.org/now-is-the-time-for-organizations-to-adopt-the-future-dated-requirements-of-pci-dss-v4-x>

**Obligations:** `../../scripts/compliance_controls.json`, regime `pci-dss`.

## Current version and dates, verified during this build

v4.0.1 is a limited revision published June 2024, providing clarification rather than
new requirements. Of the 64 new requirements in v4, 51 were best practice until 31
March 2025 and have been mandatory in assessments since. v4.0.1 did not move that
date. Three e-commerce requirements in particular — 6.4.3, 11.6.1 and 12.3.1 — became
effective then and catch people out, because they are about the payment page rather
than the backend.

## Who it binds, and the scoping question that decides everything

PCI applies to systems that store, process or transmit cardholder data, **and to
everything connected to them**. That second clause is the whole game.

The first and most valuable question is therefore: **does a card number ever touch
anything we build?** If payment is fully redirected or fully tokenised by a provider
and no card number reaches the client's systems, the scope collapses to the payment
page and the assessment gets dramatically cheaper. That conversation is worth having
before designing anything, because it can remove most of this regime.

If card data does touch the system, the cardholder data environment has to be
segmented so that non-CDE workloads are demonstrably out of scope. Without
segmentation, everything connected is in scope, which means the whole estate.

## What actually changes the architecture

**Segmentation (Requirement 1, and scoping).** Default-deny at the boundary and
between tiers, with a business justification per allowed flow, reviewed at the
required interval. Namespace-level or tag-level isolation does not achieve this — the
contradiction gate treats that combination as an error, because it puts the CDE in
the same blast radius as everything else and thereby widens scope to all of it.

**Key management (Requirements 3 and 12).** Keys in a managed HSM or KMS, split
custody, rotation, and demonstrable absence of key material from application
configuration and container images. The evidence is custody records and rotation
history, so this needs to be a designed process rather than a setting.

**Logging (Requirement 10).** Twelve months retained, three months immediately
available, tamper-evident. This is a real cost line — see domain 10 — and it conflicts
with erasure obligations under GDPR or DPDP if personal data is in those logs. Name
the conflict.

**Vulnerability management and testing (Requirements 6 and 11).** Scanning in the
pipeline with a defined remediation window, plus internal and external penetration
testing. Ask when the last test was; frequently the answer is never.

**Access (Requirements 7 and 8).** Role-based, through an identity provider, MFA
enforced, no shared accounts. An access review with dates is the evidence.

**Payment page integrity (6.4.3 and 11.6.1).** An inventory of every script on the
payment page, each authorised, with integrity checking and change detection on the
page. This exists because of e-skimming, and it is a frontend concern that lands in a
document nobody expects to contain frontend concerns.

## Traps

- Designing for PCI before asking whether card data is in scope at all.
- Assuming a tokenisation provider removes all obligations. It removes most, and
  leaves the payment page requirements.
- Treating segmentation as configured rather than tested. Segmentation testing is
  itself a requirement.
- Serverless container platforms make segmentation evidence harder, since the
  platform owns more of the network. Not disqualifying, and worth knowing before
  choosing in domain 6.

## What to record

Per obligation: control, location, evidence, owner. Plus a network diagram and a
data-flow diagram showing the segmentation boundary — those two are asked for
directly, so produce them as Mermaid in the specification rather than as an
afterthought.

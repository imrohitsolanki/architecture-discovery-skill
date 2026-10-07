# SEBI Cybersecurity and Cyber Resilience Framework (CSCRF)

**Sources:**
- Circular SEBI/HO/ITD-1/ITD_CSC_EXT/P/CIR/2024/113, August 2024 —
  <https://www.sebi.gov.in/legal/circulars/aug-2024/cybersecurity-and-cyber-resilience-framework-cscrf-for-sebi-regulated-entities-res-_85964.html>
- Clarifications, December 2024 —
  <https://www.sebi.gov.in/legal/circulars/dec-2024/clarifications-to-cybersecurity-and-cyber-resilience-framework-cscrf-for-sebi-regulated-entities-res-_90401.html>
- Implementation extension, March 2025 —
  <https://www.sebi.gov.in/legal/circulars/mar-2025/extension-towards-adoption-and-implementation-of-cybersecurity-and-cyber-resilience-framework-cscrf-for-sebi-regulated-entities-res-_93146.html>
- Technical clarifications, August 2025 —
  <https://www.sebi.gov.in/legal/circulars/aug-2025/technical-clarifications-to-cybersecurity-and-cyber-resilience-framework-cscrf-for-sebi-regulated-entities-res-_96329.html>

**Obligations:** `../../scripts/compliance_controls.json`, regime `sebi`.

## Establish the entity classification first

Nothing else in this framework means anything until the classification is known. The
CSCRF sets different requirements for market infrastructure institutions, qualified
regulated entities, mid-size, small-size and self-certification entities — and the
class decides both what is required and how it is assessed.

Two consequences worth stating in the interview:

- Market infrastructure institutions conduct third-party assessment of cyber
  resilience on a half-yearly basis; qualified regulated entities self-assess. Those
  are very different amounts of work and cost.
- Smaller entities can onboard to the Market SOC that SEBI directed NSE and BSE to
  operate, rather than standing up their own security operations capability. That is
  a genuine architectural option and it is frequently unknown to the client.

So the first question is which class, and the second is whether the Market SOC route
is available and wanted.

## What actually changes the architecture

**Two organising ideas.** Cybersecurity across identify, detect, protect, respond and
recover; and cyber resilience across anticipate, withstand, contain and recover. The
useful discipline is mapping each of those to a *specific control in this
architecture* rather than to a policy statement — a mapping to a policy is what makes
a framework feel like paperwork.

**Periodic risk assessment with scenario-based testing.** Internal and external risk,
with the scenarios recorded. The framework also references post-quantum risk
consideration, which for an architecture at discovery stage means noting where
long-lived encrypted data sits rather than changing algorithms today.

**Security operations monitoring.** Either an owned capability or the Market SOC,
with the choice recorded. This connects directly to domain 10's alert-routing and
domain 14's on-call answers — a monitoring obligation with nobody receiving alerts is
not satisfied.

**Assessment cadence.** Per the entity class, and the March 2025 circular extended
the adoption timeline, so check the current deadline rather than assuming.

## Traps

- Producing a control list before establishing the classification. The list will be
  wrong in one direction or the other.
- Reading only the August 2024 circular. Three subsequent instruments clarify and
  extend it, and the technical clarifications in particular change details.
- Treating the resilience goals as synonyms for the security functions. Withstand and
  contain are about operating through an incident, which is a different design
  question from preventing one.

## What to record

The classification and its basis, first. Then per obligation: control, evidence,
owner, cadence, and the assessment method the class requires.

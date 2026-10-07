# GDPR — Regulation (EU) 2016/679

**Source:** consolidated text at <https://eur-lex.europa.eu/eli/reg/2016/679/oj>

**Obligations:** `../../scripts/compliance_controls.json`, regime `gdpr`.

## Who it binds

Processing of personal data of people in the EU or EEA, regardless of where the
processor is established. Location of the data subject decides it, not location of
the company — which is why an Indian company with European customers is in scope and
frequently surprised by it.

Establish whether the client is a controller, a processor, or both. It changes who
owes what, and a client who has not thought about it usually assumes controller
without checking.

## What actually changes the architecture

**Transfers outside the EEA (Chapter V).** This is the one with topology
consequences. Keeping processing and backups in an EEA region avoids the question
entirely; anything else means recording the Article 46 mechanism relied on, per data
flow. Note that a backup or a DR copy outside the EEA is a transfer — this is the
oversight the contradiction gate blocks on.

**Right to erasure (Articles 16-17).** A deletion path that reaches only the primary
database is incomplete. Backups, logs, analytics copies and search indices all hold
personal data. In practice backups are handled by retention expiry rather than by
surgical deletion, and that reasoning needs writing down rather than leaving
implicit, because an assessor will ask.

**Security of processing (Article 32).** Encryption in transit and at rest, least
privilege, and — explicitly — a tested restore. Article 32 names availability
alongside confidentiality, so an untested backup is a security gap and not only an
operational one.

**Breach notification within 72 hours (Articles 33-34).** The architectural
requirement hiding in this is detection that can *scope* what was affected. A system
that can tell you it was breached but not which records were touched cannot support a
72-hour notification. That is a logging and audit-trail decision made in domain 10.

**Processors and sub-processors (Article 28).** Every third party in the data path is
a sub-processor, cloud providers included. The register is the deliverable.

## Traps

- Assuming a European region is sufficient. Support access from outside the EEA, a
  monitoring vendor, or an offsite backup can each constitute a transfer.
- Logging personal data by default. Application logs are the most common place
  personal data ends up somewhere with no deletion path.
- Treating consent as the only lawful basis. It is one of six, and contract or
  legitimate interests is often the better fit — but that determination is the
  client's counsel's, not yours.

## What to record in the specification

Per obligation: the control, where it is implemented, the evidence, and the owner.
For transfers, a data-flow statement showing where each class of personal data rests
and moves — that is the artefact that answers most GDPR questions at once.

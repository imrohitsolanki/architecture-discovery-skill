# Open questions — {{project name}}

Every unresolved item, with a proposed default, a named owner, and the date the
default takes effect if nobody decides.

Two rules this file exists to enforce. An open question with no owner is not a
question anyone will answer. And an open question with no default is a blocker, so
every row has a default even where the default is "we stop and wait".

`check_completeness.py` reports any row missing an owner or a date.

## Blocking

These prevent the specification being finalised. Each sits in a domain that cannot be
defaulted, because a default would be a guess about the business rather than a
technical choice.

| ID | Question | Domain | Proposed default | Owner | Default applies from | Status |
|---|---|---|---|---|---|---|
| OQ-{{n}} | {{}} | {{03-compliance}} | {{}} | {{named person}} | {{YYYY-MM-DD}} | Open |

## Non-blocking

The specification can be finalised with these open. Each will be filled from a
documented default, and the specification records it as a default rather than as a
decision.

| ID | Question | Domain | Proposed default | Owner | Default applies from | Status |
|---|---|---|---|---|---|---|
| OQ-{{n}} | {{}} | {{}} | {{}} | {{}} | {{}} | Open |

## Resolved

Kept rather than deleted, so a reader can see what was asked and what was decided.

| ID | Question | Resolution | Decided by | Date |
|---|---|---|---|---|
| OQ-{{n}} | {{}} | {{}} | {{}} | {{}} |

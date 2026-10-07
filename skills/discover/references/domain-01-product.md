# Domain 1 — Product context

**Blocks a final specification.** Everything downstream hangs off what the thing is
and what an outage costs, and there is no technical default for a business
requirement.

Nothing here is detectable from a repository. Ask all of it.

## What you are trying to leave with

- What it does, in one sentence a stranger would understand.
- Who uses it, and roughly how many, now and in a year.
- What breaks for a customer when it is down, in their words.
- Whether there is a fixed date, and whether date or scope gives way.
- Availability target, recovery time and recovery point — derived by you from the
  above, not asked for as numbers.

## Questions

Five questions, which is the batch limit — the recovery-point and recovery-time pair
is deliberately one item rather than two, because they are confused apart and the
domain would otherwise exceed a single turn. Ask in this order; later ones read the
earlier answers.

**1. What does it do?** One sentence. If the answer runs to a paragraph, the system
probably has more than one job, which matters in domain 2.

**2. Who uses it, and how many?** Ask for both a launch figure and a one-year
figure, and accept a range. Being out by a factor of ten either way is expensive in
opposite directions.

**3. When it is down, what happens to a customer?** Do not ask for a percentage. See
`interview-method.md` worked turn 1 for why: a product manager asked for an
availability figure will produce one chosen to sound serious. Ask what breaks, then
convert:

| What they describe | Reasonable target | What it implies |
|---|---|---|
| "They come back later, mildly annoyed" | 99.5% | Single region, multi-zone, business-hours response is defensible |
| "They cannot complete a purchase" | 99.9% | Multi-zone required, on-call required, roughly 43 minutes of budget a month |
| "Money is in flight and could be lost" | 99.95%+ | Multi-zone plus a DR region, 24x7 response, and a real error budget discipline |
| "A regulator would want to know" | 99.95%+ and evidence | Everything above, plus incident records and reporting deadlines |

Say the target back and confirm it, so it is their number rather than yours.

**4. If we lost the last hour of data, inconvenience or incident? And how long can
it be down before it is a serious problem — an hour, a day?** One question with two
parts, deliberately: these are the recovery point and the recovery time, people
confuse them, and asking together makes the difference concrete. For anything
financial, default to "incident" on the first part and say that this costs real money
in database configuration. For a content site an hour is often genuinely fine, and
saying so saves the budget for somewhere it matters.

**5. Is the launch date fixed?** State the default — date moves, scope does not — and
ask to have it overturned. A genuinely fixed date is a constraint that changes
recommendations toward managed services that stand up in days.

## Gating consequences

Record these; they drive later contradiction checks.

- Availability target 99.9% or higher makes multi-zone the default in domain 4, and
  a single-zone answer in domain 6 becomes a contradiction rather than a preference.
- 99.95% or higher with no DR region is flagged: a regional failure would have no
  answer.
- The recovery time answer sets a floor on the DR tier in domain 12. Four hours
  permits pilot light; fifteen minutes does not, and backup-and-restore is ruled out
  by anything under a day.
- "A regulator would want to know" is a strong hint that domain 3 has a regime in
  it, even if the person has not said so. Ask directly rather than inferring.
- A fixed launch date plus a small team biases domain 6 and domain 9 toward managed
  everything, and that trade should be stated in the specification rather than made
  quietly.

## What to write into the state file

```json
"01-product": {
  "status": "complete",
  "answers": {
    "what_it_does": "one sentence",
    "users": "who they are",
    "scale_launch": "figure or range, with the unit",
    "scale_year_one": "figure or range",
    "downtime_impact": "in their words",
    "sla": "99.9",
    "rto": "4h",
    "rpo": "15m",
    "launch_date": "date or none",
    "date_or_scope_gives": "date | scope"
  }
}
```

Record the availability target as a bare number, since the contradiction gate parses
it. Record recovery time and point with units — `15m`, `4h`, `2 days` all parse.

If scale is unknown, write the assumption you sized against into
`open-questions.md` with an owner, and record it here as an assumption rather than as
an answer. A stated assumption can be argued with; a vague requirement cannot.

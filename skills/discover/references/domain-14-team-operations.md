# Domain 14 — Team and operations

**Blocks a final specification.** Who operates this decides managed versus
self-hosted throughout, and a two-person team and a platform team get different
correct answers to the same question.

This domain is asked last and used everywhere. If its answers never change a
recommendation you made in domains 6, 8, 9 or 10, you are not using it — and the
usual sign of that is a specification that would suit a team three times the size.

## Nothing here is detectable. Ask all of it.

## Questions

**1. How many engineers, and how much of their time is this?** Headcount and
full-time equivalents are different numbers. Four engineers at a quarter of their
time is one engineer, and it is the second number that determines what can be
operated.

**2. Is there anyone whose job is operations or platform?** Not "who is good at
infrastructure" — whose job it is. If nobody's, then every self-hosted component is
work taken from feature delivery, and that trade belongs in the specification rather
than in a surprise three months later.

**3. Who gets called at 2am, and have they agreed to it?** The second half matters.
Options, and each changes the architecture:

| Answer | What it means for the design |
|---|---|
| Nobody | Alerting is a dashboard. Every self-hosted component is a contradiction; managed everything, with failure modes that degrade rather than page. Say this plainly in the specification |
| Business hours only | An availability target of 99.9% or above is not achievable — a Friday-evening failure alone exceeds the annual budget. The gate treats that combination as an error |
| Informal, whoever notices | Works until it does not, and it fails on holiday. Worth naming as a risk with an owner |
| Formal rotation, named people | Self-hosted components become viable. Ask how many people are in it: fewer than four is not a sustainable rotation |
| Follow-the-sun or a third party | Genuine 24x7. Everything is on the table |

**4. What does the team already know?** Existing knowledge is an asset and it should
change the recommendation. A team that has run Postgres for years should probably
keep running it. A team that has never used Kubernetes and has two people should
probably not start with it on a deadline. Ask specifically about Kubernetes,
Terraform, the cloud provider, and the database — those four carry most of the
operational load.

**5. What support hours does the business promise its own customers?** Sometimes
looser than the technical target, occasionally tighter. A mismatch is worth
surfacing: promising customers 24x7 support over a business-hours on-call is a
commitment somebody will have to break.

**6. What runbooks are expected, and who writes them?** "None" is an answer. A
realistic minimum is one page per component covering how to tell it is broken, how to
restart it, and how to restore it. If nobody will write them, prefer managed services
harder, because the vendor's documentation becomes the runbook.

**7. Who signs off on this specification, and who owns each open question?** Every
entry in `open-questions.md` needs a named owner and a date. Without both it is not a
question anyone will answer, and `check_completeness.py` reports entries missing
either.

## How this domain changes the recommendation

State the bias explicitly rather than applying it silently, so the reasoning is
visible in the specification:

- **One or two engineers, no operations role, no pager.** Managed everything.
  Serverless containers over Kubernetes unless something specific requires it.
  Managed database, never an operator. Provider secret store over Vault. Cloud
  monitoring or a hosted stack over self-hosted Prometheus and Loki. GitOps only if
  it replaces work rather than adding it.
- **Three to five engineers, informal on-call.** Managed Kubernetes becomes
  reasonable. Managed database still. Self-hosted observability becomes reasonable if
  one person owns it. Self-hosted Vault does not.
- **Six or more with a real rotation, or a platform person.** Most options open.
  Self-hosted observability, Vault, and a service mesh become defensible. A
  self-managed control plane is still rarely worth it, and the reason is that it buys
  very little for the ongoing cost.
- **On premises, any size.** Add the requirement for somebody who owns hardware,
  firmware, switching and storage, and who can be physically present. This is a
  wider skill mix, not just more hours. If the team cannot cover it, record that as a
  finding rather than working around it.

## Gating consequences

- Self-hosted control plane with three or fewer engineers is an error.
- Self-hosted control plane with nobody on the pager is an error.
- Business-hours-only cover with an availability target of 99.9% or above is an
  error.
- Any self-hosted component with no named owner should be recorded as an open
  question, not assumed.

## What to write

```json
"14-team": {
  "status": "complete",
  "answers": {
    "headcount": 2,
    "fte_on_this": 1.5,
    "ops_role": "none",
    "pager": "nobody",
    "rotation_size": 0,
    "skills": {"kubernetes": "none", "terraform": "some", "aws": "some", "postgres": "good"},
    "business_support_hours": "09:00-18:00 IST weekdays",
    "runbooks": "one page per component, written by the engineer who builds it",
    "spec_signoff": "named person",
    "hiring_planned": "one engineer in six months, not committed"
  }
}
```

`headcount` and `pager` are read by the contradiction gate. Use `nobody`,
`business-hours`, `informal`, `rotation` or `24x7` for `pager` so the checks apply.

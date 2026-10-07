# Domain 13 — Cost

**Blocks a final specification.** Without a ceiling the cost gate has nothing to
check against, so a specification can be affordable or ruinous and read identically.

Read `cost-method.md` before writing any number. The rule that matters: never invent
pricing. Derive a range from stated assumptions, show the arithmetic, or ask.
`check_cost.py` refuses a price with no assumptions attached.

## Pre-filled from the repository

Only one thing: whether a `default_tags` block exists and whether it carries a
`CostCenter` key. `detect_conventions.py` reports the tag keys it finds. Everything
else in this domain is a business answer.

## Questions

**1. What is the monthly ceiling, and is it per environment or in total?** Ask for a
number. "As cheap as possible" is not a ceiling and cannot be checked against — if
that is the answer, propose a figure derived from the topology so far and ask for it
to be confirmed or corrected.

Ask whether the ceiling is a hard limit or a target. That changes what happens on
overage: a hard limit means the topology changes, a target means somebody is told.

**2. Is this operating or capital expenditure?** Cloud is operating. Owned hardware
is capital plus running costs, and the two cannot be compared without amortising the
capital over a stated life. `check_cost.py` handles both; the model goes in
`cost.model` as `cloud` or `on-prem`.

**3. Who is billed, and how is that split?** Tagging and chargeback. If more than one
team or client shares infrastructure, the tag scheme has to carry enough to split the
bill, and retrofitting tags across an estate is unpleasant. The exemplar repository's
scheme — `Project`, `Environment`, `ManagedBy`, `Provisioner`, `CostCenter`, `Repo` —
is a reasonable starting point, and `CostCenter` is the one that does the work.

**4. Are there budget guardrails, and what do they do?** A budget alert that emails
somebody is different from one that stops provisioning. Options: provider budgets
with alerts, Infracost on pull requests to show the cost of a change before merge,
Cloud Custodian to clean up untagged or idle resources. Ask what should happen at
eighty per cent of the ceiling.

**5. Commitment discounts — but not yet.** Savings Plans, reserved instances and
committed-use discounts give roughly twenty to forty per cent off the committed
portion in exchange for a one- to three-year commitment. The right answer at
discovery is almost always "not yet": commit to the steady-state floor once it is
known, not to a forecast. Record it as a decision to revisit at a named point.

## FinOps tooling

| Option | When it wins | Trade-off |
|---|---|---|
| Provider cost explorer and budgets | Always. Free, already there | Coarse; attribution depends entirely on tagging discipline |
| Infracost | Shows the cost delta of an infrastructure pull request before merge | Estimates from list prices, so it will not match the bill exactly. Still the highest-value item here |
| OpenCost | Kubernetes cost allocation by namespace and workload, CNCF, free | Kubernetes only; needs accurate resource requests to attribute well |
| Kubecost | OpenCost with a commercial tier and more features | Cost above the free tier |
| Cloud Custodian | Finds and can remediate waste — untagged, idle, oversized | Remediation needs care; a rule that deletes can delete the wrong thing |
| Komiser | Multi-cloud inventory and cost visibility | Another service to run |
| Vantage and similar | Good reporting with little setup | Commercial, and it needs billing access |

Default at discovery: provider budgets plus Infracost on infrastructure pull
requests. Add OpenCost once Kubernetes cost attribution is actually being asked
about.

## Where the money usually goes

Useful for sanity-checking an estimate. Typical rather than authoritative — verify
against the provider's calculator:

- **Compute** is the largest line for most workloads, and the one most affected by
  spot usage and by shutting non-production down.
- **Observability** is often second and almost always underestimated. Retention and
  cardinality are the multipliers.
- **Data transfer** is the line people forget. Cross-zone traffic, NAT gateway
  processing and egress to the internet all charge, and a chatty service mesh across
  zones can cost more than the compute it connects.
- **Managed database** is expensive per unit and worth it. Multi-AZ roughly doubles
  it.
- **Control planes and fixed charges** are brutal at small scale: a per-cluster
  charge across three environments is three charges regardless of load.
- **Idle non-production** is the easiest saving and the one nobody makes.

## Reductions, in the order worth offering

`check_cost.py` generates these from what the interview recorded, so they arrive
specific rather than generic. In rough order of saving per unit of pain:

1. Shut non-production down outside working hours. A twelve-hour weekday schedule
   removes about sixty-five per cent of the hours.
2. Spot or preemptible capacity for non-production. Sixty to seventy per cent off
   that compute. Never production.
3. Share one cluster across non-production environments with namespace separation,
   keeping production separate. Removes a control-plane charge and a node floor per
   environment. Not available where a regime requires segmentation.
4. Single availability zone outside production. Removes cross-zone transfer and a
   duplicate node floor.
5. Reduce observability retention and drop high-cardinality labels. Check the
   compliance floor first.
6. Step the DR tier down, if the recovery target permits it. Re-run the contradiction
   gate afterwards.
7. Commitment discounts on the steady-state floor, once it is known.

## Gating consequences

- A ceiling under 1,500 with two or more structural cost drivers — Kubernetes, three
  or more persistent environments, three-zone spread, a warm or active DR posture —
  is a contradiction the gate raises as an error rather than a warning.
- A ceiling under 4,000 with three or more drivers is a warning.
- An empty estimate with this domain marked complete is a failure: a specification
  with no costing that looks costed is worse than one that admits it.
- On premises, the reduction levers change entirely — there is no spot market, and
  the main lever is the amortisation period.

## What to write

```json
"13-cost": {
  "status": "complete",
  "answers": {
    "ceiling": 6000,
    "currency": "USD",
    "period": "monthly",
    "ceiling_scope": "total across all environments",
    "ceiling_is_hard": false,
    "model": "cloud",
    "tagging": ["Project", "Environment", "ManagedBy", "CostCenter", "Repo"],
    "chargeback": "single client, no split needed",
    "guardrails": "provider budget alert at 80%, Infracost on infra PRs",
    "commitments": "none yet; revisit after three months of steady state"
  }
}
```

The estimate itself goes in the top-level `cost` object, not here — see
`cost-method.md` for the line-item shape and the two models.

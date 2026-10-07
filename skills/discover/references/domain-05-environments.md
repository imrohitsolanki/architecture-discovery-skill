# Domain 5 — Environment topology

**Does not block.** The default is production plus one pre-production environment,
which is right far more often than it is chosen deliberately.

## Pre-filled from the repository

`detect_conventions.py` reports directories that look like environment units —
`env/*`, `environments/*`, `live/*`, and top-level names like `prod` or `staging`. On
the exemplar repository that correctly yielded exactly one environment, `prod`,
which was a deliberate client decision rather than an omission. Confirm; do not
assume a missing staging environment is a gap.

## Questions

**1. Which environments, and is each one always on?**

| Option | When it wins | Trade-off |
|---|---|---|
| Production only | Genuinely small scope, or a deliberate decision with compensating discipline | Every change is tested in production. Raises the bar on plan review and rollback rather than lowering it |
| Production plus staging | The common default | One more environment to pay for and keep in step. Staging drifts from production unless it is built from the same code |
| Development, staging, production | Several engineers, or a release process with sign-off | Three of everything. This is where cost surprises come from |
| Ephemeral per pull request | Fast feedback, good isolation | Needs the whole stack to stand up from nothing, which is real work and worth it only if it will be used |

Ask specifically whether pre-production must resemble production. "Yes" is expensive
and sometimes required by a regime. "No" is cheaper and needs saying out loud, so
nobody is surprised when a load test in staging means nothing.

**2. How are environments separated?**

| Option | When it wins | Trade-off |
|---|---|---|
| Separate account, project or subscription | Real isolation, separable billing | Cross-account plumbing, more setup |
| Separate VPC or network, same account | Reasonable middle ground | IAM is now the boundary that matters, and IAM mistakes cross it |
| Separate cluster, shared network | Kubernetes-heavy estates | Control-plane cost per environment |
| Namespace within one cluster | Cheapest by a distance | Shared control plane, shared nodes, shared failure domain. Not acceptable where a regime requires segmentation |
| Tags only | Almost never | Not a boundary. Record it as a waiver if chosen |

With PCI-DSS named in domain 3, namespace or tag isolation is a contradiction rather
than a trade-off, and the gate treats it as an error.

**3. What is shared across environments?** State management, DNS zones, the artifact
registry, the identity provider, observability. Sharing is usually right and
occasionally the single point of failure nobody drew on the diagram. Whatever is
shared belongs on the topology diagram explicitly.

**4. How does a change get from one to the next?** This is the promotion model, and
it belongs on the promotion diagram: same artifact promoted, or rebuilt per
environment. Same artifact is strongly preferred — rebuilding per environment means
what you tested is not what you shipped.

## Gating consequences

- Three or more persistent environments is a cost driver the contradiction gate
  counts against the ceiling in domain 13.
- More than one environment in a single account opens isolation-by-VPC-and-IAM, and
  the blast-radius trade-off has to be stated in the specification rather than
  implied.
- Namespace or tag isolation with PCI-DSS is an error.
- Ephemeral environments open cost-per-environment and teardown-reliability
  questions in 13 and 9. An ephemeral environment that fails to tear down is a
  recurring bill nobody notices.
- On owned hardware, isolation becomes physical or VLAN-based, and the account-model
  question does not apply at all.

## What to write

```json
"05-environments": {
  "status": "complete",
  "answers": {
    "environments": ["staging", "prod"],
    "ephemeral": "none | per-pr",
    "isolation": "account | vpc | cluster | namespace | tag | physical",
    "prod_like_preprod": false,
    "shared": ["dns", "registry", "idp"],
    "promotion": "same-artifact | rebuild"
  }
}
```

`environments` is counted by the contradiction gate, and `isolation` is read by the
PCI check, so use the values above rather than prose.

# Domain 9 — Delivery

**Does not block.** Defaults exist: build in CI on the repository's own platform,
push a signed image to the provider's registry, promote the same artifact between
environments.

Two files. This one covers continuous integration, continuous delivery and GitOps,
artifact registries, and supply chain. Infrastructure as code, manifest templating
and policy as code are in `domain-09a-iac-and-policy.md`, because six categories in
one file passes the point where a reference should be split.

## Pre-filled from the repository

`detect_conventions.py` reports CI configuration by file, Argo CD or Flux, Helm and
Kustomize, `Taskfile.yml` or a `Makefile`, TFLint, terraform-docs, and pre-commit. It
also reports when the helm Terraform provider is configured, which means add-ons are
applied by the IaC tool rather than by a GitOps controller — a real architectural
choice that is easy to misread.

Absence matters here. No CI configuration at all is worth asking about directly:
something is building this today, and finding out what is more useful than proposing
a replacement.

## Questions

**1. Where does the code live, and what runs on a push?** Usually settled by the
platform already in use.

| Option | When it wins | Trade-off |
|---|---|---|
| GitHub Actions | Code is on GitHub; largest action ecosystem | Minutes cost at scale; self-hosted runners are their own operational surface |
| GitLab CI | Code is on GitLab; integrated registry and environments | Runner management; YAML grows unwieldy on large pipelines |
| Bitbucket Pipelines | Code is on Bitbucket | Smallest ecosystem of the three; fewer prebuilt steps |
| Azure Pipelines | Microsoft estate | Verbose configuration |
| Jenkins | Deep existing investment, unusual requirements | A platform you operate, and plugin drift is a genuine long-term cost |
| Tekton, Argo Workflows | Kubernetes-native pipelines, wants CI on the cluster | You now run CI as a workload, with its own scaling and failure modes |
| Woodpecker, Drone | Lightweight self-hosted | Small community |
| Buildkite, CircleCI | Commercial, good scaling and developer experience | Per-seat or per-minute cost; another vendor |

Default: whatever the code host provides. A separate CI system is a real cost and
needs a reason.

**2. How does a change reach a cluster?**

| Option | When it wins | Trade-off |
|---|---|---|
| Argo CD | Wants GitOps with a UI, multi-cluster, and clear drift visibility | A component to run and upgrade; the UI needs its own access control |
| Flux CD | Wants GitOps with no UI and a smaller footprint | No UI, which some teams miss more than they expect |
| Push from CI (kubectl or helm in the pipeline) | Simplest; nothing extra to run | CI holds cluster credentials, drift is invisible, and there is no reconciliation |
| Terraform helm provider | Add-ons managed with the rest of the infrastructure, one apply | Application deploys become infrastructure applies, which couples release cadence to infrastructure change |
| Argo Rollouts, Flagger | Progressive delivery — canary and blue-green with automated analysis | Needs metrics good enough to make an automated decision, which most teams do not have at first |
| Kargo | Promotion between environments as a managed process | Young; another component |
| Spinnaker | Named so it can be rejected | Very heavy for the value in most projects |

State the trade-off honestly: GitOps gives reconciliation and drift detection at the
cost of a component to run; pushing from CI is simpler and gives neither. Both are
defensible, and the exemplar repository for this skill deliberately runs no GitOps
controller.

**3. Where do artifacts go?**

| Option | When it wins | Trade-off |
|---|---|---|
| Provider registry — ECR, Artifact Registry, ACR | Same account and region as the workload; nodes need only a pull policy | Provider-specific; cross-provider pulls cost egress |
| GitHub or GitLab registry | Already there, one fewer system | Rate limits and egress on heavy pulls |
| Harbor | Self-hosted, wants replication, scanning and signing in one place | You operate it, and it needs storage |
| Zot | Minimal OCI registry, low footprint | Fewer features |
| Nexus, Artifactory | Many artifact types, existing investment | Artifactory licensing is significant |

**4. Promotion model.** Same artifact promoted, or rebuilt per environment. Same
artifact is strongly preferred: rebuilding means what you tested is not what you
shipped. If configuration differs per environment, it is injected at deploy time
rather than baked into the image.

**5. Release strategy.** Rolling, blue-green, canary, or a maintenance window. Ask
what a rollback looks like and how long it takes — that answer is more useful than
the strategy name, and it is frequently "we have not tried".

**6. Supply chain.** How much of this applies depends on the regime and the appetite.

| Option | What it gives | Trade-off |
|---|---|---|
| Sigstore cosign | Image signing and verification, keyless with OIDC | Verification must be enforced at admission or signing is decoration |
| SLSA provenance | Attestation of how the artifact was built | Level 1 is nearly free; higher levels need a hardened builder |
| Syft with Grype, or Trivy | SBOM generation and vulnerability scanning | An SBOM nobody queries is a file. Decide who consumes it |
| Notation | Signing under the CNCF Notary v2 model | Smaller adoption than cosign |
| Dependency-Track | Continuous SBOM monitoring | A service to run |

Ask the question that decides it: **is anything verified before it runs?** An
unenforced signature is a false sense of security, and enforcement lives in domain
11's admission policy.

## Gating consequences

- PCI-DSS opens change control here: who authorises a production change, and where
  the record of that authorisation lives.
- RBI, SEBI or IFSCA open the third-party register — every service in the delivery
  path is a third party, cloud CI included.
- GDPR or DPDP add the processor register, which covers the same ground from a
  different angle.
- Functions from domain 6 change this domain rather than closing it: packaging and
  promotion still exist, but there is no image to sign in the usual sense.

## What to write

```json
"09-delivery": {
  "status": "complete",
  "answers": {
    "scm": "GitHub",
    "ci": "GitHub Actions",
    "cd": "Argo CD",
    "registry": "ECR",
    "promotion": "same-artifact",
    "release_strategy": "rolling",
    "rollback": "helm rollback, tested, about 3 minutes",
    "signing": "cosign keyless, verified at admission by Kyverno",
    "sbom": "Trivy in CI, stored as a build artifact",
    "change_control": "PR approval by a second engineer, recorded in the PR"
  }
}
```

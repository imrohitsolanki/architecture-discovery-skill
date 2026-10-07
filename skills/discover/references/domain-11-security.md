# Domain 11 — Security posture

**Does not block.** Secure defaults cover the baseline. This domain decides how much
beyond the baseline, and who does the work.

Scale the answer to the team. A two-person team with six security tools installed and
nobody reading the output is worse off than the same team with two tools and a habit
of acting on them. Ask who reads the findings before recommending a scanner.

## Pre-filled from the repository

`detect_conventions.py` reports gitleaks and Trivy configuration, Kyverno or
Gatekeeper, Falco or Tetragon, and NetworkPolicy manifests. It reports absence of an
admission policy engine and of secret scanning as gaps worth raising regardless of
what the interview decides.

## Threat modelling depth

Ask, and accept a small answer:

| Option | When it wins | Trade-off |
|---|---|---|
| None, rely on secure defaults | Genuinely low-risk internal tooling | You will not notice the risk specific to this system |
| One session, listing what an attacker would want and how they would reach it | Almost every project. A couple of hours, high return | Not a substitute for review as the system changes |
| Structured, e.g. STRIDE per component | Regulated, or handling money or health data | Real time investment; needs someone who has done it |
| Third-party assessment | A regulator or customer requires it | Cost and scheduling |

Default: one session, with the output recorded as a short section in the
specification rather than a separate document nobody opens.

## Image and dependency scanning

| Option | When it wins | Trade-off |
|---|---|---|
| Trivy | One tool covering images, filesystems, IaC and secrets; easy to adopt | Noisy without a policy on what to fail on |
| Grype with Syft | Good SBOM-first workflow | Two tools |
| Clair | Registry-integrated (Harbor uses it) | Less useful standalone |
| Dependabot or Renovate | Dependency updates as pull requests, which is the fix rather than the finding | Pull-request volume needs managing; Renovate is more configurable |
| Snyk | Good developer experience, broad language support | Commercial, per-seat |

The deciding question: **what happens when a scan finds a critical vulnerability with
no fix available?** If the answer is "the build fails and we override it", say so and
set the policy deliberately — an override that happens every day is not a control.

## Runtime security

| Option | When it wins | Trade-off |
|---|---|---|
| None | Small team, no regulatory driver | You learn about a compromise from its effects |
| Falco | The established open-source choice, large rule ecosystem | Rule tuning is real work; noisy out of the box |
| Tetragon | eBPF-based, low overhead, can enforce as well as observe | Younger; Cilium-adjacent |
| Tracee | eBPF-based alternative | Smaller community |
| KubeArmor | Policy enforcement at runtime | Smaller ecosystem |
| Sysdig, commercial | Managed rules and support | Cost |

Default: none at launch unless a regime asks for it, and say why. Runtime security
generates alerts, and an alert with no responder is a cost with no benefit.

## Cloud posture

| Option | When it wins | Trade-off |
|---|---|---|
| Prowler | Broad open-source assessment against CIS and other benchmarks | Point-in-time unless scheduled |
| Cloud Custodian | Policy plus remediation — can fix, not just report | Remediation needs care; a rule that deletes is a rule that can delete the wrong thing |
| Steampipe with Powerpipe | Query cloud state with SQL; excellent for ad-hoc questions | Not a monitor by itself |
| CloudQuery | Cloud state into a database for analysis | Infrastructure to run |
| Security Hub, Security Command Center, Defender for Cloud | Provider-native, continuous | Per-resource cost; findings volume needs triage |

The CIS Foundations Benchmark for the chosen provider is the reasonable baseline to
assess against, and the CIS Kubernetes Benchmark for the cluster.

## Workload hardening

Mostly free, so there is little reason not to:

- **Pod Security Admission** at `restricted` where workloads tolerate it. Built in,
  nothing to operate.
- **Non-root containers, read-only root filesystem, dropped capabilities.** Set at
  the start; retrofitting is unpleasant.
- **seccomp** — `RuntimeDefault` is a one-line change with real value.
- **Resource requests and limits** on everything. Absent limits are a stability
  problem before they are a security one, and the exemplar repository had none.

## Backup, restore and penetration testing

- Backup belongs to domain 12, but the **restore test** is a security control as much
  as an availability one, because a compromise that requires restoring from before
  the compromise is the case where it matters.
- **Penetration test cadence.** Annually and after significant change is the common
  expectation, and PCI-DSS is explicit about it. Ask who, and when the last one was.

## Gating consequences

- PCI-DSS requires internal and external penetration testing, scanning in the
  pipeline with a remediation window, and evidence that policy is enforced rather
  than observed.
- SEBI requires periodic risk assessment including scenario-based testing, and a
  monitoring capability which for smaller entities may be the market SOC.
- IFSCA requires third-party review on a risk basis and staff training with records.
- RBI requires an information systems audit function able to sample change and
  access records.
- Nobody on the pager from domain 14 means every tool that generates alerts should be
  reconsidered, and that reasoning belongs in the specification.

## What to write

```json
"11-security": {
  "status": "complete",
  "answers": {
    "threat_model": "one session, recorded in the spec",
    "image_scanning": "Trivy in CI, fails on critical with a fix available",
    "dependency_updates": "Renovate, grouped weekly",
    "runtime_security": "none at launch, reconsider once on-call exists",
    "cspm": "Prowler quarterly against CIS AWS Foundations",
    "admission_policy": "Pod Security Admission restricted plus Kyverno",
    "workload_hardening": "non-root, read-only root fs, seccomp RuntimeDefault, limits on all workloads",
    "pen_test": "annual and after significant change; none yet",
    "secret_scanning": "gitleaks in pre-commit and CI"
  }
}
```

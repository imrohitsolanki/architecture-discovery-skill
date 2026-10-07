# Domain 9a — Infrastructure as code, templating and policy

The second half of domain 9. Read this alongside `domain-09-delivery.md`.

## Pre-filled from the repository

This is the domain detection speaks to most confidently, because the evidence is
unambiguous: `root.hcl`, `terragrunt.hcl`, `*.tf`, `cdk.json`, `Pulumi.yaml`,
`*.bicep`, `Chart.yaml`, `kustomization.yaml`, `.tflint.hcl`, `.terraform-version`.
If a repository already has an IaC tool, that decision is made — the useful question
is whether its conventions are documented, and where they are not, name them in the
specification so they become explicit.

## Infrastructure as code

| Option | When it wins | Trade-off |
|---|---|---|
| Terraform | Largest provider ecosystem, largest hiring pool | The BUSL licence change is a real consideration for some organisations; state management is yours to run |
| OpenTofu | Wants Terraform without the licence question; a drop-in fork | Younger; provider and module compatibility is good but worth verifying for anything unusual |
| Terragrunt | Wrapper over Terraform or OpenTofu for DRY backends, provider generation and dependency ordering | Another layer to learn, and its own version to pin. Earns its place once there is more than one unit |
| AWS CloudFormation | AWS-only, no state file to manage, native drift detection | Verbose; slower to gain support for new services than Terraform |
| AWS CDK | Prefers a programming language to a DSL | Synthesises CloudFormation, so you debug two layers. Abstractions can hide what is actually created |
| Pulumi | Real programming language, multi-cloud | Smaller community; a managed backend unless self-hosted |
| Azure Bicep | Azure-only, much cleaner than ARM templates | Azure-only |
| Google Config Connector | Manages GCP resources as Kubernetes objects | Ties infrastructure lifecycle to a cluster's health |
| Crossplane | Infrastructure through the Kubernetes API, wants a platform-team abstraction | Substantial concept load; the cluster becomes a dependency for provisioning |
| Ansible | Configuration management, or provisioning where no declarative provider exists | Not declarative in the same sense; drift handling is weaker |

Default: whatever the repository uses. Where nothing exists and the target is a
single cloud, Terraform or OpenTofu with Terragrunt once there is more than one unit.

Ask about **state**: where it lives, whether it is locked, and who can read it. State
contains secrets in plain form more often than people expect, so read access to the
state bucket is production read access. Object storage with versioning, encryption
and native locking is the current default; a DynamoDB lock table is no longer needed
on Terraform 1.10 and later.

Ask about **version pinning**. Provider and module versions pinned, and the tool
version pinned in a file — `.terraform-version`, `.terragrunt-version`. Unpinned
versions mean the build changes under you.

## Manifest templating

| Option | When it wins | Trade-off |
|---|---|---|
| Helm | Charts exist for nearly everything; the de facto packaging format | Go templating over YAML is unpleasant at scale; `helm rollback` is genuinely useful |
| Kustomize | Wants overlays without templating; built into kubectl | Patch semantics get hard to follow with deep overlay chains |
| Helmfile | Declarative management of many Helm releases | Another layer |
| Timoni | CUE-based, real schema validation | Young, small community |
| jsonnet with Tanka | Wants a real language with strong composition | Steep learning curve; few people know jsonnet |

A common and defensible answer: Helm for third-party charts, Kustomize for your own
manifests.

## Policy as code

Two distinct places policy runs, and conflating them is a frequent mistake.

**Before apply, on the definition:**

| Option | When it wins | Trade-off |
|---|---|---|
| Checkov | Broad IaC coverage, good defaults | Noisy at first; needs a suppression discipline |
| tfsec | Terraform-focused, fast | Now largely folded into Trivy |
| Trivy config scanning | Already using Trivy for images, wants one tool | Less IaC-specific depth than Checkov |
| Terrascan | Alternative with policy-as-code in Rego | Smaller community |
| Conftest with Rego | Wants to write custom policy over any structured file | You write Rego, which is a skill to acquire |

**At admission, on the cluster:**

| Option | When it wins | Trade-off |
|---|---|---|
| Kyverno | Policy in YAML; no new language; can mutate and generate | Kubernetes-only |
| OPA Gatekeeper | Rego, so policy is portable to other Rego consumers | Rego is a real learning curve |
| Kubewarden | Policies as WebAssembly modules, many languages | Younger, smaller ecosystem |
| Pod Security Admission | Built in, no component to run, covers the common cases | Only pod-security concerns; three fixed levels |

Start with Pod Security Admission at `restricted` where workloads tolerate it: it is
built in, has nothing to operate, and covers most of what a first policy engine gets
used for. Add Kyverno or Gatekeeper when there is a specific rule beyond pod
security — signature verification at admission being the usual one.

Ask the question that makes any of this matter: **does a policy failure block, or
warn?** A policy engine in audit mode forever is documentation, not enforcement.
Recording that honestly is more useful than a policy set nobody enforces.

## Gating consequences

- PCI-DSS wants change control and evidence that policy is enforced rather than
  observed.
- Cosign signing from `domain-09-delivery.md` only means something if verification is
  enforced at admission, which is a decision that lives here.
- On premises, Crossplane and cloud-native IaC providers are largely irrelevant, and
  Ansible's weight in the answer goes up considerably.

## What to write

Extend the `09-delivery` answers rather than creating a separate domain. Two of these
keys are read by name, by the generation skill rather than by a gate here: `iac`
decides whether the stack is Terraform, OpenTofu or Terragrunt, and `policy_pre_apply`
decides which scanner `check_iac.py` runs. Under any other name the generation gate
reports that the specification named no scanner at all, which is a sentence about a
decision nobody made.

```json
"09-delivery": {
  "answers": {
    "iac": "Terraform with Terragrunt",
    "iac_state": "S3 with versioning, encryption and native locking; read access limited to CI and two engineers",
    "iac_pinning": ".terraform-version and .terragrunt-version committed; providers pinned",
    "templating": "Helm for third-party charts, Kustomize for our manifests",
    "policy_pre_apply": "Checkov in CI, blocking",
    "policy_admission": "Pod Security Admission restricted, plus Kyverno for signature verification",
    "policy_mode": "blocking"
  }
}
```

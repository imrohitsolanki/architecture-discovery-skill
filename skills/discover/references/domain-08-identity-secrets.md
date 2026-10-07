# Domain 8 — Identity and secrets

**Does not block.** Secure defaults cover it: no long-lived static credentials,
workload identity federated to the platform, secrets in a managed store, least
privilege.

This is the domain where a default is most often silently violated. A CI pipeline
with a stored access key is the single most common finding in a real estate, and it
is usually nobody's decision — it is what happened while everyone was busy.

## Pre-filled from the repository

`detect_conventions.py` reports Vault, External Secrets Operator, Sealed Secrets,
SOPS, AWS Secrets Manager, IRSA or web-identity role assumption, SPIFFE and SPIRE,
Keycloak, and cert-manager. Absence is reported too, and an absent secrets backend is
the question worth asking first.

## Questions

**1. Who are the humans, and where do their identities live?**

| Option | When it wins | Trade-off |
|---|---|---|
| Existing IdP — Okta, Entra ID, Google Workspace | It already exists, which is nearly always | Licensing per seat; federation setup is a one-off cost |
| AWS IAM Identity Center | AWS-only estate, no separate IdP | AWS-centric; awkward if other systems need the same identities |
| Keycloak | Self-hosted, no per-seat cost, full control | You operate an identity provider, and it is on the critical path for logging in |
| Authentik, Zitadel | Lighter self-hosted alternatives, better ergonomics than Keycloak | Smaller communities |
| Dex | A thin federating layer in front of something else | Not a user store; needs a backing IdP |

Default: whatever exists. Introducing an IdP for one project is rarely the right
call, and self-hosting one puts your ability to log in behind your ability to keep it
running.

**2. How do workloads authenticate — and there must be no static keys.**

| Option | When it wins | Trade-off |
|---|---|---|
| IRSA or EKS Pod Identity | AWS Kubernetes | AWS-specific |
| GCP Workload Identity | GKE | GCP-specific |
| Azure Workload Identity | AKS | Azure-specific |
| SPIFFE and SPIRE | On premises, multi-cloud, or workloads outside Kubernetes | You run SPIRE, and it is on the critical path for workloads starting |
| OIDC federation from CI | CI authenticating to a cloud provider with no stored key | Needs the trust policy scoped to the repository and branch, or any repository can assume the role |
| Static access key | Never, without a waiver | Cannot be rotated without coordination, is copied, and leaks. If it must exist, the waiver names who accepted it and when it will be removed |

On owned hardware there is no IRSA and no Workload Identity, which moves SPIFFE and
SPIRE from an option to the likely answer.

**3. Where do secrets live, and how do they reach a workload?**

| Option | When it wins | Trade-off |
|---|---|---|
| Cloud-native store — Secrets Manager, Secret Manager, Key Vault | Already on the provider; least to operate | Per-secret cost; provider-specific API |
| HashiCorp Vault, or OpenBao | Dynamic credentials, PKI, multi-cloud, strong audit | The most capable and the most operational weight. Unsealing is a real procedure people forget until an outage |
| External Secrets Operator | Wants Kubernetes-native syncing from a cloud store | A controller to run; secrets end up as Kubernetes Secrets, which are base64 rather than encrypted at rest unless configured |
| Secrets Store CSI driver | Mounts secrets as files without creating Kubernetes Secrets | Volume mount semantics; not all applications read files |
| Sealed Secrets | Wants encrypted secrets committed to git | Rotating the controller key re-encrypts everything; not suited to dynamic secrets |
| SOPS with age or KMS | GitOps, few secrets, simple model | Manual rotation; decryption keys still need distributing |
| Infisical, Doppler | Good developer experience | Commercial tiers; another vendor in the critical path |

Ask specifically: **who can read a production secret, and would anyone know if they
did?** The answer is often nobody and no, and it is worth writing down.

**4. Rotation.** For each class of secret, what rotates it and how often. "Manually,
when someone remembers" is an answer, and recording it honestly is more useful than a
policy nobody follows. Dynamic credentials from Vault remove the question, at the
cost of running Vault.

**5. Internal PKI and certificates.**

| Option | When it wins | Trade-off |
|---|---|---|
| cert-manager with ACME (Let's Encrypt) | Public TLS on Kubernetes | Rate limits; needs DNS or HTTP validation to work reliably |
| ACM or the provider's certificate service | Provider load balancers | Certificates cannot leave the provider |
| step-ca | Internal certificate authority, short-lived certificates | You run a CA, and CA key custody is a serious responsibility |
| Vault PKI | Already running Vault | Same |
| Manual certificates | Never deliberately | Expiry is the outage. If it exists, put the expiry date in the specification |

On owned hardware there is no ACM, so internal PKI stops being optional.

**6. RBAC model.** Who can do what in the cluster and in the cloud account. Ask for
roles rather than people — "engineers", "on-call", "CI", "read-only auditor" — and
whether production access is standing or requested. Standing production write access
for everyone is common and worth naming as a deviation.

## Gating consequences

- PCI-DSS opens key custody: keys in a managed HSM or KMS, split custody, rotation,
  and proof no key material appears in configuration or images.
- GDPR or DPDP opens data-subject access — which humans and services can read
  personal data, and how that is evidenced.
- A static credential recorded anywhere is a secure-default deviation that requires a
  waiver, and the contradiction gate treats its absence as an error.
- HIPAA opens the business-associate-agreement question, which lands in domain 14.
- On premises: no IRSA, no ACM, so SPIFFE/SPIRE and an internal CA become the path.

## What to write

```json
"08-identity": {
  "status": "complete",
  "answers": {
    "idp": "Google Workspace, federated",
    "workload_identity": "IRSA",
    "ci_auth": "OIDC federation, no stored keys",
    "secrets_backend": "AWS Secrets Manager with External Secrets Operator",
    "secret_rotation": "database credentials 90 days automated; API keys manual",
    "pki": "cert-manager with ACME for public, no internal CA",
    "rbac_roles": ["engineer", "on-call", "ci", "auditor-readonly"],
    "prod_access": "requested | standing"
  }
}
```

Avoid writing the phrases `static credential`, `long-lived key`, `publicly
accessible` or `0.0.0.0/0` here unless a matching waiver exists — the contradiction
gate scans every answer for them and will block, which is the intended behaviour.

# Secure defaults, and what a waiver has to contain

Read this when a deviation is proposed, or when you are unsure whether something is a
default worth defending.

These are the starting point, not an upsell. They are not presented to the client as
options with a cost, because the cost of the alternative is higher and usually
deferred onto somebody else. What *is* presented is any deviation, and it is presented
as a decision with a name on it.

## The defaults, and why each one

### Data stores are not reachable from the internet

Put them in a subnet tier with no route to a NAT gateway, so it is structural rather
than a promise. The reason to make it structural is that every security-group rule is
one mistake away from being wrong, and a subnet with no route out cannot be
misconfigured into reachability by a single change.

The common deviation is an analytics database reachable from an office IP range, for
a tool that cannot go through a bastion. That is sometimes the right call. It is a
waiver.

### Private subnets for compute; public subnets hold load balancers only

A workload with a public IP has an attack surface for no benefit, since traffic
should arrive through something that terminates TLS and can be rate-limited. The
exception people reach for is egress, and the answer to egress is a NAT gateway or an
egress proxy rather than a public IP.

### Least privilege, and no standing production write access

Two parts, and the second is the one that gets skipped. Roles scoped to what they do
is understood; production write access being requested rather than standing is
usually not, because it is inconvenient. Standing write access for everyone is common
and worth naming as a deviation even when it is accepted, because naming it is what
makes it a choice.

### No long-lived static credentials

Workload identity federated to the platform — IRSA, Workload Identity, SPIFFE — and
OIDC federation from CI. The reason is that a static key cannot be rotated without
coordination, so it does not get rotated; it gets copied into a second place for
convenience; and it leaks from one of those places eventually.

This is the default violated most often, and usually by nobody's decision — it is
what happened while everyone was busy. Where one must exist, the waiver names who
accepted it *and when it will be removed*, because a waiver with no end date is a
permanent exception written down.

### Encryption in transit and at rest

At rest is nearly free on every managed service and there is no argument for
disabling it. In transit inside a cluster is the one that gets debated, and the honest
position is that it matters most where the network is shared or where a regime asks
for it. Terminating TLS at the load balancer and running plaintext inside is a common
and defensible posture — and it is a deviation from this default, so say it explicitly
rather than letting it be assumed.

### Default-deny network policy

Between tiers, and between namespaces. The reason is lateral movement: a compromised
workload with unrestricted network access reaches everything, and the difference
between an incident and a breach is usually how far the attacker could move. Every
compliance regime asks for this, and it is right without one.

Default-allow is the state most clusters are in. Moving to default-deny after the
fact is genuinely hard, which is the argument for doing it at the start.

### Resource requests and limits on every workload

A stability default before it is a security one. Without limits, one workload's
memory leak takes down its neighbours, and without requests the scheduler cannot make
sensible decisions. The exemplar repository for this skill had none across roughly
sixty pods, which is common and is a real risk.

### Backups exist, offsite, and a restore has been tested

Untested backups are the default state and they are not a control. GDPR Article 32
names availability alongside confidentiality, so this is a security requirement and
not only an operational one. "Offsite" means outside the primary blast radius — a
backup in the same account and region survives a disk failure and not an account
compromise.

"Never tested" is a common and honest answer. Record it and put a first restore test
in `open-questions.md` with an owner and a date.

### Nothing sensitive in a committed artifact

Account identifiers, endpoint hostnames, registry URLs and credentials are read from
configuration at runtime, not written into a document. `scan_secrets.py` enforces it
over the artifacts and the state file. An account identifier is not a secret, and it
is still most of what a role-assumption attempt needs when paired with a role name.

## Reasoning about a case these do not cover

The defaults above are instances of four ideas. When something new comes up, reason
from these rather than looking for a rule:

1. **Prefer structural to procedural.** A control that cannot be bypassed by one
   mistaken change beats one that depends on nobody making it. A subnet with no route
   beats a security-group rule; an admission policy that blocks beats a review that
   should have caught it.
2. **Assume one thing is already compromised.** The question is not whether an
   attacker gets in but how far they get. That reasoning produces least privilege,
   default-deny and segmentation without needing them as separate rules.
3. **A credential that cannot be rotated will not be rotated.** So prefer identity
   that is issued, short-lived and automatic over a secret that is stored.
4. **A control nobody operates is not a control.** This one cuts *against* adding
   security. A runtime-security tool generating alerts nobody reads is a cost with no
   benefit, and recommending it to a team with no on-call is bad advice dressed as
   good practice. Cross-check domain 14 before adding anything that produces alerts.

## What a waiver must contain

In the state file's `waivers` array, and reproduced in the specification:

```json
{
  "control": "no publicly reachable data stores",
  "deviation": "Analytics Postgres is reachable from the office IP range on 5432",
  "reason": "The BI tool cannot proxy through the bastion. Reviewed alternatives: VPN (rejected, no VPN today), bastion tunnel (rejected, tool cannot use it)",
  "compensating": "Restricted to two office IPs, read-only credentials, connection logging enabled and retained 90 days",
  "owner": "named person who accepted it",
  "date": "2026-09-07",
  "review": "2026-12-07"
}
```

Six things, and each is there because its absence is a specific failure:

- **control** — the exact default being departed from, so the gate can match it and
  stop blocking
- **deviation** — what is actually happening, concretely enough that a reader can
  picture it
- **reason** — including what alternatives were considered and why they were
  rejected. Without this, the next person cannot tell whether the constraint still
  holds
- **compensating** — what reduces the risk instead. A waiver with nothing here is an
  acceptance, which is allowed, and should say so rather than looking like a control
- **owner** — a named person, not a team. Somebody accepted this
- **review** — a date. A waiver with no review date is a permanent exception that
  merely looks temporary

The contradiction gate blocks a deviation with no matching waiver. That is the
intended behaviour: it makes the deviation into a conversation, which is the whole
point.

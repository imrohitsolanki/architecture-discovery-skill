# Domain 4 — Cloud and region

**Blocks a final specification.** Provider and region decide which managed services
exist at all, so every service-level choice depends on it.

## Pre-filled from the repository

`detect_conventions.py` reports provider blocks and any `region` it finds in
Terragrunt locals, Terraform, or tfvars — and it can report more than one provider,
which is a real finding rather than noise. Confirm rather than adopt.

## Questions

**1. Which provider, and is that already settled?** Frequently it is, by an existing
account or an existing contract, in which case record it and move on.

| Option | When it wins | Trade-off |
|---|---|---|
| AWS | Widest service catalogue, deepest hiring pool, most third-party integration | Most services means most ways to build something needlessly complicated; per-service IAM is powerful and verbose |
| Google Cloud | Strong Kubernetes and data tooling, project-per-environment isolation is clean | Smaller regional footprint in some geographies; fewer engineers have deep experience |
| Azure | Existing Microsoft agreements, Entra ID already the identity provider | Resource-manager modelling is its own learning curve; regional service parity varies |
| Oracle Cloud, DigitalOcean, Hetzner, Scaleway | Cost at small and mid scale, sometimes dramatically | Thinner managed-service catalogue, so more falls to you; smaller ecosystem |
| Owned datacentre or colocation | Residency that no region satisfies, sustained heavy load where cloud economics stop working, hardware you already have | Everything below in the on-premises section |
| Hybrid | A genuine split, usually data on premises and compute in cloud | Two operating models, and the network between them becomes a first-class component |
| Multi-cloud | A real requirement, e.g. a regulator or customer demanding provider independence | Levels every service down to the lowest common denominator and roughly doubles the operational surface. Rarely worth it as insurance; occasionally mandatory |

Default: whichever provider the organisation already uses. Provider migration is
expensive and almost never the highest-value thing to spend on.

**2. Which region?** Decided by residency first, latency to users second, service
availability third, and cost last.

State plainly that this script cannot verify which services exist in a given region
— that is a live fact that changes, and an offline table would go stale and be
believed. The contradiction gate raises it as an advisory to check by hand, and it is
worth doing before sign-off rather than after.

**3. How many availability zones?** Default three where the region has three. Two is
acceptable; one is a decision that has to survive the availability target from domain
1, and if that target is 99.9% or higher the contradiction gate treats single-zone as
an error rather than a choice.

**4. Is there a DR region, and where?** Ask even when the answer is no, so "no" is
recorded as a decision. If a residency obligation exists, the DR region is bound by
it too — a disaster-recovery copy is still a copy, and this is a common and expensive
oversight.

**5. Single account, or several?** Under AWS in a single account, environment
isolation rests on VPC boundaries, IAM and tags rather than on an account boundary.
That is defensible and it needs arguing explicitly in the specification, because the
blast radius of a mistaken IAM policy spans everything.

| Option | When it wins | Trade-off |
|---|---|---|
| Single account or project | Small team, low overhead, one bill | No hard boundary between environments; one IAM error reaches production |
| Account or project per environment | Real isolation, separable billing, blast-radius containment | Cross-account access to manage, more setup, and an organisation to run |
| Full organisation with OUs and guardrails | Many teams, or a compliance regime that expects separation | Genuine platform work. Disproportionate for one project with two engineers |

## If the answer is on-premises or bare metal

The interview changes shape from here; these branches open:

- **Virtualisation or bare metal**: Proxmox VE, VMware vSphere (state the
  post-acquisition licensing cost as a factor rather than a footnote), OpenStack,
  Harvester, oVirt, XCP-ng, or provisioning straight onto metal with MAAS or
  Tinkerbell.
- **Where the hardware lives**: owned datacentre, colocation, or a mix. Power and
  cooling headroom, and rack space, become real constraints with real numbers.
- **What connects it**: transit providers, whether there is redundant connectivity,
  and what the bandwidth commitment costs. There is no free egress and no elastic
  escape hatch.
- **Storage**: no managed object store or block store exists, so this becomes a
  first-class decision in domain 12 rather than a detail — Ceph with Rook, Longhorn,
  OpenEBS, TopoLVM, NFS, or a SAN.
- **Capacity**: no autoscaling to hide a sizing mistake. Peak has to be provisioned,
  and the growth figure from domain 1 becomes a purchasing decision.

Say clearly that this raises the operational bar. Domain 14 has to cover somebody
replacing a failed disk, owning firmware and switch configuration, and holding the
storage layer. If the team cannot cover it, that is a finding to record, not a detail
to route around.

## What to write

```json
"04-cloud": {
  "status": "complete",
  "answers": {
    "provider": "aws",
    "region": "ap-south-1",
    "region_driver": "residency | latency | cost | existing",
    "az_spread": 3,
    "dr_region": "ap-south-2",
    "account_model": "single",
    "multi_cloud": false,
    "on_prem": null
  }
}
```

`provider` must be `aws`, `gcp`, `azure`, `on-prem`, `bare-metal`, `colocation` or
`hybrid` for the provider-service consistency check to run; anything else is
reported as unknown rather than silently skipped. `region` is parsed for geography,
so use the provider's own identifier.

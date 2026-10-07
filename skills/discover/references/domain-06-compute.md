# Domain 6 — Compute platform

**Blocks a final specification.** The platform sets the shape of networking,
delivery and operations, so defaulting it defaults most of the specification.

Read domain 14's answers before recommending anything here. Team size and pager
coverage should change your recommendation, and if they never do you are not using
them.

## Pre-filled from the repository

`detect_conventions.py` reports EKS, GKE or AKS module calls, Lambda and ECS
resources, Dockerfiles, `serverless.yml`, Talos configuration, and whether the
Kubernetes and helm Terraform providers are configured. That last one matters: it
distinguishes add-ons applied by the IaC tool from add-ons applied by GitOps, and
they lead to different answers in domain 9.

## The options

Managed and self-hosted sit in one table because the real question is not which
software but whether to run it, and that is decided by domain 14.

| Option | When it wins | Trade-off |
|---|---|---|
| Managed Kubernetes — EKS, GKE, AKS, DOKS, OKE | Several services, a need for a standard platform, a team that can hold Kubernetes | A fixed control-plane charge whether used or not, and Kubernetes is a body of knowledge somebody must hold. Node upgrades remain yours |
| Serverless containers — Fargate, Cloud Run, Container Apps, App Runner | Small team, HTTP services, no desire to own a platform | Less control over networking and scheduling, which makes segmentation evidence harder under PCI. Per-request cost can exceed nodes at sustained load |
| Functions — Lambda, Cloud Functions, Azure Functions | Spiky or infrequent load, event-driven work | Cold starts, execution ceilings, and a per-invocation cost that is excellent at low volume and poor at sustained volume. Vendor coupling is real |
| Self-managed Kubernetes — kubeadm, kops | A specific requirement no managed offering meets | You patch the control plane, hold an etcd backup you have restored from, and rotate certificates. Below roughly five engineers with on-call this is a contradiction, not a preference |
| Lightweight Kubernetes — k3s, RKE2, Talos | Edge, on premises, or small fixed footprints. Talos in particular removes most of the OS surface | Still self-managed. Smaller ecosystem, fewer people who have run it |
| OpenShift or OKD | An organisation already invested, or wanting a batteries-included platform | Heaviest option here, and licensing on the commercial edition is significant |
| Nomad | Mixed workloads including non-containerised, simpler operational model than Kubernetes | Much smaller ecosystem; most tooling in this document assumes Kubernetes |
| Plain VMs with systemd | A single service, a small fixed deployment, a team with no container experience | No orchestration, so scaling and rollout are yours to build. Frequently the right answer and rarely proposed |
| Knative, OpenFaaS | Functions without provider coupling | Runs on Kubernetes, so you own Kubernetes plus a functions layer |
| Docker Swarm | Named so it can be rejected explicitly | Effectively unmaintained. Do not start here |

Autoscaling, once a platform is chosen:

| Option | When it wins | Trade-off |
|---|---|---|
| Cluster Autoscaler | Node-group scaling, widely understood | Reacts to pending pods; slower, and tied to node-group shapes |
| Karpenter | AWS, wants right-sized nodes provisioned quickly | AWS-centric, another component to understand and keep current |
| Horizontal Pod Autoscaler | Pod count from CPU, memory or custom metrics | Needs sensible requests set, and most workloads do not have them |
| Vertical Pod Autoscaler | Right-sizing requests over time | Restarts pods to apply changes; awkward with the HPA |
| KEDA | Scaling on queue depth or external events | Another controller; excellent when the trigger is not CPU |

## Questions

**1. Which of the above, and why not the one below it?** Recommend, reject the
neighbours by name, and say what your recommendation costs. Worked turn 2 in
`interview-method.md` is exactly this turn.

**2. Same platform in every environment, or different?** Different is legitimate —
serverless in development, Kubernetes in production — and it is also how a
"works in staging" bug reaches production. Say which you are trading.

**3. Then drill down one level.** This is where the specification earns its keep.

- **Managed Kubernetes**: node strategy (managed node group, self-managed, or
  Karpenter); spot or preemptible proportion, and never for production; upgrade
  cadence, who performs it, and in what window; multi-tenancy — namespace per team
  or per environment, and what enforces the boundary.
- **Self-managed or lightweight Kubernetes**: who patches the control plane; the
  etcd backup schedule and the date of the last restore *test*, not the last backup;
  certificate rotation before expiry; what happens when a control-plane node dies.
- **Serverless containers**: concurrency ceiling, cold-start budget, image size and
  its effect on start time, and how you get a shell for debugging.
- **Functions**: execution time limit against the longest task, memory sizing,
  concurrency limits and what happens when they are hit.
- **Plain VMs**: how a deploy happens, how a rollback happens, and what patches the
  operating system.
- **Bare metal**: capacity headroom, failure domains across racks, who replaces
  hardware, and how long a replacement takes to arrive.

## Gating consequences

- Functions closes the ingress-controller and node-pool branches in 7 entirely.
- Self-managed anything with a team of three or fewer, or nobody on the pager, is an
  error from the contradiction gate. It is not a style disagreement: an expired
  certificate on a Sunday is the outcome.
- Any Kubernetes counts as a cost driver against the ceiling in 13.
- Single-zone with an availability target of 99.9% or higher is an error.
- Bare metal opens storage as a first-class decision in 12 and removes spot pricing
  from every lever the cost gate can offer.

## What to write

```json
"06-compute": {
  "status": "complete",
  "answers": {
    "platform": "Amazon EKS",
    "control_plane": "managed",
    "multi_az": true,
    "node_strategy": "managed node groups with Karpenter for burst",
    "spot_usage": "non-production only",
    "upgrade_cadence": "monthly, manual, Tuesday 02:00 IST window",
    "multi_tenancy": "namespace per environment",
    "differs_by_environment": false
  }
}
```

`control_plane` is read by the contradiction gate — use `managed` or `self-hosted`.
`platform` is scanned for both the self-hosted names and the Kubernetes names, so
write the product name plainly.

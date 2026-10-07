# Domain 7 — Networking and ingress

**Does not block.** Secure defaults cover it: private subnets, a load balancer in
public subnets only, egress controlled, no data store reachable from the internet.

## Pre-filled from the repository

`detect_conventions.py` reports ingress controllers, CNI plugins, service meshes,
`external-dns`, `cert-manager`, NetworkPolicy manifests, and RFC 1918 CIDR blocks. It
deliberately ignores `0.0.0.0/0`, since that is a security-group rule rather than a
network plan.

## Questions

**1. Is there an existing VPC and CIDR plan, or is this greenfield?** If greenfield,
propose the plan rather than asking for one — a `/16` per environment with `/20` per
tier per zone is a defensible default, and the important part is leaving room. Ask
what it must not overlap with: a VPN, an office range, a peer, a future acquisition.
Overlapping CIDRs are discovered at the worst possible moment.

**2. Subnet tiers.** Default three: public for load balancers only, private for
compute, isolated for data with no route to a NAT gateway. State that the third tier
is what makes "no publicly reachable data store" structural rather than a promise.

**3. How does traffic get in?**

| Option | When it wins | Trade-off |
|---|---|---|
| ingress-nginx | Most widely deployed, so answers to problems are easy to find | Configuration through annotations gets unwieldy; the project has had a bumpy governance history worth checking currency on |
| Traefik | Pleasant configuration, good dynamic behaviour | Smaller community than ingress-nginx |
| Envoy Gateway | Gateway API native, modern data plane | Younger; fewer worked examples in the wild |
| Contour | Envoy-based, stable, straightforward | Less feature surface than the alternatives |
| Kong, APISIX | Real API-gateway needs — rate limiting, auth, transformation at the edge | A platform of its own, with its own operational weight |
| Cloud load balancer controller (ALB, GCLB, App Gateway) | Fewest moving parts, provider-integrated WAF | Provider-specific; less portable configuration |
| MetalLB or kube-vip | Bare metal, where no cloud load balancer exists | You now own load-balancer availability |

Also ask Gateway API or the older Ingress API. Gateway API is where the ecosystem is
going and has a better role-separation model; Ingress has more worked examples. Say
which you are choosing and why, since it is hard to change later.

**4. Service mesh — and "no mesh" is a first-class answer.** Ask what problem it
would solve. Mutual TLS between services, fine-grained traffic shifting, and
per-service observability are real reasons. "Best practice" is not.

| Option | When it wins | Trade-off |
|---|---|---|
| No mesh | Small service count; mTLS achievable at the ingress and by the platform | You do not get per-hop mTLS or traffic shifting |
| Istio, ambient mode | The full feature set; ambient removes the per-pod sidecar | The heaviest option, and a substantial thing to debug |
| Linkerd | Simplest real mesh, low overhead | Fewer features than Istio |
| Cilium Service Mesh | Already running Cilium, wants mesh without sidecars | Ties mesh and CNI decisions together |
| Consul Connect, Kuma | Multi-platform including VMs | Smaller Kubernetes-native community |

**5. CNI and network policy.** Cilium and Calico both do policy well; Cilium adds
eBPF observability and can replace kube-proxy. The provider's own CNI is simplest and
often has IP-allocation constraints worth knowing about in advance. Whatever the
choice, ask whether policy will be default-deny. Default-deny is the answer under any
compliance regime and the honest answer everywhere else.

**6. Egress.** Ask whether outbound traffic is controlled. Unrestricted egress is the
default in most builds and the path by which data leaves. Options: NAT gateway with
no filtering, an egress proxy with an allowlist, or per-namespace policy. Cost is a
factor — NAT gateway data processing charges surprise people.

**7. Private connectivity to managed services.** VPC endpoints, Private Service
Connect, private endpoints. Keeps traffic off the public internet and off the NAT
gateway bill. Usually worth it for object storage and secrets.

**8. Edge: WAF, DDoS, CDN, DNS.**

| Option | When it wins | Trade-off |
|---|---|---|
| Cloudflare | Strong DDoS and WAF, good value, easy to adopt | Another vendor, and TLS terminates there unless configured otherwise |
| AWS WAF with Shield | Deep AWS integration | Rule management is fiddly; Shield Advanced is expensive |
| CloudFront, Cloud CDN, Front Door, Fastly | Provider-native caching and edge | Provider-specific configuration |
| Coraza or ModSecurity self-hosted | On premises where no cloud WAF exists | You own the rules and the tuning, and tuning is the whole job |
| external-dns with the provider's DNS | Records follow the workload | Give it a scoped zone, not account-wide DNS write |

## Gating consequences

- PCI-DSS makes segmentation of the cardholder environment mandatory here, with
  default-deny between tiers and a business justification per allowed flow.
- A `0.0.0.0/0` ingress range recorded anywhere is a secure-default deviation and
  requires a waiver naming who accepted it.
- Functions or serverless containers from domain 6 close most of this domain; record
  it `not-applicable` with the reason rather than leaving it unanswered.
- Bare metal replaces the cloud load-balancer branch with MetalLB or hardware, and
  makes DDoS protection something bought upstream rather than enabled.

## What to write

```json
"07-networking": {
  "status": "complete",
  "answers": {
    "vpc_cidr": "10.20.0.0/16",
    "must_not_overlap": ["10.0.0.0/16 office VPN"],
    "subnet_tiers": ["public-lb", "private-compute", "isolated-data"],
    "ingress": "ingress-nginx",
    "api_style": "gateway-api | ingress",
    "service_mesh": "none",
    "cni": "cilium",
    "network_policy": "default-deny",
    "egress": "nat-gateway-unfiltered | egress-proxy-allowlist",
    "private_endpoints": ["s3", "secretsmanager"],
    "waf": "cloudflare",
    "dns": "route53 with external-dns"
  }
}
```

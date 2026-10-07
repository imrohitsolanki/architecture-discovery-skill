#!/usr/bin/env python3
"""Read a repository and report the infrastructure conventions it already uses.

Reach for this once, at the start of a discovery interview, when the project has an
existing repository. Every fact it returns is a question you do not have to ask.
There is no reason to run it twice in a session.

Inputs
    --repo PATH   Repository to inspect. Defaults to $CLAUDE_PROJECT_DIR, then the
                  current directory.
    --json        Emit findings as JSON. Use this when you want to branch on a
                  specific finding rather than read the summary.
    --max-files N Safety cap on files inspected. Default 4000.

Outputs
    A report on stdout, grouped by interview domain. Each finding carries the file
    that evidenced it, so a wrong inference is visible and correctable instead of
    silent. Domains with no signal are listed explicitly as "no signal", because
    knowing to ask is as useful as knowing the answer.

    Exit 0  inspection completed, whether or not anything was found. Finding
            nothing is a valid result, not a failure.
    Exit 2  the path does not exist or is not a directory.

Why every finding carries its evidence
    A detected convention is an inference, and inferences are sometimes wrong. The
    repository this skill was designed against specifies no ArgoCD and installs
    Kubernetes add-ons through the Terraform helm provider, while the house default
    is ArgoCD. A pre-fill presented as a fact would have put the wrong tool into a
    signed-off specification. Presented as "detected X, evidenced by Y, confirm?" it
    costs one turn and cannot go wrong quietly. So report the evidence, always, and
    let the interview confirm rather than assume.

Why it never writes
    Gate and detection scripts here read and exit with a status. Nothing this skill
    creates is written by a subprocess, because Read and Edit permission rules do
    not apply to files a Python process opens itself; going through the Write tool
    keeps every file the skill creates visible as a tool call.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", ".terraform", ".terragrunt-cache", "node_modules", "vendor", "dist",
    "build", "target", ".venv", "venv", "__pycache__", ".next", ".gradle",
    ".idea", ".mypy_cache", ".pytest_cache", "site-packages",
}
MAX_DEPTH = 7
MAX_READ_BYTES = 512 * 1024

# Lines whose first non-whitespace characters are one of these are comments in HCL,
# Terraform, YAML and Dockerfiles. They are stripped before content matching.
#
# This is not fussiness. Every questionable finding in the first run against the
# exemplar repository came from a comment: "ingress-nginx" named in a subnet
# comment, "cluster-autoscaler" named in an IRSA module's docstring listing roles it
# might later serve. Those tools were being *discussed*, not configured. A finding
# evidenced by a comment invites the interview to confirm something the repository
# does not actually do, which is the specific failure this script exists to avoid.
COMMENT_PREFIXES = ("#", "//")


def _strip_comments(text: str) -> str:
    kept = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(COMMENT_PREFIXES):
            continue
        kept.append(line)
    return "\n".join(kept)

# Filename or directory markers. marker -> (domain, key, value)
# Matched against the path relative to the repo root, case-insensitively.
NAME_MARKERS: list[tuple[str, str, str, str]] = [
    # domain 9 — infrastructure as code
    (r"(^|/)root\.hcl$",                 "09-delivery", "iac", "Terragrunt (single root.hcl)"),
    (r"(^|/)terragrunt\.hcl$",           "09-delivery", "iac", "Terragrunt"),
    (r"\.tf$",                           "09-delivery", "iac", "Terraform"),
    (r"(^|/)\.terraform-version$",       "09-delivery", "iac-pinning", "tfenv (.terraform-version)"),
    (r"(^|/)\.terragrunt-version$",      "09-delivery", "iac-pinning", "tgenv (.terragrunt-version)"),
    (r"(^|/)template\.ya?ml$",           "09-delivery", "iac", "AWS SAM or CloudFormation template"),
    (r"(^|/)cdk\.json$",                 "09-delivery", "iac", "AWS CDK"),
    (r"(^|/)Pulumi\.ya?ml$",             "09-delivery", "iac", "Pulumi"),
    (r"\.bicep$",                        "09-delivery", "iac", "Azure Bicep"),
    (r"(^|/)ansible\.cfg$",              "09-delivery", "config-mgmt", "Ansible"),
    (r"(^|/)playbooks?/",                "09-delivery", "config-mgmt", "Ansible playbooks"),
    (r"(^|/)Chart\.ya?ml$",              "09-delivery", "templating", "Helm"),
    (r"(^|/)kustomization\.ya?ml$",      "09-delivery", "templating", "Kustomize"),
    (r"(^|/)helmfile\.ya?ml$",           "09-delivery", "templating", "Helmfile"),
    # domain 9 — CI
    (r"(^|/)\.github/workflows/",        "09-delivery", "ci", "GitHub Actions"),
    (r"(^|/)\.gitlab-ci\.ya?ml$",        "09-delivery", "ci", "GitLab CI"),
    (r"(^|/)bitbucket-pipelines\.ya?ml$", "09-delivery", "ci", "Bitbucket Pipelines"),
    (r"(^|/)Jenkinsfile$",               "09-delivery", "ci", "Jenkins"),
    (r"(^|/)azure-pipelines\.ya?ml$",    "09-delivery", "ci", "Azure Pipelines"),
    (r"(^|/)\.circleci/",                "09-delivery", "ci", "CircleCI"),
    (r"(^|/)\.woodpecker",               "09-delivery", "ci", "Woodpecker CI"),
    # domain 9 — task runner and lint
    (r"(^|/)Taskfile\.ya?ml$",           "09-delivery", "task-runner", "Task (Taskfile.yml)"),
    (r"(^|/)Makefile$",                  "09-delivery", "task-runner", "Make"),
    (r"(^|/)\.tflint\.hcl$",             "09-delivery", "iac-lint", "TFLint"),
    (r"(^|/)\.terraform-docs\.ya?ml$",   "09-delivery", "iac-docs", "terraform-docs"),
    (r"(^|/)\.pre-commit-config\.ya?ml$", "09-delivery", "pre-commit", "pre-commit framework"),
    # domain 6 — compute
    (r"(^|/)Dockerfile",                 "06-compute", "packaging", "Container images (Dockerfile)"),
    (r"(^|/)docker-compose\.ya?ml$",     "06-compute", "local-orchestration", "Docker Compose"),
    (r"(^|/)serverless\.ya?ml$",         "06-compute", "platform", "Serverless Framework (FaaS)"),
    (r"(^|/)talconfig\.ya?ml$",          "06-compute", "platform", "Talos Linux (bare-metal Kubernetes)"),
    (r"(^|/)nomad/",                     "06-compute", "platform", "HashiCorp Nomad"),
    # domain 2 — application shape
    (r"(^|/)package\.json$",             "02-app-shape", "stack", "Node.js or TypeScript"),
    (r"(^|/)go\.mod$",                   "02-app-shape", "stack", "Go"),
    (r"(^|/)requirements\.txt$",         "02-app-shape", "stack", "Python"),
    (r"(^|/)pyproject\.toml$",           "02-app-shape", "stack", "Python"),
    (r"(^|/)pom\.xml$",                  "02-app-shape", "stack", "Java (Maven)"),
    (r"(^|/)build\.gradle",              "02-app-shape", "stack", "Java or Kotlin (Gradle)"),
    (r"(^|/)Cargo\.toml$",               "02-app-shape", "stack", "Rust"),
    (r"(^|/)Gemfile$",                   "02-app-shape", "stack", "Ruby"),
    (r"(^|/)composer\.json$",            "02-app-shape", "stack", "PHP"),
    (r"(^|/)\.csproj$",                  "02-app-shape", "stack", ".NET"),
    # domain 11 — security tooling already in place
    (r"(^|/)\.gitleaks\.toml$",          "11-security", "secret-scanning", "gitleaks (configured)"),
    (r"(^|/)trivy\.ya?ml$",              "11-security", "image-scanning", "Trivy"),
    (r"(^|/)\.trivyignore$",             "11-security", "image-scanning", "Trivy"),
]

# Content patterns. Applied only to files whose name matches `files`.
# (regex, files-regex, domain, key, template) — \1 from the match fills {} in template.
CONTENT_MARKERS: list[tuple[str, str, str, str, str]] = [
    # domain 4 — cloud provider and region
    (r'provider\s+"aws"',            r"\.tf$|\.hcl$", "04-cloud", "provider", "AWS"),
    (r'provider\s+"google"',         r"\.tf$|\.hcl$", "04-cloud", "provider", "Google Cloud"),
    (r'provider\s+"azurerm"',        r"\.tf$|\.hcl$", "04-cloud", "provider", "Azure"),
    (r'provider\s+"kubernetes"|source\s*=\s*"hashicorp/kubernetes"', r"\.tf$|\.hcl$", "06-compute", "platform", "Kubernetes (Terraform provider configured)"),
    (r'provider\s+"helm"|source\s*=\s*"hashicorp/helm"', r"\.tf$|\.hcl$", "09-delivery", "addon-delivery", "Terraform helm provider (add-ons applied by Terraform, not GitOps)"),
    (r'region\s*=\s*"([a-z0-9-]+)"', r"\.tf$|\.hcl$|\.tfvars", "04-cloud", "region", "{}"),
    # domain 9 — GitOps
    (r"argo-?cd|argoproj",           r"\.ya?ml$|\.tf$|\.hcl$", "09-delivery", "gitops", "Argo CD"),
    (r"fluxcd|flux-system",          r"\.ya?ml$|\.tf$|\.hcl$", "09-delivery", "gitops", "Flux CD"),
    # domain 6 — managed Kubernetes
    (r"terraform-aws-modules/eks|aws_eks_cluster", r"\.tf$|\.hcl$", "06-compute", "platform", "Amazon EKS"),
    (r"google_container_cluster",    r"\.tf$|\.hcl$", "06-compute", "platform", "Google GKE"),
    (r"azurerm_kubernetes_cluster",  r"\.tf$|\.hcl$", "06-compute", "platform", "Azure AKS"),
    (r"aws_lambda_function",         r"\.tf$|\.hcl$", "06-compute", "platform", "AWS Lambda (FaaS)"),
    (r"aws_ecs_service|aws_ecs_task_definition", r"\.tf$|\.hcl$", "06-compute", "platform", "Amazon ECS"),
    (r"karpenter",                   r"\.tf$|\.hcl$|\.ya?ml$", "06-compute", "autoscaling", "Karpenter"),
    (r"cluster-autoscaler",          r"\.tf$|\.hcl$|\.ya?ml$", "06-compute", "autoscaling", "Cluster Autoscaler"),
    (r"\bkeda\b",                    r"\.tf$|\.hcl$|\.ya?ml$", "06-compute", "autoscaling", "KEDA"),
    # domain 7 — networking.
    # The CIDR pattern accepts only RFC 1918 ranges. Matching any CIDR reported
    # 0.0.0.0/0 as a "VPC CIDR" on a real repository, where it was actually a
    # security-group rule allowing the world. A private range is the only kind of
    # CIDR a VPC or subnet plan uses, so restricting the pattern removes the whole
    # class of false positive rather than special-casing the one that showed up.
    (r'cidr_block\s*=\s*"(10\.[0-9./]+|192\.168\.[0-9./]+|172\.(?:1[6-9]|2[0-9]|3[01])\.[0-9./]+)"',
     r"\.tf$|\.hcl$|\.tfvars", "07-networking", "vpc-cidr", "{}"),
    (r"ingress-nginx",               r"\.tf$|\.hcl$|\.ya?ml$", "07-networking", "ingress", "ingress-nginx"),
    (r"\btraefik\b",                 r"\.tf$|\.hcl$|\.ya?ml$", "07-networking", "ingress", "Traefik"),
    (r"envoy-?gateway",              r"\.tf$|\.hcl$|\.ya?ml$", "07-networking", "ingress", "Envoy Gateway"),
    (r"\bmetallb\b",                 r"\.tf$|\.hcl$|\.ya?ml$", "07-networking", "load-balancer", "MetalLB (bare metal)"),
    (r"\bistio\b",                   r"\.tf$|\.hcl$|\.ya?ml$", "07-networking", "service-mesh", "Istio"),
    (r"\blinkerd\b",                 r"\.tf$|\.hcl$|\.ya?ml$", "07-networking", "service-mesh", "Linkerd"),
    (r"\bcilium\b",                  r"\.tf$|\.hcl$|\.ya?ml$", "07-networking", "cni", "Cilium"),
    (r"\bcalico\b",                  r"\.tf$|\.hcl$|\.ya?ml$", "07-networking", "cni", "Calico"),
    (r"cert-manager",                r"\.tf$|\.hcl$|\.ya?ml$", "08-identity", "certificates", "cert-manager"),
    (r"external-dns",                r"\.tf$|\.hcl$|\.ya?ml$", "07-networking", "dns", "external-dns"),
    (r"kind:\s*NetworkPolicy",       r"\.ya?ml$", "11-security", "network-policy", "Kubernetes NetworkPolicy in use"),
    # domain 8 — identity and secrets
    (r"external-secrets|ExternalSecret", r"\.tf$|\.hcl$|\.ya?ml$", "08-identity", "secrets", "External Secrets Operator"),
    (r"\bvault\b",                   r"\.tf$|\.hcl$|\.ya?ml$", "08-identity", "secrets", "HashiCorp Vault"),
    (r"sealed-?secrets|SealedSecret", r"\.tf$|\.hcl$|\.ya?ml$", "08-identity", "secrets", "Sealed Secrets"),
    (r"aws_secretsmanager_secret",   r"\.tf$|\.hcl$", "08-identity", "secrets", "AWS Secrets Manager"),
    (r"\bsops\b",                    r"\.tf$|\.hcl$|\.ya?ml$", "08-identity", "secrets", "SOPS"),
    (r"\birsa\b|assume_role_with_web_identity", r"\.tf$|\.hcl$", "08-identity", "workload-identity", "IRSA"),
    (r"spiffe|spire",                r"\.tf$|\.hcl$|\.ya?ml$", "08-identity", "workload-identity", "SPIFFE/SPIRE"),
    (r"\bkeycloak\b",                r"\.tf$|\.hcl$|\.ya?ml$", "08-identity", "idp", "Keycloak"),
    # domain 10 — observability
    (r"kube-prometheus-stack|prometheus-operator", r"\.tf$|\.hcl$|\.ya?ml$", "10-observability", "metrics", "kube-prometheus-stack"),
    (r"victoriametrics",             r"\.tf$|\.hcl$|\.ya?ml$", "10-observability", "metrics", "VictoriaMetrics"),
    (r"\bthanos\b",                  r"\.tf$|\.hcl$|\.ya?ml$", "10-observability", "metrics", "Thanos"),
    (r"\bloki\b",                    r"\.tf$|\.hcl$|\.ya?ml$", "10-observability", "logs", "Loki"),
    (r"opensearch|elasticsearch",    r"\.tf$|\.hcl$|\.ya?ml$", "10-observability", "logs", "OpenSearch or Elasticsearch"),
    (r"fluent-?bit",                 r"\.tf$|\.hcl$|\.ya?ml$", "10-observability", "log-shipper", "Fluent Bit"),
    (r"\bpromtail\b",                r"\.tf$|\.hcl$|\.ya?ml$", "10-observability", "log-shipper", "Promtail (deprecated by Grafana)"),
    (r"\bvector\b",                  r"\.tf$|\.hcl$|\.ya?ml$", "10-observability", "log-shipper", "Vector"),
    (r"\bgrafana\b",                 r"\.tf$|\.hcl$|\.ya?ml$", "10-observability", "dashboards", "Grafana"),
    (r"opentelemetry|otel-collector", r"\.tf$|\.hcl$|\.ya?ml$", "10-observability", "traces", "OpenTelemetry Collector"),
    (r"\btempo\b|\bjaeger\b",        r"\.tf$|\.hcl$|\.ya?ml$", "10-observability", "traces", "Tempo or Jaeger"),
    (r"alertmanager",                r"\.tf$|\.hcl$|\.ya?ml$", "10-observability", "alerting", "Alertmanager"),
    # domain 11 — policy and posture
    (r"\bkyverno\b",                 r"\.tf$|\.hcl$|\.ya?ml$", "11-security", "policy-as-code", "Kyverno"),
    (r"gatekeeper|open-?policy-agent", r"\.tf$|\.hcl$|\.ya?ml$", "11-security", "policy-as-code", "OPA Gatekeeper"),
    (r"\bfalco\b",                   r"\.tf$|\.hcl$|\.ya?ml$", "11-security", "runtime-security", "Falco"),
    (r"\btetragon\b",                r"\.tf$|\.hcl$|\.ya?ml$", "11-security", "runtime-security", "Tetragon"),
    (r"\bvelero\b",                  r"\.tf$|\.hcl$|\.ya?ml$", "12-data-dr", "backup", "Velero"),
    (r"cloudnative-?pg|CloudNativePG", r"\.tf$|\.hcl$|\.ya?ml$", "12-data-dr", "database-operator", "CloudNativePG"),
    (r"\bpatroni\b",                 r"\.tf$|\.hcl$|\.ya?ml$", "12-data-dr", "database-operator", "Patroni"),
    (r"\bstrimzi\b|\bkafka\b",       r"\.tf$|\.hcl$|\.ya?ml$", "12-data-dr", "queue", "Kafka"),
    (r"\brook-?ceph\b|\bceph\b",     r"\.tf$|\.hcl$|\.ya?ml$", "12-data-dr", "storage", "Ceph (Rook)"),
    (r"\blonghorn\b",                r"\.tf$|\.hcl$|\.ya?ml$", "12-data-dr", "storage", "Longhorn"),
    (r"\bopencost\b|\bkubecost\b",   r"\.tf$|\.hcl$|\.ya?ml$", "13-cost", "finops", "OpenCost or Kubecost"),
    (r"\binfracost\b",               r"\.ya?ml$|\.hcl$", "13-cost", "finops", "Infracost"),
]

# Categories whose absence is itself worth reporting. If a repository provisions
# Kubernetes but nothing ships its logs, that gap is a question the interview should
# ask, and it is invisible in a report that only lists what was found.
#
# Only reported when the repository shows enough infrastructure for the absence to
# mean something — an empty repository is not missing a backup tool, it simply has
# nothing to back up.
EXPECTED_CATEGORIES: list[tuple[str, str, str]] = [
    ("09-delivery", "gitops", "No GitOps controller found. Either delivery is push-based from CI, or add-ons are applied directly by the IaC tool. Confirm which, and whether that is deliberate."),
    ("09-delivery", "ci", "No CI configuration found. Ask how anything is currently built and deployed."),
    ("08-identity", "secrets", "No secrets backend found. Ask where credentials live today; this is the most common place static secrets hide."),
    ("10-observability", "metrics", "No metrics stack found. Ask what is watched today and who looks at it."),
    ("10-observability", "logs", "No log aggregation found. Ask how a production incident is currently investigated."),
    ("11-security", "policy-as-code", "No admission policy engine found. Ask whether workload standards are enforced or only documented."),
    ("11-security", "secret-scanning", "No secret scanning configured. Worth raising regardless of what the interview decides."),
    ("12-data-dr", "backup", "No backup tooling found. Ask what is backed up, how often, and when a restore was last tested."),
]

DOMAIN_LABELS = {
    "02-app-shape": "2  Application shape",
    "04-cloud": "4  Cloud and region",
    "05-environments": "5  Environment topology",
    "06-compute": "6  Compute platform",
    "07-networking": "7  Networking and ingress",
    "08-identity": "8  Identity and secrets",
    "09-delivery": "9  Delivery",
    "10-observability": "10 Observability",
    "11-security": "11 Security posture",
    "12-data-dr": "12 Data, backup and DR",
    "13-cost": "13 Cost",
}

# Domains this script cannot speak to. Listed so the interview knows to ask cold.
INTERVIEW_ONLY = {
    "01-product": "product context, users, scale, SLA and SLO, RTO and RPO",
    "03-compliance": "which compliance regimes apply",
    "14-team": "team size, skills, who carries the pager, support hours",
}


def _walk(root: Path, max_files: int) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        if len(rel.parts) >= MAX_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".terragrunt")]
        for fn in filenames:
            found.append(Path(dirpath) / fn)
            if len(found) >= max_files:
                return found
    return found


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_READ_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def _add(findings: dict, domain: str, key: str, value: str, evidence: str) -> None:
    bucket = findings.setdefault(domain, {}).setdefault(key, {})
    ev = bucket.setdefault(value, [])
    if len(ev) < 3 and evidence not in ev:
        ev.append(evidence)


def detect(root: Path, max_files: int) -> dict:
    files = _walk(root, max_files)
    rels = [str(f.relative_to(root)) for f in files]
    findings: dict = {}

    name_pats = [(re.compile(p, re.I), d, k, v) for p, d, k, v in NAME_MARKERS]
    for f, rel in zip(files, rels):
        for pat, dom, key, val in name_pats:
            if pat.search(rel):
                _add(findings, dom, key, val, rel)

    content_pats = [
        (re.compile(p, re.I | re.M), re.compile(fp, re.I), d, k, t)
        for p, fp, d, k, t in CONTENT_MARKERS
    ]
    for f, rel in zip(files, rels):
        if not any(fp.search(rel) for _, fp, _, _, _ in content_pats):
            continue
        raw = _read(f)
        if raw is None:
            continue
        text = _strip_comments(raw)
        for pat, filepat, dom, key, template in content_pats:
            if not filepat.search(rel):
                continue
            m = pat.search(text)
            if not m:
                continue
            value = template.format(m.group(1)) if "{}" in template and m.groups() else template
            _add(findings, dom, key, value, rel)

    # Environment topology: directories that look like environment units.
    env_names = {"dev", "development", "test", "qa", "stage", "staging", "uat",
                 "prod", "production", "sandbox", "preprod", "demo"}
    envs: dict[str, list[str]] = {}
    for rel in rels:
        parts = Path(rel).parts
        for i, part in enumerate(parts[:-1]):
            if part in ("env", "envs", "environments", "live") and i + 1 < len(parts) - 1:
                envs.setdefault(parts[i + 1], []).append(rel)
            elif part.lower() in env_names and i == 0:
                envs.setdefault(part, []).append(rel)
    for name, ev in sorted(envs.items()):
        _add(findings, "05-environments", "environment", name, ev[0])

    # Tag scheme: keys inside a default_tags block.
    for f, rel in zip(files, rels):
        if not rel.endswith((".hcl", ".tf")):
            continue
        raw = _read(f)
        text = _strip_comments(raw) if raw else ""
        if "default_tags" not in text:
            continue
        block = text[text.index("default_tags"):][:1200]
        for key in sorted(set(re.findall(r"^\s{2,}([A-Z][A-Za-z]+)\s*=", block, re.M))):
            _add(findings, "13-cost", "tag-key", key, rel)

    # Service-count heuristic: how many distinct directories hold a Dockerfile.
    dockerdirs = {str(Path(r).parent) for r in rels if Path(r).name.startswith("Dockerfile")}
    if len(dockerdirs) > 1:
        _add(findings, "02-app-shape", "shape",
             f"Likely multi-service: {len(dockerdirs)} directories contain a Dockerfile",
             sorted(dockerdirs)[0])
    elif len(dockerdirs) == 1:
        _add(findings, "02-app-shape", "shape",
             "Single container image found; likely a monolith or a single service",
             sorted(dockerdirs)[0])

    # Absence only means something once there is infrastructure to be absent from.
    substantive = sum(len(v) for v in findings.values()) >= 4
    gaps = []
    if substantive:
        for domain, key, note in EXPECTED_CATEGORIES:
            if key not in findings.get(domain, {}):
                gaps.append({"domain": domain, "category": key, "note": note})

    return {
        "repo": str(root),
        "repo_as_given": None,  # filled by main(), which knows what was typed
        "files_inspected": len(files),
        "gaps": gaps,
        "truncated": len(files) >= max_files,
        "findings": findings,
        "no_signal": sorted(
            d for d in DOMAIN_LABELS if d not in findings
        ),
        "interview_only": INTERVIEW_ONLY,
    }


def render(report: dict) -> str:
    out: list[str] = []
    # Print the path the operator typed, and the resolved one only when it differs.
    # Echoing back a path nobody typed — a symlinked home directory is the everyday
    # case — reads as a bug and costs a minute of checking before it turns out to be
    # nothing.
    given = report.get("repo_as_given")
    if given and given != report["repo"]:
        out.append(f"Repository: {given}")
        out.append(f"            (resolved to {report['repo']})")
    else:
        out.append(f"Repository: {report['repo']}")
    out.append(f"Files inspected: {report['files_inspected']}"
               + (" (capped, results may be partial)" if report["truncated"] else ""))
    out.append("")
    if not report["findings"]:
        out.append("No infrastructure conventions detected. Treat every domain as an "
                   "interview question and ask cold.")
    else:
        out.append("Detected — each of these is an INFERENCE from the file named. "
                   "Confirm it in the interview rather than adopting it.")
        out.append("")
        for domain in sorted(report["findings"]):
            out.append(DOMAIN_LABELS.get(domain, domain))
            for key, values in sorted(report["findings"][domain].items()):
                for value, evidence in sorted(values.items()):
                    out.append(f"    {key}: {value}")
                    out.append(f"        evidence: {', '.join(evidence)}")
            out.append("")
    if report.get("gaps"):
        out.append("Expected but not found — ask about each:")
        out.append("")
        for g in report["gaps"]:
            out.append(f"    {g['category']} ({DOMAIN_LABELS.get(g['domain'], g['domain']).strip()})")
            out.append(f"        {g['note']}")
        out.append("")
    if report["no_signal"]:
        out.append("No signal — ask these cold:")
        for d in report["no_signal"]:
            out.append(f"    {DOMAIN_LABELS[d]}")
        out.append("")
    out.append("Never detectable from a repository — always ask:")
    for _, label in sorted(report["interview_only"].items()):
        out.append(f"    {label}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=os.environ.get("CLAUDE_PROJECT_DIR", "."))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-files", type=int, default=4000)
    args = ap.parse_args()

    root = Path(args.repo).expanduser().resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    report = detect(root, args.max_files)
    report["repo_as_given"] = str(Path(args.repo).expanduser())
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

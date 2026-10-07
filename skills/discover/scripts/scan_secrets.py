#!/usr/bin/env python3
"""Scan the artifacts and the state file for anything that must not be committed.

Reach for this immediately before committing artifacts, every time, including on a
revision. The artifacts and `discovery-state.json` go into a repository, so anything
sensitive that reaches them is published and, once pushed, may be cached or indexed
whether or not it is later deleted.

Inputs
    TARGET       Directory or file to scan. Positional, required. Normally the
                 artifact output directory, which contains discovery-state.json.
    --json       Emit findings as JSON.
    --config     Path to a gitleaks config, if the repository has one.

Outputs
    Two classes of finding, both blocking, then a verdict.

    Exit 0  nothing found.
    Exit 1  something was found.
    Exit 2  the target does not exist, or a report could not be parsed.
    Exit 3  gitleaks is not available, so the scan did not happen. See below.

Why it fails closed when gitleaks is missing
    A pass means "these files were scanned and were clean". If the scanner is absent
    there is no basis for that claim, and reporting success would be a lie in the
    one place where a lie is most expensive: the moment before a credential is
    committed. Exit 3 is distinct from exit 1 so CI can tell "found something" from
    "could not look", which need different fixes.

Why it does not rely on gitleaks alone
    §7 requires that no credentials, keys **or account identifiers** appear in the
    emitted artifacts. gitleaks finds credentials and keys; it does not flag an AWS
    account number or an ECR registry hostname, because those are not secrets. They
    are still not ours to publish: an account identifier plus a role name is most of
    what an attacker needs to attempt role assumption, and a registry URL discloses
    both the account and the region. So this script adds identifier patterns on top
    of the credential scan, and reports them separately so the reader can see which
    kind of problem they have.

Why an obvious placeholder is reported at a lower confidence
    A generated Terragrunt stack is required to carry `mock_outputs`, and a
    realistic mock for an ARN-typed input is ARN-shaped — which means it has an
    account slot somebody has to fill. Filled with zeros, one stack produced 54
    findings, every one classified `definite` and none of them real. A gate that
    cries wolf 54 times is a gate people scroll past, so a twelve-digit run of one
    repeated digit is reported as `needs a look` rather than `definite`. It still
    blocks: the right fix is a mock that is a plain string rather than an ARN, and
    the finding is what says so.

Why account identifiers matter for this skill specifically
    §8 says the skill holds no environment specifics: account IDs, registry URLs and
    endpoints are read from repository config at runtime, never written down. The
    artifacts reference configuration, they do not embed it. This gate is what makes
    that rule enforceable rather than aspirational.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Identifier patterns, with why each one matters. Severity is uniform: all block.
# `review` marks a pattern that cannot be made precise without context; it still
# blocks, because a false positive costs a glance and a false negative costs an
# account identifier in a public repository.
IDENTIFIER_PATTERNS: list[tuple[str, str, str, str]] = [
    ("aws-arn-account", r"arn:aws[a-z-]*:[a-z0-9-]*:[a-z0-9-]*:(\d{12}):",
     "certain",
     "An ARN embeds the AWS account number. Reference the resource by name and read "
     "the ARN from repository config at runtime."),
    ("aws-account-labelled", r"(?i)account[_\- ]?(?:id|number)\D{0,10}(\d{12})",
     "certain",
     "A labelled AWS account number. Account identifier plus a role name is most of "
     "what a role-assumption attempt needs."),
    ("ecr-registry", r"(\d{12})\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com",
     "certain",
     "An ECR registry hostname discloses both the account number and the region."),
    # The boundaries exclude letters and underscores, not just digits and
    # punctuation. With `(?<![\d.\-])` a twelve-digit run *inside* a hex digest
    # matched — `zh:17324d4335a7a7ac01cc23eded530775606680ff53b...` in every
    # `.terraform.lock.hcl` reported two account ids that were four characters of
    # somebody's SHA. A `review` pattern is allowed to be imprecise; it is not
    # allowed to fire on every generated checksum file, because a gate that cries
    # wolf on a committed artifact is a gate people learn to scroll past.
    ("aws-account-bare", r"(?<![\w.\-])(\d{12})(?![\w.\-])",
     "review",
     "A bare twelve-digit number, which is the shape of an AWS account id. If it is "
     "something else, say what it is so the next reader does not have to guess."),
    ("gcp-project", r"projects/([a-z][a-z0-9\-]{4,28}[a-z0-9])",
     "review",
     "A GCP project identifier. Projects are the isolation boundary, so the "
     "identifier is worth as much as an AWS account number."),
    ("azure-guid", r"(?i)(?:subscription|tenant)[_\- ]?id\D{0,10}"
                   r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
     "certain",
     "An Azure subscription or tenant identifier."),
    # AWS managed-service endpoints are <name>.<hash>.<region>.<service>.amazonaws.com
    # — the region comes BEFORE the service word, not after it. The first version of
    # this pattern had that order reversed and silently matched nothing, which the
    # fixture caught only because the seeded RDS hostname went unreported while
    # everything around it was found.
    ("private-endpoint",
     r"([a-z0-9-]+(?:\.[a-z0-9-]+){1,3}\.(?:rds|elasticache|es|cache|docdb|"
     r"documentdb|redshift|memorydb|neptune)\.amazonaws\.com)",
     "certain",
     "A managed-service endpoint hostname. It names the instance and the region, and "
     "belongs in configuration rather than in a document."),
    ("internal-host", r"\b([a-z0-9-]+\.(?:internal|local|intranet|corp)\b[a-z0-9.\-]*)",
     "review",
     "An internal hostname. Harmless alone, useful to an attacker in aggregate."),
    ("jdbc-with-credentials", r"(jdbc:[a-z0-9]+://[^\s\"']*[?&](?:user|password)=[^\s\"'&]+)",
     "certain",
     "A connection string carrying credentials."),
    ("basic-auth-url", r"([a-z][a-z0-9+.\-]*://[^/\s:@\"']+:[^/\s:@\"']+@[^\s\"']+)",
     "certain",
     "A URL with a username and password in it."),
]

# Files whose content is documentation about patterns rather than data. Scanning this
# skill's own reference material for examples of what not to write would flag the
# examples, which is why the pattern list lives in a script and the prose that
# discusses it says so.
SKIP_NAMES = {".gitleaksignore", ".gitleaks.toml"}

# Directories holding content that was downloaded rather than written, and that is
# never committed. `.terraform/` and `.terragrunt-cache/` appear as soon as anything
# in a generated tree is initialised, and they hold third-party modules whose own
# examples contain example account numbers — so scanning them reports a dozen
# findings in somebody else's code, none of which the reader can act on, and buries
# the one finding in their own. Excluding them is not a loosening: nothing in either
# directory reaches a commit.
SKIP_DIRS = {".git", ".terraform", ".terragrunt-cache", "node_modules", "vendor"}


def run_gitleaks(target: Path, config: str | None) -> tuple[str, list[dict]]:
    """('ok'|'absent'|'error', findings)."""
    if shutil.which("gitleaks") is None:
        return "absent", []
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "gitleaks.json"
        cmd = ["gitleaks", "dir", str(target),
               "--report-format", "json", "--report-path", str(report),
               "--no-banner", "--exit-code", "7"]
        if config:
            cmd += ["--config", config]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            return f"error: {exc}", []
        if proc.returncode not in (0, 7):
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            return f"error: gitleaks exited {proc.returncode}: " \
                   f"{detail[-1] if detail else 'no output'}", []
        if not report.is_file():
            return "ok", []
        try:
            data = json.loads(report.read_text(encoding="utf-8") or "[]")
        except json.JSONDecodeError as exc:
            return f"error: unparseable gitleaks report: {exc}", []
        # gitleaks has no path-exclusion flag, so the same directories `files_to_scan`
        # skips are filtered out of its report instead. Without this, one
        # `terraform init` in the target tree puts every credential-shaped string in
        # every vendored third-party module into the findings.
        return "ok", [f for f in (data or [])
                      if not (SKIP_DIRS & set(Path(str(f.get("File", ""))).parts))]


def excluded(path: Path) -> bool:
    return bool(SKIP_DIRS & set(path.parts)) or path.name in SKIP_NAMES


def files_to_scan(target: Path) -> list[Path]:
    return ([target] if target.is_file()
            else [p for p in target.rglob("*") if p.is_file() and not excluded(p)])


# A twelve-digit run of one repeated digit — 000000000000, 999999999999. Nobody's
# AWS account looks like that, and generated Terragrunt stacks are full of them:
# `layout.md` requires `mock_outputs`, a realistic mock for an ARN-typed input is
# ARN-shaped, and an ARN has an account slot that has to be filled with something.
# One generated stack produced 54 findings, every one classified `definite`, none of
# them real. Reported at `needs a look` instead: still visible, no longer drowning
# the findings that matter.
PLACEHOLDER_ACCOUNT = re.compile(r"^(\d)\1{11}$")

# Rules whose match is an account identifier, and so can be a placeholder.
ACCOUNT_RULES = {"aws-arn-account", "aws-account-labelled", "ecr-registry",
                 "aws-account-bare"}


def scan_identifiers(target: Path) -> list[dict]:
    files = files_to_scan(target)
    compiled = [(name, re.compile(pat), conf, why)
                for name, pat, conf, why in IDENTIFIER_PATTERNS]
    findings = []
    for path in files:
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, pat, conf, why in compiled:
                m = pat.search(line)
                if not m:
                    continue
                value = m.group(1) if m.groups() else m.group(0)
                confidence, reason = conf, why
                if name in ACCOUNT_RULES and PLACEHOLDER_ACCOUNT.match(value):
                    confidence = "review"
                    reason = ("A twelve-digit placeholder, all one repeated digit. "
                              "Almost certainly a mock rather than an account — but "
                              "a mock that is ARN-shaped is indistinguishable from a "
                              "real ARN to everything downstream, so prefer a plain "
                              "string like \"mock-db-secret\".")
                findings.append({
                    "rule": name, "confidence": confidence,
                    "file": str(path), "line": lineno,
                    "match": value[:60], "why_it_matters": reason,
                })
    return findings


def render(status: str, secrets: list[dict], identifiers: list[dict],
           target: Path) -> str:
    out: list[str] = []

    if status == "absent":
        return ("Scan did not run: gitleaks is not on PATH.\n\n"
                "Failing closed rather than reporting success. A pass here means "
                "these files were scanned and were clean, and with no scanner there "
                "is no basis for that claim — in the one place where an unfounded "
                "claim is most expensive, immediately before a credential is "
                "committed.\n\n"
                "Install it: brew install gitleaks, or see "
                "https://github.com/gitleaks/gitleaks#installing")
    if status.startswith("error"):
        return f"Scan did not complete: {status}\n\nFailing closed."

    if secrets:
        out.append(f"Credentials or keys found ({len(secrets)}):")
        out.append("")
        for s in secrets:
            out.append(f"  {s.get('RuleID', 'unknown')}  "
                       f"{s.get('File', '?')}:{s.get('StartLine', '?')}")
            desc = s.get("Description")
            if desc:
                out.append(f"      {desc}")
        out.append("")

    if identifiers:
        certain = [x for x in identifiers if x["confidence"] == "certain"]
        review = [x for x in identifiers if x["confidence"] == "review"]
        out.append(f"Account identifiers and endpoints found ({len(identifiers)}). "
                   f"gitleaks does not flag these because they are not secrets; they "
                   f"are still not ours to publish:")
        out.append("")
        # Paths relative to the scanned root, not basenames. Fifty-four findings
        # printed as `terragrunt.hcl:21` in a seventeen-unit tree name no file at
        # all: every unit has a terragrunt.hcl, and the reader has nothing to go on.
        root = target if target.is_dir() else target.parent
        for group, label in ((certain, "definite"), (review, "needs a look")):
            for x in group:
                path = Path(x["file"])
                try:
                    shown = path.relative_to(root)
                except ValueError:
                    shown = path
                out.append(f"  [{x['rule']} / {label}] "
                           f"{shown}:{x['line']}  {x['match']}")
                out.append(f"      {x['why_it_matters']}")
            if group:
                out.append("")

    if not secrets and not identifiers:
        out.append(f"Clean. Scanned {target} with gitleaks and "
                   f"{len(IDENTIFIER_PATTERNS)} identifier patterns; nothing found.")
    else:
        out.append("Do not commit. Replace each value with a reference to where it "
                   "is read from at runtime — the artifacts reference configuration, "
                   "they do not embed it.")

    return "\n".join(out).rstrip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("target", help="artifact directory or a single file")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--config", help="path to a gitleaks config")
    args = ap.parse_args()

    target = Path(args.target).expanduser().resolve()
    if not target.exists():
        print(f"error: no such path: {target}", file=sys.stderr)
        return 2

    # An empty directory, or a path pointing somewhere the artifacts are not, used
    # to print "Clean ... nothing found" and exit 0. That is the same output as a
    # real clean scan, so a mistyped path read as a security pass. A scan of nothing
    # is not a pass; it is a scan that did not happen.
    if not files_to_scan(target):
        print(f"error: nothing to scan at {target}. A pass means these files were "
              f"scanned and were clean, and there are no files here — so there is "
              f"no such claim to make. Check the artifact path.", file=sys.stderr)
        return 2

    status, secrets = run_gitleaks(target, args.config)
    identifiers = scan_identifiers(target) if status == "ok" else []

    if args.json:
        print(json.dumps({"status": status, "secrets": secrets,
                          "identifiers": identifiers}, indent=2))
    else:
        print(render(status, secrets, identifiers, target))

    if status == "absent":
        return 3
    if status.startswith("error"):
        return 3
    return 1 if (secrets or identifiers) else 0


if __name__ == "__main__":
    sys.exit(main())

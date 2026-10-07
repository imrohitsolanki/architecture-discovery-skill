#!/usr/bin/env python3
"""Judge a generated Terragrunt and Terraform stack before it is committed.

Reach for this after writing or changing any `.tf` or `.hcl` file in a generated
tree, and again after every revision. It is the only gate command in this skill run
by hand; it invokes the discovery skill's gates and its secret scan as subprocesses.

Both halves of the stack are checked every run. Terraform writes the modules;
Terragrunt composes them into environments, and a stack where only one half is
formatted and validated is a stack where the other half breaks in CI. So `fmt` runs
`terraform fmt -check` **and** `terragrunt hcl fmt --check`, and `validate` runs
`terraform validate` in every module **and** `terragrunt hcl validate` over the
units. Either half failing fails the gate; either half being unable to run means the
gate did not run, which is not the same as passing.

Inputs
    --state PATH       discovery-state.json. Required. The specification this
                       stack is supposed to implement.
    --tf-dir DIR       Root of the generated stack. Required.
    --artifacts DIR    The discovery artifact directory, holding the specification
                       and discovery-state.json. Required unless --draft.
    --root DIR         Treat DIR as a root module, in addition to the ones detected.
                       Repeatable.
    --draft            Report everything, block nothing. Always exits 0.
    --skip NAME        Skip a named gate. Repeatable. Every skip is printed, because
                       a gate skipped silently is worse than one that failed loudly.
    --json             Emit the aggregate as JSON.

Outputs
    A summary line per gate, then the full output of every gate that had something
    to say.

    Exit 0  every gate passed, or --draft.
    Exit 1  at least one gate failed.
    Exit 2  the arguments are wrong, or the tree does not exist.

Gate order, and why it is this order
    `spec` first: Terraform generated from a specification that fails its own gates
    is a faithful implementation of a document nobody should be building from, and
    every gate after it would be checking the wrong thing carefully. Then `pins`,
    because an unpinned provider means the tree validated today is not the tree that
    applies tomorrow. Then `provenance`, which is the machine-checkable half of
    "write nothing you were not told". Then `fmt` and `validate`, which need the
    binary. `secrets` last, because it is the only gate that cares what the files
    say rather than what they mean.

    A failing early gate does not stop the later ones. One report with five problems
    beats five runs finding one problem each.

What this gate cannot do
    It reads HCL with regular expressions after stripping comments, not with a
    parser. That is enough to find a missing `version`, an unpinned module and a
    missing provenance header, and it is not enough to understand an expression. The
    real check on whether the configuration is coherent is `terraform validate` and
    `terragrunt hcl validate`, and the first of those needs a successful `init`.

    `terragrunt hcl validate` parses and evaluates the unit configurations. It does
    not resolve `dependency` outputs, so it proves the stack is well-formed and its
    includes and sources resolve, not that a plan would succeed. Add `--inputs` by
    hand when you want the inputs cross-checked against each module's variables;
    that needs the modules initialised and is left out of the gate for the same
    reason `plan` is.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from _shared import RUN_GATES, SCAN_SECRETS

GATES = ("spec", "pins", "provenance", "conventions", "guardrails", "graph", "fmt",
         "validate", "secrets")

DESCRIPTIONS = {
    "spec": "the specification this implements does not pass its own gates",
    "pins": "a provider, module or tool version is not pinned to a released version",
    "provenance": "a file does not say which decision put it there",
    "conventions": "the code departs from a convention every reviewer will expect",
    "guardrails": "a resource contradicts a secure default, with no waiver for it",
    "graph": "the units depend on each other in a circle, so no apply order exists",
    "fmt": "the tree is not canonically formatted",
    "validate": "the configuration is not valid",
    "secrets": "a credential, key or account identifier is in the stack",
}

# The Terragrunt CLI was reorganised in 0.78: `hclfmt` and `hclvalidate` became
# `hcl fmt` and `hcl validate`. Both spellings are still in the field, because
# `.terragrunt-version` is pinned per repository and plenty of teams are on 0.6x or
# 0.7x. Probing the version is deterministic; guessing from a failed invocation is
# not, since an unknown subcommand and a real failure both exit non-zero.
TERRAGRUNT_HCL_CLI_FROM = (0, 78)

# Directories never walked. `.terraform` holds downloaded provider binaries and
# vendored modules — thousands of files nobody wrote, every one of which would fail
# the provenance check.
SKIP_DIRS = {".terraform", ".git", ".terragrunt-cache", "node_modules", "vendor"}

LINE_COMMENT = re.compile(r"(?m)(^|\s)(#|//).*$")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)

# A version constraint that names a patch release: "6.64.0", "= 6.64.0", "~> 6.64.0".
# "~> 6.0" and ">= 6.0" do not match, on purpose — see the module docstring of
# resolve_versions.py for why an exact provider pin is the point.
EXACT_VERSION = re.compile(r"\d+\.\d+\.\d+")

REQUIRED_VERSION = re.compile(r"required_version\s*=\s*\"([^\"]+)\"")
REQUIRED_PROVIDERS = re.compile(r"required_providers\s*\{", re.S)
PROVIDER_ENTRY = re.compile(
    r"(?P<name>[A-Za-z_][\w-]*)\s*=\s*\{(?P<body>[^{}]*)\}", re.S)
SOURCE_ATTR = re.compile(r"source\s*=\s*\"([^\"]+)\"")
VERSION_ATTR = re.compile(r"version\s*=\s*\"([^\"]+)\"")
MODULE_BLOCK = re.compile(r"(?m)^\s*module\s+\"(?P<name>[^\"]+)\"\s*\{")
BACKEND_BLOCK = re.compile(r"(?m)^\s*backend\s+\"[^\"]+\"\s*\{")
PROVIDER_BLOCK = re.compile(r"(?m)^\s*provider\s+\"[^\"]+\"\s*\{")
# A registry module address: namespace/name/provider, optionally host-prefixed.
REGISTRY_SOURCE = re.compile(r"^(?:[\w.-]+/)?[\w-]+/[\w-]+/[\w-]+$")
PROVENANCE = re.compile(r"(?m)^\s*#\s*spec:\s*\S")
# A Terragrunt unit points at the Terraform it runs with a `terraform` block, which
# is the same `source` attribute under a different block type.
TERRAFORM_BLOCK = re.compile(r"(?m)^\s*terraform\s*\{")
VARIABLE_BLOCK = re.compile(r"(?m)^\s*variable\s+\"(?P<name>[^\"]+)\"\s*\{")
OUTPUT_BLOCK = re.compile(r"(?m)^\s*output\s+\"(?P<name>[^\"]+)\"\s*\{")
DESCRIPTION_ATTR = re.compile(r"(?m)^\s*description\s*=")
TYPE_ATTR = re.compile(r"(?m)^\s*type\s*=")
# Generated, not written: it holds provider checksums and no decisions, so it is
# exempt from the provenance rule that every other .hcl file in the tree obeys.
GENERATED_HCL = {".terraform.lock.hcl"}


def strip_comments(text: str) -> str:
    """HCL with comments removed, so a tool named in a comment is not a finding.

    Same reasoning as `detect_conventions.py`: every questionable finding in its
    first run came from a comment. Here the hazard is the reverse and worse — a
    commented-out `version = "6.64.0"` satisfying a pin check.
    """
    return LINE_COMMENT.sub(r"\1", BLOCK_COMMENT.sub("", text))


def tf_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.tf")
                  if not SKIP_DIRS & set(p.parts))


def hcl_files(root: Path) -> list[Path]:
    """Terragrunt configuration: `root.hcl`, `env.hcl`, every `terragrunt.hcl`.

    `.terraform.lock.hcl` is excluded — it is generated, holds checksums rather than
    decisions, and requiring a provenance header on it would mean editing a file
    Terraform rewrites.
    """
    return sorted(p for p in root.rglob("*.hcl")
                  if not SKIP_DIRS & set(p.parts) and p.name not in GENERATED_HCL)


def tf_dirs(root: Path) -> list[Path]:
    """Every directory holding Terraform, root module or child module alike.

    `terraform validate` is worth running in a child module: `init -backend=false`
    infers its providers from `required_providers` and validates it standalone. In a
    Terragrunt stack there are no root modules at all — the backend and the provider
    are generated from `root.hcl` — so validating only detected roots would validate
    nothing at all and report a pass.
    """
    return sorted({p.parent for p in tf_files(root)})


def terragrunt_units(root: Path) -> list[Path]:
    return sorted(p.parent for p in root.rglob("terragrunt.hcl")
                  if not SKIP_DIRS & set(p.parts))


def is_terragrunt(root: Path) -> bool:
    """Whether this tree is composed by Terragrunt rather than run directly.

    Any `terragrunt.hcl` unit, a `root.hcl` at the top, or a `terragrunt.stack.hcl`.
    A tree with none of those is plain Terraform, and the Terragrunt halves of the
    `fmt` and `validate` gates report that there was nothing for them to do rather
    than failing.
    """
    if (root / "root.hcl").is_file() or (root / "terragrunt.hcl").is_file():
        return True
    return bool(terragrunt_units(root)) or any(
        not SKIP_DIRS & set(p.parts) for p in root.rglob("terragrunt.stack.hcl"))


def _balanced(text: str, start: int) -> str:
    """The body of the block whose opening brace is at or after `start`.

    Brace counting, not parsing. Strings containing braces would defeat it, which is
    why this only ever runs over comment-stripped HCL and only to find attributes.
    """
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return text[start:]


def called_modules(tf_dir: Path) -> set[Path]:
    """Directories something else points at as a local `source`.

    Direct evidence of being a child module, rather than a heuristic: a `module`
    block in Terraform or a `terraform { source = "../..." }` in a Terragrunt unit
    names the directory it calls.

    This exists because the structural root-module test — declares a backend or
    configures a provider — is self-defeating for the rule that a child module must
    not configure a provider: adding the forbidden block is exactly what made the
    directory look like a root and exempted it. Being called is not something a
    module can grant itself.
    """
    called: set[Path] = set()

    def add(base: Path, address: str) -> None:
        if address.startswith((".", "/")) and "${" not in address:
            target = (base / address.split("//")[0]).resolve()
            if target.is_dir():
                called.add(target)

    for path in tf_files(tf_dir):
        body = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        for mod in MODULE_BLOCK.finditer(body):
            block = _balanced(body, body.index("{", mod.end() - 1))
            src = SOURCE_ATTR.search(block)
            if src:
                add(path.parent, src.group(1))

    for unit in terragrunt_units(tf_dir):
        body = strip_comments(
            (unit / "terragrunt.hcl").read_text(encoding="utf-8", errors="replace"))
        m = TERRAFORM_BLOCK.search(body)
        if not m:
            continue
        src = SOURCE_ATTR.search(_balanced(body, body.index("{", m.end() - 1)))
        if src:
            add(unit, src.group(1))

    return called


def root_modules(tf_dir: Path, extra: list[Path]) -> list[Path]:
    """Directories that get initialised and applied, as opposed to called.

    Detected structurally: a root module declares a backend or configures a
    provider; a child module does neither, which is a Terraform convention rather
    than this script's invention. `--root` covers a layout where that does not hold,
    such as a backend supplied entirely by `-backend-config`.
    """
    explicit = {d.resolve() for d in extra}
    found = set(explicit)
    called = called_modules(tf_dir)
    for path in tf_files(tf_dir):
        body = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        if BACKEND_BLOCK.search(body) or PROVIDER_BLOCK.search(body):
            found.add(path.parent.resolve())
    # Something calls it, so it is a child module however many root-shaped blocks it
    # contains — and one of those blocks being there is a `conventions` finding, not
    # a reason to reclassify the directory. `--root` still wins, for the layout this
    # gets wrong.
    return sorted((found - called) | explicit)


def gate_spec(state: Path, artifacts: Path) -> tuple[bool, str]:
    """The discovery skill's five gates, over the specification being implemented.

    Run for real, never with `--draft`. `--draft` always exits 0, so a draft run
    here would report a passing spec gate whatever the specification said — the
    decorative-gate failure this whole plugin is built to avoid. That is why
    `--artifacts` is required rather than optional.
    """
    proc = subprocess.run(
        [sys.executable, str(RUN_GATES), "--state", str(state),
         "--artifacts", str(artifacts)], capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode == 0:
        # One line on success rather than the whole report. A passing gate that
        # prints five paragraphs is how the one gate with something worth reading
        # gets scrolled past.
        return True, ""
    return False, (
        "The specification this Terraform implements does not pass its own gates, so "
        "there is nothing here worth checking yet. Fix the specification first — "
        "Terraform generated from a draft is a faithful implementation of a document "
        "nobody should be building from.\n\n" + out)


def gate_pins(tf_dir: Path, roots: list[Path]) -> tuple[bool, str]:
    problems: list[str] = []
    notes: list[str] = []

    for path in tf_files(tf_dir):
        rel = path.relative_to(tf_dir)
        body = strip_comments(path.read_text(encoding="utf-8", errors="replace"))

        m = REQUIRED_PROVIDERS.search(body)
        if m:
            block = _balanced(body, m.end() - 1)
            for entry in PROVIDER_ENTRY.finditer(block):
                name, inner = entry.group("name"), entry.group("body")
                src = SOURCE_ATTR.search(inner)
                ver = VERSION_ATTR.search(inner)
                if not src:
                    problems.append(
                        f"{rel}: provider `{name}` has no `source`. Without it "
                        f"Terraform assumes hashicorp/{name}, which is right often "
                        f"enough to be dangerous when it is wrong.")
                if not ver:
                    problems.append(
                        f"{rel}: provider `{name}` has no `version`. Every "
                        f"`terraform init` without a lock file would then resolve "
                        f"whatever is newest, so the tree reviewed is not the tree "
                        f"applied.")
                elif not EXACT_VERSION.fullmatch(ver.group(1).strip().lstrip("=~> ")):
                    problems.append(
                        f"{rel}: provider `{name}` is pinned as "
                        f"`{ver.group(1)}`, which does not name a patch release. "
                        f"Pin the exact version resolve_versions.py returned; raise "
                        f"it deliberately, with a changelog read.")

        for mod in MODULE_BLOCK.finditer(body):
            block = _balanced(body, body.index("{", mod.end() - 1))
            name = mod.group("name")
            src = SOURCE_ATTR.search(block)
            ver = VERSION_ATTR.search(block)
            if not src:
                problems.append(f"{rel}: module `{name}` has no `source`.")
                continue
            address = src.group(1)
            if address.startswith((".", "/")):
                continue  # local module: versioned by the repository it lives in
            if address.startswith(("git::", "github.com/", "git@")):
                if "?ref=" not in address:
                    problems.append(
                        f"{rel}: module `{name}` is a git source with no `?ref=`. "
                        f"It tracks the default branch, so the module can change "
                        f"under an unchanged commit of this repository.")
            elif REGISTRY_SOURCE.match(address):
                if not ver:
                    problems.append(
                        f"{rel}: registry module `{name}` (`{address}`) has no "
                        f"`version`.")
                elif not EXACT_VERSION.search(ver.group(1)):
                    problems.append(
                        f"{rel}: registry module `{name}` is pinned as "
                        f"`{ver.group(1)}`, which does not name a patch release.")

    # Every directory holding Terraform, not only detected roots. In a Terragrunt
    # stack nothing is a root module — the backend and provider come from
    # `root.hcl` — so checking roots alone would check nothing and report a pass.
    for directory in tf_dirs(tf_dir):
        rel = (directory.relative_to(tf_dir)
               if directory.is_relative_to(tf_dir) else directory)
        text = "\n".join(strip_comments(f.read_text(encoding="utf-8", errors="replace"))
                         for f in sorted(directory.glob("*.tf")))
        if not REQUIRED_VERSION.search(text):
            problems.append(
                f"{rel or '.'}: no `required_version`. Terraform's own version is "
                f"then whatever the person running it happens to have, and a state "
                f"file written by a newer version cannot be read by an older one. A "
                f"child module states what it needs too, rather than inheriting it "
                f"silently from whichever root called it.")

    for unit in terragrunt_units(tf_dir):
        rel = unit.relative_to(tf_dir) if unit.is_relative_to(tf_dir) else unit
        body = strip_comments(
            (unit / "terragrunt.hcl").read_text(encoding="utf-8", errors="replace"))
        m = TERRAFORM_BLOCK.search(body)
        if not m:
            continue  # a unit that only includes and sets inputs; nothing to pin
        block = _balanced(body, body.index("{", m.end() - 1))
        src = SOURCE_ATTR.search(block)
        if not src:
            continue
        address = src.group(1)
        if address.startswith((".", "/")) or "${" in address:
            continue  # local path, or built from a variable this cannot evaluate
        if "?ref=" not in address and not REGISTRY_SOURCE.match(address.split("//")[0]):
            problems.append(
                f"{rel}/terragrunt.hcl: `terraform.source` is `{address}` with no "
                f"`?ref=`. The unit then tracks whatever the default branch of that "
                f"module says today, so an unchanged commit of this repository "
                f"applies different infrastructure next week.")

    for root in roots:
        rel = root.relative_to(tf_dir) if root.is_relative_to(tf_dir) else root
        if not (root / ".terraform.lock.hcl").is_file():
            notes.append(
                f"{rel}: no `.terraform.lock.hcl`. It is written by `terraform init` "
                f"and must be committed — it is what makes the provider pins "
                f"reproducible including their checksums. Not a failure here because "
                f"nothing has been initialised yet.")

    multi = (".tool-versions", ".mise.toml")
    pinned_by_multi = any((tf_dir / f).is_file() for f in multi)

    if not pinned_by_multi and not any(
            (tf_dir / f).is_file() for f in (".terraform-version", ".opentofu-version")):
        problems.append(
            "no `.terraform-version` (or `.opentofu-version`, `.tool-versions`) at "
            "the root of the tree. The tool version has to be pinned in a file that "
            "tfenv, asdf or mise reads, or every engineer runs a different one and "
            "`required_version` only tells them so after the fact.")

    if is_terragrunt(tf_dir) and not pinned_by_multi and not (
            tf_dir / ".terragrunt-version").is_file():
        problems.append(
            "this is a Terragrunt stack with no `.terragrunt-version` (or "
            "`.tool-versions`) at the root of the tree. Terragrunt is a second tool "
            "with its own release cadence and its own breaking changes — the HCL "
            "commands were renamed in 0.78 — so an unpinned Terragrunt is a stack "
            "that behaves differently on each engineer's machine while every "
            "version in the repository says otherwise.")

    sections = []
    if problems:
        sections.append("\n".join("  - " + p for p in problems))
    if notes:
        sections.append("Notes, not failures:\n"
                        + "\n".join("  - " + n for n in notes))
    return (not problems), "\n\n".join(sections)


def gate_provenance(tf_dir: Path) -> tuple[bool, str]:
    """Every `.tf` and Terragrunt `.hcl` file says which decision put it there.

    A Terragrunt unit is where an environment's shape is actually decided — which
    module, which inputs, which dependencies — so it needs the header at least as
    much as the Terraform it points at.

    This is the machine-checkable half of rule 2 of the interview — write nothing
    you were not told. A generator's characteristic failure is not a wrong resource,
    it is a plausible one nobody asked for, and a plausible resource reviews clean.
    A file that cannot name the domain, ADR or open question it came from is a file
    that should not have been generated.

    It checks that the line exists, not that it is true; a header claiming ADR-007
    when ADR-007 says something else is beyond what any regex can know. It costs one
    line per file and makes the omission visible, which is the whole of its claim.
    """
    missing, empty = [], []
    for path in tf_files(tf_dir) + hcl_files(tf_dir):
        text = path.read_text(encoding="utf-8", errors="replace")
        # Size before content. A file truncated to zero bytes has no `# spec:` line
        # either, so it used to surface only as a provenance failure — which reads
        # as a missing comment and is fixed by adding one, while the real problem is
        # that the file has nothing in it.
        if not text.strip():
            empty.append(str(path.relative_to(tf_dir)))
            continue
        head = "\n".join(text.splitlines()[:12])
        if not PROVENANCE.search(head):
            missing.append(str(path.relative_to(tf_dir)))
    missing.sort()
    empty.sort()
    if not missing and not empty:
        return True, ""
    sections = []
    if empty:
        sections.append(
            "These files are empty:\n"
            + "\n".join("  - " + e for e in empty)
            + "\n\nAn empty `.tf` or `.hcl` is a file that was truncated, or one "
              "written and never filled in. Terraform reads it without complaint, so "
              "nothing downstream notices — the unit simply does nothing.")
    if missing:
        sections.append(_provenance_message(missing))
    return False, "\n\n".join(sections)


def _provenance_message(missing: list[str]) -> str:
    return (
        "These files carry no `# spec:` line in their first twelve lines:\n"
        + "\n".join("  - " + m for m in missing)
        + "\n\nAdd one naming the domain, ADR or open question that put the file "
          "there, for example:\n"
          "  # spec: domain 07-networking, ADR-004 — three private subnets, one per "
          "availability zone\n"
          "A resource nobody can trace to a decision is one nobody agreed to.")


# Secure defaults from the interview, as patterns over generated code. Each is a
# control the specification already asserts — §6 of the discovery skill: private
# subnets, least privilege, encryption in transit and at rest, no publicly reachable
# data stores, no long-lived static credentials — and until now nothing checked that
# the generated stack actually implemented them.
#
# The bar for inclusion is the same as the conventions gate: always wrong, never a
# judgement call. A public load balancer on 0.0.0.0/0:443 is normal and is not here;
# 0.0.0.0/0 to port 22 is not normal in any architecture this interview can produce.
#
# (id, what it means, why it matters)
GUARDRAILS = {
    "public-admin-ingress": (
        "an ingress rule open to the whole internet on an administrative port",
        "SSH, RDP and database ports reachable from 0.0.0.0/0 are found by scanners "
        "within minutes. The specification put compute in private subnets; this "
        "undoes that for one rule.",
    ),
    "public-data-store": (
        "a data store reachable from the internet",
        "§6 is explicit that no data store is publicly reachable. A managed database "
        "with a public endpoint is one credential away from being a breach.",
    ),
    "unencrypted-storage": (
        "encryption explicitly disabled",
        "Encryption at rest is a secure default the specification asserts, and "
        "turning it off after creation usually means recreating the resource.",
    ),
    "wildcard-iam": (
        "an IAM policy granting every action on every resource",
        "Least privilege is a secure default. A wildcard policy makes every other "
        "access control in the stack decorative.",
    ),
    "static-credentials": (
        "a long-lived credential written into the configuration",
        "§6 forbids long-lived static credentials, and anything in a .tf file is "
        "committed. Authentication comes from the environment the operator is in.",
    ),
    "unrestricted-mock-outputs": (
        "a Terragrunt `mock_outputs` with no `mock_outputs_allowed_terraform_commands`",
        "The mock is then used at `apply` too, which is how a placeholder value "
        "reaches real infrastructure.",
    ),
    "key-rotation-disabled": (
        "automatic key rotation turned off",
        "Rotation is free and on by default; switching it off is a decision that "
        "needs a reason recorded against it.",
    ),
    "secret-in-variable-default": (
        "a secret-shaped variable with a literal default",
        "A default is committed. Secrets come from the store domain 8 chose, never "
        "from a variable default or a tfvars file.",
    ),
    "vpc-without-flow-logs": (
        "a virtual network with no flow log anywhere in the tree",
        "Flow logs are the only record of what actually talked to what. Without "
        "them an incident review has no network evidence at all, and they cannot be "
        "backfilled — the traffic is gone.",
    ),
    "vpc-default-sg-unmanaged": (
        "a VPC whose default security group is not managed by this stack",
        "Every VPC gets a default security group allowing all traffic between its "
        "members, and anything launched without an explicit group lands in it. "
        "Taking ownership of the resource and leaving it with no rules is the only "
        "way to close it; it cannot be deleted.",
    ),
    "public-lb-without-access-logs": (
        "an internet-facing load balancer with no access logging",
        "The access log is the request-level record of who reached the application. "
        "It is the first thing asked for after an incident and, like flow logs, "
        "cannot be produced retrospectively.",
    ),
    "kms-key-without-policy": (
        "a KMS key with no explicit key policy",
        "Without a `policy` the key gets the default, which grants the account root "
        "full control and defers every decision to IAM. A key whose access is "
        "decided elsewhere is a key nobody can reason about from the stack.",
    ),
    "log-group-unencrypted": (
        "a log group with no encryption key",
        "Logs carry request paths, identifiers and error payloads. Encryption at "
        "rest is a secure default the specification asserts, and a log group is "
        "storage like any other.",
    ),
}

# The other half, and the half that was missing. Every check above fires on the
# *presence* of a bad attribute: a public port, a wildcard policy, encryption
# switched off. None fires on an *absence*, so a stack with no VPC flow logs, no
# load-balancer access logs, an unmanaged default security group and no KMS key
# policies went through all eight green — and an external scanner then found them.
#
# The bar is the same as above: always wrong, never a judgement call, and waivable
# through the `control` field like any other. A sibling resource that is required
# for the headline resource to be operable or auditable qualifies; a sibling that is
# merely a good idea does not.
#
# Resource names are the provider's, so a check is silent on a stack that does not
# use that provider. That is honest — this is a floor, not a survey — and a provider
# whose equivalent cannot be expressed as one resource is left out rather than
# approximated.
GUARDRAILS_OMISSION = {
    # (id, parent resource type, the sibling that must exist somewhere in the tree)
    "vpc-without-flow-logs": [
        ("aws_vpc", "aws_flow_log"),
        ("azurerm_virtual_network", "azurerm_network_watcher_flow_log"),
    ],
    "vpc-default-sg-unmanaged": [
        ("aws_vpc", "aws_default_security_group"),
    ],
}

# (id, resource type, attribute or block that must be inside it, exemption)
# An exemption is a pattern that makes the requirement inapplicable — an internal
# load balancer has no internet to log access from.
GUARDRAILS_REQUIRED_ATTR = [
    ("public-lb-without-access-logs", "aws_lb",
     re.compile(r"(?m)^\s*access_logs\s*[={]"),
     re.compile(r"(?m)^\s*internal\s*=\s*true")),
    ("kms-key-without-policy", "aws_kms_key",
     re.compile(r"(?m)^\s*policy\s*="), None),
    ("log-group-unencrypted", "aws_cloudwatch_log_group",
     re.compile(r"(?m)^\s*kms_key_id\s*="), None),
]

RESOURCE_BLOCK = re.compile(
    r'(?m)^\s*resource\s+"(?P<type>[A-Za-z0-9_]+)"\s+"(?P<name>[^"]+)"\s*\{')

SENSITIVE_PORTS = (22, 3389, 3306, 5432, 1433, 6379, 27017, 9200, 2379)
ANY_CIDR = re.compile(r"\"(?:0\.0\.0\.0/0|::/0)\"")
INGRESS_BLOCK = re.compile(r"(?m)^\s*ingress\s*\{")
PORT_ATTR = re.compile(r"(?:from_port|to_port)\s*=\s*(\d+)")
PUBLIC_ACL = re.compile(r"acl\s*=\s*\"public-read(?:-write)?\"")
PUBLIC_ACCESS = re.compile(r"publicly_accessible\s*=\s*true")
BLOCK_PUBLIC_FALSE = re.compile(
    r"(?:block_public_acls|block_public_policy|ignore_public_acls|"
    r"restrict_public_buckets)\s*=\s*false")
ENCRYPTION_OFF = re.compile(
    r"(?:storage_encrypted|encrypted|encryption_enabled|at_rest_encryption_enabled|"
    r"enable_encryption)\s*=\s*false")
ROTATION_OFF = re.compile(r"(?:enable_key_rotation|rotation_enabled)\s*=\s*false")
STATIC_CRED = re.compile(
    r"(?:access_key|secret_key|secret_access_key|client_secret|password)\s*=\s*"
    r"\"[^\"${}]{8,}\"")
WILDCARD_ACTION = re.compile(r"(?:\"Action\"|actions)\s*[=:]\s*\[?\s*\"\*\"")
WILDCARD_RESOURCE = re.compile(r"(?:\"Resource\"|resources)\s*[=:]\s*\[?\s*\"\*\"")
MOCK_OUTPUTS = re.compile(r"(?m)^\s*mock_outputs\s*=")
MOCK_ALLOWED = re.compile(r"mock_outputs_allowed_terraform_commands\s*=")
SECRET_NAME = re.compile(r"password|secret|token|private_key|passphrase|credential",
                         re.I)
DEFAULT_STRING = re.compile(r"(?m)^\s*default\s*=\s*\"([^\"]+)\"")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _guardrail_findings(tf_dir: Path) -> list[tuple[str, str, int]]:
    """(check id, file, line) for every secure default the code contradicts."""
    findings: list[tuple[str, str, int]] = []

    def note(check: str, path: Path, text: str, index: int) -> None:
        findings.append((check, str(path.relative_to(tf_dir)), _line_of(text, index)))

    for path in tf_files(tf_dir):
        raw = path.read_text(encoding="utf-8", errors="replace")
        body = strip_comments(raw)

        for m in INGRESS_BLOCK.finditer(body):
            block = _balanced(body, body.index("{", m.end() - 1))
            if not ANY_CIDR.search(block):
                continue
            ports = [int(p) for p in PORT_ATTR.findall(block)]
            if not ports or any(p in SENSITIVE_PORTS for p in ports) or 0 in ports:
                note("public-admin-ingress", path, body, m.start())

        for pattern, check in ((PUBLIC_ACCESS, "public-data-store"),
                               (PUBLIC_ACL, "public-data-store"),
                               (BLOCK_PUBLIC_FALSE, "public-data-store"),
                               (ENCRYPTION_OFF, "unencrypted-storage"),
                               (ROTATION_OFF, "key-rotation-disabled"),
                               (STATIC_CRED, "static-credentials")):
            for m in pattern.finditer(body):
                note(check, path, body, m.start())

        if WILDCARD_ACTION.search(body) and WILDCARD_RESOURCE.search(body):
            note("wildcard-iam", path, body, WILDCARD_ACTION.search(body).start())

        for var in VARIABLE_BLOCK.finditer(body):
            if not SECRET_NAME.search(var.group("name")):
                continue
            block = _balanced(body, body.index("{", var.end() - 1))
            default = DEFAULT_STRING.search(block)
            if default and default.group(1).strip():
                note("secret-in-variable-default", path, body, var.start())

    for path in hcl_files(tf_dir):
        body = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        for m in MOCK_OUTPUTS.finditer(body):
            if not MOCK_ALLOWED.search(body):
                note("unrestricted-mock-outputs", path, body, m.start())

    findings.extend(_omission_findings(tf_dir))
    return findings


def _resources(tf_dir: Path) -> list[tuple[str, Path, str, int, str]]:
    """(type, file, comment-stripped body, offset, block body) for every resource."""
    out = []
    for path in tf_files(tf_dir):
        body = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        for m in RESOURCE_BLOCK.finditer(body):
            block = _balanced(body, body.index("{", m.end() - 1))
            out.append((m.group("type"), path, body, m.start(), block))
    return out


def _omission_findings(tf_dir: Path) -> list[tuple[str, str, int]]:
    """Required siblings and attributes that are absent.

    Absence is checked across the whole tree rather than per file, because the
    module layout decides which file a sibling lands in and a finding that depended
    on that would be a finding about the layout. A flow log in `logging.tf` is a
    flow log.
    """
    findings: list[tuple[str, str, int]] = []
    resources = _resources(tf_dir)
    present = {kind for kind, _, _, _, _ in resources}

    for check, pairs in GUARDRAILS_OMISSION.items():
        for parent, sibling in pairs:
            if parent not in present or sibling in present:
                continue
            for kind, path, body, start, _block in resources:
                if kind != parent:
                    continue
                findings.append((check, str(path.relative_to(tf_dir)),
                                 _line_of(body, start)))

    for check, kind_wanted, required, exempt in GUARDRAILS_REQUIRED_ATTR:
        for kind, path, body, start, block in resources:
            if kind != kind_wanted or required.search(block):
                continue
            if exempt is not None and exempt.search(block):
                continue
            findings.append((check, str(path.relative_to(tf_dir)),
                             _line_of(body, start)))

    return findings


def _waived(state: Path) -> set[str]:
    """Guardrail ids a waiver in the state file names verbatim.

    The interview already records deviations from the secure defaults — control,
    deviation, reason, who accepted it — so a guardrail finding the specification
    knowingly accepted must not fail this gate twice. Matching is on the id appearing
    literally in the waiver text, not on meaning: `check_contradictions.py` matches
    words rather than sense and says so, and a looser match here would quietly waive
    things nobody agreed to. Every finding prints its id so the string is
    copy-pasteable into the waiver.
    """
    try:
        import _state
        loaded = _state.load(state)
    except Exception:  # noqa: BLE001 — the spec gate reports a bad state file
        return set()
    text = " ".join(
        f"{w.get('control', '')} {w.get('deviation', '')} {w.get('reason', '')}"
        for w in loaded.get("waivers", []) if isinstance(w, dict))
    return {check for check in GUARDRAILS if check in text}


def _waiver_text(state: Path) -> str:
    """Every waiver's control, deviation and reason, as one lowercase string.

    Used to match a scanner's own check id — `CKV_AWS_86` — against a waiver, so the
    single record of what was accepted and by whom stays `discovery-state.json`
    whichever tool found the deviation. The scanner's config file then carries only
    false positives, which is what a tool-specific file should hold.
    """
    try:
        import _state
        loaded = _state.load(state)
    except Exception:  # noqa: BLE001
        return ""
    return " ".join(
        f"{w.get('control', '')} {w.get('deviation', '')} {w.get('reason', '')}"
        for w in loaded.get("waivers", []) if isinstance(w, dict)).lower()


# Scanners the interview can have chosen in domain 9a, and how to run one over a
# directory. Nothing is installed by this plugin; a scanner the specification named
# and the machine does not have is reported as not run, never as passed.
#
# The target is always `.` and the process always runs with `cwd` set to the stack
# root, because every one of these discovers its configuration relative to the
# current working directory rather than to the directory it was pointed at. Run from
# anywhere else, a project's own `.checkov.yaml` is ignored and the gate reports
# findings that were considered and reasoned about weeks ago. One stack showed
# thirty findings or zero, decided entirely by which directory the command was typed
# in.
SCANNERS = {
    "checkov": ["checkov", "--quiet", "--compact", "-d", "."],
    "tfsec": ["tfsec", "--no-colour", "."],
    "trivy": ["trivy", "config", "--quiet", "."],
    "terrascan": ["terrascan", "scan", "--iac-dir", "."],
}

# Config files each scanner reads from the working directory. Named explicitly where
# the tool supports it, so the report says which config was in force rather than
# leaving it to discovery.
SCANNER_CONFIGS = {
    "checkov": ((".checkov.yaml", ".checkov.yml"), "--config-file"),
    "tfsec": ((".tfsec.yml", ".tfsec.yaml"), "--config-file"),
    "trivy": (("trivy.yaml",), "--config"),
    "terrascan": (("terrascan.toml",), "--config-path"),
}

# Check identifiers the four scanners emit: CKV_AWS_86, CKV2_AWS_5, AVD-AWS-0053,
# AC_AWS_0207. Parsed so a finding can be matched against a waiver's `control` field
# the same way a built-in id is — otherwise a deliberate, owner-accepted deviation
# lives in the scanner's own config file when the scanner found it and in
# discovery-state.json when this gate found it, which is two records of one decision.
SCANNER_CHECK_ID = re.compile(r"\b(CKV\d?_[A-Z0-9]+_\d+|AVD-[A-Z]+-\d+|AC_[A-Z0-9]+_\d+)\b")


def gate_guardrails(tf_dir: Path, state: Path) -> tuple[bool | None, str]:
    """Secure defaults, checked against the code rather than asserted in a document.

    Two halves. A built-in baseline of eight patterns that needs no tooling, so the
    gate is never silently absent; and the policy scanner the specification chose in
    domain 9a, run when it is installed.

    A finding the interview knowingly accepted is waived rather than failed — the
    waiver already names the control, the deviation, the reason and who accepted it,
    and refusing it here a second time would mean a recorded decision cannot be
    implemented.
    """
    waived = _waived(state)
    findings = _guardrail_findings(tf_dir)

    blocking = [f for f in findings if f[0] not in waived]
    accepted = [f for f in findings if f[0] in waived]

    lines: list[str] = []
    if blocking:
        lines.append("These contradict a secure default the specification asserts, "
                     "and no waiver records the deviation:\n")
        for check, rel, line in blocking:
            what, why = GUARDRAILS[check]
            lines.append(f"  [{check}] {rel}:{line}")
            lines.append(f"      {what}. {why}")
        lines.append(
            "\nTwo ways forward, and only two. Fix the code, or have the deviation "
            "accepted: add a waiver to discovery-state.json naming the control, the "
            "deviation, the reason and who accepted it, with the id above in the "
            "`control` field so this gate can match it. Generating it anyway and "
            "mentioning it afterwards is how an accepted risk becomes an unnoticed "
            "one — and an interview that recorded no waiver did not accept it.")

    if accepted:
        lines.append("\nWaived by the specification, reported rather than blocked:")
        for check, rel, line in accepted:
            lines.append(f"  [{check}] {rel}:{line} — a waiver names this control")

    # The scanner the interview chose, where it named one.
    scanner_note = ""
    chosen = ""
    try:
        import _state
        delivery = _state.load(state).get("domains", {}).get("09-delivery", {})
        chosen = str((delivery.get("answers") or {}).get("policy_pre_apply", "")).lower()
    except Exception:  # noqa: BLE001
        chosen = ""
    # "none, reviewed by hand" is an answer, not a tool. Without this a specification
    # that deliberately chose no scanner reads as one naming a scanner this gate
    # cannot run — the opposite of what was decided. Matched on how the answer opens,
    # because the rest of it is the reason rather than the choice.
    if not any(s in chosen for s in SCANNERS) and re.match(
            r"^(none|no\b|nothing|n/?a\b|tbd|undecided|not\b|manual)",
            chosen.strip(" .")):
        chosen = ""

    ran_scanner: bool | None = True
    for name, argv in SCANNERS.items():
        if name not in chosen:
            continue
        if shutil.which(name) is None:
            ran_scanner = None
            scanner_note = (
                f"\nThe specification chose `{name}` for pre-apply policy "
                f"(domain 9a), and it is not on PATH, so it did not run. The "
                f"{len(GUARDRAILS)} built-in checks in this gate are a floor, not a "
                f"substitute — install it before treating this stack as scanned.")
            break

        # Run from the stack root, with its own config named explicitly. Both
        # matter: every one of these tools discovers configuration relative to the
        # working directory, not to the directory it scans.
        config_note = ""
        names, flag = SCANNER_CONFIGS.get(name, ((), ""))
        for candidate in names:
            if (tf_dir / candidate).is_file():
                argv = argv + [flag, candidate]
                config_note = f" using {candidate}"
                break
        proc = subprocess.run(argv, cwd=tf_dir, capture_output=True, text=True)
        if proc.returncode != 0:
            out = (proc.stdout + proc.stderr).strip()
            ids = set(SCANNER_CHECK_ID.findall(out))
            waivers = _waiver_text(state)
            waived_ids = {i for i in ids if i.lower() in waivers}
            if ids and ids == waived_ids:
                lines.append(
                    f"\n{name} reported findings{config_note}, and a waiver in "
                    f"discovery-state.json names every one of them "
                    f"({', '.join(sorted(waived_ids))}). Reported, not blocked:\n"
                    + out)
                scanner_note = ""
                break
            blocking_ids = sorted(ids - waived_ids)
            lines.append(f"\n{name} reported findings{config_note}:\n" + out)
            if waived_ids:
                lines.append(
                    f"\nWaived by the specification: {', '.join(sorted(waived_ids))}. "
                    f"Still blocking: "
                    + (", ".join(blocking_ids) if blocking_ids
                       else "findings whose check id could not be read from the "
                            "output, so none of them could be matched to a waiver"))
            else:
                lines.append(
                    "\nA finding here is accepted the same way a built-in one is: "
                    "put the scanner's own check id in a waiver's `control` field in "
                    "discovery-state.json, with the deviation, the reason and who "
                    "accepted it. The state file stays the single record of what was "
                    "decided; the scanner's config file carries only false positives.")
            return False, "\n".join(lines)
        scanner_note = f"\n`{name}` scanned this stack{config_note} and reported nothing."
        break
    else:
        if not chosen:
            scanner_note = (
                f"\nThe specification named no pre-apply policy scanner in domain 9a, "
                f"so only the {len(GUARDRAILS)} built-in checks ran. They are a "
                f"floor: they catch what is always wrong, not what is wrong here.")
        else:
            # A scanner this gate cannot drive is not the same as no scanner, and
            # printing nothing made the two indistinguishable: the run reads clean
            # while the tool the specification chose never ran and never said so.
            ran_scanner = None
            scanner_note = (
                f"\nThe specification chose {chosen!r} for pre-apply policy (domain "
                f"9a), which this gate cannot run — it drives "
                f"{', '.join(sorted(SCANNERS))}. Only the {len(GUARDRAILS)} built-in "
                f"checks ran, so run the chosen scanner yourself before treating this "
                f"stack as scanned.")

    lines.append(scanner_note)
    output = "\n".join(l for l in lines if l is not None).strip()

    if blocking:
        return False, output
    if ran_scanner is None:
        return None, output
    # The scanner note prints on a clean pass too. "guardrails pass" reads stronger
    # than it is when only the eight built-in checks ran, and a gate overstating its
    # own coverage is the same defect as a gate that did not run reporting a pass.
    return True, output


def gate_conventions(tf_dir: Path) -> tuple[bool, str]:
    """Four conventions a reviewer will expect, and a regex can actually check.

    These are the mechanical subset of `references/conventions.md`. Everything else
    in that file — naming, `for_each` over `count`, `moved` blocks, where a `local`
    belongs — needs judgement about the code, and a gate that guessed at it would
    produce findings nobody can act on. Four rules that are always right are worth
    more than twenty that are usually right.

    Each is a rule `tflint` would also enforce, chosen because the failure it
    prevents is concrete rather than aesthetic:

    - **A `variable` with no `description`.** The variable file is the interface;
      an undescribed input is one the next person guesses at, and a guess about an
      input is applied infrastructure.
    - **A `variable` with no `type`.** Untyped means `any`, so a string arrives
      where a list was meant and the error surfaces inside a module, far from the
      call that caused it.
    - **An `output` with no `description`.** An output is a published interface;
      other stacks consume it by name and cannot see why it exists.
    - **A `provider` block inside a child module.** It cannot then be used with
      `for_each` or `count`, and removing one later is a breaking change to every
      caller. Providers are configured by the root module, or generated by
      Terragrunt from `root.hcl`.
    """
    problems: list[str] = []
    called = called_modules(tf_dir)

    for path in tf_files(tf_dir):
        rel = path.relative_to(tf_dir)
        body = strip_comments(path.read_text(encoding="utf-8", errors="replace"))

        for var in VARIABLE_BLOCK.finditer(body):
            block = _balanced(body, body.index("{", var.end() - 1))
            name = var.group("name")
            if not DESCRIPTION_ATTR.search(block):
                problems.append(
                    f"{rel}: variable `{name}` has no `description`. The variables "
                    f"file is this module's interface, and an undescribed input is "
                    f"one the next person guesses at.")
            if not TYPE_ATTR.search(block):
                problems.append(
                    f"{rel}: variable `{name}` has no `type`, so it is `any`. A "
                    f"string arriving where a list was meant then fails somewhere "
                    f"inside the module rather than at the call that caused it.")

        for out in OUTPUT_BLOCK.finditer(body):
            block = _balanced(body, body.index("{", out.end() - 1))
            if not DESCRIPTION_ATTR.search(block):
                problems.append(
                    f"{rel}: output `{out.group('name')}` has no `description`. An "
                    f"output is a published interface — whoever consumes it sees the "
                    f"name and nothing else.")

        if PROVIDER_BLOCK.search(body) and path.parent.resolve() in called:
            problems.append(
                f"{rel}: a `provider` block in what is not a root module. A module "
                f"that configures its own provider cannot be used with `for_each` or "
                f"`count`, and taking the block out later is a breaking change for "
                f"every caller. Configure providers in the root module, or let "
                f"Terragrunt generate them from `root.hcl`.")

    if not problems:
        return True, ""
    return False, "\n".join("  - " + p for p in problems)


DEPENDENCY_BLOCK = re.compile(r'(?m)^\s*dependency\s+"(?P<name>[^"]+)"\s*\{')
DEPENDENCIES_PATHS = re.compile(r"(?m)^\s*paths\s*=\s*\[(?P<body>[^\]]*)\]")
CONFIG_PATH = re.compile(r'(?m)^\s*config_path\s*=\s*"(?P<path>[^"]+)"')


def dependency_edges(tf_dir: Path) -> dict[Path, set[Path]]:
    """unit -> the units it declares a dependency on.

    Read from `dependency` blocks and from `dependencies { paths = [...] }`, which
    are the two ways a Terragrunt unit states an ordering. Paths built from a
    variable are skipped rather than guessed at.
    """
    edges: dict[Path, set[Path]] = {}
    for unit in terragrunt_units(tf_dir):
        body = strip_comments(
            (unit / "terragrunt.hcl").read_text(encoding="utf-8", errors="replace"))
        targets: set[Path] = set()
        for m in DEPENDENCY_BLOCK.finditer(body):
            block = _balanced(body, body.index("{", m.end() - 1))
            cp = CONFIG_PATH.search(block)
            if cp and "${" not in cp.group("path"):
                targets.add((unit / cp.group("path")).resolve())
        for m in DEPENDENCIES_PATHS.finditer(body):
            for raw in re.findall(r'"([^"]+)"', m.group("body")):
                if "${" not in raw:
                    targets.add((unit / raw).resolve())
        edges[unit.resolve()] = {x for x in targets if x.is_dir()}
    return edges


def dependency_cycles(edges: dict[Path, set[Path]]) -> list[list[Path]]:
    """Every cycle in the unit graph, as a path back to its own start.

    `terragrunt hcl validate` does not catch this: it evaluates each unit's
    configuration without resolving the graph, so a stack where compute depends on
    observability for a log group name and observability depends on compute for its
    alarm dimensions validates clean. Only `run --all` finds it, and that needs
    credentials — so the first person to meet it meets it at the first real plan.
    """
    cycles: list[list[Path]] = []
    seen_cycles: set[tuple[Path, ...]] = set()
    visiting: list[Path] = []

    def walk(node: Path, stack: list[Path], done: set[Path]) -> None:
        if node in stack:
            cycle = stack[stack.index(node):] + [node]
            key = tuple(sorted(set(cycle)))
            if key not in seen_cycles:
                seen_cycles.add(key)
                cycles.append(cycle)
            return
        if node in done:
            return
        stack.append(node)
        for target in sorted(edges.get(node, ())):
            walk(target, stack, done)
        stack.pop()
        done.add(node)

    done: set[Path] = set()
    for node in sorted(edges):
        walk(node, visiting, done)
    return cycles


def gate_graph(tf_dir: Path) -> tuple[bool | None, str]:
    """The unit dependency graph is a graph and not a loop. Static, no binaries."""
    if not terragrunt_units(tf_dir):
        return True, ""
    cycles = dependency_cycles(dependency_edges(tf_dir))
    if not cycles:
        return True, ""
    lines = ["These units depend on each other in a circle, so no apply order "
             "exists:", ""]
    for cycle in cycles:
        shown = [str(c.relative_to(tf_dir)) if c.is_relative_to(tf_dir) else str(c)
                 for c in cycle]
        lines.append("  " + " -> ".join(shown))
    lines.append("")
    lines.append(
        "Break it by deciding which module owns the shared resource. The rule in "
        "`references/layout.md`: a resource belongs to the module that writes to "
        "it, and where two modules both claim it, the one earlier in apply order "
        "wins. A log group written to by compute belongs to compute, even though "
        "observability reads it.")
    return False, "\n".join(lines)


def _tool(tf_dir: Path) -> str | None:
    """The binary this tree is written for, or None if neither is installed.

    A tree carrying `.opentofu-version` is an OpenTofu tree and gets `tofu` where it
    is available; everything else prefers `terraform` and falls back. Running the
    wrong one is not harmless — they diverge on state file versions.
    """
    if (tf_dir / ".opentofu-version").is_file() and shutil.which("tofu"):
        return "tofu"
    for candidate in ("terraform", "tofu"):
        if shutil.which(candidate):
            return candidate
    return None


# Phrases Terraform and Terragrunt use when a command failed because it could not
# reach a registry, rather than because the configuration is wrong. The distinction
# has to be drawn from the message because the exit code is the same for both, and
# the two need opposite responses: one is "you are offline", the other is "this stack
# is broken". Anything not matching here is treated as a real failure — a wrong
# `source` that slipped through as "could not run" is the expensive direction.
NETWORK_MARKERS = (
    "failed to query available provider packages",
    "could not connect",
    "no such host",
    "connection refused",
    "network is unreachable",
    "i/o timeout",
    "context deadline exceeded",
    "tls handshake timeout",
    "temporary failure in name resolution",
    "error installing provider",
    "failed to download module",
    "could not download module",
    "error downloading",
)


def _terragrunt() -> tuple[str, tuple[int, ...]] | None:
    """The `terragrunt` binary and its version, or None if it is not installed."""
    if shutil.which("terragrunt") is None:
        return None
    proc = subprocess.run(["terragrunt", "--version"], capture_output=True, text=True)
    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", proc.stdout + proc.stderr)
    return "terragrunt", tuple(int(g) for g in m.groups()) if m else ()


def _tg_hcl(argv: list[str], version: tuple[int, ...]) -> list[str]:
    """`hcl fmt`/`hcl validate` on 0.78 and later, `hclfmt`/`hclvalidate` before it.

    The subcommand was renamed in the 0.78 CLI reorganisation, and both spellings
    are still in the field because `.terragrunt-version` is pinned per repository.
    Dispatching on the reported version is deterministic; retrying after a failure
    is not, since an unknown subcommand and a real formatting failure both exit
    non-zero and the gate would report the wrong one.
    """
    if version >= TERRAGRUNT_HCL_CLI_FROM:
        return ["terragrunt", "hcl"] + argv
    joined = {"fmt": "hclfmt", "validate": "hclvalidate"}[argv[0]]
    rest = ["--terragrunt-check" if a == "--check" else a for a in argv[1:]]
    return ["terragrunt", joined] + rest


def _combine(parts: list[tuple[bool | None, str, str]]) -> tuple[bool | None, str]:
    """One verdict from the Terraform half and the Terragrunt half.

    Any failure fails. Otherwise any half that could not run makes the whole gate
    "did not run", because a stack half-checked is not a stack checked — and a gate
    that reports a pass on the strength of the half that happened to be installed is
    the silent pass this plugin exists to avoid.
    """
    rendered = "\n\n".join(f"{label}:\n{out}" for ok, label, out in parts
                            if out and ok is not True)
    if any(ok is False for ok, _, _ in parts):
        return False, rendered
    if any(ok is None for ok, _, _ in parts):
        return None, rendered
    return True, ""


def gate_fmt(tf_dir: Path) -> tuple[bool | None, str]:
    """`terraform fmt -check` over the modules, `terragrunt hcl fmt --check` over
    the units. Both halves, every run.

    Formatting is the cheapest thing a reviewer should never have to think about,
    and the two tools format different files — `terraform fmt` does not touch
    `terragrunt.hcl`, and `terragrunt hcl fmt` does not touch `.tf`. Running only
    one leaves half the stack to be reformatted by whoever notices in CI, which
    turns every subsequent diff into noise.
    """
    parts: list[tuple[bool | None, str, str]] = []

    if tf_files(tf_dir):
        tool = _tool(tf_dir)
        if tool is None:
            parts.append((None, "terraform fmt",
                          "neither `terraform` nor `tofu` is on PATH, so the "
                          "Terraform half was not checked"))
        else:
            # Run from inside the tree with `.` as the target, rather than handing
            # terraform an absolute path from an unrelated working directory. On a
            # path behind a symlink — macOS resolving /tmp to /private/tmp is the
            # everyday case — terraform relativises the argument against its own cwd
            # and reports "No file or directory at ../../private/tmp/...", which
            # reads as a formatting failure and is not one.
            proc = subprocess.run(
                [tool, "fmt", "-check", "-recursive", "-no-color", "."],
                cwd=tf_dir, capture_output=True, text=True)
            parts.append((
                proc.returncode == 0, "terraform fmt",
                "" if proc.returncode == 0 else
                (f"These files are not canonically formatted:\n"
                 f"{(proc.stdout + proc.stderr).strip()}\n\n"
                 f"Run: {tool} fmt -recursive   (from {tf_dir})")))

    if is_terragrunt(tf_dir):
        tg = _terragrunt()
        if tg is None:
            parts.append((None, "terragrunt hcl fmt",
                          "this is a Terragrunt stack and `terragrunt` is not on "
                          "PATH, so the unit files were not checked"))
        else:
            _, version = tg
            proc = subprocess.run(
                _tg_hcl(["fmt", "--check", "--diff"], version) + ["--no-color"],
                cwd=tf_dir, capture_output=True, text=True)
            parts.append((
                proc.returncode == 0, "terragrunt hcl fmt",
                "" if proc.returncode == 0 else
                (f"These Terragrunt files are not canonically formatted:\n"
                 f"{(proc.stdout + proc.stderr).strip()}\n\n"
                 f"Run: terragrunt hcl fmt   (from {tf_dir})")))

    if not parts:
        return None, "nothing to format: no .tf files and no Terragrunt units"
    return _combine(parts)


def gate_validate(tf_dir: Path, roots: list[Path]) -> tuple[bool | None, str]:
    """`terraform validate` in every module, `terragrunt hcl validate` over the stack.

    Terraform is validated per directory rather than per detected root module. In a
    Terragrunt stack nothing declares a backend or a provider — `root.hcl` generates
    both — so there are no root modules to find, and validating only those would
    validate nothing and report a pass. `init -backend=false` in a child module
    infers its providers from `required_providers` and validates it standalone.

    A failed `init` is reported as "could not run" when its output matches a known
    connectivity failure, and as a failure otherwise — see `NETWORK_MARKERS`.

    `terragrunt hcl validate` parses and evaluates the unit configurations: that the
    includes resolve, the sources are readable and the HCL is well-formed. It does
    not resolve `dependency` outputs and is not a plan.
    """
    parts: list[tuple[bool | None, str, str]] = []
    directories = tf_dirs(tf_dir)

    if directories:
        tool = _tool(tf_dir)
        if tool is None:
            parts.append((None, "terraform validate",
                          "neither `terraform` nor `tofu` is on PATH, so no module "
                          "was validated"))
        else:
            failures, unreachable = [], []
            for directory in directories:
                init = subprocess.run(
                    [tool, "init", "-backend=false", "-input=false", "-no-color"],
                    cwd=directory, capture_output=True, text=True)
                if init.returncode != 0:
                    out = (init.stdout + init.stderr).strip()
                    bucket = (unreachable
                              if any(m in out.lower() for m in NETWORK_MARKERS)
                              else failures)
                    bucket.append(f"{directory}: `{tool} init` failed\n{out}")
                    continue
                val = subprocess.run([tool, "validate", "-no-color"],
                                     cwd=directory, capture_output=True, text=True)
                if val.returncode != 0:
                    failures.append(
                        f"{directory}:\n{(val.stdout + val.stderr).strip()}")
            if failures:
                joined = "\n\n".join(failures)
                # `required_version` is the last place anyone looks, and the raw
                # message names the constraint without saying that the constraint is
                # the problem. resolve_versions.py now emits a floor the installed
                # binary satisfies; this is for the trees written before it did.
                if "unsupported terraform core version" in joined.lower():
                    joined += (
                        f"\n\nThis is the `required_version` constraint, not the "
                        f"configuration: the {tool} on this machine is older than the "
                        f"floor these modules declare. Either install the version "
                        f"`.terraform-version` pins, or lower the floor to the "
                        f"version everyone is actually running — "
                        f"`resolve_versions.py --hcl` emits one the installed binary "
                        f"satisfies.")
                parts.append((False, "terraform validate", joined))
            elif unreachable:
                parts.append((None, "terraform validate", (
                    f"`{tool} init` could not reach the registry for "
                    f"{len(unreachable)} module(s), so they were not validated. This "
                    f"is a connectivity failure, not a verdict on the "
                    f"configuration.\n\n" + "\n\n".join(unreachable))))
            else:
                parts.append((True, "terraform validate", ""))

    if is_terragrunt(tf_dir):
        tg = _terragrunt()
        if tg is None:
            parts.append((None, "terragrunt hcl validate",
                          "this is a Terragrunt stack and `terragrunt` is not on "
                          "PATH, so the units were not validated"))
        else:
            _, version = tg
            env = dict(os.environ)
            # Terragrunt defaults to `tofu`. A tree pinned to Terraform would fail
            # with "tofu not found", which reads as a broken stack rather than as a
            # missing binary nobody asked for.
            chosen = _tool(tf_dir)
            if chosen and "TG_TF_PATH" not in env and "TERRAGRUNT_TFPATH" not in env:
                env["TG_TF_PATH"] = chosen
            proc = subprocess.run(
                _tg_hcl(["validate"], version) + ["--no-color"],
                cwd=tf_dir, capture_output=True, text=True, env=env)
            out = (proc.stdout + proc.stderr).strip()
            if proc.returncode == 0:
                parts.append((True, "terragrunt hcl validate", ""))
            elif any(m in out.lower() for m in NETWORK_MARKERS):
                parts.append((None, "terragrunt hcl validate", (
                    "could not reach the registry, so the units were not "
                    "validated.\n\n" + out)))
            else:
                parts.append((False, "terragrunt hcl validate", out))

    if not parts:
        return None, ("nothing to validate: no .tf files and no Terragrunt units. "
                      "Pass --root if this tree is laid out unusually.")
    return _combine(parts)


def gate_secrets(tf_dir: Path) -> tuple[bool | None, str]:
    proc = subprocess.run([sys.executable, str(SCAN_SECRETS), str(tf_dir)],
                          capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode == 0:
        return True, ""
    if proc.returncode == 3:
        return None, ("gitleaks is not installed, so nothing was scanned. Install it "
                      "before committing: a pass would otherwise mean nothing.\n\n" + out)
    return False, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state", required=True)
    ap.add_argument("--tf-dir", required=True)
    ap.add_argument("--artifacts")
    ap.add_argument("--root", action="append", default=[])
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--skip", action="append", default=[], choices=GATES)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    state = Path(args.state).expanduser().resolve()
    tf_dir = Path(args.tf_dir).expanduser().resolve()
    artifacts = Path(args.artifacts).expanduser().resolve() if args.artifacts else None

    if artifacts is None and not args.draft:
        print("error: --artifacts is required unless --draft is given. Without it "
              "the specification's own gates cannot run, and a Terraform tree is "
              "only as trustworthy as the specification it implements.",
              file=sys.stderr)
        return 2

    if not tf_dir.is_dir():
        print(f"error: --tf-dir {tf_dir} is not a directory. Scanning nothing is not "
              f"a pass.", file=sys.stderr)
        return 2
    if not tf_files(tf_dir) and not hcl_files(tf_dir):
        print(f"error: no .tf or Terragrunt .hcl files under {tf_dir}. Nothing was "
              f"checked, and that is reported as an error rather than a clean run — "
              f"the two look identical in a summary and need different fixes.",
              file=sys.stderr)
        return 2

    roots = root_modules(tf_dir, [Path(r).expanduser().resolve() for r in args.root])

    runners = {
        "spec": (lambda: gate_spec(state, artifacts)) if artifacts else
                (lambda: (None, "no --artifacts given, so the specification's own "
                                "gates did not run")),
        "pins": lambda: gate_pins(tf_dir, roots),
        "provenance": lambda: gate_provenance(tf_dir),
        "conventions": lambda: gate_conventions(tf_dir),
        "guardrails": lambda: gate_guardrails(tf_dir, state),
        "graph": lambda: gate_graph(tf_dir),
        "fmt": lambda: gate_fmt(tf_dir),
        "validate": lambda: gate_validate(tf_dir, roots),
        "secrets": lambda: gate_secrets(tf_dir),
    }

    results = []
    for name in GATES:
        if name in args.skip:
            results.append({"gate": name, "status": "skipped", "output": "",
                            "note": "skipped on the command line"})
            continue
        ok, out = runners[name]()
        status = {True: "pass", False: "fail", None: "not-run"}[ok]
        results.append({"gate": name, "status": status, "output": out,
                        "note": out if status == "not-run" else None})

    failed = [r for r in results if r["status"] == "fail"]
    absent = [r for r in results if r["status"] in ("skipped", "not-run")]

    if args.json:
        print(json.dumps({"state": str(state), "tf_dir": str(tf_dir),
                          "roots": [str(r) for r in roots], "draft": args.draft,
                          "results": results, "ok": not failed}, indent=2))
        return 0 if (args.draft or not failed) else 1

    print("IaC gate summary")
    print("")
    def show(paths: list[Path]) -> str:
        return ", ".join(
            str(q.relative_to(tf_dir)) if q.is_relative_to(tf_dir) else str(q)
            for q in paths) or "none"

    units = terragrunt_units(tf_dir)
    print(f"  tree:    {tf_dir}")
    print(f"  stack:   " + ("Terragrunt over Terraform" if units or is_terragrunt(tf_dir)
                            else "plain Terraform, no Terragrunt units"))
    print(f"  modules: {show(tf_dirs(tf_dir))}")
    if units:
        print(f"  units:   {show(units)}")
    if roots:
        print(f"  roots:   {show(roots)}")
    print("")
    for r in results:
        mark = {"pass": "pass", "fail": "FAIL", "skipped": "skip",
                "not-run": "----"}[r["status"]]
        line = f"  [{mark}] {r['gate']}"
        if r["status"] == "fail":
            line += f"  — {DESCRIPTIONS[r['gate']]}"
        elif r["status"] == "skipped":
            line += "  — skipped on the command line"
        elif r["status"] == "not-run":
            line += "  — did not run"
        print(line)
    print("")
    for r in results:
        # A passing gate with something to say still says it. `guardrails` passes
        # while reporting a deviation the specification waived, and a waived
        # deviation that vanishes from the report is a deviation nobody sees again.
        if not r["output"]:
            continue
        print("=" * 72)
        print(r["gate"])
        print("=" * 72)
        print(r["output"])
        print("")

    if args.draft:
        print("Draft mode: reporting only. Nothing here blocks. Run again without "
              "--draft before committing.")
    elif failed:
        print(f"{len(failed)} gate(s) failed. Fix the cause; a Terraform tree that "
              f"does not pass these is not ready to be reviewed, let alone applied.")
    elif absent:
        print("Every gate that ran passed, but "
              + ", ".join(r["gate"] for r in absent)
              + " did not run. A gate that did not run has not passed.")
    else:
        print("Every gate passed. This stack is ready for review — which is not the "
              "same as ready to apply: nothing here has seen a plan against a real "
              "account.")

    return 0 if (args.draft or not failed) else 1


if __name__ == "__main__":
    sys.exit(main())

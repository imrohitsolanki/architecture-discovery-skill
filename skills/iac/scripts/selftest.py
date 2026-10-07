#!/usr/bin/env python3
"""Prove every IaC gate still catches the thing it exists to catch.

Run it after changing any script in this directory:

    python3 skills/iac/scripts/selftest.py

Exit 0  every gate accepted its clean case and rejected its violating case.
Exit 1  a gate let a violation through, or rejected a clean tree.

It mirrors `skills/discover/scripts/selftest.py` and for the same reason: a gate that
never fires is indistinguishable from a gate that always passes, and the second reads
as a clean bill of health. So every check runs twice, against a tree it must accept
and a tree it must reject, asserted on exit codes rather than on report wording.

Fixtures are built here rather than committed. A committed tree drifts from the rules
it is supposed to pin; a one-line mutation of `CLEAN_TF` states in one place exactly
what makes each case a violation.

What it does not cover
    `fmt` and `validate` need the `terraform` binary, and `validate` additionally
    needs a reachable registry. Both are skipped loudly when unavailable rather than
    silently passed. `resolve_versions.py` needs the network; its offline path is
    asserted, its online path is not — a test that fails on a train is a test that
    gets deleted.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _shared import BLOCK_MUTATING_IAC, DISCOVER_SCRIPTS  # noqa: E402


def _load(path: Path, name: str):
    """Import a module by file path, under a name of our choosing.

    Both skills have a `selftest.py`, so `import selftest` resolves to whichever
    directory is earlier on `sys.path` — which is this one when the harness runs as
    `__main__`, and the other one when anything imports it. Loading by path removes
    the ambiguity instead of depending on path order to resolve it.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# The clean state fixture is the discovery skill's, deliberately: generation gates a
# state file the interview wrote, so a second idea of what a valid one looks like would
# let the two drift.
CLEAN_STATE = _load(DISCOVER_SCRIPTS / "selftest.py", "discover_selftest").CLEAN


# A stack every gate must accept: Terragrunt units over Terraform modules,
# provenance on every file, exact provider pins, both tool versions pinned,
# variables and outputs described and typed.
#
# `required_version` is a floor rather than the house `~> x.y`, because this fixture
# is also run by hand against whatever Terraform the machine has, and a fixture that
# fails `init` on the maintainer's own binary teaches nothing.
CLEAN_TF: dict[str, str] = {
    ".terraform-version": "1.16.2\n",
    ".terragrunt-version": "1.1.1\n",
    "root.hcl": '''\
# spec: domain 09-delivery — one backend and one provider definition for the stack
locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals

  # Derived, not read from the environment. `get_env` with no default makes the
  # whole stack fail `terragrunt hcl validate` on any machine that has not exported
  # the variable — which is every machine at generation time.
  state_bucket = "${local.env.project}-tfstate-${local.env.region}"
}

remote_state {
  backend = "s3"

  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }

  config = {
    bucket       = local.state_bucket
    key          = "${path_relative_to_include()}/terraform.tfstate"
    region       = local.env.region
    encrypt      = true
    use_lockfile = true
  }
}

# spec: domain 04-cloud — provider generated once, never repeated per unit
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"

  contents = <<-EOF
    provider "aws" {
      region = "${local.env.region}"
    }
  EOF
}
''',
    "live/prod/env.hcl": '''\
# spec: domain 05-environments — prod values; the code is shared, only these differ
locals {
  project     = "selftest"
  environment = "prod"
  region      = "eu-west-1"
}
''',
    "live/prod/network/terragrunt.hcl": '''\
# spec: domain 07-networking, ADR-002 — one VPC per environment
include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals
}

terraform {
  source = "../../../modules/network"
}

inputs = {
  name = "selftest-${local.env.environment}"
  cidr = "10.0.0.0/16"
}
''',
    "modules/network/versions.tf": '''\
# spec: domain 09-delivery — Terraform, versions resolved 2026-09-14
terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.64.0"
    }
  }
}
''',
    "modules/network/variables.tf": '''\
# spec: domain 05-environments — the module's interface, one value per environment
variable "name" {
  type        = string
  description = "Name prefix for every resource this module creates."
}

variable "cidr" {
  type        = string
  description = "IPv4 CIDR block for the VPC."
}

variable "flow_log_destination_arn" {
  type        = string
  description = "Bucket the VPC flow log is delivered to. Supplied by the unit; flow logs are the only record of what talked to what."
}
''',
    "modules/network/main.tf": '''\
# spec: domain 07-networking, ADR-002 — a VPC per environment, DNS on
resource "aws_vpc" "this" {
  cidr_block           = var.cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = var.name
  }
}

# spec: domain 10-observability — network evidence cannot be backfilled
resource "aws_flow_log" "this" {
  vpc_id               = aws_vpc.this.id
  traffic_type         = "ALL"
  log_destination_type = "s3"
  log_destination      = var.flow_log_destination_arn
}

# spec: domain 11-security — the default group cannot be deleted, only emptied
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id
}
''',
    "modules/network/outputs.tf": '''\
# spec: domain 07-networking — consumed by the compute unit's dependency block
output "vpc_id" {
  description = "Identifier of the VPC every other unit attaches to."
  value       = aws_vpc.this.id
}
''',
}


# The artifact directory the spec gate is run against. It is here rather than
# inline because CI's `build_fixture.py` needs the same one: the completeness gate
# now checks the specification exists and carries its three diagrams, so a fixture
# with a one-line spec fails the spec gate and every generation gate reports on a
# tree whose specification was never written.
CLEAN_ARTIFACTS: dict[str, str] = {
    "architecture-spec.md": """\
# Specification

The account id lives in `root.hcl`, referenced not copied.

## Network topology

```mermaid
graph TD
  internet --> lb --> app --> db
```

## Delivery

```mermaid
flowchart LR
  commit --> build --> gate --> review
```

## Environment promotion

```mermaid
stateDiagram-v2
  dev --> prod
```
""",
    "README.md": "# Selftest\n\nWhat is being built, in plain language.\n",
    "open-questions.md": "# Open questions\n\nNone outstanding.\n",
}


def write_artifacts(base: Path, state: dict) -> Path:
    """The artifact directory, with `discovery-state.json` beside the documents."""
    base.mkdir(parents=True, exist_ok=True)
    for name, body in CLEAN_ARTIFACTS.items():
        (base / name).write_text(body, encoding="utf-8")
    (base / "discovery-state.json").write_text(json.dumps(state, indent=2),
                                               encoding="utf-8")
    return base


def write_tree(base: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return base


def mutate(replacements: dict[str, str | None]) -> dict[str, str]:
    """CLEAN_TF with named files replaced, or removed where the value is None.

    Paths are written out in full rather than encoded into keyword names. The first
    version of this encoded `/` and `.` into the argument name and silently produced
    `.terraform.version` when the fixture meant `.terraform-version`, so the case
    that was supposed to delete the tool version file created a second file instead
    and the gate passed — a fixture bug that reads exactly like a gate bug.
    """
    files = copy.deepcopy(CLEAN_TF)
    for rel, body in replacements.items():
        if body is None:
            files.pop(rel, None)
        else:
            files[rel] = body
    return files


LOOSE_PIN = CLEAN_TF["modules/network/versions.tf"].replace('"6.64.0"', '"~> 6.0"')
COMMENTED_PIN = CLEAN_TF["modules/network/versions.tf"].replace(
    '      version = "6.64.0"', '      # version = "6.64.0"')
NO_REQUIRED_VERSION = CLEAN_TF["modules/network/versions.tf"].replace(
    '  required_version = ">= 1.9"\n\n', "")
# Every `# spec:` line removed, not just the first: the gate reads the first twelve
# lines, and a file whose header was deleted while a later resource kept its own
# would pass for the wrong reason.
NO_PROVENANCE_TF = "\n".join(
    line for line in CLEAN_TF["modules/network/main.tf"].splitlines()
    if not line.lstrip().startswith("# spec:")) + "\n"
NO_PROVENANCE_HCL = CLEAN_TF["live/prod/network/terragrunt.hcl"].split("\n", 1)[1]
UNPINNED_UNIT_SOURCE = CLEAN_TF["live/prod/network/terragrunt.hcl"].replace(
    '  source = "../../../modules/network"',
    '  source = "git::https://example.com/infra/network.git"')
UNDESCRIBED_VARIABLE = CLEAN_TF["modules/network/variables.tf"].replace(
    '  description = "IPv4 CIDR block for the VPC."\n', "")
UNTYPED_VARIABLE = CLEAN_TF["modules/network/variables.tf"].replace(
    '  type        = string\n  description = "IPv4 CIDR block for the VPC."',
    '  description = "IPv4 CIDR block for the VPC."')
UNDESCRIBED_OUTPUT = CLEAN_TF["modules/network/outputs.tf"].replace(
    '  description = "Identifier of the VPC every other unit attaches to."\n', "")
PROVIDER_IN_MODULE = CLEAN_TF["modules/network/main.tf"] + \
    'provider "aws" {\n  region = "eu-west-1"\n}\n'

# One secure default contradicted per fixture. Each is a control §6 of the interview
# asserts, so a stack containing it is not merely unidiomatic — it fails to implement
# the specification it claims to.
PUBLIC_SSH = CLEAN_TF["modules/network/main.tf"] + '''
resource "aws_security_group" "bastion" {
  vpc_id = aws_vpc.this.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
'''
# A public load balancer on 443 is normal, and must not be a finding. This is the
# near-miss that keeps the rule honest.
PUBLIC_HTTPS = CLEAN_TF["modules/network/main.tf"] + '''
resource "aws_security_group" "public_lb" {
  vpc_id = aws_vpc.this.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
'''
PUBLIC_DATABASE = CLEAN_TF["modules/network/main.tf"] + '''
resource "aws_db_instance" "main" {
  identifier          = var.name
  publicly_accessible = true
}
'''
UNENCRYPTED = CLEAN_TF["modules/network/main.tf"] + '''
resource "aws_db_instance" "main" {
  identifier        = var.name
  storage_encrypted = false
}
'''
STATIC_CREDENTIAL = CLEAN_TF["modules/network/main.tf"] + '''
resource "aws_db_instance" "main" {
  identifier = var.name
  password   = "hunter2-not-a-real-one"
}
'''
SECRET_DEFAULT = CLEAN_TF["modules/network/variables.tf"] + '''
variable "db_password" {
  type        = string
  description = "Database password."
  default     = "changeme-please"
}
'''
# The omission half: a required sibling silently absent. Each of these reviews
# clean — there is nothing wrong on the page, which is exactly why a gate that only
# fires on the presence of a bad attribute went green on all of them.
NO_FLOW_LOG = CLEAN_TF["modules/network/main.tf"].replace(
    '''
# spec: domain 10-observability — network evidence cannot be backfilled
resource "aws_flow_log" "this" {
  vpc_id               = aws_vpc.this.id
  traffic_type         = "ALL"
  log_destination_type = "s3"
  log_destination      = var.flow_log_destination_arn
}
''', "")
NO_DEFAULT_SG = CLEAN_TF["modules/network/main.tf"].replace(
    '''
# spec: domain 11-security — the default group cannot be deleted, only emptied
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id
}
''', "")
PUBLIC_LB_NO_LOGS = CLEAN_TF["modules/network/main.tf"] + '''
resource "aws_lb" "public" {
  name               = var.name
  load_balancer_type = "application"
  subnets            = [var.cidr]
}
'''
# An internal load balancer has no internet to log access from, and must not fire.
INTERNAL_LB_NO_LOGS = CLEAN_TF["modules/network/main.tf"] + '''
resource "aws_lb" "internal" {
  name               = var.name
  internal           = true
  load_balancer_type = "application"
  subnets            = [var.cidr]
}
'''
KMS_WITHOUT_POLICY = CLEAN_TF["modules/network/main.tf"] + '''
resource "aws_kms_key" "this" {
  description         = "Data at rest"
  enable_key_rotation = true
}
'''
LOG_GROUP_UNENCRYPTED = CLEAN_TF["modules/network/main.tf"] + '''
resource "aws_cloudwatch_log_group" "this" {
  name              = var.name
  retention_in_days = 365
}
'''

# A cycle between units. `terragrunt hcl validate` passes on this: it evaluates each
# unit without resolving the graph, so only `run --all` — which needs credentials —
# would ever have found it.
CYCLE_NETWORK = CLEAN_TF["live/prod/network/terragrunt.hcl"] + '''
dependency "compute" {
  config_path = "../compute"

  mock_outputs                            = { role_arn = "mock-role" }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}
'''
CYCLE_COMPUTE = '''\
# spec: domain 06-compute — depends on the network it runs in
include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/network"
}

dependency "network" {
  config_path = "../network"

  mock_outputs                            = { vpc_id = "mock-vpc" }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}
'''

UNRESTRICTED_MOCKS = CLEAN_TF["live/prod/network/terragrunt.hcl"] + '''
dependency "data" {
  config_path = "../data"

  mock_outputs = {
    endpoint = "mock-endpoint"
  }
}
'''

CASES = [
    ("a loose provider pin", "pins",
     mutate({"modules/network/versions.tf": LOOSE_PIN}),
     "`~> 6.0` names no patch release"),
    ("a pin that is only in a comment", "pins",
     mutate({"modules/network/versions.tf": COMMENTED_PIN}),
     "a commented-out `version` must not satisfy the check"),
    ("a module with no required_version", "pins",
     mutate({"modules/network/versions.tf": NO_REQUIRED_VERSION}),
     "a child module states what it needs too"),
    ("no .terraform-version", "pins",
     mutate({".terraform-version": None}),
     "the Terraform version is unpinned"),
    ("no .terragrunt-version in a Terragrunt stack", "pins",
     mutate({".terragrunt-version": None}),
     "Terragrunt is a second tool with its own breaking changes"),
    ("an unpinned Terragrunt unit source", "pins",
     mutate({"live/prod/network/terragrunt.hcl": UNPINNED_UNIT_SOURCE}),
     "a remote `terraform.source` with no `?ref=` tracks the default branch"),
    ("a .tf file with no provenance header", "provenance",
     mutate({"modules/network/main.tf": NO_PROVENANCE_TF}),
     "main.tf without its `# spec:` line"),
    ("a terragrunt.hcl with no provenance header", "provenance",
     mutate({"live/prod/network/terragrunt.hcl": NO_PROVENANCE_HCL}),
     "the unit is where an environment's shape is decided"),
    ("a variable with no description", "conventions",
     mutate({"modules/network/variables.tf": UNDESCRIBED_VARIABLE}),
     "the variables file is the module's interface"),
    ("a variable with no type", "conventions",
     mutate({"modules/network/variables.tf": UNTYPED_VARIABLE}),
     "untyped means `any`, and the error surfaces far from its cause"),
    ("an output with no description", "conventions",
     mutate({"modules/network/outputs.tf": UNDESCRIBED_OUTPUT}),
     "an output is a published interface"),
    ("a provider block in a child module", "conventions",
     mutate({"modules/network/main.tf": PROVIDER_IN_MODULE}),
     "it cannot then be used with `for_each`"),
    ("SSH open to the internet", "guardrails",
     mutate({"modules/network/main.tf": PUBLIC_SSH}),
     "0.0.0.0/0 to port 22 is not normal in any architecture"),
    ("a publicly reachable data store", "guardrails",
     mutate({"modules/network/main.tf": PUBLIC_DATABASE}),
     "§6 is explicit that no data store is publicly reachable"),
    ("encryption explicitly disabled", "guardrails",
     mutate({"modules/network/main.tf": UNENCRYPTED}),
     "encryption at rest is a secure default the specification asserts"),
    ("a static credential in the configuration", "guardrails",
     mutate({"modules/network/main.tf": STATIC_CREDENTIAL}),
     "§6 forbids long-lived static credentials"),
    ("a secret-shaped variable with a literal default", "guardrails",
     mutate({"modules/network/variables.tf": SECRET_DEFAULT}),
     "a default is committed"),
    ("mock_outputs with no command restriction", "guardrails",
     mutate({"live/prod/network/terragrunt.hcl": UNRESTRICTED_MOCKS}),
     "the mock is then used at apply too"),
    ("a VPC with no flow log", "guardrails",
     mutate({"modules/network/main.tf": NO_FLOW_LOG}),
     "network evidence cannot be produced retrospectively"),
    ("a VPC whose default security group is unmanaged", "guardrails",
     mutate({"modules/network/main.tf": NO_DEFAULT_SG}),
     "it allows all traffic between its members and cannot be deleted"),
    ("an internet-facing load balancer with no access logs", "guardrails",
     mutate({"modules/network/main.tf": PUBLIC_LB_NO_LOGS}),
     "the request-level record of who reached the application"),
    ("a KMS key with no policy", "guardrails",
     mutate({"modules/network/main.tf": KMS_WITHOUT_POLICY}),
     "the default policy defers every decision to IAM"),
    ("a log group with no encryption key", "guardrails",
     mutate({"modules/network/main.tf": LOG_GROUP_UNENCRYPTED}),
     "a log group is storage like any other"),
    ("a dependency cycle between two units", "graph",
     mutate({"live/prod/network/terragrunt.hcl": CYCLE_NETWORK,
             "live/prod/compute/terragrunt.hcl": CYCLE_COMPUTE}),
     "hcl validate passes on a cycle; only run --all would catch it"),
    ("a file truncated to zero bytes", "provenance",
     mutate({"live/prod/network/terragrunt.hcl": ""}),
     "an empty file is not a missing comment, and the fix is different"),
]


def run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable] + argv, capture_output=True, text=True)


def check(state: Path, tf_dir: Path, skip: list[str],
          artifacts: Path) -> subprocess.CompletedProcess:
    argv = [str(HERE / "check_iac.py"), "--state", str(state),
            "--tf-dir", str(tf_dir), "--artifacts", str(artifacts)]
    for name in skip:
        argv += ["--skip", name]
    return run(argv)


# (command, is the cwd inside a generated stack, must be denied, why)
HOOK_CASES = [
    ("terraform apply", True, True, "the verb this whole rule exists for"),
    ("terragrunt run --all apply", True, True, "the Terragrunt spelling of it"),
    ("terraform destroy -auto-approve", True, True, "destroy, unattended"),
    ("terraform state rm aws_vpc.this", True, True, "mutates the state file"),
    ("terraform plan", True, False, "plan is how the review happens"),
    ("terragrunt hcl validate", True, False, "so is validate"),
    ("terraform init -backend=false", True, False, "and init"),
    ("terraform state list", True, False, "a read-only state subcommand"),
    ("terraform plan -out=apply.tfplan", True, False,
     "the word apply in a filename is not the verb"),
    ("terraform apply", False, False,
     "outside a generated stack this is ordinary work and must not be touched"),
]


def check_hook(tmp: Path) -> list[str]:
    """The `PreToolUse` hook that turns rule 3 from prose into enforcement.

    Every case matters in one direction or the other. A hook that misses
    `terragrunt run --all apply` does not enforce the rule; a hook that blocks
    `terraform plan`, or blocks anything in a repository this plugin never wrote,
    gets uninstalled within a day and takes the real protection with it.
    """
    if not BLOCK_MUTATING_IAC.is_file():
        return [f"FAIL  the guardrail hook is missing from {BLOCK_MUTATING_IAC}"]
    if not os.access(BLOCK_MUTATING_IAC, os.X_OK):
        return [f"FAIL  {BLOCK_MUTATING_IAC.name} is not executable, so the hook "
                f"never runs and rule 3 is prose again"]

    inside = tmp / "stack" / "live" / "prod"
    inside.mkdir(parents=True)
    (tmp / "stack" / ".architecture-discovery.json").write_text(
        json.dumps({"specification": "docs/architecture/x/architecture-spec.md",
                    "generated": "2026-01-01"}), encoding="utf-8")
    outside = tmp / "elsewhere"
    outside.mkdir()

    results, failures = [], 0
    for command, in_stack, want_deny, why in HOOK_CASES:
        cwd = inside if in_stack else outside
        proc = subprocess.run(
            [sys.executable, str(BLOCK_MUTATING_IAC)],
            input=json.dumps({"tool_name": "Bash", "cwd": str(cwd),
                              "tool_input": {"command": command}}),
            capture_output=True, text=True)
        denied = False
        if proc.stdout.strip():
            try:
                decision = json.loads(proc.stdout)["hookSpecificOutput"]
                denied = decision.get("permissionDecision") == "deny"
            except Exception:  # noqa: BLE001
                denied = False
        if denied == want_deny:
            continue
        failures += 1
        results.append(
            f"FAIL  hook {'let through' if want_deny else 'blocked'} "
            f"`{command}` {'inside' if in_stack else 'outside'} a generated stack "
            f"— {why}")

    # Malformed input must never break a session. The hook fails open by design.
    proc = subprocess.run([sys.executable, str(BLOCK_MUTATING_IAC)],
                          input="not json at all", capture_output=True, text=True)
    if proc.returncode != 0 or proc.stdout.strip():
        failures += 1
        results.append("FAIL  hook did not fail open on malformed input — a guardrail "
                       "that breaks the session when it malfunctions gets disabled")

    if failures:
        return results
    return [f"ok    hook        {len(HOOK_CASES)} commands classified correctly, and "
            f"it fails open on malformed input"]


def check_plan_tasks() -> list[str]:
    """The task plan: nothing invented, waves genuinely independent, no cycle.

    The plan decides what several agents write at the same time, so a defect here is
    not one wrong file — it is one agent writing a component nobody asked for while
    another waits on a dependency that will never arrive.
    """
    import plan_tasks  # noqa: PLC0415

    problems: list[str] = []

    # The component graph itself must be acyclic and must only name components that
    # exist, or the wave loop cannot place them and falls back to one big wave.
    for name, spec in plan_tasks.COMPONENTS.items():
        for dep in spec["depends_on"]:
            if dep not in plan_tasks.COMPONENTS:
                problems.append(f"{name} depends on {dep!r}, which is not a component")
            elif name in plan_tasks.COMPONENTS[dep]["depends_on"]:
                problems.append(f"{name} and {dep} depend on each other")
        if name not in plan_tasks.ORDER:
            problems.append(f"{name} is not in ORDER, so it has no place in the "
                            f"apply order the tie-break rule depends on")

    rich = copy.deepcopy(CLEAN_STATE)
    rich["domains"]["02-app-shape"]["answers"] = {
        "shape": "containerised API and worker, Redis cache, SQS queue"}
    rich["domains"]["07-networking"]["answers"] = {"ingress": "ALB and CloudFront"}
    rich["domains"]["08-identity"]["answers"] = {"workload_identity": "IRSA"}
    rich["domains"]["09-delivery"]["answers"] = {"registry": "ECR"}
    rich["domains"]["10-observability"]["answers"] = {"logs": "CloudWatch"}
    rich["domains"]["12-data-dr"]["answers"] = {"rto": "4h", "stores": "Aurora and S3"}
    plan = plan_tasks.plan(rich, "infra")

    placed: set[str] = set()
    for wave in plan["waves"]:
        for task_id in wave:
            task = next(t for t in plan["tasks"] if t["id"] == task_id)
            outstanding = [d for d in task["depends_on"] if d not in placed]
            if outstanding:
                problems.append(
                    f"{task_id} is in the same wave as, or before, {outstanding} — "
                    f"a wave is only safe to parallelise if nothing in it waits on "
                    f"anything else in it")
            if task_id in wave and any(d in wave for d in task["depends_on"]):
                problems.append(f"{task_id} depends on something in its own wave")
        placed |= set(wave)

    if not any(len(w) > 1 for w in plan["waves"]):
        problems.append("no wave has more than one task, so the plan describes no "
                        "parallelism at all on a stack that plainly has some")

    # A domain ruled out produces nothing. This is the rule-1 half of the plan: a
    # component nobody asked for is the characteristic failure of a generator.
    ruled_out = copy.deepcopy(rich)
    ruled_out["domains"]["12-data-dr"]["status"] = "not-applicable"
    ruled_out["domains"]["12-data-dr"]["answers"] = {}
    ruled_out["domains"]["02-app-shape"]["answers"] = {"shape": "stateless API"}
    lean = plan_tasks.plan(ruled_out, "infra")
    if any(t["id"] == "data" for t in lean["tasks"]):
        problems.append("a data component was planned from a specification whose "
                        "data domain is not-applicable")

    empty = plan_tasks.plan({"domains": {}}, "infra")
    if empty["ok"]:
        problems.append("an empty state file produced a plan; an unfinished "
                        "interview is not a system with nothing in it")

    if problems:
        return ["FAIL  plan_tasks.py — " + p for p in problems]
    return ["ok    plan_tasks.py  waves are independent, a ruled-out domain "
            "produces no task, and an empty state produces no plan"]


def main() -> int:
    lines: list[str] = []
    failed = 0
    # fmt and validate need the binary and, for validate, a registry. They are the
    # two gates this harness cannot assert offline, so they are skipped by name and
    # the skip is printed.
    skip = ["fmt", "validate"]
    if shutil.which("gitleaks") is None:
        skip.append("secrets")
        lines.append("SKIP  secrets — gitleaks not installed (the gate would not run)")
    lines.append("SKIP  fmt, validate — asserted by hand; they need the binary and a "
                 "reachable registry")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        artifacts = write_artifacts(tmp / "artifacts", CLEAN_STATE)
        state = artifacts / "discovery-state.json"

        clean = write_tree(tmp / "clean", CLEAN_TF)
        proc = check(state, clean, skip, artifacts)
        if proc.returncode == 0:
            lines.append("ok    check_iac.py accepts a clean tree")
        else:
            failed += 1
            lines.append(f"FAIL  check_iac.py rejects a clean tree "
                         f"(exit {proc.returncode})\n{proc.stdout}{proc.stderr}")

        for i, (title, gate, files, why) in enumerate(CASES):
            tree = write_tree(tmp / f"case{i}", files)
            proc = check(state, tree, skip, artifacts)
            if proc.returncode == 1 and f"[FAIL] {gate}" in proc.stdout:
                lines.append(f"ok    {gate:<11} catches {title} — {why}")
            else:
                failed += 1
                lines.append(
                    f"FAIL  {gate:<11} let through {title} ({why}) — exit "
                    f"{proc.returncode}\n{proc.stdout}{proc.stderr}")

        # A public load balancer on 443 is normal architecture. A guardrail that
        # fires on it is one people switch off, and the eight that matter go too.
        tree = write_tree(tmp / "https", mutate({"modules/network/main.tf": PUBLIC_HTTPS}))
        proc = check(state, tree, skip, artifacts)
        if proc.returncode == 0:
            lines.append("ok    guardrails  0.0.0.0/0 on 443 is normal and is not a "
                         "finding")
        else:
            failed += 1
            lines.append(f"FAIL  guardrails fired on a public load balancer — a "
                         f"guardrail that cries wolf is one people switch "
                         f"off\n{proc.stdout}")

        # An internal load balancer has no internet-facing access to log. A floor
        # that fires on it is a floor people waive by habit, and the habit is what
        # costs the next real finding.
        tree = write_tree(tmp / "internal-lb",
                          mutate({"modules/network/main.tf": INTERNAL_LB_NO_LOGS}))
        proc = check(state, tree, skip, artifacts)
        if proc.returncode == 0:
            lines.append("ok    guardrails  an internal load balancer needs no access "
                         "logs and is not a finding")
        else:
            failed += 1
            lines.append(f"FAIL  guardrails fired on an internal load "
                         f"balancer\n{proc.stdout}")

        # A deviation the interview recorded must be implementable. The waiver names
        # the control, the deviation, the reason and who accepted it; refusing it
        # here a second time would mean a recorded decision cannot be carried out.
        waived_state = copy.deepcopy(CLEAN_STATE)
        waived_state["waivers"] = [{
            "control": "public-admin-ingress",
            "deviation": "Bastion reachable on 22 from the office range",
            "reason": "No VPN yet; tracked as OQ-4",
            "owner": "Client CTO",
            "date": "2026-01-01",
        }]
        waived_path = artifacts / "waived-state.json"
        waived_path.write_text(json.dumps(waived_state, indent=2), encoding="utf-8")
        tree = write_tree(tmp / "waived", mutate({"modules/network/main.tf": PUBLIC_SSH}))
        proc = check(waived_path, tree, skip, artifacts)
        if proc.returncode == 0 and "public-admin-ingress" in proc.stdout:
            lines.append("ok    guardrails  a recorded waiver waives the finding, and "
                         "it is still reported")
        elif proc.returncode == 0:
            failed += 1
            lines.append("FAIL  guardrails waived a finding silently — a waived "
                         "deviation must still be visible in the report")
        else:
            failed += 1
            lines.append(f"FAIL  guardrails refused a deviation the specification "
                         f"recorded a waiver for (exit {proc.returncode})")

        # And the waiver must be specific: waiving one control must not waive another.
        tree = write_tree(tmp / "waived-other",
                          mutate({"modules/network/main.tf": UNENCRYPTED}))
        proc = check(waived_path, tree, skip, artifacts)
        if proc.returncode == 1:
            lines.append("ok    guardrails  a waiver for one control does not waive "
                         "another")
        else:
            failed += 1
            lines.append(f"FAIL  a waiver for public-admin-ingress also waived "
                         f"unencrypted-storage (exit {proc.returncode})")

        # A scanner this gate cannot drive must not read as a clean scan. The gate
        # drives four; a specification naming any other one used to print nothing at
        # all, so the run was indistinguishable from one where the chosen tool ran
        # and found nothing.
        for recorded, want_marker, why in (
                ("KICS in CI, blocking", True,
                 "a scanner this gate cannot drive is reported as not run"),
                ("none — reviewed by hand", False,
                 "'none' is an answer, not a tool this gate failed to find")):
            unrunnable = copy.deepcopy(CLEAN_STATE)
            unrunnable["domains"]["09-delivery"]["answers"] = {
                "iac": "Terraform with Terragrunt", "policy_pre_apply": recorded}
            unrunnable_path = artifacts / "unrunnable-scanner-state.json"
            unrunnable_path.write_text(json.dumps(unrunnable, indent=2), encoding="utf-8")
            proc = check(unrunnable_path, write_tree(tmp / f"scanner-{want_marker}",
                                                     mutate({})), skip, artifacts)
            marked = "[----] guardrails" in proc.stdout
            if proc.returncode == 0 and marked == want_marker:
                lines.append(f"ok    guardrails  {why}")
            else:
                failed += 1
                lines.append(f"FAIL  guardrails — {why}: exit {proc.returncode}, "
                             f"did-not-run marker {marked}\n{proc.stdout}")

        # A tree with no .tf files is exit 2, never a clean pass. Same defect the
        # discovery skill's secret scan had: scanning nothing and reporting success.
        empty = tmp / "empty"
        empty.mkdir()
        proc = check(state, empty, skip, artifacts)
        if proc.returncode == 2:
            lines.append("ok    an empty tree is exit 2, never a clean pass")
        else:
            failed += 1
            lines.append(f"FAIL  an empty tree exited {proc.returncode}, wanted 2")

        # --draft reports and never blocks, so a mid-generation run is usable.
        tree = write_tree(tmp / "draft", CASES[0][2])
        argv = [str(HERE / "check_iac.py"), "--state", str(state),
                "--tf-dir", str(tree), "--artifacts", str(artifacts), "--draft"]
        for name in skip:
            argv += ["--skip", name]
        proc = run(argv)
        if proc.returncode == 0 and "[FAIL] pins" in proc.stdout:
            lines.append("ok    --draft reports a failing gate without blocking")
        else:
            failed += 1
            lines.append(f"FAIL  --draft exited {proc.returncode}, wanted 0 with the "
                         f"failure still reported")

        # The spec gate must refuse to bless Terraform built from a broken spec.
        broken = copy.deepcopy(CLEAN_STATE)
        broken["domains"]["13-cost"]["status"] = "not-started"
        broken_path = artifacts / "broken-state.json"
        broken_path.write_text(json.dumps(broken, indent=2), encoding="utf-8")
        proc = check(broken_path, clean, skip, artifacts)
        if proc.returncode == 1 and "[FAIL] spec" in proc.stdout:
            lines.append("ok    spec        refuses a tree whose specification fails "
                         "its own gates")
        else:
            failed += 1
            lines.append(f"FAIL  spec gate passed a specification with an unanswered "
                         f"blocking domain (exit {proc.returncode})")

        # B6: the emitted floor must be one the installed binary satisfies. A
        # block resolved as `~> 1.16` and pasted verbatim — which is what rule 2
        # instructs — makes every module fail `validate` on a 1.15 machine with an
        # error that names no cause.
        import resolve_versions as rv  # noqa: PLC0415
        providers = [{"name": "aws", "source": "hashicorp/aws", "version": "6.64.0"}]
        older = rv.hcl_block("terraform", "1.16.2", providers, "1.15.8")
        same = rv.hcl_block("terraform", "1.16.2", providers, "1.16.2")
        unknown = rv.hcl_block("terraform", "1.16.2", providers, None)
        if ('required_version = "~> 1.15"' in older
                and 'required_version = "~> 1.16"' in same
                and 'required_version = "~> 1.16"' in unknown):
            lines.append("ok    resolve_versions.py emits a floor the installed "
                         "binary satisfies, and the resolved one where it does not "
                         "know")
        else:
            failed += 1
            lines.append("FAIL  resolve_versions.py emitted a required_version floor "
                         "the installed binary cannot satisfy\n" + older)

        # resolve_versions.py must never invent a version. Two paths, and they are
        # kept distinct because they need different fixes: a name that does not
        # exist, and a registry that could not be reached.
        import resolve_versions  # noqa: PLC0415 — imported here, not at module load,
                                 # so a network-less machine still runs everything else
        try:
            resolve_versions._get("http://127.0.0.1:1/nothing", 1.0)
        except resolve_versions.Unreachable:
            lines.append("ok    resolve_versions.py raises Unreachable rather than "
                         "falling back to a bundled version table")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            lines.append(f"FAIL  resolve_versions.py raised {exc.__class__.__name__} "
                         f"for an unreachable host, not Unreachable")
        else:
            failed += 1
            lines.append("FAIL  resolve_versions.py returned a result from an "
                         "unreachable host")

    # The fmt gate used to hand terraform an absolute path from an unrelated working
    # directory, and on a path behind a symlink — /tmp on macOS — terraform
    # relativised it, failed to find it, and the gate reported a formatting failure
    # that was really a path bug. CI found it; this keeps it found.
    symlinked = Path(tempfile.mkdtemp()) / "link"
    try:
        symlinked.symlink_to(clean, target_is_directory=True)
    except OSError:
        lines.append("SKIP  fmt path handling — symlinks unavailable here")
    else:
        proc = check(state, symlinked, [s for s in skip if s != "fmt"], artifacts)
        if "[FAIL] fmt" in proc.stdout:
            failed += 1
            lines.append("FAIL  fmt reported a formatting failure for a tree reached "
                         "through a symlink — that is a path bug wearing a gate's "
                         f"verdict\n{proc.stdout}")
        else:
            lines.append("ok    fmt         a tree reached through a symlink is not a "
                         "formatting failure")

    lines += check_plan_tasks()

    lines += check_hook(Path(tempfile.mkdtemp()))

    # The allowed-tools rules name these scripts by path, and a Bash rule only
    # matches a direct invocation — which needs the executable bit. Without it the
    # script still runs via `python3 <path>`, but that command matches no rule and
    # prompts, which is exactly what the grant was written to avoid. Same reasoning
    # as preflight.py treating it as exit 1 rather than a warning.
    for name in ("preflight.py", "plan_tasks.py", "resolve_versions.py",
                 "check_iac.py"):
        if os.access(HERE / name, os.X_OK):
            lines.append(f"ok    {name} is executable, so its allowed-tools rule "
                         f"can match")
        else:
            failed += 1
            lines.append(f"FAIL  {name} is not executable. Run: chmod +x "
                         f"{HERE / name}")

    print("IaC gate selftest\n")
    for line in lines:
        print("  " + line)
    print("")
    if failed:
        print(f"{failed} check(s) are not behaving. A gate that cannot catch its own "
              f"violation is worse than no gate: it reads as a clean bill of health.")
        return 1
    print("Every gate accepted its clean case and rejected its violating case.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

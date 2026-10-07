---
name: iac
description: Turn an approved architecture specification into reviewable infrastructure as code — a Terragrunt and Terraform stack, or OpenTofu, or plain Terraform, whichever the interview recorded — Terraform modules, Terragrunt units per environment, versions resolved from the registry and pinned exactly, every file naming the decision that put it there — then gate it with terraform fmt and validate plus terragrunt hcl fmt and hcl validate, and open a pull request. Use this after a discovery interview has produced a specification and its gates pass, whenever the infrastructure that was scoped now has to be written as code.
when_to_use: |
  Trigger on casual phrasing as readily as formal: "right, the spec is signed off, write the terraform", "turn this architecture doc into IaC", "we agreed the design last week, can you scaffold the infra", "generate the modules for what we scoped", "set up the terragrunt stack", "write the infrastructure code for this". The skill is named for what it produces — infrastructure as code — rather than for one tool, and domain 9's `iac` answer decides which tool that is. Trigger when resuming a generation that already has a stack next to a discovery-state.json, and when a revised specification means the stack has to move with it. Trigger when someone asks for the infrastructure code for a system this plugin already scoped, even if they never say "terraform" or "terragrunt".
  Do not trigger to edit Terraform that already manages live infrastructure, to debug a failing plan or apply, to import existing resources, or to review somebody else's modules. Those act on what is built. This writes what was scoped and has not been built yet. Do not trigger without a specification: with no discovery-state.json there is nothing to generate from, and guessing the architecture is the one failure this skill exists to prevent.
argument-hint: "[project slug]"
allowed-tools:
  - Bash(${CLAUDE_SKILL_DIR}/scripts/preflight.py *)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/plan_tasks.py *)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/resolve_versions.py *)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/check_iac.py *)
metadata:
  version: "1.0.0"
compatibility: "Claude Code only. Uses when_to_use, argument-hint and ${CLAUDE_SKILL_DIR} substitution, none of which are in the Agent Skills spec, so this will not upload to claude.ai or package with package_skill.py. It reads the state file the discovery skill writes, so the two ship together."
license: MIT
---

# Infrastructure as code, from an approved specification

The generation stage. The interview decided what to build and recorded it; this
writes that, and only that, as a stack a reviewer can read — Terragrunt over
Terraform by default, OpenTofu or plain Terraform where domain 9 recorded it.

Two layers, one job each. **Terraform writes the modules** — resources, inputs,
outputs, no environment knowledge. **Terragrunt composes them into environments** —
one `root.hcl` generating the backend and the provider for every unit, one thin unit
per component per environment, dependency ordering between them, one state file each.
Where domain 9 recorded plain Terraform instead, follow the specification; everything
here except the unit layer still applies.

The input is `discovery-state.json` and the specification beside it. Not the
conversation, not a recollection of the interview, and not what the architecture
probably ought to be.

## Standing rules

Nine rules, and they apply for the whole generation rather than just the first turn.
They are first in this file because generation outlives compaction, and on compaction
only the beginning of this file reliably comes back.

### 1. The specification is the input, and the only one

Every resource traces to a domain answer, an ADR or a recorded waiver in
`discovery-state.json`. If it traces to none of those, it does not get written.

The characteristic failure of a generator is not a wrong resource, it is a
**plausible** one nobody asked for — a NAT gateway per availability zone in a
specification that never discussed egress cost, a KMS key nobody will rotate, a
second environment that does not exist. A plausible resource reviews clean, gets
applied, and is billed monthly forever.

So `check_iac.py` requires every `.tf` file **and every Terragrunt `.hcl`
file** to open with a provenance line — the unit is where an environment's shape is
actually decided, so it needs the header at least as much as the module it points at:

```hcl
# spec: domain 07-networking, ADR-004 — three private subnets, one per availability zone
```

Naming the domain, the ADR or the open question. The gate checks the line exists;
whether it is true is yours. Write the header first and the resources after, and the
question "which decision is this?" gets asked before the resource exists rather than
in review.

### 2. Never invent a version

```
${CLAUDE_SKILL_DIR}/scripts/resolve_versions.py --provider aws --provider kubernetes --hcl
```

That prints a ready-to-paste `terraform {}` block with the current published
versions. Your recollection of the latest AWS provider is your training cut-off's
recollection, and it is confidently wrong in exactly the way a pin must never be: a
`~> 5.0` written long after 6.x shipped looks deliberate, reviews clean, and freezes
the project a major version behind.

If the registry cannot be reached the script exits 3 and resolves nothing. There is
no bundled fallback table and there will not be one — a table compiled at build time
is wrong within weeks. Ask for the versions instead, and record where they came from.

Providers and registry modules are pinned **exactly**, to a patch release.
`required_version` for Terraform itself is `~> x.y`, which is the one place a range
is right: patch releases of the tool are bug fixes, and pinning them makes every
engineer and every CI image move in lockstep for nothing. `check_iac.py`
enforces both shapes.

### 3. Never apply, never destroy, never touch a real account

This skill writes files. It does not run `terraform apply`, `terraform destroy`,
`terraform import`, `terraform state` or any command that mutates infrastructure or
state — nor their Terragrunt spellings, `terragrunt apply` and
`terragrunt run --all apply` — and it does not do so at the user's suggestion either.
A generated stack has never been reviewed by the people who will operate it.

**This one is enforced rather than trusted.** Step 1 of generation writes
`.architecture-discovery.json` at the root of the stack, and the plugin ships a
`PreToolUse` hook that denies every mutating verb inside a directory carrying that
marker. `plan`, `validate`, `fmt`, `init`, `show` and `output` are untouched — they
are how the review happens.

The marker is the handover. A person reads the plan and takes ownership by deleting
the file; that is a deliberate one-line action by a human, which is the right shape
for this decision. It is not a flag to pass, and not something to delete on the
user's behalf to get a command through. If someone asks you to apply, say what the
marker is and let them remove it.

`terraform fmt`, `terraform init -backend=false`, `terraform validate`,
`terragrunt hcl fmt` and `terragrunt hcl validate` are run — all read-only, and
`check_iac.py` runs them for you. `terragrunt apply`, `run --all apply` and
`run --all destroy` are never run, and `run --all plan` is not either: a plan against
a real account needs credentials, a backend and somebody who accepts the consequence,
so it is handed over, not run. Say what to run and let them run it.

### 4. Nothing sensitive in the stack

Account identifiers, bucket names, endpoints, ARNs, connection strings: none of
these get written into a `.tf` file. They become variables, supplied from a file the
tree does not commit.

- The backend is generated once by `root.hcl`, and its bucket name is **derived from
  locals the repository already holds**, never read from an unset environment
  variable — `get_env` with no default makes the whole stack fail `terragrunt hcl
  validate` on every machine that has not exported it, which is every machine while
  the code is being written. In a plain Terraform layout the equivalent is partial
  backend configuration: `backend "s3" {}` committed, the values in an uncommitted
  `backend.hcl` with an `.example` beside it.
- Values per environment go in `live/<env>/env.hcl` where they are not sensitive;
  anything else is a variable with no default, supplied at apply time.
- Secrets are never `variable` defaults, never in `inputs`, never in `env.hcl`. They
  come from the secret store the interview chose in domain 8.

`check_iac.py` runs the discovery skill's secret scan over the whole stack and
blocks on a finding. The stack gets committed, and committed means published.

### 5. Write code a reviewer will recognise

Industry conventions are in `references/conventions.md`, and four of them are
machine-checked: every `variable` typed and described, every `output` described, and
no `provider` block in a child module. Read that file before the first resource, not
after the gate refuses one.

The rest — `for_each` over `count`, one naming local rather than repeated
interpolation, `moved` blocks when renaming, `mock_outputs` limited to `validate` and
`plan`, no `get_env` without a default, thin units and logic in modules — is
judgement, and judgement is why it is written down rather than gated.

### 6. The secure defaults were decided, not proposed

Private subnets, encryption at rest and in transit, no public data stores, least
privilege, no long-lived static credentials. The specification already settled these
and the reasoning is not reopened here: write them.

A deviation is legitimate only where the state file already carries a waiver naming
the control, the deviation, the reason and who accepted it. **If the specification
has no waiver and the architecture seems to need one, stop and ask.** Writing the
deviation and mentioning it afterwards is how an accepted risk becomes an unnoticed
one — and an interview that recorded no waiver did not accept the risk.

The `guardrails` gate checks thirteen of these against the code rather than against
the document, in two halves.

**Eight fire on something present.** An admin port open to the internet, a publicly
reachable data store, encryption switched off, a wildcard IAM policy, a static
credential, an unrestricted `mock_outputs`, key rotation disabled, a secret-shaped
variable with a literal default.

**Five fire on something absent**, and this is the half a generator fails: a VPC with
no flow log, a VPC whose default security group is unmanaged, an internet-facing load
balancer with no access logs, a KMS key with no policy, a log group with no
encryption key. Nothing is wrong on the page — a required sibling resource is simply
not there, and it reviews clean. `references/providers.md` names the siblings per
decision for the same reason.

A finding the specification waived is reported and not blocked — put the check id in
the waiver's `control` field so the gate can match it. That works for the policy
scanner's own ids too (`CKV_AWS_86` and the like), so `discovery-state.json` stays
the single record of what was accepted and by whom, and the scanner's config file
carries only false positives. `references/conventions.md` has the suppression
convention and `assets/scanner-config.template.yaml` the skeleton.

Thirteen checks are a floor, not a security review. They catch what is always wrong,
never what is wrong here — which is why domain 9a chose a scanner, and why the gate
runs it where it is installed.

### 7. An unknown becomes a variable, never a guess

Where the specification did not settle a value — a CIDR, an instance size, a
retention period — write a `variable` with no default, a `description` naming the
open question, and a line in the tree's README. Then carry on.

```hcl
# spec: OQ-7 — instance class not settled; owner Client CTO, default applies 2026-09-20
variable "db_instance_class" {
  type        = string
  description = "RDS instance class. OQ-7 is open; no default here on purpose, so this fails at plan rather than provisioning a size nobody chose."
}
```

A default that nobody chose is applied silently. A missing one fails loudly at plan
time, which is the correct place for it to fail.

### 8. Format and validate both halves, after every file

```
${CLAUDE_SKILL_DIR}/scripts/check_iac.py --state <state> --tf-dir <tree> --artifacts <dir>
```

Run this after each step of generation, not once at the end. `--draft` mid-generation
reports without blocking. Invoke it as its own command; never chain it behind `&&`,
because a Bash permission rule does not extend across shell operators and the chained
form will prompt.

**The first module is the checkpoint that matters.** Run the gate the moment the
first module and its unit exist, before writing the second. A finding there is almost
never one finding — it is a class of finding, and the same omission will be in all
six modules by the time the gate runs at the end. Fixing the class once is the
difference between one edit and six. This is also where a missing scanner shows up as
`did not run`, which is worth knowing before six modules are written rather than
after.

Nine gates: the specification's own five, then pins, provenance, conventions,
guardrails, the dependency graph, formatting, validation and the secret scan. The
`graph` gate is static and always runs — it reads the `dependency` edges and refuses
a cycle, which `terragrunt hcl validate` cannot see and only `run --all` would catch,
against a real account. Formatting and validation each cover **both tools, every
run**:

| | Terraform | Terragrunt |
|---|---|---|
| `fmt` | `terraform fmt -check -recursive` | `terragrunt hcl fmt --check --diff` |
| `validate` | `init -backend=false` + `validate`, per module | `terragrunt hcl validate` over the units |

`terraform fmt` does not touch `terragrunt.hcl` and `terragrunt hcl fmt` does not
touch `.tf`, so checking one leaves the other to be reformatted by whoever notices in
CI — and every diff after that is noise. Either half failing fails the gate. Either
half being unable to run means the gate **did not run**, which is not the same as
passing, and the summary says which.

If you write a file and do not run this, you have not finished writing the file.

### 9. Where to read next

Load a reference when its question is in play. Reading all of them at once spends
the attention the current file needs.

| When | Read |
|---|---|
| Deciding the directory shape, `root.hcl`, state backend or environment split | `references/layout.md` |
| Before the first file, and whenever a reviewer asks why something is shaped as it is | `references/conventions.md` |
| Writing `versions.tf`, or raising a pin | `references/versions.md` |
| Turning a domain answer into resources | `references/providers.md` |
| Writing the files | `assets/stack.template.md` |
| Writing the stack's README | `assets/tf-readme.template.md` |
| Setting up the policy scanner's suppressions | `assets/scanner-config.template.yaml` |
| Deciding what to generate, in what order, and whether to fan out | `scripts/plan_tasks.py`, then the section on working through the waves below |

## Before the first file

0. **Preflight.**

   ```
   ${CLAUDE_SKILL_DIR}/scripts/preflight.py --state <state>
   ```

   `terraform` or `tofu`, `terragrunt`, `gitleaks`, and the policy scanner domain 9a
   recorded. Each missing tool costs a gate, and a gate that did not run has not
   passed — finding that out six modules in means fixing six modules. It reads the
   state file so the scanner is probed by name rather than guessed at.

1. **Find the specification.** `discovery-state.json` and the artifacts beside it,
   normally `docs/architecture/<project-slug>/`. Without one, stop: there is nothing
   to generate from, and this skill does not conduct the interview. Point at
   `/architecture-discovery:discover` instead.

2. **Run the gate in draft mode against an empty tree** — or simply run the
   discovery skill's gates — and confirm the specification passes its own. Terraform
   generated from a specification that fails is a faithful implementation of a
   document nobody should be building from.

3. **Read the state file completely** before writing anything. Every domain, every
   decision, every waiver, every open question. Then say back, in one short
   paragraph, what you are about to generate and what you are deliberately not
   generating because the specification did not settle it.

4. **Agree three things**, do not decide them silently:
   - Where the stack goes. Default `infra/`; if the repository already keeps
     infrastructure somewhere, follow the repository.
   - Whether this is Terraform or OpenTofu underneath, and whether Terragrunt
     composes it. Domain 9's `iac` answer decides this — it is already recorded.
     Terragrunt over Terraform is the default for anything with more than one
     environment or more than about three components; below that it is a second tool
     earning nothing.
   - The branch name. A separate branch from the discovery one, so the specification
     review and the code review do not collide.

5. **Check what already exists.** If the repository has Terraform or Terragrunt, this
   extends it and follows its conventions rather than introducing a second layout —
   including where those conventions differ from `references/conventions.md`. A
   consistent repository beats a correct file. Read before writing.

6. **Plan the work.**

   ```
   ${CLAUDE_SKILL_DIR}/scripts/plan_tasks.py --state <state> --stack <dir>
   ```

   This reads the state file and prints the components the specification implies,
   grouped into waves. It invents nothing: a component appears only because an
   answer implies it, and what it left out is printed with the reason. Read the
   "not generated" list and check you agree with it — a component missing from the
   plan is a component missing from the stack.

   Show the plan before generating. It is the cheapest moment to catch a
   misunderstanding: a wrong plan costs a sentence, and the same mistake found after
   six modules costs six.

## Order of generation

Not arbitrary. Each step is reviewable on its own, and an early mistake found cheap.

| # | What | Why here |
|---|---|---|
| 1 | `.terraform-version`, `.terragrunt-version`, `.gitignore`, `.architecture-discovery.json` | Both tools pinned before anything depends on either, and the marker in place before there is anything to apply. |
| 2 | `root.hcl` and `live/<env>/env.hcl` | Backend and provider generated once. No account id, and no `get_env` without a default — that makes the whole stack fail `hcl validate` on any machine that has not exported the variable. |
| 3 | Network — module, then unit | Everything else lands inside it. Domains 4, 5 and 7. |
| 4 | Data stores — module, then unit | Domain 12. They dictate subnets, encryption and backup, and are the hardest thing to move later. |
| 5 | Identity — module, then unit | Domain 8. Roles and policies, **before** the compute that takes them as inputs: an ECS task definition requires `execution_role_arn` and `task_role_arn`, a Lambda requires a role ARN. Correct for EKS and IRSA too, whose trust policy reads the cluster's OIDC issuer as one `dependency`. |
| 6 | Compute — module, then unit | Domain 6. Its unit `dependency` blocks point at the network and identity units that now exist. |
| 7 | Observability and delivery | Domains 9 and 10. A resource two modules both claim belongs to the one that **writes** to it — a log group is compute's, and observability takes its name as a dependency. Put it the other way and the graph closes into a circle the `graph` gate refuses. |
| 8 | The stack's README | Last, describing what is actually there. |

The canonical apply order, which `references/layout.md` states once and this table
follows: `registry -> network -> data -> identity -> compute -> observability`.

Write the module and its unit together, then run the gate, then move on. Not all
eight and then a gate: `terragrunt hcl validate` catches a broken `include` or a
mistyped `config_path` in a second, and finding it eight steps later means finding it
in eight places.

A domain recorded `not-applicable` produces nothing, and that is the correct output.
Do not write a placeholder module for it.

## Working through the waves, and when to fan out

`plan_tasks.py` produces waves. Everything inside a wave is independent by
construction — no unit in it names an output of another unit in it. Between waves
there is a real dependency, and doing those at once does not make the stack arrive
sooner; it makes a `config_path` point at a directory that does not exist yet.

**Work through them yourself, one component at a time, gating after each.** That is
the default and it is the right one for most stacks. A four-module stack written in
one thread shares one naming convention, one reading of the state file and one memory
of what the last module named its outputs — and the gate is the same nine checks
however the files got there. Spawning agents to write it buys nothing and costs
coordination.

### When to fan out instead

Three conditions. Any one of them is enough; none of them is common on a small stack:

- **A wave has three or more substantial components.** Two is not worth the
  coordination, and the plan prints the count.
- **The context is already long.** Generation outlives compaction, and six modules of
  file content in this thread is what ends a run early. A builder carries its own
  component and returns fifteen lines.
- **You want a component reviewed by something that did not write it.** This one
  stands on its own, with no parallelism at all: re-reading your own generation is the
  weakest review there is.

The plugin ships three agents for it:

| Agent | Does | Writes |
|---|---|---|
| `iac-planner` | Reads one component's domains, ADRs and provider rows, and returns the file-by-file plan with the decision behind each resource | nothing |
| `iac-builder` | Writes that component's module and its units, following the plan | only `modules/<component>/` and `live/<env>/<component>/` |
| `iac-validator` | Reviews one component against the specification — false provenance, resources nobody asked for, siblings missing | nothing |

`iac-validator` is the one worth reaching for on any stack. The other two earn their
keep on a large one.

### The sequence, when you do fan out

1. **You write the shared files first, before any fan-out.** Steps 1 and 2 of the
   order of generation — the version files, `.gitignore`,
   `.architecture-discovery.json`, `root.hcl`, every `live/<env>/env.hcl` — and you
   resolve the provider versions once with `resolve_versions.py`. These are the files
   every component reads and none of them owns. An agent editing a shared file while
   another reads it is the one failure mode parallelism introduces, and writing them
   up front removes it rather than managing it.

2. **Per wave: one planner per task, all in the same message.** Parallel agents only
   run in parallel if they are launched together. Give each planner its component id,
   the state file path, the stack root and the domains from the plan.

3. **Per wave: one builder per task, all in the same message**, each handed its
   planner's output and the resolved versions. A builder writes only inside its own
   module and unit directories; anything it needs from another component it takes as
   a `dependency` output. Hand every builder the same naming convention explicitly —
   six agents left to infer one will produce six.

4. **You run the real gate.** Not the agents — they run `--draft` over their own
   files, which reports without blocking. The gate that decides is yours, run
   without `--draft`, over the whole tree:

   ```
   ${CLAUDE_SKILL_DIR}/scripts/check_iac.py --state <state> --tf-dir <tree> --artifacts <dir>
   ```

5. **Per wave: one validator per task**, in the same message, for the half no gate
   can check — whether the provenance headers are *true*, whether anything here was
   asked for, whether a required sibling is missing.

6. **Fix the wave before starting the next one.** A finding in wave 1 is almost never
   one finding: it is a class of finding, and every later builder will repeat it.
   This is the same reasoning as rule 8's first-module checkpoint, and with agents it
   matters more, because six builders repeat a mistake at once.

### What stays yours either way

- The shared files, and the versions.
- The real gate, and the decision about what a finding means.
- Every waiver. An agent that meets a secure default it cannot satisfy **stops and
  reports**; it does not write the deviation and mention it afterwards, and it does
  not add a waiver. A waiver names who accepted the risk, and no agent can be that
  person.
- The commit, the pull request, and the handover.

## Environments

One `live/<env>/` directory per environment, its units calling the same modules with
different inputs. Differences between environments are **values**, not code — a
staging stack that has drifted from production's is how a tested change fails in the
place that matters.

Where an environment genuinely differs in shape — no DR replica in staging, a single
availability zone in dev — that is an input driving `for_each` or a `count` ternary,
and the specification's environment topology table says which. Do not infer it.

A component that exists in one environment and not another is a unit directory that
exists in one `live/<env>/` and not the other. That is legible in a directory
listing; a `count = var.environment == "prod" ? 1 : 0` buried in a module is not.

## Delivery

1. Gate clean, without `--draft`.
2. Commit to the agreed branch. The commit message says which specification version
   this implements.
3. Open a pull request. In the description: what was generated, what was left as an
   open question, what the reviewer has to supply before a plan will run
   (credentials, the state bucket, any variable with no default), and the exact
   commands to run a plan — `terragrunt run --all plan` from `live/<env>/`, or
   `terragrunt plan` in one unit.

   Where the repository has no remote — a fresh demo, a spike, an offline
   machine — there is nowhere to open one. Commit to the branch, say plainly that no
   remote is configured and that nothing has been pushed, and give the command to run
   once there is one: `git push -u origin <branch>`. Do not add a remote on the
   user's behalf.
4. **Say plainly that nothing here has been planned against a real account**, and
   that `.architecture-discovery.json` blocks every mutating command until a person
   reviews the plan and deletes it. Say who you expect that person to be. The
   gate checks the tree is coherent; it cannot check the architecture is right or
   that the resources will apply.

## Revising after the specification changes

A revision is not a regeneration.

1. Re-read the state file and find what moved.
2. Change only the files the changed domains touch. Regenerating the tree loses
   every hand edit a reviewer asked for.
3. Update the provenance headers where the decision behind a file changed.
4. Re-resolve versions only if raising a pin is part of the change. A version bump
   smuggled into an architecture change is two reviews in one diff.
5. Re-run the gate, push to the same branch.

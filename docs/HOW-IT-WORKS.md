# How it works

The machinery behind this plugin's two skills: what is loaded and when, what runs as
a deterministic script versus what the model decides, how a decision travels from a
spoken answer to a committed artifact and then to a resource, and what verifies that
the whole thing still behaves.

Written for someone auditing or modifying the plugin. If you only want to run an
interview, [`README.md`](../README.md) is enough.

This page is the map. The detail lives in three documents beside it:

| Document | What it covers |
|---|---|
| [`DISCOVERY.md`](DISCOVERY.md) | Discovery — the interview. The runtime loop, the fourteen domains and which seven block, how an answer becomes an artifact, the five gates and what each refuses, the harness. |
| [`GENERATION.md`](GENERATION.md) | Generation — the stack. What Terragrunt and Terraform each own, the nine standing rules, version resolution, provenance, the nine gates, the harness. |
| [`GUARDRAILS.md`](GUARDRAILS.md) | The `PreToolUse` hook that stops a generated stack being applied, and the gate that checks the secure defaults against the code. What neither covers. |

## Contents

- [The shape of it](#the-shape-of-it)
- [What this is built on](#what-this-is-built-on)
- [Division of labour: model versus scripts](#division-of-labour-model-versus-scripts)
- [What is loaded, and when](#what-is-loaded-and-when)
- [Changing the plugin safely](#changing-the-plugin-safely)
- [Trust and data boundaries](#trust-and-data-boundaries)

## The shape of it

Three parts, and the separation between them is the whole design:

1. **A prompt contract** — `SKILL.md` plus `references/`. Standing rules the model
   follows for the length of the interview, and per-domain question material it loads
   only when that domain is in play.
2. **Deterministic scripts** — `scripts/`. Python, standard library only. They
   inspect the machine, read the repository, and judge the interview's recorded
   state. They write nothing into the project — the only file any of them creates is a
   `gitleaks` JSON report in a temporary directory — and none of them calls a
   model.
3. **A committed state file** — `discovery-state.json`. The interview's memory and
   the only input the gates read. Conversation is not evidence; this file is.

The model conducts the conversation. The scripts decide whether what came out of it
is allowed to ship. Neither can override the other: a script cannot invent an answer,
and the model cannot pass a gate by arguing with it.

Generation repeats that shape exactly one level down. `skills/iac/SKILL.md` plus
its references are the prompt contract; `resolve_versions.py` and
`check_iac.py` are the deterministic scripts; the same committed
`discovery-state.json` is the input — the interview's output is the generation's
contract, which is why the two skills ship together and why `_shared.py` imports the
discovery skill's `_state.py` rather than restating it.

One asymmetry between the two stages is worth naming up front. Every discovery script is
offline. `resolve_versions.py` is not, and it is the only script in the repository
that makes a network call. That is deliberate, and
[`GENERATION.md`](GENERATION.md#why-version-resolution-is-a-script-and-why-it-reaches-the-network)
says what was traded for what.


## What this is built on

| Layer | What | Why this and not more |
|---|---|---|
| Harness | Claude Code skills — `allowed-tools`, injected `!` commands, and three things outside the Agent Skills spec: `when_to_use`, `argument-hint` and `${CLAUDE_SKILL_DIR}` substitution | Those last three are why this will not upload to claude.ai or package with `package_skill.py`, stated in `SKILL.md`'s frontmatter `compatibility` field. |
| Scripts | Python 3.9+, standard library only | Nothing to `pip install`, no lockfile, no supply chain. A skill a teammate cannot run is a skill nobody runs. |
| External binaries | `git`, `gitleaks`, and in generation `terraform` (or `tofu`) and `terragrunt` | The only third-party binaries any script spawns; the other subprocess is `python3` itself, when `run_gates.py` or `check_iac.py` invokes a gate. `gitleaks` is hard-required because the secret scan fails closed without it. The two IaC binaries are not: without either, the half of `fmt` and `validate` that needed it reports that it did not run, and the gate reports "did not run" rather than a pass. |
| Diagrams | Mermaid, embedded in the spec | Diffs in git, renders in the PR. An image nobody can edit is not reviewable. |
| Delivery | A branch and a pull request | Review lands on lines, not in chat scrollback. |
| Verification | Three harnesses and a GitHub Actions workflow | Two prove the gates catch what they exist to catch; `scripts/check_repo.py` proves the layer above — that every reference, grant, version and anchor the repository declares actually exists. CI runs all three, plus the two gates the local harnesses have to skip. |
| Enforcement | A plugin `PreToolUse` hook on `Bash`, scoped by a marker file | The one prompt rule that could not be left to compliance. Scoped so it never touches infrastructure work this plugin did not write. |

Every discovery script is local and offline. None makes a network call, reads an API
key, or contacts a model — the only outbound literals there are two `gitleaks`
installation URLs printed in help text. There is no price table, no cached regulator
text fetched at runtime, and no telemetry anywhere in the repository.

`resolve_versions.py` in generation is the single exception, and its four endpoints are
listed in its module docstring: the HashiCorp releases API, the OpenTofu releases page
on GitHub, and the public Terraform registry's provider and module endpoints. All
public, unauthenticated and read-only; a request carries a provider name and nothing
about the project. `terraform init` reaches the registry too, for the same reason and
under the same terms.


## Division of labour: model versus scripts

| Job | Owner | Why there |
|---|---|---|
| Asking questions, translating jargon, proposing defaults | Model | Needs judgement about the person answering. |
| Recording answers into the state file | Model | It is the only party that heard the answer. |
| Reading the repository for pre-fills | `detect_conventions.py` | Reproducible, evidence-carrying, and cheaper than a model reading a tree. |
| Deciding whether the interview is finishable | Gates | A verdict that changes with phrasing is not a verdict. |
| Writing the artifacts | Model, through the Write tool | Deliberate: nothing the skill creates is written by a subprocess, so every created file stays visible as a tool call rather than happening inside a Python process where Read/Edit permission rules do not reach. |
| Recording a deviation as a waiver | Human, via the model | A gate can detect words, not intent. See below. |

The gates read one input — the state file — and emit one output: an exit code with a
report. They have no memory, no configuration and no discretion, which is what makes
their verdict worth anything.


## What is loaded, and when

Attention is the scarce resource, so neither skill is one large prompt.

**Discovery, `skills/discover/`:**

| Artefact | Loaded | Size discipline |
|---|---|---|
| `SKILL.md` | Always, on invocation | Standing rules and routing only. Rules sit at the top because on compaction only the beginning of the file reliably returns. |
| `references/domain-NN-*.md` | On the first turn of that domain | 15 files. Domain 9 is two files (delivery, IaC/policy) and both are read. |
| `references/compliance/<regime>.md` | When a regime is named | 9 regimes. |
| `references/interview-method.md` | When a turn needs shaping | How to run a turn, how to weigh a trade-off, what to do with a non-answer. |
| `references/interview-examples.md` | When the method is still not concrete | Three worked turns — a vague answer, a real trade-off, an answer that contradicts an earlier one. Read one, not all three. |
| `references/cost-method.md` | On any cost figure | The two cost models, and why there is no price table. |
| `references/secure-defaults.md` | When a deviation is proposed | The reasoning per default, for cases the rules did not anticipate. |
| `assets/*.template.md` | When writing that artifact | 4 templates. |

**Generation, `skills/iac/`:**

| Artefact | Loaded | Size discipline |
|---|---|---|
| `SKILL.md` | Always, on invocation | Nine standing rules, the order of generation, delivery. Rules first, for the same compaction reason. |
| `references/layout.md` | Deciding the directory shape, state backend or environment split | Once, near the start. |
| `references/versions.md` | Writing `versions.tf`, or raising a pin | The pinning policy and why each shape is what it is. |
| `references/providers.md` | Turning a domain answer into resources | Three provider tables, one row per capability the interview can decide — `check_repo.py` asserts the rows keep up with the domains. Read the one in play. |
| `references/conventions.md` | Before the first resource, and when suppressing a scanner finding | The four gated conventions, the thirteen guardrails, and the suppression discipline. |
| `assets/*.template.md` | When writing the files | 2 templates. |
| `assets/scanner-config.template.yaml` | Setting up the policy scanner | The suppression skeleton, with the three categories pre-labelled. |

Generation injects nothing. There is no equivalent of `preflight.py --context` because
its session facts are in the state file it is about to read.

Each `SKILL.md` carries a routing table for exactly this, so a domain's material is a
lookup rather than a judgement call.

One line of `SKILL.md` is executed rather than read: an injected
`preflight.py --context` call that resolves the session's facts — working directory,
repository root, any existing `discovery-state.json`, and what infrastructure is
already present — before the model's first sentence. That script is written to always
exit 0, because a non-zero exit from an injected command aborts the whole skill
invocation, and an unreadable directory must never be what stops an interview
starting.


## Changing the plugin safely

Where a change belongs to one phase, its own document has the detail —
[`DISCOVERY.md`](DISCOVERY.md), [`GENERATION.md`](GENERATION.md),
[`GUARDRAILS.md`](GUARDRAILS.md). This table is the index.

| Change | What else has to move |
|---|---|
| Add a gate | A `check_*.py` in `scripts/`, an entry in `GATES` and `DESCRIPTIONS` in `run_gates.py`, an `_argv` branch, and a paired case in `selftest.py`. No rule in `allowed-tools` — it runs as a subprocess of `run_gates.py`. |
| Add or rename a domain | `DOMAINS` in `_state.py`, `BLOCKING` if it blocks, `ANSWER_KEYS` if a gate reads it, a `references/domain-NN-*.md`, and the domain table in `SKILL.md`. |
| Add an answer key a gate reads | `ANSWER_KEYS` in `_state.py`, and a `selftest.py` case proving a paraphrase is caught. |
| Add a compliance regime | `compliance_controls.json`, a `references/compliance/<regime>.md`, aliases in `REGIME_ALIASES`, and `RESIDENCY_REGIMES` if it carries a residency obligation — the harness asserts those two agree. |
| Add or change a generation agent | A file in `agents/` whose frontmatter `name` matches its filename, the fan-out sequence in `skills/iac/SKILL.md`, and `check_repo.py` asserts every agent a SKILL.md names exists. An agent is loaded by name: naming one that is not installed fails several steps into a generation. |
| Add a component to the task plan | `COMPONENTS` and `ORDER` in `plan_tasks.py`, with its trigger pattern matched against the domains that decide it, and the harness case that asserts the waves stay independent. |
| Add an entry-point script | `ENTRY_POINTS` in `preflight.py`, a rule in that skill's `allowed-tools`, and the executable bit. Read the next section first. |
| Add an IaC gate | A `gate_*` function in `check_iac.py`, an entry in `GATES` and `DESCRIPTIONS`, a branch in `runners`, and a paired case in `skills/iac/scripts/selftest.py`. No new `allowed-tools` rule. |
| Add a guardrail check, or change what the hook blocks | See [`GUARDRAILS.md`](GUARDRAILS.md#changing-them-safely). Both have a bar higher than the other gates: the hook must not touch infrastructure work this plugin did not write, and a check must be always right rather than usually right. |
| Add a row to `providers.md` | Nothing, unless it is a new capability — then a key in `PROVIDER_CAPABILITIES` in `scripts/check_repo.py`, which asserts every provider table has a row for it and that a domain reference file still asks about it. |
| Add a conventions rule | The regex and the check in `gate_conventions`, a row in `references/conventions.md`, and a `selftest.py` case. Only add one that is *always* right — a rule producing findings nobody can act on is how a gate gets skipped. |
| Support a new Terragrunt CLI spelling | `_tg_hcl` in `check_iac.py` and `TERRAGRUNT_HCL_CLI_FROM`. The 0.78 rename is why that dispatch exists; another one will need the same treatment. |
| Add a provider to the resource mapping | A table in `skills/iac/references/providers.md`, and its short names in `PROVIDER_NAMESPACES` in `resolve_versions.py` if they are not already resolvable. Nothing in the gates: they check pinning and provenance, not which provider. |
| Change what a pin may look like | `EXACT_VERSION` in `check_iac.py`, the table in `references/versions.md`, the `hcl_block()` writer in `resolve_versions.py`, and a `selftest.py` case for the shape now refused. |
| Release | Run `python3 scripts/bump_version.py X.Y.Z`, which bumps `plugin.json`, both skills and the changelog together; that bump *is* the release. Describe it in [`CHANGELOG.md`](../CHANGELOG.md). |

### The third harness

```bash
python3 scripts/check_repo.py
```

Seven checks over the layer the gate harnesses cannot see: every relative link and
anchor across the seven documents, frontmatter that parses and carries the keys the
skill depends on, `metadata.version` agreeing with `plugin.json`, every
`allowed-tools` grant pointing at a file that exists and is executable, every
`references/` and `assets/` path a `SKILL.md` names, a reference file for every domain
in `_state.DOMAINS` and every regime in `compliance_controls.json`, the guardrail hook
wired through the manifest, and a marketplace entry that resolves.

None of those break a gate. All of them break the skill, quietly — a reference the
model is told to read and cannot is an instruction with nothing behind it, a drifted
version ships one number and announces another, and a missing executable bit costs a
permission prompt the grant was written to avoid.

### Continuous integration

`.github/workflows/checks.yml`, on every push to `main` and every pull request. Two
jobs.

**`harnesses`** runs `check_repo.py` and both gate harnesses on **Python 3.9** — the
floor `preflight.py` enforces, so a 3.10-ism cannot reach a teammate on what the
manifest allows — with `gitleaks` installed, because without it the secret scan fails
closed and its harness case is skipped.

**`stack`** closes the gap the local harnesses cannot. `fmt` and `validate` are
skipped there because they need both IaC binaries and a reachable registry; CI has
both. It builds the harness's own clean fixture — the same definition, so the two
cannot disagree about what is being tested — puts it through all nine gates for
real, and then **fails if the summary contains a `did not run` marker**, because a
job passing on the strength of checks that never happened is the exact failure this
repository is built around avoiding. Finally it runs the guardrail hook against that
stack on disk rather than a synthetic fixture.

Versions of `gitleaks` and Terragrunt are pinned in the workflow's `env`, for the
same reason the generated stacks pin their providers.

`.github/dependabot.yml` watches one ecosystem, `github-actions`, monthly and grouped
into a single pull request. The three pinned actions are the only dependencies this
repository resolves — it is stdlib Python and Markdown otherwise — and a pinned action
goes stale silently, since the build keeps passing on a version nobody has looked at.
The two `env` pins are deliberately outside that: they are release URLs fetched with
curl, which no dependency ecosystem sees, so they move by hand. Every Dependabot pull
request runs the same two jobs as any other.

### Why `allowed-tools` is seven lines across two skills

```yaml
# skills/discover/SKILL.md
allowed-tools:
  - Bash(${CLAUDE_SKILL_DIR}/scripts/preflight.py *)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/detect_conventions.py *)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/run_gates.py *)

# skills/iac/SKILL.md
allowed-tools:
  - Bash(${CLAUDE_SKILL_DIR}/scripts/preflight.py *)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/plan_tasks.py *)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/resolve_versions.py *)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/check_iac.py *)
```

Seven entry points: check the machine and read the repository before the interview,
run the interview's gates, check the machine again before generation, plan the
components and their waves, resolve versions, run the IaC gates. Nothing else is granted — and notably not
`terraform` itself, so no grant in this plugin can run an `apply`. `check_iac.py`
spawns `terraform fmt`, `init -backend=false` and `validate` as subprocesses, all three
read-only, and nothing else. `Read`, `Write`, `Edit`, `Glob`, `Grep` and `AskUserQuestion` are
used under the session's existing permissions, exactly as any other work is — as are
the three generation subagents in `agents/`, which inherit the session's permissions
and grant nothing of their own. `iac-builder` is the only one of the three with write
tools at all, and the hook denies a mutating command from a subagent exactly as it
does from the main thread: it sees tool calls, not who made them.

That restraint matters more than it looks. A skill's `allowed-tools` grant is
[never gated by workspace trust](https://code.claude.com/docs/en/permissions), and at
personal scope it applies in **every repository you open**. Read any addition to that
list as a change to what this skill can do everywhere on the machine.

Two consequences worth knowing:

- Rules match a **direct invocation** of the script path, which requires the
  executable bit. Without it the script still runs via `python3 <path>`, but that
  command matches no rule and prompts — which is why `preflight.py` treats a missing
  executable bit as exit 1 rather than a cosmetic warning.
- A Bash permission rule **does not extend across shell operators**. `run_gates.py`
  chained behind `&&` falls outside the rule, which is why `SKILL.md` says to invoke
  it on its own and why `run_gates.py` builds argument lists instead of command
  strings.

One honest caveat on both of those. That the grant is *minimal* is verifiable by
reading it. That it actually *suppresses prompts* was never observed working — three
attempts in non-interactive `-p` runs could not discriminate granted from ungranted
scripts, which is [`LIMITATIONS.md`](../LIMITATIONS.md) L7. So the matcher behaviour
above rests on documented rule semantics rather than on a measurement taken here. The
security property — that each skill grants nothing beyond its own entry points — does
not depend on it.


## Trust and data boundaries

**Everything in the output directory is committed, including `discovery-state.json`.**
Committed means published, and once pushed it may be cached or indexed even if it is
later deleted.

So the interview **references configuration rather than copying it**: "the account id
in `root.hcl`", not the twelve digits. This keeps the identifier out of the
transcript and out of any summary of it, as well as out of the artifacts. The secret
scan is what makes that rule enforceable rather than aspirational.

The Terraform tree is committed on the same terms, which is why backend configuration
is partial: `backend "s3" {}` in git, the bucket name in an uncommitted `backend.hcl`.
A state bucket name discloses the account and often the client, and the same secret
scan runs over the generated tree.

**Almost everything the scripts do is local.** They read the repository, the state file
and the tree, spawn `git`, `gitleaks` and `terraform`, and print. They never write
artifacts, and they hold no environment specifics themselves — account IDs, registry
URLs and endpoints are read from repository configuration at runtime, never baked in.

The exception is version resolution, stated rather than buried: `resolve_versions.py`
reads four public unauthenticated endpoints, and `terraform init` reads the registry.
Nothing about the project is sent to either — a request carries a provider name. No
script anywhere contacts a model or reads an API key.

**Three things this plugin will never do**, all structural rather than stylistic:
apply Terraform, invent a price, and assert that you are compliant. The first is rule
3 of generation, the shape of the `allowed-tools` grant — which contains no route to
`terraform apply` — and a `PreToolUse` hook that denies the mutating verbs inside any
stack this plugin generated, until a person deletes the marker file that says nobody
has taken ownership of it.

The cost gate enforces the second by refusing a figure with no assumptions. The
compliance gate enforces the third by
producing a worklist of obligation → control → evidence with verification assigned to
a named owner, and by failing outright on a regime it has no sourced controls for.

Standing limits — twenty-two of them, including the three unsourced regimes, the
advisory nature of every control mapping, and what the guardrails do not cover — are
in [`LIMITATIONS.md`](../LIMITATIONS.md). Read it before relying on this for anything
consequential.

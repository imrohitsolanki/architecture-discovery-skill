# architecture-discovery-skill

A Claude Code plugin in two phases. The first turns a requirements conversation into
a reviewable infrastructure specification — with diagrams, decision records, a costed
estimate and an owned list of everything still open. The second turns that approved
specification into a Terragrunt and Terraform stack, with every version pinned to
what the registry publishes today and every file naming the decision that put it
there.

You answer questions. It writes the document, checks its own work, and opens a pull
request your team can comment on. Then, once the document is signed off, it writes
the infrastructure code the document describes — and nothing the document did not.

## The problem it solves

A new project's requirements session is usually ad hoc. Things get forgotten, the
awkward questions get skipped, and the real decisions get made three weeks later
under time pressure with nobody recording why. Then someone asks "why are we on
Kubernetes?" and the answer is lost.

This makes that session repeatable, and ends it in artifacts a team can review.

## Who this is for

**If you gather requirements** — an engineering manager, a consultant, a tech lead
running a scoping call — this is the checklist you would otherwise keep in your head,
and it writes the document for you.

**If you are the one answering** — a product manager, a founder, a client — you do
not need to know what an ingress controller is. Every question arrives as options
with a recommended default and a one-line explanation of the trade-off, so you are
choosing between consequences rather than being quizzed about tools. "I don't know
yet" is always an available answer, and it becomes a tracked question rather than a
guess.

## Contents

- [Requirements](#requirements)
- [Install](#install)
- [Your first run](#your-first-run)
- [What a session is actually like](#what-a-session-is-actually-like)
- [What you get](#what-you-get)
- [Generation: the infrastructure code](#generation-the-infrastructure-code)
- [Guardrails](#guardrails)
- [How it works](#how-it-works)
- [Three things it will never do](#three-things-it-will-never-do)
- [What gets committed](#what-gets-committed)
- [Troubleshooting](#troubleshooting)
- [Honest limits](#honest-limits)
- [For maintainers](#for-maintainers)

## Requirements

| | | |
|---|---|---|
| **Claude Code** | required | The plugin runs nowhere else. |
| **Python 3.9+** | required | The validation gates. Standard library only — there is nothing to `pip install`. |
| **git** | required | Artifacts are delivered as a branch and a pull request. |
| **`gitleaks`** | required | The secret scan. **Without it the scan fails closed and you cannot finish** — see below. |
| **`terraform`** | generation only | `fmt` and `validate` over the modules. Without it those halves report that they did not run, which is not the same as passing. `tofu` works too. |
| **`terragrunt`** | generation only | `hcl fmt` and `hcl validate` over the units. Same rule: absent means those halves did not run. |
| **Network access** | generation only | Provider and module versions are resolved from the public registry at generation time. There is no bundled version table and there will not be one. |

Install `gitleaks`:

```bash
brew install gitleaks
```

Other platforms: <https://github.com/gitleaks/gitleaks#installing>.

`gitleaks` is a hard dependency on purpose. The specification and the interview's
state file both get committed, so they are scanned before that happens. A scan that
silently passes because the scanner is missing is worse than a blocked interview, so
a missing `gitleaks` stops you rather than waving you through.

The interview checks all of this on its first turn and tells you what is missing, so
you do not have to verify it up front. If you cloned the repository and want to check
now:

```bash
python3 skills/discover/scripts/preflight.py
```

## Install

The plugin route:

```bash
/plugin marketplace add rohit-solanki-k/architecture-discovery-skill
/plugin install architecture-discovery@architecture-discovery
```

Or clone it, so you can read and edit what you are running:

```bash
git clone https://github.com/rohit-solanki-k/architecture-discovery-skill.git
ln -s "$(pwd)/architecture-discovery-skill" ~/.claude/skills/architecture-discovery
```

Any folder under `~/.claude/skills/` containing a `.claude-plugin/plugin.json` loads
on your next session, with no install step. That directory is personal scope, so it
loads in **every** project you open — and the symlink keeps the repository as the
single source of truth: `git pull` and the change is live next session.

To try it without installing anything:

```bash
claude --plugin-dir /path/to/architecture-discovery-skill
```

To stop it loading: `claude plugin disable architecture-discovery@skills-dir`, or
remove the symlink.

> **A note on teammates.** Installing this is per-person. It does **not** arrive when
> someone clones your project — personal-scope plugins never do. Each teammate
> installs it themselves.

## Your first run

**1. Open Claude Code in the repository the work belongs to.** Artifacts are written
there, so run it from the project's repo, not from this plugin's directory. If the
project has no repository yet, any repo you intend to keep the planning docs in is
fine.

**2. Start the interview.**

```
/architecture-discovery:discover acme-lending
```

The name is the project slug — it becomes the output folder. You can also just say
what you are doing and let it pick up:

> new client project just landed, some kind of lending app. their PM is on a call
> with me tomorrow and i need to come out of it knowing what we're building

**3. Agree two things before the questions start** — where the documents go
(default: `docs/architecture/<project-slug>/`) and the branch name. It asks rather
than deciding silently.

**4. Answer the questions.** Three to five at a time, one topic at a time.

**5. Stop whenever you like.** Progress is saved to a file after every topic. See
[resuming](#pausing-and-resuming).

## What a session is actually like

**Fourteen topics**, in an order that is not arbitrary — each one's answers narrow
the next. What the product is and what an outage costs comes first, because
everything else hangs off it. Cost and operations come last, once there is something
to cost.

**Three to five questions per turn.** Past five, answers get shorter and worse — you
get two considered replies and eight shrugs, and afterwards you cannot tell which
were which.

**Earlier answers close later branches.** Choose serverless and the node-strategy
questions never get asked. Say PCI-DSS applies and segmentation, key custody and
twelve-month log retention open up. Say the team is two people with nobody on a
pager, and every platform question tilts toward managed — and if a self-hosted
control plane gets chosen anyway, that is flagged as a contradiction, not a
preference.

**It reads your repository first** and pre-fills what it can — cloud provider,
region, IaC layout — always labelled as a guess for you to confirm. A pre-fill
presented as fact is how the wrong tool ends up in a signed-off document.

**It never stalls on a question.** Anything unknown becomes a row in
`open-questions.md` with a proposed default, a named owner and a date the default
takes effect. Then it moves on.

### Pausing and resuming

State is written to `discovery-state.json` after every topic, so an interview can
span days and survive a session ending. To resume, invoke it again in the same
repository — it reads the state, tells you in a short paragraph what is already
answered, and continues from the first unfinished topic. **It never re-asks a
finished one.**

## What you get

Written to `docs/architecture/<project-slug>/`, on a branch, as a commit:

| File | What it is | Who reads it |
|---|---|---|
| `architecture-spec.md` | The decisions, with rationale, the alternatives rejected and why, a per-environment topology table, three diagrams, and security controls mapped to each compliance obligation named | Engineers, reviewers |
| `README.md` | Plain language: what is being built, what it costs, what is needed from you, what is still open, what that means for the timeline | The PM or client |
| `decisions/ADR-NNN-*.md` | One short record per significant choice — context, decision, alternatives, consequences | Whoever asks "why did we do it this way?" in a year |
| `open-questions.md` | Every unresolved item with an owner and a deadline | Everyone, at the next standup |
| `discovery-state.json` | The machine-readable record, so a revision does not restart the interview | The tool itself |

Diagrams are [Mermaid](https://mermaid.js.org/) source embedded in the specification,
so they diff in git and render in the pull request rather than being an image nobody
can edit. Three are always produced: network topology, delivery flow, and environment
promotion.

Open questions look like this — every row has an owner and a date, because a question
with neither is not a question anyone will answer:

| ID | Question | Domain | Proposed default | Owner | Default applies from | Status |
|---|---|---|---|---|---|---|
| OQ-3 | Does the client hold cardholder data directly? | 03-compliance | Assume yes and scope for PCI-DSS | Client CTO | 2026-09-20 | Open |

**Review happens in the pull request**, so comments land on specific lines instead of
scrolling away in a chat log. On a revision it updates only the affected documents,
checks what the change invalidated, re-runs its checks, tells you what moved, and
pushes to the same branch so the review stays in one place.

### It checks its own work before writing anything

Five gates run before a specification is emitted, and a failure stops it:

| Gate | Refuses when |
|---|---|
| Completeness | A topic that cannot be defaulted is still unanswered |
| Contradictions | Two answers cannot both be satisfied |
| Compliance coverage | A named regime has an obligation nothing addresses |
| Cost | A price has no stated assumptions, or the total exceeds your ceiling |
| Secret scan | A credential, key or account identifier reached the documents |

Once the specification is approved, [generation](#generation-the-infrastructure-code) writes the
Terraform that implements it.

## Generation: the infrastructure code

Once the specification is approved and its gates pass:

```
/architecture-discovery:iac acme-lending
```

It reads `discovery-state.json` — not the conversation, not a recollection of it —
and writes a Terraform tree that implements what the interview decided. On its own
branch, as its own pull request, so the document review and the code review do not
collide.

```
infra/
  .terraform-version        both tools pinned, in files tfenv and mise read
  .terragrunt-version
  root.hcl                  backend and provider, generated once for every unit
  modules/                  Terraform. The only .tf in the repository.
    network/ data/ compute/
  live/
    prod/
      env.hcl               this environment's values
      network/terragrunt.hcl    a unit: which module, which inputs, what it needs
      compute/terragrunt.hcl
    staging/                the same code, different values
```

Terraform writes the modules; Terragrunt composes them into environments — one
`root.hcl` instead of a `backend.tf` and a `providers.tf` copied into every
environment directory, which is where those copies drift. Below roughly three
components it does not pay for itself, and where the specification recorded plain
Terraform it follows the specification.

Five things worth knowing before you read the diff:

- **Versions come from the registry, not from memory.** A model's idea of the latest
  AWS provider is its training cut-off's idea, and a `~> 5.0` written long after 6.x
  shipped looks deliberate, reviews clean, and freezes the project a major version
  behind. If the registry is unreachable it resolves nothing and asks.
- **Every file says which decision put it there**, and that is a gate. The
  characteristic failure of a generator is not a wrong resource, it is a **plausible**
  one nobody asked for — and a plausible resource reviews clean, gets applied, and is
  billed monthly forever.
- **Unknowns become variables with no default**, so a plan fails loudly rather than
  provisioning a size nobody chose.
- **It never invents a resource, and never generates without a specification.** A
  domain the interview recorded as not-applicable produces nothing, which is the
  correct output — and with no `discovery-state.json` there is nothing to implement,
  because guessing the architecture is the one failure this plugin exists to prevent.
- **It never applies what it wrote**, and that one is enforced rather than promised —
  see [Guardrails](#guardrails).

Nine gates run over the result: the specification's own gates, pins, provenance,
conventions, [guardrails](#guardrails), the dependency graph, formatting, validation
and the secret scan. Formatting and validation each cover **both tools, every run** —
`terraform fmt` does not touch `terragrunt.hcl` and `terragrunt hcl fmt` does not
touch `.tf`, so checking one leaves the other to be reformatted by whoever notices in
CI. Either half failing fails the gate; either half being unable to run means the gate
did not run, which is not the same as passing.

**A clean run means the tree is ready for review. It does not mean it is ready to
apply** — nothing here has seen a plan against a real account, and quotas, service
control policies and what already exists in the account are all invisible to it. The
first plan is a review step, not a formality.

How it groups the components into waves and when it fans out to the three subagents,
what each gate reads and what it refuses, and why version resolution is a script:
[`docs/GENERATION.md`](docs/GENERATION.md).

## Guardrails

Two of them, and they answer different questions. Neither is a wall.
[`docs/GUARDRAILS.md`](docs/GUARDRAILS.md) states exactly what each one does and does
not cover.

### It cannot apply what it generated

Generation's rule is that it never applies, never destroys, never touches a real
account. That used to be a sentence in a prompt — a rule with nothing behind it but
the model's own compliance.

It is now enforced. The generated stack carries `.architecture-discovery.json`, and
the plugin ships a hook that **denies** `apply`, `destroy`, `import`,
`run --all apply` and state-mutating commands anywhere inside a directory holding
that marker. `plan`, `validate`, `fmt`, `init`, `show` and `output` are untouched:
they are how the review happens.

**The marker is the handover.** A person reads the plan and takes ownership by
deleting the file — a deliberate one-line action by a human, which is the right shape
for a decision about applying infrastructure nobody has reviewed. It is committed, so
a reviewer who clones the branch is protected too.

**It only fires inside stacks this plugin wrote.** Your ordinary Terraform work in
every other repository is untouched, which is the point: a hook that blocked
`terraform apply` everywhere would be uninstalled within a day, and the real
protection would go with it.

### It cannot quietly drop a secure default

The interview asserts private subnets, encryption at rest and in transit, no public
data stores, least privilege, no long-lived static credentials. The `guardrails` gate
checks thirteen patterns **against the generated code**, not against the document
that asserts them — eight on something present that should not be (an admin port open
to `0.0.0.0/0`, a publicly reachable data store, encryption switched off, a wildcard
IAM policy, a static credential, an unrestricted `mock_outputs`, key rotation
disabled, a secret-shaped variable with a literal default) and five on something
absent that should be there (a VPC with no flow log, a public load balancer with no
access logs, a KMS key with no policy).

The second half is the one a generator fails, because nothing on the page is wrong. A
public load balancer on 443 is normal and is deliberately not a finding; a guardrail
that cries wolf is one people switch off, and the thirteen that matter go with it.
Where you named Checkov, tfsec, Trivy or Terrascan in the interview, the gate runs
that too.

**A deviation you already accepted is not refused twice.** If the interview recorded
a waiver — naming the control, the deviation, the reason and who accepted it — the
finding is reported rather than blocked. A recorded decision has to be implementable.

### Neither is a wall

The hook sees tool calls, not your machine — a terminal the agent is not driving, a
CI job, or a teammate's laptop is not covered, and nor is a stack whose marker has
been deleted. The gate is thirteen patterns, not a security audit.

Treat them as well-placed tripwires on specific failures, not as controls that make a
mistake impossible. The thing that actually protects production is a person reading
the plan.

## How it works

Two skills, and three parts within each. The separation is the design:

- **A prompt contract** — `SKILL.md` and `references/`. Eight standing rules the model
  follows for the whole interview, nine for generation, plus per-domain question material loaded only when
  that domain is in play.
- **Deterministic scripts** — `scripts/`. Python, standard library only, offline. They
  check the machine, read the repository, and judge the interview's recorded state.
  They write nothing into your project and never call a model.
- **A committed state file** — `discovery-state.json`. The interview's memory, and the
  only input the gates read. Conversation is not evidence; the file is.

The model conducts the conversation. The scripts decide whether what came out of it is
allowed to ship. Neither overrides the other: a script cannot invent an answer, and
the model cannot pass a gate by arguing with it.

The gates themselves are checked by three harnesses — one per skill, each running
every gate against a state it must accept and a state it must reject, plus
`scripts/check_repo.py` over the layer neither can see. All three run in CI on every
push, along with the two gates the local harnesses have to skip. What each covers is
in [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md#the-third-harness).

It does **not** evaluate the interview's judgement. Whether it asks good questions,
holds the three-to-five limit or labels its pre-fills as inferences is prompt
discipline with no automated check behind it, deliberately: grading judgement costs
model calls to produce noisy verdicts.

Routing is not judgement, so that part is measured. `evals/` holds six
`claude plugin eval` cases — three phrasings that must reach a skill, three that must
reach neither — because every anti-trigger instruction this plugin has lives in
`when_to_use` and nothing else looks at it. It is run when a skill's frontmatter
changes and before a release, not in CI, since a model call per case buys nothing on
a commit that edited a script.

The full account is in `docs/`, split by what you are looking at:

| | |
|---|---|
| [**`HOW-IT-WORKS.md`**](docs/HOW-IT-WORKS.md) | The map. What loads when, the division of labour between the model and the scripts, trust boundaries, and what has to move when you change something. |
| [**`DISCOVERY.md`**](docs/DISCOVERY.md) | Discovery. The runtime loop, the fourteen domains and which seven block, every gate rule and exit code, the harness. |
| [**`GENERATION.md`**](docs/GENERATION.md) | Generation. What Terragrunt and Terraform each own, the nine standing rules, version resolution, provenance, the nine gates, the harness. |
| [**`GUARDRAILS.md`**](docs/GUARDRAILS.md) | The hook and the secure-defaults gate — how each is scoped, and what neither covers. |

## Three things it will never do

**It will never apply what it wrote.** Not at your suggestion either. This is the one
that is enforced rather than promised — see [Guardrails](#guardrails) — because a
generated stack has never been planned against a real account, and a rule with
nothing behind it but good intentions is not a rule.

**It will never invent a price.** Every figure derives from assumptions it shows you,
with the arithmetic. Anything nobody can price yet is marked unpriced with a note —
labelled, not guessed. A number with no assumptions attached cannot be told apart
from one that was made up, and once it has a currency symbol beside it somebody will
plan against it. Every figure is a planning range, **not a quote** — check it against
your provider's calculator before committing budget.

**It will never tell you that you are compliant.** It maps each obligation to a
proposed control and the evidence an assessor would ask for, and records that
verifying it belongs to a named owner. It advises; it does not certify. No mapping it
produces has been reviewed by an auditor or by counsel.

Three regimes — **HIPAA, ISO 27001 and SOC 2** — have no control list in this build,
because their primary texts could not be retrieved. Naming one of those makes the
compliance gate **fail** rather than pass quietly, because an empty control list
would otherwise read exactly like a clean bill of health.

## What gets committed

The documents and `discovery-state.json` go into your repository, which means
anything written there is published — and once pushed it may be cached or indexed
even if you delete it later.

So the interview references configuration rather than copying it: "the account id in
`root.hcl`", not the twelve digits. Nothing sensitive should be typed into an answer,
and the secret scan blocks the commit if something is. If you are asked for a value
that looks like a credential, give the file that holds it instead.

## Troubleshooting

**It did not trigger when I described my project.** Invoke it directly:
`/architecture-discovery:discover <project-name>`. It also deliberately stays out of
work on infrastructure that already exists — reviewing a live cluster, debugging a
running deployment, forecasting spend on current resources, editing existing
Terraform. Those act on what is built; this scopes what is not.

**"gitleaks is not installed" and I cannot finish.** That is the intended behaviour,
not a bug. `brew install gitleaks`, then continue — your progress is in
`discovery-state.json`.

**A gate is blocking me and I disagree with it.** Two legitimate exits: fix the cause,
or record a waiver in the state file naming the control, the deviation, the reason and
who accepted it. Some deviations are correct. What is not available is emitting the
document anyway and mentioning it afterwards.

**It is asking about things my project does not have.** Say so — "not applicable" is a
real answer and gets recorded with the reason. A serverless application genuinely has
no node strategy, and inventing one would be worse than recording why there is none.

**I want to see what remains without being blocked.** Ask it to run the gates in draft
mode; it reports everything and blocks nothing.

**It pre-filled something wrong.** Correct it. Pre-fills are labelled as inferences
precisely so they can be contradicted.

**Generation says there is nothing to generate from.** It needs a `discovery-state.json`.
Run the interview first — it does not conduct one itself, because a generator that
invents the architecture is worse than no generator.

**Version resolution exits 3.** It could not reach the registry. Nothing
was resolved and nothing was guessed. Restore network access, or supply the versions
yourself and say where they came from.

**`fmt` or `validate` says it did not run.** One of the two binaries is missing —
`terraform` for the modules, `terragrunt` for the units — or `init` could not reach
the registry. A gate that did not run has not passed, which is why
the summary says so rather than quietly counting it as a pass.

**It refuses to run `terraform apply`.** That is the guardrail, not a bug. The stack
has never been planned against a real account. Read the plan, then delete
`.architecture-discovery.json` from the root of the tree — that deletion is the
record that a person read what this does and accepts it.

**The hook is blocking a command in a repository this plugin never touched.** It
should not: it only fires when a `.architecture-discovery.json` is in the directory
or above it. If one is there and should not be, delete it.

**A generated resource is wrong.** The specification is upstream and wins. Fix the
specification, re-run the interview's revision flow, then let generation update only the
files the changed domains touch.

## Honest limits

[`LIMITATIONS.md`](LIMITATIONS.md) records twenty-two standing limits in full — among
them the three unsourced compliance regimes, the advisory nature of every control
mapping, cost figures being planning ranges rather than quotes, version resolution
needing the network with no fallback, the guardrails being well-placed tripwires
rather than controls that make a mistake impossible, and that no generated stack has
ever been planned against a real account.

**Read it before relying on this for anything consequential.**

## For maintainers

### Layout

```
.claude-plugin/
  plugin.json          manifest; bumping its version is the act of releasing
  marketplace.json     so `/plugin marketplace add` works
skills/discover/       discovery — the interview
  SKILL.md             always-loaded body: standing rules and routing only
  references/          15 domain files, 9 compliance regimes, method, cost, defaults
  scripts/             3 entry points, 5 gates, a shared state contract, a selftest
  assets/              4 artifact templates
skills/iac/            generation — the stack
  SKILL.md             9 standing rules, generation order, parallel waves, delivery
  references/          layout and state, conventions, version pinning, resource mapping
  scripts/             4 entry points, 9 gates, a selftest
  assets/              stack skeleton, generated-stack README, scanner config
agents/                the three subagents generation fans out to
  iac-planner.md       plans one component, writes nothing
  iac-builder.md       writes one component, owns only its own files
  iac-validator.md     reviews one component, writes nothing
hooks/
  hooks.json           a PreToolUse hook, so "never apply" is enforced not promised
  block_mutating_iac.py
scripts/
  check_repo.py        the third harness: links, grants, versions, routing
.github/
  workflows/checks.yml all three harnesses, plus the two gates they have to skip
  scripts/             what that workflow runs, kept out of the YAML
  dependabot.yml       the three pinned actions, monthly, in one grouped PR
docs/
  HOW-IT-WORKS.md      the map: what loads when, trust boundaries, changing it
  DISCOVERY.md         discovery internals
  GENERATION.md        generation internals
  GUARDRAILS.md        the hook and the secure-defaults gate, and their limits
```

Nothing else. The repository is the plugin.

Run all three after touching anything under `scripts/`, `hooks/` or `docs/`:

```bash
python3 scripts/check_repo.py                   # links, grants, versions, routing
python3 skills/discover/scripts/selftest.py     # the interview's five gates
python3 skills/iac/scripts/selftest.py    # the stack's nine gates, and the hook
```

CI runs all three on every push and pull request, plus the fixture stack through
`fmt` and `validate` for real.

### The check that matters

```bash
python3 skills/discover/scripts/selftest.py
```

It builds a clean state and a violating one per gate and asserts each gate accepts
the first and rejects the second. A gate that cannot catch its own violation is worse
than no gate, because it reads as a clean bill of health — so a gate added without a
case here is a gate with no evidence it does anything. It also pins every gate defect
found so far, so none of them can come back quietly.

What has to move when you add a gate, a domain, an answer key or a compliance regime
is tabulated in
[`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md#changing-the-plugin-safely).

### The `allowed-tools` grant

Seven entry points across the two skills, and nothing else granted — notably not
`terraform` or `terragrunt` themselves, so no grant here reaches an `apply`. `Read`,
`Write`, `Edit`, `Glob`, `Grep` and `AskUserQuestion` are used under your session's
existing permissions exactly as any other work does.

That restraint matters more than it looks: a skill's `allowed-tools` grant is
[never gated by workspace trust](https://code.claude.com/docs/en/permissions), and at
personal scope it applies in **every repository you open**. What each entry point is
and what a change to that list means is in
[`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md#why-allowed-tools-is-seven-lines-across-two-skills).

### Releasing

The version in `plugin.json` decides when anyone who installed from a marketplace
receives an update, so bumping it *is* the release. [`CHANGELOG.md`](CHANGELOG.md)
defines what counts as major, minor and patch for a skill.

## Licence

MIT. See [LICENSE](LICENSE).

---
name: discover
description: Run a structured architecture discovery interview for a system that has not been built yet, then emit a reviewable infrastructure spec, Mermaid diagrams, ADRs and an open-questions log as a branch and PR. Use this whenever a new project, service or client engagement needs its infrastructure scoped, whenever infra or platform requirements are being gathered from a product or project manager, or whenever architecture is being planned before anything exists.
when_to_use: |
  Trigger on casual phrasing as readily as formal: "new client project, need to scope the infra", "the PM wants to know what we need for the new service", "what do we need to build for this", "help me not forget anything in tomorrow's requirements call". Trigger when resuming or revising an interview that already has a discovery-state.json. Trigger even when the user never says "architecture" or "discovery" but is clearly scoping something not yet built. Do not trigger for work on infrastructure that already exists: reviewing a live cluster's network policy, debugging a running deployment, estimating next quarter's spend on current resources, editing existing Terraform, or writing an ADR for a decision already made. Those act on what is built; this scopes what is not.
argument-hint: "[project or client name]"
allowed-tools:
  - Bash(${CLAUDE_SKILL_DIR}/scripts/preflight.py *)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/detect_conventions.py *)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/run_gates.py *)
metadata:
  version: "1.0.0"
compatibility: "Claude Code only. Uses when_to_use, argument-hint and ${CLAUDE_SKILL_DIR} substitution, none of which are in the Agent Skills spec, so this will not upload to claude.ai or package with package_skill.py."
license: MIT
---

# Architecture discovery

Turn a requirements conversation into a reviewable specification. The person on the
other side is often non-technical, so the interview does the translating.

Session facts, resolved before you read this:

!`${CLAUDE_SKILL_DIR}/scripts/preflight.py --context`

If a state file is listed above, this is a resume. Read it before saying anything
else, and go to **Resuming** below.

## Standing rules

These apply for the whole interview, not just the first turn. They are first in this
file because an interview outlives compaction, and on compaction only the beginning
of this file comes back.

### 1. The state file is the interview

Write `discovery-state.json` into the artifact directory after finishing each
domain, not at the end. An interview spans sessions and will outlive compaction; the
file is what survives, and your memory of the conversation is not.

The schema is documented in `${CLAUDE_SKILL_DIR}/scripts/_state.py`. Read it before
the first write, including its `ANSWER_KEYS` map: most answers take any key you
like, but the gates read some by exact name, and a synonym there does not make a
gate wrong — it makes it blind. `check_completeness.py` refuses a domain marked
`complete` whose required keys are missing, and names what you called them instead. Domain status is one of `not-started`, `partial`, `complete`,
`not-applicable` — and `not-applicable` is a real answer, used when an earlier choice
ruled the domain out. A serverless application has no node strategy, and inventing
one would be worse than recording why there is none.

Nothing sensitive goes in it: it gets committed, so an account identifier or an
endpoint written there is published. Reference configuration, never embed it.
`scan_secrets.py` enforces this and blocks the commit.

Report detections the same way. Cite the file that holds a value, not the value:
"the account id in `root.hcl`", not the twelve digits. This keeps the identifier out
of transcripts and summaries too.

### 2. Write nothing you were not told

An empty section is better than a plausible one. The whole value of these documents
is that a reader can trust every line was actually discussed.

### 3. Never invent a number, never assert compliance

On cost: derive a range from stated assumptions, show the arithmetic, or ask. Mark
anything nobody can price yet `"unpriced": true` with a note — labelled, not guessed.
`check_cost.py` rejects a price with no assumptions. Reasoning and the two cost
models: `references/cost-method.md`.

On compliance: map obligation → proposed control → evidence required, and record
that verification belongs to a named owner and, where required, an auditor. Never
write that something *is* compliant; you are advising, not certifying. Whether a
regime applies is a question about the client's regulatory status, not their sector
— ask, and record the answer.

**A regime this build cannot map is recorded, not dropped.** Three regimes in the
control map are stubs whose primary text was never read, and a client can name one
that has no control file here at all. Either way: put it in
`03-compliance.answers.regimes_unmapped`, raise an open question with an owner and a
date, say plainly that this skill cannot produce a control mapping for it, and
continue. The compliance gate reports those on every run and does not block on them.
Putting one in `regimes` instead fails the gate with no waiver path, and the only
way out of that is deleting a real obligation from the record to get a green run.

### 4. Never block

An unknown becomes an entry in `open-questions.md` with a proposed default, a named
owner and a date by which the default takes effect. Then carry on. An interview that
stalls on question four produces nothing.

The owner and the date are not decoration: without both, the unknown has left the
conversation rather than been parked, and `check_completeness.py` refuses the run.
Mid-interview `--draft` still reports it without blocking, because that is exactly
when the owner is not yet known.

This keeps the interview moving; it does not make the specification final. A blocking
domain whose answer is still an open question is unanswered, and
`check_completeness.py` says so.

### 5. One domain at a time, three to five questions per turn

The person answering is often not technical. A forty-question dump yields six bad
answers and a lost afternoon. Finish a domain, write state, move on.

A reference file listing seven questions is not permission to ask seven: split it
across two turns. The limit is the point of the rule.

Give every enumerable question options, a recommended default and a one-line
trade-off, so it can be answered without translation. "Don't know yet" and "other"
are always available, and choosing them is a normal outcome.

Pre-fill anything the repository can tell you, and **always label it as an
inference**: "I can see this is a Terragrunt repo on AWS in ap-south-1 — is that
right for the new service too?" A pre-fill presented as fact is how the wrong tool
reaches a signed-off specification.

### 6. Secure by default, and a deviation is a recorded waiver

Private subnets, least privilege, encryption in transit and at rest, no publicly
reachable data stores, no long-lived static credentials. Start here and do not
justify it.

A departure needs a waiver in the state file naming the control, the deviation, the
reason and who accepted it. Some deviations are correct — record them, do not argue
them. `references/secure-defaults.md` has the reasoning per default, for cases these
rules did not anticipate.

Recording the waiver is yours, not the gate's. `check_contradictions.py` matches the
words a control uses, not their sense — it cannot tell "no public data stores" from
"the database is public" — so it warns and leaves the judgement to you. A deviation
you do not record is a deviation nothing downstream will catch.

### 7. Run the gates before emitting, never after

```
${CLAUDE_SKILL_DIR}/scripts/run_gates.py --state <state> --artifacts <dir>
```

Add `--draft` mid-interview to see what remains without being blocked. Invoke it as
its own command; never chain it behind `&&`, because a Bash permission rule does not
extend across shell operators and the chained form will prompt.

Without `--draft` the completeness gate also reads the output directory: the three
documents exist, and the specification carries its three Mermaid diagrams. Every
domain can be answered and every other gate green while nothing has been written, so
the state file alone is not evidence that a specification exists.

If a gate fails, fix the cause or record a waiver. Never emit and mention it
afterwards: a problem found now costs a question, and the same problem found after
sign-off costs a redesign.

### 8. Where to read next

Load a reference only when its domain is in play. Reading all of them at once spends
the attention the current domain needs.

| When | Read |
|---|---|
| First turn of any domain | `references/domain-NN*.md` — note domain 9 matches two files, delivery and IaC/policy; read both |
| A regime is named | `references/compliance/<regime>.md` |
| Unsure how to run a turn | `references/interview-method.md` |
| That is still not concrete enough | `references/interview-examples.md` — one transcript, not all three |
| Any cost figure | `references/cost-method.md` |
| A deviation is proposed | `references/secure-defaults.md` |
| Writing an artifact | `assets/*.template.md` |

## Starting a new interview

1. Run `${CLAUDE_SKILL_DIR}/scripts/preflight.py`. It reports missing tools, and
   `gitleaks` genuinely matters: without it the secret scan fails closed and you
   cannot finish.
2. Agree the project slug and the output directory. Default is
   `${CLAUDE_PROJECT_DIR}/docs/architecture/<project-slug>/`, and if the repository
   keeps planning documents somewhere else, follow the repository.
3. Run `${CLAUDE_SKILL_DIR}/scripts/detect_conventions.py --repo ${CLAUDE_PROJECT_DIR}`
   if there is a repository. Present what it found as inferences to confirm, and
   note what it says is missing — an absent backup tool or log pipeline is a
   question, not an omission from the report.
4. Create the branch. Artifacts are reviewed in a pull request, not in chat
   scrollback, so the PM and the team comment on diffs. Where the repository has no
   remote — a fresh demo, a spike, an offline machine — commit to the branch, say
   plainly that no remote is configured and nothing was pushed, and give the command
   for once there is one: `git push -u origin <branch>`. Do not add a remote on the
   user's behalf.
5. Start at domain 1. Read its reference file first.

Ask about the output directory and the branch name; do not decide them silently.

## Domain order, and what gates what

Order is not arbitrary: each domain's answers narrow the next. Product context comes
first because everything else hangs off what the thing is and what an outage costs.

| # | Domain | Blocks a final spec |
|---|---|---|
| 1 | Product context | yes |
| 2 | Application shape | no |
| 3 | Compliance and data governance | yes |
| 4 | Cloud and region | yes |
| 5 | Environment topology | no |
| 6 | Compute platform | yes |
| 7 | Networking and ingress | no |
| 8 | Identity and secrets | no |
| 9 | Delivery — two reference files, read both | no |
| 10 | Observability | no |
| 11 | Security posture | no |
| 12 | Data, backup and DR | yes |
| 13 | Cost | yes |
| 14 | Team and operations | yes |

A domain blocks when a default would be a guess about the *business*. The other seven
have defensible technical defaults, recorded in the specification as defaults rather
than as decisions, so a reviewer can see they were never chosen.

The full gating graph is in each domain's reference file. The edges that change the
interview most:

- **Serverless or FaaS** closes the node-strategy and ingress-controller branches
  entirely, and opens cold-start tolerance, concurrency limits and per-invocation
  cost.
- **PCI-DSS** opens cardholder-data-environment segmentation in 7, key custody in 8,
  twelve-month log retention in 10, penetration-test cadence in 11, change control
  in 9.
- **GDPR or India DPDP** opens residency, retention and erasure in 12, and
  data-subject access in 8.
- **RBI, SEBI or IFSCA** opens incident-reporting deadlines, third-party review, and
  DR drill cadence — and the entity's regulatory classification has to be
  established before any control list means anything.
- **A team of two, or nobody on the pager**, pushes every choice in 6, 8, 9 and 10
  toward managed. A self-hosted control plane here is a contradiction, not a
  preference, and `check_contradictions.py` treats it as one.
- **On-premises or bare metal** changes most domains rather than one: isolation
  becomes physical, there is no spot market and no managed node group, SPIFFE and
  SPIRE replace IRSA, internal PKI stops being optional because there is no ACM,
  storage becomes a first-class decision, and cost inverts to capital expenditure
  with amortisation.

After each significant choice, drill down one level. Managed Kubernetes leads to node
strategy, spot proportion, upgrade cadence and who performs it, and the multi-tenancy
model. Self-hosted leads to who patches the control plane, what the etcd backup and
restore story is, and who rotates certificates.

## Resuming

1. Read `discovery-state.json`.
2. Say what is already answered, in one short paragraph. Do not re-ask it.
3. Run `${CLAUDE_SKILL_DIR}/scripts/run_gates.py --state <state> --draft` to
   see what remains.
4. Continue from the first domain that is not `complete` or `not-applicable`.

Never restart a completed domain. Re-asking answered questions is the fastest way to
lose the room.

## Revising after review

A revision is not a new interview.

1. Update the affected domains in the state file, and nothing else.
2. Check what the change invalidates. A budget cut can contradict the DR tier; a new
   environment can contradict the isolation model. `check_contradictions.py` finds
   these, so run it before rewriting anything.
3. Update only the artifacts the change touches.
4. Re-run the gates.
5. Report what moved and why, and push to the same branch so the review continues in
   one place.

## Artifacts

All under the agreed output directory. Templates are in `assets/`.

| File | What it is |
|---|---|
| `architecture-spec.md` | Decisions with rationale, alternatives rejected and why, non-functional requirements, a per-environment topology table, and security controls mapped to each named compliance obligation |
| `README.md` | For the PM, in plain language: what is being built, what it costs, what is needed from them, what is still open, and what that means for the timeline |
| `decisions/ADR-NNN-*.md` | One short ADR per significant choice. How many a project needs is your judgement, but each one recorded in the state file carries a title, a rationale and at least one rejected alternative with its reason — the gate refuses a decision with the reasoning stripped out |
| `open-questions.md` | Every TBD with an owner and the default that applies if it is unanswered by a stated date |
| `discovery-state.json` | The machine-readable record, so a revision does not restart the interview |

## Handing over to generation

Once the specification is approved and its gates pass, the infrastructure it scoped
gets written as Terraform by `/architecture-discovery:iac`, which reads this
interview's `discovery-state.json` and generates only what the interview decided.

Say so when the specification is delivered, and do not start generating here: this
skill scopes, and a specification still under review is not a thing to implement.

Diagrams are Mermaid, embedded in the specification so they diff in git and render in
the pull request. Three are required: network topology, delivery flow, and
environment promotion. If the `arch-diagram` skill is available, use it — it holds
the diagram conventions, and duplicating them here would let the two drift. If it is
not available, write the Mermaid directly: `graph TD` for network topology,
`flowchart LR` for delivery, `stateDiagram-v2` for promotion.


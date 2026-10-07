# Limitations

What this plugin's two skills cannot do, could not be verified, or do in a way you
should know about before relying on them. Each entry states what the limit is and what it means
for you.

Nothing here is a placeholder for unfinished work. These are the standing limits.

| Group | Limits | What they are about |
|---|---|---|
| [Compliance](#compliance) | L1–L3 | Three regimes with no control list, and why every mapping is advisory |
| [Cost](#cost) | L4 | Estimates are arithmetic over stated assumptions, never quotes |
| [Installation and permissions](#installation-and-permissions) | L5–L7 | Personal scope, what a teammate does not get, and one thing never observed working |
| [Accuracy of what it detects](#accuracy-of-what-it-detects-and-recommends) | L8–L9 | Convention detection was validated against two repositories; the tool landscape is a snapshot |
| [Tooling around the skill](#tooling-around-the-skill) | L10–L11 | What `claude plugin validate` does not check |
| [Generation](#terragrunt-and-terraform-generation) | L12–L19 | The network dependency, what provenance proves, that nothing has been planned, and what the gates cannot parse |
| [Guardrails](#guardrails) | L20–L22 | What the hook and the secure-defaults gate do **not** cover |

The last group is the one to read before trusting a green run.

---

## Compliance

### L1. Three regimes have no control list, and the gate refuses rather than passing

`https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html`
and `https://www.iso.org/standard/27001` both returned **HTTP 403** to a scripted
request — bot protection, not dead links. The AICPA SOC 2 Trust Services Criteria
was not fetched at all.

So **HIPAA, ISO/IEC 27001 and SOC 2 are stubs**: `sourced: false` in
`compliance_controls.json`, with no obligations behind them. Naming one of those
regimes makes `check_compliance.py` **fail**, deliberately. An empty control list
would otherwise render as "0 obligations unaddressed", which reads exactly like a
clean bill of health — the most dangerous output this skill could produce.

Consequence: for those three, the reference material has to be written from the
primary text before the gate can report on them. GDPR, India DPDP, PCI-DSS, RBI,
SEBI and IFSCA are sourced.

### L2. Control mappings are advisory, and that is structural

The skill maps obligation → proposed control → evidence required, and marks
verification as the owner's responsibility. **No mapping produced by this skill has
been reviewed by a qualified auditor or by counsel, for any regime.**

This is not a gap to close later; it is what the skill is. Treat every mapping as a
starting point for an assessment, never as evidence of compliance. The skill will
never write that something *is* compliant, and neither should the spec it emits.

### L3. Regulator material is jurisdiction- and entity-class-specific

The SEBI CSCRF applies different requirements by entity classification (MIIs,
Qualified REs, mid-size, small-size, self-certification). The RBI Master Direction
RBI/2023-24/107 is addressed to a named list of entity types — scheduled commercial
banks excluding RRBs, small finance banks, payments banks, NBFCs, credit information
companies and All India Financial Institutions.

Whether either applies to a given project depends on the client's **regulatory
status**, which the skill cannot determine and must not infer from the sector.

Consequence: the skill asks which regime applies and records the answer. Where the
answer is unknown it becomes an entry in `open-questions.md` with a named owner —
never a guess.

## Cost

### L4. Estimates are arithmetic over stated assumptions, never quotes

No price is invented; estimates show their assumptions and their arithmetic. But
list prices move, regional pricing differs, and negotiated, committed-use and
Savings Plan rates are invisible to this skill. **AWS pricing is not read from an
API at runtime.**

Consequence: every figure is a planning range, not a quote. The cost gate compares
an estimate to a stated ceiling; it does **not** validate the estimate against
actual cloud pricing. Verify against <https://calculator.aws/> before anyone commits
budget.

## Installation and permissions

### L5. Teammates do not get this from a `git clone`

Project skills in a repo's `.claude/skills/` arrive with a clone. This is a
**personal-scope skills-directory plugin**: it loads globally for whoever installs
it, and does not travel with the repository.

Consequence: what the repo gives is one reviewable source of truth with version
history and code review. Distribution is a separate, explicit step — each teammate
symlinks or clones into their own `~/.claude/skills/`, or installs from a
marketplace if one is later published.

### L6. Personal scope makes the `allowed-tools` grant broader in reach

At personal scope the grant applies in **every repository you open**, not just this
one. Workspace trust does not gate it:

> Workspace trust never gates a skill's `allowed-tools` in any session

(<https://code.claude.com/docs/en/permissions>). Personal-scope skills-directory
plugins are also exempt from the trust restrictions that constrain project-scope
ones (<https://code.claude.com/docs/en/plugins-reference>).

Consequence: this is why the grant is three exact script-path rules and nothing
else. The skill adds nothing to your session's normal permissions beyond running its
own three bundled entry points. Read any addition to that list as a change to what
this skill can do everywhere on your machine.

### L7. Prompt suppression by `allowed-tools` was never observed working

That the grant is *minimal* is verifiable by reading it. That it *suppresses
prompts* was not confirmed, after three attempts:

1. **Auto mode** permitted an ungranted script too, so nothing about the grant was
   being tested.
2. **Manual mode (`--permission-mode default`)** produced no tool calls at all, for
   granted and ungranted scripts alike — so it cannot discriminate.
3. **Manual mode with `--allowedTools Skill` only**: same result, both directions.

The likely explanation is that a non-interactive `-p` run has nobody to answer a
prompt, so a call needing approval is never attempted — making "was it prompted?"
unobservable in exactly the mode that would be ideal for testing it.

Consequence: the claim rests on documented matcher behaviour (everything before the
first wildcard matches as written; a trailing ` *` makes an absolute script path a
prefix rule) rather than on an observation. Worth confirming in one interactive
session in manual mode — a two-minute check.

## Accuracy of what it detects and recommends

### L8. Convention detection was validated against two repositories, not many

`detect_conventions.py` was designed by reading two real layouts: one with a single
`root.hcl`, `env/<env>/` units and `modules/<name>/`, and one built around
`charts/{argocd,ingress,observability}`. Two layouts is enough to prove detection
must be a script rather than a fixed assumption, and **not enough to claim broad
coverage**.

Consequence: on an unfamiliar layout it degrades to asking rather than guessing, and
the skill names the convention it inferred so a wrong inference is visible and
correctable rather than silent. Always check the pre-fills it presents.

### L9. The tool landscape is a dated snapshot

The option matrices characterise roughly 150 tools by licence and maturity. Every
one of those is point-in-time. OpenTofu exists because Terraform's licence changed;
Promtail was deprecated by its own maintainer; VMware's pricing changed hands. A
recommendation made from a stale landscape is confidently wrong, which is worse than
being uncertain.

Consequence: where a licence or a deprecation is load-bearing in a recommendation,
verify it at the time of the recommendation rather than trusting the file. The
reference files carry the date they were written.

## Tooling around the skill

### L10. `claude plugin validate` does not parse `SKILL.md`

The command validates only the plugin manifest. Run against the plugin root it
prints "Validating plugin manifest: .claude-plugin/plugin.json" and says nothing
about the skill; run against `skills/discover/` it fails with "No manifest found in
directory". `--strict` does not change this, and `claude plugin details` has no
`--plugin-dir` option, so it cannot inspect an uninstalled plugin either.

Consequence: a green `claude plugin validate` says nothing about whether the
frontmatter is correct. The real proof is loading the plugin —
`claude --plugin-dir . -p` and confirming `/architecture-discovery:discover` appears
— which fails if the frontmatter does not parse.

### L11. Trigger matching reads `description`, not `when_to_use`

Tooling that scores skill triggering reads only `description`. That matters here
because **every anti-trigger instruction this skill has** — the list of things it
must stay out of — lives in `when_to_use`.

Claude Code itself appends `when_to_use` to `description` in the skill listing, so
real triggering does see both. But any harness measuring `description` alone is
measuring text with none of this skill's guardrails in it, and will report a
false-positive rate for something nobody runs.

Consequence: when measuring trigger accuracy, score the concatenation of
`description` and `when_to_use` — 1,236 characters — not `description` alone.

---

## Terragrunt and Terraform generation

### L12. Version resolution needs the network, and there is no fallback

`resolve_versions.py` is the only script in this repository that makes a network
call. It reads the public Terraform registry and, for OpenTofu, the GitHub releases
API. With neither reachable it exits 3 and resolves nothing.

There is deliberately **no bundled version table** to fall back to. A table compiled
at build time is wrong within weeks, and a stale pin that reads as deliberate is the
exact failure the script exists to prevent — the same reasoning that keeps a price
table out of the cost gate.

Consequence: generation on a machine with no network access cannot pin versions from
this plugin. Ask for the versions, record where they came from, and write those. Do
not let the model supply them from memory: its idea of the latest provider is its
training cut-off's idea, and it is wrong in the direction that reviews clean.

### L13. The provenance check verifies the line exists, not that it is true

`check_iac.py` requires a `# spec:` header in the first twelve lines of every
`.tf` file. It cannot know whether the ADR the header names actually says what the
resource does, and a header citing ADR-007 for a resource ADR-007 never discussed
passes.

This is a regex over text, not a claim about meaning — the same limit the
contradiction gate has in the discovery skill, for the same reason.

Consequence: the header makes an untraceable file visible, which is worth the one
line it costs. It does not make traceability automatic. A reviewer still has to
check that the resources match the specification, and the specification is what wins
when they disagree.

### L14. No generated stack has been planned against a real account

The gate checks the tree is pinned, traceable, canonically formatted, valid and free
of identifiers. `terraform validate` proves the configuration is internally coherent.
None of that proves the resources will apply: quotas, service control policies,
organisation restrictions, region availability of a specific managed service, and
whatever already exists in the account are all invisible to it.

The skill also never runs `apply`, `destroy`, `import` or any state command — by
rule, and since this version by enforcement: a `PreToolUse` hook denies those verbs
inside any stack carrying `.architecture-discovery.json`. See L20 for what that hook
does not cover.

Consequence: the first `terraform plan` against a real account is a review step, not
a formality, and it belongs to whoever accepts the consequence of applying it. Read
the plan — particularly the counts, where a specification costed one of something and
the tree creates three per availability zone.

### L15. The resource mapping covers three providers, and the interview records more

`references/providers.md` maps domain answers to resources for AWS, Azure and GCP.
Those tables are common shapes, not a catalogue, and they are a starting point rather
than permission to write a row.

Nothing is shipped for on premises or bare metal, which domain 4 can legitimately
record. That is not an oversight: the provider underneath could be vSphere, Proxmox,
OpenStack, MAAS or nothing declarative at all, and a plausible mapping written from
the nearest cloud analogue is exactly the invented resource the skill's first rule
exists to prevent.

Consequence: on an unmapped provider, or for a service not in the tables, read the
provider documentation. Where no declarative provider exists, recording that
Terraform does not cover that layer is a better answer than a module that half does.

### L16. A failed `terraform init` is classified by its message, not by its cause

`init` reaches the network, so an unreachable registry and a genuinely wrong provider
`source` exit the same way. `check_iac.py` matches the output against a list of
known connectivity phrases: a match is reported as "could not run", and everything
else is a failure.

It fails closed on a message it does not recognise, which is the safe direction — a
tree that will not initialise is not ready for review whatever the reason — but a
connectivity failure phrased in a way the list does not cover will be reported as a
validation failure.

Consequence: read the output the gate prints rather than only its verdict, and use
`--skip validate` where the cause is genuinely the network. The skip is printed in
the summary, because a gate skipped silently is worse than one that failed loudly.

### L17. Only four conventions are gated, and the rest are prose

`references/conventions.md` describes the conventions a Terraform reviewer expects.
Four are machine-checked — every `variable` typed and described, every `output`
described, no `provider` block in a called module. Everything else in that file —
`for_each` over `count`, one naming local rather than repeated interpolation, `moved`
blocks when renaming, thin units with logic in modules, no `null_resource` with
`local-exec` — is judgement about the code, and nothing verifies it.

That split is deliberate rather than a gap to close. Four rules that are always right
are worth more than twenty that are usually right: a gate producing findings nobody
can act on is a gate people learn to skip, and once it is being skipped the four that
did matter go with it.

Consequence: the conventions gate passing means four specific things are true, not
that the code is idiomatic. Read the diff.

### L18. `terragrunt hcl validate` is not a plan, and does not resolve dependencies

It parses and evaluates the unit configurations: that the `include` resolves, the
`terraform.source` is readable, the HCL is well-formed and the functions evaluate. It
does **not** resolve `dependency` outputs, so a `config_path` pointing at a unit whose
outputs do not contain what the input expects passes.

`--inputs` cross-checks each unit's inputs against its module's variables, and is left
out of the gate because it needs the modules initialised — the same reason `plan` is
left out.

Consequence: a stack that passes has units that parse and wire up. Whether the values
flowing between them are the right ones is what the first `terragrunt run --all plan`
tells you, and that belongs to whoever accepts the consequence of applying it.

### L19. The Terragrunt CLI rename is handled by version dispatch, not by capability

`terragrunt hclfmt` and `hclvalidate` became `terragrunt hcl fmt` and `hcl validate`
in 0.78. `check_iac.py` reads `terragrunt --version` and calls whichever
spelling that release understands.

If a future release renames them again, or if a build reports a version string the
regex does not match, the gate will call a subcommand that does not exist and report
that as a formatting or validation failure rather than as a tooling mismatch.

Consequence: read the gate's printed output when a Terragrunt half fails
unexpectedly, and check the installed version against `.terragrunt-version`. The
version pin exists partly for this.

---

## Guardrails

Read these before treating a passing run as a clean bill of health.
[`docs/GUARDRAILS.md`](docs/GUARDRAILS.md) is the design; these are its edges.

### L20. The guardrail hook is scoped to a marker file, and scope means gaps

`hooks/block_mutating_iac.py` denies `apply`, `destroy`, `import`, `taint`,
`force-unlock` and the mutating `state` and `workspace` subcommands — for Terraform,
OpenTofu and Terragrunt alike — but **only** inside a directory tree carrying
`.architecture-discovery.json`.

That scope is deliberate: a hook denying `terraform apply` everywhere would break
ordinary infrastructure work in unrelated repositories and would be uninstalled
within a day. It also means the following are not covered, and none of them is a bug:

- A stack whose marker has been deleted. That is the handover working as intended: a
  person read the plan and took ownership.
- A copy of the generated code moved outside the marked tree.
- Anything run outside a Claude Code `Bash` tool call — a terminal the agent is not
  driving, a CI job, a teammate's laptop. Hooks see tool calls, not the machine.
- A verb spelled in a way token matching does not recognise: a shell alias, a
  wrapper script, a command built from a variable.

The hook also **fails open by design**. Malformed input or any internal error means
exit 0 and silence, because a guardrail that breaks the session when it malfunctions
gets disabled and takes the real protection with it.

Consequence: treat it as a well-placed tripwire on the specific failure it was built
for — an unreviewed generated stack being applied from this session — not as a
control that makes applying impossible. The thing that actually protects production
is a person reading the plan.

### L21. The guardrails gate is thirteen patterns, not a security review

`check_iac.py`'s `guardrails` gate checks thirteen things that are always wrong.
Eight fire on something present: an admin port open to `0.0.0.0/0`, a publicly
reachable data store, encryption explicitly disabled, a wildcard IAM policy, a static
credential in the configuration, an unrestricted `mock_outputs`, key rotation
disabled, and a secret-shaped variable with a literal default. Five fire on something
absent: a VPC with no flow log, an unmanaged default security group, a public load
balancer with no access logs, a KMS key with no policy, and an unencrypted log group.

They are patterns over comment-stripped HCL, chosen on the bar that a public load
balancer on `0.0.0.0/0:443` must not be a finding. That bar is why the list is short:
a guardrail that cries wolf is one people switch off, and the thirteen that matter go
with it.

What it does not do: reason about reachability, follow a value through a module
boundary, know which of your resources hold regulated data, or replace Checkov,
tfsec, Trivy or Terrascan. Where domain 9a named one of those the gate runs it, and
reports "did not run" when the specification named a scanner the machine does not
have, or named one outside those four — the gate drives no others, and reporting
nothing made that case read exactly like a scan that found nothing. Nothing is
installed by this plugin.

Consequence: a passing `guardrails` gate means thirteen specific things are not wrong.
It is a floor under the secure defaults, not evidence that the stack is secure, and
it is certainly not the policy review L2 already says no mapping here has had.

### L22. Waiver matching is literal, and the check id is a compatibility surface

A guardrail finding is waived when its check id — `public-admin-ingress`,
`unencrypted-storage` and so on — appears verbatim in the `control`, `deviation` or
`reason` text of a waiver in `discovery-state.json`.

Literal matching is deliberate: `check_contradictions.py` matches words rather than
sense and says so, and a looser match here would quietly waive deviations nobody
agreed to. But it means a waiver that describes the right control in different words
does not waive anything, and the gate will refuse a deviation the interview genuinely
accepted.

It also makes the ids a compatibility surface. Renaming one silently un-waives every
specification that recorded it.

Consequence: every finding prints its id so the string can be copied into the waiver,
and `references/conventions.md` and this file are where the ids are written down. If
the gate refuses something you believe is waived, check the spelling in the waiver
before arguing with the gate.

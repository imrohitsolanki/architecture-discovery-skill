# Guardrails

Two guardrails, and they answer different questions. One constrains what the plugin
is allowed to **do**; the other constrains what it is allowed to **produce**.

| | What it is | What it stops |
|---|---|---|
| [The hook](#the-guardrail-hook-and-why-it-is-scoped-the-way-it-is) | A `PreToolUse` hook on `Bash`, shipped with the plugin | A generated stack being applied, destroyed or state-mutated before a person has taken ownership of it |
| [The gate](#the-guardrails-gate-and-its-relationship-to-waivers) | Gate 5 of `check_iac.py` | A generated stack contradicting a secure default the specification asserts, with no waiver recording the deviation |

Both exist because the alternative was trust. Generation's rule 3 — never apply, never
destroy, never touch a real account — was a sentence in a prompt, and §6 of the
interview asserted secure defaults that nothing checked the generated code actually
implemented. A rule with no check behind it is a hope.

Neither is a wall. [`LIMITATIONS.md`](../LIMITATIONS.md) L20, L21 and L22 state what
each one does not cover, and those limits are the important half of reading this
page: the thing that actually protects production is a person reading a plan.

## The guardrail hook, and why it is scoped the way it is

`hooks/hooks.json` registers a `PreToolUse` hook on `Bash`. It reads the tool call,
and denies `apply`, `destroy`, `import`, `taint`, `force-unlock`, the mutating
`state` and `workspace` subcommands, and their Terragrunt spellings —
`terragrunt apply`, `terragrunt run --all destroy` — when the command targets a
directory this plugin generated.

`plan`, `validate`, `fmt`, `init`, `show` and `output` are deliberately absent from
that list. They are how the stack gets reviewed, and blocking them would block the
review the hook exists to protect.

**The scope is the interesting decision.** A plugin's hooks run in every session
where the plugin is enabled, not only while its skill is active. A hook that denied
`terraform apply` everywhere would break ordinary infrastructure work in unrelated
repositories, and would be uninstalled within a day — taking the real protection with
it. So the scope is exactly what this plugin is responsible for: a stack it wrote,
which by definition nobody has reviewed.

The mechanism is a marker file. Step 1 of generation writes
`.architecture-discovery.json` at the root of the tree; the hook resolves the
command's target directory — allowing for a `cd` prefix, `-chdir=`, `--working-dir`
— and walks up at most twenty levels looking for one.

**The marker is the handover, and deleting it is the act of taking ownership.** A
person reads the plan and removes the file. That is a deliberate one-line action by a
human, which is the correct shape for a decision about applying unreviewed
infrastructure — not a flag the model can pass, and not something the skill deletes
on a user's behalf to get a command through. It is committed rather than ignored, so
a reviewer who clones the branch gets the same protection.

**It fails open, always.** Malformed input, an unexpected shape, any internal error:
exit 0 and say nothing. A guardrail that breaks the session when it malfunctions is a
guardrail people disable, so denying is the exception and silence is the default.
The harness asserts this directly.

Verb matching is on tokens rather than substrings, which is what keeps
`terraform plan -out=apply.tfplan` and `terraform state list` from being caught.


## The guardrails gate, and its relationship to waivers

The hook stops the stack being applied. The `guardrails` gate is the other half:
whether the stack *should* be applied, checked against the secure defaults §6 of the
interview asserts rather than against the document that asserts them.

Thirteen patterns, chosen on the same bar as the conventions gate — always wrong,
never a judgement call. Eight fire on something **present**:

| Check | Secure default it contradicts |
|---|---|
| `public-admin-ingress` | `0.0.0.0/0` to SSH, RDP or a database port |
| `public-data-store` | `publicly_accessible = true`, a public-read ACL, public access block disabled |
| `unencrypted-storage` | encryption explicitly set to `false` |
| `wildcard-iam` | every action on every resource |
| `static-credentials` | a long-lived credential written into the configuration |
| `unrestricted-mock-outputs` | `mock_outputs` with no `mock_outputs_allowed_terraform_commands`, so a placeholder reaches `apply` |
| `key-rotation-disabled` | rotation switched off |
| `secret-in-variable-default` | a secret-shaped variable with a literal default, which is committed |

And five on something **absent**, which is the half a generator actually fails:

| Check | What is missing |
|---|---|
| `vpc-without-flow-logs` | no flow log anywhere in the tree for a VPC or virtual network |
| `vpc-default-sg-unmanaged` | no `aws_default_security_group` taking ownership of the group that allows all traffic and cannot be deleted |
| `public-lb-without-access-logs` | an internet-facing load balancer with no `access_logs` |
| `kms-key-without-policy` | a KMS key with no explicit policy, so access is decided entirely elsewhere |
| `log-group-unencrypted` | a log group with no `kms_key_id` |

The second table exists because every check in the first fires on a bad attribute
being *there*, and a generated stack fails the other way: the required sibling
resource is simply absent, nothing on the page is wrong, and it reviews clean. One
stack passed all eight of the original checks and an external scanner then found
eight real omissions in it — flow logs, access logs, the default security group, key
policies among them.

A public load balancer on `0.0.0.0/0:443` is normal architecture and is deliberately
not a finding, and so is an internal load balancer with no access logs — the harness
pins both cases, because a guardrail that cries wolf is one people switch off and the
thirteen that matter go with it.

**Waivers close the loop between the two stages.** The interview already records a
deviation from a secure default as a waiver naming the control, the deviation, the
reason and who accepted it. Refusing that deviation here a second time would mean a
recorded decision cannot be implemented, so a finding whose check id appears in a
waiver is **reported and not blocked**.

The same mechanism covers the policy scanner: put its own check id — `CKV_AWS_86`,
`AVD-AWS-0053` — in a waiver's `control` field and the gate downgrades that finding
too. Without it a deliberate, owner-accepted deviation lives in the scanner's config
file when the scanner found it and in `discovery-state.json` when the built-in checks
found it, which is two records of one decision. The scanner config then carries only
false positives, which is what a tool-specific file should hold.

Matching is on the id appearing literally in the waiver text, not on meaning:
`check_contradictions.py` matches words rather than sense and says so, and a looser
match here would quietly waive things nobody agreed to. Every finding prints its id
so the string is copy-pasteable into the waiver. The harness pins both directions — a
waiver waives its own control, and does not waive a different one.

Waived findings are still printed, which is why `check_iac.py` now shows the
output of a *passing* gate as well as a failing one. It did not at first, and a
waived deviation vanished from the report entirely — the harness caught that.

Where domain 9a named a policy scanner — Checkov, tfsec, Trivy, Terrascan — the gate
runs it too, and reports "did not run" when the specification named one the machine
does not have, or one outside those four that the gate cannot drive at all. Nothing is
installed by this plugin. An answer that opens with "none" or "not" is read as a
decision rather than as a tool, so choosing no scanner deliberately is reported as
that and not as a missing one.


## What neither of them covers

Stated here rather than only in `LIMITATIONS.md`, because a guardrail whose limits
are documented somewhere else gets trusted past them.

**The hook sees tool calls, not the machine.** Anything run outside a Claude Code
`Bash` call — a terminal the agent is not driving, a CI job, a teammate's laptop — is
not touched. Nor is a stack whose marker has been deleted, which is the handover
working as intended; nor code copied out of the marked tree; nor a verb spelled in a
way token matching does not recognise, such as a shell alias or a wrapper script.

**The gate is thirteen patterns over comment-stripped HCL.** It does not reason about
reachability, follow a value across a module boundary, or know which of your
resources hold regulated data. A passing `guardrails` gate means thirteen specific
things are not wrong. It is a floor under the secure defaults, not evidence that the
stack is secure.

**Waiver matching is literal**, so a waiver describing the right control in different
words waives nothing, and the check ids are a compatibility surface: renaming one
silently un-waives every specification that recorded it.

## Changing them safely

| Change | What else has to move |
|---|---|
| Add a guardrail check | An entry in `GUARDRAILS`, its pattern, a branch in `_guardrail_findings`, and **two** `selftest.py` cases: one that catches it and one near-miss that must not fire. |
| Rename a check id | Every specification that waived it. Prefer not to. |
| Change what the hook blocks | `MUTATING`, `STATE_SUBCOMMANDS` or `WORKSPACE_SUBCOMMANDS` in `hooks/block_mutating_iac.py`, and a `HOOK_CASES` entry. Adding a read-only verb to that list would block the review the hook exists to protect. |

The bar for a new check is the one the existing thirteen were chosen on: **always
wrong, never a judgement call**. A public load balancer on `0.0.0.0/0:443` is normal
architecture, and a guardrail that fires on it is one people switch off — taking the
thirteen that matter with it.

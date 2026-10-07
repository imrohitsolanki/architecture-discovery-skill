# {{Project}} infrastructure

Generated from [`{{path to architecture-spec.md}}`]({{path}}) version {{n}},
{{YYYY-MM-DD}}. Every file names the decision that put it there in a `# spec:` line;
if a resource here does not match the specification, the specification wins and this
is a bug.

> **Nothing here has been planned or applied against a real account.** The generation
> gate checks the tree is pinned, traceable, formatted, valid and free of
> identifiers. It cannot check that the architecture is right, or that these
> resources will apply in your account with your quotas and your service control
> policies. The first plan is a review step, not a formality.

## What is here

| Path | What |
|---|---|
| `root.hcl` | Backend and provider, generated once for every unit. |
| `live/{{prod}}/` | {{prod}}: one unit per component, one state file each. |
| `modules/{{name}}/` | {{what it creates, in one line}} |

## Before you can run anything

| | |
|---|---|
| {{Terraform}} | `{{~> 1.16}}`, pinned in `.terraform-version` — `tfenv install` or `mise install` reads it |
| Terragrunt | `{{1.1.1}}`, pinned in `.terragrunt-version` |
| Credentials | {{how: an SSO profile, an OIDC role in CI. Not an access key}} |
| State bucket | `{{derived name}}`, in {{account/subscription}}. Create it before the first run; {{who owns it}} |

Variables with no default are unsettled questions, not omissions. Each names its
open question in its `description`, and supplying a value is a decision somebody has
to make:

| Variable | Open question | Owner | Default applies from |
|---|---|---|---|
| {{name}} | {{OQ-n}} | {{who}} | {{date}} |

## Before you can apply

`.architecture-discovery.json` is still in this directory, which means nobody has
taken ownership of this stack yet. While it is there, the architecture-discovery
plugin blocks `apply`, `destroy`, `import` and state-mutating commands in this tree.
`plan`, `validate`, `fmt` and `init` are not blocked — they are how the review
happens.

Read the plan. Then delete the file. That deletion is the record that a person read
what this does and accepts it.

## Running a plan

```
cd live/{{prod}}
terragrunt run --all plan          # the whole environment, in dependency order
```

```
cd live/{{prod}}/{{component}}
terragrunt plan                     # one unit
```

Read the plan before applying it. Pay attention to anything being destroyed or
replaced, and to counts — a plan creating three NAT gateways where the specification
costed one is a discrepancy worth finding before it is billed.

Apply is deliberately not documented here as a copy-paste command. Whoever applies
this accepts what it does.

## State

Held in {{where}}, versioned and encrypted, locked natively.

**Read access to state is production read access.** It contains resource attributes
in plain form — generated passwords, connection strings, private keys — whatever the
configuration marked sensitive. The access list is {{who}}.

## Checking the tree

```
{{path to plugin}}/skills/iac/scripts/check_iac.py \
  --state {{path}}/discovery-state.json \
  --tf-dir . \
  --artifacts {{path to the architecture directory}}
```

Eight gates: the specification's own five, then pins, provenance, conventions,
guardrails, formatting and validation — `terraform fmt` and `validate` over the
modules, `terragrunt hcl fmt` and `hcl validate` over the units — and a secret scan.
Run it after every file, not once before the commit.

## What is deliberately not here

{{The domains the specification recorded as not-applicable, and the open questions
that have not resolved into resources yet. An empty section is better than a
plausible one; this list is what stops the next reader assuming an omission was an
oversight.}}

## Changing this

The specification is upstream. A change to the infrastructure starts with a change to
the specification, which is what keeps the `# spec:` headers true — and what stops
this tree and the document that justified it drifting apart until neither can be
trusted.

Version pins, for either tool, are raised in their own commit, never inside an architecture change.
See `references/versions.md` in the plugin for the upgrade sequence.

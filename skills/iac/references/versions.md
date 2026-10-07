# Versions and pinning

Read this before writing `versions.tf`, and again before raising any pin.

## Resolve, never recall

```
${CLAUDE_SKILL_DIR}/scripts/resolve_versions.py \
  --terragrunt \
  --provider aws --provider kubernetes --provider helm \
  --module terraform-aws-modules/vpc/aws \
  --hcl
```

Output is a table and, with `--hcl`, a `terraform {}` block ready to paste.

`--tool opentofu` where the specification chose OpenTofu. `--provider` takes a short
name the script knows or an explicit `namespace/name` — `Azure/azapi`,
`integrations/github`. `--module` takes `namespace/name/provider`.

**Exit 3 means the registry could not be reached and nothing was resolved.** There is
no bundled version table, deliberately: one compiled at build time is wrong within
weeks, and a stale pin that reads as deliberate is the failure the script exists to
prevent. Ask whoever is running this for the versions, record where they got them,
and write those.

**Exit 1 means a name does not exist.** Nothing is substituted for it. Check the
spelling on the registry.

## The pinning rules, and why each is what it is

| What | Shape | Why |
|---|---|---|
| `required_version` | `~> 1.16` | Terraform's own patch releases are bug fixes. Pinning the patch forces every engineer and every CI image to move in lockstep for no benefit. The minor is pinned because state file format changes with it. |
| Provider `version` | `6.64.0` | Exact. A provider patch can change a resource schema, and a range re-resolves on every `init` without a lock file — so three people can be on three builds while the repository says one thing. |
| Registry module `version` | `6.7.2` | Exact, same reason. A module minor bump can add a resource to your plan. |
| Git module `source` | `?ref=v1.4.0` or a full SHA | Without a ref it tracks the default branch, so the module changes under an unchanged commit of this repository. |
| Tool version | `.terraform-version` | `required_version` tells someone they have the wrong binary *after* they run it. A file tfenv, asdf or mise reads means they never did. |
| Terragrunt version | `.terragrunt-version` | A second tool with its own cadence and its own breaking changes — the HCL commands were renamed in 0.78, so `terragrunt hcl fmt` on one machine is `terragrunt hclfmt` on another. Unpinned, the stack behaves differently per machine while every version in the repository says otherwise. |

`check_iac.py` enforces every row, including the Terragrunt line: a stack with
units and no `.terragrunt-version` fails the `pins` gate. `.tool-versions` or
`.mise.toml` covering both tools satisfies it too.

A Terragrunt unit's `terraform.source` is the sixth pin. A local path needs no ref —
the repository is the version — but a remote source without `?ref=` tracks a default
branch, so an unchanged commit of this repository applies different infrastructure
next week.

## The lock file

`.terraform.lock.hcl` is written by `terraform init` and **is committed**. It records
the exact provider builds and their checksums, which is what turns an exact
`required_providers` version into a reproducible one — the version says which release,
the lock file says which artifact, verified.

It does not exist at generation time, because nothing has been initialised. The gate
notes its absence rather than failing. Whoever runs the first `init` commits it.

For a team on more than one platform, generate for all of them or the lock file
fights CI:

```
terraform providers lock \
  -platform=darwin_arm64 -platform=linux_amd64 -platform=linux_arm64
```

## Raising a Terragrunt pin

Terragrunt's own upgrades are the ones most likely to surprise, because they change
the commands rather than the infrastructure. The 0.78 reorganisation renamed
`hclfmt` to `hcl fmt` and `hclvalidate` to `hcl validate`, which breaks every CI
pipeline that called the old names on the day the pin moves.

`check_iac.py` dispatches on the reported version and calls whichever spelling
that release understands, so the gate keeps working across the boundary. Your
pipeline probably does not. Read the release notes, not just the diff.

## Raising a pin

Deliberately, in its own commit, never bundled into an architecture change — a
version bump hidden inside a feature diff is two reviews in one and gets one.

1. Re-run `resolve_versions.py` to see what is current.
2. Read the provider changelog between the pinned version and the target. Major
   versions of the AWS provider have removed arguments and changed defaults; the
   changelog is where that is stated, and the plan is where it is discovered
   otherwise.
3. Bump `versions.tf`, run `terraform init -upgrade`, commit the changed lock file.
4. `terraform plan` in the lowest environment first. A provider upgrade that plans
   clean in dev can still surface a diff in production where a resource has drift.

## What "latest" means, and its one caveat

`resolve_versions.py` returns what the registry publishes as current at the moment it
runs. That is the right default for a system that does not exist yet: there is no
installed base to be compatible with, and starting a major version behind buys
nothing.

The caveat is that the newest provider is newest. Where the specification names a
managed service that is itself new, or a module the team already runs elsewhere on an
older pin, say so and let them choose — and record the choice in the tree's README,
because an unexplained older pin looks like neglect to the next reader.

# Layout, state and environments

Read this when deciding the directory shape, before the first file.

## The stack

Terragrunt composes, Terraform implements. Two layers with one job each:

```
infra/
  .terraform-version          pinned, read by tfenv/asdf/mise
  .terragrunt-version         pinned, because Terragrunt has its own breaking changes
  .gitignore                  .terraform/, .terragrunt-cache/, *.tfstate*
  README.md                   what this stack is, what a reviewer must supply
  root.hcl                    backend and provider generated once, for every unit
  modules/                    Terraform. The only .tf in the repository.
    network/
      versions.tf variables.tf main.tf outputs.tf
    data/
    compute/
  live/
    prod/
      env.hcl                 this environment's values
      network/terragrunt.hcl  a unit: which module, which inputs, what it depends on
      data/terragrunt.hcl
      compute/terragrunt.hcl
    staging/
      env.hcl
      network/terragrunt.hcl
      ...
```

**Modules hold no environment knowledge.** A module takes inputs and creates
resources. It does not know which environment called it, and it never declares a
backend or configures a provider — `root.hcl` generates both for every unit, once.

**Units hold no logic.** An `include`, a `terraform` block naming its module,
`dependency` blocks, and `inputs`. A unit that computes things is a module in the
wrong place, where it cannot be reused or tested.

**Environments differ in values, not in code.** Every `live/*/` calls the same
modules with different inputs. A staging stack that has drifted from production's is
how a change tested in one fails in the other, and it drifts by one small justified
edit at a time.

Where the specification's topology table says an environment differs in shape — no
read replica in dev, one availability zone instead of three — that is an input
driving `for_each` or a `count` ternary, and the table says which. Never infer a
difference the table does not state.

### Why this and not plain Terraform root modules

One `root.hcl` instead of a `backend.tf` and a `providers.tf` copied into every
environment directory, which is where those copies drift. Dependency ordering
between units, so `terragrunt run --all plan` walks the graph rather than a person
remembering that network comes before compute. And one state file per unit, so a
change to one component locks one component.

The cost is a second tool, a second version to pin, and a second set of concepts for
a new engineer. Below roughly three units it does not pay for itself. Where domain 9
recorded plain Terraform, follow the specification: root modules per environment,
`backend.tf` with partial configuration, and everything else in this file still
applies.

## Apply order, and who owns what

One order, stated once, because everything else in this file assumes it:

```
registry -> network -> data -> identity -> compute -> observability
```

Identity comes **before** compute, not after. The tempting reasoning is that roles
are granted "once there is something to grant access to", and that holds for EKS
with IRSA, where the role trusts a service account that has to exist first. It is
backwards for almost everything else: an ECS task definition takes
`execution_role_arn` and `task_role_arn` as inputs, a Lambda takes a role ARN, an
instance profile is attached at launch. Generating identity first is correct for
both — IRSA's trust policy can be written against a cluster OIDC issuer the compute
unit outputs, and that is one `dependency` rather than a cycle.

**The tie-break rule for a resource two modules both claim:** a resource belongs to
the module that **writes** to it, and where two modules both write, the one earlier
in apply order wins.

The case that comes up every time is a log group. Observability owns dashboards and
alarms; compute writes log lines. The log group belongs to **compute**, and
observability takes its name as a `dependency` output. Put it the other way around
and the graph closes into a circle: compute depends on observability for the group
name, observability depends on compute for its alarm dimensions.

**A cycle is not caught by `terragrunt hcl validate`.** It evaluates each unit's
configuration without resolving the graph, so a circular stack validates clean; only
`terragrunt run --all` finds it, and that needs credentials, so the first person to
meet it meets it at the first real plan. `check_iac.py` has a `graph` gate that reads
the `dependency` edges statically and refuses a cycle — but the fix is always this
ownership rule, not a rearranged `config_path`.

## `root.hcl`

```hcl
# spec: domain 09-delivery — one backend and one provider definition for the stack
locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals

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

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"

  contents = <<-EOF
    provider "aws" {
      region = "${local.env.region}"

      default_tags {
        tags = ${jsonencode(local.env.tags)}
      }
    }
  EOF
}
```

**The bucket name is derived, not read from the environment.** `get_env` with no
default makes the whole stack fail `terragrunt hcl validate` on any machine that has
not exported the variable — which is every machine at the moment the code is being
written, and the gate runs constantly. Derive it from values the repository already
holds. Where a client's convention embeds the account id in the bucket name, that is
the one case for `get_env`, and it takes a default that is obviously not real.

**No account id anywhere.** The provider authenticates from the environment the
operator is in — an OIDC role in CI, SSO locally — which is what domain 8's "no
long-lived static credentials" means in practice. `check_iac.py` runs the
secret scan over the stack and blocks on an identifier.

## A unit

```hcl
# spec: domain 06-compute, ADR-005 — EKS, three node groups, spot for batch
include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals
}

terraform {
  source = "../../../modules/compute"
}

dependency "network" {
  config_path = "../network"

  mock_outputs                            = { vpc_id = "vpc-mock", private_subnet_ids = ["subnet-mock"] }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

inputs = {
  name       = "${local.env.project}-${local.env.environment}"
  vpc_id     = dependency.network.outputs.vpc_id
  subnet_ids = dependency.network.outputs.private_subnet_ids
}
```

`mock_outputs_allowed_terraform_commands` is not optional. Without it the mock is
used at `apply` too, which is how `vpc-mock` reaches real infrastructure.

**Mock values are plain strings, never ARN-shaped.** `"mock-db-secret"`, not
`"arn:aws:secretsmanager:eu-west-1:000000000000:secret:mock"`. An ARN has an account
slot that has to be filled with something, the secret scan reads that slot, and a
mock that looks like a real ARN is indistinguishable from one to every tool
downstream. One generated stack produced 54 findings this way, all from mocks. The
mock exists to let `validate` and `plan` run before the dependency exists; it does
not have to be realistic to do that.

A remote `terraform.source` needs a `?ref=` pinning a tag or a SHA; without one the
unit tracks a default branch and applies different infrastructure next week from an
unchanged commit. Local paths need no ref — the repository is the version.
`check_iac.py` enforces this.

## `env.hcl`

```hcl
# spec: the environment topology table in architecture-spec.md
locals {
  project     = "acme-lending"
  environment = "prod"
  region      = "eu-west-1"

  tags = {
    Project     = "acme-lending"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}
```

Non-sensitive values only. No account id, no endpoint, no secret — this file is
committed, and the secret scan reads it.

## What goes in `modules/`

A module when the same thing exists in more than one environment, which is nearly
everything in this layout. Not a module for a single resource: `module "kms_key"`
wrapping one `aws_kms_key` adds a directory, a variables file and an indirection to
save nothing.

Do not build an abstraction the specification did not ask for.

**Registry modules earn their place where they encode work you would otherwise
repeat badly** — `terraform-aws-modules/vpc/aws` is the usual example, because
subnet arithmetic, route tables and gateway wiring are tedious and easy to get
subtly wrong. They cost a version to track and a layer to read through when
something is wrong. Pin them exactly; `resolve_versions.py --module` resolves them.

File conventions inside a module are in `references/conventions.md`.

## State

Ask the specification first: domain 9 recorded `iac_state`. Where it did not, these
are the defaults, and they are recorded as defaults rather than decisions.

**Object storage, versioned, encrypted, with native locking.** On AWS that is S3 with
`use_lockfile = true`; the separate DynamoDB lock table is no longer needed on
Terraform 1.10 and later, and adding one now is carrying a dead dependency. On Azure,
a storage account container with blob leasing. On GCP, a GCS bucket with versioning.

**One state file per unit**, which `path_relative_to_include()` gives you for free. A
single state for everything means a change to one component takes a lock every other
component waits on, and a corrupted state loses all of them.

**State is production read access.** It holds resource attributes in plain form —
generated passwords, connection strings, private keys — whatever the configuration
marks sensitive. Whoever can read the state bucket can read those. Say so in the
stack's README, and keep the access list as short as the specification's identity
answers allow.

## What is never committed

`.gitignore`, written in step 1 rather than after the first accident:

```
.terraform/
.terragrunt-cache/
*.tfstate
*.tfstate.*
crash.log
backend.hcl
*.auto.tfvars
override.tf
override.tf.json
```

`.terraform.lock.hcl` **is** committed — it is what makes the provider pins
reproducible down to the checksums. In a Terragrunt stack it lives beside the module
it locks, and Terragrunt copies it into the cache on each run.

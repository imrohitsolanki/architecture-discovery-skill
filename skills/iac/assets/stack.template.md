# Stack skeleton

Every file a Terragrunt-over-Terraform stack has, and what belongs in each. Replace
every `{{...}}` marker. Delete a file that has nothing to hold — an empty
`outputs.tf` is noise, and a deleted one is a decision.

Every file opens with its provenance line. `check_iac.py` requires it in the
first twelve lines of every `.tf` and every Terragrunt `.hcl`, and will not accept a
file without one.

Conventions inside a module — naming, `for_each`, validation, tagging — are in
`references/conventions.md`. This file is the skeleton; that one is the style.

---

## Tool pins, at the root of the stack

`.terraform-version`

```
{{1.16.2 — whatever resolve_versions.py returned}}
```

`.terragrunt-version`

```
{{1.1.1 — resolve_versions.py --terragrunt}}
```

Both, not one. Terragrunt has its own release cadence and its own breaking changes —
the HCL commands were renamed in 0.78 — so an unpinned Terragrunt is a stack that
behaves differently on each machine while every version in the repository says
otherwise.

`.architecture-discovery.json`

```json
{
  "specification": "{{path to architecture-spec.md}}",
  "generated": "{{YYYY-MM-DD}}",
  "note": "This stack was generated from the specification above and has never been planned against a real account. While this file exists, the architecture-discovery plugin blocks terraform and terragrunt apply, destroy, import and state-mutating commands in this tree. Delete it when a person has read the plan and accepts what applying it does."
}
```

Committed, not ignored — the guardrail travels with the branch, so a reviewer who
clones it gets the same protection. Deleting it is how a human takes ownership.

`.gitignore`

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

`.terraform.lock.hcl` is **not** in this list. It is committed.

---

## `root.hcl`

```hcl
# spec: domain 09-delivery — one backend and one provider definition for the stack
locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals

  # Derived from what the repository already holds. `get_env` with no default makes
  # the whole stack fail `terragrunt hcl validate` on any machine that has not
  # exported the variable, which is every machine while the code is being written.
  state_bucket = "${local.env.project}-tfstate-${local.env.region}"
}

remote_state {
  backend = "{{s3}}"

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

# spec: domain 04-cloud — {{provider}}, {{region}}; domain 08-identity — {{how it authenticates}}
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"

  contents = <<-EOF
    provider "{{aws}}" {
      region = "${local.env.region}"

      default_tags {
        tags = ${jsonencode(local.env.tags)}
      }
    }
  EOF
}
```

No credentials, no profile name, no account id. Authentication comes from the
environment the operator is in — an OIDC role in CI, SSO locally — which is what
domain 8's "no long-lived static credentials" means in practice.

---

## `live/{{prod}}/env.hcl`

```hcl
# spec: the environment topology table in architecture-spec.md
locals {
  project     = "{{slug}}"
  environment = "{{prod}}"
  region      = "{{region}}"

  tags = {
    Project     = "{{slug}}"
    Environment = "{{prod}}"
    ManagedBy   = "terraform"
    Spec        = "{{path to architecture-spec.md}}"
  }
}
```

Non-sensitive values only. No account id, no endpoint, no secret — this file is
committed, and the secret scan reads it.

---

## `live/{{prod}}/{{component}}/terragrunt.hcl`

```hcl
# spec: domain {{NN-domain}}, ADR-{{nnn}} — {{the decision in one line}}
include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals
}

terraform {
  source = "../../../modules/{{component}}"
}

dependency "{{network}}" {
  config_path = "../{{network}}"

  mock_outputs                            = { {{vpc_id}} = "{{vpc-mock}}" }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

inputs = {
  name   = "${local.env.project}-${local.env.environment}"
  tags   = local.env.tags
  {{vpc_id}} = dependency.{{network}}.outputs.{{vpc_id}}
}
```

`mock_outputs_allowed_terraform_commands` is not optional. Without it the mock is
used at `apply` too, which is how `vpc-mock` reaches real infrastructure.

**Mock values are plain strings, never ARN-shaped.** `"mock-db-secret"`, not
`"arn:aws:secretsmanager:eu-west-1:000000000000:secret:mock"` — an ARN has an account
slot that has to be filled, the secret scan reads that slot, and a mock that looks
like a real ARN is indistinguishable from one. A mock only has to let `validate` and
`plan` run before the dependency exists; it does not have to be realistic.

A remote `terraform.source` needs `?ref=` pinning a tag or a SHA. A local path needs
none — the repository is the version.

Keep the unit thin: include, source, dependencies, inputs. Logic belongs in the
module, where it can be reused and validated.

---

## `modules/{{component}}/versions.tf`

```hcl
# spec: domain 09-delivery — {{Terraform | OpenTofu}}, versions resolved {{YYYY-MM-DD}}
terraform {
  required_version = "~> {{1.16}}"

  required_providers {
    {{aws}} = {
      source  = "{{hashicorp/aws}}"
      version = "{{6.64.0}}"
    }
  }
}
```

Paste this from `resolve_versions.py --hcl`. Do not type versions from memory.

**No `provider` block and no `backend` block in a module.** A module that configures
its own provider cannot be used with `for_each` or `count`, and `root.hcl` already
generates both. `check_iac.py` refuses it.

## `modules/{{component}}/variables.tf`

```hcl
# spec: domain 05-environments — the module's interface, one value per environment

variable "name" {
  type        = string
  description = "{{name prefix for every resource this module creates}}"
}

variable "tags" {
  type        = map(string)
  description = "Tags merged onto every resource."
  default     = {}
}

# spec: OQ-{{n}} — {{what is unsettled}}; owner {{who}}, default applies {{date}}
variable "{{unsettled_thing}}" {
  type        = {{string}}
  description = "{{what it is}}. OQ-{{n}} is open; no default here on purpose, so this fails at plan rather than provisioning something nobody chose."
}
```

Every variable typed and described — both are gated. A variable the specification
settled gets a `default`; one it did not gets none, and a `description` naming the
open question. Add a `validation` block where a wrong value is expensive.

## `modules/{{component}}/main.tf`

```hcl
# spec: domain {{NN-domain}}, ADR-{{nnn}} — {{the decision in one line}}
locals {
  tags = merge(var.tags, { Component = "{{component}}" })
}

resource "{{aws_vpc}}" "this" {
  {{...}}

  tags = merge(local.tags, { Name = var.name })
}
```

`this` when there is one of something; a descriptive name when there are several. The
resource type is already in the address, so `aws_vpc.vpc` says the same word twice.

Split into `network.tf`, `iam.tf`, `data.tf` past roughly 200 lines — one file per
concern, not one per resource.

## `modules/{{component}}/outputs.tf`

```hcl
# spec: consumed by the {{compute}} unit's dependency block
output "{{vpc_id}}" {
  description = "{{what it is for}}"
  value       = {{aws_vpc.this.id}}
  sensitive   = {{true | false}}
}
```

Every output described — gated. Export what a `dependency` block or an operator
needs, not everything that was created. `sensitive` hides it from the console; it is
still in the state file.

---

## Plain Terraform, where the specification chose that instead

No `root.hcl` and no `live/`. One root module per environment in `envs/<name>/`,
holding `versions.tf`, `providers.tf`, `main.tf`, `variables.tf`, `outputs.tf`,
`terraform.tfvars` and:

```hcl
# spec: domain 09-delivery — remote state, bucket supplied by -backend-config
terraform {
  backend "{{s3}}" {}
}
```

Empty braces on purpose, with the values in an uncommitted `backend.hcl` and a
`backend.hcl.example` beside it:

```hcl
bucket       = "{{name of the state bucket}}"
key          = "{{environment}}/terraform.tfstate"
region       = "{{region}}"
encrypt      = true
use_lockfile = true
```

```
terraform init -backend-config=backend.hcl
```

Everything about modules above is unchanged. Only the composition layer differs.

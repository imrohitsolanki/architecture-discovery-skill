#!/usr/bin/env python3
"""Resolve the current published version of Terraform, its providers and its modules.

Reach for this immediately before writing `versions.tf`, and again whenever a pin is
being raised. Nothing else in this plugin makes a network call; this script exists
because the alternative is worse.

Inputs
    --tool NAME          terraform (default) or opentofu. Repeatable is pointless:
                         a stack pins one.
    --terragrunt         Also resolve the current Terragrunt release, for
                         `.terragrunt-version`. Terragrunt has its own cadence and
                         its own breaking changes — the HCL commands were renamed in
                         0.78 — so it is pinned separately from the tool it wraps.
    --provider SPEC      A provider to resolve. Repeatable. Either a short name this
                         script knows (`aws`, `azurerm`, `google`, `kubernetes`,
                         `helm`, ...) or an explicit `namespace/name`.
    --module SPEC        A registry module, as `namespace/name/provider`. Repeatable.
    --hcl                Print a ready-to-paste `terraform {}` block as well as the
                         table. This is the output the interview actually uses.
    --json               Emit the resolution as JSON.
    --timeout SECONDS    Per-request timeout. Default 10.

Outputs
    One line per resolved item, then optionally the HCL block.

    Exit 0  everything asked for resolved to a concrete version.
    Exit 1  something did not exist — a misspelled provider, a module that is not
            published. The name is wrong; nothing here is guessed in its place.
    Exit 2  the arguments are wrong.
    Exit 3  the registry could not be reached, so nothing was resolved.

Why this is a script and not the model's recollection
    A model's idea of "the latest AWS provider" is its training cut-off's idea, and
    it is confidently wrong in exactly the way a pin must never be: `~> 5.0` written
    into a repository long after 6.x shipped looks deliberate, reviews clean, and
    silently freezes a project a major version behind. Rule 3 of the interview is
    "never invent a number"; a version is a number. This resolves it or says it
    could not.

Why it fails closed rather than falling back
    There is no bundled version table and there will not be one. A table compiled at
    build time is wrong within weeks, and a stale pin that looks authoritative is the
    failure this script exists to prevent — the same reasoning that keeps a price
    table out of the cost gate. Exit 3 is kept distinct from exit 1 so "that provider
    does not exist" and "I could not look" are not confused; they need different
    fixes. With no network, ask for the version rather than writing one.

Why exact pins
    `~> 6.0` re-resolves on every `terraform init` that has no lock file, so two
    engineers and CI can be on three different provider builds while the repository
    says one thing. The lock file is the mechanism that stops that, and an exact
    `required_providers` version is what makes the lock file's contents a decision
    rather than an accident. `check_iac.py` refuses a pin without a patch
    component for this reason.

Network endpoints, stated plainly because this is the only script that has any
    - https://api.releases.hashicorp.com/v1/releases/terraform/latest
    - https://api.github.com/repos/opentofu/opentofu/releases/latest
    - https://api.github.com/repos/gruntwork-io/terragrunt/releases/latest
    - https://registry.terraform.io/v1/providers/<namespace>/<name>
    - https://registry.terraform.io/v1/modules/<namespace>/<name>/<provider>

    All public, all unauthenticated, all read-only. Nothing about the project being
    designed is sent: the request carries a provider name and nothing else.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

USER_AGENT = "architecture-discovery-skill/resolve_versions"

# Short names that get typed, mapped to the registry namespace that publishes them.
# Anything absent here is still resolvable by writing `namespace/name` in full; this
# map only saves typing for the ones an interview names constantly.
PROVIDER_NAMESPACES = {
    "aws": "hashicorp", "awscc": "hashicorp",
    "azurerm": "hashicorp", "azuread": "hashicorp", "azapi": "Azure",
    "google": "hashicorp", "google-beta": "hashicorp",
    "kubernetes": "hashicorp", "helm": "hashicorp", "kubectl": "gavinbunney",
    "random": "hashicorp", "null": "hashicorp", "tls": "hashicorp",
    "time": "hashicorp", "local": "hashicorp", "external": "hashicorp",
    "archive": "hashicorp", "cloudinit": "hashicorp", "dns": "hashicorp",
    "vault": "hashicorp", "consul": "hashicorp", "tfe": "hashicorp",
    "cloudflare": "cloudflare", "datadog": "DataDog", "github": "integrations",
    "grafana": "grafana", "oci": "oracle", "digitalocean": "digitalocean",
    "hetznercloud": "hetznercloud", "proxmox": "Telmate", "vsphere": "hashicorp",
}


class Unreachable(Exception):
    """The registry could not be contacted. Distinct from a name that does not exist."""


def _get(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise LookupError(f"{url} returned 404 — no such name") from exc
        # A 403 from the GitHub API is a rate limit, not a missing release. Treating
        # it as "does not exist" would report OpenTofu as unpublished.
        raise Unreachable(f"{url} returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Unreachable(f"{url} could not be reached: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise Unreachable(f"{url} did not return JSON: {exc}") from exc


def resolve_terragrunt(timeout: float) -> str:
    tag = str(_get("https://api.github.com/repos/gruntwork-io/terragrunt/releases/latest",
                   timeout)["tag_name"])
    return tag.lstrip("v")


def resolve_tool(tool: str, timeout: float) -> str:
    if tool == "terraform":
        return str(_get("https://api.releases.hashicorp.com/v1/releases/terraform/latest",
                        timeout)["version"])
    if tool == "opentofu":
        tag = str(_get("https://api.github.com/repos/opentofu/opentofu/releases/latest",
                       timeout)["tag_name"])
        return tag.lstrip("v")
    raise ValueError(tool)


def split_provider(spec: str) -> tuple[str, str]:
    """`aws` -> (hashicorp, aws); `Azure/azapi` -> (Azure, azapi)."""
    if "/" in spec:
        namespace, _, name = spec.partition("/")
        return namespace, name
    namespace = PROVIDER_NAMESPACES.get(spec.lower())
    if namespace is None:
        raise ValueError(
            f"{spec!r} is not a short name this script knows. Write it as "
            f"`namespace/name` — the registry page for the provider shows both."
        )
    return namespace, spec.lower()


def resolve_provider(spec: str, timeout: float) -> dict:
    namespace, name = split_provider(spec)
    data = _get(f"https://registry.terraform.io/v1/providers/{namespace}/{name}",
                timeout)
    return {"source": f"{namespace}/{name}", "version": str(data["version"]),
            "name": name}


def resolve_module(spec: str, timeout: float) -> dict:
    parts = spec.split("/")
    if len(parts) != 3:
        raise ValueError(
            f"{spec!r} is not a module address. Registry modules are "
            f"`namespace/name/provider`, for example "
            f"`terraform-aws-modules/vpc/aws`."
        )
    data = _get("https://registry.terraform.io/v1/modules/" + "/".join(parts), timeout)
    return {"source": spec, "version": str(data["version"])}


def installed_version(tool: str) -> str | None:
    """The version of the binary on this machine, or None if it is not installed.

    `terraform version` prints `Terraform v1.15.8` on its first line; `tofu version`
    is the same shape.
    """
    binary = "terraform" if tool == "terraform" else "tofu"
    if shutil.which(binary) is None:
        return None
    try:
        proc = subprocess.run([binary, "version"], capture_output=True, text=True,
                              timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"v?(\d+\.\d+\.\d+)", proc.stdout + proc.stderr)
    return m.group(1) if m else None


def _minor(version: str) -> tuple[int, int]:
    parts = version.split(".")
    return int(parts[0]), int(parts[1])


def hcl_block(tool: str, tool_version: str, providers: list[dict],
              local_version: str | None = None) -> str:
    """The `terraform {}` block, with the resolved versions pinned exactly.

    `required_version` is written as `~> x.y` deliberately, and it is the one place
    a range is right: patch releases of Terraform itself are bug fixes, and pinning
    the patch means every engineer and every CI image has to move in lockstep for
    no benefit. Providers are the opposite — a provider patch can change a resource
    schema — so those are exact.

    The floor is the *installed* minor version where that is older than the released
    one. Rule 2 says paste this block verbatim, and a block resolved as `~> 1.16` on
    a machine running 1.15.8 makes every module fail `validate` with an
    unsupported-version error that names no cause — the version block is the last
    place anyone looks. The exact resolved version still goes in
    `.terraform-version`, which is where a tool version belongs; this is the floor
    the configuration will accept, not a statement about what to run.
    """
    floor = tool_version
    note_extra = ""
    if local_version and _minor(local_version) < _minor(tool_version):
        floor = local_version
        note_extra = (
            f"# Floor is {'.'.join(local_version.split('.')[:2])} because the "
            f"{tool} on this machine is {local_version}, older than the released "
            f"{tool_version}.\n"
            f"# Put {tool_version} in .terraform-version and raise this floor when "
            f"everyone is on it.\n")
    lines = [
        "terraform {",
        f'  required_version = "~> {".".join(floor.split(".")[:2])}"',
        "",
        "  required_providers {",
    ]
    for p in providers:
        lines += [
            f"    {p['name']} = {{",
            f'      source  = "{p["source"]}"',
            f'      version = "{p["version"]}"',
            "    }",
        ]
    lines += ["  }", "}"]
    note = (f"# Resolved from the {'public Terraform registry' if tool == 'terraform' else 'registry and the OpenTofu releases API'}. "
            f"{tool} {tool_version} was current when this was written.\n"
            "# Raise a pin deliberately, with a changelog read, not by loosening it.\n"
            + note_extra)
    return note + "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tool", default="terraform", choices=("terraform", "opentofu"))
    ap.add_argument("--terragrunt", action="store_true",
                    help="also resolve the current Terragrunt release")
    ap.add_argument("--provider", action="append", default=[])
    ap.add_argument("--module", action="append", default=[])
    ap.add_argument("--hcl", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeout", type=float, default=10.0)
    args = ap.parse_args()

    result: dict = {"tool": args.tool, "tool_version": None, "terragrunt": None,
                    "installed": installed_version(args.tool),
                    "providers": [], "modules": [], "not_found": []}
    try:
        result["tool_version"] = resolve_tool(args.tool, args.timeout)
        if args.terragrunt:
            result["terragrunt"] = resolve_terragrunt(args.timeout)
        for spec in args.provider:
            try:
                result["providers"].append(resolve_provider(spec, args.timeout))
            except LookupError:
                result["not_found"].append({"kind": "provider", "spec": spec})
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
        for spec in args.module:
            try:
                result["modules"].append(resolve_module(spec, args.timeout))
            except LookupError:
                result["not_found"].append({"kind": "module", "spec": spec})
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
    except Unreachable as exc:
        print(f"error: {exc}\n\n"
              f"Nothing was resolved, and nothing will be guessed in its place. "
              f"There is no bundled version table: one compiled at build time would "
              f"be wrong within weeks, and a stale pin that reads as deliberate is "
              f"the failure this script exists to prevent.\n\n"
              f"Ask whoever is running the interview for the versions to pin, record "
              f"where they got them, and write those. Or re-run this with network "
              f"access.", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{args.tool:<12} {result['tool_version']}"
              + (f"   (installed: {result['installed']})" if result["installed"] else
                 f"   (not installed here)"))
        if result["terragrunt"]:
            print(f"{'terragrunt':<12} {result['terragrunt']}")
        for p in result["providers"]:
            print(f"provider     {p['source']:<36} {p['version']}")
        for m in result["modules"]:
            print(f"module       {m['source']:<36} {m['version']}")
        for nf in result["not_found"]:
            print(f"NOT FOUND    {nf['kind']} {nf['spec']} — check the spelling on "
                  f"the registry; nothing was substituted")
        if args.hcl and result["providers"]:
            print("")
            print(hcl_block(args.tool, result["tool_version"], result["providers"],
                            result.get("installed")))

    return 1 if result["not_found"] else 0


if __name__ == "__main__":
    sys.exit(main())

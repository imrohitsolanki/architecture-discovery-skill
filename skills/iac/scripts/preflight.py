#!/usr/bin/env python3
"""Check the tools generation depends on, before the first file is written.

Reach for this once, as step 0 of "Before the first file". Nothing it reports
changes while generation is in progress, and every missing tool it names costs a
gate that reports "did not run" halfway through a stack rather than at the start —
which is when the finding is cheap.

The discovery stage has its own preflight for git and gitleaks. This is the other
half: the two IaC binaries, and the policy scanner the specification itself chose.

Inputs
    --state PATH   discovery-state.json, so the scanner domain 9a recorded is
                   probed by name rather than guessed at. Optional: without it the
                   scanner tier is reported as unknown rather than as present.
    --json         Emit the report as JSON.
    --list         Print the dependency manifest and exit 0 without probing.

Outputs
    One line per tool, each saying what its absence costs.

    Exit 0  every required tool is present.
    Exit 1  a required tool is missing, or a bundled entry point is not executable.

Why `terraform` is required here and optional in the documentation
    Both statements are true and they are about different things. The *skill* still
    works without it: files get written and every static gate runs. But `fmt` and
    `validate` then report "did not run", and a gate that did not run has not
    passed — so a stack generated on a machine with no binary is a stack nobody has
    checked, handed over as though checked. That is worth an exit 1 at the start
    rather than a line nobody reads at the end.

Why the scanner is a notice and not a failure
    The specification chooses it in domain 9a and this plugin installs nothing. A
    named scanner that is absent is reported loudly, because the built-in checks are
    a floor and the run that found eight real omissions in a stack that passed all
    of them found them with a scanner.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _shared import DISCOVER_SCRIPTS  # noqa: E402

# name -> (why, how to install, what its absence costs)
REQUIRED: dict[str, tuple[str, str, str]] = {
    "terraform": (
        "`terraform fmt -check` and `terraform validate` over every module. `tofu` "
        "satisfies this too, and a tree carrying `.opentofu-version` wants tofu.",
        "brew install terraform, or tfenv/asdf/mise per the version file",
        "Both halves of `fmt` and `validate` report that they did not run. The "
        "stack is then handed over unchecked while the summary reads as though it "
        "were checked.",
    ),
    "terragrunt": (
        "`terragrunt hcl fmt --check` and `terragrunt hcl validate` over the units. "
        "Only required where domain 9 chose Terragrunt.",
        "brew install terragrunt, or see https://terragrunt.gruntwork.io/docs/getting-started/install/",
        "The unit half of `fmt` and `validate` does not run, so a broken `include` "
        "or a mistyped `config_path` surfaces at the first real plan instead of in "
        "a second.",
    ),
    "gitleaks": (
        "The secret scan `check_iac.py` runs over the whole generated stack before "
        "it is committed.",
        "brew install gitleaks, or see https://github.com/gitleaks/gitleaks#installing",
        "The secret gate fails closed and blocks. A stack committed without it is "
        "published with whatever is in it.",
    ),
}

OPTIONAL = {
    "tofu": "OpenTofu, where the specification chose it over Terraform.",
}

SCANNERS = ("checkov", "tfsec", "trivy", "terrascan")

ENTRY_POINTS = ("preflight.py", "plan_tasks.py", "resolve_versions.py",
                "check_iac.py")


def _version_of(tool: str) -> str | None:
    for flag in ("--version", "version", "-v"):
        try:
            out = subprocess.run([tool, flag], capture_output=True, text=True,
                                 timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue
        text = (out.stdout or out.stderr).strip()
        if text:
            return text.splitlines()[0][:80]
    return None


def _probe(tool: str) -> dict:
    path = shutil.which(tool)
    return {"tool": tool, "present": path is not None, "path": path,
            "version": _version_of(tool) if path else None}


def chosen_scanner(state: Path | None) -> str | None:
    """The scanner domain 9a recorded, if the state file names one."""
    if state is None or not state.is_file():
        return None
    sys.path.insert(0, str(DISCOVER_SCRIPTS))
    try:
        import _state
        answers = (_state.load(state).get("domains", {})
                   .get("09-delivery", {}).get("answers") or {})
    except Exception:  # noqa: BLE001 — the spec gate reports a bad state file
        return None
    recorded = str(answers.get("policy_pre_apply", "")).lower()
    return next((s for s in SCANNERS if s in recorded), None)


def _manifest_text() -> str:
    lines = ["Required:"]
    for tool, (why, install, without) in REQUIRED.items():
        lines += [f"  {tool}", f"      why: {why}", f"      install: {install}",
                  f"      without it: {without}"]
    lines.append("Chosen by the specification:")
    lines.append("  the domain 9a policy scanner, one of: " + ", ".join(SCANNERS))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state", help="path to discovery-state.json")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        print(_manifest_text())
        return 0

    state = Path(args.state).expanduser().resolve() if args.state else None
    scanner = chosen_scanner(state)

    required = [_probe(t) for t in REQUIRED]
    # OpenTofu satisfies the Terraform requirement. A tree pinned to tofu has no
    # reason to install terraform, and failing it here would be this script
    # insisting on a tool the specification did not choose.
    tofu = _probe("tofu")
    for entry in required:
        if entry["tool"] == "terraform" and not entry["present"] and tofu["present"]:
            entry["present"] = True
            entry["path"] = tofu["path"]
            entry["version"] = tofu["version"] + "  (satisfies the terraform requirement)"

    report = {
        "required": required,
        "optional": [tofu],
        "scanner": ({"tool": scanner, **_probe(scanner)} if scanner else None),
        "entry_points": [
            {"script": n, "exists": (HERE / n).is_file(),
             "executable": (HERE / n).is_file() and os.access(HERE / n, os.X_OK)}
            for n in ENTRY_POINTS
        ],
    }
    missing = [r["tool"] for r in required if not r["present"]]
    bad = [e["script"] for e in report["entry_points"]
           if not e["exists"] or not e["executable"]]
    report["ok"] = not missing and not bad

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1

    print("Required")
    for r in required:
        if r["present"]:
            print(f"  [ok]   {r['tool']:<12} {r['version'] or r['path']}")
        else:
            why, install, without = REQUIRED[r["tool"]]
            print(f"  [FAIL] {r['tool']:<12} not on PATH")
            print(f"         needed for: {why}")
            print(f"         install:    {install}")
            print(f"         without it: {without}")

    print("\nPolicy scanner (domain 9a)")
    if report["scanner"] is None:
        print("  [----] none recorded in the specification, or no --state given. "
              "Only the built-in checks will run, and they are a floor: they catch "
              "what is always wrong, never what is wrong here.")
    elif report["scanner"]["present"]:
        print(f"  [ok]   {report['scanner']['tool']:<12} "
              f"{report['scanner']['version'] or report['scanner']['path']}")
    else:
        print(f"  [----] {report['scanner']['tool']:<12} not on PATH, and the "
              f"specification chose it. The guardrails gate will report that it did "
              f"not run — which is not the same as passing. Install it before "
              f"treating this stack as scanned.")

    print("\nBundled entry points")
    for e in report["entry_points"]:
        if e["exists"] and e["executable"]:
            print(f"  [ok]   {e['script']}")
        elif e["exists"]:
            print(f"  [FAIL] {e['script']} exists but is not executable. "
                  f"Run: chmod +x {HERE / e['script']}")
        else:
            print(f"  [FAIL] {e['script']} is missing")

    if not report["ok"]:
        print("\nPreflight failed. Fix the items marked FAIL before writing the "
              "first file — a gate that cannot run is a gate that has not passed, "
              "and finding that out six modules in means fixing six modules.")
    else:
        print("\nPreflight passed.")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

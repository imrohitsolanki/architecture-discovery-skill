#!/usr/bin/env python3
"""Prove the guardrail hook denies an apply against a real generated stack.

The generation harness already classifies ten commands against a synthetic marker.
This runs the same hook against the stack CI just built and gated, because the thing
being protected is a stack on disk rather than a fixture in a temporary directory —
and a hook that works on the fixture and not on the real layout would pass the
harness and protect nothing.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOK = ROOT / "hooks" / "block_mutating_iac.py"


def decision(command: str, cwd: pathlib.Path) -> str:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "cwd": str(cwd),
                          "tool_input": {"command": command}}),
        capture_output=True, text=True)
    if not proc.stdout.strip():
        return "allow"
    return json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_hook_denies.py <stack directory>", file=sys.stderr)
        return 2
    stack = pathlib.Path(sys.argv[1])
    (stack / ".architecture-discovery.json").write_text(json.dumps({
        "specification": "artifacts/architecture-spec.md",
        "generated": "ci",
    }), encoding="utf-8")

    failures = []
    for command, want in (("terraform apply", "deny"),
                          ("terragrunt run --all apply", "deny"),
                          ("terraform destroy -auto-approve", "deny"),
                          ("terraform plan", "allow"),
                          ("terragrunt hcl validate", "allow")):
        got = decision(command, stack)
        mark = "ok  " if got == want else "FAIL"
        print(f"  {mark} {command!r} -> {got}")
        if got != want:
            failures.append(f"{command!r} was {got}, wanted {want}")

    # And nothing outside the marked tree, which is the whole basis of the scoping.
    outside = stack.parent / "unrelated"
    outside.mkdir(exist_ok=True)
    got = decision("terraform apply", outside)
    print(f"  {'ok  ' if got == 'allow' else 'FAIL'} 'terraform apply' outside the "
          f"stack -> {got}")
    if got != "allow":
        failures.append("the hook reached outside a generated stack")

    if failures:
        print("\n" + "\n".join(failures))
        return 1
    print("\nThe hook denies what it must and touches nothing else.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

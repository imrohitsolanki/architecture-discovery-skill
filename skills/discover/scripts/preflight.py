#!/usr/bin/env python3
"""Check that the tools this skill depends on are present before the interview starts.

Reach for this once at the beginning of a discovery session, or when something
unexpectedly failed and you want to know whether a missing binary explains it.
There is no reason to run it again mid-interview; nothing it reports changes while
a session is in progress.

Inputs
    --json      Emit the report as JSON instead of text. Use this when you want to
                branch on a specific tool rather than read the summary.
    --list      Print the dependency manifest and exit 0 without probing anything.
                Useful for documentation, and for answering "what does this need?"
                without running it.

Outputs
    A report on stdout, one line per tool.
    Exit 0  every required tool is present, and the bundled scripts are executable.
            Optional tools may be missing; each is reported as a notice.
    Exit 1  a required tool is missing, or a bundled script is not executable.

Why the executable check is in here
    The skill's `allowed-tools` grant names each entry-point script by absolute path.
    A rule like Bash(/path/run_gates.py *) only matches when the file is invoked
    directly, which needs the executable bit set. Without it the script still runs
    via `python3 /path/run_gates.py`, but that command matches no rule, so the user
    gets a permission prompt that the grant was written to avoid. A missing
    executable bit is therefore a real defect and not a cosmetic one, which is why
    it exits 1 rather than warning.

The manifest below is the only one
    There used to be a prose copy in TOOLS.md, maintained by hand alongside this,
    and it drifted: it advertised terraform, terragrunt and the aws CLI as optional
    tools that improve pre-fill, guarded behind `|| true`. No script invokes any of
    them — detect_conventions.py imports neither subprocess nor shutil and reads .tf
    and .hcl as text — so the whole optional tier was a dependency contract nothing
    honoured, probed once per session for nothing. Both are gone. README.md states
    the four real requirements; this file is what actually runs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 9)

# name -> (why it is needed, how to install it, what happens without it)
REQUIRED: dict[str, tuple[str, str, str]] = {
    "git": (
        "Artifacts are delivered as a reviewable branch and pull request, and repo "
        "history is read when pre-filling interview answers.",
        "Preinstalled on macOS via Xcode command line tools; apt install git on Debian.",
        "The interview still works, but artifacts cannot be delivered for review.",
    ),
    "gitleaks": (
        "The secret scan over emitted artifacts and discovery-state.json, all of "
        "which get committed.",
        "brew install gitleaks, or see https://github.com/gitleaks/gitleaks#installing",
        "The secret-scan gate fails closed and blocks spec emission. A committed "
        "state file that was never scanned is worse than a blocked interview.",
    ),
}

# Entry points named in the skill's allowed-tools. Kept in step with the frontmatter
# by hand: a script added here without a matching `allowed-tools` rule cannot be run,
# and a rule with no script here is a grant nothing uses.
ENTRY_POINTS = ("preflight.py", "detect_conventions.py", "run_gates.py")


def _version_of(tool: str) -> str | None:
    """Best-effort version string. None when the tool runs but says nothing useful."""
    for flag in ("--version", "version", "-v"):
        try:
            out = subprocess.run(
                [tool, flag], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            continue
        text = (out.stdout or out.stderr).strip()
        if text:
            return text.splitlines()[0][:80]
    return None


def _probe(tool: str) -> dict[str, object]:
    path = shutil.which(tool)
    return {
        "tool": tool,
        "present": path is not None,
        "path": path,
        "version": _version_of(tool) if path else None,
    }


def _check_entry_points(script_dir: Path) -> list[dict[str, object]]:
    results = []
    for name in ENTRY_POINTS:
        target = script_dir / name
        results.append(
            {
                "script": name,
                "exists": target.is_file(),
                "executable": target.is_file() and os.access(target, os.X_OK),
            }
        )
    return results


def _manifest_text() -> str:
    lines = ["Required:"]
    for tool, (why, install, without) in REQUIRED.items():
        lines += [f"  {tool}", f"      why: {why}", f"      install: {install}",
                  f"      without it: {without}"]
    return "\n".join(lines)


# Depth 4 matches what the shell version used. Unbounded recursion is not worth it
# here: this runs before the interview's first turn, and a monorepo with a deep
# node_modules would make the skill look hung while it walked something irrelevant.
MAX_PROBE_DEPTH = 4


def _bounded(root: Path, name: str) -> list[Path]:
    """Every match for `name` within MAX_PROBE_DEPTH levels of root. Never raises."""
    hits: list[Path] = []
    for depth in range(MAX_PROBE_DEPTH):
        try:
            hits.extend(root.glob("/".join(["*"] * depth + [name])))
        except OSError:
            continue
    return hits


def _k8s(root: Path) -> int:
    """YAML sitting under a directory named k8s or kubernetes."""
    return sum(1 for p in _bounded(root, "*.yaml")
               if any(part in ("k8s", "kubernetes") for part in p.parts))


def session_context() -> str:
    """The four session facts SKILL.md needs before its first turn.

    SKILL.md used to gather these with four injected shell commands, two of them
    brace groups wrapping pipelines and command substitutions. Injected commands are
    permission-checked, and the skill's `allowed-tools` grants exactly three script
    paths — so that shell was outside the grant, and a non-zero exit from an injected
    command aborts the whole skill invocation. Doing it here puts the work inside a
    script the grant already covers, in one process instead of four.

    Every probe is best-effort. This function must not raise and must not exit
    non-zero, whatever the invocation directory looks like.
    """
    cwd = Path.cwd()
    out = [f"- Working directory: {cwd}"]

    states = [p for p in _bounded(cwd, "discovery-state.json") if ".git" not in p.parts][:5]
    out.append("- Existing state files: " + (
        ", ".join(str(p.relative_to(cwd)) for p in states) if states
        else "none — this is a new interview"))

    try:
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=5)
        repo = root.stdout.strip() if root.returncode == 0 else "not a git repository"
    except (OSError, subprocess.SubprocessError):
        repo = "not a git repository"
    out.append(f"- Repository: {repo}")

    def count(name: str, exclude: str | None = None) -> int:
        return sum(1 for p in _bounded(cwd, name)
                   if exclude is None or exclude not in p.parts)

    infra = (f"terraform:{count('*.tf', '.terraform')} "
             f"helm:{count('Chart.yaml')} "
             f"k8s-manifests:{_k8s(cwd)} "
             f"compose:{count('docker-compose*')}")
    out.append(f"- Infrastructure present: {infra}")

    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--list", action="store_true", help="print the manifest and exit")
    ap.add_argument("--context", action="store_true",
                    help="print the session facts SKILL.md injects, and exit 0")
    args = ap.parse_args()

    if args.list:
        print(_manifest_text())
        return 0

    if args.context:
        # Always exit 0, whatever happened. A non-zero exit from an injected
        # skill command aborts the whole invocation, so a probe failing on some
        # unreadable directory must never be what stops the interview starting.
        try:
            print(session_context())
        except Exception as exc:  # noqa: BLE001 — deliberately total
            print(f"- Working directory: {Path.cwd()}\n"
                  f"- Session probe failed ({exc.__class__.__name__}), so nothing "
                  f"is pre-filled. Ask for these rather than inferring them.")
        return 0

    script_dir = Path(__file__).resolve().parent
    report = {
        "python": {
            "version": f"{sys.version_info.major}.{sys.version_info.minor}."
                       f"{sys.version_info.micro}",
            "ok": sys.version_info[:2] >= MIN_PYTHON,
            "minimum": f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
        },
        "required": [_probe(t) for t in REQUIRED],
        "entry_points": _check_entry_points(script_dir),
    }

    missing_required = [r["tool"] for r in report["required"] if not r["present"]]
    bad_scripts = [
        e["script"] for e in report["entry_points"]
        if not e["exists"] or not e["executable"]
    ]
    failed = bool(missing_required) or bool(bad_scripts) or not report["python"]["ok"]
    report["ok"] = not failed

    if args.json:
        print(json.dumps(report, indent=2))
        return 1 if failed else 0

    py = report["python"]
    mark = "ok" if py["ok"] else "FAIL"
    print(f"[{mark}] python3 {py['version']} (minimum {py['minimum']})")

    print("\nRequired")
    for r in report["required"]:
        if r["present"]:
            print(f"  [ok]   {r['tool']:<12} {r['version'] or r['path']}")
        else:
            why, install, without = REQUIRED[r["tool"]]
            print(f"  [FAIL] {r['tool']:<12} not on PATH")
            print(f"         needed for: {why}")
            print(f"         install:    {install}")
            print(f"         without it: {without}")

    print("\nBundled entry points")
    for e in report["entry_points"]:
        if e["exists"] and e["executable"]:
            print(f"  [ok]   {e['script']}")
        elif e["exists"]:
            print(f"  [FAIL] {e['script']} exists but is not executable. "
                  f"Run: chmod +x {script_dir / e['script']}")
            print("         Without the executable bit the allowed-tools rule for "
                  "this script does not match, so it will prompt.")
        else:
            print(f"  [FAIL] {e['script']} is missing")

    if failed:
        print("\nPreflight failed. Fix the items marked FAIL before starting the "
              "interview.")
    else:
        print("\nPreflight passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

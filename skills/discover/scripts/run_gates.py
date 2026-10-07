#!/usr/bin/env python3
"""Run every validation gate and report one verdict.

Reach for this before emitting or updating a specification, and again after any
revision. It is the only gate command that needs to be run by hand; it invokes the
five individual gates itself.

Inputs
    --state PATH       discovery-state.json. Required.
    --artifacts DIR    The artifact output directory. Required unless --draft.
                       The secret scan needs somewhere to look, and the completeness
                       gate checks the documents are actually there.
    --draft            Mid-interview mode: report everything, tolerate an
                       unfinished interview, and skip the secret scan because
                       there is nothing written yet. Always exits 0.
    --strict           Pass --strict to the contradiction gate, so warnings fail too.
    --skip NAME        Skip a named gate. Repeatable. Every skip is printed in the
                       summary, because a gate that was skipped silently is worse
                       than one that failed loudly.
    --json             Emit the aggregate as JSON.

Outputs
    A summary line per gate, then the full output of every gate that had something
    to say.

    Exit 0  every gate passed, or --draft.
    Exit 1  at least one gate failed.
    Exit 2  arguments are wrong, or a gate script is missing.

Gate order, and why it is this order
    completeness first, because a specification with an unanswered blocking domain
    should not have its cost or its compliance discussed yet — the later gates would
    be analysing a draft as though it were finished. Then contradictions, which can
    invalidate answers the remaining gates depend on. Then compliance and cost, which
    are independent of each other. The secret scan runs last, on written artifacts,
    since it is the only gate that reads output rather than state.

    A failing early gate does not stop the later ones. Getting one report with five
    problems beats five runs finding one problem each.

Why each gate is a separate process
    A Bash permission rule does not extend across shell operators, so this script
    never builds a command line with `&&` or a pipe; it invokes each gate with an
    argument list and no shell. That is also why only three scripts appear in the
    skill's `allowed-tools`: a subprocess of an already-allowed command needs no rule
    of its own, so the five gates are reachable through this one entry point without
    granting five more rules.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# name -> (script, builds argv, what a failure means)
GATES = ("completeness", "contradictions", "compliance", "cost", "secrets")

# Exit codes every gate shares. Only exit 1 is the gate's own verdict.
EXIT_MEANING = {
    2: "the state file is missing or malformed, so this gate never ran",
    3: "gitleaks is not installed, so nothing was scanned",
}

DESCRIPTIONS = {
    "completeness": "a blocking domain is unanswered, or an artifact is missing",
    "contradictions": "two answers cannot both be satisfied",
    "compliance": "an obligation is unaddressed, or a regime is a stub",
    "cost": "a price has no assumptions, or the ceiling is exceeded",
    "secrets": "a credential, key or account identifier is in the artifacts",
}


def _argv(name: str, state: Path, artifacts: Path | None,
          draft: bool, strict: bool) -> list[str] | None:
    if name == "completeness":
        argv = [str(HERE / "check_completeness.py"), str(state)]
        if draft:
            # Mid-interview nothing is written yet, so the artifact half would fail
            # on every draft run and train people to ignore it.
            return argv + ["--draft"]
        if artifacts is not None:
            argv += ["--artifacts", str(artifacts)]
        return argv
    if name == "contradictions":
        return [str(HERE / "check_contradictions.py"), str(state)] + (["--strict"] if strict else [])
    if name == "compliance":
        return [str(HERE / "check_compliance.py"), str(state)]
    if name == "cost":
        return [str(HERE / "check_cost.py"), str(state)]
    if name == "secrets":
        # --draft skips it as the docstring promises. It used to test only
        # `artifacts is None`, so a draft run given an artifact directory scanned
        # anyway and then printed that it had not — the summary understating what
        # the security gate did is the one direction that must never happen.
        if artifacts is None or draft:
            return None
        return [str(HERE / "scan_secrets.py"), str(artifacts)]
    raise ValueError(name)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state", required=True)
    ap.add_argument("--artifacts")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--skip", action="append", default=[], choices=GATES)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    state = Path(args.state).expanduser().resolve()
    artifacts = Path(args.artifacts).expanduser().resolve() if args.artifacts else None

    if artifacts is None and not args.draft:
        print("error: --artifacts is required unless --draft is given. The secret "
              "scan has to have somewhere to look, and skipping it silently before a "
              "commit is the one thing this script must not do.", file=sys.stderr)
        return 2

    missing = [g for g in GATES
               if g not in args.skip
               and not (HERE / f"check_{g}.py").is_file()
               and not (g == "secrets" and (HERE / "scan_secrets.py").is_file())]
    if missing:
        print(f"error: gate script(s) not found for: {', '.join(missing)}",
              file=sys.stderr)
        return 2

    results = []
    for name in GATES:
        if name in args.skip:
            results.append({"gate": name, "status": "skipped", "code": None,
                            "output": "", "note": "skipped on the command line"})
            continue
        argv = _argv(name, state, artifacts, args.draft, args.strict)
        if argv is None:
            note = ("skipped in draft mode; run again without --draft before "
                    "committing" if args.draft else
                    "no artifact directory given; nothing written to scan yet")
            results.append({
                "gate": name, "status": "not-run", "code": None, "output": "",
                "note": note})
            continue
        proc = subprocess.run([sys.executable] + argv, capture_output=True, text=True)
        out = (proc.stdout + proc.stderr).strip()
        results.append({
            "gate": name,
            "status": "pass" if proc.returncode == 0 else "fail",
            "code": proc.returncode, "output": out, "note": None,
        })

    failed = [r for r in results if r["status"] == "fail"]
    skipped = [r for r in results if r["status"] in ("skipped", "not-run")]
    aggregate = {
        "state": str(state), "artifacts": str(artifacts) if artifacts else None,
        "draft": args.draft, "strict": args.strict,
        "results": results,
        "ok": not failed,
    }

    if args.json:
        print(json.dumps(aggregate, indent=2))
    else:
        print("Gate summary")
        print("")
        for r in results:
            mark = {"pass": "pass", "fail": "FAIL",
                    "skipped": "skip", "not-run": "----"}[r["status"]]
            line = f"  [{mark}] {r['gate']}"
            if r["status"] == "fail":
                # Exit 1 is the gate's own verdict; 2 and 3 mean it never got far
                # enough to have one. Printing the verdict blurb for all three told
                # a confident lie — a missing state file reported as "a blocking
                # domain is unanswered", and a missing gitleaks as a secret found.
                line += f"  (exit {r['code']}) — {EXIT_MEANING.get(r['code'], DESCRIPTIONS[r['gate']])}"
            elif r["note"]:
                line += f"  — {r['note']}"
            print(line)
        print("")
        for r in results:
            if not r["output"]:
                continue
            print("=" * 72)
            print(f"{r['gate']}")
            print("=" * 72)
            print(r["output"])
            print("")
        if args.draft:
            print("Draft mode: reporting only. Nothing here blocks, and the secret "
                  "scan has not run. Run again without --draft before committing.")
        elif failed:
            print(f"{len(failed)} gate(s) failed. Do not emit a specification until "
                  f"each is either fixed or recorded as a waiver with a reason and an "
                  f"owner.")
        elif skipped:
            print("All gates that ran passed, but "
                  f"{len(skipped)} did not run: "
                  f"{', '.join(r['gate'] for r in skipped)}. A gate that did not run "
                  f"has not passed.")
        else:
            print("All five gates passed.")

    return 0 if (args.draft or not failed) else 1


if __name__ == "__main__":
    sys.exit(main())

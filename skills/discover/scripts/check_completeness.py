#!/usr/bin/env python3
"""Refuse to emit a final specification while a blocking domain is unanswered.

Reach for this before writing `architecture-spec.md`, not after. It is the gate that
stops a specification being published with a hole in it, and it names the hole
precisely so the interview knows what to go and ask.

Inputs
    STATE            Path to discovery-state.json. Positional, required.
    --artifacts DIR  The artifact output directory. When given, the documents the
                     specification is delivered as are checked for existence, and
                     the specification for the three diagrams SKILL.md requires.
                     Omitted mid-interview, when nothing has been written yet.
    --draft          Report the same findings but exit 0. Use while the interview is
                     still running, when you want the shape of what remains rather
                     than a verdict.
    --json           Emit findings as JSON.

Outputs
    A report naming every blocking domain that is unanswered, with why that domain
    blocks, and every non-blocking domain that will be filled from a secure default
    if it stays unanswered.

    Exit 0  every blocking domain is answered, or --draft was passed.
    Exit 1  at least one blocking domain is unanswered.
    Exit 2  the state file is missing or malformed.

Why it distinguishes blocking from merely incomplete
    A gate that refuses on everything is a gate somebody switches off. Seven of the
    fourteen domains block, and the test is whether a default would be a guess about
    the *business* — what the thing does, who regulates it, what an outage costs, what
    they can spend, who will run it. Nobody can default those on a client's behalf.
    The other seven have defensible technical defaults, so they are reported as
    "will be defaulted" rather than as failures, and the specification records them as
    defaults rather than as decisions so a reviewer can see they were never chosen.

Why the artifacts are checked here and not only the state file
    This gate used to read the state file alone, so nothing anywhere verified that
    the specification had been written at all. Every domain could be answered, every
    gate green, and the output directory empty — the gates would report a
    specification ready to emit while describing a document that did not exist.

    The check is deliberately shallow: the three documents exist, and the
    specification carries the three Mermaid blocks SKILL.md requires — network
    topology, delivery flow, environment promotion. Whether a diagram is *right* is
    a reviewer's judgement; whether it is *there* is not, and it was the missing
    half.

Why an unowned open question blocks
    §4's bargain is that the interview never stalls: an unknown becomes an open
    question with a proposed default, a named owner and a date the default takes
    effect, and the next question gets asked. The owner and the date are the whole
    consideration. Without them nothing is deferred — the unknown has left the
    conversation with nobody holding it — so an open question missing either one is
    refused here rather than listed.

Why an open question does not unblock a domain
    §4 says the interview never blocks: an unknown becomes an open question with a
    proposed default and an owner, and the interview moves on. That keeps the
    *interview* going. It does not make the *specification* final. A blocking domain
    whose answer is an unresolved open question is still unanswered, and this gate
    says so — otherwise "never block" would quietly become "never finish".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import (  # noqa: E402
    BLOCKING, DOMAINS, StateError, answer_key_problems, is_answered, load, status_of,
)


# The documents SKILL.md promises to deliver, and what each is for. ADRs are not
# here: how many a project needs is a judgement about the project, and a gate
# demanding a fixed number would get one written to satisfy it.
REQUIRED_ARTIFACTS = {
    "architecture-spec.md": "the specification itself — decisions, rationale, the "
                            "environment topology table and the control mapping",
    "README.md": "the plain-language version, for whoever is paying for this",
    "open-questions.md": "every TBD with an owner and the default that applies",
}

MERMAID_BLOCK = re.compile(r"(?m)^\s*```\s*mermaid\b")
REQUIRED_DIAGRAMS = 3


def check_artifacts(artifacts: Path) -> list[dict]:
    """The documents exist, and the specification carries its three diagrams."""
    problems = []
    for name, why in REQUIRED_ARTIFACTS.items():
        path = artifacts / name
        if not path.is_file():
            problems.append({
                "artifact": name,
                "detail": f"{name} is not in {artifacts}. It is {why}. A gate that "
                          f"reads only the state file reports a specification ready "
                          f"to emit while the specification does not exist."})
        elif not path.read_text(encoding="utf-8", errors="replace").strip():
            problems.append({
                "artifact": name,
                "detail": f"{name} exists but is empty. An empty file and a written "
                          f"one are indistinguishable in a directory listing, which "
                          f"is where this would otherwise be noticed."})

    spec = artifacts / "architecture-spec.md"
    if spec.is_file():
        found = len(MERMAID_BLOCK.findall(
            spec.read_text(encoding="utf-8", errors="replace")))
        if found < REQUIRED_DIAGRAMS:
            problems.append({
                "artifact": "architecture-spec.md",
                "detail": f"{found} Mermaid block(s) in the specification, and "
                          f"{REQUIRED_DIAGRAMS} are required: network topology, "
                          f"delivery flow, environment promotion. They are embedded "
                          f"rather than attached so they diff in git and render in "
                          f"the pull request; a specification without them is one "
                          f"nobody can check the shape of."})
    return problems


# What a decision has to carry to be worth having recorded. Not how many: how many
# ADRs a project needs is a judgement about the project, and a gate demanding a
# number gets one written to satisfy it. This checks the shape of the ones that are
# there, because a decision with no rationale and no rejected alternative is a
# sentence naming a tool — which is what the specification would have said anyway.
DECISION_FIELDS = ("title", "rationale")


def check_decisions(state: dict) -> list[dict]:
    problems = []
    for i, d in enumerate(state.get("decisions", [])):
        if not isinstance(d, dict):
            problems.append({"decision": f"decisions[{i}]",
                             "detail": "is not an object"})
            continue
        label = str(d.get("id") or d.get("title") or f"decisions[{i}]")
        missing = [f for f in DECISION_FIELDS if not str(d.get(f, "")).strip()]
        rejected = d.get("alternatives_rejected")
        if not isinstance(rejected, list) or not rejected:
            missing.append("alternatives_rejected")
        elif any(not isinstance(a, dict) or not str(a.get("reason", "")).strip()
                 for a in rejected):
            missing.append("alternatives_rejected[].reason")
        if missing:
            problems.append({
                "decision": label,
                "detail": "has no " + ", ".join(f"`{m}`" for m in missing)
                          + ". The specification promises what was chosen, what was "
                            "rejected and why; a decision missing either half is a "
                            "record of the choice with the reasoning removed."})
    return problems


def evaluate(state: dict, artifacts: Path | None = None) -> dict:
    blocking_missing, blocking_partial, defaulted, open_in_blocking = [], [], [], []

    for domain, reason in BLOCKING.items():
        status = status_of(state, domain)
        if is_answered(state, domain):
            continue
        entry = {"domain": domain, "label": DOMAINS[domain],
                 "status": status, "why_it_blocks": reason}
        (blocking_partial if status == "partial" else blocking_missing).append(entry)

    for oq in state.get("open_questions", []):
        if not isinstance(oq, dict) or oq.get("status") == "resolved":
            continue
        domain = oq.get("domain")
        if domain in BLOCKING and not is_answered(state, domain):
            open_in_blocking.append({
                "id": oq.get("id"), "domain": domain,
                "question": oq.get("question"),
                "proposed_default": oq.get("proposed_default"),
                "owner": oq.get("owner"), "due": oq.get("due"),
            })

    for domain in DOMAINS:
        if domain in BLOCKING or is_answered(state, domain):
            continue
        defaulted.append({"domain": domain, "label": DOMAINS[domain],
                          "status": status_of(state, domain)})

    unowned = [
        {"id": oq.get("id"), "question": oq.get("question")}
        for oq in state.get("open_questions", [])
        if isinstance(oq, dict) and oq.get("status") != "resolved"
        and not (oq.get("owner") and oq.get("due"))
    ]

    # A domain marked complete whose gate keys are absent is a domain the other
    # gates silently cannot check. That is worse than an unanswered one, which at
    # least reports itself, so it blocks here too.
    key_problems = answer_key_problems(state)
    artifact_problems = check_artifacts(artifacts) if artifacts else []
    decision_problems = check_decisions(state)

    return {
        "blocking_unanswered": blocking_missing,
        "blocking_partial": blocking_partial,
        "will_be_defaulted": defaulted,
        "open_questions_in_blocking_domains": open_in_blocking,
        "open_questions_without_owner_or_date": unowned,
        "unreadable_answers": key_problems,
        "missing_artifacts": artifact_problems,
        "incomplete_decisions": decision_problems,
        "ok": (not blocking_missing and not blocking_partial and not key_problems
               and not artifact_problems and not unowned and not decision_problems),
    }


def render(result: dict) -> str:
    out: list[str] = []
    blockers = result["blocking_unanswered"] + result["blocking_partial"]

    if blockers:
        out.append("Not ready to emit a specification. "
                   f"{len(blockers)} blocking domain(s) unanswered:")
        out.append("")
        for e in blockers:
            out.append(f"  {e['domain']}  {e['label']}  [{e['status']}]")
            out.append(f"      blocks because: {e['why_it_blocks']}")
        out.append("")
    elif (not result.get("unreadable_answers") and not result.get("missing_artifacts")
          and not result.get("open_questions_without_owner_or_date")
          and not result.get("incomplete_decisions")):
        out.append("All seven blocking domains are answered.")
        out.append("")

    if result.get("unreadable_answers"):
        out.append("Domains marked complete whose answers the gates cannot read. "
                   "Every gate below reads answers by exact key, so a paraphrased "
                   "key is not a smaller problem than a missing answer — it is the "
                   "same problem without the warning:")
        out.append("")
        for e in result["unreadable_answers"]:
            out.append(f"  {e['domain']}")
            out.append(f"      {e['detail']}")
        out.append("")

    if result.get("missing_artifacts"):
        out.append("The specification's own documents. Every domain can be answered "
                   "and every other gate green while the output directory is empty, "
                   "so this is checked against the directory rather than the record "
                   "of what was decided:")
        out.append("")
        for e in result["missing_artifacts"]:
            out.append(f"  {e['artifact']}")
            out.append(f"      {e['detail']}")
        out.append("")

    if result.get("incomplete_decisions"):
        out.append("Decisions recorded without the reasoning behind them. Nothing "
                   "here demands a particular number of ADRs — that is a judgement "
                   "about the project — but a decision that is recorded has to say "
                   "what it rejected and why, or the reviewer cannot tell a choice "
                   "from a preference:")
        out.append("")
        for e in result["incomplete_decisions"]:
            out.append(f"  {e['decision']}")
            out.append(f"      {e['detail']}")
        out.append("")

    if result["open_questions_in_blocking_domains"]:
        out.append("Open questions sitting in blocking domains. An open question keeps "
                   "the interview moving; it does not make the specification final:")
        out.append("")
        for oq in result["open_questions_in_blocking_domains"]:
            out.append(f"  {oq['id']}  ({oq['domain']}) {oq['question']}")
            out.append(f"      proposed default: {oq['proposed_default']}")
            out.append(f"      owner: {oq['owner']}   due: {oq['due']}")
        out.append("")

    if result["open_questions_without_owner_or_date"]:
        out.append("Open questions missing an owner or a date. §4 lets the interview "
                   "move past an unknown precisely because the unknown leaves with a "
                   "name and a date attached; without both it is not deferred, it is "
                   "dropped, so this blocks:")
        for oq in result["open_questions_without_owner_or_date"]:
            out.append(f"  {oq['id']}  {oq['question']}")
        out.append("")

    if result["will_be_defaulted"]:
        out.append("Unanswered but non-blocking. These will be filled from "
                   "references/secure-defaults.md and must be recorded in the "
                   "specification as defaults, not as decisions:")
        for e in result["will_be_defaulted"]:
            out.append(f"  {e['domain']}  {e['label']}  [{e['status']}]")
        out.append("")

    return "\n".join(out).rstrip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state", help="path to discovery-state.json")
    ap.add_argument("--artifacts",
                    help="artifact output directory; when given, the emitted "
                         "documents and their diagrams are checked too")
    ap.add_argument("--draft", action="store_true",
                    help="report findings but always exit 0")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        state = load(args.state)
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    artifacts = Path(args.artifacts).expanduser() if args.artifacts else None
    if artifacts is not None and not artifacts.is_dir():
        print(f"error: --artifacts {artifacts} is not a directory. Checking nothing "
              f"is not a pass.", file=sys.stderr)
        return 2

    result = evaluate(state, artifacts)
    print(json.dumps(result, indent=2) if args.json else render(result))
    if args.draft:
        return 0
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""For each named compliance regime, list the controls not yet addressed.

Reach for this once domain 3 has recorded which regimes apply, and again before
emitting a specification. It reports gaps; it never reports compliance.

Inputs
    STATE        Path to discovery-state.json. Positional, required.
    --json       Emit findings as JSON.
    --regimes    Comma-separated regimes to check instead of reading them from the
                 state file. Useful for exploring what a regime would require before
                 the interview has committed to it.

Outputs
    Per regime: the obligations whose control is not yet addressed by an answered
    domain, each with the proposed control and the evidence an assessor would ask
    for. Then the regimes this build cannot speak to, with why.

    Exit 0  every named regime is sourced, every obligation is addressed, and every
            regime recorded as unmappable has an owner and a date against it.
    Exit 1  an obligation is unaddressed, a named regime is a stub this build cannot
            report on, or an unmappable regime has nobody accountable for it.
    Exit 2  the state file is missing or malformed, or the control map is unreadable.

What "addressed" means here, and what it does not
    An obligation counts as addressed when every domain it depends on is answered.
    That is a weak test on purpose, and it is important not to read more into it.
    It says the interview has *considered* the area, not that the resulting control
    satisfies the obligation. Nothing automated can make the second judgement.

    §8: never assert compliance. Map obligation to proposed control to evidence
    required, and mark verification as the owner's responsibility. So this gate's
    output is a worklist for a person, and its clean exit means "the interview
    covered the ground", never "you are compliant".

Why a stub regime fails rather than passing quietly
    Three regimes in the control map have no controls, because their primary text
    could not be read during the build (LIMITATIONS.md L1). An empty control list
    would otherwise render as "0 obligations unaddressed", which reads exactly like
    a clean bill of health. That is the most dangerous output this script could
    produce, so a named stub regime is a failure with the reason attached.

Why an unmappable regime is reported rather than refused
    A regime this build cannot map — a catalogue stub, or one with no control file
    here at all — used to have nowhere to live. Naming it in `regimes` failed the
    gate with no waiver path, so the instruction both SKILL.md and domain-03 give,
    "record it as an open question with an owner and continue", could not be
    followed: an honest state file naming SOC 2 could never go green. The observed
    outcome was the regime being moved out of the state file to get a green run,
    which left the generation stage with no obligation to implement.

    `03-compliance.answers.regimes_unmapped` is where it goes instead. The gate
    reports every entry prominently on every run and does not fail on it, provided
    an open question with an owner and a date names it. The refusal to invent a
    control list is untouched; what changes is that the honest answer now has
    somewhere to be recorded.

Why applicability is never inferred
    Several regimes bind only certain entity classes. The RBI Master Direction is
    addressed to a named list of entity types; the SEBI framework sets different
    requirements per classification. Whether a client falls inside is a question for
    the client, so where the control map records an applicability note this script
    prints it and does not resolve it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import (  # noqa: E402
    DOMAINS, StateError, is_answered, load, normalise_regime, regimes,
    unmapped_regimes,
)

CONTROL_MAP = Path(__file__).resolve().parent / "compliance_controls.json"


def _open_question_for(state: dict, regime: str) -> dict | None:
    """The open question that owns an unmappable regime, if one names it.

    Matching is on the regime's own words appearing in the question, its `regime`
    key, or its title. Punctuation and spacing are squashed out of both sides first,
    because `soc2` is the slug and "SOC 2 control mapping" is how anybody would
    actually write the question — matching the raw strings found neither. Beyond
    that it stays literal: a looser match would let one open question cover regimes
    nobody looked at.
    """
    squash = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())  # noqa: E731
    needle = squash(regime)
    if len(needle) < 3:
        return None
    for oq in state.get("open_questions", []):
        if not isinstance(oq, dict) or oq.get("status") == "resolved":
            continue
        haystack = squash(" ".join(str(oq.get(k, "")) for k in
                                   ("regime", "question", "title", "proposed_default")))
        if needle in haystack:
            return oq
    return None


def evaluate_unmapped(state: dict, control_map: dict) -> list[dict]:
    """Regimes recorded as unmappable, and whether each is owned by anybody.

    This exists because "record it as an open question with an owner and continue" —
    what SKILL.md and domain-03 both instruct for a regime this build cannot map —
    was impossible to follow: naming a stub regime in `regimes` failed the gate
    permanently, and the only lever was `--skip compliance`, which also switched off
    the PCI DSS checking that does work. The observed workaround was to move the
    regime out of the state file entirely, so the generation stage saw no obligation
    at all and wrote nothing for it. That is exactly the misreporting this gate
    exists to prevent.

    So an entry here is reported prominently and does not fail — provided somebody
    owns it by a date. Without an owner it is not a deferred obligation, it is a
    note, and a note is what the gate refuses.
    """
    entries = []
    for raw in unmapped_regimes(state):
        key = normalise_regime(raw)
        known = control_map["regimes"].get(key)
        oq = _open_question_for(state, raw) or (_open_question_for(state, key)
                                                if key != raw.strip().lower() else None)
        owned = bool(oq and oq.get("owner") and oq.get("due"))
        entries.append({
            "regime": raw,
            "title": known["title"] if known else raw,
            "citation": known["citation"] if known else None,
            "in_catalogue": known is not None,
            "reason": (known.get("not_sourced_reason") if known else
                       "not in this build's control map at all"),
            "open_question": ({"id": oq.get("id"), "owner": oq.get("owner"),
                               "due": oq.get("due")} if oq else None),
            "owned": owned,
        })
    return entries


def evaluate(state: dict, named: list[str], control_map: dict) -> dict:
    all_regimes = control_map["regimes"]
    checked, stubs, unknown = [], [], []

    for raw in named:
        key = normalise_regime(raw)
        entry = all_regimes.get(key)
        if entry is None:
            unknown.append(raw)
            continue
        if not entry.get("sourced"):
            stubs.append({
                "regime": key, "title": entry["title"],
                "citation": entry["citation"],
                "reason": entry.get("not_sourced_reason", "not sourced"),
            })
            continue

        unaddressed, addressed = [], []
        for control in entry["controls"]:
            blocking = [d for d in control["domains"] if not is_answered(state, d)]
            record = {
                "id": control["id"],
                "obligation": control["obligation"],
                "proposed_control": control["proposed_control"],
                "evidence_required": control["evidence"],
                "verify": control.get("verify"),
                "depends_on": [f"{d} {DOMAINS.get(d, '')}".strip() for d in control["domains"]],
                "unanswered_domains": [f"{d} {DOMAINS.get(d, '')}".strip() for d in blocking],
            }
            (unaddressed if blocking else addressed).append(record)

        checked.append({
            "regime": key, "title": entry["title"], "citation": entry["citation"],
            "applicability_note": entry.get("applicability_note"),
            "residency": entry.get("residency"),
            "addressed": addressed, "unaddressed": unaddressed,
        })

    unmapped = evaluate_unmapped(state, control_map)
    unowned_unmapped = [u for u in unmapped if not u["owned"]]

    ok = (not stubs and not unknown and not unowned_unmapped
          and all(not c["unaddressed"] for c in checked))
    return {"named": named, "checked": checked, "stubs": stubs,
            "unknown": unknown, "unmapped": unmapped, "ok": ok}


def render(r: dict) -> str:
    out: list[str] = []
    if not r["named"] and not r.get("unmapped"):
        return ("No compliance regime recorded in domain 3. Either none applies, in "
                "which case record that explicitly so a reviewer can see it was "
                "asked, or the domain is not finished.")

    for c in r["checked"]:
        out.append(f"{c['title']}")
        out.append(f"    source: {c['citation']}")
        if c["applicability_note"]:
            out.append(f"    applicability: {c['applicability_note']}")
        if c["residency"]:
            out.append(f"    carries a residency obligation: {c['residency']}")
        out.append("")
        if c["unaddressed"]:
            out.append(f"    {len(c['unaddressed'])} obligation(s) not yet addressed:")
            out.append("")
            for u in c["unaddressed"]:
                out.append(f"      [{u['id']}] {u['obligation']}")
                out.append(f"          proposed control: {u['proposed_control']}")
                out.append(f"          evidence required: {u['evidence_required']}")
                out.append(f"          waiting on: {', '.join(u['unanswered_domains'])}")
                out.append("")
        else:
            out.append(f"    All {len(c['addressed'])} obligations have their domains "
                       f"answered. That means the ground was covered, not that the "
                       f"controls satisfy the obligation — verification is the "
                       f"owner's responsibility, and where required, an auditor's.")
            out.append("")

        # Obligations whose primary text states a number. "Domains answered" is the
        # weakest possible claim about these — a seven-day log retention answers
        # domain 10 and misses a thirty-day root-cause window by three weeks — so the
        # ones with a figure behind them are printed whether or not they are
        # addressed, with what a reviewer has to check.
        with_numbers = [o for o in (c["addressed"] + c["unaddressed"]) if o.get("verify")]
        if with_numbers:
            out.append("    Obligations with a number in the primary text. The gate "
                       "checks that the domain was answered; whether the answer "
                       "meets the figure is a reading of the answer:")
            out.append("")
            for o in with_numbers:
                out.append(f"      [{o['id']}] {o['obligation']}")
                out.append(f"          verify: {o['verify']}")
                out.append("")

    if r["stubs"]:
        out.append("Named regimes this build cannot report on:")
        out.append("")
        for s in r["stubs"]:
            out.append(f"    {s['title']}")
            out.append(f"        {s['reason']}")
            out.append(f"        source to read: {s['citation']}")
            out.append("")
        out.append("    These are failures rather than silent passes. An empty control "
                   "list would render as zero obligations unaddressed, which reads "
                   "exactly like a clean bill of health.")
        out.append("")
        out.append("    To record one honestly and keep going, move it from `regimes` "
                   "to `regimes_unmapped` in the 03-compliance answers and raise an "
                   "open question with an owner and a date. It is then reported on "
                   "every run, visible to the generation stage, and does not block.")
        out.append("")

    if r["unknown"]:
        out.append("Recorded in `regimes` but not in the control map. Either the "
                   "spelling is wrong, or this is a real obligation this build cannot "
                   "map — in which case move it to `regimes_unmapped` with an open "
                   "question, rather than deleting it to get a green run:")
        for u in r["unknown"]:
            out.append(f"    {u}")
        out.append("")

    if r.get("unmapped"):
        out.append("Recorded as unmappable by this build. No control list is produced "
                   "for these, and none is invented. They are in scope and somebody "
                   "still owes an answer:")
        out.append("")
        for u in r["unmapped"]:
            out.append(f"    {u['title']}")
            out.append(f"        why unmapped: {u['reason']}")
            if u["citation"]:
                out.append(f"        source to read: {u['citation']}")
            if u["owned"]:
                oq = u["open_question"]
                out.append(f"        owned by: {oq['owner']}, due {oq['due']} "
                           f"({oq['id']})")
            else:
                out.append("        NO OWNER. An unmappable regime with nobody "
                           "accountable and no date is a note, not a deferral — "
                           "raise an open question in 03-compliance naming this "
                           "regime, with an owner and a due date.")
            out.append("")

    return "\n".join(out).rstrip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state")
    ap.add_argument("--regimes", help="comma-separated override")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        control_map = json.loads(CONTROL_MAP.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read {CONTROL_MAP}: {exc}", file=sys.stderr)
        return 2
    try:
        state = load(args.state)
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    named = ([x for x in args.regimes.split(",") if x.strip()]
             if args.regimes else regimes(state))
    r = evaluate(state, named, control_map)
    print(json.dumps(r, indent=2) if args.json else render(r))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

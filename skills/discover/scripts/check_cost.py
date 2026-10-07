#!/usr/bin/env python3
"""Check the cost estimate against the stated ceiling, and refuse invented prices.

Reach for this once the cost domain has an estimate in it, and again after any
change that adds or removes infrastructure. It does not price anything itself.

Inputs
    STATE            Path to discovery-state.json. Positional, required.
    --json           Emit findings as JSON.

Outputs
    The arithmetic, line by line, then the total against the ceiling, then — if the
    total is over — specific reductions drawn from what this project actually has,
    each with the trade-off it costs.

    Exit 0  the estimate is within the ceiling, or there is no ceiling yet and every
            line item is properly evidenced. Where items are unpriced, the verdict
            is printed as provisional rather than as "within".
    Exit 1  a line item carries a price with no stated assumptions, or the estimate
            exceeds the ceiling — including where the subtotal of the priced items
            alone already exceeds it, since pricing the rest can only add to it.
    Exit 2  the state file is missing or malformed.

Why a price without assumptions is a failure and not a warning
    §8: never invent pricing. Derive a range from stated assumptions, showing the
    arithmetic and the assumptions, or ask. A figure with no assumptions attached is
    indistinguishable from a number that was made up, and once it is in a document
    with a currency symbol next to it, somebody will plan against it. The only
    defence that works is refusing to carry it.

    An item nobody can price yet is not a problem — mark it `"unpriced": true` with a
    note, and it appears in the report as explicitly unpriced. §8 asks for unpriced
    items to be labelled, not guessed, and that is what the flag is for.

    An unpriced item makes the ceiling comparison provisional, not unavailable. The
    report says "the subtotal of the priced items is within the ceiling, with N
    unpriced" and never "within the ceiling", so the reassurance is exactly as
    strong as the evidence for it.

Why this script has no price list
    Any table of prices compiled today is wrong within months, differs by region,
    and cannot see committed-use or negotiated rates. A stale table that looks
    authoritative is worse than no table, because it removes the prompt to go and
    check. So the numbers come from whoever ran the interview, the assumptions come
    with them, and this script checks the arithmetic and the ceiling.

The two cost models
    `"model": "cloud"` — line items are monthly amounts. Total is their sum.
    `"model": "on-prem"` — line items may carry `capex` with `life_years`, and
    `opex_monthly`. A monthly equivalent is capex / (life_years x 12) + opex_monthly,
    so a capital purchase can be compared against a monthly ceiling at all. Power,
    cooling, rack space, bandwidth commits and hardware refresh belong in opex; if
    they are missing from an on-prem estimate the report says so, because leaving
    them out is how on-premises comes to look cheaper than it is.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import StateError, load, num  # noqa: E402

# ponytail: substring match over the serialised estimate. A line named
# "Top-of-rack switching" satisfies the "rack" key without there being any rack-space
# cost, so this under-reports. It is a prompt to think, not a gate — it never changes
# the exit code — so a keyword scan is proportionate. If it starts missing real gaps,
# give each estimate line an explicit `category` field and match on that instead.
ONPREM_EXPECTED_OPEX = {
    "power": "electricity for the hardware",
    "cooling": "cooling, which is usually a similar order to power",
    "rack": "rack space or colocation fees",
    "bandwidth": "transit or bandwidth commitment",
    "support": "hardware support contract or spares",
    "staff": "the operations time owned hardware requires",
}


# The cloud counterpart to ONPREM_EXPECTED_OPEX, and the more common omission of the
# two: an estimate is assembled from the things the interview named — a cluster, a
# database, some storage — and the charges that arrive because those things are in a
# cloud at all are the ones nobody thought to ask about. Each entry is
# (keywords, condition over the recorded answers, what is missing).
#
# ponytail: same substring scan over the serialised estimate as ONPREM_EXPECTED_OPEX,
# with the same ceiling — a line named "Gateway API controller" satisfies "gateway",
# so this under-reports. It never changes the exit code; it is a prompt to think. If
# it starts missing real gaps, give each line an explicit `category` and match on that.
CLOUD_EXPECTED = [
    (("nat", "egress", "transfer", "bandwidth"), "always",
     "outbound data transfer and the NAT or equivalent egress path. Private subnets "
     "are the secure default, and everything they reach out to bills per gigabyte"),
    (("cross-zone", "cross zone", "inter-az", "inter az", "transfer"), "multi_az",
     "cross-zone traffic between the zones this design spans, which is charged in "
     "both directions"),
    (("log", "metric", "trace", "ingest", "observability", "monitoring"), "observability",
     "log, metric and trace ingestion and retention, routinely one of the largest "
     "lines and the one that scales with traffic rather than with the fleet"),
    (("backup", "snapshot", "restore"), "backups",
     "backup and snapshot storage, which is charged separately from the volume it "
     "protects and accumulates for as long as the retention says"),
    (("standby", "dr ", "replica", "secondary"), "dr_region",
     "the standing cost of the DR region — a warm or active copy is a second bill, "
     "not a rounding error on the first"),
    (("load balancer", "alb", "nlb", "ingress", "gateway", "cloudfront", "cdn"),
     "ingress",
     "the load balancer or ingress itself, which bills per hour and per unit of "
     "traffic on top of the compute behind it"),
]


def _cloud_gaps(state: dict, items: list) -> list[str]:
    """Categories this project will be billed for that its estimate does not mention.

    Every condition reads something the interview actually recorded, so a project
    that never got as far as observability is not nagged about log ingest.
    """
    d = state.get("domains", {})

    def answered(domain: str) -> bool:
        return (d.get(domain, {}) or {}).get("status") in {"complete", "partial"}

    cloud = (d.get("04-cloud", {}).get("answers") or {})
    compute = (d.get("06-compute", {}).get("answers") or {})
    datadr = (d.get("12-data-dr", {}).get("answers") or {})
    az = num(cloud.get("az_spread"))
    holds = {
        "always": True,
        "multi_az": compute.get("multi_az") is True or (az is not None and az >= 2),
        "observability": answered("10-observability"),
        "backups": answered("12-data-dr"),
        "dr_region": bool(cloud.get("dr_region") or datadr.get("dr_region")),
        "ingress": answered("07-networking"),
    }
    blob = json.dumps(items).lower()
    return [note for keys, condition, note in CLOUD_EXPECTED
            if holds.get(condition) and not any(k in blob for k in keys)]


def _levers(state: dict) -> list[tuple[str, str]]:
    """Reductions that apply to *this* project, with what each costs.

    Generic advice is easy to write and easy to ignore. A lever the reader can see
    applies to their own topology is one they can act on, so each is gated on
    something the interview actually recorded.
    """
    d = state.get("domains", {})

    def ans(domain, key, default=None):
        return (d.get(domain, {}).get("answers") or {}).get(key, default)

    envs = [e for e in (ans("05-environments", "environments") or []) if isinstance(e, str)]
    nonprod = [e for e in envs if not e.lower().startswith(("prod", "live"))]
    platform = str(ans("06-compute", "platform", "") or "").lower()
    tier = str(ans("12-data-dr", "dr_tier", "") or "").lower()
    az = ans("04-cloud", "az_spread")
    regimes = [str(r).lower() for r in (ans("03-compliance", "regimes") or [])]
    onprem = str(state.get("cost", {}).get("model", "cloud")).lower() != "cloud"

    out: list[tuple[str, str]] = []

    if nonprod and not onprem:
        out.append((
            f"Run {', '.join(nonprod)} on spot or preemptible capacity.",
            "Saves roughly 60-70% of that compute at list price. Costs you "
            "interruptions, so anything with a long-running job or in-memory state "
            "needs to tolerate being killed. Not appropriate for production."))
        out.append((
            f"Shut {', '.join(nonprod)} down outside working hours.",
            "A 12-hour weekday schedule removes about 65% of the running hours. "
            "Costs you a cold environment when someone works late, and needs the "
            "shutdown to be automated or it will not happen."))
    if nonprod and "kube" in platform or nonprod and any(
            k in platform for k in ("eks", "gke", "aks", "k3s", "rke2")):
        out.append((
            f"Share one cluster across {', '.join(nonprod)} with namespace isolation, "
            f"keeping production on its own.",
            "Removes a control-plane charge and a node floor per environment. Costs "
            "you a weaker boundary between non-production environments and a shared "
            "failure domain for them."
            + (" Not available if a compliance regime requires segmentation."
               if regimes else "")))
    if az and isinstance(az, (int, float)) and az >= 3 and nonprod:
        out.append((
            "Reduce non-production to a single availability zone.",
            "Removes cross-zone data transfer and the duplicate node floor. Costs "
            "you the ability to test zone-failure behaviour outside production."))
    if tier in {"active-active", "warm", "warm-standby"}:
        out.append((
            f"Step the DR posture down from {tier} to pilot light.",
            "Removes the standing duplicate of the running environment. Costs you "
            "recovery time, so it only works if the RTO genuinely allows it. Check "
            "the contradiction gate after changing this."))
    if not onprem:
        out.append((
            "Commit to Savings Plans or committed-use discounts on the steady-state "
            "baseline only.",
            "Typically 20-40% off the committed portion. Costs you flexibility for "
            "one to three years, so commit to the floor you are confident about and "
            "leave the peak on demand."))
        out.append((
            "Reduce log and metric retention, and drop high-cardinality labels.",
            "Observability is usually among the largest single lines, and retention "
            "is the multiplier. Costs you history during an investigation, and a "
            "compliance regime may set a floor you cannot go below."))
    else:
        out.append((
            "Extend the hardware refresh period before buying.",
            "Amortising over five years instead of three lowers the monthly "
            "equivalent by about 40%. Costs you a longer tail of aging hardware and "
            "a higher failure rate late in life."))
    return out


def evaluate(state: dict) -> dict:
    """Assess the estimate. See the module docstring for the two cost models.

    One case deserves naming because it is easy to get wrong: an empty estimate.
    With no line items there is nothing to compare against the ceiling, and the
    first version of this script returned a pass — the same shape of mistake as a
    compliance regime with no controls reporting zero unaddressed obligations. So
    if the cost domain has been marked answered and there are still no line items,
    that is a failure: the domain was closed without anything actually being
    estimated.
    """
    cost = state.get("cost", {}) or {}
    model = str(cost.get("model", "cloud")).lower()
    currency = cost.get("currency", "")
    period = cost.get("period", "monthly")
    ceiling = cost.get("ceiling")
    items = cost.get("estimate", []) or []

    lines, problems, unpriced = [], [], []
    total_low = total_high = 0.0

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            problems.append({"item": f"estimate[{idx}]",
                             "problem": "not an object"})
            continue
        name = item.get("item", f"estimate[{idx}]")
        assumptions = item.get("assumptions") or []

        if item.get("unpriced"):
            unpriced.append({"item": name, "note": item.get("note", "")})
            continue

        low, high = item.get("low"), item.get("high")
        if low is None and high is None:
            problems.append({"item": name,
                             "problem": "has neither a price nor the unpriced flag"})
            continue
        if not assumptions:
            problems.append({
                "item": name,
                "problem": "carries a price with no stated assumptions. Either state "
                           "what the number assumes, or mark it unpriced. A figure "
                           "with no assumptions cannot be told apart from a guess, "
                           "and somebody will plan against it."})
            continue

        raw_low = low if low is not None else high
        raw_high = high if high is not None else low
        low, high = num(raw_low), num(raw_high)
        if low is None or high is None:
            # The state file is written from a spoken conversation, so "$73" and
            # "4,000 USD" reach here routinely. num() handles those; anything it
            # cannot read is refused with the value quoted, because a price the
            # gate cannot parse is a price it must not silently carry.
            bad = raw_low if low is None else raw_high
            problems.append({
                "item": name,
                "problem": f"has a price this gate cannot read: {bad!r}. Give a "
                           f"number, or mark the item unpriced with a note."})
            continue
        monthly_low, monthly_high = low, high
        detail = None

        if model != "cloud":
            capex = item.get("capex")
            life = item.get("life_years")
            opex = num(item.get("opex_monthly")) or 0.0
            if capex is not None:
                capex_n, life_n = num(capex), num(life)
                if not life or life_n in (None, 0):
                    problems.append({
                        "item": name,
                        "problem": "has capex but no usable life_years, so it "
                                   "cannot be amortised into a monthly equivalent."})
                    continue
                if capex_n is None:
                    problems.append({
                        "item": name,
                        "problem": f"has a capex this gate cannot read: {capex!r}."})
                    continue
                amortised = capex_n / (life_n * 12.0)
                monthly_low = monthly_high = amortised + opex
                detail = (f"{capex} capex over {life}y = {amortised:.2f}/month, "
                          f"plus {opex:.2f}/month running")

        total_low += monthly_low
        total_high += monthly_high
        lines.append({"item": name, "low": monthly_low, "high": monthly_high,
                      "assumptions": assumptions, "arithmetic": detail})

    domain_status = (state.get("domains", {}).get("13-cost", {}) or {}).get("status")
    if not items and domain_status in {"complete", "not-applicable"}:
        problems.append({
            "item": "the estimate itself",
            "problem": f"domain 13 is marked {domain_status!r} but cost.estimate is "
                       f"empty, so nothing was estimated. Either add the line items "
                       f"with their assumptions, or record why this project needs no "
                       f"cost estimate. An empty estimate that returns a pass is a "
                       f"specification with no costing that looks costed."})

    onprem_gaps, cloud_gaps = [], []
    if model != "cloud" and items:
        blob = json.dumps(items).lower()
        onprem_gaps = [note for key, note in ONPREM_EXPECTED_OPEX.items()
                       if key not in blob]
    elif model == "cloud" and items:
        cloud_gaps = _cloud_gaps(state, items)

    # A rejected line item is excluded from the total, so any verdict against the
    # ceiling would be computed over an incomplete estimate. The first version of
    # this script printed "Within the stated ceiling" while silently omitting a
    # 410/month database, which is worse than printing nothing: it is a reassuring
    # number that is not true. So no ceiling verdict is reached while any item is
    # rejected.
    # Unpriced items are excluded from the total, so a subtotal compared against a
    # ceiling is not the whole estimate. The first fix for that suppressed the
    # comparison entirely, which was all-or-nothing: one unpriced line out of twelve
    # threw away the signal from the other eleven, and the honest workaround was to
    # price everything, which only happens when the interviewer chooses to.
    #
    # The middle ground keeps both. A subtotal already over the ceiling is a real
    # failure — pricing the rest can only add to it — so that blocks. A subtotal
    # under the ceiling is reported as provisional, with the count of what is
    # missing from it, and never as "within".
    incomplete = bool(problems)
    provisional = bool(unpriced) and not problems
    # A ceiling of "4,000 USD" is as likely as 4000, and an unreadable one must
    # become a stated problem rather than a crash — or, worse, a silently absent
    # ceiling that lets any total pass.
    if ceiling is not None:
        ceiling_n = num(ceiling)
        if ceiling_n is None:
            problems.append({
                "item": "ceiling",
                "problem": f"the budget ceiling cannot be read as a number: "
                           f"{ceiling!r}. Nothing can be checked against it."})
            incomplete = True
        ceiling = ceiling_n
    over = (not incomplete) and ceiling is not None and total_low > ceiling
    tight = ((not incomplete) and ceiling is not None and not over
             and total_high > ceiling)

    return {
        "model": model, "currency": currency, "period": period,
        "ceiling": ceiling, "lines": lines, "unpriced": unpriced,
        "problems": problems, "total_low": round(total_low, 2),
        "total_high": round(total_high, 2), "over_ceiling": over,
        "within_low_over_high": tight,
        "total_incomplete": incomplete,
        # Machine-visible so a caller can tell a real "within ceiling" from a
        # refusal to judge. An unpriced item is permitted by design, so it does not
        # make the gate fail — it makes the ceiling verdict unavailable, which is a
        # different thing and has to be readable as such.
        "provisional": provisional,
        "unpriced_count": len(unpriced),
        "ceiling_verdict": (
            "none-rejected" if problems else
            "over" if over else
            "at-risk" if tight else
            ("provisional-within" if provisional else "within")
            if ceiling is not None and lines else
            "no-ceiling"
        ),
        "onprem_missing_opex": onprem_gaps,
        "cloud_missing_charges": cloud_gaps,
        "reductions": [{"lever": a, "trade_off": b} for a, b in _levers(state)]
                      if (over or tight) else [],
        "ok": not problems and not over,
    }


def render(r: dict) -> str:
    cur, per = r["currency"], r["period"]
    out: list[str] = []

    if r["problems"]:
        out.append(f"Estimate rejected. {len(r['problems'])} line item(s) cannot be "
                   f"carried:")
        out.append("")
        for p in r["problems"]:
            out.append(f"  {p['item']}")
            out.append(f"      {p['problem']}")
        out.append("")

    if r["lines"]:
        out.append(f"Estimate ({r['model']} model, {per}, {cur}):")
        out.append("")
        for ln in r["lines"]:
            span = (f"{ln['low']:.2f}" if ln["low"] == ln["high"]
                    else f"{ln['low']:.2f} to {ln['high']:.2f}")
            out.append(f"  {ln['item']}: {span}")
            if ln["arithmetic"]:
                out.append(f"      arithmetic: {ln['arithmetic']}")
            for a in ln["assumptions"]:
                out.append(f"      assumes: {a}")
        out.append("")
        total = (f"{r['total_low']:.2f}" if r["total_low"] == r["total_high"]
                 else f"{r['total_low']:.2f} to {r['total_high']:.2f}")
        label = ("Total of the items that could be carried"
                 if r.get("total_incomplete") else "Total")
        if r["unpriced"] and not r["problems"]:
            label = f"Subtotal of the {len(r['lines'])} priced item(s) only"
        out.append(f"  {label}: {total} {cur} {per}")
        if r["ceiling"] is not None:
            out.append(f"  Ceiling: {r['ceiling']:.2f} {cur} {per}")
        out.append("")

    if r["unpriced"]:
        out.append("Explicitly unpriced — labelled rather than guessed:")
        for u in r["unpriced"]:
            out.append(f"  {u['item']}" + (f" — {u['note']}" if u["note"] else ""))
        out.append("")

    if r["onprem_missing_opex"]:
        out.append("On-premises estimate appears to be missing recurring costs. "
                   "Leaving these out is how owned hardware comes to look cheaper "
                   "than it is:")
        for note in r["onprem_missing_opex"]:
            out.append(f"  no line for {note}")
        out.append("")

    if r.get("cloud_missing_charges"):
        out.append("Charges this topology will attract that the estimate does not "
                   "mention. Not a failure — the gate cannot know what a line item "
                   "was meant to include — but each one has surprised somebody's "
                   "first invoice:")
        for note in r["cloud_missing_charges"]:
            out.append(f"  no line for {note}")
        out.append("")

    if r.get("total_incomplete"):
        out.append(f"No verdict against the ceiling: {len(r['problems'])} line "
                   f"item(s) were rejected, so the total above is not the whole "
                   f"estimate. Fix them and run this again — a partial total "
                   f"compared to a ceiling reads as reassurance that has not been "
                   f"earned.")
    elif r["over_ceiling"]:
        out.append("Over the ceiling even at the low end."
                   + (f" That verdict holds whatever the {r['unpriced_count']} "
                      f"unpriced item(s) turn out to cost — pricing them can only "
                      f"add to the total." if r.get("provisional") else ""))
    elif r["within_low_over_high"]:
        out.append("Within the ceiling at the low end, over it at the high end. "
                   "Treat the ceiling as at risk rather than met."
                   + (f" And {r['unpriced_count']} item(s) are still unpriced, so "
                      f"the high end is a floor rather than a high end."
                      if r.get("provisional") else ""))
    elif r.get("provisional") and r["ceiling"] is not None and r["lines"]:
        out.append(f"Provisional: the subtotal of the priced items is within the "
                   f"ceiling, with {r['unpriced_count']} item(s) unpriced and "
                   f"therefore outside it. This is not 'within the ceiling' — it is "
                   f"the part of the estimate that exists, compared against the "
                   f"whole ceiling. Price the rest, or say in the specification what "
                   f"the comparison excludes.")
    elif r["ceiling"] is None and r["lines"]:
        out.append("No ceiling recorded, so there is nothing to check the total "
                   "against. Ask what the monthly limit is.")
    elif r["lines"]:
        out.append("Within the stated ceiling.")

    if r["reductions"]:
        out.append("")
        out.append("Reductions that apply to this topology, each with what it costs:")
        out.append("")
        for red in r["reductions"]:
            out.append(f"  {red['lever']}")
            out.append(f"      trade-off: {red['trade_off']}")

    return "\n".join(out).rstrip() or "No cost estimate recorded yet."


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        state = load(args.state)
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    r = evaluate(state)
    print(json.dumps(r, indent=2) if args.json else render(r))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Prove every gate still catches the thing it exists to catch.

Run it after changing any script in this directory:

    python3 skills/discover/scripts/selftest.py

Exit 0  every gate passed its clean case and failed its violating case.
Exit 1  a gate let a violation through, or rejected a clean state.

Why fixture pairs and not assertions on output
    A gate that never fires is indistinguishable from a gate that always passes, and
    the second is the failure mode that matters — it reads as a clean bill of health.
    So every gate is run twice: once against a state it must accept, once against a
    state it must reject. Checking the wording of the report would break on every
    rewording; checking the exit code breaks only when the behaviour changes.

Why the fixtures are built here rather than committed
    They are small, and a fixture tree drifts from the schema it is supposed to
    pin. Built from `CLEAN` by mutation, each violating case states in one place
    exactly which field makes it a violation.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

DOMAINS = [
    "01-product", "02-app-shape", "03-compliance", "04-cloud", "05-environments",
    "06-compute", "07-networking", "08-identity", "09-delivery", "10-observability",
    "11-security", "12-data-dr", "13-cost", "14-team",
]

# A state every gate must accept: answered throughout, internally consistent, priced
# with assumptions, under its ceiling, and naming a regime whose text was sourced.
CLEAN: dict = {
    "schema_version": "1",
    "project": {"name": "Selftest", "slug": "selftest",
                "started": "2026-01-01", "updated": "2026-01-01"},
    "domains": {d: {"status": "complete", "answers": {}} for d in DOMAINS},
    "open_questions": [],
    "decisions": [],
    "waivers": [],
    "detected": {},
    "cost": {
        "currency": "USD", "period": "monthly", "ceiling": 20000, "model": "cloud",
        "estimate": [
            {"item": "EKS control plane",
             "assumptions": ["one cluster", "eu-west-1", "on-demand list price"],
             "low": 73, "high": 73, "unpriced": False},
            {"item": "Object storage",
             "assumptions": ["500 GB", "standard tier"],
             "low": 12, "high": 20, "unpriced": False},
        ],
    },
}
CLEAN["domains"]["01-product"]["answers"] = {"sla": 99.5}
CLEAN["domains"]["03-compliance"]["answers"] = {"regimes": ["gdpr"], "residency": "eu"}
CLEAN["domains"]["04-cloud"]["answers"] = {"provider": "aws", "region": "eu-west-1"}
CLEAN["domains"]["06-compute"]["answers"] = {"platform": "managed kubernetes (eks)"}
CLEAN["domains"]["05-environments"]["answers"] = {"environments": ["dev", "prod"]}
# No `policy_pre_apply` here deliberately: the generation harness builds its fixtures
# from this state, and naming a scanner would make its runs depend on which scanners
# the machine happens to have installed. The scanner paths are exercised there.
CLEAN["domains"]["09-delivery"]["answers"] = {"iac": "Terraform with Terragrunt"}
CLEAN["domains"]["12-data-dr"]["answers"] = {"rto": "4h"}
CLEAN["domains"]["14-team"]["answers"] = {"headcount": 8, "pager": "24x7"}


def mutate(**domain_answers) -> dict:
    """CLEAN with specific domain answers replaced. Everything else stays valid, so a
    failure names one cause rather than a fixture that is wrong in several ways."""
    state = copy.deepcopy(CLEAN)
    for domain, answers in domain_answers.items():
        state["domains"][domain.replace("_", "-")]["answers"].update(answers)
    return state


def unanswer(domain: str) -> dict:
    state = copy.deepcopy(CLEAN)
    state["domains"][domain]["status"] = "not-started"
    return state


def unpriced_without_assumptions() -> dict:
    state = copy.deepcopy(CLEAN)
    state["cost"]["estimate"].append(
        {"item": "Managed database", "assumptions": [], "low": 400, "high": 400})
    return state


def over_ceiling() -> dict:
    state = copy.deepcopy(CLEAN)
    state["cost"]["ceiling"] = 50
    return state


def paraphrased_iac_key() -> dict:
    """Domain 9a's answers under keys the generation skill does not read.

    The one that matters is `policy_pre_apply`: recorded as `scanner`, check_iac.py
    reads an empty string and reports that the specification named no policy scanner,
    which is a sentence about a decision nobody made.
    """
    state = copy.deepcopy(CLEAN)
    state["domains"]["09-delivery"]["answers"] = {
        "tool": "Terraform with Terragrunt", "scanner": "Checkov in CI"}
    return state


def unowned_open_question() -> dict:
    """A real unknown, deferred to nobody. §4 trades blocking for an owner and a
    date; without them the question has left the conversation rather than been
    parked."""
    state = copy.deepcopy(CLEAN)
    state["open_questions"] = [{
        "id": "OQ-1", "domain": "12-data-dr",
        "question": "Does the analytics store need point-in-time recovery?",
        "proposed_default": "Daily snapshots only", "status": "open"}]
    return state


def paraphrased_answer_keys() -> dict:
    """The gate keys 14-team needs, renamed to plausible synonyms. Every answer is
    still there and still correct; only the keys changed, which used to be enough to
    make the contradiction gate pass a two-person self-hosted control plane."""
    state = copy.deepcopy(CLEAN)
    state["domains"]["14-team"]["answers"] = {"team_size": 8, "on_call": "24x7"}
    return state


# (gate script, description, clean state, violating state, what the violation is)
CASES = [
    ("check_completeness.py", "a blocking domain is unanswered",
     CLEAN, unanswer("13-cost"), "13-cost set back to not-started"),
    ("check_contradictions.py", "two answers cannot both be satisfied",
     CLEAN, mutate(**{"06-compute": {"platform": "self-hosted kubeadm"},
                      "14-team": {"headcount": 2}}),
     "self-hosted control plane with a team of two"),
    ("check_compliance.py", "a named regime is a stub this build cannot report on",
     CLEAN, mutate(**{"03-compliance": {"regimes": ["hipaa"]}}),
     "hipaa, whose primary text was never sourced"),
    ("check_cost.py", "a price carries no assumptions",
     CLEAN, unpriced_without_assumptions(), "a $400 line item with assumptions: []"),
    ("check_cost.py", "the estimate exceeds the ceiling",
     CLEAN, over_ceiling(), "ceiling dropped to $50"),
    ("check_completeness.py", "a complete domain's answers are unreadable by key",
     CLEAN, paraphrased_answer_keys(),
     "14-team answering under `team_size`/`on_call` instead of `headcount`/`pager`"),
    ("check_completeness.py", "the generation skill's keys are paraphrased",
     CLEAN, paraphrased_iac_key(),
     "09-delivery answering under `tool`/`scanner` instead of `iac`/`policy_pre_apply`"),
    ("check_completeness.py", "an open question has no owner or date",
     CLEAN, unowned_open_question(), "OQ-1 with a proposed default and nobody to ask"),
]


def check_regime_vocabulary() -> tuple[bool, str]:
    """RESIDENCY_REGIMES must agree with compliance_controls.json, the sourced artifact.

    They disagreed once: ifsca was listed as carrying an India residency obligation
    while the control map recorded null for it. Nothing caught that, because the two
    tables live in different files and neither reads the other.
    """
    sys.path.insert(0, str(HERE))
    import json as _json
    from check_contradictions import RESIDENCY_REGIMES
    from _state import normalise_regime

    controls = _json.loads((HERE / "compliance_controls.json").read_text(
        encoding="utf-8"))["regimes"]
    problems = []
    for slug, (geo, _why) in RESIDENCY_REGIMES.items():
        if slug != normalise_regime(slug):
            problems.append(f"{slug!r} is not a canonical slug")
        elif slug not in controls:
            problems.append(f"{slug!r} is not in the control map")
        elif controls[slug].get("residency") != geo:
            problems.append(
                f"{slug!r} claims {geo!r} but the control map says "
                f"{controls[slug].get('residency')!r}")
    # And the reverse: a regime the control map gives a residency must be checkable.
    for slug, spec in controls.items():
        if spec.get("residency") and slug not in RESIDENCY_REGIMES:
            problems.append(f"the control map gives {slug!r} a residency obligation "
                            f"that the contradiction gate cannot check")
    if problems:
        return False, "FAIL  residency tables disagree — " + "; ".join(problems)
    return True, ("ok    RESIDENCY_REGIMES agrees with compliance_controls.json")


def check_geo_tables() -> tuple[bool, str]:
    """The residency geography tables have to hold together on their own.

    Three properties, each of which was violated at some point by a table that read
    fine: containment with a cycle would hang `_ancestry`; a regime whose geography
    is not a node in the containment tree can never be satisfied by any region, so
    the gate's only accepted answer would be a wrong one; and a country pattern
    placed after the continent pattern that swallows it is the defect that made
    `ap-southeast-2` classify as `apac` and forced an Australian project to record
    `"residency": "apac"` — which is not the obligation and permits Singapore.
    """
    sys.path.insert(0, str(HERE))
    from check_contradictions import (  # noqa: PLC0415
        GEO_PARENTS, REGION_GEO, RESIDENCY_REGIMES, _ancestry, _geo_of, _known_geo,
    )

    problems = []
    for geo in GEO_PARENTS:
        chain, seen = [geo], {geo}
        node = geo
        while node in GEO_PARENTS:
            node = GEO_PARENTS[node]
            if node in seen:
                problems.append(f"containment cycle through {geo!r}: "
                                + " -> ".join(chain + [node]))
                break
            chain.append(node)
            seen.add(node)

    for slug, (geo, _why) in RESIDENCY_REGIMES.items():
        if not _known_geo(geo):
            problems.append(f"regime {slug!r} names geography {geo!r}, which is not a "
                            f"node in GEO_PARENTS, so no region can ever satisfy it")

    # Every geography a region maps to must be placeable in the tree, or the
    # containment test silently returns False for it.
    for _pattern, geo in REGION_GEO:
        if not _known_geo(geo) and geo != "global":
            problems.append(f"REGION_GEO maps a region to {geo!r}, which GEO_PARENTS "
                            f"does not contain")

    # A country region must resolve to its country, not to the continent above it.
    # These are the three providers' spellings of the same place.
    for region, want in (("ap-southeast-2", "australia"), ("australiaeast", "australia"),
                         ("australia-southeast1", "australia"),
                         ("ap-south-1", "india"), ("centralindia", "india"),
                         ("ca-central-1", "canada"), ("eu-west-2", "uk"),
                         ("eu-west-1", "ireland"), ("us-east-1", "us")):
        got = _geo_of(region)
        if got != want:
            problems.append(f"{region!r} classifies as {got!r}, wanted {want!r} — a "
                            f"continent pattern is shadowing the country one")

    if problems:
        return False, "FAIL  residency geography tables — " + "; ".join(problems)
    return True, ("ok    geography containment is acyclic, every regime's geography "
                  "is reachable, and country regions beat continent patterns")


def run(argv: list[str]) -> int:
    return subprocess.run([sys.executable] + argv,
                          capture_output=True, text=True).returncode


def write(tmp: Path, name: str, state: dict) -> Path:
    p = tmp / name
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return p


def check_secrets(tmp: Path) -> tuple[bool, str]:
    """The one gate whose fixtures are files rather than state. Skipped, loudly, when
    gitleaks is absent: the gate itself exits 3 there, which is neither pass nor fail."""
    if shutil.which("gitleaks") is None:
        return True, "SKIP  scan_secrets.py — gitleaks not installed (the gate would exit 3)"

    clean = tmp / "artifacts-clean"
    clean.mkdir()
    (clean / "architecture-spec.md").write_text(
        "# Spec\n\nThe account id lives in `root.hcl`; it is referenced, never copied here.\n",
        encoding="utf-8")
    dirty = tmp / "artifacts-dirty"
    dirty.mkdir()
    (dirty / "architecture-spec.md").write_text(
        "# Spec\n\nAWS account 123456789012, registry "
        "123456789012.dkr.ecr.ap-south-1.amazonaws.com\n",
        encoding="utf-8")

    # Downloaded, never committed, and full of other people's example account ids.
    # One `terraform init` in a scanned tree used to put a dozen unactionable
    # findings from third-party modules ahead of the reader's own.
    vendored = clean / ".terraform" / "modules" / "vpc"
    vendored.mkdir(parents=True)
    (vendored / "main.tf").write_text(
        "# arn:aws:iam::123456789012:role/example from somebody else's module\n",
        encoding="utf-8")

    # Generated and committed, and full of hex digests. A twelve-digit run inside
    # one is not an account id, and reporting it on every lock file in every
    # Terraform tree is how a `review` pattern gets ignored.
    (clean / ".terraform.lock.hcl").write_text(
        'provider "registry.terraform.io/hashicorp/aws" {\n'
        '  version = "6.64.0"\n'
        '  hashes = [\n'
        '    "zh:17324d4335a7a7ac01cc23eded530775606680ff53b47cb74a3cb95d1121f836",\n'
        '    "zh:6eb29ead5a4aca3b1f35812e7e8c75419180e1928e479b458f206861277736db",\n'
        "  ]\n}\n", encoding="utf-8")

    ok_clean = run([str(HERE / "scan_secrets.py"), str(clean)]) == 0
    ok_dirty = run([str(HERE / "scan_secrets.py"), str(dirty)]) == 1
    if ok_clean and ok_dirty:
        return True, ("ok    scan_secrets.py — an account id and an ECR host are "
                      "caught; `.terraform/` and lock-file hashes are not")
    detail = []
    if not ok_clean:
        detail.append("rejected a clean artifact directory")
    if not ok_dirty:
        detail.append("PASSED an artifact containing an account id and ECR host")
    return False, "FAIL  scan_secrets.py — " + "; ".join(detail)


def main() -> int:
    lines, failed = [], 0
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        for i, (script, what, clean, violating, why) in enumerate(CASES):
            clean_path = write(tmp, f"clean-{i}.json", clean)
            bad_path = write(tmp, f"violating-{i}.json", violating)

            clean_code = run([str(HERE / script), str(clean_path)])
            bad_code = run([str(HERE / script), str(bad_path)])

            problems = []
            if clean_code != 0:
                problems.append(f"rejected a clean state (exit {clean_code})")
            if bad_code != 1:
                problems.append(f"did not catch {why} (exit {bad_code}, wanted 1)")
            if problems:
                failed += 1
                lines.append(f"FAIL  {script} — {what}: " + "; ".join(problems))
            else:
                lines.append(f"ok    {script} — {what}")

        ok, line = check_secrets(tmp)
        lines.append(line)
        if not ok:
            failed += 1

        # B5: an all-zeros account in a mock ARN is a placeholder, and a finding
        # that names `terragrunt.hcl` without its directory names no file at all in
        # a stack where every unit has one.
        mocks = tmp / "mock-stack" / "live" / "prod" / "data"
        mocks.mkdir(parents=True)
        (mocks / "terragrunt.hcl").write_text(
            'mock = "arn:aws:secretsmanager:eu-west-1:000000000000:secret:mock"\n',
            encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(HERE / "scan_secrets.py"), str(tmp / "mock-stack")],
            capture_output=True, text=True)
        placeholder_ok = ("needs a look" in proc.stdout
                          and "definite" not in proc.stdout
                          and "live/prod/data/terragrunt.hcl" in proc.stdout)
        if placeholder_ok:
            lines.append("ok    scan_secrets.py — an all-zeros account reads as a "
                         "placeholder, and paths are relative to the scanned root")
        else:
            failed += 1
            lines.append(f"FAIL  scan_secrets.py — placeholder account or path "
                         f"rendering\n{proc.stdout}")

        ok, line = check_regime_vocabulary()
        lines.append(line)
        if not ok:
            failed += 1

        ok, line = check_geo_tables()
        lines.append(line)
        if not ok:
            failed += 1

        # C1: a country-level obligation used to have no accepted answer at all.
        # `ap-southeast-2` fell through to `apac`, so recording the real obligation
        # produced two hard errors and the only value that passed was `apac` —
        # which permits Singapore, Tokyo and Mumbai.
        residency_cases = [
            ("australia", "ap-southeast-2", None, 0, "the obligation and the region agree"),
            ("australia", "ap-southeast-1", None, 1, "Singapore is apac but not Australia"),
            ("apac", "ap-southeast-2", None, 0, "a country satisfies its continent"),
            ("australia", "us-east-1", False, 0, "a preference warns rather than blocks"),
            ("australia", "us-east-1", None, 1, "an obligation blocks"),
        ]
        for i, (residency, region, legal, want, why) in enumerate(residency_cases):
            s = copy.deepcopy(CLEAN)
            s["domains"]["04-cloud"]["answers"]["region"] = region
            answers = {"regimes": [], "residency": residency}
            if legal is not None:
                answers["residency_is_legal_requirement"] = legal
            s["domains"]["03-compliance"]["answers"] = answers
            code = run([str(HERE / "check_contradictions.py"),
                        str(write(tmp, f"residency-{i}.json", s))])
            if code == want:
                lines.append(f"ok    check_contradictions.py — {why}")
            else:
                failed += 1
                lines.append(f"FAIL  check_contradictions.py — {why}: exit {code}, "
                             f"wanted {want}")

        # An explicit list of permitted regions needs no geography table, and is the
        # one form of this answer that cannot be wrong.
        for regions, region, want in ((["ap-southeast-2"], "ap-southeast-2", 0),
                                      (["ap-southeast-2"], "ap-southeast-1", 1)):
            s = copy.deepcopy(CLEAN)
            s["domains"]["04-cloud"]["answers"]["region"] = region
            s["domains"]["03-compliance"]["answers"] = {"regimes": [], "residency": regions}
            code = run([str(HERE / "check_contradictions.py"),
                        str(write(tmp, f"regionlist-{region}.json", s))])
            if code != want:
                failed += 1
                lines.append(f"FAIL  check_contradictions.py — permitted-region list "
                             f"with {region}: exit {code}, wanted {want}")
        else:
            lines.append("ok    check_contradictions.py — residency as an explicit "
                         "list of permitted regions")

        # A regime alias must reach the same verdict as its canonical spelling. It
        # did not: `cscrf` normalises to `sebi` but contained none of the substrings
        # the residency check matched on, so a SEBI entity in us-east-1 passed clean.
        offshore = copy.deepcopy(CLEAN)
        offshore["domains"]["04-cloud"]["answers"]["region"] = "us-east-1"
        codes = {}
        for spelling in ("sebi", "sebi-cscrf", "cscrf", "SEBI_CSCRF"):
            s = copy.deepcopy(offshore)
            s["domains"]["03-compliance"]["answers"] = {"regimes": [spelling]}
            codes[spelling] = run([str(HERE / "check_contradictions.py"),
                                   str(write(tmp, f"regime-{spelling}.json", s))])
        if set(codes.values()) == {1}:
            lines.append("ok    check_contradictions.py — every SEBI alias flags the "
                         "residency obligation")
        else:
            failed += 1
            lines.append(f"FAIL  check_contradictions.py — regime aliases disagree: "
                         f"{codes}")

        # C3: a regime this build cannot map has to have somewhere to live. Naming
        # a stub in `regimes` fails forever with no waiver path, so the honest
        # answer used to be deleted from the state file to get a green run — which
        # left the generation stage with no obligation to implement.
        unmapped = copy.deepcopy(CLEAN)
        unmapped["domains"]["03-compliance"]["answers"] = {
            "regimes": ["gdpr"], "residency": "eu",
            "regimes_unmapped": ["soc2", "Local Privacy Act 1988"]}
        unowned = run([str(HERE / "check_compliance.py"),
                       str(write(tmp, "unmapped-unowned.json", unmapped))])
        unmapped["open_questions"] = [
            {"id": "OQ-1", "domain": "03-compliance",
             "question": "SOC 2 control mapping — who supplies it?",
             "owner": "Client CISO", "due": "2026-10-01", "status": "open"},
            {"id": "OQ-2", "domain": "03-compliance",
             "question": "Local Privacy Act 1988 obligations, confirmed by counsel",
             "owner": "Counsel", "due": "2026-10-15", "status": "open"},
        ]
        owned = run([str(HERE / "check_compliance.py"),
                     str(write(tmp, "unmapped-owned.json", unmapped))])
        still_fails = run([str(HERE / "check_compliance.py"),
                           str(write(tmp, "stub-in-regimes.json",
                                     mutate(**{"03-compliance": {"regimes": ["soc2"]}})))])
        if (unowned, owned, still_fails) == (1, 0, 1):
            lines.append("ok    check_compliance.py — an unmappable regime passes "
                         "with an owner and a date, fails without one, and a stub in "
                         "`regimes` still fails")
        else:
            failed += 1
            lines.append(f"FAIL  check_compliance.py — regimes_unmapped: unowned exit "
                         f"{unowned} (want 1), owned {owned} (want 0), stub in "
                         f"`regimes` {still_fails} (want 1)")

        # Ordinary English must not read as another provider's service.
        english = copy.deepcopy(CLEAN)
        english["domains"]["12-data-dr"]["answers"]["backup"] = (
            "we need cloud storage for backups, and a secret manager for keys")
        code = run([str(HERE / "check_contradictions.py"),
                    str(write(tmp, "english.json", english))])
        real = copy.deepcopy(CLEAN)
        real["domains"]["12-data-dr"]["answers"]["backup"] = "backups go to GCS"
        code_real = run([str(HERE / "check_contradictions.py"),
                         str(write(tmp, "realgcp.json", real))])
        if code == 0 and code_real == 1:
            lines.append("ok    check_contradictions.py — 'cloud storage' is English, "
                         "'GCS' is a provider mismatch")
        else:
            failed += 1
            lines.append(f"FAIL  check_contradictions.py — provider tokens: plain "
                         f"English exit {code} (want 0), real GCP exit {code_real} "
                         f"(want 1)")

        # An answer affirming a secure default must not be a hard error.
        affirm = copy.deepcopy(CLEAN)
        affirm["domains"]["11-security"]["answers"] = {
            "posture": "no plaintext secrets anywhere, nothing publicly accessible, "
                       "and never allow 0.0.0.0/0"}
        path = write(tmp, "affirm.json", affirm)
        code = run([str(HERE / "check_contradictions.py"), str(path)])
        strict = run([str(HERE / "check_contradictions.py"), "--strict", str(path)])
        if code == 0 and strict == 1:
            lines.append("ok    check_contradictions.py — affirming a secure default "
                         "warns, and --strict still gates")
        else:
            failed += 1
            lines.append(f"FAIL  check_contradictions.py — affirming answer exit "
                         f"{code} (want 0), --strict {strict} (want 1)")

        # --- regressions, each one a bug this file exists to keep fixed --------

        # A price the interview spoke rather than typed. float() used to die here
        # with a traceback; num() reads it, and refuses only what it cannot.
        spoken = copy.deepcopy(CLEAN)
        spoken["cost"]["estimate"][0].update({"low": "$73", "high": "$73"})
        spoken["cost"]["ceiling"] = "20,000 USD"
        code = run([str(HERE / "check_cost.py"), str(write(tmp, "spoken.json", spoken))])
        ok = code == 0
        lines.append(("ok    " if ok else "FAIL  ") +
                     f"check_cost.py — reads '$73' and a '20,000 USD' ceiling"
                     + ("" if ok else f" (exit {code}, wanted 0)"))
        failed += not ok

        # ...and a price that is not a number at all is refused, not carried.
        junk = copy.deepcopy(CLEAN)
        junk["cost"]["estimate"][0].update({"low": "lots", "high": "lots"})
        code = run([str(HERE / "check_cost.py"), str(write(tmp, "junk.json", junk))])
        ok = code == 1
        lines.append(("ok    " if ok else "FAIL  ") +
                     "check_cost.py — refuses an unreadable price"
                     + ("" if ok else f" (exit {code}, wanted 1)"))
        failed += not ok

        # D1: an unpriced line makes the ceiling verdict provisional, not absent.
        # Suppressing the comparison entirely was all-or-nothing — one unpriced item
        # out of twelve threw away the signal from the other eleven.
        provisional = copy.deepcopy(CLEAN)
        provisional["cost"]["estimate"].append(
            {"item": "WAF", "assumptions": [], "unpriced": True,
             "note": "no rate card for this region yet"})
        proc = subprocess.run(
            [sys.executable, str(HERE / "check_cost.py"),
             str(write(tmp, "provisional.json", provisional))],
            capture_output=True, text=True)
        over = copy.deepcopy(provisional)
        over["cost"]["ceiling"] = 50
        over_code = run([str(HERE / "check_cost.py"),
                         str(write(tmp, "provisional-over.json", over))])
        if proc.returncode == 0 and "Provisional" in proc.stdout and over_code == 1:
            lines.append("ok    check_cost.py — an unpriced item makes the ceiling "
                         "verdict provisional, and a subtotal already over it still "
                         "fails")
        else:
            failed += 1
            lines.append(f"FAIL  check_cost.py — provisional ceiling verdict: exit "
                         f"{proc.returncode} (want 0), over-with-unpriced exit "
                         f"{over_code} (want 1)\n{proc.stdout}")

        # A scan of nothing is not a pass. An empty or mistyped artifact path used
        # to print "Clean ... nothing found" and exit 0, identical to a real pass.
        empty = tmp / "empty-artifacts"
        empty.mkdir()
        code = run([str(HERE / "scan_secrets.py"), str(empty)])
        ok = code == 2
        lines.append(("ok    " if ok else "FAIL  ") +
                     "scan_secrets.py — an empty target is exit 2, never a clean pass"
                     + ("" if ok else f" (exit {code}, wanted 2)"))
        failed += not ok

        # D3: SKILL.md requires three diagrams and three documents, and nothing
        # read the output directory, so every gate could be green over a
        # specification that was never written.
        docs = tmp / "docs-missing"
        docs.mkdir()
        state_only = write(tmp, "docs-state.json", CLEAN)
        empty_dir = run([str(HERE / "check_completeness.py"), str(state_only),
                         "--artifacts", str(docs)])
        (docs / "README.md").write_text("# plain language\n", encoding="utf-8")
        (docs / "open-questions.md").write_text("# open questions\n", encoding="utf-8")
        (docs / "architecture-spec.md").write_text(
            "# Spec\n\n```mermaid\ngraph TD\n  a --> b\n```\n", encoding="utf-8")
        one_diagram = run([str(HERE / "check_completeness.py"), str(state_only),
                           "--artifacts", str(docs)])
        (docs / "architecture-spec.md").write_text(
            "# Spec\n\n```mermaid\ngraph TD\n  a --> b\n```\n"
            "```mermaid\nflowchart LR\n  a --> b\n```\n"
            "```mermaid\nstateDiagram-v2\n  dev --> prod\n```\n", encoding="utf-8")
        three = run([str(HERE / "check_completeness.py"), str(state_only),
                     "--artifacts", str(docs)])
        no_artifacts = run([str(HERE / "check_completeness.py"), str(state_only)])
        if (empty_dir, one_diagram, three, no_artifacts) == (1, 1, 0, 0):
            lines.append("ok    check_completeness.py — the three documents and the "
                         "three diagrams are checked when --artifacts is given, and "
                         "not when it is not")
        else:
            failed += 1
            lines.append(f"FAIL  check_completeness.py — artifact checks: empty "
                         f"{empty_dir} (want 1), one diagram {one_diagram} (want 1), "
                         f"three {three} (want 0), state-only {no_artifacts} (want 0)")

        # The aggregate entry point: --draft always exits 0, and a real run over a
        # clean state must too. Catches a broken argv builder in run_gates.py that
        # every individual gate above would miss.
        state_path = write(tmp, "aggregate.json", CLEAN)
        arts = tmp / "artifacts-clean"
        if not arts.exists():
            arts.mkdir()
            (arts / "architecture-spec.md").write_text("# Spec\n", encoding="utf-8")
        draft = run([str(HERE / "run_gates.py"), "--state", str(state_path), "--draft"])
        if draft == 0:
            lines.append("ok    run_gates.py --draft — reports without blocking")
        else:
            failed += 1
            lines.append(f"FAIL  run_gates.py --draft — exit {draft}, wanted 0")

        # --draft must not run the secret scan while saying it did not. The summary
        # understating what the security gate actually did is the one direction
        # that must never happen, so it is asserted on the output, not the code.
        proc = subprocess.run(
            [sys.executable, str(HERE / "run_gates.py"), "--state", str(state_path),
             "--artifacts", str(arts), "--draft"], capture_output=True, text=True)
        scanned = "[pass] secrets" in proc.stdout or "[FAIL] secrets" in proc.stdout
        if scanned:
            failed += 1
            lines.append("FAIL  run_gates.py --draft — ran the secret scan, then "
                         "reported that it had not")
        else:
            lines.append("ok    run_gates.py --draft — skips the secret scan, as it says")

        # A gate that exited 2 never reached a verdict. Printing its verdict blurb
        # anyway reported a missing state file as an unanswered blocking domain.
        proc = subprocess.run(
            [sys.executable, str(HERE / "run_gates.py"), "--state", str(tmp / "absent.json"),
             "--artifacts", str(arts)], capture_output=True, text=True)
        if "never ran" in proc.stdout:
            lines.append("ok    run_gates.py — exit 2 is reported as 'never ran', "
                         "not as a verdict")
        else:
            failed += 1
            lines.append("FAIL  run_gates.py — misreports exit 2 as the gate's own "
                         "verdict")

    print("Gate selftest\n")
    for line in lines:
        print("  " + line)
    print("")
    if failed:
        print(f"{failed} gate(s) are not behaving. A gate that cannot catch its own "
              f"violation is worse than no gate: it reads as a clean bill of health.")
        return 1
    print("Every gate accepted its clean case and rejected its violating case.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

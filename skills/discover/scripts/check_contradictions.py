#!/usr/bin/env python3
"""Find places where the interview's own answers disagree with each other.

Reach for this before emitting a specification, and again after any revision. A
contradiction found here costs a question; the same contradiction found after
sign-off costs a redesign.

Inputs
    STATE        Path to discovery-state.json. Positional, required.
    --strict     Treat warnings as failures too. Use in CI, where a warning nobody
                 reads is a warning that does nothing.
    --json       Emit findings as JSON.

Outputs
    Findings grouped by severity. Each names the two answers that disagree, so the
    output is something to act on rather than a score.

    Exit 0  no errors. Warnings may be present unless --strict.
    Exit 1  at least one error, or --strict with at least one warning.
    Exit 2  the state file is missing or malformed.

Severity
    error     the two answers cannot both be satisfied. Something has to change.
    warning   they can both be true, but the combination is usually a mistake.
              Changing an answer can clear it, so --strict can gate on it.
    advisory  something to verify by hand, which no answer in the state file can
              clear. It never gates, not even under --strict.

    The third level exists because it was needed. Region service-availability is a
    live fact this script cannot check, so it is reported on every run where a cloud
    region is set. Filed as a warning it made --strict fail on a perfectly consistent
    state file, which would have meant --strict never being switched on and the real
    warnings never gating anything. A permanently-failing check trains people to
    ignore the checker.

Why some checks only warn
    §8 forbids asserting things this skill cannot establish. Whether a specific
    managed service exists in a specific region is a live fact that changes, and no
    offline table can be trusted for it. So the region-availability check reports
    what to verify and says plainly that it did not verify it, rather than producing
    a confident wrong answer. A warning that names the thing to check is worth more
    than an error that is sometimes false.

Answer keys read
    01-product     sla, rto, rpo
    03-compliance  regimes[], residency, residency_is_legal_requirement
    04-cloud       provider, region, az_spread, dr_region
    05-environments environments[], isolation
    06-compute     platform, control_plane, multi_az
    12-data-dr     dr_tier
    13-cost        ceiling
    14-team        headcount, pager
    Any answer, anywhere, is also scanned for named managed services, so the
    provider-consistency check does not depend on which domain recorded them.

Residency, and the three shapes the answer can take
    `residency` holds a geography (`"australia"`), several of them, or a list of
    permitted region names (`["ap-southeast-2", "ap-southeast-4"]`). The last needs
    no geography table and cannot be wrong, so prefer it where the obligation is
    already written as a list of regions in a contract.

    Geographies nest: a region in `australia` satisfies an obligation recorded as
    `apac`, and a region known only as `apac` does not satisfy one recorded as
    `australia` — that case is a warning, because it is this script not knowing the
    country rather than the answer being wrong.

    `residency_is_legal_requirement: false` downgrades a recorded residency from an
    error to a warning. Absent means obligation, which is the safe direction. A
    regime's own residency rule is always an error: it is a fact about the regime,
    not a preference of the project's.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import StateError, load, regimes  # noqa: E402

# Regimes that carry a data-residency obligation, and the geography each permits.
# The obligation is the regime's; whether it binds this client is the interview's
# question, which is why the compliance gate refuses to assert applicability.
#
# Keys are canonical slugs, as `_state.normalise_regime` produces and as
# compliance_controls.json spells them, and the lookup below is exact. It used to be
# a substring test, which silently missed every alias: `cscrf` normalises to `sebi`
# but contains none of these keys, so a SEBI entity in us-east-1 passed clean.
#
# The geographies must agree with `residency` in compliance_controls.json, which is
# the sourced artifact. selftest.py asserts they do. `ifsca` was listed here as
# india while the control map records null for it, and the control map wins — an
# obligation this repo cannot cite is one it must not assert.
RESIDENCY_REGIMES = {
    "dpdp": ("india", "India's DPDP Act framework, with transfer restrictions set by "
                      "government notification"),
    "rbi": ("india", "RBI storage requirements for payment and customer data"),
    "sebi": ("india", "SEBI CSCRF, for a SEBI-regulated entity"),
    "gdpr": ("eu", "GDPR Chapter V restrictions on transfers outside the EEA"),
}

# Region -> geography, finest first. A country pattern must come before the
# continental one that would otherwise swallow it: `ap-southeast-2` used to fall
# through to `^ap-` and be classified `apac`, so an Australian residency obligation
# could not be recorded at all — the only value the gate accepted was `apac`, which
# is the wrong answer and a dangerous one, since Singapore, Tokyo and Mumbai are all
# `apac` and all forbidden under an Australia-only contract. A gate whose only
# accepted answer is wrong is worse than no gate.
#
# Deliberately coarse below country level, and deliberately not a legal opinion: it
# is enough to catch a region that sits outside a stated obligation, not a substitute
# for someone reading the transfer rules. Where a region is not listed, `_geo_of`
# returns None and the residency check says it could not be checked rather than
# guessing.
#
# Patterns cover the three providers' spellings: AWS (`ap-southeast-2`), Azure
# (`australiaeast`) and GCP (`australia-southeast1`).
REGION_GEO = [
    # --- Asia Pacific, by country ---
    (r"^ap-south-\d", "india"), (r"^asia-south\d", "india"),
    (r"^(central|south|west)india", "india"),
    (r"^ap-southeast-(2|4)\b", "australia"), (r"^australia", "australia"),
    (r"^ap-southeast-1\b", "singapore"), (r"^southeastasia", "singapore"),
    (r"^asia-southeast1\b", "singapore"),
    (r"^ap-southeast-3\b", "indonesia"), (r"^asia-southeast2\b", "indonesia"),
    (r"^indonesiacentral", "indonesia"),
    (r"^ap-southeast-5\b", "malaysia"), (r"^malaysia", "malaysia"),
    (r"^ap-southeast-7\b", "thailand"), (r"^asia-southeast3\b", "thailand"),
    (r"^ap-northeast-(1|3)\b", "japan"), (r"^asia-northeast(1|2)\b", "japan"),
    (r"^japan(east|west)", "japan"),
    (r"^ap-northeast-2\b", "south-korea"), (r"^asia-northeast3\b", "south-korea"),
    (r"^korea(central|south)", "south-korea"),
    (r"^ap-east-1\b", "hong-kong"), (r"^asia-east2\b", "hong-kong"),
    (r"^eastasia", "hong-kong"),
    (r"^ap-east-2\b", "taiwan"), (r"^asia-east1\b", "taiwan"), (r"^taiwan", "taiwan"),
    (r"^cn-", "china"), (r"^china(north|east)", "china"),
    (r"^newzealand", "new-zealand"),
    # --- Europe, by country. `eu` here means the EEA, which is what GDPR Chapter V
    # restricts transfers out of; the UK and Switzerland are Europe but not the EEA,
    # and a transfer to either is a transfer out.
    (r"^eu-west-1\b", "ireland"), (r"^northeurope\b", "ireland"),
    (r"^eu-west-2\b", "uk"), (r"^uk(south|west)", "uk"), (r"^europe-west2\b", "uk"),
    (r"^eu-west-3\b", "france"), (r"^france", "france"), (r"^europe-west9\b", "france"),
    (r"^eu-central-1\b", "germany"), (r"^germany", "germany"),
    (r"^europe-west3\b", "germany"),
    (r"^eu-central-2\b", "switzerland"), (r"^switzerland", "switzerland"),
    (r"^europe-west6\b", "switzerland"),
    (r"^eu-north-1\b", "sweden"), (r"^sweden", "sweden"),
    (r"^europe-north2\b", "sweden"),
    (r"^eu-south-1\b", "italy"), (r"^italy", "italy"), (r"^europe-west8\b", "italy"),
    (r"^eu-south-2\b", "spain"), (r"^spain", "spain"), (r"^europe-southwest1\b", "spain"),
    (r"^westeurope\b", "netherlands"), (r"^europe-west4\b", "netherlands"),
    (r"^europe-west1\b", "belgium"),
    (r"^europe-north1\b", "finland"),
    (r"^norway", "norway"),
    (r"^poland", "poland"), (r"^europe-central2\b", "poland"),
    # --- North America ---
    (r"^ca-", "canada"), (r"^canada", "canada"), (r"^northamerica-northeast", "canada"),
    (r"^mexicocentral", "mexico"), (r"^northamerica-south1\b", "mexico"),
    (r"^us-", "us"), (r"^(east|west|central|north|south)us", "us"),
    (r"^us(east|west|central)", "us"), (r"^northamerica-", "us"),
    # --- Latin America ---
    (r"^sa-east-1\b", "brazil"), (r"^brazil", "brazil"),
    (r"^southamerica-east1\b", "brazil"), (r"^southamerica-west1\b", "chile"),
    (r"^chile", "chile"),
    (r"^(sa|southamerica)-", "latam"),
    # --- Middle East and Africa ---
    (r"^me-south-1\b", "bahrain"),
    (r"^me-central-1\b", "uae"), (r"^uae", "uae"),
    (r"^me-central2\b", "saudi-arabia"), (r"^saudi", "saudi-arabia"),
    (r"^qatar", "qatar"), (r"^me-central1\b", "qatar"),
    (r"^il-central-1\b", "israel"), (r"^israel", "israel"), (r"^me-west1\b", "israel"),
    (r"^af-south-1\b", "south-africa"), (r"^southafrica", "south-africa"),
    (r"^africa-south1\b", "south-africa"),
    # --- Continental fallbacks, for a region no country pattern claimed ---
    (r"^ap-", "apac"), (r"^asia-", "apac"), (r"^(southeast|east)asia", "apac"),
    (r"^(eu|europe)-", "eu"),
    (r"^(west|north)europe", "eu"),
    (r"^me-", "middle-east"), (r"^af-", "africa"),
]

# Which geography contains which. A region in `australia` satisfies an obligation
# recorded as `apac`; a region known only as `apac` does not satisfy an obligation
# recorded as `australia`, and says so as a warning rather than an error, because
# that is the gate not knowing the country rather than the answer being wrong.
#
# `eu` is the EEA: the GDPR obligation is about transfers out of it, so the UK and
# Switzerland sit under `europe` instead. Nothing here is legal advice; it is the
# containment the residency check compares against, written down where it can be
# read and argued with.
GEO_PARENTS: dict[str, str] = {
    "india": "apac", "australia": "apac", "new-zealand": "apac",
    "singapore": "apac", "indonesia": "apac", "malaysia": "apac",
    "thailand": "apac", "japan": "apac", "south-korea": "apac",
    "hong-kong": "apac", "taiwan": "apac", "china": "apac",
    "ireland": "eu", "france": "eu", "germany": "eu", "netherlands": "eu",
    "belgium": "eu", "spain": "eu", "italy": "eu", "sweden": "eu",
    "finland": "eu", "poland": "eu", "norway": "eu",
    "eu": "europe", "uk": "europe", "switzerland": "europe",
    "us": "north-america", "canada": "north-america", "mexico": "north-america",
    "brazil": "latam", "chile": "latam",
    "uae": "middle-east", "qatar": "middle-east", "bahrain": "middle-east",
    "israel": "middle-east", "saudi-arabia": "middle-east",
    "south-africa": "africa",
    "apac": "global", "europe": "global", "north-america": "global",
    "latam": "global", "middle-east": "global", "africa": "global",
}

# What an interview is likely to write, mapped to the slug the table above uses.
# The alternative is a hard error on a perfectly clear answer, which is how an
# interviewer learns to write whatever the gate accepts rather than what is true.
RESIDENCY_ALIASES = {
    "eea": "eu", "european-union": "eu", "european-economic-area": "eu",
    "europe": "europe",
    "usa": "us", "united-states": "us", "united-states-of-america": "us", "america": "us",
    "united-kingdom": "uk", "gb": "uk", "britain": "uk", "great-britain": "uk",
    "aus": "australia", "au": "australia",
    "in": "india", "bharat": "india",
    "ca": "canada", "sg": "singapore", "jp": "japan", "kr": "south-korea",
    "de": "germany", "fr": "france", "ch": "switzerland", "br": "brazil",
    "za": "south-africa", "ae": "uae", "uae-only": "uae",
    "asia-pacific": "apac", "asia": "apac",
    "latin-america": "latam", "south-america": "latam",
    "middle-east-and-africa": "middle-east",
}

# A region name, not a geography: `ap-southeast-2`, `westeurope`, `us-central1`.
# When `residency` holds these instead of a geography, the interview has given an
# explicit allow-list, which is the one form of this answer that cannot be wrong.
REGION_SHAPED = re.compile(r"^[a-z]{2,}-[a-z]+-?\d|^[a-z]+(east|west|central|north|south)\w*\d*$")

# Distinctive service tokens only. A token like "kms" appears in more than one
# provider's naming and would produce noise, so it is left out; the goal is to catch
# a real mismatch, not to inventory every service.
#
# "Distinctive" was not being honoured. The GCP set carried three ordinary English
# phrases — "cloud storage", "secret manager", "cloud dns" and friends — so an AWS
# project whose answer read "we need cloud storage for backups" got a hard error
# claiming a GCP service had been chosen. A gate that fires on plain English is a
# gate people learn to ignore, so every ambiguous token here is provider-qualified.
# The bare forms are gone rather than downgraded: this check earns its error level
# only if a match really means the wrong provider.
PROVIDER_SERVICES: dict[str, set[str]] = {
    "aws": {"eks", "ecs", "fargate", "lambda", "rds", "aurora", "dynamodb", "s3",
            "elasticache", "msk", "sqs", "sns", "cloudfront", "route 53", "route53",
            "acm", "secrets manager", "cloudwatch", "guardduty", "security hub",
            "cloudtrail", "iam identity center", "app runner", "efs", "alb", "nlb",
            "amazon managed prometheus", "opensearch service", "aws waf", "shield"},
    "gcp": {"gke", "cloud run", "spanner", "bigquery", "memorystore", "pub/sub",
            "cloud armor", "filestore", "security command center",
            "gcs", "google cloud storage", "google secret manager",
            "google artifact registry", "google cloud sql", "google cloud dns",
            "google cloud cdn", "google cloud functions", "google cloud logging",
            "google cloud monitoring"},
    "azure": {"aks", "cosmos db", "azure functions", "azure sql", "azure blob storage",
              "azure cache for redis", "azure service bus", "azure event hubs",
              "azure dns", "azure front door", "azure key vault", "azure monitor",
              "azure log analytics", "defender for cloud", "entra id",
              "azure container apps", "azure container registry"},
}

SELF_HOSTED_CONTROL_PLANE = {
    "kubeadm", "k3s", "rke2", "talos", "openshift", "okd", "self-hosted",
    "self-managed", "nomad", "microk8s", "kops",
}

# Any Kubernetes, managed or not. Kept separate from the set above because the two
# questions are different: "who patches the control plane" versus "does this carry
# Kubernetes' cost floor". A self-hosted cluster answers yes to both, and a managed
# one only to the second — which is why the first version of the budget check missed
# a kubeadm cluster entirely.
ANY_KUBERNETES = SELF_HOSTED_CONTROL_PLANE | {
    "kubernetes", "k8s", "eks", "gke", "aks", "doks", "oke", "magnum",
}

DR_TIER_RTO_CEILING_HOURS = {
    "active-active": 0.1, "warm": 1.0, "warm-standby": 1.0,
    "pilot-light": 4.0, "backup-restore": 24.0,
}


def _answers(state: dict, domain: str) -> dict:
    return state.get("domains", {}).get(domain, {}).get("answers", {}) or {}


def _num(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = re.search(r"(\d+(?:\.\d+)?)", value)
        if m:
            return float(m.group(1))
    return None


def _duration_hours(value) -> float | None:
    """Parse '15m', '4h', '2 days', 'zero', 30 (minutes assumed for bare numbers)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) / 60.0
    text = str(value).strip().lower()
    if text in {"0", "zero", "none", "near-zero", "instant"}:
        return 0.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)?", text)
    if not m:
        return None
    n, unit = float(m.group(1)), (m.group(2) or "m")
    if unit.startswith("m"):
        return n / 60.0
    if unit.startswith("h"):
        return n
    return n * 24.0


def _geo_of(region: str) -> str | None:
    """The finest geography the tables know for a region, or None.

    None means "not in the table", and every caller has to report that as
    unchecked. Returning a continent for an unrecognised region would be a guess
    with the same shape as a fact.
    """
    r = region.strip().lower()
    for pattern, geo in REGION_GEO:
        if re.search(pattern, r):
            return geo
    return None


def _ancestry(geo: str) -> list[str]:
    """`geo` and everything that contains it, nearest first.

    Loop-guarded: GEO_PARENTS is hand-maintained, and one wrong entry would
    otherwise hang the gate rather than fail it. selftest.py asserts it is acyclic.
    """
    chain, seen = [geo], {geo}
    while geo in GEO_PARENTS:
        geo = GEO_PARENTS[geo]
        if geo in seen:
            break
        chain.append(geo)
        seen.add(geo)
    return chain


def _within(region_geo: str, obligation: str) -> bool:
    """Whether a region in `region_geo` sits inside `obligation`."""
    return obligation in _ancestry(region_geo)


def _known_geo(name: str) -> bool:
    return name in GEO_PARENTS or name in set(GEO_PARENTS.values()) or name == "global"


def _normalise_geo(name: str) -> str:
    n = str(name).strip().lower().replace("_", "-").replace(" ", "-")
    return RESIDENCY_ALIASES.get(n, n)


def _residency_answer(compliance: dict) -> tuple[list[str], list[str], bool | None]:
    """(geographies, explicit permitted regions, is it a legal requirement).

    `residency` may be a geography (`"australia"`), a list of them, or a list of
    region names (`["ap-southeast-2", "ap-southeast-4"]`). The last form is the one
    that cannot be wrong — it needs no table and no containment reasoning — so it is
    supported rather than argued with.

    The third element reads `residency_is_legal_requirement`, which
    `domain-03-compliance.md` tells the interviewer to record and which nothing used
    to read. Absent means "treat it as an obligation": the safe direction, and the
    behaviour before the flag existed.
    """
    raw = compliance.get("residency")
    values = raw if isinstance(raw, list) else [raw]
    geos: list[str] = []
    regions: list[str] = []
    for v in values:
        if not isinstance(v, (str, int, float)):
            continue
        text = str(v).strip().lower()
        if not text or text in {"none", "no constraint", "unconstrained", "n/a"}:
            continue
        if REGION_SHAPED.match(text.replace(" ", "")):
            regions.append(text)
        else:
            geos.append(_normalise_geo(text))
    legal = compliance.get("residency_is_legal_requirement")
    return geos, regions, (None if legal is None else bool(legal))


def _all_answer_text(state: dict) -> list[tuple[str, str]]:
    """(domain, lowercased text) for every answer value, for service scanning."""
    out = []
    for domain, entry in state.get("domains", {}).items():
        for key, value in (entry.get("answers") or {}).items():
            values = value if isinstance(value, list) else [value]
            for v in values:
                if isinstance(v, (str, int, float)):
                    out.append((f"{domain}.{key}", str(v).lower()))
    return out


def check(state: dict) -> list[dict]:
    f: list[dict] = []

    def add(sev, rule, message, detail):
        f.append({"severity": sev, "rule": rule, "message": message, "detail": detail})

    product, compliance = _answers(state, "01-product"), _answers(state, "03-compliance")
    cloud, envs = _answers(state, "04-cloud"), _answers(state, "05-environments")
    compute, datadr = _answers(state, "06-compute"), _answers(state, "12-data-dr")
    cost, team = _answers(state, "13-cost"), _answers(state, "14-team")

    region = str(cloud.get("region", "") or "")
    provider = str(cloud.get("provider", "") or "").strip().lower()
    named_regimes = regimes(state)

    # --- 1. residency versus chosen region -----------------------------------
    #
    # Two kinds of obligation, and they are not equally hard. One comes from a
    # regime whose own text carries a residency rule, and is a legal fact about the
    # regime. The other is what the interview recorded, and `domain-03-compliance.md`
    # asks whether that one is a legal requirement or a preference — so a preference
    # warns and an obligation blocks, which is what that reference file has always
    # claimed happens.
    stated_geos, permitted_regions, legal = _residency_answer(compliance)
    obligations: dict[str, tuple[str, str]] = {}  # geo -> (why, severity)
    for r in named_regimes:
        if r in RESIDENCY_REGIMES:
            geo, why = RESIDENCY_REGIMES[r]
            obligations[geo] = (why, "error")
    stated_severity = "warning" if legal is False else "error"
    for geo in stated_geos:
        if not _known_geo(geo):
            add("warning", "residency-not-recognised",
                f"Residency is recorded as {geo!r}, which is not a geography this "
                f"script knows, so the region could not be checked against it. Use a "
                f"country or continent slug the table lists, or record the permitted "
                f"regions explicitly — a list of region names needs no table at all.",
                {"residency": geo})
            continue
        obligations.setdefault(geo, ("residency recorded in the interview",
                                     stated_severity))

    def _check_region(label: str, value: str, rule: str, extra: str = "") -> None:
        geo = _geo_of(value)
        if permitted_regions:
            if value.strip().lower() not in permitted_regions:
                add("error", rule,
                    f"{label} {value!r} is not in the list of permitted regions the "
                    f"interview recorded ({', '.join(sorted(permitted_regions))})."
                    + extra,
                    {"region": value, "permitted_regions": sorted(permitted_regions)})
            return
        if not obligations:
            return
        if geo is None:
            add("warning", rule,
                f"{label} {value!r} could not be mapped to a geography, so the "
                f"residency obligation could not be checked. Add it to REGION_GEO, "
                f"or record the permitted regions explicitly.",
                {"region": value, "obligations": sorted(obligations)})
            return
        satisfied = [o for o in obligations if _within(geo, o)]
        if satisfied:
            return
        # The region is known only at continent level and the obligation is a
        # country inside that continent. That is the table being coarse, not the
        # answer being wrong, so it is reported as unverified rather than refused.
        coarse = [o for o in obligations if _within(o, geo)]
        severity = "warning" if coarse else max(
            (obligations[o][1] for o in obligations),
            key=lambda s: {"warning": 0, "error": 1}[s])
        if coarse:
            add("warning", rule,
                f"{label} {value!r} is in {geo}, and the obligation is for "
                f"{', '.join(sorted(coarse))} — inside {geo}, so this could not be "
                f"confirmed either way. Name the country-level region, or record the "
                f"permitted regions explicitly.",
                {"region": value, "region_geo": geo, "obligations": sorted(obligations)})
        else:
            add(severity, rule,
                f"{label} {value!r} is in {geo}, but the interview records a "
                f"residency obligation for {', '.join(sorted(obligations))}." + extra,
                {"region": value, "region_geo": geo,
                 "reasons": [obligations[o][0] for o in sorted(obligations)],
                 "severity_from": ("a preference, not a stated legal requirement"
                                   if severity == "warning" else "a stated obligation")})

    if region:
        _check_region("Region", region, "residency-vs-region")
    elif obligations or permitted_regions:
        add("warning", "residency-vs-region",
            "A residency obligation is recorded but no region has been chosen yet.",
            {"obligations": sorted(obligations),
             "permitted_regions": sorted(permitted_regions)})

    dr_region = str(cloud.get("dr_region", "") or "")
    if dr_region:
        _check_region("DR region", dr_region, "residency-vs-dr-region",
                      " A disaster-recovery copy is still a copy.")

    # --- 2. provider versus named managed services ---------------------------
    if provider in PROVIDER_SERVICES:
        own = PROVIDER_SERVICES[provider]
        for other, services in PROVIDER_SERVICES.items():
            if other == provider:
                continue
            for where, text in _all_answer_text(state):
                for svc in services:
                    if svc in own:
                        continue
                    if re.search(rf"(^|[^a-z0-9]){re.escape(svc)}($|[^a-z0-9])", text):
                        add("error", "provider-service-mismatch",
                            f"{svc!r} is a {other.upper()} service, but the chosen "
                            f"provider is {provider.upper()}.",
                            {"service": svc, "belongs_to": other,
                             "chosen_provider": provider, "recorded_at": where})
    if provider and provider not in PROVIDER_SERVICES and provider not in {
            "on-prem", "on-premises", "bare-metal", "colocation", "hybrid"}:
        add("warning", "unknown-provider",
            f"Provider {provider!r} is not one this script knows, so the "
            f"service-consistency check did not run.",
            {"provider": provider})

    if provider in PROVIDER_SERVICES and region:
        add("advisory", "region-availability-unverified",
            f"Service availability in {region!r} was not verified. This script has no "
            f"live pricing or availability data, and an offline table would go stale. "
            f"Confirm each managed service exists in that region before sign-off.",
            {"region": region, "provider": provider})

    # --- 3. SLA versus availability topology ---------------------------------
    sla = _num(product.get("sla"))
    az_spread = _num(cloud.get("az_spread"))
    multi_az = compute.get("multi_az")
    single_az = (az_spread is not None and az_spread < 2) or multi_az is False
    if sla is not None and sla >= 99.9 and single_az:
        add("error", "sla-vs-single-az",
            f"An SLA of {sla}% cannot be met in a single availability zone. A single "
            f"zone's own failure budget is larger than the whole allowance.",
            {"sla": sla, "az_spread": az_spread, "multi_az": multi_az})
    if sla is not None and sla >= 99.95 and not dr_region:
        add("warning", "sla-vs-single-region",
            f"An SLA of {sla}% with no DR region leaves a regional failure with no "
            f"answer. Either record a DR region or record that the SLA excludes it.",
            {"sla": sla})

    # --- 4. team capacity versus self-hosted control planes ------------------
    headcount = _num(team.get("headcount"))
    pager = str(team.get("pager", "") or "").strip().lower()
    platform_text = " ".join(
        str(v).lower() for v in [compute.get("platform"), compute.get("control_plane")] if v
    )
    self_hosted = any(k in platform_text for k in SELF_HOSTED_CONTROL_PLANE)
    if self_hosted and headcount is not None and headcount <= 3:
        add("error", "team-vs-self-hosted",
            f"A self-hosted control plane ({platform_text.strip()}) with a team of "
            f"{int(headcount)} has nobody to patch it, restore etcd, or answer a 3am "
            f"page. Either take the managed option or record who does those things.",
            {"headcount": headcount, "platform": platform_text.strip()})
    if self_hosted and pager in {"nobody", "none", "no one", "unstaffed"}:
        add("error", "pager-vs-self-hosted",
            "A self-hosted control plane with nobody on call is an outage with no "
            "responder. Record an owner or choose a managed platform.",
            {"pager": pager, "platform": platform_text.strip()})
    if pager in {"business-hours", "business hours", "9-5"} and sla is not None and sla >= 99.9:
        add("error", "pager-vs-sla",
            f"An SLA of {sla}% allows roughly {round((100 - sla) / 100 * 8760 * 60)} "
            f"minutes of downtime a year. Business-hours-only cover cannot hold that, "
            f"because a Friday-evening failure alone exceeds it.",
            {"sla": sla, "pager": pager})

    # --- 5. RTO versus DR tier ------------------------------------------------
    rto_hours = _duration_hours(product.get("rto") or datadr.get("rto"))
    tier = str(datadr.get("dr_tier", "") or "").strip().lower().replace(" ", "-")
    if rto_hours is not None and tier in DR_TIER_RTO_CEILING_HOURS:
        ceiling = DR_TIER_RTO_CEILING_HOURS[tier]
        if rto_hours < ceiling:
            add("error", "rto-vs-dr-tier",
                f"An RTO of {rto_hours:g}h is shorter than a {tier} strategy can "
                f"deliver; that tier realistically restores in {ceiling:g}h or more. "
                f"Either relax the RTO or move up a tier and price it.",
                {"rto_hours": rto_hours, "dr_tier": tier, "tier_floor_hours": ceiling})

    # A standby tier with nowhere to stand by. Found in Phase 4 by the skill's own
    # run: a state file recorded dr_tier "warm" with dr_region null while the cost
    # estimate priced a copy in a second region — three answers disagreeing, and no
    # existing rule looked at the pair.
    if tier in {"active-active", "warm", "warm-standby", "pilot-light"} and not dr_region:
        add("error", "dr-tier-without-dr-region",
            f"DR tier is {tier!r} but no DR region is recorded. Every tier above "
            f"backup-and-restore needs somewhere to recover to, so either name the "
            f"region or record the tier as backup-restore.",
            {"dr_tier": tier, "dr_region": dr_region or None})

    # --- 6. budget versus structural choices ---------------------------------
    ceiling_cost = _num(cost.get("ceiling"))
    env_list = envs.get("environments") or []
    persistent = [e for e in env_list if isinstance(e, str)]
    drivers = []
    if any(k in platform_text for k in ANY_KUBERNETES):
        drivers.append("a Kubernetes platform")
    if len(persistent) >= 3:
        drivers.append(f"{len(persistent)} persistent environments")
    if not single_az and az_spread and az_spread >= 3:
        drivers.append("three-zone spread")
    if tier in {"active-active", "warm", "warm-standby"}:
        drivers.append(f"a {tier} DR posture")
    if ceiling_cost is not None and ceiling_cost < 1500 and len(drivers) >= 2:
        add("error", "budget-vs-topology",
            f"A ceiling of {ceiling_cost:g} {cost.get('currency', '')} "
            f"{cost.get('period', 'monthly')} against "
            f"{', '.join(drivers)} is very unlikely to hold. Reduce the topology or "
            f"raise the ceiling; the cost gate will show the arithmetic.",
            {"ceiling": ceiling_cost, "drivers": drivers})
    elif ceiling_cost is not None and ceiling_cost < 4000 and len(drivers) >= 3:
        add("warning", "budget-vs-topology",
            f"A ceiling of {ceiling_cost:g} against {', '.join(drivers)} is tight. "
            f"Check the cost gate's arithmetic before committing to it.",
            {"ceiling": ceiling_cost, "drivers": drivers})

    # --- 7. compliance versus isolation model -------------------------------
    isolation = str(envs.get("isolation", "") or "").strip().lower()
    if any("pci" in r for r in named_regimes) and isolation in {"namespace", "tag", "tags", "none"}:
        add("error", "pci-vs-isolation",
            f"PCI-DSS expects the cardholder data environment to be segmented from "
            f"everything else. {isolation!r} isolation puts it in the same blast "
            f"radius as non-PCI workloads, which widens the assessment scope to all "
            f"of them.",
            {"isolation": isolation, "regimes": named_regimes})
    if any("pci" in r for r in named_regimes) and len(persistent) >= 2 and \
            isolation in {"vpc", "subnet"} and str(cloud.get("account_model", "")).lower() in {"single", "single-account", ""}:
        add("warning", "pci-vs-account-model",
            "PCI-DSS in a single cloud account relies entirely on IAM and network "
            "boundaries holding. It is defensible, and it needs to be argued "
            "explicitly in the specification rather than assumed.",
            {"isolation": isolation, "environments": persistent})

    # --- 8. secure defaults deviated without a waiver ------------------------
    waived = {str(w.get("control", "")).strip().lower()
              for w in state.get("waivers", []) if isinstance(w, dict)}
    deviations = [
        (r"public(ly)?[ -]?(accessible|reachable|exposed)", "public data store or endpoint",
         "no publicly reachable data stores"),
        (r"static (credential|key|token)|long-?lived (credential|key)", "long-lived static credentials",
         "no long-lived static credentials"),
        (r"unencrypted|no encryption|plaintext", "unencrypted data",
         "encryption in transit and at rest"),
        (r"\b0\.0\.0\.0/0\b", "an unrestricted ingress range", "least privilege"),
    ]
    # A warning, not an error, and once per control rather than once per mention.
    #
    # These patterns are bare substrings over free text, and free text about security
    # is usually affirming the control: "no plaintext secrets anywhere", "nothing
    # publicly accessible", "we must never allow 0.0.0.0/0" each matched and each
    # produced a hard error demanding a waiver for a control the answer was upholding.
    # No cheap regex separates "we allow" from "we forbid" — negation scope in English
    # defeats it — so the honest move is to stop claiming to know which one it is.
    # Filed as an error it blocked correct answers, which trains people to bypass the
    # gate; filed as a warning it still surfaces, and --strict still gates on it.
    seen_controls = set()
    for where, text in _all_answer_text(state):
        for pattern, label, control in deviations:
            if control in waived or control in seen_controls:
                continue
            if re.search(pattern, text):
                seen_controls.add(control)
                add("warning", "secure-default-without-waiver",
                    f"{label.capitalize()} is mentioned in {where}. If that is a real "
                    f"deviation from {control!r}, record a waiver with a reason and an "
                    f"owner. If the answer is affirming the control, nothing to do — "
                    f"this check matches the words, not their sense.",
                    {"recorded_at": where, "control": control, "excerpt": text[:120]})

    return f


def render(findings: list[dict]) -> str:
    if not findings:
        return "No contradictions found."

    out: list[str] = []
    for sev, title in (
            ("error", "Errors — these answers cannot both be satisfied"),
            ("warning", "Warnings — possible, but usually a mistake"),
            ("advisory", "Verify by hand — this script cannot check these")):
        group = [x for x in findings if x["severity"] == sev]
        if not group:
            continue
        out.append(f"{title} ({len(group)}):")
        out.append("")
        for x in group:
            out.append(f"  [{x['rule']}]")
            out.append(f"      {x['message']}")
        out.append("")
    return "\n".join(out).rstrip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        state = load(args.state)
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    findings = check(state)
    print(json.dumps(findings, indent=2) if args.json else render(findings))
    errors = [x for x in findings if x["severity"] == "error"]
    warnings = [x for x in findings if x["severity"] == "warning"]
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())

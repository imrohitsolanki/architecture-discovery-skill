"""The discovery-state.json contract, shared by every gate.

Not an entry point. It is imported by the gate scripts, which run as subprocesses of
`run_gates.py`, so it needs no permission rule of its own.

It exists so the schema is defined once. Five gates all read the same state file, and
five independent notions of what that file looks like would drift within a week.

## The state file

`discovery-state.json` lives with the artifacts, in the output directory, and is
committed. That last fact is why the secret scan covers it: a state file nobody
scanned is a credential leak waiting to be indexed.

```json
{
  "schema_version": "1",
  "project": {
    "name": "Human readable name",
    "slug": "kebab-case-slug",
    "started": "2026-09-07",
    "updated": "2026-09-07"
  },
  "domains": {
    "01-product": {
      "status": "complete",
      "answers": {"sla": 99.9, "any-other-key": "the answer as given"},
      "notes": "anything that did not fit an answer"
    }
  },
  "open_questions": [
    {
      "id": "OQ-1",
      "domain": "03-compliance",
      "question": "Does the client hold cardholder data directly?",
      "proposed_default": "Assume yes and scope for PCI-DSS",
      "owner": "Client CTO",
      "due": "2026-09-20",
      "status": "open"
    }
  ],
  "decisions": [
    {
      "id": "ADR-001",
      "title": "Managed Kubernetes over self-hosted",
      "domain": "06-compute",
      "choice": "Amazon EKS",
      "alternatives_rejected": [
        {"option": "kubeadm on EC2", "reason": "Two-person team, nobody carries a pager"}
      ],
      "rationale": "why this choice, in the project's own terms",
      "date": "2026-09-07"
    }
  ],
  "waivers": [
    {
      "control": "Data store in a private subnet",
      "deviation": "Analytics database reachable from the office IP range",
      "reason": "Stated reason, from the person who accepted it",
      "owner": "Named person",
      "date": "2026-09-07"
    }
  ],
  "detected": {},
  "cost": {
    "currency": "USD",
    "period": "monthly",
    "ceiling": 4000,
    "model": "cloud",
    "estimate": [
      {
        "item": "EKS control plane",
        "assumptions": ["one cluster", "ap-south-1", "on-demand list price"],
        "low": 73,
        "high": 73,
        "unpriced": false
      }
    ]
  }
}
```

## Answer keys are a vocabulary, not free text

Record whatever the interview produced, under whatever key fits — except where a
gate reads a key by name. Those are listed in `ANSWER_KEYS` below, and a paraphrase
there does not make a gate wrong, it makes the gate blind: `{"team_size": 2}` with a
self-hosted control plane passed the contradiction gate clean, where
`{"headcount": 2}` failed it. `check_completeness.py` now refuses a domain marked
`complete` whose required keys are absent, and names the unrecognised keys it found
so the rename is obvious.

Use the exact key for anything in `ANSWER_KEYS["<domain>"]["required"]`. Everything
else in a domain's answers is yours.

## Compliance regimes this build cannot map

`03-compliance.answers.regimes` holds the regimes whose controls this repository can
actually map. Two kinds of regime cannot go there and must still be recorded:

- one in the catalogue whose primary text was never sourced (LIMITATIONS.md L1), and
- one that is real but has no control file here at all, such as a national privacy
  act this build never read.

Both go in `regimes_unmapped`, alongside an open question with an owner and a date:

```json
"03-compliance": {
  "status": "complete",
  "answers": {
    "regimes": ["pci-dss"],
    "regimes_unmapped": ["soc2", "Local Privacy Act 1988"],
    "residency": "australia",
    "residency_is_legal_requirement": true
  }
}
```

The compliance gate reports those prominently and does not fail on them, so the
honest answer stays in the state file where the generation stage can see it. Putting
them in `regimes` instead fails the gate permanently with no waiver path, which is
how a real obligation ends up deleted from the record to get a green run.

## Domain status values

- `not-started` — never asked
- `partial` — some questions answered, others outstanding
- `complete` — asked and answered
- `not-applicable` — ruled out by an earlier answer, with the reason in `notes`.
  Counts as answered. A serverless application legitimately has no node strategy,
  and forcing an answer would invent one.

## Which domains block a final spec

Blocking where a default would be a guess about the *business*: what the thing does,
who regulates it, which provider the client is committed to, what downtime costs,
what they can spend, and who will operate it. Nobody can default those on the
client's behalf.

Non-blocking where a defensible *technical* default exists. Those are filled from
`references/secure-defaults.md` and recorded as a default rather than a decision, so
a reviewer can see it was never actually chosen.

The distinction matters because §7 requires the completeness gate to refuse a spec
with a blocking domain unanswered, and a gate that blocks on everything is a gate
that gets switched off.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_VERSION = "1"

DOMAINS: dict[str, str] = {
    "01-product": "Product context",
    "02-app-shape": "Application shape",
    "03-compliance": "Compliance and data governance",
    "04-cloud": "Cloud and region",
    "05-environments": "Environment topology",
    "06-compute": "Compute platform",
    "07-networking": "Networking and ingress",
    "08-identity": "Identity and secrets",
    "09-delivery": "Delivery",
    "10-observability": "Observability",
    "11-security": "Security posture",
    "12-data-dr": "Data, backup and DR",
    "13-cost": "Cost",
    "14-team": "Team and operations",
}

# See the module docstring for why these seven and not the others.
BLOCKING: dict[str, str] = {
    "01-product": "Without what it does, who uses it and what downtime costs, every "
                  "later choice is unanchored. There is no technical default for a "
                  "business requirement.",
    "03-compliance": "A regime discovered after the design is a redesign. Segmentation, "
                     "key custody and log retention all change the topology.",
    "04-cloud": "Provider and region decide which managed services exist at all, so "
                "every service-level choice depends on it.",
    "06-compute": "The platform decides the shape of networking, delivery and "
                  "operations. Defaulting it defaults most of the specification.",
    "12-data-dr": "RTO and RPO are commercial decisions about what an outage costs. "
                  "Guessing them sets a budget nobody agreed to.",
    "13-cost": "Without a ceiling the cost gate has nothing to check against, so a "
               "specification can be affordable or ruinous and read identically.",
    "14-team": "Who operates this decides managed versus self-hosted throughout. A "
               "two-person team and a platform team get different correct answers.",
}

# Answer keys the gates read by name. A domain can carry any other answers it
# likes — the reference files ask more questions than these — but where a gate
# depends on an exact key, a paraphrase makes that gate blind rather than wrong.
#
# The failure this catches: "14-team": {"team_size": 2, "on_call": "nobody"} with a
# self-hosted control plane passed the contradiction gate clean, because the rule
# reads `headcount` and `pager`. Same project written as `headcount`/`pager` exits 1.
# Nothing surfaced the difference, which makes it the worst kind of gate defect —
# a silent pass that reads exactly like a real one.
#
# `required` means a gate cannot do its job without it. `optional` means recognised
# but conditional: dr_region only matters once DR is in scope, az_spread only for a
# provider that has zones.
ANSWER_KEYS: dict[str, dict[str, set[str]]] = {
    "01-product":      {"required": {"sla"}, "optional": {"rto"}},
    "03-compliance":   {"required": {"regimes"},
                        "optional": {"residency", "residency_is_legal_requirement",
                                     "regimes_unmapped"}},
    "04-cloud":        {"required": {"provider", "region"},
                        "optional": {"dr_region", "az_spread", "account_model"}},
    "05-environments": {"required": {"environments"}, "optional": {"isolation"}},
    "06-compute":      {"required": {"platform"},
                        "optional": {"control_plane", "multi_az"}},
    # Read by the generation skill rather than by a gate here: `iac` decides
    # Terraform, OpenTofu or Terragrunt, and `policy_pre_apply` decides which policy
    # scanner check_iac.py runs. A paraphrase is worse across the skill boundary than
    # within it — `scanner: "Checkov"` leaves the generation gate reporting that the
    # specification named no scanner at all, which reads like a decision rather than
    # a misread key.
    "09-delivery":     {"required": {"iac"},
                        "optional": {"policy_pre_apply", "policy_admission",
                                     "policy_mode", "iac_state", "iac_pinning",
                                     "templating", "registry"}},
    "12-data-dr":      {"required": {"rto"}, "optional": {"dr_tier", "dr_region"}},
    "13-cost":         {"required": set(), "optional": {"ceiling"}},
    "14-team":         {"required": {"headcount", "pager"}, "optional": set()},
}

ANSWERED = {"complete", "not-applicable"}
VALID_STATUS = {"not-started", "partial", "complete", "not-applicable"}


class StateError(Exception):
    """The state file is missing, unreadable, or not shaped like the contract."""


def load(path: str | Path) -> dict:
    """Read and shape-check discovery-state.json.

    Raises StateError with a message meant for a person, because every caller
    surfaces it directly to whoever is running the interview.
    """
    p = Path(path)
    if not p.is_file():
        raise StateError(
            f"no state file at {p}. The interview writes discovery-state.json as it "
            f"goes; if this is a fresh start there is nothing to gate yet."
        )
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StateError(f"{p} is not valid JSON: {exc}") from exc
    if not isinstance(state, dict):
        raise StateError(f"{p} must contain a JSON object, found {type(state).__name__}")

    version = str(state.get("schema_version", ""))
    if version and version != SCHEMA_VERSION:
        raise StateError(
            f"{p} declares schema_version {version!r}, this gate understands "
            f"{SCHEMA_VERSION!r}. Migrate the file rather than ignoring the mismatch."
        )

    domains = state.setdefault("domains", {})
    if not isinstance(domains, dict):
        raise StateError("`domains` must be an object keyed by domain id")
    unknown = sorted(set(domains) - set(DOMAINS))
    if unknown:
        raise StateError(
            "unknown domain ids in `domains`: " + ", ".join(unknown)
            + ". Valid ids: " + ", ".join(DOMAINS)
        )
    for key, entry in domains.items():
        if not isinstance(entry, dict):
            raise StateError(f"domain {key} must be an object")
        status = entry.get("status", "not-started")
        if status not in VALID_STATUS:
            raise StateError(
                f"domain {key} has status {status!r}; valid values are "
                + ", ".join(sorted(VALID_STATUS))
            )

    for field, kind in (("open_questions", list), ("decisions", list),
                        ("waivers", list), ("cost", dict), ("detected", dict),
                        ("project", dict)):
        state.setdefault(field, kind())
        if not isinstance(state[field], kind):
            raise StateError(f"`{field}` must be a {kind.__name__}")

    return state


def num(value) -> float | None:
    """A number from whatever the interview wrote, or None if there isn't one.

    The state file is written from a spoken conversation, so a price arrives as
    73, "73", "$73" or "73 USD" with equal likelihood. A gate that assumes float()
    will parse it dies with a traceback on the third form. None means "no number
    here" and the caller must say so rather than guessing a value.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.replace(" ", "")
        m = re.search(r"-?\d+(?:[\d,]*\d)?(?:\.\d+)?", text)
        if not m:
            return None
        try:
            n = float(m.group(0).replace(",", ""))
        except ValueError:
            return None
        # "1.2k" is 1200, not 1.2. Reading the digits and dropping the magnitude
        # would produce a confidently wrong figure, which is the one outcome the
        # cost rule exists to prevent.
        suffix = text[m.end():m.end() + 2].lower()
        for token, factor in (("bn", 1e9), ("b", 1e9), ("m", 1e6), ("k", 1e3)):
            if suffix.startswith(token):
                return n * factor
        return n
    return None


def answer_key_problems(state: dict) -> list[dict]:
    """Domains marked `complete` that a gate still cannot read.

    Only `complete` is checked. `not-applicable` means the domain was ruled out, so
    it owes no answers, and `partial` is by definition still being filled in.

    Unrecognised keys are reported only alongside a missing required one, as
    candidates for what the answer was actually called. On their own they are fine:
    the interview asks more than the gates read.
    """
    problems = []
    for domain, spec in ANSWER_KEYS.items():
        entry = state.get("domains", {}).get(domain, {})
        if entry.get("status") != "complete":
            continue
        present = set((entry.get("answers") or {}).keys())
        missing = sorted(spec["required"] - present)
        if not missing:
            continue
        unknown = sorted(present - spec["required"] - spec["optional"])
        problems.append({
            "domain": domain, "missing": missing, "unrecognised": unknown,
            "detail": (
                f"{domain} is marked complete but has no "
                + ", ".join(f"`{k}`" for k in missing)
                + (f". Found instead: " + ", ".join(f"`{k}`" for k in unknown)
                   + " — if one of those is the same answer under a different name, "
                     "rename it, because the gates read the key, not the meaning."
                   if unknown else
                   ". No answers here at all, so nothing can be checked.")),
        })
    return problems


def status_of(state: dict, domain: str) -> str:
    return state.get("domains", {}).get(domain, {}).get("status", "not-started")


def is_answered(state: dict, domain: str) -> bool:
    return status_of(state, domain) in ANSWERED


# One spelling per regime, for every gate. This lived in check_compliance.py, which
# meant check_contradictions.py had its own idea of what a regime is called and
# substring-matched against it: `["cscrf"]` with a US region passed the residency
# check clean, where the same regime spelled `["sebi-cscrf"]` failed it. Two gates
# holding divergent notions of the state file is the thing this module exists to
# prevent, and regime naming was the last piece still unshared.
REGIME_ALIASES = {
    "pci": "pci-dss", "pcidss": "pci-dss", "pci-dss-v4": "pci-dss",
    "dpdpa": "dpdp", "dpdp-act": "dpdp", "india-dpdp": "dpdp",
    "iso27001": "iso-27001", "iso-27001-2022": "iso-27001", "iso": "iso-27001",
    "soc-2": "soc2", "soc2-type-2": "soc2", "soc-2-type-ii": "soc2",
    "rbi-master-direction": "rbi", "sebi-cscrf": "sebi", "cscrf": "sebi",
    "gdpr-eu": "gdpr",
}


def normalise_regime(name: str) -> str:
    """A regime name as the control map spells it."""
    n = str(name).strip().lower().replace("_", "-").replace(" ", "-")
    return REGIME_ALIASES.get(n, n)


def unmapped_regimes(state: dict) -> list[str]:
    """Regimes the interview recorded that this build cannot map to controls.

    Two cases, one mechanism. A regime in the catalogue whose primary text was never
    sourced (SOC 2, HIPAA, ISO 27001 — see LIMITATIONS.md L1), and a regime that is
    real but outside the catalogue entirely, such as a national privacy act with no
    control file here. Both belong in the state file where the generation stage can
    see them; neither can be given a control list without inventing one.

    Naming one in `regimes` fails the compliance gate permanently and there is no
    waiver path, so "record it as an open question with an owner and continue" —
    which is what SKILL.md and domain-03 both instruct — used to be impossible to
    follow. This key is where it goes instead: the gate reports it prominently and
    passes, provided an open question with an owner and a date names it.

    Spelling is preserved rather than normalised: an entry here is often a regime
    with no slug in this repository at all, and `normalise_regime` would only mangle
    it. The compliance gate normalises when it needs to look one up.
    """
    answers = state.get("domains", {}).get("03-compliance", {}).get("answers", {})
    raw = answers.get("regimes_unmapped", [])
    if isinstance(raw, str):
        raw = [raw]
    return [str(r).strip() for r in raw if str(r).strip()]


def regimes(state: dict) -> list[str]:
    """Compliance regimes the interview recorded, as canonical slugs.

    Normalising here rather than at each call site is deliberate: a gate that reads
    regimes gets the same spelling as every other gate, so a lookup can be exact.
    """
    answers = state.get("domains", {}).get("03-compliance", {}).get("answers", {})
    raw = answers.get("regimes", [])
    if isinstance(raw, str):
        raw = [raw]
    return [normalise_regime(r) for r in raw if str(r).strip()]

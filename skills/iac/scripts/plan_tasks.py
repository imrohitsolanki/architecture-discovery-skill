#!/usr/bin/env python3
"""Turn the specification into a dependency-ordered task list for parallel generation.

Reach for this once, immediately after the preflight and before the first file. It
decides *what* gets generated and *in what order*, so that the work can be handed to
several agents at once without them writing over each other or inventing components
nobody asked for.

Inputs
    --state PATH    discovery-state.json. Required.
    --stack DIR     Where the stack will live, for the paths in the plan.
                    Default `infra`.
    --json          Emit the plan as JSON. This is the form an orchestrator reads.

Outputs
    The components this specification implies, grouped into waves. Everything in a
    wave is independent of everything else in it and can be generated in parallel;
    a wave starts only when the one before it is written and gated.

    Exit 0  a plan was produced.
    Exit 1  the specification implies no components at all, which means the state
            file is not finished rather than that there is nothing to build.
    Exit 2  the state file is missing or malformed.

Why a task list at all
    Generation is the one part of this plugin with real parallelism in it: six
    modules, each traceable to different domains, most of them independent. Done
    one at a time it is six sequential reads of the same state file. Done as a
    free-for-all it is six agents inventing six naming conventions and two of them
    writing the same log group.

    A wave plan is what makes the difference: within a wave the components genuinely
    do not touch each other, so they can be written at the same time by different
    agents; between waves there is a dependency, and the later one needs the earlier
    one's outputs to exist before its unit can even name them.

Why nothing is invented here
    Rule 1 of the skill — the specification is the only input — applies to the plan
    as much as to the code. A component appears in this plan only because an answer
    in the state file implies it, and every task carries the domains it came from so
    the provenance header can be written before the resource. A domain recorded
    `not-applicable` produces no task, and that is the correct output.

    Where the interview genuinely did not decide something, this prints it as a gap
    rather than inferring a component from the shape of the others.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _shared import DISCOVER_SCRIPTS  # noqa: E402

sys.path.insert(0, str(DISCOVER_SCRIPTS))
from _state import StateError, load, status_of  # noqa: E402

# The canonical apply order, stated once in references/layout.md and encoded here.
# A component's position in this list is what breaks a tie when two of them could
# own the same resource: the earlier one wins, because it applies first.
ORDER = ["registry", "network", "data", "identity", "compute", "edge",
         "messaging", "observability"]

# component -> (domains that decide it, what it holds, the words in an answer that
# imply it, dependencies)
#
# The trigger words are matched against the answers of the domains named, not against
# the whole state file: "cache" in a cost line is not a decision to build one.
COMPONENTS: dict[str, dict] = {
    "registry": {
        "domains": ["09-delivery", "02-app-shape"],
        "holds": "container registry and its lifecycle policy",
        "triggers": r"\b(registry|ecr|acr|artifact registry|gcr|image|container)",
        "depends_on": [],
    },
    "network": {
        "domains": ["07-networking", "04-cloud", "05-environments"],
        "holds": "VPC or virtual network, subnets, routing, egress, flow logs",
        "triggers": r".",  # any answer at all: everything else lands inside it
        "depends_on": [],
    },
    "data": {
        "domains": ["12-data-dr", "02-app-shape"],
        "holds": "databases, object storage, backups, encryption keys",
        "triggers": r"\b(database|rds|aurora|postgres|mysql|sql|mongo|dynamo|"
                    r"spanner|storage|bucket|blob|backup|snapshot)",
        "depends_on": ["network"],
    },
    "identity": {
        "domains": ["08-identity"],
        "holds": "roles, policies, workload identity, secret references",
        "triggers": r"\b(iam|role|identity|secret|vault|oidc|irsa|service account)",
        # Before compute, not after: a task definition takes its role ARNs as inputs.
        "depends_on": ["network"],
    },
    "compute": {
        "domains": ["06-compute", "02-app-shape"],
        "holds": "the platform the application runs on, and its autoscaling",
        "triggers": r"\b(eks|aks|gke|kubernetes|ecs|fargate|lambda|function|"
                    r"cloud run|container app|vm|instance|app runner|serverless)",
        "depends_on": ["network", "identity", "data"],
    },
    "edge": {
        "domains": ["07-networking", "11-security"],
        "holds": "CDN, WAF, DNS, certificates, and the response headers on them",
        "triggers": r"\b(cdn|cloudfront|front door|waf|shield|armor|dns|route ?53|"
                    r"certificate|acm|ingress|load balancer)",
        "depends_on": ["network", "compute"],
    },
    "messaging": {
        "domains": ["02-app-shape", "12-data-dr"],
        "holds": "queues, topics, streams and caches",
        "triggers": r"\b(queue|sqs|sns|kafka|msk|nats|pub/?sub|service bus|"
                    r"event hub|stream|cache|redis|valkey|memcached|elasticache)",
        "depends_on": ["network"],
    },
    "observability": {
        "domains": ["10-observability", "11-security"],
        "holds": "log destinations, metrics, alarms, audit trail, posture services",
        "triggers": r"\b(log|metric|trace|alarm|alert|dashboard|monitor|audit|"
                    r"cloudtrail|guardduty|security hub|posture)",
        "depends_on": ["compute"],
    },
}


def _answer_text(state: dict, domains: list[str]) -> str:
    out = []
    for domain in domains:
        entry = state.get("domains", {}).get(domain, {})
        if status_of(state, domain) == "not-applicable":
            continue
        for key, value in (entry.get("answers") or {}).items():
            values = value if isinstance(value, list) else [value]
            for v in values:
                if isinstance(v, (str, int, float, bool)):
                    out.append(f"{key} {v}")
        if entry.get("notes"):
            out.append(str(entry["notes"]))
    return " ".join(out).lower()


def environments(state: dict) -> list[str]:
    raw = (state.get("domains", {}).get("05-environments", {})
           .get("answers", {}) or {}).get("environments", [])
    if isinstance(raw, str):
        raw = [raw]
    return [str(e).strip().lower() for e in raw if str(e).strip()] or ["prod"]


def plan(state: dict, stack: str) -> dict:
    envs = environments(state)
    chosen: dict[str, dict] = {}
    skipped: list[dict] = []

    for name in ORDER:
        spec = COMPONENTS[name]
        # A domain ruled out produces nothing, and that is the correct output.
        live = [d for d in spec["domains"] if status_of(state, d) != "not-applicable"]
        text = _answer_text(state, spec["domains"])
        if not live or not text.strip():
            skipped.append({"component": name,
                            "why": "every domain that would decide it is "
                                   "not-applicable or unanswered"})
            continue
        if not re.search(spec["triggers"], text):
            skipped.append({"component": name,
                            "why": f"nothing in {', '.join(live)} names anything this "
                                   f"component would hold"})
            continue
        chosen[name] = spec

    tasks = []
    for name, spec in chosen.items():
        deps = [d for d in spec["depends_on"] if d in chosen]
        tasks.append({
            "id": name,
            "module": f"{stack}/modules/{name}",
            "units": [f"{stack}/live/{env}/{name}" for env in envs],
            "holds": spec["holds"],
            "domains": [d for d in spec["domains"]
                        if status_of(state, d) != "not-applicable"],
            "depends_on": deps,
        })

    # Waves: everything whose dependencies are already placed. The order within a
    # wave is irrelevant by construction, which is exactly what makes it safe to
    # hand each task to a different agent at the same time.
    waves: list[list[dict]] = []
    placed: set[str] = set()
    remaining = list(tasks)
    while remaining:
        wave = [t for t in remaining if set(t["depends_on"]) <= placed]
        if not wave:
            # Only reachable if COMPONENTS itself has a cycle, which the harness
            # asserts it does not. Reported rather than looping forever.
            waves.append(remaining)
            break
        waves.append(wave)
        placed |= {t["id"] for t in wave}
        remaining = [t for t in remaining if t["id"] not in placed]

    return {
        "stack": stack,
        "environments": envs,
        "tasks": tasks,
        "waves": [[t["id"] for t in wave] for wave in waves],
        "wave_detail": waves,
        "skipped": skipped,
        "ok": bool(tasks),
    }


def render(p: dict) -> str:
    out: list[str] = []
    out.append(f"Stack root: {p['stack']}")
    out.append(f"Environments: {', '.join(p['environments'])}")
    out.append("")
    if not p["tasks"]:
        out.append("No component is implied by this specification. That is a state "
                   "file that is not finished, not a system with nothing in it — "
                   "run the discovery gates before generating.")
        return "\n".join(out)

    for i, wave in enumerate(p["wave_detail"], 1):
        parallel = ("one task, so nothing to parallelise" if len(wave) == 1
                    else f"{len(wave)} tasks, independent of each other — generate "
                         f"them at the same time")
        out.append(f"Wave {i} ({parallel}):")
        out.append("")
        for task in wave:
            out.append(f"  {task['id']}")
            out.append(f"      holds:   {task['holds']}")
            out.append(f"      module:  {task['module']}")
            out.append(f"      units:   {', '.join(task['units'])}")
            out.append(f"      reads:   {', '.join(task['domains'])}")
            out.append(f"      after:   {', '.join(task['depends_on']) or 'nothing'}")
        out.append("")

    out.append("Every task in a wave is written, gated and reviewed before the next "
               "wave starts. The dependency is real: a unit in wave 2 names an "
               "output of a unit in wave 1, and a `config_path` pointing at a "
               "directory that does not exist yet fails `terragrunt hcl validate` "
               "rather than waiting for it.")

    if p["skipped"]:
        out.append("")
        out.append("Not generated, and that is the correct output — a component "
                   "nobody asked for is the characteristic failure of a generator:")
        for s in p["skipped"]:
            out.append(f"  {s['component']}: {s['why']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state", required=True)
    ap.add_argument("--stack", default="infra")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        state = load(args.state)
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    p = plan(state, args.stack.rstrip("/"))
    print(json.dumps(p, indent=2) if args.json else render(p))
    return 0 if p["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Check the repository still hangs together: links, routing, versions, permissions.

Run it after changing anything outside `scripts/`, and in CI on every push:

    python3 scripts/check_repo.py

Exit 0  every reference resolves and every declaration agrees with reality.
Exit 1  something points at something that is not there.

Why this exists as a third harness
    The two gate harnesses prove the gates catch what they exist to catch. Neither
    can see the layer above: a routing table in `SKILL.md` naming a reference file
    that was renamed, a `metadata.version` that drifted from `plugin.json`, a
    documentation anchor that died when a heading was reworded, an entry-point
    script that lost its executable bit.

    None of those break a gate. All of them break the skill, quietly — a reference
    the model is told to read and cannot is an instruction with nothing behind it,
    and a missing executable bit costs a permission prompt the grant was written to
    avoid.

    It is the honest, cheap slice of the end-to-end test this repository does not
    have. It does not drive an interview or plan a stack, and it does not pretend to:
    it checks that everything those would need is where the repository says it is.

Every check is static. Nothing is executed, nothing is fetched, no model is called.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MARKDOWN = ["README.md", "LIMITATIONS.md", "CHANGELOG.md",
            "docs/HOW-IT-WORKS.md", "docs/DISCOVERY.md", "docs/GENERATION.md",
            "docs/GUARDRAILS.md"]

# Repeated `### Added` per release is the Keep a Changelog format, not a defect.
DUPLICATE_HEADINGS_OK = {"CHANGELOG.md"}

SKILLS = ["skills/discover", "skills/iac"]

FRONTMATTER_REQUIRED = ("name", "description", "when_to_use", "allowed-tools",
                        "metadata", "license")


def slug(heading: str) -> str:
    text = heading.strip().lower().replace("`", "")
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text).strip("-")


def headings(text: str) -> set[str]:
    return {slug(m.group(1)) for m in re.finditer(r"(?m)^#{1,6}\s+(.*)$", text)}


def frontmatter(path: Path) -> tuple[str, str]:
    """(raw frontmatter, body). Empty frontmatter when the file has none."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    return (m.group(1), m.group(2)) if m else ("", text)


def check_markdown_links() -> list[str]:
    """Every relative link resolves, and every anchor names a real heading."""
    problems = []
    indexed = {}
    for rel in MARKDOWN:
        path = ROOT / rel
        if not path.is_file():
            problems.append(f"{rel} is listed in MARKDOWN but does not exist")
            continue
        text = path.read_text(encoding="utf-8")
        indexed[rel] = (text, headings(text))

    for rel, (text, _) in indexed.items():
        base = (ROOT / rel).parent
        for m in re.finditer(r"\[[^\]]*\]\(([^)\s]+)\)", text):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            file_part, _, anchor = target.partition("#")
            key = rel
            if file_part:
                resolved = (base / file_part).resolve()
                if not resolved.exists():
                    problems.append(f"{rel}: link to a missing file — {target}")
                    continue
                try:
                    key = str(resolved.relative_to(ROOT))
                except ValueError:
                    continue
            if anchor and key in indexed and anchor not in indexed[key][1]:
                problems.append(f"{rel}: dangling anchor — {target}")

    for rel, (text, _) in indexed.items():
        if rel in DUPLICATE_HEADINGS_OK:
            continue
        seen: dict[str, int] = {}
        for m in re.finditer(r"(?m)^#{1,6}\s+(.*)$", text):
            s = slug(m.group(1))
            seen[s] = seen.get(s, 0) + 1
        for anchor, count in seen.items():
            if count > 1:
                problems.append(
                    f"{rel}: {count} headings share the anchor `#{anchor}`, so every "
                    f"link to it reaches whichever comes first")
    return problems


def check_skill_frontmatter() -> list[str]:
    """Frontmatter parses, carries what the harness depends on, and agrees on version."""
    problems = []
    try:
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    except Exception as exc:  # noqa: BLE001
        return [f".claude-plugin/plugin.json is unreadable: {exc}"]

    for skill in SKILLS:
        path = ROOT / skill / "SKILL.md"
        if not path.is_file():
            problems.append(f"{skill}/SKILL.md is missing")
            continue
        raw, _ = frontmatter(path)
        if not raw:
            problems.append(f"{skill}/SKILL.md has no `---` frontmatter block, so the "
                            f"skill will not load at all")
            continue
        for key in FRONTMATTER_REQUIRED:
            if not re.search(rf"(?m)^{re.escape(key)}:", raw):
                problems.append(f"{skill}/SKILL.md frontmatter has no `{key}:`")

        version = re.search(r"(?m)^\s+version:\s*\"?([\d.]+)\"?", raw)
        if version and version.group(1) != manifest.get("version"):
            problems.append(
                f"{skill}/SKILL.md declares version {version.group(1)} but "
                f"plugin.json says {manifest.get('version')}. The manifest version is "
                f"the release, so a drift here ships one number and announces "
                f"another.")
    return problems


def check_allowed_tools() -> list[str]:
    """Every granted script exists and is executable.

    A Bash permission rule matches a direct invocation, which needs the executable
    bit. Without it the script still runs via `python3 <path>`, but that command
    matches no rule and prompts — exactly what the grant was written to avoid.
    """
    problems = []
    for skill in SKILLS:
        raw, _ = frontmatter(ROOT / skill / "SKILL.md")
        for m in re.finditer(r"Bash\(\$\{CLAUDE_SKILL_DIR\}/([^\s)]+)", raw):
            target = ROOT / skill / m.group(1)
            if not target.is_file():
                problems.append(f"{skill}/SKILL.md grants `{m.group(1)}`, which does "
                                f"not exist")
            elif not target.stat().st_mode & 0o111:
                problems.append(
                    f"{skill}/{m.group(1)} is granted in allowed-tools but is not "
                    f"executable, so the rule cannot match and it will prompt. "
                    f"Run: chmod +x {skill}/{m.group(1)}")
    return problems


def check_skill_references() -> list[str]:
    """Every `references/`, `assets/` and `scripts/` path a SKILL.md names exists."""
    problems = []
    pattern = re.compile(r"`(?:\$\{CLAUDE_SKILL_DIR\}/)?((?:references|assets|scripts)"
                         r"/[\w./*-]+)`")
    for skill in SKILLS:
        text = (ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
        for m in pattern.finditer(text):
            named = m.group(1)
            if "*" in named or "NN" in named:
                # `domain-NN*.md` is how SKILL.md writes the family, with NN standing
                # for the domain number rather than being two literal characters.
                if not list((ROOT / skill).glob(named.replace("NN", "[0-9][0-9]"))):
                    problems.append(f"{skill}/SKILL.md names `{named}`, which matches "
                                    f"nothing")
            elif not (ROOT / skill / named).exists():
                problems.append(f"{skill}/SKILL.md names `{named}`, which does not "
                                f"exist")
    return problems


def check_domain_references() -> list[str]:
    """Every domain the state contract defines has reference material to load.

    `SKILL.md` routes the model to `references/domain-NN*.md` on the first turn of a
    domain. A domain added to `_state.DOMAINS` without one leaves that instruction
    pointing at nothing, and the model improvises the questions.
    """
    sys.path.insert(0, str(ROOT / "skills" / "discover" / "scripts"))
    try:
        import _state
    except Exception as exc:  # noqa: BLE001
        return [f"skills/discover/scripts/_state.py will not import: {exc}"]

    problems = []
    refs = ROOT / "skills" / "discover" / "references"
    for domain in _state.DOMAINS:
        number = domain.split("-")[0]
        if not list(refs.glob(f"domain-{number}*.md")):
            problems.append(f"domain `{domain}` is in _state.DOMAINS but no "
                            f"references/domain-{number}*.md exists")

    try:
        controls = json.loads(
            (ROOT / "skills" / "discover" / "scripts"
             / "compliance_controls.json").read_text())["regimes"]
    except Exception as exc:  # noqa: BLE001
        return problems + [f"compliance_controls.json is unreadable: {exc}"]

    for regime in controls:
        if not (refs / "compliance" / f"{regime}.md").is_file():
            problems.append(f"regime `{regime}` is in compliance_controls.json but no "
                            f"references/compliance/{regime}.md exists")
    return problems


# Capabilities the interview can decide, and the words that identify a row for one.
# The mapping file is what turns a decision into resources, so a capability the
# interview offers and `providers.md` has no row for is a decision the generator
# meets with nothing — which is how a CDN, a WAF, a queue, a cache and a posture
# service came to be written with no guidance at all, and how the content-security
# header, a named PCI-DSS control, went missing from a stack that passed every gate.
#
# Anchored at both ends: each capability must appear in a domain reference file, so
# the list tracks what the interview actually asks, and must have a row in every
# provider table, so the mapping cannot fall behind it.
PROVIDER_CAPABILITIES: dict[str, str] = {
    "network": r"\b(vpc|virtual network|virtual_network|compute_network|subnet)",
    "ingress": r"\b(ingress|load balancer|_lb\b|application_gateway|forwarding_rule)",
    "cdn": r"\b(cdn|cloudfront|frontdoor|front door|enable_cdn)",
    "waf": r"\b(waf|firewall_policy|cloud armor|security_policy)",
    "dns": r"\b(dns|route 53|route53)",
    "queue": r"\b(queue|sqs|servicebus|pubsub|pub/sub|eventhub|kafka|msk)",
    "cache": r"\b(cache|redis|elasticache|memorystore|valkey|memcached)",
    "database": r"\b(database|rds|sql|spanner|postgres)",
    "object storage": r"\b(object storage|bucket|storage_account|blob)",
    "secrets": r"\b(secret|key vault|key_vault|secretsmanager|secret_manager)",
    "workload identity": r"\b(identity|iam_role|service_account|federated)",
    "logs": r"\b(log|logging|log_analytics|cloudwatch)",
    "autoscaling": r"\b(autoscal|auto_scaling|karpenter|hpa|keda)",
    "posture": r"\b(guardduty|security ?hub|security center|security command|posture|falco|prowler)",
}

PROVIDER_SECTIONS = ("AWS", "Azure", "GCP")


def check_provider_coverage() -> list[str]:
    """Every capability the interview offers has a row for every provider table."""
    path = ROOT / "skills" / "iac" / "references" / "providers.md"
    if not path.is_file():
        return ["skills/iac/references/providers.md is missing, so no decision can "
                "be turned into resources"]
    text = path.read_text(encoding="utf-8")

    sections: dict[str, str] = {}
    for name in PROVIDER_SECTIONS:
        m = re.search(rf"(?m)^##\s+{re.escape(name)}\s*$", text)
        if not m:
            return [f"providers.md has no `## {name}` section, so the coverage check "
                    f"cannot run — and a check that cannot run has not passed"]
        rest = text[m.end():]
        nxt = re.search(r"(?m)^##\s+", rest)
        sections[name] = (rest[:nxt.start()] if nxt else rest).lower()

    domain_text = "\n".join(
        p.read_text(encoding="utf-8").lower()
        for p in sorted((ROOT / "skills" / "discover" / "references").glob("domain-*.md")))

    problems = []
    for capability, pattern in PROVIDER_CAPABILITIES.items():
        if not re.search(pattern, domain_text):
            problems.append(
                f"`{capability}` is in PROVIDER_CAPABILITIES but no domain reference "
                f"file mentions it — either the interview stopped asking about it, "
                f"or this list has drifted from the interview")
        for name, body in sections.items():
            if not re.search(pattern, body):
                problems.append(
                    f"providers.md `## {name}` has no row for `{capability}`, which "
                    f"the interview can decide. A decision the mapping file cannot "
                    f"map is one the generator writes from nothing.")
    return problems


def check_hooks() -> list[str]:
    """hooks/hooks.json exists and can run.

    A plugin's `hooks/hooks.json` loads by convention — the CLI rejects a manifest
    that also declares `hooks` explicitly as a duplicate. So there is nothing to
    read from plugin.json here; the file at the conventional path is the contract.
    """
    problems = []
    declared = "./hooks/hooks.json"
    hooks_path = (ROOT / declared.lstrip("./")).resolve()
    if not hooks_path.is_file():
        return [f"{declared} does not exist, so the guardrail hook never loads "
                "and rule 3 of generation is prose again"]

    try:
        hooks = json.loads(hooks_path.read_text())
    except Exception as exc:  # noqa: BLE001
        return [f"{declared} is not valid JSON: {exc}"]

    entries = hooks.get("hooks", {}).get("PreToolUse", [])
    if not entries:
        problems.append(f"{declared} declares no PreToolUse hook")
    for entry in entries:
        for hook in entry.get("hooks", []):
            command = str(hook.get("command", ""))
            m = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}\"?/(\S+)", command)
            if not m:
                problems.append(f"{declared}: hook command does not resolve through "
                                f"${{CLAUDE_PLUGIN_ROOT}} — {command}")
                continue
            target = ROOT / m.group(1).strip('"')
            if not target.is_file():
                problems.append(f"{declared} points at {m.group(1)}, which does not "
                                f"exist")
            elif not target.stat().st_mode & 0o111:
                problems.append(f"{m.group(1)} is not executable, so the hook silently "
                                f"never runs. Run: chmod +x {m.group(1)}")
    return problems


def check_agents() -> list[str]:
    """Every agent the plugin declares exists, parses, and is named where it is used.

    A subagent is loaded by name. A `SKILL.md` telling the model to launch
    `iac-builder` when no such agent is installed fails at the moment of fan-out,
    several steps into a generation — and the failure reads as the model being
    unable to follow an instruction rather than as a missing file.
    """
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    declared = manifest.get("agents")
    if not declared:
        return []
    if not isinstance(declared, list):
        return [f"plugin.json points `agents` at {declared!r}, which is not a list "
                f"of file paths"]

    problems, names = [], set()
    paths = []
    for entry in declared:
        path = (ROOT / str(entry).lstrip("./")).resolve()
        if not path.is_file():
            problems.append(f"plugin.json lists agent {entry}, which does not exist")
            continue
        paths.append(path)
    for path in sorted(paths):
        raw, body = frontmatter(path)
        if not raw:
            problems.append(f"{path.relative_to(ROOT)} has no `---` frontmatter, so "
                            f"it will not load as an agent")
            continue
        for key in ("name", "description"):
            if not re.search(rf"(?m)^{key}:", raw):
                problems.append(f"{path.relative_to(ROOT)} frontmatter has no `{key}:`")
        m = re.search(r"(?m)^name:\s*(\S+)", raw)
        if m:
            names.add(m.group(1))
            if m.group(1) != path.stem:
                problems.append(
                    f"{path.relative_to(ROOT)} declares name `{m.group(1)}`, which "
                    f"does not match its filename — the file name is what a reader "
                    f"looks for and the frontmatter is what loads")
        if not body.strip():
            problems.append(f"{path.relative_to(ROOT)} has frontmatter and no body, "
                            f"so the agent has no instructions")

    # And the other direction: an agent named in a SKILL.md has to exist.
    for skill in SKILLS:
        text = (ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
        for m in re.finditer(r"`(iac-[a-z-]+)`", text):
            if m.group(1) not in names:
                problems.append(f"{skill}/SKILL.md names the agent `{m.group(1)}`, "
                                f"which {declared} does not define")
    return problems


def check_marketplace() -> list[str]:
    path = ROOT / ".claude-plugin" / "marketplace.json"
    try:
        data = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        return [f"marketplace.json is unreadable: {exc}"]
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    names = {p.get("name") for p in data.get("plugins", [])}
    if manifest.get("name") not in names:
        return [f"marketplace.json lists {sorted(names)}, which does not include "
                f"`{manifest.get('name')}` from plugin.json, so "
                f"`/plugin install` cannot resolve it"]
    return []


CHECKS = (
    ("markdown links and anchors", check_markdown_links),
    ("skill frontmatter and version agreement", check_skill_frontmatter),
    ("allowed-tools grants are runnable", check_allowed_tools),
    ("references a SKILL.md names exist", check_skill_references),
    ("every domain and regime has reference material", check_domain_references),
    ("providers.md covers what the interview can decide", check_provider_coverage),
    ("the guardrail hook is wired up", check_hooks),
    ("the agents the plugin ships are loadable", check_agents),
    ("the marketplace entry resolves", check_marketplace),
)


def main() -> int:
    failed = 0
    print("Repository selftest\n")
    for label, check in CHECKS:
        try:
            problems = check()
        except Exception as exc:  # noqa: BLE001 — a broken check is a failure
            problems = [f"the check itself raised {exc.__class__.__name__}: {exc}"]
        if problems:
            failed += len(problems)
            print(f"  FAIL  {label}")
            for problem in problems:
                print(f"          {problem}")
        else:
            print(f"  ok    {label}")
    print("")
    if failed:
        print(f"{failed} problem(s). Each one is something the repository declares and "
              f"does not have — an instruction pointing at nothing, which fails "
              f"silently at the moment somebody relies on it.")
        return 1
    print("Everything the repository declares, it has.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

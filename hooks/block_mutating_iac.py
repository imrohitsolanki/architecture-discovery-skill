#!/usr/bin/env python3
"""Refuse to apply, destroy or mutate the state of a stack this plugin generated.

A `PreToolUse` hook on `Bash`. It reads the tool call on stdin and denies the
mutating Terraform, OpenTofu and Terragrunt verbs when the command targets a
directory this plugin generated and nobody has taken ownership of yet.

Why a hook and not a rule in SKILL.md
    `SKILL.md` already says never apply. That is an instruction, and an instruction
    is not an enforcement: nothing in the repository could stop the model running
    `terraform apply` except its own compliance, which was `LIMITATIONS.md` L14 and
    the one prompt rule whose absence of a check mattered most. This closes it.

Why it is scoped to generated stacks rather than to every terraform command
    A plugin's hooks run in every session where the plugin is enabled, not only
    while its skill is active. A hook that denied `terraform apply` everywhere would
    break ordinary infrastructure work in unrelated repositories — the guardrail
    would be uninstalled within a day, and the real protection would go with it.

    So the scope is exactly what this plugin is responsible for: a stack it wrote,
    which by definition no human has reviewed. The skill drops a marker file at the
    root of the tree it generates; this hook walks up from the command's working
    directory looking for one.

The marker is the handover
    `.architecture-discovery.json` says "this was generated from a specification and
    nobody has taken ownership of it". Deleting it is how a person says they have
    read the plan and accept what applying it does. That is a deliberate, one-line
    action by a human, which is the correct shape for this decision — not a flag the
    model can pass.

Fails open, always
    Any error, any unparseable input, any unexpected shape: exit 0 and say nothing.
    A guardrail that breaks the session when it malfunctions is a guardrail people
    disable. Denying is the exception; the default is silence.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

MARKER = ".architecture-discovery.json"

# Walking up forever would let a marker in a home directory govern the whole
# machine. Twenty levels is more than any real tree and bounded.
MAX_ASCENT = 20

TOOLS = ("terraform", "tofu", "terragrunt")

# Verbs that change infrastructure or the state that describes it. `plan`,
# `validate`, `fmt`, `show`, `output` and `init` are absent on purpose: they are how
# the stack gets checked, and blocking them would block the review this exists to
# protect.
MUTATING = (
    "apply", "destroy", "import", "taint", "untaint", "force-unlock",
)
# `state` and `workspace` are only mutating in some of their subcommands.
STATE_SUBCOMMANDS = ("mv", "rm", "push", "replace-provider")
WORKSPACE_SUBCOMMANDS = ("delete", "new")


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def mutating_verb(tokens: list[str]) -> str | None:
    """The mutating verb in this command, or None.

    Token-based rather than substring: `terraform plan -out=apply.tfplan` contains
    the word apply and must not match, and a directory named `destroy-me` must not
    either.
    """
    if not any(t in TOOLS or t.endswith("/" + t.split("/")[-1]) and
               t.split("/")[-1] in TOOLS for t in tokens):
        return None

    for i, token in enumerate(tokens):
        if token in MUTATING:
            return token
        if token == "state" and i + 1 < len(tokens) and tokens[i + 1] in STATE_SUBCOMMANDS:
            return f"state {tokens[i + 1]}"
        if token == "workspace" and i + 1 < len(tokens) and \
                tokens[i + 1] in WORKSPACE_SUBCOMMANDS:
            return f"workspace {tokens[i + 1]}"
    return None


def target_dirs(command: str, cwd: str) -> list[Path]:
    """Every directory the command might act on. Best effort, deliberately generous.

    A command can change directory before it runs, or be pointed elsewhere with
    `-chdir`, `--working-dir` or a trailing path. Missing one of those and letting
    an apply through is the expensive direction, so every candidate is checked and
    any one of them carrying a marker is enough to deny.
    """
    candidates = [Path(cwd or ".")]
    base = Path(cwd or ".")

    for path in re.findall(r"(?:^|&&|;|\|)\s*cd\s+([^\s;&|]+)", command):
        candidates.append((base / path.strip("'\"")).resolve()
                          if not path.startswith("/") else Path(path.strip("'\"")))
    for path in re.findall(r"-chdir=([^\s]+)", command):
        candidates.append(base / path.strip("'\""))
    for path in re.findall(r"--working-dir[= ]([^\s]+)", command):
        candidates.append(base / path.strip("'\""))

    return candidates


def marker_above(start: Path) -> Path | None:
    try:
        here = start.resolve()
    except OSError:
        return None
    for _ in range(MAX_ASCENT):
        candidate = here / MARKER
        if candidate.is_file():
            return candidate
        if here.parent == here:
            break
        here = here.parent
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — a malformed payload must never block a session
        return 0

    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command:
        return 0

    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    verb = mutating_verb(tokens)
    if verb is None:
        return 0

    for directory in target_dirs(command, payload.get("cwd") or ""):
        marker = marker_above(directory)
        if marker is None:
            continue

        detail = ""
        try:
            info = json.loads(marker.read_text(encoding="utf-8"))
            spec = info.get("specification")
            generated = info.get("generated")
            detail = (f" It was generated from {spec}"
                      + (f" on {generated}" if generated else "") + ".") if spec else ""
        except Exception:  # noqa: BLE001 — the marker existing is the signal
            pass

        deny(
            f"Refused: `{verb}` against a stack that was generated from a "
            f"specification and that nobody has taken ownership of yet.{detail}\n\n"
            f"This stack has never been planned against a real account. The "
            f"generation gate checks it is pinned, traceable and valid; it cannot "
            f"check that quotas, service control policies, or what already exists in "
            f"the account will let these resources apply.\n\n"
            f"A person reviews the plan and then takes ownership by deleting "
            f"{marker}. That is a deliberate one-line action by a human, which is "
            f"the right shape for this decision — it is not a flag to pass here.\n\n"
            f"`plan`, `validate`, `fmt`, `init`, `show` and `output` are not "
            f"blocked; they are how the review happens."
        )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 — fail open, always
        sys.exit(0)

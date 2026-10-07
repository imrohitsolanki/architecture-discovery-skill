"""Reach the discovery skill's shared modules from the IaC skill.

Generation reads the same `discovery-state.json` that the interview wrote, so it needs the
same contract — `DOMAINS`, `BLOCKING`, `ANSWER_KEYS`, `normalise_regime`. Copying
those here would give the plugin two ideas of what a state file is, and they would
disagree within a week. `_state.py` in the discovery skill is the one definition;
this module is only the import path to it.

It also resolves the discovery skill's gate scripts, because `check_iac.py`
runs `run_gates.py` and `scan_secrets.py` as subprocesses rather than reimplementing
them, and the plugin root, so the harness can exercise the `PreToolUse` hook that
enforces rule 3. A subprocess of an already-permitted command needs no permission rule of its
own, which is why the IaC skill's `allowed-tools` stays at two lines.

The path is relative and structural: `skills/<skill>/scripts/`, so `parents[2]` is
`skills/`. If the plugin layout ever changes, this raises at import with a message
naming what it looked for, rather than failing later as a confusing NameError.
"""

from __future__ import annotations

import sys
from pathlib import Path

DISCOVER_SCRIPTS = Path(__file__).resolve().parents[2] / "discover" / "scripts"

if not (DISCOVER_SCRIPTS / "_state.py").is_file():
    raise ImportError(
        f"the discovery skill's scripts are not where this expects them: looked in "
        f"{DISCOVER_SCRIPTS}. The IaC skill reads the state file the discovery "
        f"skill writes, so the two ship together; an IaC skill installed on its "
        f"own has nothing to generate from."
    )

if str(DISCOVER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DISCOVER_SCRIPTS))

PLUGIN_ROOT = DISCOVER_SCRIPTS.parents[2]
BLOCK_MUTATING_IAC = PLUGIN_ROOT / "hooks" / "block_mutating_iac.py"

RUN_GATES = DISCOVER_SCRIPTS / "run_gates.py"
SCAN_SECRETS = DISCOVER_SCRIPTS / "scan_secrets.py"

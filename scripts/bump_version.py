#!/usr/bin/env python3
"""Bump the plugin version everywhere it is declared, in one step.

    python3 scripts/bump_version.py 1.1.0

Writes the new version to `.claude-plugin/plugin.json`, every skill's
`metadata.version`, and `CHANGELOG.md` — renaming `## [Unreleased]` to the new
release if there is one, otherwise adding an empty release heading to fill in.
`check_repo.py` fails if any of them disagree, so run it afterwards.
"""
from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ["skills/discover", "skills/iac"]


def replace(path: Path, pattern: str, repl: str) -> None:
    text = path.read_text()
    new, count = re.subn(pattern, repl, text, count=1, flags=re.M)
    if count != 1:
        sys.exit(f"{path.relative_to(ROOT)}: no version found to replace")
    path.write_text(new)


def main() -> int:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        sys.exit("usage: bump_version.py MAJOR.MINOR.PATCH")
    version = sys.argv[1]
    today = datetime.date.today().isoformat()

    replace(ROOT / ".claude-plugin" / "plugin.json",
            r'("version":\s*")[\d.]+(")', rf"\g<1>{version}\g<2>")
    for skill in SKILLS:
        replace(ROOT / skill / "SKILL.md",
                r'^(\s+version:\s*")[\d.]+(")', rf"\g<1>{version}\g<2>")

    changelog = ROOT / "CHANGELOG.md"
    text = changelog.read_text()
    if re.search(r"(?m)^## \[Unreleased\]", text):
        replace(changelog, r"^## \[Unreleased\].*$", f"## [{version}] - {today}")
    else:
        replace(changelog, r"^(## \[[\d.]+\])",
                rf"## [{version}] - {today}\n\n### Changed\n\n- \n\n\g<1>")
        print(f"CHANGELOG.md: fill in the empty {version} entry")

    print(f"Bumped to {version}. Run python3 scripts/check_repo.py to confirm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

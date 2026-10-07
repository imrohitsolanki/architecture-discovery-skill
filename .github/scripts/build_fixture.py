#!/usr/bin/env python3
"""Write the harness's clean fixture stack to a directory, for CI to gate for real.

The generation harness skips `fmt` and `validate`: they need both IaC binaries and a
reachable registry, and a test that fails on a train is a test that gets deleted. CI
has both, so it builds the same fixture and puts it through all eight gates.

Same fixture, deliberately. A second definition of "a clean stack" would drift from
the one the harness asserts against, and then the two would disagree about what is
being tested.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills" / "iac" / "scripts"))

from selftest import CLEAN_STATE, CLEAN_TF, write_artifacts, write_tree  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_fixture.py <directory>", file=sys.stderr)
        return 2
    base = pathlib.Path(sys.argv[1])
    write_artifacts(base / "artifacts", CLEAN_STATE)
    write_tree(base / "stack", CLEAN_TF)
    print(f"fixture stack written to {base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

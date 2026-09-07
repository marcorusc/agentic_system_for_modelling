#!/usr/bin/env python3
"""Run all Codex and Claude regression suites without external dependencies."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITES = ("tests/codex", ".claude/scripts", "tests/setup")


def main() -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required.", file=sys.stderr)
        return 2
    failed = False
    for suite in SUITES:
        print(f"Running {suite}", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", suite, "-v"],
            cwd=ROOT,
            check=False,
        )
        failed = failed or result.returncode != 0
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

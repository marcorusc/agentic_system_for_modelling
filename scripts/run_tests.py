#!/usr/bin/env python3
"""Run all Codex and Claude regression suites without external dependencies."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITES = ("tests/codex", ".claude/scripts", "tests/setup")
SUITE_TIMEOUT_SECONDS = 120


def run_suite(suite: str) -> int:
    # Stop fixtures that inherit the suite process group on timeout, without
    # signalling the caller or another suite. Detached groups are not covered.
    with subprocess.Popen(
        [sys.executable, "-m", "unittest", "discover", "-s", suite, "-v"],
        cwd=ROOT,
        start_new_session=os.name == "posix",
    ) as process:
        try:
            return process.wait(timeout=SUITE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            print(
                f"FAILED: {suite} timed out after {SUITE_TIMEOUT_SECONDS} seconds; "
                "test completion was not verified.",
                file=sys.stderr,
                flush=True,
            )
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # The suite exited between the timeout and signal.
            else:
                process.kill()
            process.wait()
            return 124


def main() -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required.", file=sys.stderr)
        return 2
    failed = False
    for suite in SUITES:
        print(f"Running {suite}", flush=True)
        return_code = run_suite(suite)
        failed = failed or return_code != 0
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

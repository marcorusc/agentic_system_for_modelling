#!/usr/bin/env python3
"""Validate literature-reviewer Read and Write tool calls.

Claude Code passes PreToolUse hook input as JSON on stdin. This guard deliberately
uses only the Python standard library so the literature reviewer does not depend on
an external JSON parser such as jq.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import NoReturn


def deny(message: str) -> NoReturn:
    """Block the tool call with an actionable message for the reviewer."""

    print(f"literature-reviewer file guard: {message}", file=sys.stderr)
    raise SystemExit(2)


def resolved(path: Path, description: str) -> Path:
    """Resolve a path without requiring its final component to exist."""

    try:
        return path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as error:
        deny(f"could not resolve {description}: {error}")


def is_strictly_below(path: Path, directory: Path) -> bool:
    """Return True only when path is a descendant, not directory itself."""

    if path == directory:
        return False
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def load_hook_input() -> tuple[str, Path]:
    """Parse and validate the common tool-call fields used by this guard."""

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as error:
        deny(f"invalid hook JSON input: {error}")

    if not isinstance(payload, dict):
        deny("hook input must be a JSON object")

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if tool_name not in {"Read", "Write"}:
        deny(f"unexpected tool_name {tool_name!r}; expected 'Read' or 'Write'")
    if not isinstance(tool_input, dict):
        deny("tool_input must be a JSON object")

    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        deny("tool_input.file_path must be a non-empty string")

    candidate = Path(file_path)
    if not candidate.is_absolute():
        deny("tool_input.file_path must be absolute")
    return tool_name, candidate


def validate_write(candidate: Path) -> None:
    """Allow report writes only and ensure their parent directory exists."""

    project_value = os.environ.get("CLAUDE_PROJECT_DIR")
    if not project_value:
        deny("CLAUDE_PROJECT_DIR is not set")

    project_root = resolved(Path(project_value), "CLAUDE_PROJECT_DIR")
    reports_root = resolved(project_root / "evidence" / "reports", "report root")
    if not is_strictly_below(reports_root, project_root):
        deny("evidence/reports resolves outside the project root")

    target = resolved(candidate, "write target")
    if not is_strictly_below(target, reports_root):
        deny(
            "Write is allowed only below "
            f"{project_root / 'evidence' / 'reports'}; requested {candidate}"
        )

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        deny(f"could not create report directory {target.parent}: {error}")


def validate_read(candidate: Path) -> None:
    """Prevent expensive full-file reads of queue and SIF artifacts."""

    if candidate.name == "literature_queue.json" or candidate.suffix.lower() == ".sif":
        deny(
            "do not Read literature_queue.json or .sif files in full; "
            "use Grep to retrieve only the lines for the requested edges"
        )


def main() -> int:
    tool_name, candidate = load_hook_input()
    if tool_name == "Write":
        validate_write(candidate)
    else:
        validate_read(candidate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate the provider-neutral typed specialist handoff contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1
SESSION_ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
STATUSES = {"completed", "blocked", "needs_approval", "failed"}
SPECIALIST_STAGES = {
    "network_curator": "neko_network",
    "literature_reviewer": "literature_review",
    "boolean_dynamics_modeler": "maboss_dynamics",
    "multicellular_configurator": "physicell_configuration",
}
SAFE_NEXT_STAGES = {
    "neko_network": {None, "literature_review", "researcher_approval"},
    "literature_review": {None, "researcher_approval"},
    "maboss_dynamics": {None, "researcher_approval"},
    "physicell_configuration": {None, "researcher_approval"},
}
ARTIFACT_ROOTS = {
    "network_curator": ("runs/network-curator",),
    "literature_reviewer": ("evidence/reports",),
    "boolean_dynamics_modeler": ("runs/boolean-dynamics-modeler",),
    "multicellular_configurator": ("runs/multicellular-configurator",),
}
REQUIRED_FIELDS = {
    "schema_version",
    "specialist",
    "status",
    "stage",
    "session_id",
    "derived_from_session_id",
    "actions",
    "assumptions",
    "decisions_required",
    "artifacts",
    "validation",
    "recommended_next_stage",
}


class HandoffValidationError(ValueError):
    """A specialist result violates the common handoff contract."""


def _session(value: object, field: str, *, nullable: bool = True) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or SESSION_ID.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise HandoffValidationError(f"{field} must be a safe session identifier{suffix}")
    return value


def _list_field(handoff: dict[str, Any], field: str) -> list[Any]:
    value = handoff[field]
    if not isinstance(value, list):
        raise HandoffValidationError(f"{field} must be an array")
    return value


def _artifact_path(entry: object, index: int) -> str:
    if isinstance(entry, str):
        path = entry
    elif isinstance(entry, dict) and isinstance(entry.get("path"), str):
        path = entry["path"]
    else:
        raise HandoffValidationError(
            f"artifacts[{index}] must be a path string or an object with a path string"
        )
    if not path or "\\" in path:
        raise HandoffValidationError(f"artifacts[{index}] is not a POSIX project path")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or "." in parsed.parts:
        raise HandoffValidationError(f"artifacts[{index}] must be project-relative without traversal")
    return parsed.as_posix()


def _validate_artifact(
    *,
    project_root: Path,
    specialist: str,
    session_id: str | None,
    path: str,
) -> None:
    allowed_roots = ARTIFACT_ROOTS[specialist]
    if not any(path == root or path.startswith(root + "/") for root in allowed_roots):
        raise HandoffValidationError(
            f"artifact path is outside the allowed location for {specialist}: {path}"
        )

    candidate = (project_root / path).resolve(strict=False)
    project = project_root.resolve(strict=True)
    try:
        candidate.relative_to(project)
    except ValueError as error:
        raise HandoffValidationError(f"artifact resolves outside the project: {path}") from error

    if session_id is None:
        raise HandoffValidationError("a handoff with artifacts must include session_id")
    expected_prefixes = {
        f"{root}/{session_id}" for root in allowed_roots
    }
    if not any(path == prefix or path.startswith(prefix + "/") for prefix in expected_prefixes):
        raise HandoffValidationError(
            f"artifact does not belong to session {session_id}: {path}"
        )


def validate_handoff(
    handoff: object,
    *,
    project_root: Path = PROJECT_ROOT,
    expected_specialist: str | None = None,
    expected_session_id: str | None = None,
) -> dict[str, Any]:
    """Validate and return the original handoff object."""

    if not isinstance(handoff, dict):
        raise HandoffValidationError("handoff must be a JSON object")
    missing = sorted(REQUIRED_FIELDS - handoff.keys())
    if missing:
        raise HandoffValidationError(f"handoff is missing required fields: {', '.join(missing)}")
    if handoff["schema_version"] != SCHEMA_VERSION:
        raise HandoffValidationError(f"schema_version must be {SCHEMA_VERSION}")

    specialist = handoff["specialist"]
    if specialist not in SPECIALIST_STAGES:
        raise HandoffValidationError(f"unknown specialist: {specialist!r}")
    if expected_specialist is not None and specialist != expected_specialist:
        raise HandoffValidationError(
            f"specialist {specialist!r} does not match requested role {expected_specialist!r}"
        )
    expected_stage = SPECIALIST_STAGES[specialist]
    if handoff["stage"] != expected_stage:
        raise HandoffValidationError(
            f"specialist {specialist} must produce stage {expected_stage}"
        )

    status = handoff["status"]
    if status not in STATUSES:
        raise HandoffValidationError(f"unknown status: {status!r}")
    session_id = _session(handoff["session_id"], "session_id")
    derived = _session(handoff["derived_from_session_id"], "derived_from_session_id")
    if expected_session_id is not None:
        expected_session_id = _session(expected_session_id, "expected_session_id", nullable=False)
        if session_id != expected_session_id:
            raise HandoffValidationError("session_id does not match the expected session")

    if status in {"completed", "needs_approval"} and session_id is None:
        raise HandoffValidationError(f"{status} handoff requires session_id")
    if specialist == "literature_reviewer" and derived is not None:
        raise HandoffValidationError("literature_reviewer derived_from_session_id must be null")
    if (
        specialist in {"boolean_dynamics_modeler", "multicellular_configurator"}
        and status in {"completed", "needs_approval"}
        and derived is None
    ):
        raise HandoffValidationError(f"{specialist} requires upstream session lineage")

    for field in ("actions", "assumptions", "decisions_required"):
        _list_field(handoff, field)
    artifacts = _list_field(handoff, "artifacts")

    validation = handoff["validation"]
    if not isinstance(validation, dict):
        raise HandoffValidationError("validation must be an object")
    if set(("checks", "passed")) - validation.keys():
        raise HandoffValidationError("validation must contain checks and passed")
    if not isinstance(validation["checks"], list):
        raise HandoffValidationError("validation.checks must be an array")
    if not isinstance(validation["passed"], bool):
        raise HandoffValidationError("validation.passed must be a boolean")
    if status == "completed" and not validation["passed"]:
        raise HandoffValidationError("completed handoff cannot have failing validation")

    next_stage = handoff["recommended_next_stage"]
    if next_stage not in SAFE_NEXT_STAGES[expected_stage]:
        raise HandoffValidationError(
            f"recommended_next_stage {next_stage!r} skips or mismatches a required approval gate"
        )
    if status in {"blocked", "failed"} and next_stage is not None:
        raise HandoffValidationError(f"{status} handoff must recommend null next stage")
    if status == "needs_approval" and not handoff["decisions_required"]:
        raise HandoffValidationError("needs_approval handoff requires decisions_required")

    project = project_root.resolve(strict=True)
    for index, entry in enumerate(artifacts):
        _validate_artifact(
            project_root=project,
            specialist=specialist,
            session_id=session_id,
            path=_artifact_path(entry, index),
        )
    return handoff


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path, help="JSON handoff file")
    parser.add_argument("--specialist", choices=sorted(SPECIALIST_STAGES))
    parser.add_argument("--session-id")
    return parser.parse_args(argv)


def fail(message: str) -> NoReturn:
    print(f"handoff validation failed: {message}", file=sys.stderr)
    raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        payload = json.loads(arguments.handoff.read_text(encoding="utf-8"))
        validate_handoff(
            payload,
            expected_specialist=arguments.specialist,
            expected_session_id=arguments.session_id,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, HandoffValidationError) as error:
        fail(str(error))
    print(json.dumps({"valid": True, "handoff": str(arguments.handoff)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

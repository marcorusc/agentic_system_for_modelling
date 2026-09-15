"""Specialist launcher provenance helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.codex.launcher_config import validate_session_id
except ModuleNotFoundError:
    from launcher_config import validate_session_id


RUN_ROOTS = {
    "ode_modeler": Path("runs/ode-modeler"),
    "network_curator": Path("runs/network-curator"),
    "literature_reviewer": Path("runs/network-curator"),
    "boolean_dynamics_modeler": Path("runs/boolean-dynamics-modeler"),
    "multicellular_configurator": Path("runs/multicellular-configurator"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def specialist_run_base(project_root: Path, specialist: str, review_kind: str = "edge") -> Path:
    project = project_root.resolve(strict=True)
    if review_kind not in {"edge", "ode"}:
        raise ValueError("unknown literature review kind")
    role = "ode_modeler" if specialist == "literature_reviewer" and review_kind == "ode" else specialist
    base = (project / RUN_ROOTS[role]).resolve(strict=False)
    try:
        base.relative_to(project)
    except ValueError as exc:
        raise ValueError("specialist run root resolves outside the project") from exc
    return base


def create_launcher_run(
    *, project_root: Path, specialist: str, prompt: str, launcher_run_id: str, review_kind: str = "edge"
) -> Path:
    validate_session_id(launcher_run_id)
    base = specialist_run_base(project_root, specialist, review_kind)
    target = (base / "_launcher-runs" / launcher_run_id).resolve(strict=False)
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError("launcher run resolves outside the specialist run root") from exc
    target.mkdir(parents=True, exist_ok=False)
    (target / "task.txt").write_text(prompt.rstrip() + "\n", encoding="utf-8")
    return target


def record_invocation(
    *,
    project_root: Path,
    specialist: str,
    prompt: str,
    final_output: str,
    handoff: dict[str, Any] | None,
    expected_session_id: str | None,
    provenance: dict[str, Any],
    invocation_id: str,
    launcher_dir: Path | None = None,
    review_kind: str = "edge",
) -> Path:
    handoff_session_id = handoff.get("session_id") if handoff is not None else None
    if handoff_session_id is not None and not isinstance(handoff_session_id, str):
        raise ValueError("handoff session_id must be a string or null")
    if expected_session_id is not None:
        expected_session_id = validate_session_id(expected_session_id)
    if handoff_session_id is not None:
        handoff_session_id = validate_session_id(handoff_session_id)
    if (
        expected_session_id is not None
        and handoff_session_id is not None
        and expected_session_id != handoff_session_id
    ):
        raise ValueError("handoff session_id does not match --record-session-id")

    session_id = expected_session_id or handoff_session_id
    if session_id is None:
        status = handoff.get("status") if handoff is not None else None
        session_id = "_blocked" if status == "blocked" else "_unresolved"

    base = specialist_run_base(project_root, specialist, review_kind)
    target = (base / session_id / "specialist-invocations" / invocation_id).resolve(
        strict=False
    )
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError("invocation output resolves outside the specialist run root") from exc

    if launcher_dir is None:
        target.mkdir(parents=True, exist_ok=False)
        (target / "task.txt").write_text(prompt.rstrip() + "\n", encoding="utf-8")
        working = target
    else:
        working = launcher_dir.resolve(strict=True)
        launcher_root = (base / "_launcher-runs").resolve(strict=False)
        try:
            working.relative_to(launcher_root)
        except ValueError as exc:
            raise ValueError("launcher directory is outside the launcher run root") from exc
        if working.name != invocation_id:
            raise ValueError("launcher directory does not match invocation ID")

    (working / "specialist-output.txt").write_text(final_output, encoding="utf-8")
    if handoff is not None:
        write_json(working / "handoff.json", handoff)
    write_json(working / "provenance.json", provenance)
    if launcher_dir is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ValueError("specialist invocation directory already exists")
        working.rename(target)
    return target

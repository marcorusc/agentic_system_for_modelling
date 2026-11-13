"""Resolve researcher approvals recorded in DECISIONS.md for data sessions and mappings.

`scripts.state` is imported lazily: state.py imports this module, and it must also
keep working when run as a script.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.data.common import RUNS_ROOT


def _state():
    from scripts import state
    return state


def load_record(root: Path, record_id: str) -> dict:
    state = _state()
    root = Path(root)
    text = (root / "DECISIONS.md").read_text(encoding="utf-8")
    for record in state.records(text):
        if record["id"] == record_id:
            return record
    raise ValueError("decision_id not found in DECISIONS.md governance records")


def _stage_approval(record: dict, record_id: str, stage: str) -> None:
    if record.get("kind") != "stage_approval":
        raise ValueError(f"decision {record_id} must be a stage_approval, not {record.get('kind')!r}")
    if record.get("stage") != stage:
        raise ValueError(f"decision {record_id} must approve stage {stage}, not {record.get('stage')!r}")


def _read_json(path: Path, rel: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"cannot read {rel}: {exc}") from exc


def require_data_approval(root: Path, record_id: str, session_id: str) -> dict:
    state = _state()
    root = Path(root)
    record = load_record(root, record_id)
    _stage_approval(record, record_id, "data")
    if record.get("session_id") != session_id:
        raise ValueError(f"decision {record_id} approves session {record.get('session_id')!r}, not {session_id}")
    handoff_rel = f"{(RUNS_ROOT / session_id).as_posix()}/handoff.json"
    approved = record.get("artifact")
    if not isinstance(approved, dict) or approved.get("path") != handoff_rel:
        raise ValueError(f"decision {record_id} artifact must be {handoff_rel}")
    if state.digest(state.artifact(root, handoff_rel)) != approved.get("sha256"):
        raise ValueError(f"{handoff_rel} changed since approval {record_id} (sha256 mismatch)")
    return record


def handoff_artifacts(root: Path, session_id: str) -> set:
    """The (path, sha256) pairs listed by the session's handoff.json."""
    state = _state()
    handoff_rel = f"{(RUNS_ROOT / session_id).as_posix()}/handoff.json"
    handoff = _read_json(state.artifact(Path(root), handoff_rel), handoff_rel)
    artifacts = handoff.get("artifacts") if isinstance(handoff, dict) else None
    if not isinstance(artifacts, list) or handoff.get("session_id") != session_id:
        raise ValueError(f"{handoff_rel} is not a handoff of session {session_id}")
    return {(a.get("path"), a.get("sha256")) for a in artifacts if isinstance(a, dict)}


def require_in_handoff(root: Path, session_id: str, path: str, sha256: str, listed: set | None = None) -> set:
    listed = handoff_artifacts(root, session_id) if listed is None else listed
    if (path, sha256) not in listed:
        handoff_rel = f"{(RUNS_ROOT / session_id).as_posix()}/handoff.json"
        raise ValueError(f"{path} (sha256 {sha256[:12]}) is not an artifact of the approved handoff {handoff_rel}")
    return listed


def proposal_index(root: Path, session_id: str, listed: set) -> tuple[str, list]:
    state = _state()
    index_rel = f"{(RUNS_ROOT / session_id).as_posix()}/proposals/index.json"
    index_path = state.artifact(Path(root), index_rel)
    if (index_rel, state.digest(index_path)) not in listed:
        raise ValueError(f"{index_rel} differs from the approved handoff")
    index = _read_json(index_path, index_rel)
    return index_rel, index if isinstance(index, list) else []


def proposal_entry_for_path(root: Path, session_id: str, path: str, listed: set) -> dict:
    base = (RUNS_ROOT / session_id).as_posix()
    index_rel, index = proposal_index(root, session_id, listed)
    rel = path[len(base) + 1:]
    found = [p for p in index if isinstance(p, dict) and p.get("path") == rel]
    if len(found) != 1 or not isinstance(found[0].get("id"), str):
        raise ValueError(f"{path} is not exactly one proposal in {index_rel}")
    return found[0]


def require_proposal_in_outputs(record: dict, proposal_id: str) -> None:
    outputs = record.get("outputs")
    if not isinstance(outputs, list) or proposal_id not in outputs:
        raise ValueError(f"proposal {proposal_id} is not in the approved outputs of decision {record.get('id')}")


def require_proposal_approved(root: Path, record: dict, session_id: str, proposal_id: str) -> dict:
    state = _state()
    root = Path(root)
    base = (RUNS_ROOT / session_id).as_posix()
    # Never trust the caller's record: re-resolve it from DECISIONS.md and re-check it.
    record = require_data_approval(root, record.get("id"), session_id)
    require_proposal_in_outputs(record, proposal_id)
    listed = handoff_artifacts(root, session_id)
    index_rel, index = proposal_index(root, session_id, listed)
    found = [p for p in index if isinstance(p, dict) and p.get("id") == proposal_id]
    if len(found) != 1 or not isinstance(found[0].get("path"), str):
        raise ValueError(f"proposal {proposal_id} is not exactly one proposal in {index_rel}")
    entry = dict(found[0])
    rel = f"{base}/{entry['path']}"
    digest = state.digest(state.artifact(root, rel))
    require_in_handoff(root, session_id, rel, digest, listed)
    entry["path"] = rel
    entry["sha256"] = digest
    return entry


def require_mapping_approval(root: Path, record_id: str, mapping_rel: str, sha256: str) -> dict:
    state = _state()
    root = Path(root)
    record = load_record(root, record_id)
    _stage_approval(record, record_id, "data_mapping")
    approved = record.get("artifact")
    if not isinstance(approved, dict) or approved.get("path") != mapping_rel:
        raise ValueError(f"decision {record_id} artifact must be {mapping_rel}")
    if approved.get("sha256") != sha256:
        raise ValueError(f"decision {record_id} approves a different sha256 than {sha256}")
    if state.digest(state.artifact(root, mapping_rel)) != sha256:
        raise ValueError(f"{mapping_rel} changed since approval {record_id} (sha256 mismatch)")
    return record

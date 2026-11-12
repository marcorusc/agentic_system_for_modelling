#!/usr/bin/env python3
"""Build the handoff.json envelope of a data-analyst session mechanically.

CLI:
  handoff.py build --session ID --status needs_approval|completed|blocked|failed --notes REL

The agent supplies only a notes file; every other field is generated from the
session (identity.json, manifest.json) and fresh file hashes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.data import manifest  # noqa: E402
from scripts.data.common import RUNS_ROOT, project_root, reject_symlinks, session_dir, sha256_file  # noqa: E402

STATUSES = ("needs_approval", "completed", "blocked", "failed")
NOTE_KEYS = frozenset({"actions", "assumptions", "validation_checks", "decisions", "blocked"})
DECISION_ID_RE = re.compile(r"\AD\d+\Z")
BASE_ARTIFACTS = ("manifest.json", "sources.jsonl", "outputs/index.json", "proposals/index.json")


def _session_file(session: Path, rel, label: str) -> Path:
    """Resolve a session-relative path to a regular file inside the session, or raise ValueError."""
    if not isinstance(rel, str) or not rel:
        raise ValueError(f"{label} must be a non-empty session-relative path")
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts or "\\" in rel:
        raise ValueError(f"{label} must be session-relative without '..': {rel}")
    full = session / path
    reject_symlinks(full, session)
    if not full.is_file():
        raise ValueError(f"{label} is not a regular file in the session: {rel}")
    return full


def _strings(value, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"notes.{name} must be a list of strings")
    return value


def _load_notes(session: Path, notes_rel: str) -> dict:
    path = _session_file(session, notes_rel, "notes path")
    try:
        notes = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read notes {notes_rel}: {exc}") from exc
    if not isinstance(notes, dict):
        raise ValueError("notes must be a JSON object")
    unknown = sorted(set(notes) - NOTE_KEYS)
    if unknown:
        raise ValueError(f"unknown notes keys: {', '.join(unknown)}")
    clean = {k: _strings(notes.get(k, []), k) for k in ("actions", "assumptions", "validation_checks")}
    decisions = notes.get("decisions", [])
    if not isinstance(decisions, list):
        raise ValueError("notes.decisions must be a list")
    seen: set[str] = set()
    for item in decisions:
        if not isinstance(item, dict) or not set(item) <= {"id", "question", "artifact"}:
            raise ValueError("each decision must be an object with id, question and optional artifact")
        did, question = item.get("id"), item.get("question")
        if not isinstance(did, str) or DECISION_ID_RE.fullmatch(did) is None:
            raise ValueError(f"decision id must match ^D\\d+$: {did!r}")
        if did in seen:
            raise ValueError(f"duplicate decision id: {did}")
        seen.add(did)
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"decision {did} needs a non-empty question")
        if "artifact" in item:
            _session_file(session, item["artifact"], f"decision {did} artifact")
    clean["decisions"] = decisions
    blocked = notes.get("blocked", [])
    if not isinstance(blocked, list):
        raise ValueError("notes.blocked must be a list")
    for item in blocked:
        if (not isinstance(item, dict) or set(item) != {"what", "why", "remediation"}
                or not all(isinstance(v, str) and v.strip() for v in item.values())):
            raise ValueError("each blocked item must have non-empty string what, why and remediation")
    clean["blocked"] = blocked
    return clean


def _read_manifest(session: Path) -> dict:
    try:
        data = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _listed(data: dict, key: str) -> list[dict]:
    items = data.get(key)
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def _artifacts(session: Path, session_id: str, data: dict) -> list[dict]:
    rels = list(BASE_ARTIFACTS)
    for key in ("scripts", "outputs", "proposals"):
        rels += [i["path"] for i in _listed(data, key) if isinstance(i.get("path"), str)]
    result, seen = [], set()
    for rel in rels:
        if rel in seen:
            continue
        seen.add(rel)
        try:
            full = _session_file(session, rel, "artifact")
        except ValueError:
            continue  # absent optional file (or, for failed sessions, a missing listed file)
        result.append({"path": (RUNS_ROOT / session_id / rel).as_posix(), "sha256": sha256_file(full)})
    return result


def build(root: Path, session_id: str, status: str, notes_rel: str) -> tuple[Path, str]:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    session = session_dir(root, session_id)
    notes = _load_notes(session, notes_rel)
    errors = manifest.verify(root, session_id)
    if errors and status != "failed":
        raise ValueError("manifest.py verify failed (rebuild the manifest or use status failed): "
                         + "; ".join(errors))
    data = _read_manifest(session)
    proposals = _listed(data, "proposals")
    outputs = _listed(data, "outputs")
    blocked = notes["blocked"]

    if status != "failed":
        if proposals and status != "needs_approval":
            raise ValueError(f"manifest has proposals; status must be needs_approval, not {status}")
        if status == "blocked" and outputs:
            raise ValueError("status blocked is not allowed when outputs exist; "
                             "use needs_approval or completed")
        if status == "completed" and (not outputs or blocked):
            raise ValueError("status completed needs outputs and no blocked items")
        if status == "needs_approval" and not (proposals or notes["decisions"] or blocked):
            raise ValueError("status needs_approval needs a proposal, a decision or a blocked item")
        if status == "blocked" and not (notes["decisions"] or blocked):
            raise ValueError("status blocked needs a blocked item or a decision in the notes "
                             "(the researcher must see why)")
        if not proposals and not outputs and status != "blocked":
            raise ValueError("no outputs and no proposals; status must be blocked")

    try:
        identity = json.loads((session / "identity.json").read_text(encoding="utf-8"))
        ids = {k: identity[k] for k in ("session_id", "derived_from_session_id")}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"cannot read identity.json: {exc}") from exc

    decisions = [
        {"id": p.get("id"), "kind": p.get("kind"), "target_layer": p.get("target_layer"),
         "path": (RUNS_ROOT / session_id / p["path"]).as_posix(), "sha256": p.get("sha256"),
         "question": f"Approve, edit or reject {p.get('kind')} for {p.get('target_layer')}"}
        for p in proposals if isinstance(p.get("path"), str)
    ]
    for d in notes["decisions"]:
        entry = {"id": d["id"], "question": d["question"]}
        if "artifact" in d:
            entry["artifact"] = d["artifact"]
            entry["sha256"] = sha256_file(session / d["artifact"])
        decisions.append(entry)
    for n, b in enumerate(blocked, 1):
        decisions.append({"id": f"B{n}",
                          "question": f"{b['what']} — {b['why']}; remediation: {b['remediation']}"})

    checks = [f"manifest.py verify: {e}" for e in errors] or ["manifest.py verify: passed"]
    envelope = {
        "schema_version": 1,
        "specialist": "data_analyst",
        "stage": "data",
        **ids,
        "status": status,
        "recommended_next_stage": None,
        "actions": notes["actions"],
        "assumptions": notes["assumptions"],
        "artifacts": _artifacts(session, session_id, data),
        "decisions_required": decisions,
        "validation": {"checks": checks[:] + notes["validation_checks"],
                       "passed": status in ("needs_approval", "completed") and not errors},
    }
    target = session / "handoff.json"
    fd, tmp = tempfile.mkstemp(dir=session, prefix=".handoff-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target, sha256_file(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--session", required=True)
    b.add_argument("--status", required=True, choices=STATUSES)
    b.add_argument("--notes", required=True)
    args = parser.parse_args(argv)
    root = project_root().resolve()
    try:
        _, digest = build(root, args.session, args.status, args.notes)
    except (ValueError, KeyError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Handoff written: {(RUNS_ROOT / args.session / 'handoff.json').as_posix()} sha256={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

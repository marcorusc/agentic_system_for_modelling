#!/usr/bin/env python3
"""Orchestrator post-run step for a data-analyst invocation.

Usage: receive.py --session ID --agent-id AID [--transcript-root DIR]

Recovers the SubagentStop capture when the hook did not fire (no integrity.json or
no index registration) after checking that the agent transcript binds --session,
then verifies the manifest, the integrity verdict, the handoff and the final
report's ``Handoff: ... sha256=<hex>`` line against handoff.json, and prints the
decisions table, the handoff status and ``RECEIVED <session> OK``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the repo importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.capture.record_invocation import _data_guard, _index_registers, record
from scripts.codex.validate_handoff import HandoffValidationError, validate_handoff
from scripts.data import manifest
from scripts.data.common import RUNS_ROOT, project_root, session_dir, sha256_file

AGENT_ID_RE = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")
HANDOFF_LINE_RE = re.compile(r"Handoff: (\S+) sha256=([0-9a-f]{64})")


def project_slug(root: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(root).resolve()))


def default_transcript_root() -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config) if config else Path.home() / ".claude") / "projects"


def _check_agent_id(agent_id: object) -> str:
    if not isinstance(agent_id, str) or AGENT_ID_RE.fullmatch(agent_id) is None:
        raise ValueError(f"invalid agent id: {agent_id!r}")
    return agent_id


def find_transcript(root: Path, agent_id: str, transcript_root: Path) -> Path:
    _check_agent_id(agent_id)
    base = Path(transcript_root) / project_slug(root)
    matches = sorted(p for p in base.glob(f"*/subagents/agent-{agent_id}.jsonl") if p.is_file())
    if not matches:
        raise ValueError(f"no transcript found for agent {agent_id} under {base}")
    if len(matches) != 1:
        raise ValueError(f"exactly one transcript required for agent {agent_id}, "
                         f"found {len(matches)}: {', '.join(map(str, matches))}")
    return matches[0]


def _check_binding(root: Path, transcript: Path, agent_id: str, session_id: str) -> None:
    """Refuse recovery unless the transcript binds exactly --session (never record another session)."""
    try:
        bound = _data_guard().transcript_data_session(transcript, root=root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot bind a data session from the transcript of agent {agent_id}: {exc}; "
                         "check --agent-id") from exc
    if bound is None:
        raise ValueError(f"the transcript of agent {agent_id} binds no data session; check --agent-id")
    if bound[0] != session_id:
        raise ValueError(f"the transcript of agent {agent_id} binds data session {bound[0]}, not {session_id}; "
                         "check --agent-id (nothing was recorded)")


def receive(root: Path, session_id: str, agent_id: str, transcript_root: Path | None) -> dict:
    _check_agent_id(agent_id)
    root = Path(root).resolve()
    session = session_dir(root, session_id)
    relative = (RUNS_ROOT / session_id / "invocation" / agent_id).as_posix()
    recovered = False
    if not (session / "integrity.json").is_file() or not _index_registers(root, relative):
        transcript = find_transcript(root, agent_id, transcript_root or default_transcript_root())
        _check_binding(root, transcript, agent_id, session_id)
        record(root, {"agent_type": "data-analyst", "agent_id": agent_id,
                      "agent_transcript_path": str(transcript), "stop_hook_active": False,
                      "hook_event_name": "SubagentStop"})
        recovered = True
        if not _index_registers(root, relative):
            raise ValueError(f"invocation {agent_id} is not registered in runs/index.json after recovery")
    errors = manifest.verify(root, session_id)
    if errors:
        raise ValueError("manifest.py verify failed: " + "; ".join(errors))
    try:
        integrity = json.loads((session / "integrity.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read integrity.json: {exc}") from exc
    if not isinstance(integrity, dict) or integrity.get("passed") is not True:
        raise ValueError("integrity check failed: " + json.dumps(integrity, sort_keys=True)[:500])
    handoff_path = session / "handoff.json"
    if not handoff_path.is_file() or handoff_path.is_symlink():
        raise ValueError("handoff.json is missing")
    try:
        data = json.loads(handoff_path.read_text(encoding="utf-8"))
        validate_handoff(data, project_root=root, expected_specialist="data_analyst",
                         expected_session_id=session_id)
    except (HandoffValidationError, ValueError) as exc:
        raise ValueError(f"handoff validation failed: {exc}") from exc
    _check_handoff_line(session, session_id, agent_id, handoff_path)
    prefix = (RUNS_ROOT / session_id).as_posix()
    rows = [{"id": d.get("id"), "kind": d.get("kind") or "-", "layer": d.get("target_layer") or "-",
             "path": d.get("path") or (f"{prefix}/{d['artifact']}" if isinstance(d.get("artifact"), str) else "-"),
             "sha256": (d.get("sha256") or "-")[:12]}
            for d in data.get("decisions_required", []) if isinstance(d, dict)]
    return {"session_id": session_id, "recovered": recovered, "status": data.get("status"), "rows": rows}


def _check_handoff_line(session: Path, session_id: str, agent_id: str, handoff_path: Path) -> None:
    """The recorded final report must end with the Handoff line naming the current handoff.json."""
    final = session / "invocation" / agent_id / "final_report.md"
    try:
        if final.is_symlink():
            raise OSError("final_report.md is a symlink")
        lines = [line for line in final.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read the recorded final report of agent {agent_id}: {exc}") from exc
    rel = (RUNS_ROOT / session_id / "handoff.json").as_posix()
    match = HANDOFF_LINE_RE.fullmatch(lines[-1].strip()) if lines else None
    if match is None or match.group(1) != rel:
        raise ValueError(f"the recorded final report does not end with the `Handoff: {rel} sha256=<hex>` line")
    if match.group(2) != sha256_file(handoff_path):
        raise ValueError(f"the final report's Handoff: line sha256 {match.group(2)} differs from handoff.json "
                         "(rebuilt or edited after the final message)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--transcript-root")
    args = parser.parse_args(argv)
    try:
        result = receive(project_root(), args.session, args.agent_id,
                         Path(args.transcript_root) if args.transcript_root else None)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"RECEIVE FAILED: {exc}", file=sys.stderr)
        return 1
    if result["recovered"]:
        print("note: SubagentStop capture was missing; recovered from the agent transcript")
    for row in result["rows"]:
        print(" | ".join(row[key] for key in ("id", "kind", "layer", "path", "sha256")))
    print(f"Handoff status: {result['status']}")
    print(f"RECEIVED {args.session} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

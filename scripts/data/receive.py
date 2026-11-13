#!/usr/bin/env python3
"""Orchestrator post-run step for a data-analyst invocation.

Usage: receive.py --session ID --agent-id AID [--transcript-root DIR]

Recovers the SubagentStop capture (scripts/capture/recover.py) when the hook did not fire (no integrity.json or
no index registration) after checking that the agent transcript binds --session,
then verifies the manifest, the integrity verdict, the handoff and the final
report's ``Handoff: ... sha256=<hex>`` line against handoff.json, and prints the
decisions table, the handoff status and ``RECEIVED <session> OK``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the repo importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.capture import recover
from scripts.capture.record_invocation import _index_registers
from scripts.capture.transcripts import (  # noqa: F401 (re-exported)
    check_agent_id as _check_agent_id, default_transcript_root, find_transcript, project_slug)
from scripts.codex.validate_handoff import HandoffValidationError, validate_handoff
from scripts.data import manifest
from scripts.data.common import RUNS_ROOT, project_root, session_dir, sha256_file

HEADING_RE = re.compile(r"\A\s{0,3}#{1,6}\s+(.*?)\s*#*\s*\Z")
HANDOFF_LINE_RE = re.compile(r"Handoff: (\S+) sha256=([0-9a-f]{64})")


def receive(root: Path, session_id: str, agent_id: str, transcript_root: Path | None) -> dict:
    _check_agent_id(agent_id)
    root = Path(root).resolve()
    session = session_dir(root, session_id)
    relative = (RUNS_ROOT / session_id / "invocation" / agent_id).as_posix()
    recovered = False
    if not (session / "integrity.json").is_file() or not _index_registers(root, relative):
        recovered = recover.recover(root, "data-analyst", agent_id, session_id,
                                    transcript_root)["status"] == "recorded"
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
    final = _check_handoff_line(session, session_id, agent_id, handoff_path)
    _check_report_sections(session, final)
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
    return "\n".join(lines)


def _check_report_sections(session: Path, report: str) -> None:
    """The report needs Figures and Abbreviations headings and must name every indexed figure."""
    headings = {m.group(1).strip().strip("*_ ").lower()
                for m in (HEADING_RE.match(line) for line in report.splitlines()) if m}
    missing = [f"a `{name}` heading" for name in ("Figures", "Abbreviations") if name.lower() not in headings]
    try:
        index = json.loads((session / "outputs" / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = []
    names = {}
    for entry in index if isinstance(index, list) else []:
        rel = entry.get("path") if isinstance(entry, dict) else None
        if manifest.is_figure(rel):
            names.setdefault(Path(rel).stem, []).append(Path(rel).name)
    unnamed = sorted(stem for stem in names
                     if not re.search(rf"(?<![\w.-]){re.escape(stem)}(?![\w-])", report, re.IGNORECASE))
    if unnamed:
        missing.append("figure(s) " + ", ".join(f"{'/'.join(sorted(names[s]))}" for s in unnamed))
    if missing:
        raise ValueError("report is missing " + "; ".join(missing)
                         + " (the final report needs `## Figures` and `## Abbreviations` headings "
                         "and must name every figure file)")


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

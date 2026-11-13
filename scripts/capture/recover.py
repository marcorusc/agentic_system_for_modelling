#!/usr/bin/env python3
"""Orchestrator post-run step: recover a specialist's missing SubagentStop capture.

Usage: recover.py --specialist NAME --agent-id AID [--session ID] [--transcript-root DIR]

Claude Code does not reliably fire SubagentStop for background subagents. This finds
the agent transcript, binds its scientific session, and (unless the invocation is
already captured and indexed) runs the normal recorder on a synthetic SubagentStop
payload, then checks the recorder-written report.md. Prints ``RECOVERED <specialist>
<session-or-unbound> <status>`` as its last line, or ``RECOVER FAILED: <reason>``
on stderr with exit 1. It writes nothing but what the recorder writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the repo importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.capture.index import SPECIALISTS
from scripts.capture.record_invocation import _index_registers, record, session_ids
from scripts.capture.transcripts import check_agent_id, default_transcript_root, find_transcript
from scripts.data.common import project_root


def _bind(root: Path, transcript: Path, specialist: str, agent_id: str, session: str | None) -> str | None:
    label = "data session" if specialist == "data-analyst" else "session"
    try:
        bound = session_ids(transcript, specialist, root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot bind a {label} from the transcript of agent {agent_id}: {exc}; "
                         "check --agent-id") from exc
    if len(bound) > 1:
        raise ValueError(f"the transcript of agent {agent_id} binds more than one {label} "
                         f"({', '.join(sorted(bound))}); record manually with reviewed attribution")
    found = next(iter(bound), None)
    if session is not None:
        if found is None:
            raise ValueError(f"the transcript of agent {agent_id} binds no {label}; "
                             "check --agent-id; nothing was recorded")
        if found != session:
            raise ValueError(f"the transcript of agent {agent_id} binds {label} {found}, not {session}; "
                             "check --agent-id; nothing was recorded")
    return found


def recover(root: Path, specialist: str, agent_id: str, session: str | None,
            transcript_root: Path | None) -> dict:
    if specialist not in SPECIALISTS:
        raise ValueError(f"unknown specialist: {specialist!r} (expected one of {', '.join(sorted(SPECIALISTS))})")
    check_agent_id(agent_id)
    root = Path(root).resolve()
    transcript = find_transcript(root, agent_id, transcript_root or default_transcript_root())
    bound = _bind(root, transcript, specialist, agent_id, session)
    if bound is not None:
        relative = f"runs/{specialist}/{bound}/invocation/{agent_id}"
        # data-analyst also needs the recorder's integrity verdict (receive.py reads it)
        verdict = specialist != "data-analyst" or (root / "runs" / specialist / bound / "integrity.json").is_file()
        if verdict and (root / relative).is_dir() and _index_registers(root, relative):
            report_md = None
            try:
                report_md = json.loads((root / relative / "invocation.json").read_text(encoding="utf-8")).get("report_md")
            except (OSError, ValueError, AttributeError):
                pass
            return {"status": "already-recorded", "session_id": bound, "capture_path": relative,
                    "report_md": report_md, "transcript": str(transcript)}
    result = record(root, {"agent_type": specialist, "agent_id": agent_id,
                           "agent_transcript_path": str(transcript), "stop_hook_active": False,
                           "hook_event_name": "SubagentStop"})
    if result.get("status") == "unbound":
        if session is not None:
            raise ValueError(f"agent {agent_id} was filed as an unbound invocation, not session {session}")
        return {"status": "unbound", "session_id": None, "capture_path": result.get("invocation_path"),
                "report_md": None, "transcript": str(transcript)}
    if bound is None or result.get("session_id") not in (None, bound):
        raise ValueError(f"recorder result does not match the bound session: {result}")
    if not (root / "runs" / specialist / bound / "report.md").is_file():
        raise ValueError(f"runs/{specialist}/{bound}/report.md is missing after recording")
    return {"status": "recorded", "session_id": bound, "capture_path": result.get("capture_path"),
            "report_md": result.get("report_md"), "transcript": str(transcript)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specialist", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--session")
    parser.add_argument("--transcript-root")
    args = parser.parse_args(argv)
    try:
        result = recover(project_root(), args.specialist, args.agent_id, args.session,
                         Path(args.transcript_root) if args.transcript_root else None)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"RECOVER FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"transcript: {result['transcript']}")
    print(f"capture: {result['capture_path']}")
    if result["report_md"]:
        print(f"report.md: {result['report_md']}")
    print(f"RECOVERED {args.specialist} {result['session_id'] or 'unbound'} {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

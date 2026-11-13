"""Locate Claude Code subagent transcripts for post-run recovery (shared helpers)."""

from __future__ import annotations

import os
import re
from pathlib import Path

AGENT_ID_RE = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")


def project_slug(root: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(root).resolve()))


def default_transcript_root() -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config) if config else Path.home() / ".claude") / "projects"


def check_agent_id(agent_id: object) -> str:
    if not isinstance(agent_id, str) or AGENT_ID_RE.fullmatch(agent_id) is None:
        raise ValueError(f"invalid agent id: {agent_id!r}")
    return agent_id


def find_transcript(root: Path, agent_id: str, transcript_root: Path) -> Path:
    check_agent_id(agent_id)
    base = Path(transcript_root) / project_slug(root)
    matches = sorted(p for p in base.glob(f"*/subagents/agent-{agent_id}.jsonl") if p.is_file())
    if not matches:
        raise ValueError(f"no transcript found for agent {agent_id} under {base}")
    if len(matches) != 1:
        raise ValueError(f"exactly one transcript required for agent {agent_id}, "
                         f"found {len(matches)}: {', '.join(map(str, matches))}")
    return matches[0]

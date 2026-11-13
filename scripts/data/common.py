"""Shared helpers for data-analyst sessions."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

SESSION_RE = re.compile(r"\Adata-\d{8}T\d{6}Z-[0-9a-f]{8}\Z")
RUNS_ROOT = Path("runs/data-analyst")


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reject_symlinks(path: Path, root: Path) -> None:
    """Raise ValueError if any component from root down to path is a symlink."""
    root = Path(root)
    path = Path(path)
    try:
        parts = path.relative_to(root).parts
    except ValueError as exc:
        raise ValueError(f"{path} is not under {root}") from exc
    current = root
    if current.is_symlink():
        raise ValueError(f"symlink not allowed: {current}")
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlink not allowed: {current}")


def session_dir(root: Path, session_id: str) -> Path:
    if not isinstance(session_id, str) or SESSION_RE.fullmatch(session_id) is None:
        raise ValueError(f"invalid data session id: {session_id!r}")
    path = Path(root) / RUNS_ROOT / session_id
    reject_symlinks(path, Path(root))
    if not path.is_dir():
        raise ValueError(f"data session does not exist: {session_id}")
    return path


def _unique_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key: {key}")
        out[key] = value
    return out


def _no_constant(name):
    raise ValueError(f"non-finite value: {name}")


def strict_json(raw: bytes):
    """Parse UTF-8 JSON, refusing duplicate keys and NaN/Infinity."""
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys, parse_constant=_no_constant)

"""Protected-state snapshot: file hashes of the repo outside the session."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from scripts.data.common import RUNS_ROOT, session_dir, sha256_file

EXCLUDED_DIRS = (".git", ".venv-data", ".venv-cellprofiler", "data-cache", "__pycache__")


def digest_of(snapshot: dict[str, str]) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def take(root: Path, session_id: str) -> dict[str, str]:
    root = Path(root)
    own = (root / RUNS_ROOT / session_id).resolve()
    result: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        kept = []
        for name in sorted(dirnames):
            child = current / name
            if name in EXCLUDED_DIRS:
                continue
            if child.is_symlink():
                result[child.relative_to(root).as_posix()] = "symlink:" + os.readlink(child)
                continue
            if child.resolve() == own:
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            path = current / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                result[rel] = "symlink:" + os.readlink(path)
            elif path.is_file():
                result[rel] = sha256_file(path)
    return result


def diff(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        k for k in set(before) | set(after) if before.get(k) != after.get(k)
    )


def verify_session(root: Path, session_id: str, expected_digest: str | None) -> dict:
    root = Path(root)
    identity = json.loads(
        (session_dir(root, session_id) / "identity.json").read_text(encoding="utf-8")
    )
    stored = identity.get("protected_snapshot", {})
    intact = expected_digest is None or digest_of(stored) == expected_digest
    changed = diff(stored, take(root, session_id))
    return {"passed": intact and not changed, "changed": changed, "identity_intact": intact}

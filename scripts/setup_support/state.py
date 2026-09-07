"""Local setup state and recoverable, atomic configuration updates."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


class SetupError(ValueError):
    pass


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SetupError(f"Expected JSON object: {path}")
    return value


def atomic_write(path: Path, content: bytes) -> None:
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise SetupError(f"Refusing symlink configuration path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".setup-")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_config(path: Path, text: str, backups: Path) -> dict:
    content = text.encode("utf-8")
    if path.is_symlink():
        raise SetupError(f"Refusing symlink configuration: {path}")
    old = path.read_bytes() if path.exists() else None
    if old == content:
        return {"path": str(path), "sha256": digest(content), "changed": False}
    backup = None
    if old is not None:
        key = digest(str(path).encode())[:16] + "-" + digest(old)
        backup = backups / key
        if not backup.exists():
            atomic_write(backup, old)
    atomic_write(path, content)
    return {"path": str(path), "sha256": digest(content), "changed": True,
            "backup": str(backup) if backup else None}

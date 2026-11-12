"""Source ledger (sources.jsonl) for data-analyst sessions.

Entry ``path`` values are project-root-relative POSIX paths (R24):
``data-cache/sha256/<hex>``, ``runs/data-analyst/<id>/raw/<name>`` or ``inputs/<file>``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.data.common import reject_symlinks, sha256_file, utc_now  # noqa: E402

KINDS = ("download", "api", "input")
_SHA_RE = re.compile(r"\A[0-9a-f]{64}\Z")


def validate_entry(entry: dict) -> None:
    """Raise ValueError unless entry is a well-formed ledger entry."""
    if not isinstance(entry, dict):
        raise ValueError("ledger entry must be an object")
    if entry.get("kind") not in KINDS:
        raise ValueError(f"ledger kind must be one of {KINDS}")
    for key in ("uri", "release", "retrieved_at", "path"):
        value = entry.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"ledger entry needs non-empty string {key!r}")
    sha = entry.get("sha256")
    if not isinstance(sha, str) or _SHA_RE.fullmatch(sha) is None:
        raise ValueError("ledger sha256 must be 64 lowercase hex characters")
    if not isinstance(entry.get("terms"), str):
        raise ValueError("ledger terms must be a string")


def append(session: Path, entry: dict) -> None:
    validate_entry(entry)
    with (Path(session) / "sources.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def check_name(name: str) -> None:
    if (
        not isinstance(name, str)
        or name in ("", ".", "..")
        or "/" in name
        or "\\" in name
        or "\0" in name
    ):
        raise ValueError(f"name must be a plain filename: {name!r}")


def record_api(
    session: Path,
    *,
    url: str,
    params: dict,
    response: bytes | str,
    release: str,
    name: str,
    terms: str = "",
    root: Path | None = None,
) -> dict:
    """Save an API response under raw/ and ledger it.

    ``root`` defaults to the project root implied by the session location
    (``<root>/runs/data-analyst/<id>``); the ledger path is root-relative (R24).
    """
    check_name(name)
    session = Path(session)
    root = Path(root) if root is not None else session.parents[2]
    raw = session / "raw" / name
    reject_symlinks(raw.parent, session)
    rel = raw.relative_to(root).as_posix()
    data = response.encode("utf-8") if isinstance(response, str) else bytes(response)
    uri = url
    if params:
        uri = f"{url}{'&' if '?' in url else '?'}{urlencode(sorted(params.items()))}"
    try:
        with raw.open("xb") as handle:
            handle.write(data)
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite {raw}") from exc
    entry = {
        "kind": "api",
        "uri": uri,
        "release": release,
        "retrieved_at": utc_now(),
        "sha256": sha256_file(raw),
        "terms": terms,
        "path": rel,
    }
    try:
        validate_entry(entry)
    except ValueError:
        raw.unlink()
        raise
    append(session, entry)
    return entry


def record_input(
    session: Path,
    path: Path,
    root: Path,
    *,
    release: str = "researcher-supplied",
    terms: str = "",
) -> dict:
    root = Path(root)
    path = Path(path)
    inputs = root / "inputs"
    if ".." in path.parts:
        raise ValueError(f"'..' not allowed in input path: {path}")
    try:
        path.relative_to(inputs)
    except ValueError as exc:
        raise ValueError(f"input must be under {inputs}: {path}") from exc
    reject_symlinks(path, root)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(inputs.resolve())
    except (ValueError, OSError) as exc:
        raise ValueError(f"input must be a file under {inputs}: {path}") from exc
    if not resolved.is_file():
        raise ValueError(f"input is not a regular file: {path}")
    entry = {
        "kind": "input",
        "uri": path.relative_to(root).as_posix(),
        "release": release,
        "retrieved_at": utc_now(),
        "sha256": sha256_file(path),
        "terms": terms,
        "path": path.relative_to(root).as_posix(),
    }
    append(session, entry)
    return entry

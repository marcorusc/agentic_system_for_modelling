"""Source ledger (sources.jsonl) for data-analyst sessions."""

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
) -> dict:
    check_name(name)
    session = Path(session)
    raw = session / "raw" / name
    reject_symlinks(raw.parent, session)
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
        "path": str(raw),
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
    try:
        path.relative_to(inputs)
    except ValueError as exc:
        raise ValueError(f"input must be under {inputs}: {path}") from exc
    reject_symlinks(path, root)
    if not path.is_file():
        raise ValueError(f"input is not a file: {path}")
    entry = {
        "kind": "input",
        "uri": path.relative_to(root).as_posix(),
        "release": release,
        "retrieved_at": utc_now(),
        "sha256": sha256_file(path),
        "terms": terms,
        "path": str(path),
    }
    append(session, entry)
    return entry

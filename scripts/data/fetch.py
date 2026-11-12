#!/usr/bin/env python3
"""Download or register source data with provenance.

CLI:
  fetch.py --session ID (--url URL --name NAME | --input PATH) --release TEXT
           [--terms TEXT] [--expect binary|tabular|json] [--max-bytes N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.data import ledger  # noqa: E402
from scripts.data.common import (  # noqa: E402
    project_root,
    reject_symlinks,
    session_dir,
    sha256_file,
    utc_now,
)

TIMEOUT = 120
DEFAULT_MAX_BYTES = 5_000_000_000


def _looks_like_html(head: bytes) -> bool:
    start = head.lstrip().lower()
    return start.startswith(b"<!doctype") or start.startswith(b"<html")


def download(
    session: Path,
    *,
    url: str,
    name: str,
    release: str,
    terms: str = "",
    expect: str = "binary",
    max_bytes: int = DEFAULT_MAX_BYTES,
    root: Path | None = None,
) -> dict:
    ledger.check_name(name)
    if expect not in ("binary", "tabular", "json"):
        raise ValueError(f"invalid expect: {expect!r}")
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("only http(s) URLs are supported")
    if not isinstance(release, str) or not release.strip():
        raise ValueError("release must be a non-empty string")
    root = Path(root) if root is not None else project_root()
    session = Path(session)
    raw = session / "raw"
    reject_symlinks(raw, session)
    target = raw / name
    source = raw / f"{name}.source.json"
    for path in (target, source):
        if os.path.lexists(path):
            raise ValueError(f"refusing to overwrite {path}")
    cache = root / "data-cache"
    reject_symlinks(cache, root)
    (cache / "sha256").mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(prefix="tmp-", dir=cache)
    tmp = Path(tmp_name)
    try:
        total = 0
        head = b""
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "") or ""
            if expect != "binary" and content_type.lower().lstrip().startswith("text/html"):
                raise ValueError(f"received HTML, expected {expect}")
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"download exceeds max bytes ({max_bytes})")
                if len(head) < 1024:
                    head += chunk[: 1024 - len(head)]
                out.write(chunk)
        if expect != "binary" and _looks_like_html(head):
            raise ValueError(f"received HTML, expected {expect}")
        digest = sha256_file(tmp)
        final = cache / "sha256" / digest
        # R24: a cache hit is re-hashed; modified or non-regular entries are
        # replaced with the freshly downloaded bytes. Cache files are read-only.
        if not final.is_symlink() and final.is_file() and sha256_file(final) == digest:
            tmp.unlink()
        else:
            os.replace(tmp, final)
        os.chmod(final, 0o444)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    retrieved_at = utc_now()
    meta = {
        "uri": url,
        "release": release,
        "retrieved_at": retrieved_at,
        "sha256": digest,
        "cache_path": str(final),
        "content_type": content_type,
        "terms": terms,
    }
    entry = {
        "kind": "download",
        "uri": url,
        "release": release,
        "retrieved_at": retrieved_at,
        "sha256": digest,
        "terms": terms,
        "path": final.relative_to(root).as_posix(),
    }
    ledger.validate_entry(entry)
    try:
        with source.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite {source}") from exc
    ledger.append(session, entry)
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--url")
    parser.add_argument("--name")
    parser.add_argument("--input")
    parser.add_argument("--release", required=True)
    parser.add_argument("--terms", default="")
    parser.add_argument("--expect", choices=("binary", "tabular", "json"), default="binary")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)
    if bool(args.url) == bool(args.input):
        parser.error("exactly one of --url or --input is required")
    if args.url and not args.name:
        parser.error("--url requires --name")
    try:
        root = project_root().resolve()
        session = session_dir(root, args.session)
        if args.url:
            entry = download(
                session, url=args.url, name=args.name, release=args.release,
                terms=args.terms, expect=args.expect, max_bytes=args.max_bytes, root=root,
            )
        else:
            entry = ledger.record_input(
                session, Path(args.input).resolve(), root,
                release=args.release, terms=args.terms,
            )
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(entry, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

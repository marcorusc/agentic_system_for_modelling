#!/usr/bin/env python3
"""Create data-analyst sessions.

CLI:
  session.py new --purpose TEXT [--derived-from ID]
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.data import snapshot  # noqa: E402
from scripts.data.common import (  # noqa: E402
    RUNS_ROOT,
    SESSION_RE,
    project_root,
    session_dir,
    utc_now,
)

SUBDIRS = ("scripts", "raw", "outputs", "proposals")


def snapshot_digest(protected: dict[str, str]) -> str:
    return snapshot.digest_of(protected)


def new_session(root: Path, purpose: str, derived_from: str | None) -> tuple[str, str]:
    if derived_from is not None:
        if SESSION_RE.fullmatch(derived_from) is None:
            raise ValueError(f"invalid --derived-from id: {derived_from!r}")
        session_dir(root, derived_from)  # raises if missing
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_id = f"data-{stamp}-{secrets.token_hex(4)}"
    base = root / RUNS_ROOT / session_id
    for sub in SUBDIRS:
        (base / sub).mkdir(parents=True)
    protected = snapshot.take(root, session_id)
    identity = {
        "schema_version": 1,
        "session_id": session_id,
        "purpose": purpose,
        "created_at": utc_now(),
        "derived_from_session_id": derived_from,
        "protected_snapshot": protected,
    }
    (base / "identity.json").write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return session_id, snapshot_digest(protected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new")
    new.add_argument("--purpose", required=True)
    new.add_argument("--derived-from")
    args = parser.parse_args(argv)
    try:
        session_id, digest = new_session(project_root(), args.purpose, args.derived_from)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Data session created: {session_id} (snapshot sha256={digest})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Hash lock for the vendored K-Dense scientific-agent-skills tree.

CLI:
  vendor_lock.py build --upstream DIR [--modified-reason PATH=REASON ...]
  vendor_lock.py verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

VENDORED_SKILLS: tuple[str, ...] = (
    "depmap",
    "database-lookup",
    "gget",
    "bulk-rnaseq",
    "pydeseq2",
    "pathway-enrichment",
    "cellprofiler",
    "statistical-analysis",
    "scikit-learn",
    "uncertainty-and-units",
)
VENDOR_ROOT = Path("vendor/scientific-agent-skills")
UPSTREAM_URL = "https://github.com/K-Dense-AI/scientific-agent-skills"
UPSTREAM_COMMIT = "2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5"
LOCK_NAME = "VENDOR.lock.json"
TOP_LEVEL_FILES = ("LICENSE.md", "CITATION.cff")
MODIFICATION_DATE = "2026-11-12"
REPO_ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_files(vendor_root: Path) -> list[str]:
    """Relative POSIX paths of every vendored file covered by the lock."""
    names = list(TOP_LEVEL_FILES)
    for skill in VENDORED_SKILLS:
        base = vendor_root / skill
        names.extend(
            p.relative_to(vendor_root).as_posix()
            for p in base.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
    return sorted(names)


def build_lock(
    vendor_root: Path, modified: dict[str, dict], upstream_root: Path | None = None
) -> dict:
    """Build the lock. `files` holds upstream hashes; modified entries carry
    upstream_sha256/local_sha256 (upstream hash computed from `upstream_root`
    unless the entry already supplies it)."""
    files: dict[str, str] = {}
    mods: dict[str, dict] = {}
    for rel in tracked_files(vendor_root):
        local = sha256_file(vendor_root / rel)
        if rel in modified:
            entry = dict(modified[rel])
            upstream = entry.get("upstream_sha256")
            if upstream is None:
                if upstream_root is None:
                    raise ValueError(f"upstream hash required for modified file {rel}")
                src = upstream_root / (rel if rel in TOP_LEVEL_FILES else f"skills/{rel}")
                upstream = sha256_file(src)
            mods[rel] = {
                "upstream_sha256": upstream,
                "local_sha256": local,
                "reason": entry["reason"],
                "date": entry.get("date", MODIFICATION_DATE),
            }
            files[rel] = upstream
        else:
            files[rel] = local
    unknown = set(modified) - set(mods)
    if unknown:
        raise ValueError(f"modified paths not found: {sorted(unknown)}")
    return {
        "upstream": UPSTREAM_URL,
        "commit": UPSTREAM_COMMIT,
        "files": files,
        "modified": mods,
    }


def verify_lock(vendor_root: Path) -> list[str]:
    lock_path = vendor_root / LOCK_NAME
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{LOCK_NAME}: unreadable ({exc})"]
    errors: list[str] = []
    files = lock.get("files", {})
    modified = lock.get("modified", {})
    if lock.get("commit") != UPSTREAM_COMMIT:
        errors.append(f"{LOCK_NAME}: commit does not match UPSTREAM_COMMIT")
    for rel, expected in sorted(files.items()):
        path = vendor_root / rel
        if not path.is_file():
            errors.append(f"{rel}: missing")
            continue
        if rel in modified:
            expected = modified[rel]["local_sha256"]
        if sha256_file(path) != expected:
            errors.append(f"{rel}: hash mismatch")
    for rel in sorted(set(tracked_files(vendor_root)) - set(files)):
        errors.append(f"{rel}: not in lock")
    for skill in VENDORED_SKILLS:
        if not (vendor_root / skill / "SKILL.md").is_file():
            errors.append(f"{skill}/SKILL.md: missing")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--upstream", type=Path, required=True,
                       help="clean upstream checkout used for upstream hashes")
    build.add_argument("--modified-reason", action="append", default=[],
                       metavar="PATH=REASON")
    sub.add_parser("verify")
    args = parser.parse_args(argv)
    root = REPO_ROOT / VENDOR_ROOT
    if args.command == "build":
        modified = {}
        for item in args.modified_reason:
            path, sep, reason = item.partition("=")
            if not sep or not reason:
                parser.error(f"expected PATH=REASON, got {item!r}")
            modified[path] = {"reason": reason}
        lock = build_lock(root, modified, args.upstream)
        (root / LOCK_NAME).write_text(
            json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {VENDOR_ROOT / LOCK_NAME} ({len(lock['files'])} files)")
        return 0
    errors = verify_lock(root)
    for error in errors:
        print(error, file=sys.stderr)
    print("vendor lock OK" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

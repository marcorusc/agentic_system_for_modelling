#!/usr/bin/env python3
"""Build and verify the data-product manifest of a data-analyst session.

CLI:
  manifest.py build --session ID [--skills NAME ...]
  manifest.py verify --session ID
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.data.common import project_root, reject_symlinks, session_dir, sha256_file  # noqa: E402
from scripts.data.environment import lock_sha256  # noqa: E402
from scripts.data.ledger import validate_entry  # noqa: E402
from scripts.data.vendor_lock import VENDORED_SKILLS  # noqa: E402

LAYERS = ("spec", "neko", "maboss", "biomass", "physicell")
KINDS = ("seed_genes", "initial_states", "mutations", "validation_targets", "parameters", "time_course")
PROPOSAL_ID_RE = re.compile(r"\AP\d+\Z")
TABULAR = {".csv": ",", ".tsv": "\t"}
IDENTITY_FIELDS = ("session_id", "derived_from_session_id")


def _read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _read_index(session: Path, name: str) -> list:
    data = _read_json(session / name / "index.json", [])
    if not isinstance(data, list) or not all(isinstance(e, dict) for e in data):
        raise ValueError(f"{name}/index.json must be a list of objects")
    return data


def _files(session: Path, sub: str, suffix: str | None = None) -> list[str]:
    base = session / sub
    found = []
    if base.is_dir():
        for p in base.rglob("*"):
            if (p.is_symlink() or not p.is_dir()) and (suffix is None or p.suffix == suffix):
                found.append(p.relative_to(session).as_posix())
    return sorted(found)


def _read_ledger(session: Path) -> list:
    path = session / "sources.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _check_source(root: Path, session_id: str, index: int, entry: dict, errors: list[str]) -> None:
    """R24: a source path is root-relative and its bytes still match the ledger."""
    rel = entry["path"]
    parts = Path(rel).parts
    allowed = (("data-cache", "sha256"), ("runs", "data-analyst", session_id, "raw"), ("inputs",))
    if (Path(rel).is_absolute() or "\\" in rel or ".." in parts
            or not any(parts[:len(p)] == p and len(parts) > len(p) for p in allowed)):
        errors.append(f"source {index}: path must be root-relative under data-cache/sha256/, "
                      f"runs/data-analyst/{session_id}/raw/ or inputs/: {rel}")
        return
    path = Path(root) / rel
    try:
        reject_symlinks(path, Path(root))
    except ValueError as exc:
        errors.append(f"source {index} {rel}: {exc}")
        return
    if not path.is_file():
        errors.append(f"source {index} {rel}: not a regular file")
    elif sha256_file(path) != entry["sha256"]:
        errors.append(f"source {index} {rel}: hash mismatch")


def _hashed(session: Path, rel: str) -> str:
    return sha256_file(session / rel)


def build(root: Path, session_id: str, skills: list[str]) -> dict:
    session = session_dir(root, session_id)
    identity = _read_json(session / "identity.json")
    sources = _read_ledger(session)
    outputs = []
    for entry in _read_index(session, "outputs"):
        outputs.append({**entry, "sha256": _hashed(session, entry["path"])})
    proposals = []
    for entry in _read_index(session, "proposals"):
        proposals.append({**entry, "sha256": _hashed(session, entry["path"]), "status": "proposed"})
    data = {
        "schema_version": 1,
        "specialist": "data_analyst",
        "stage": "data",
        "session_id": identity["session_id"],
        "derived_from_session_id": identity["derived_from_session_id"],
        "environment": {"python": platform.python_version(), "lock_sha256": lock_sha256(root)},
        "vendored_skills_used": list(skills),
        "sources": sources,
        "scripts": [{"path": p, "sha256": _hashed(session, p)} for p in _files(session, "scripts", ".py")],
        "outputs": outputs,
        "proposals": proposals,
    }
    (session / "manifest.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def _check_listed(session: Path, items, label: str, prefix: str, errors: list[str]) -> set[str]:
    listed: set[str] = set()
    if not isinstance(items, list):
        errors.append(f"{label} must be a list")
        return listed
    for item in items:
        rel = item.get("path") if isinstance(item, dict) else None
        if not isinstance(rel, str) or not rel:
            errors.append(f"{label} entry needs a string path")
            continue
        listed.add(rel)
        parts = Path(rel).parts
        if Path(rel).is_absolute() or ".." in parts or parts[:1] != (prefix,):
            errors.append(f"{label} path must be relative under {prefix}/: {rel}")
            continue
        path = session / rel
        try:
            reject_symlinks(path, session)
        except ValueError as exc:
            errors.append(f"{label} {rel}: {exc}")
            continue
        if not path.is_file():
            errors.append(f"{label} {rel}: not a regular file")
        elif sha256_file(path) != item.get("sha256"):
            errors.append(f"{label} {rel}: hash mismatch")
    return listed


def _numeric_columns(path: Path, delimiter: str) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        values: dict[str, list[str]] = {name: [] for name in reader.fieldnames or []}
        for row in reader:
            for name in values:
                cell = row.get(name)
                if cell is not None and cell.strip():
                    values[name].append(cell)
    numeric = []
    for name, cells in values.items():
        if not cells:
            continue
        try:
            for cell in cells:
                float(cell)
        except ValueError:
            continue
        numeric.append(name)
    return numeric


def _check_output(session: Path, entry: dict, errors: list[str]) -> None:
    rel = entry.get("path")
    if not isinstance(rel, str):
        return
    ident = entry.get("identifiers")
    if not isinstance(ident, str) or not ident.strip():
        errors.append(f"output {rel}: identifiers must be a non-empty string")
    units = entry.get("units")
    unit_ok = units in ("dimensionless", "none") or (
        isinstance(units, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in units.items())
    )
    if not unit_ok:
        errors.append(f"output {rel}: units must be a dict, 'dimensionless' or 'none'")
        return
    delimiter = TABULAR.get(Path(rel).suffix.lower())
    path = session / rel
    if delimiter is None or units == "dimensionless" or not path.is_file() or path.is_symlink():
        return
    declared = units if isinstance(units, dict) else {}
    try:
        columns = _numeric_columns(path, delimiter)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        errors.append(f"output {rel}: cannot read table: {exc}")
        return
    for name in columns:
        if name not in declared:
            errors.append(f"output {rel}: numeric column {name!r} has no unit")


def verify(root: Path, session_id: str) -> list[str]:
    session = session_dir(root, session_id)
    errors: list[str] = []
    path = session / "manifest.json"
    if not path.is_file():
        return ["manifest.json is missing"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        identity = _read_json(session / "identity.json")
    except (OSError, ValueError) as exc:
        return [f"cannot read manifest or identity: {exc}"]
    if not isinstance(data, dict) or not isinstance(identity, dict):
        return ["manifest.json and identity.json must be objects"]

    for key, expected in (("schema_version", 1), ("specialist", "data_analyst"), ("stage", "data")):
        if data.get(key) != expected:
            errors.append(f"{key} must be {expected!r}")
    for key in IDENTITY_FIELDS:
        if data.get(key) != identity.get(key):
            errors.append(f"{key} does not match identity.json")

    skills = data.get("vendored_skills_used")
    if not isinstance(skills, list):
        errors.append("vendored_skills_used must be a list")
    else:
        for skill in skills:
            if skill not in VENDORED_SKILLS:
                errors.append(f"unknown vendored skill: {skill!r}")

    sources = data.get("sources")
    if not isinstance(sources, list):
        errors.append("sources must be a list")
    else:
        for i, entry in enumerate(sources):
            try:
                validate_entry(entry)
            except ValueError as exc:
                errors.append(f"source {i}: {exc}")
                continue
            _check_source(root, session_id, i, entry, errors)
        try:
            ledgered = _read_ledger(session)
        except (OSError, ValueError) as exc:
            errors.append(f"cannot read sources.jsonl: {exc}")
        else:
            if sources != ledgered:
                errors.append("manifest sources differ from sources.jsonl")

    scripts = _check_listed(session, data.get("scripts"), "script", "scripts", errors)
    outputs = _check_listed(session, data.get("outputs"), "output", "outputs", errors)
    proposals = _check_listed(session, data.get("proposals"), "proposal", "proposals", errors)
    for label, sub, listed, skip in (
        ("script", "scripts", scripts, None),
        ("output", "outputs", outputs, "outputs/index.json"),
        ("proposal", "proposals", proposals, "proposals/index.json"),
    ):
        for rel in _files(session, sub, ".py" if sub == "scripts" else None):
            if rel != skip and rel not in listed:
                errors.append(f"{label} not listed in manifest: {rel}")

    if isinstance(data.get("outputs"), list):
        for entry in data["outputs"]:
            if isinstance(entry, dict):
                _check_output(session, entry, errors)

    if isinstance(data.get("proposals"), list):
        seen: set[str] = set()
        for entry in data["proposals"]:
            if not isinstance(entry, dict):
                errors.append("proposal entry must be an object")
                continue
            pid = entry.get("id")
            if not isinstance(pid, str) or PROPOSAL_ID_RE.fullmatch(pid) is None:
                errors.append(f"proposal id must match ^P\\d+$: {pid!r}")
            elif pid in seen:
                errors.append(f"duplicate proposal id: {pid}")
            else:
                seen.add(pid)
            if entry.get("target_layer") not in LAYERS:
                errors.append(f"proposal {pid}: target_layer must be one of {LAYERS}")
            if entry.get("kind") not in KINDS:
                errors.append(f"proposal {pid}: kind must be one of {KINDS}")
            if entry.get("status") != "proposed":
                errors.append(f"proposal {pid}: status must be 'proposed'")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--session", required=True)
    b.add_argument("--skills", nargs="*", default=[])
    v = sub.add_parser("verify")
    v.add_argument("--session", required=True)
    args = parser.parse_args(argv)
    root = project_root().resolve()
    try:
        if args.command == "build":
            build(root, args.session, args.skills)
            print(f"manifest written for {args.session}")
            return 0
        errors = verify(root, args.session)
    except (ValueError, KeyError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("manifest verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())

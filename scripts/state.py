#!/usr/bin/env python3
"""Checked, atomic edits of the human-readable scientific sources of truth.

JSON inputs are files, never interpolated shell fragments. Governance records live
in DECISIONS.md itself; they record researcher authorization, not grant it.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    # Run as `python3 scripts/state.py`: make the `scripts` package importable.
    sys.path.insert(0, str(ROOT))
REGISTRY = ["Specialist", "Session ID", "Stage", "Status", "Derived from", "Handoff", "Artifacts"]
DECISIONS = ["Date", "Decision", "Alternatives considered", "Rationale", "Evidence", "Approved by"]
VALIDATION = ["Criterion", "Method", "Required evidence", "Status", "Result"]
DATA_DICTIONARY = ["Name", "Type", "Biological meaning", "Unit", "Source", "Version", "Notes"]
DATA_PRODUCT_KEYS = {"name", "type", "meaning", "unit", "identifiers", "source_session", "path", "sha256", "release", "decision_id", "notes"}
RECORD = re.compile(r"<!-- governance-record -->\s*```json\n(.*?)\n```", re.S)
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ROLES = {"network-curator": "topology", "boolean-dynamics-modeler": "boolean-dynamics", "multicellular-configurator": "multicellular", "ode-modeler": "biomass_ode", "data-analyst": "data"}

GOVERNANCE_STAGES = set(ROLES.values()) | {"data_mapping", "data_seeds"}


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value) or value in {".", ".."}:
        raise ValueError("invalid complete identifier")
    return value


def artifact(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("artifact must be a repository-relative path")
    path = root / value
    if ".." in Path(value).parts or any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
        raise ValueError("artifact traversal/symlink is forbidden")
    path.resolve().relative_to(root.resolve())
    if not path.is_file():
        raise ValueError(f"missing artifact: {value}")
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_artifact(root, item):
    if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
        raise ValueError("artifact reference requires path and sha256")
    path = artifact(root, item["path"])
    if digest(path) != item["sha256"]:
        raise ValueError(f"artifact hash mismatch: {item['path']}")
    return path


# Characters a Markdown table cell cannot hold: the delimiter, and every control, line- or
# paragraph-separator character (str.splitlines breaks on \x0b, \x0c, \x1c-\x1e, \x85, U+2028, U+2029).
UNSAFE_CELL_CATEGORIES = {"Cc", "Zl", "Zp"}


def unsafe_cell_char(value):
    """The first character of `value` that a table cell cannot hold, or None."""
    return next((c for c in value if c == "|" or unicodedata.category(c) in UNSAFE_CELL_CATEGORIES), None)


def cell(value):
    value = str(value)
    bad = unsafe_cell_char(value)
    if bad is not None:
        raise ValueError(f"table cell contains a delimiter, newline or control character ({bad!r})")
    return value


def table(text, headers):
    lines = text.splitlines()
    matches = [i for i, line in enumerate(lines) if [x.strip() for x in line.strip().strip("|").split("|")] == headers]
    if len(matches) != 1:
        raise ValueError("expected exactly one recognized state table")
    start = matches[0] + 2
    if start > len(lines) or not re.fullmatch(r"[| :\-]+", lines[start - 1]):
        raise ValueError("invalid table separator")
    end = start
    rows = []
    while end < len(lines) and lines[end].startswith("|"):
        values = [x.strip().strip("`") for x in lines[end].strip().strip("|").split("|")]
        if len(values) != len(headers):
            raise ValueError("malformed state row")
        if values[0] != "_(none yet)_":
            rows.append(dict(zip(headers, values)))
        end += 1
    return lines, start, end, rows


def replace_table(text, headers, rows):
    lines, start, end, _ = table(text, headers)
    lines[start:end] = ["| " + " | ".join(cell(row[h]) for h in headers) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def records(text):
    result = [json.loads(m.group(1)) for m in RECORD.finditer(text)]
    if text.count("<!-- governance-record -->") != len(result):
        raise ValueError("malformed governance record")
    if any(not isinstance(r, dict) for r in result):
        raise ValueError("governance records must be JSON objects")
    ids = [identifier(r.get("id")) for r in result]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate governance record ID")
    return result


@contextlib.contextmanager
def locked(root):
    # Locks belong to machine-local infrastructure, not scientific state.
    import fcntl
    folder = root / ".setup"
    folder.mkdir(exist_ok=True)
    with (folder / "state.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def atomic(path, text):
    if path.is_symlink():
        raise ValueError("refusing symlinked state file")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".state-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def validate_record(root, item):
    if not isinstance(item, dict):
        raise ValueError("governance record must be an object")
    identifier(item.get("id"))
    kind = item.get("kind")
    if kind not in {"stage_approval", "stage_review", "conditional_approval", "standalone_approval"}:
        raise ValueError("unknown governance record kind")
    if kind != "standalone_approval":
        identifier(item.get("session_id"))
    if item.get("stage") not in GOVERNANCE_STAGES:
        raise ValueError("unknown scientific stage")
    if kind == "stage_review":
        if item.get("outcome") not in {"approved", "approved_with_limitations", "revision_required", "blocked"}:
            raise ValueError("invalid review outcome")
        for role in ("scientific-reviewer", "reproducibility-auditor"):
            checked_artifact(root, item.get(role))
        checked_artifact(root, item.get("artifact"))
    elif kind in {"stage_approval", "standalone_approval"}:
        if item.get("approved_by") != "researcher" or not item.get("authorization"):
            raise ValueError("explicit researcher authorization quotation/reference required")
        if not isinstance(item.get("outputs"), list) or not item["outputs"] or any(not isinstance(x, str) or not x for x in item["outputs"]) or len(item["outputs"]) != len(set(item["outputs"])):
            raise ValueError("explicit unique nonempty declared outputs required")
        checked_artifact(root, item.get("artifact"))
    else:
        if item.get("approved_by") != "researcher" or not item.get("authorization"):
            raise ValueError("conditional approval needs explicit researcher authorization")
        from scripts.evidence_contract import report_identity, validate_footer
        report = checked_artifact(root, item.get("evidence"))
        session, source, target, _, _ = report_identity(root.resolve(), report.resolve())
        edge = item.get("edge")
        if not isinstance(edge, list) or len(edge) != 3 or any(not isinstance(x, str) or not x for x in edge):
            raise ValueError("conditional approval requires its exact literal [source, effect, target] edge")
        from scripts.codex.write_literature_report import validate_report
        validate_report(report.read_text(), source, target, item["session_id"])
        footer = validate_footer(report.read_text(), source, target, item["session_id"])
        if session != item["session_id"] or footer["edge"] != edge:
            raise ValueError("conditional approval edge/session disagrees with evidence identity")
        conditions = item.get("conditions")
        if not isinstance(conditions, dict) or not conditions or set(conditions) - {"verdict", "confidence", "interaction_type"}:
            raise ValueError("conditions must name supported evidence footer fields")
        if any(not isinstance(v, list) or not v or any(not isinstance(x, str) for x in v) for v in conditions.values()):
            raise ValueError("condition values must be nonempty string allowlists")


def data_product_approval(root, item):
    """Require decision_id to be the researcher's stage_approval of this data session's
    current handoff.json, and the product to be an approved artifact of that handoff."""
    from scripts.data import approvals
    from scripts.data.common import RUNS_ROOT
    session = item["source_session"]
    record = approvals.require_data_approval(root, item["decision_id"], session)
    listed = approvals.require_in_handoff(root, session, item["path"], item["sha256"])
    base = (RUNS_ROOT / session).as_posix()
    if item["path"].startswith(f"{base}/proposals/"):
        entry = approvals.proposal_entry_for_path(root, session, item["path"], listed)
        approvals.require_proposal_approved(root, record, session, entry["id"])


def update(root, operation, item):
    if not isinstance(item, dict):
        raise ValueError("state update must be a JSON object")
    root = root.resolve()
    with locked(root):
        name = "DECISIONS.md" if operation in {"decision", "record"} else "DATA_DICTIONARY.md" if operation == "data-product" else "VALIDATION_PLAN.md" if operation in {"validation", "validation-declare"} else "CURRENT_STATE.md"
        path = root / name
        text = path.read_text(encoding="utf-8")
        if operation == "decision":
            if set(item) != set(DECISIONS) - {"Date"}:
                raise ValueError("decision requires all decision-table fields except generated Date")
            rows = table(text, DECISIONS)[3]
            rows.append({"Date": now(), **item})
            text = replace_table(text, DECISIONS, rows)
        elif operation == "record":
            validate_record(root, item)
            if item["id"] in {r["id"] for r in records(text)}:
                raise ValueError("governance record ID already exists")
            item = {**item, "recorded_at": now()}
            text = text.rstrip() + "\n\n<!-- governance-record -->\n```json\n" + json.dumps(item, indent=2) + "\n```\n"
        elif operation == "registry-add":
            if set(item) != set(REGISTRY):
                raise ValueError("registry fields do not match schema")
            identifier(item["Session ID"])
            if ROLES.get(item["Specialist"]) != item["Stage"] or item["Status"] != "active" or item["Handoff"] not in {"pending", "approved", "exported"}:
                raise ValueError("invalid role, stage, status or handoff")
            if item["Derived from"] != "—":
                identifier(item["Derived from"])
            rows = table(text, REGISTRY)[3]
            if any(r["Session ID"] == item["Session ID"] for r in rows):
                raise ValueError("session already registered")
            rows.append(item)
            text = replace_table(text, REGISTRY, rows)
        elif operation in {"registry-supersede", "registry-handoff"}:
            rows = table(text, REGISTRY)[3]
            matches = [r for r in rows if r["Session ID"] == item.get("session_id")]
            if len(matches) != 1:
                raise ValueError("expected exactly one existing session")
            row = matches[0]
            if row["Status"] != "active":
                raise ValueError("only an active registry row may change")
            if operation == "registry-supersede":
                row["Status"] = "superseded"
            else:
                allowed = {"pending": "approved", "approved": "exported"}
                if allowed.get(row["Handoff"]) != item.get("handoff"):
                    raise ValueError("handoff transitions must be pending -> approved -> exported")
                if item["handoff"] == "exported":
                    checked_artifact(root, item.get("artifact"))
                row["Handoff"] = item["handoff"]
            text = replace_table(text, REGISTRY, rows)
        elif operation == "validation-declare":
            if set(item) != {"Criterion", "Method", "Required evidence"}:
                raise ValueError("criterion declaration requires Criterion, Method and Required evidence")
            identifier(item["Criterion"])
            if any(not isinstance(value, str) or not value.strip() for value in item.values()):
                raise ValueError("criterion declaration fields must be nonempty strings")
            rows = table(text, VALIDATION)[3]
            if any(row["Criterion"] == item["Criterion"] for row in rows):
                raise ValueError("criterion is already declared")
            rows.append({**item, "Status": "pending", "Result": "—"})
            text = replace_table(text, VALIDATION, rows)
        elif operation == "validation":
            if item.get("schema_version") != 1 or item.get("kind") != "artifact_validation":
                raise ValueError("only supported validator output may update validation status")
            checked_artifact(root, item.get("criteria"))
            rows = table(text, VALIDATION)[3]
            seen = set()
            for result in item.get("results", []):
                key = result.get("criterion_id")
                if key in seen or result.get("status") not in {"passed", "failed", "incomplete"}:
                    raise ValueError("duplicate criterion or invalid validation status")
                seen.add(key)
                matches = [r for r in rows if r["Criterion"] == key]
                if len(matches) != 1:
                    raise ValueError(f"expected exactly one declared criterion: {key}")
                for source in result.get("inputs", []):
                    checked_artifact(root, source)
                matches[0]["Status"] = result["status"]
                matches[0]["Result"] = cell(json.dumps({"metrics": result.get("metrics", {}), "criteria_sha256": item["criteria"]["sha256"], "inputs": result.get("inputs", [])}, sort_keys=True))
            if not seen:
                raise ValueError("validator output has no results")
            text = replace_table(text, VALIDATION, rows)
        elif operation == "data-product":
            if set(item) != DATA_PRODUCT_KEYS or any(not isinstance(v, str) for v in item.values()):
                raise ValueError("data-product requires exactly: " + ", ".join(sorted(DATA_PRODUCT_KEYS)))
            from scripts.data.common import SESSION_RE
            if SESSION_RE.fullmatch(item["source_session"]) is None:
                raise ValueError("source_session is not a data session ID")
            if not item["name"].strip() or not item["release"].strip():
                raise ValueError("data product needs a name and release")
            checked_artifact(root, {"path": item["path"], "sha256": item["sha256"]})
            data_product_approval(root, item)
            rows = table(text, DATA_DICTIONARY)[3]
            if any(r["Name"] == item["name"] for r in rows):
                raise ValueError("data product name already registered")
            rows.append({"Name": item["name"], "Type": item["type"], "Biological meaning": item["meaning"], "Unit": item["unit"],
                         "Source": f"`{item['source_session']}` `{item['path']}` sha256 `{item['sha256'][:12]}`",
                         "Version": item["release"],
                         "Notes": f"identifiers: {item['identifiers']}; decision {item['decision_id']}; {item['notes']}"})
            text = replace_table(text, DATA_DICTIONARY, rows)
        elif operation == "checkpoint":
            commit = item.get("commit", "")
            if not re.fullmatch(r"[a-f0-9]{40}", commit) or not item.get("summary"):
                raise ValueError("checkpoint needs a full content commit ID and summary")
            text = text.rstrip() + f"\n\n- Checkpoint {now()}: `{commit}` — {cell(item['summary'])}\n"
        else:
            raise ValueError("unknown state operation")
        atomic(path, text)
    return {"path": name, "sha256": digest(path), "operation": operation}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["decision", "record", "registry-add", "registry-supersede", "registry-handoff", "validation-declare", "validation", "checkpoint", "data-product"])
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(update(args.root, args.operation, json.loads(args.input.read_text())), indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"State update refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

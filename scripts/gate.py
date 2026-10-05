#!/usr/bin/env python3
"""Fail closed on unreviewed, unapproved or stale downstream stage requests."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.state import ROOT, REGISTRY, checked_artifact, identifier, records, table, validate_record

UPSTREAM = {"boolean-dynamics": ("network-curator", "topology"), "multicellular": ("boolean-dynamics-modeler", "boolean-dynamics"), "biomass_ode": ("network-curator", "topology")}
SPECIALIST_STAGE = {"boolean_dynamics_modeler": "boolean-dynamics", "multicellular_configurator": "multicellular", "ode_modeler": "biomass_ode"}


def _names(value, label):
    if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x.strip() for x in value) or len(set(value)) != len(value):
        raise ValueError(f"{label} must be a nonempty unique string list")
    return value


def _reference(root, ref, server, session, role):
    if not isinstance(ref, dict) or (ref.get("server"), ref.get("session_id"), ref.get("role")) != (server, session, role):
        raise ValueError(f"missing or wrong-owner {role} artifact reference")
    raw = ref.get("path")
    if not isinstance(raw, str) or not raw:
        raise ValueError("artifact path is missing")
    path = Path(raw)
    if path.is_absolute():
        path = path.relative_to(root.resolve())
    file = checked_artifact(root, {"path": path.as_posix(), "sha256": ref.get("sha256")})
    suffix, media = {"neko_bnet": (".bnet", "text/plain"), "maboss_bnd": (".bnd", "text/plain"),
                     "maboss_cfg": (".cfg", "text/plain"), "maboss_result": (".csv", "text/csv"),
                     "parent_manifest": (".json", "application/json"), "neko_ode_network": (".json", "application/json")}[role]
    if ref.get("name") != file.name or ref.get("suffix") != suffix or file.suffix != suffix or ref.get("media_type") != media:
        raise ValueError("artifact name, suffix or media type mismatch")
    if type(ref.get("size_bytes")) is not int or ref["size_bytes"] != file.stat().st_size:
        raise ValueError("artifact byte count mismatch")
    return file


def verify_manifest(root, data, expected_type, session, outputs=None):
    """Verify the versioned identity, required payloads and complete parent chain.

    This read-only boundary adds checks before the server's own typed import;
    it never imports modelling libraries or executes a scientific operation.
    """
    if not isinstance(data, dict) or (data.get("schema_name"), data.get("schema_version"), data.get("handoff_type")) != ("mcp-biomodelling-handoff", "1.0", expected_type):
        raise ValueError("expected version-1.0 typed handoff for this downstream stage")
    server = "MaBoSS" if expected_type == "maboss-to-physicell" else "NeKo"
    source = data.get("source")
    if not isinstance(source, dict) or (source.get("server"), source.get("session_id")) != (server, session):
        raise ValueError("handoff source server/session mismatch")
    network = data.get("network")
    if not isinstance(network, dict):
        raise ValueError("handoff network is missing")
    nodes = _names(network.get("nodes"), "network nodes")
    declared = _names(network.get("output_nodes"), "declared outputs")
    if not set(declared) <= set(nodes) or (outputs is not None and declared != outputs):
        raise ValueError("declared outputs do not match exported network")
    if expected_type == "neko-to-maboss":
        if data.get("lineage", []):
            raise ValueError("NeKo source cannot declare upstream lineage")
        bnet = _reference(root, data.get("bnet_file"), server, session, "neko_bnet")
        actual = [line.split(",", 1)[0].strip() for line in bnet.read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#") and "," in line and line.split(",", 1)[0].strip().lower() != "targets"]
        if actual != nodes:
            raise ValueError("BNET targets do not match declared network nodes")
    elif expected_type == "neko-to-biomass":
        _reference(root, data.get("network_file"), server, session, "neko_ode_network")
    else:
        bnd = _reference(root, data.get("bnd_file"), server, session, "maboss_bnd")
        cfg = _reference(root, data.get("cfg_file"), server, session, "maboss_cfg")
        text = re.sub(r"/\*.*?\*/", "", bnd.read_text(), flags=re.S)
        text = re.sub(r"//[^\n]*", "", text)
        if re.findall(r"(?im)^\s*Node\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{", text) != nodes:
            raise ValueError("BND nodes do not match declared network nodes")
        simulation = data.get("simulation")
        target = data.get("target")
        if not isinstance(simulation, dict) or not isinstance(target, dict) or not isinstance(target.get("cell_type"), str) or not target["cell_type"].strip():
            raise ValueError("MaBoSS simulation/target metadata is missing")
        if simulation.get("result_file") is not None:
            _reference(root, simulation["result_file"], server, session, "maboss_result")
        parent = data.get("parent_manifest")
        lineage = data.get("lineage", [])
        if parent is None:
            if lineage:
                raise ValueError("declared upstream lineage needs parent manifest")
        else:
            if not isinstance(lineage, list) or len(lineage) != 1 or not isinstance(lineage[0], dict) or lineage[0].get("server") != "NeKo":
                raise ValueError("parent manifest requires exactly one NeKo lineage entry")
            upstream = identifier(lineage[0].get("session_id"))
            file = _reference(root, parent, "NeKo", upstream, "parent_manifest")
            verify_manifest(root, json.loads(file.read_text()), "neko-to-maboss", upstream)
    return data


def check(root, stage, session, outputs):
    if stage not in UPSTREAM:
        raise ValueError("unknown downstream stage")
    identifier(session)
    if not isinstance(outputs, list) or not outputs or any(not isinstance(x, str) or not x for x in outputs) or len(set(outputs)) != len(outputs):
        raise ValueError("request must name exact unique declared outputs")
    role, upstream_stage = UPSTREAM[stage]
    rows = table((root / "CURRENT_STATE.md").read_text(), REGISTRY)[3]
    matching = [r for r in rows if r["Session ID"] == session]
    if len(matching) != 1:
        raise ValueError("upstream session must have exactly one registry row")
    row = matching[0]
    if (row["Specialist"], row["Stage"], row["Status"], row["Handoff"]) != (role, upstream_stage, "active", "exported"):
        raise ValueError("upstream must be active, at the expected stage, and exactly exported")
    recs = records((root / "DECISIONS.md").read_text())
    approvals = [r for r in recs if r.get("kind") == "stage_approval" and r.get("session_id") == session and r.get("stage") == upstream_stage and r.get("downstream_stage") == stage and r.get("outputs") == outputs]
    if not approvals:
        raise ValueError("no researcher approval names this session, downstream stage and exact outputs")
    approval = approvals[-1]
    validate_record(root, approval)
    manifest = checked_artifact(root, approval["artifact"])
    prefix = f"runs/{role}/{session}/"
    if not approval["artifact"]["path"].startswith(prefix):
        raise ValueError("handoff artifact must be inside the exact upstream session")
    data = json.loads(manifest.read_text())
    expected_type = {"boolean-dynamics": "neko-to-maboss", "multicellular": "maboss-to-physicell", "biomass_ode": "neko-to-biomass"}[stage]
    verify_manifest(root, data, expected_type, session, outputs)
    if stage == "multicellular" and row["Derived from"] != "—":
        if (data.get("parent_manifest") or {}).get("session_id") != row["Derived from"]:
            raise ValueError("registry upstream lineage and exported parent disagree")
    reviews = [r for r in recs if r.get("kind") == "stage_review" and r.get("session_id") == session and r.get("stage") == upstream_stage]
    if not reviews:
        raise ValueError("independent scientific review and reproducibility audit have not been recorded")
    review = reviews[-1]
    validate_record(root, review)
    if review["outcome"] not in {"approved", "approved_with_limitations"} or review["artifact"] != approval["artifact"]:
        raise ValueError("latest independent review blocks or covers a different artifact revision")
    if recs.index(review) > recs.index(approval):
        raise ValueError("researcher approval must follow the independent review")
    return {"passed": True, "downstream_stage": stage, "upstream_session_id": session, "outputs": outputs, "approval_id": approval["id"], "review_id": review["id"], "artifact": approval["artifact"]}


def standalone(root, stage, decision_id, outputs):
    matching = [r for r in records((root / "DECISIONS.md").read_text()) if r.get("id") == decision_id]
    if len(matching) != 1:
        raise ValueError("missing explicit standalone authorization record")
    record = matching[0]
    validate_record(root, record)
    if record["kind"] != "standalone_approval" or record["stage"] != stage or record["outputs"] != outputs:
        raise ValueError("standalone approval scope mismatch")
    return {"passed": True, "downstream_stage": stage, "standalone_decision_id": decision_id, "artifact": record["artifact"], "outputs": outputs}


def check_task(root, specialist, task):
    """A literal first-line envelope makes dispatch context machine-checkable.

    The task still contains the full bounded scientific instructions. A prompt
    assertion alone cannot pass: matching durable records and hashes are required.
    """
    if specialist not in SPECIALIST_STAGE:
        return None
    first = task.splitlines()[0] if task else ""
    if not first.startswith("STAGE_GATE "):
        raise ValueError("downstream dispatch requires first-line STAGE_GATE JSON; run scripts/gate.py first")
    value = json.loads(first[len("STAGE_GATE "):])
    if not isinstance(value, dict):
        raise ValueError("STAGE_GATE must be a JSON object")
    stage = SPECIALIST_STAGE[specialist]
    if set(value) == {"standalone_decision_id", "outputs"}:
        return standalone(root, stage, value["standalone_decision_id"], value["outputs"])
    if set(value) != {"upstream_session_id", "outputs"}:
        raise ValueError("STAGE_GATE requires upstream_session_id and outputs")
    return check(root, stage, value["upstream_session_id"], value["outputs"])


def resolve_condition(root, decision_id):
    from scripts.evidence_contract import report_identity, validate_footer
    matches = [r for r in records((root / "DECISIONS.md").read_text()) if r.get("id") == decision_id]
    if len(matches) != 1 or matches[0].get("kind") != "conditional_approval":
        raise ValueError("missing unique conditional approval")
    record = matches[0]
    validate_record(root, record)
    report = checked_artifact(root, record["evidence"])
    _, source, target, _, _ = report_identity(root.resolve(), report.resolve())
    footer = validate_footer(report.read_text(), source, target, record["session_id"])
    if footer["neko_session_id"] != record["session_id"]:
        raise ValueError("conditional evidence session mismatch")
    result = all(footer.get(field) in values for field, values in record["conditions"].items())
    return {"decision_id": decision_id, "satisfied": result, "evidence": record["evidence"], "supporting_pmids": footer["supporting_pmids"], "mutation_performed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    checker = sub.add_parser("check")
    checker.add_argument("downstream_stage", choices=list(UPSTREAM))
    checker.add_argument("upstream_session")
    checker.add_argument("--outputs", nargs="+", required=True)
    condition = sub.add_parser("resolve")
    condition.add_argument("decision_id")
    args = parser.parse_args()
    try:
        result = check(args.root, args.downstream_stage, args.upstream_session, args.outputs) if args.command == "check" else resolve_condition(args.root, args.decision_id)
        print(json.dumps(result, indent=2))
        return 0 if result.get("passed", result.get("satisfied")) else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"passed": False, "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

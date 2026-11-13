#!/usr/bin/env python3
"""Fail closed on unreviewed, unapproved or stale downstream stage requests."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import re
from pathlib import Path
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.state import ROOT, REGISTRY, checked_artifact, identifier, records, table, validate_record
from scripts.curation_contract import check_binding, check_parent_scope, check_readout_isolation
from scripts.data import approvals
from scripts.data.manifest import KIND_SCHEMAS

UPSTREAM = {"boolean-dynamics": ("network-curator", "topology"), "multicellular": ("boolean-dynamics-modeler", "boolean-dynamics"), "biomass_ode": ("network-curator", "topology")}
# Backend 2.5.0: NeKo->MaBoSS 2.1 and NeKo->BioMASS 2.0 carry curation_file;
# MaBoSS->PhysiCell 2.1 carries model_revision and readout definitions.
VERSIONS = {"neko-to-maboss": {"1.0", "2.0", "2.1"}, "maboss-to-physicell": {"1.0", "2.0", "2.1"},
            "neko-to-biomass": {"1.0", "2.0"}}
CURATED = {("neko-to-maboss", "2.1"): "bnet_file", ("neko-to-biomass", "2.0"): "network_file"}
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
                     "parent_manifest": (".json", "application/json"), "neko_ode_network": (".json", "application/json"),
                     "neko_history": (".json", "application/json")}[role]
    if ref.get("name") != file.name or ref.get("suffix") != suffix or file.suffix != suffix or ref.get("media_type") != media:
        raise ValueError("artifact name, suffix or media type mismatch")
    if type(ref.get("size_bytes")) is not int or ref["size_bytes"] != file.stat().st_size:
        raise ValueError("artifact byte count mismatch")
    return file


def ode_graph_nodes(file):
    """Node IDs of an exported NeKo-to-BioMASS graph, which must be unique."""
    try:
        graph = json.loads(file.read_text())
    except ValueError:
        raise ValueError("ODE network_file is not valid JSON") from None
    items = graph.get("nodes") if isinstance(graph, dict) else None
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("ODE network_file must contain a node list")
    return _names([item.get("node_id") for item in items], "ODE graph node IDs")


def verify_manifest(root, data, expected_type, session, outputs=None):
    """Verify the versioned identity, required payloads and complete parent chain.

    This read-only boundary adds checks before the server's own typed import;
    it never imports modelling libraries or executes a scientific operation.
    """
    if not isinstance(data, dict) or (data.get("schema_name"), data.get("handoff_type")) != ("mcp-biomodelling-handoff", expected_type):
        raise ValueError("expected typed handoff for this downstream stage")
    version = data.get("schema_version")
    if version not in VERSIONS[expected_type]:
        raise ValueError("unsupported typed handoff version for this downstream stage")
    if version != "1.0":
        from scripts.boolean_contract import validate_metadata
        validate_metadata(data)
    elif data.get("source_ancestry") is not None:
        raise ValueError("v1 handoffs cannot declare source ancestry")
    elif any(data.get(key) is not None for key in ("curation_file", "model_revision", "readouts")):
        raise ValueError("v1 handoffs cannot declare curation or readout metadata")
    server = "MaBoSS" if expected_type == "maboss-to-physicell" else "NeKo"
    source = data.get("source")
    if not isinstance(source, dict) or (source.get("server"), source.get("session_id")) != (server, session):
        raise ValueError("handoff source server/session mismatch")
    if expected_type == "neko-to-biomass":
        # An ODE graph has no output selection: its approval names the complete
        # node inventory of the exact exported graph.
        if data.get("network") is not None or data.get("lineage", []):
            raise ValueError("NeKo-to-BioMASS handoffs declare only their network_file graph")
        graph = _reference(root, data.get("network_file"), server, session, "neko_ode_network")
        nodes = ode_graph_nodes(graph)
        if outputs is not None and set(outputs) != set(nodes):
            raise ValueError("ODE approval outputs must name every node_id of the exported graph")
    else:
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
    if (expected_type, version) in CURATED:
        # The companion binds the original model path; every other identity
        # field and the pinned companion bytes must still match the payload.
        companion = _reference(root, data.get("curation_file"), "NeKo", session, "neko_history")
        model = _reference(root, data.get(CURATED[expected_type, version]), "NeKo", session,
                           "neko_bnet" if expected_type == "neko-to-maboss" else "neko_ode_network")
        tree = companion.resolve().relative_to(root.resolve()).parts
        if len(tree) < 4 or tree[0] != "runs" or tree[:3] != model.resolve().relative_to(root.resolve()).parts[:3]:
            raise ValueError("curation companion must be recorded in the same session tree as its model")
        check_binding(companion.read_bytes(), data[CURATED[expected_type, version]], session, data.get("history_state_id"))
    if expected_type == "maboss-to-physicell":
        bnd = _reference(root, data.get("bnd_file"), server, session, "maboss_bnd")
        cfg = _reference(root, data.get("cfg_file"), server, session, "maboss_cfg")
        text = re.sub(r"/\*.*?\*/", "", bnd.read_text(), flags=re.S)
        text = re.sub(r"//[^\n]*", "", text)
        if re.findall(r"(?im)^\s*Node\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{", text) != nodes:
            raise ValueError("BND nodes do not match declared network nodes")
        readouts = data.get("readouts") or {}
        if version == "2.1":
            if not isinstance(data.get("model_revision"), str) or not re.fullmatch(r"[0-9a-f]{64}", data["model_revision"]):
                raise ValueError("MaBoSS v2.1 handoff requires an exact model_revision")
            if not isinstance(data.get("readouts"), dict):
                raise ValueError("MaBoSS v2.1 handoff requires explicit readout definitions")
        check_readout_isolation(bnd.read_text(), nodes, readouts)
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
            parent_data = json.loads(file.read_text())
            verify_manifest(root, parent_data, "neko-to-maboss", upstream)
            if parent_data.get("source") != lineage[0]:
                raise ValueError("parent provenance disagrees with declared stage lineage")
            # Only declared readouts may extend the NeKo core (none before v2.1).
            check_parent_scope(parent_data["network"]["nodes"], parent_data["network"]["output_nodes"],
                               nodes, declared, readouts)
            if version != "1.0":
                inherited = [item for item in data["source_ancestry"] if item["source"]["server"] == "NeKo"]
                if inherited != (parent_data.get("source_ancestry") or []):
                    raise ValueError("current ancestry disagrees with the exact stage parent")
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
        parents = {(data.get("parent_manifest") or {}).get("session_id")}
        if data.get("schema_version") != "1.0":
            # A separately approved BNET derivative retains its immediate source
            # parent without pretending it was an unchanged typed stage import.
            # Only the current session's direct NeKo parent can bind this row;
            # arbitrary/transitive historical sessions never qualify.
            parents.update(
                item["parent_manifest"]["session_id"]
                for item in data["source_ancestry"]
                if (item["source"]["server"], item["source"]["session_id"]) == ("MaBoSS", session)
                and (item.get("parent_manifest") or {}).get("server") == "NeKo"
            )
        if row["Derived from"] not in parents:
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


# Detection runs on a normalised copy of the prompt (see _detection_text); any spelling
# of DATA_INPUT, data-analyst path or data session ID counts.
DATA_PATH = re.compile(r"runs[\\/]+data-analyst", re.I)
DATA_SESSION_PATH = re.compile(r"runs[\\/]+data-analyst[\\/]+([A-Za-z0-9][A-Za-z0-9._-]*)", re.I)
DATA_SESSION_ID = re.compile(r"data-\d{8}T\d{6}Z-[0-9a-f]{8}", re.I)
DATA_INPUT_MENTION = re.compile(r"DATA[_-]?INPUT", re.I)
DATA_REFUSAL = "brief references data-analyst artifacts without a DATA_INPUT line; see CLAUDE.md"
# Specialist -> (0-based line index of its DATA_INPUT line, human label).
DATA_INPUT_LINE = {"network_curator": (0, "network-curator DATA_INPUT must be line 1 of the prompt"),
                   "boolean_dynamics_modeler": (1, "boolean-dynamics-modeler DATA_INPUT must be line 2, after STAGE_GATE")}
SHA256 = re.compile(r"[0-9a-f]{64}")


def _strict_object(text, label):
    def unique(pairs):
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{label} has duplicate keys")
        return dict(pairs)
    try:
        value = json.loads(text, object_pairs_hook=unique)
    except RecursionError:
        raise ValueError(f"{label} JSON is nested too deeply") from None
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _detection_text(task):
    """The prompt NFKC-normalised and without format characters (BOM, zero-width), for detection only."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", task) if unicodedata.category(ch) != "Cf")


def _data_sessions_named(text):
    """Data-analyst sessions named by `runs/data-analyst/<session>` paths or by data session IDs."""
    return ({m.rstrip(".") for m in DATA_SESSION_PATH.findall(text)} | set(DATA_SESSION_ID.findall(text)))


def _newest_data_approval(root, session):
    """The researcher's newest `stage_approval` (stage data) of this data session.

    Newest is the latest `recorded_at` (state.py stamps every record); equal times
    fall back to DECISIONS.md order, which is append-only. When no candidate has a
    time, DECISIONS.md order decides; a mix of timed and untimed records, or an
    unreadable time, is ambiguous and refused.
    """
    recs = records((root / "DECISIONS.md").read_text(encoding="utf-8"))
    found = [(n, r) for n, r in enumerate(recs) if r.get("kind") == "stage_approval"
             and r.get("stage") == "data" and r.get("session_id") == session]
    if not found:
        raise ValueError(f"no researcher stage_approval of stage data names data session {session}")
    times = [r.get("recorded_at") for _, r in found]
    if all(t is None for t in times):
        return found[-1][1]
    keyed = []
    for (n, r), raw in zip(found, times):
        try:
            moment = datetime.fromisoformat(raw) if isinstance(raw, str) else None
        except ValueError:
            moment = None
        if moment is None or moment.tzinfo is None:
            raise ValueError(f"cannot order data approvals of session {session}: "
                             f"record {r.get('id')} has no timezone-aware recorded_at")
        keyed.append((moment, n, r))
    return max(keyed, key=lambda item: item[:2])[2]


def _check_neko_data_input(root, value):
    if set(value) != {"data_session", "proposals"}:
        raise ValueError("network-curator DATA_INPUT requires exactly data_session and proposals")
    session = identifier(value["data_session"])
    proposals = value["proposals"]
    if not isinstance(proposals, dict) or not proposals:
        raise ValueError("DATA_INPUT proposals must be a nonempty object of proposal id -> sha256")
    record = approvals.require_data_approval(root, _newest_data_approval(root, session)["id"], session)
    validate_record(root, record)
    resolved = {}
    for proposal_id, digest in proposals.items():
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ValueError(f"DATA_INPUT proposal {proposal_id} needs a lowercase hex sha256")
        entry = approvals.require_proposal_approved(root, record, session, proposal_id)
        if entry.get("kind") != "seed_genes":
            raise ValueError(f"proposal {proposal_id} has kind {entry.get('kind')!r}; network-curator "
                             "DATA_INPUT takes only seed_genes")
        layer = KIND_SCHEMAS["seed_genes"]["layer"]
        if entry.get("target_layer") != layer:
            raise ValueError(f"proposal {proposal_id} must target {layer}, not {entry.get('target_layer')!r}")
        if entry["sha256"] != digest:
            raise ValueError(f"proposal {proposal_id} sha256 {digest[:12]} differs from the approved file "
                             f"{entry['path']} ({entry['sha256'][:12]})")
        resolved[proposal_id] = {"path": entry["path"], "sha256": entry["sha256"]}
    from scripts.data import mapping
    mapping.validate_data_handoff(root, session)
    return {"data_session": session, "approval_id": record["id"], "proposals": resolved}, {session}


def _check_maboss_data_input(root, value, first_line):
    if set(value) != {"mapping", "sha256", "approval"}:
        raise ValueError("boolean-dynamics-modeler DATA_INPUT requires exactly mapping, sha256 and approval")
    rel, digest, approval_id = value["mapping"], value["sha256"], value["approval"]
    if not all(isinstance(v, str) and v for v in (rel, digest, approval_id)):
        raise ValueError("DATA_INPUT mapping, sha256 and approval must be nonempty strings")
    gate_value = _strict_object(first_line[len("STAGE_GATE "):], "STAGE_GATE") if first_line.startswith("STAGE_GATE ") else {}
    upstream = gate_value.get("upstream_session_id")
    if not isinstance(upstream, str):
        raise ValueError("a MaBoSS DATA_INPUT needs a line-1 STAGE_GATE naming upstream_session_id")
    record = approvals.require_mapping_approval(root, approval_id, rel, digest)
    validate_record(root, record)
    from scripts.data import mapping
    # Check exactly the approved bytes: one read gives both the parsed mapping and its hash.
    data, actual, errors = mapping.load_and_check(root, rel)
    if actual != digest:
        raise ValueError(f"{rel} changed since approval {approval_id} (sha256 mismatch)")
    if errors:
        raise ValueError(f"mapping check failed for {rel}: " + "; ".join(errors))
    ids = ({item.get("id") for item in data["perturbations"]}
           | {item.get("criterion_id") for item in data["criteria"]})
    if set(record["outputs"]) != ids:
        raise ValueError(f"mapping approval {approval_id} outputs {sorted(record['outputs'])} must equal the "
                         f"mapping's perturbation and criterion ids {sorted(ids, key=str)}")
    neko = data["inputs"]["network"]["neko_session"]
    if neko != upstream:
        raise ValueError(f"mapping network is NeKo session {neko}, but STAGE_GATE names {upstream}")
    sessions = {item["session"] for item in data["inputs"]["data"]}
    return {"mapping": rel, "sha256": digest, "approval_id": approval_id, "neko_session": neko}, sessions


def check_data_input(root, specialist, task):
    """Check the DATA_INPUT line by which network-curator and boolean-dynamics-modeler take data.

    Data reach these specialists only as approved, hash-checked artifacts named on a
    literal DATA_INPUT line (line 1 for network-curator, line 2 after STAGE_GATE for
    boolean-dynamics-modeler); data are never pasted or pointed at in prose. Returns
    None when the prompt has neither a DATA_INPUT line nor a data-analyst path.
    """
    if specialist not in DATA_INPUT_LINE:
        return None
    if task is None:
        task = ""
    if not isinstance(task, str):
        raise ValueError("dispatch prompt must be a string")
    lines = task.splitlines()  # the same line split as check_task
    expected, placement = DATA_INPUT_LINE[specialist]
    text = _detection_text(task)
    mentions = len(DATA_INPUT_MENTION.findall(text))
    if not mentions:
        if DATA_PATH.search(text) or DATA_SESSION_ID.search(text):
            raise ValueError(DATA_REFUSAL)
        return None
    # Any spelling of DATA_INPUT anywhere must be exactly the one canonical line.
    if mentions != 1 or len(lines) <= expected or not lines[expected].startswith("DATA_INPUT "):
        raise ValueError(f"{placement}: exactly one line starting 'DATA_INPUT ' and no other "
                         "mention of DATA_INPUT in any spelling")
    value = _strict_object(lines[expected][len("DATA_INPUT "):], "DATA_INPUT")
    if specialist == "network_curator":
        result, sessions = _check_neko_data_input(root, value)
    else:
        result, sessions = _check_maboss_data_input(root, value, lines[0])
    other = sorted(_data_sessions_named(text) - sessions)
    if other:
        raise ValueError(f"brief names data-analyst session(s) {', '.join(other)} outside its DATA_INPUT")
    return result


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

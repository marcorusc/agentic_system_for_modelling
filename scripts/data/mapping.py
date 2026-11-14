#!/usr/bin/env python3
"""Draft, check and turn into criteria the mapping of approved data and user sources onto a MaBoSS model.

The mapping (runs/orchestrator/<purpose>/mapping.json) is the artifact the
researcher and orchestrator agree on: which approved `perturbations` and
`validation_targets` rows, and which researcher-provided sources under inputs/
(any format, never parsed; cited by {source, locator}), become model contexts,
perturbations, readouts and criteria, and why the remaining proposal rows are
left unmapped.

The network is either a NeKo export ({neko_session, bnet, sha256}) or a
researcher-provided BNET with a standalone approval ({standalone_decision_id,
bnet, sha256}; the record's artifact is exactly that .bnet). A .bnd/.cfg-only
model cannot be mapped.

Criterion methods in a mapping are scenario_contrast, ordered_peaks and
canonical_cycles. boolean_structure is refused: it validates network structure,
not data-driven responses, and is declared directly in VALIDATION_CRITERIA.yaml.

CLI:
  mapping.py draft --purpose P [--data SESSION:PROPOSAL:APPROVAL ...] [--source ID:PATH ...]
                   (--network NEKO_SESSION:BNET | --standalone-network STANDALONE_DECISION_ID:BNET)
                                                 (at least one --data or --source; sha256s are computed)
  mapping.py draft --from OLD_MAPPING --purpose P (--network ... | --standalone-network ...)
                                                 (copy OLD onto a re-exported network; prints a note per
                                                  mapped node absent from the new BNET or whose rule changed)
  mapping.py check MAPPING [--stage-gate JSON]   (exit 1, one problem per line on stderr; with the
                                                  STAGE_GATE JSON of the MaBoSS brief, also the gate's
                                                  network binding, which reports a stale mapping, and
                                                  readout nodes outside the STAGE_GATE outputs)
  mapping.py criteria MAPPING --runs RUNS --approval RECORD_ID [--out FILE] [--merge-into VALIDATION_CRITERIA.yaml]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import state  # noqa: E402
from scripts.data import approvals  # noqa: E402
from scripts.data import sources as user_sources  # noqa: E402
from scripts.data.common import RUNS_ROOT, project_root, reject_symlinks, sha256_file, strict_json  # noqa: E402
from scripts.data.manifest import KIND_SCHEMAS, read_proposal_table  # noqa: E402
from scripts.validate.common import load_json_yaml  # noqa: E402
from scripts.validate.scenario_contrast import contrast  # noqa: E402
from scripts.validate.validate_cycles import classify_cycles, ordered_peaks  # noqa: E402

KEYS = ("schema_version", "inputs", "contexts", "perturbations", "readouts", "criteria", "unmapped")
# Which mapping section may consume rows of which proposal kind.
SECTION_KIND = {"perturbations": "perturbations", "criteria": "validation_targets"}
MAPPABLE = tuple(SECTION_KIND.values())
# evaluate.py methods allowed in a mapping, with their keys besides criterion_id, from,
# method, options (and optional note). boolean_structure is deliberately absent.
METHOD_KEYS = {"scenario_contrast": {"test", "reference"}, "ordered_peaks": {"scenarios"},
               "canonical_cycles": {"scenarios"}}
METHODS = tuple(METHOD_KEYS)
PHENOTYPES = KIND_SCHEMAS["validation_targets"]["enums"]["phenotype"]
ORCHESTRATOR = ("runs", "orchestrator")
INPUT_KEYS = {"data", "sources", "network"}
# The two network anchors: a NeKo export, or a researcher BNET with a standalone approval.
NEKO_NETWORK = {"neko_session", "bnet", "sha256"}
STANDALONE_NETWORK = {"standalone_decision_id", "bnet", "sha256"}
STANDALONE_STAGE = "boolean-dynamics"  # the stage a MaBoSS standalone_approval authorizes
NETWORK = ("runs", "network-curator")
TRAJECTORIES = ("runs", "boolean-dynamics-modeler")
SYNTHETIC_MAX_POINTS = 1_000_000


# ---------------------------------------------------------------- helpers

def bnet_rules(path: Path) -> dict[str, str]:
    """Target node -> rule text of a BNET: the text before and after the first comma of each rule line.

    Blank lines, `#` comments and the `targets, factors` header (any spacing or
    case) are skipped, as in scripts/validate/boolean_structure.py.
    """
    rules = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.lower().replace(" ", "") == "targets,factors":
            continue
        if "," not in line:
            raise ValueError(f"BNET row requires 'target, expression': {line!r}")
        node, rule = (part.strip() for part in line.split(",", 1))
        if not node:
            raise ValueError(f"BNET row has an empty target: {line!r}")
        rules[node] = rule
    if not rules:
        raise ValueError("BNET has no nodes")
    return rules


def bnet_nodes(path: Path) -> set[str]:
    """Target nodes of a BNET (see bnet_rules)."""
    return set(bnet_rules(path))


def _parts(rel) -> tuple:
    if not isinstance(rel, str) or not rel or "\\" in rel:
        return ()
    return PurePosixPath(rel).parts


def _mapping_path(root: Path, rel) -> Path:
    parts = _parts(rel)
    if len(parts) != 4 or parts[:2] != ORCHESTRATOR or not rel.endswith(".json"):
        raise ValueError(f"mapping must be runs/orchestrator/<purpose>/<name>.json, not {rel!r}")
    state.identifier(parts[2])
    return state.artifact(root, rel)


def _bnet(root: Path, neko_session, rel) -> Path:
    state.identifier(neko_session)
    parts = _parts(rel)
    if parts[:3] != (*NETWORK, neko_session) or len(parts) < 6 or parts[3] not in ("exports", "boolean-handoffs") \
            or not rel.endswith(".bnet"):
        raise ValueError(f"network BNET must be a .bnet under runs/network-curator/{neko_session}/exports/ or "
                         f"boolean-handoffs/, not {rel!r}")
    return state.artifact(root, rel)


def _standalone_bnet(root: Path, decision_id, rel) -> Path:
    """The BNET a standalone_approval authorizes for MaBoSS (the semantics of gate.standalone).

    The record must be a valid researcher standalone_approval of stage boolean-dynamics whose
    artifact is exactly this .bnet; validate_record has checked the artifact's sha256 on disk.
    """
    state.identifier(decision_id)
    try:
        record = approvals.load_record(root, decision_id)
    except ValueError:
        raise ValueError(f"standalone approval {decision_id} is not a governance record in DECISIONS.md") from None
    if record.get("kind") != "standalone_approval":
        raise ValueError(f"decision {decision_id} must be a standalone_approval, not {record.get('kind')!r}")
    state.validate_record(root, record)
    if record.get("stage") != STANDALONE_STAGE:
        raise ValueError(f"standalone approval {decision_id} must authorize stage {STANDALONE_STAGE}, "
                         f"not {record.get('stage')!r}")
    if not isinstance(rel, str) or not rel.endswith(".bnet"):
        raise ValueError(f"network BNET must be a .bnet, not {rel!r} (a .bnd/.cfg-only model cannot be mapped)")
    if record["artifact"]["path"] != rel:
        raise ValueError(f"standalone approval {decision_id} artifact is {record['artifact']['path']}, not {rel}")
    return state.artifact(root, rel)


def _network_file(root: Path, network: dict) -> Path:
    """The BNET of a {neko_session|standalone_decision_id, bnet, ...} network; ValueError if not allowed."""
    if "standalone_decision_id" in network:
        return _standalone_bnet(root, network["standalone_decision_id"], network["bnet"])
    return _bnet(root, network["neko_session"], network["bnet"])


def _network_entry(root: Path, network) -> tuple[dict, Path]:
    """The inputs.network of a draft and its BNET, from (NEKO_SESSION, BNET) or {anchor: id, "bnet": BNET}."""
    if isinstance(network, (tuple, list)) and len(network) == 2:
        network = {"neko_session": network[0], "bnet": network[1]}
    if not isinstance(network, dict) or set(network) not in ({"neko_session", "bnet"},
                                                             {"standalone_decision_id", "bnet"}):
        raise ValueError("network must be (NEKO_SESSION, BNET) or {standalone_decision_id, bnet}")
    path = _network_file(root, network)
    bnet_nodes(path)
    return {**network, "sha256": sha256_file(path)}, path


def _table_rows(root: Path, rel: str, kind: str) -> list[str]:
    """Row keys of a proposal table, in file order."""
    _, rows = read_proposal_table(state.artifact(root, rel))
    key = KIND_SCHEMAS[kind]["unique"]  # only mappable kinds reach here; both have a unique key
    return [(row.get(key) or "").strip() for row in rows]


def _validate_handoff(root: Path, session_id: str) -> None:
    from scripts.codex.validate_handoff import validate_handoff
    rel = f"{(RUNS_ROOT / session_id).as_posix()}/handoff.json"
    data = json.loads(state.artifact(root, rel).read_text(encoding="utf-8"))
    try:
        validate_handoff(data, project_root=root, expected_specialist="data_analyst", expected_session_id=session_id)
    except ValueError as exc:
        raise ValueError(f"data session {session_id} handoff no longer validates: {exc}") from exc


def _approved_proposal(root: Path, session_id, proposal_id, record_id) -> dict:
    """Resolve an approved, mappable proposal; returns its index entry with path and sha256."""
    if not all(isinstance(v, str) and v for v in (session_id, proposal_id, record_id)):
        raise ValueError("session, proposal and approval must be non-empty strings")
    record = approvals.require_data_approval(root, record_id, session_id)
    entry = approvals.require_proposal_approved(root, record, session_id, proposal_id)
    kind = entry.get("kind")
    if kind == "seed_genes":
        raise ValueError(f"proposal {proposal_id} is seed_genes: seeds go to NeKo through DATA_INPUT, "
                         "not through a MaBoSS mapping")
    if kind not in MAPPABLE:
        raise ValueError(f"proposal {proposal_id} has kind {kind!r}; a mapping takes only {', '.join(MAPPABLE)}")
    if entry.get("target_layer") != "maboss":
        raise ValueError(f"proposal {proposal_id} must target maboss, not {entry.get('target_layer')!r}")
    return entry


def _write_new(root: Path, path: Path, text: str) -> None:
    """Create a new file under root; refuse symlinked components and existing files."""
    reject_symlinks(path, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    reject_symlinks(path, root)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


# ---------------------------------------------------------------- draft

def _new_target(root: Path, purpose: str) -> Path:
    state.identifier(purpose)
    target = root / ORCHESTRATOR[0] / ORCHESTRATOR[1] / purpose / "mapping.json"
    if target.exists() or target.is_symlink():
        raise ValueError(f"{target.relative_to(root).as_posix()} exists; drafts never overwrite a mapping")
    return target


def _write_mapping(root: Path, target: Path, mapping: dict) -> None:
    try:
        _write_new(root, target, json.dumps(mapping, indent=2) + "\n")
    except FileExistsError as exc:
        raise ValueError(f"{target.relative_to(root).as_posix()} exists; drafts never overwrite a mapping") from exc


def draft(root: Path, purpose: str, data: list[tuple[str, str, str]], network,
          sources: list[tuple[str, str]] = ()) -> Path:
    """Write a skeleton mapping: data inputs, user sources (sha256 computed) and the network.

    `network` is (NEKO_SESSION, BNET) or {"standalone_decision_id": ID, "bnet": BNET}.
    """
    root = Path(root)
    target = _new_target(root, purpose)
    if not data and not sources:
        raise ValueError("a mapping needs at least one data proposal or user source")
    net, _ = _network_entry(root, network)
    inputs, unmapped, seen, sessions = [], [], set(), set()
    for session_id, proposal_id, record_id in data:
        if proposal_id in seen:
            raise ValueError(f"proposal {proposal_id} is listed twice (proposal ids must be unique in a mapping)")
        seen.add(proposal_id)
        entry = _approved_proposal(root, session_id, proposal_id, record_id)
        if session_id not in sessions:
            _validate_handoff(root, session_id)
            sessions.add(session_id)
        inputs.append({"session": session_id, "proposal": proposal_id, "path": entry["path"],
                       "sha256": entry["sha256"], "approval": record_id})
        for row in _table_rows(root, entry["path"], entry["kind"]):
            unmapped.append({"from": {"proposal": proposal_id, "row": row}, "reason": "TODO"})
    declared = []
    for source_id, rel in sources:
        if any(item["id"] == source_id for item in declared):
            raise ValueError(f"source id {source_id} is listed twice (source ids must be unique in a mapping)")
        declared.append(user_sources.entry(root, source_id, rel))
    mapping = {"schema_version": 1, "inputs": {"data": inputs, "sources": declared, "network": net},
               "contexts": {}, "perturbations": [], "readouts": [], "criteria": [], "unmapped": unmapped}
    _write_mapping(root, target, mapping)
    return target


def _used_nodes(old: dict) -> dict[str, list[str]]:
    """Node -> the mapping entries that fix or read it (contexts, perturbations, readouts)."""
    used: dict[str, list[str]] = {}

    def add(node, label):
        if isinstance(node, str):
            used.setdefault(node, []).append(label)
    contexts = old.get("contexts")
    for cid, items in (contexts.items() if isinstance(contexts, dict) else ()):
        for item in items if isinstance(items, list) else ():
            if isinstance(item, dict):
                add(item.get("node"), f"context {cid}")
    for pert in old.get("perturbations") if isinstance(old.get("perturbations"), list) else ():
        if isinstance(pert, dict) and isinstance(pert.get("model"), list):
            for item in pert["model"]:
                if isinstance(item, dict):
                    add(item.get("node"), f"perturbation {pert.get('id')}")
    for readout in old.get("readouts") if isinstance(old.get("readouts"), list) else ():
        if isinstance(readout, dict) and isinstance(readout.get("nodes"), list):
            for node in readout["nodes"]:
                add(node, f"readout {readout.get('phenotype')}")
    return used


def _old_rules(root: Path, network) -> dict[str, str] | None:
    """Rules of the old mapping's BNET if it is still on disk with its recorded sha256, else None."""
    try:
        path = state.artifact(root, network["bnet"])
        if sha256_file(path) != network["sha256"]:
            return None
        return bnet_rules(path)
    except (ValueError, OSError, KeyError, TypeError, UnicodeDecodeError):
        return None


def redraft(root: Path, old_rel: str, purpose: str, network) -> tuple[Path, list[str]]:
    """Copy OLD onto a new network as a new mapping; (path, notes) for the nodes to rediscuss.

    inputs.data/sources, contexts, perturbations, readouts, criteria and unmapped are
    copied unchanged; the old mapping and its approval are untouched, and the new one
    needs `check` and a fresh approval. A note is returned for each mapped node absent
    from the new BNET and each mapped node whose rule text changed.
    """
    root = Path(root)
    target = _new_target(root, purpose)
    old, _ = _load_mapping(root, old_rel)
    inputs = old.get("inputs")
    missing = [key for key in ("contexts", "perturbations", "readouts", "criteria", "unmapped") if key not in old]
    if not isinstance(inputs, dict) or "data" not in inputs or missing:
        raise ValueError(f"{old_rel} lacks {', '.join(missing) or 'inputs.data'}; nothing to redraft from")
    net, path = _network_entry(root, network)
    new_rules = bnet_rules(path)
    old_rules = _old_rules(root, inputs.get("network"))
    notes = []
    if old_rules is None:
        notes.append(f"note: the old network BNET of {old_rel} is missing or changed; rule changes were not compared")
    for node, labels in _used_nodes(old).items():
        where = "; ".join(dict.fromkeys(labels))
        if node not in new_rules:
            notes.append(f"note: node {node} is absent from the new BNET (used by {where})")
        elif old_rules is not None and node in old_rules \
                and "".join(old_rules[node].split()) != "".join(new_rules[node].split()):
            notes.append(f"note: node {node} rule changed ({old_rules[node]!r} -> {new_rules[node]!r}); "
                         f"rediscuss {where}")
    mapping = {"schema_version": 1,
               "inputs": {"data": inputs["data"], "sources": inputs.get("sources", []), "network": net},
               **{key: old[key] for key in ("contexts", "perturbations", "readouts", "criteria", "unmapped")}}
    _write_mapping(root, target, mapping)
    return target, notes


# ---------------------------------------------------------------- check

class _Checker:
    def __init__(self, root: Path):
        self.root = root
        self.errors: list[str] = []
        self.nodes: set[str] | None = None
        self.proposals: dict[str, dict] = {}  # id -> {"kind", "rows": list | None}
        self.contexts: set[str] = set()
        self.perturbations: set[str] = set()
        self.readouts: set[str] = set()
        self.refs: dict[tuple[str, str], list[str]] = {}
        self.sources = user_sources.Sources(root, self.error)

    def error(self, message: str) -> None:
        self.errors.append(message)

    # -- inputs
    def inputs(self, inputs) -> None:
        if not isinstance(inputs, dict) or set(inputs) != INPUT_KEYS:
            self.error("inputs must have exactly the keys data, sources and network")
            return
        self.network(inputs["network"])
        self.sources.declare(inputs["sources"], "inputs.sources")
        data = inputs["data"]
        if not isinstance(data, list):
            self.error("inputs.data must be a list")
            return
        if not data and inputs["sources"] == []:
            self.error("inputs.data and inputs.sources cannot both be empty")
        sessions = set()
        for n, item in enumerate(data):
            label = f"inputs.data[{n}]"
            if not isinstance(item, dict) or set(item) != {"session", "proposal", "path", "sha256", "approval"}:
                self.error(f"{label} must have exactly session, proposal, path, sha256, approval")
                continue
            pid = item["proposal"]
            if not isinstance(pid, str) or not pid:
                self.error(f"{label}: proposal must be a non-empty string")
                continue
            if pid in self.proposals:
                self.error(f"{label}: duplicate proposal id {pid} (proposal ids must be unique in a mapping)")
                continue
            self.proposals[pid] = {"kind": None, "rows": None}
            try:
                path = state.artifact(self.root, item["path"])
                if sha256_file(path) != item["sha256"]:
                    self.error(f"{label}: {item['path']} does not match its sha256")
                    continue
            except ValueError as exc:
                self.error(f"{label}: {exc}")
                continue
            try:
                entry = _approved_proposal(self.root, item["session"], pid, item["approval"])
            except (ValueError, OSError) as exc:
                self.error(f"{label}: {exc}")
                continue
            if (entry["path"], entry["sha256"]) != (item["path"], item["sha256"]):
                self.error(f"{label}: path/sha256 differ from approved proposal {pid} "
                           f"({entry['path']}, {entry['sha256'][:12]})")
                continue
            if item["session"] not in sessions:
                sessions.add(item["session"])
                try:
                    _validate_handoff(self.root, item["session"])
                except (ValueError, OSError) as exc:
                    self.error(f"{label}: {exc}")
            try:
                rows = _table_rows(self.root, item["path"], entry["kind"])
            except (ValueError, OSError, UnicodeDecodeError, csv.Error) as exc:
                self.error(f"{label}: cannot read proposal table: {exc}")
                continue
            self.proposals[pid] = {"kind": entry["kind"], "rows": rows}
            for row in rows:
                self.refs.setdefault((pid, row), [])

    def network(self, network) -> None:
        if not isinstance(network, dict) or set(network) not in (NEKO_NETWORK, STANDALONE_NETWORK):
            self.error("inputs.network must have exactly neko_session, bnet, sha256 "
                       "or exactly standalone_decision_id, bnet, sha256")
            return
        try:
            path = _network_file(self.root, network)
        except (ValueError, OSError) as exc:
            self.error(f"inputs.network: {exc}")
            return
        if sha256_file(path) != network["sha256"]:
            self.error(f"inputs.network: {network['bnet']} does not match its sha256")
            return
        try:
            self.nodes = bnet_nodes(path)
        except (ValueError, OSError, UnicodeDecodeError) as exc:
            self.error(f"inputs.network: cannot read {network['bnet']}: {exc}")

    # -- shared shapes
    def node(self, label: str, node) -> bool:
        if not isinstance(node, str) or not node:
            self.error(f"{label}: node must be a non-empty string")
            return False
        if self.nodes is not None and node not in self.nodes:
            self.error(f"{label}: node {node} is not in the network BNET")
            return False
        return True

    def node_states(self, label: str, items, allow_empty: bool) -> None:
        if not isinstance(items, list) or (not items and not allow_empty):
            self.error(f"{label} must be a {'' if allow_empty else 'non-empty '}list of {{node, state}}")
            return
        seen = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {"node", "state"}:
                self.error(f"{label}: each entry must have exactly node and state")
                continue
            if type(item["state"]) is not int or item["state"] not in (0, 1):
                self.error(f"{label}: state of {item['node']!r} must be 0 or 1")
            if self.node(label, item["node"]):
                if item["node"] in seen:
                    self.error(f"{label}: node {item['node']} is set twice")
                seen.add(item["node"])

    def source(self, label: str, value, section: str | None):
        """Validate a `from`: one reference or a non-empty list of them.

        A reference is {proposal, row} (recorded for row coverage) or {source, locator}
        (a declared user source; counted as cited).
        """
        if isinstance(value, list) and not value:
            self.error(f"{label}: from must be one reference or a non-empty list of references")
            return
        cited = set()
        for ref in value if isinstance(value, list) else [value]:
            if user_sources.is_ref(ref):
                key = json.dumps(ref, sort_keys=True, default=str)
                if key in cited:
                    self.error(f"{label}: cites source {ref['source']} at {ref['locator']!r} twice")
                    continue
                cited.add(key)
                self.sources.ref(label, ref)
            else:
                self.proposal_ref(label, ref, section)

    def proposal_ref(self, label: str, ref, section: str | None):
        if not isinstance(ref, dict) or set(ref) != {"proposal", "row"} \
                or not all(isinstance(v, str) for v in ref.values()):
            self.error(f"{label}: from must be {{proposal, row}} strings or {{source, locator}}, "
                       "or a non-empty list of them")
            return
        pid, row = ref["proposal"], ref["row"]
        info = self.proposals.get(pid)
        if info is None:
            self.error(f"{label}: proposal {pid} is not a data input of this mapping")
            return
        if info["rows"] is None:
            return  # the input itself is already reported
        if section is not None and info["kind"] != SECTION_KIND[section]:
            self.error(f"{label}: {section} map {SECTION_KIND[section]} rows, but {pid} is {info['kind']}")
        if row not in info["rows"]:
            self.error(f"{label}: proposal {pid} has no row {row!r}")
            return
        self.refs[(pid, row)].append(label)

    @staticmethod
    def safe_id(value) -> bool:
        return isinstance(value, str) and state.ID.fullmatch(value) is not None

    # -- sections
    def contexts_section(self, contexts) -> None:
        if not isinstance(contexts, dict):
            self.error("contexts must be an object of context id -> node states")
            return
        for cid, items in contexts.items():
            if not self.safe_id(cid):
                self.error(f"context id {cid!r} must be a safe identifier")
            self.contexts.add(cid)
            self.node_states(f"context {cid}", items, allow_empty=True)

    def perturbations_section(self, items) -> None:
        if not isinstance(items, list):
            self.error("perturbations must be a list")
            return
        for n, item in enumerate(items):
            if not isinstance(item, dict) or not {"id", "from", "model"} <= set(item) <= {"id", "from", "model", "note"}:
                self.error(f"perturbations[{n}] must have id, from, model and optional note")
                continue
            pid = item["id"]
            label = f"perturbation {pid}"
            if not self.safe_id(pid):
                self.error(f"perturbations[{n}]: id {pid!r} must be a safe identifier")
            elif pid in self.perturbations:
                self.error(f"duplicate perturbation id {pid}")
            else:
                self.perturbations.add(pid)
            if "note" in item and not isinstance(item["note"], str):
                self.error(f"{label}: note must be a string")
            self.source(label, item["from"], "perturbations")
            self.node_states(f"{label} model", item["model"], allow_empty=False)

    def readouts_section(self, items) -> None:
        if not isinstance(items, list):
            self.error("readouts must be a list")
            return
        phenotypes = set()
        for n, item in enumerate(items):
            if not isinstance(item, dict) or set(item) != {"phenotype", "nodes"}:
                self.error(f"readouts[{n}] must have exactly phenotype and nodes")
                continue
            if item["phenotype"] not in PHENOTYPES:
                self.error(f"readouts[{n}]: phenotype must be one of {PHENOTYPES}")
            elif item["phenotype"] in phenotypes:
                self.error(f"readouts[{n}]: phenotype {item['phenotype']} is declared twice")
            phenotypes.add(item["phenotype"])
            nodes = item["nodes"]
            if not isinstance(nodes, list) or not nodes or len(set(map(str, nodes))) != len(nodes):
                self.error(f"readouts[{n}]: nodes must be a non-empty list of distinct nodes")
                continue
            for node in nodes:
                if self.node(f"readouts[{n}]", node):
                    self.readouts.add(node)

    def scenario(self, label: str, value, perturbation_required: bool):
        if not isinstance(value, dict) or set(value) != {"context", "perturbation"}:
            self.error(f"{label} must have exactly context and perturbation")
            return None
        context, pert = value["context"], value["perturbation"]
        ok = True
        if not isinstance(context, str) or context not in self.contexts:
            self.error(f"{label}: context {context!r} is not defined under contexts")
            ok = False
        if pert is None and not perturbation_required:
            pass
        elif not isinstance(pert, str) or pert not in self.perturbations:
            self.error(f"{label}: perturbation {pert!r} is not defined under perturbations")
            ok = False
        return (context, pert) if ok else None

    def criteria_section(self, items) -> None:
        if not isinstance(items, list):
            self.error("criteria must be a list")
            return
        seen = set()
        for n, item in enumerate(items):
            if not isinstance(item, dict):
                self.error(f"criteria[{n}] must be an object")
                continue
            cid = item.get("criterion_id")
            label = f"criterion {cid}"
            if not self.safe_id(cid):
                self.error(f"criteria[{n}]: criterion_id {cid!r} must be a safe identifier")
            elif cid in seen:
                self.error(f"duplicate criterion id {cid}")
            else:
                seen.add(cid)
            method = item.get("method")
            if method == "boolean_structure":
                self.error(f"{label}: boolean_structure is not allowed in a data mapping (it checks network "
                           "structure, not data-driven responses); declare it directly in VALIDATION_CRITERIA.yaml")
                continue
            if method not in METHODS:
                self.error(f"{label}: method {method!r} is not supported by evaluate.py ({', '.join(METHODS)})")
                continue
            base = {"criterion_id", "from", "method", "options"} | METHOD_KEYS[method]
            if not base <= set(item) <= base | {"note"}:
                self.error(f"{label}: a {method} criterion has exactly {', '.join(sorted(base))} and optional note")
                continue
            self.source(label, item["from"], "criteria")
            if not isinstance(item["options"], dict):
                self.error(f"{label}: options must be an object")
                continue
            getattr(self, f"criterion_{method}")(label, item)

    def observed(self, label: str, nodes) -> list[str]:
        """Nodes a criterion reads from trajectories must be declared readouts."""
        names = [n for n in nodes if isinstance(n, str)]
        for node in names:
            if node not in self.readouts:
                self.error(f"{label}: readout node {node} is not declared under readouts")
        return names

    def synthetic(self, label: str, method: str, run, names, points: int = 1) -> None:
        series = [0.5] * points
        trajectory = {node: series for node in sorted(self.readouts | set(names))}
        try:
            run(trajectory, series)
        except (ValueError, KeyError, TypeError) as exc:
            self.error(f"{label}: invalid {method} options: {exc}")

    def criterion_scenario_contrast(self, label: str, item: dict) -> None:
        test = self.scenario(f"{label} test", item["test"], perturbation_required=True)
        reference = self.scenario(f"{label} reference", item["reference"], perturbation_required=True)
        if test and reference and test[0] == reference[0]:
            self.error(f"{label}: test and reference context must differ (their control runs would coincide)")
        options = item["options"]
        readouts = options.get("readouts")
        names = self.observed(label, readouts) if isinstance(readouts, list) else []
        points = options.get("tail_points")
        points = points if type(points) is int and 1 <= points <= SYNTHETIC_MAX_POINTS else 1
        self.synthetic(label, "scenario_contrast",
                       lambda traj, _s: contrast([traj] * 4, options), names, points)

    def trajectory_scenarios(self, label: str, item: dict) -> None:
        scenarios = item["scenarios"]
        if not isinstance(scenarios, list) or not scenarios:
            self.error(f"{label}: scenarios must be a non-empty list of {{context, perturbation}}")
            return
        seen = set()
        for n, value in enumerate(scenarios):
            key = self.scenario(f"{label} scenarios[{n}]", value, perturbation_required=False)
            if key is not None:
                if key in seen:
                    self.error(f"{label}: scenario {key} is listed twice")
                seen.add(key)

    def criterion_ordered_peaks(self, label: str, item: dict) -> None:
        self.trajectory_scenarios(label, item)
        options = item["options"]
        nodes = options.get("nodes")
        names = self.observed(label, nodes) if isinstance(nodes, list) else []
        self.synthetic(label, "ordered_peaks",
                       lambda traj, s: ordered_peaks(list(range(len(s))), traj, options), names, 3)

    def criterion_canonical_cycles(self, label: str, item: dict) -> None:
        self.trajectory_scenarios(label, item)
        options = item["options"]
        order = options.get("activation_order")
        nodes = [*(order if isinstance(order, list) else []), options.get("onset_node"), options.get("reset_node")]
        names = self.observed(label, nodes)
        self.synthetic(label, "canonical_cycles",
                       lambda traj, s: classify_cycles(list(range(len(s))), traj, options), names, 3)

    def unmapped_section(self, items) -> None:
        if not isinstance(items, list):
            self.error("unmapped must be a list")
            return
        for n, item in enumerate(items):
            if not isinstance(item, dict) or set(item) != {"from", "reason"}:
                self.error(f"unmapped[{n}] must have exactly from and reason")
                continue
            ref = item["from"]
            label = f"unmapped[{n}]" + (f" ({ref.get('proposal')} row {ref.get('row')})"
                                        if isinstance(ref, dict) and "proposal" in ref else "")
            reason = item["reason"]
            if not isinstance(reason, str) or not reason.strip() or reason.strip().upper() == "TODO":
                self.error(f"{label}: reason must be a non-empty explanation, not empty or TODO")
            self.source(label, ref, None)

    def coverage(self) -> None:
        for (pid, row), labels in self.refs.items():
            if not labels:
                self.error(f"{pid} row {row} is neither mapped nor listed in unmapped")
            elif len(labels) > 1:
                self.error(f"{pid} row {row} is referenced {len(labels)} times "
                           f"({'; '.join(labels)}); map it once or list it once in unmapped")


def _load_mapping(root: Path, mapping_rel: str) -> tuple[dict, str]:
    """Read the mapping once: its parsed object and the sha256 of exactly those bytes."""
    raw = _mapping_path(root, mapping_rel).read_bytes()
    data = strict_json(raw)
    if not isinstance(data, dict):
        raise ValueError("mapping must be a JSON object")
    return data, hashlib.sha256(raw).hexdigest()


def overlaps(data: dict) -> list[tuple[str, str, str]]:
    """(perturbation id, context id, node) wherever both fix a node: the perturbation overrides the context."""
    found = []
    contexts, perturbations = data.get("contexts"), data.get("perturbations")
    if not isinstance(contexts, dict) or not isinstance(perturbations, list):
        return found
    for item in perturbations:
        if not isinstance(item, dict) or not isinstance(item.get("model"), list):
            continue
        fixed = [e["node"] for e in item["model"] if isinstance(e, dict) and "node" in e]
        for cid, states in contexts.items():
            if not isinstance(states, list):
                continue
            for entry in states:
                if isinstance(entry, dict) and entry.get("node") in fixed:
                    found.append((item.get("id"), cid, entry["node"]))
    return found


def readout_nodes(data) -> list[str]:
    """Nodes declared under readouts, in file order without repeats; criteria read only these nodes."""
    found: list[str] = []
    items = data.get("readouts") if isinstance(data, dict) else None
    for item in items if isinstance(items, list) else ():
        nodes = item.get("nodes") if isinstance(item, dict) else None
        for node in nodes if isinstance(nodes, list) else ():
            if isinstance(node, str) and node not in found:
                found.append(node)
    return found


def check(root: Path, mapping_rel: str, stage_gate=None) -> list[str]:
    """Every problem with the mapping, one message each; [] when it is valid.

    With `stage_gate` (the STAGE_GATE JSON object, with or without its `STAGE_GATE `
    prefix, that line 1 of the MaBoSS brief will carry), the dispatch gate's network
    binding is checked too, so a mapping made stale by a re-export is reported, and so is
    every readout node that is not among the STAGE_GATE `outputs`.
    """
    root = Path(root)
    try:
        data, _ = _load_mapping(root, mapping_rel)
    except (ValueError, OSError, UnicodeDecodeError) as exc:
        return [f"{mapping_rel}: {exc}"]
    errors = _check_data(root, data)
    if stage_gate is not None:
        errors += network_binding_errors(root, data, stage_gate)
    return errors


def _stage_gate_line(stage_gate) -> str:
    if isinstance(stage_gate, dict):
        return "STAGE_GATE " + json.dumps(stage_gate)
    if not isinstance(stage_gate, str):
        raise ValueError("STAGE_GATE must be the JSON object of the brief's line 1")
    text = stage_gate.strip()
    return text if text.startswith("STAGE_GATE ") else "STAGE_GATE " + text


def network_binding_errors(root: Path, data: dict, stage_gate) -> list[str]:
    """The dispatch gate's checks of a mapping against a STAGE_GATE, as error lines ([] when they pass).

    The binding of inputs.network to the STAGE_GATE anchor, then the readout nodes against
    the STAGE_GATE outputs.
    """
    from scripts import gate
    inputs = data.get("inputs") if isinstance(data, dict) else None
    try:
        line = _stage_gate_line(stage_gate)
        gate.check_mapping_network(Path(root), inputs.get("network") if isinstance(inputs, dict) else None, line)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return [f"STAGE_GATE binding: {exc}"]
    try:
        gate.check_mapping_outputs(data, line)
    except (ValueError, TypeError) as exc:
        return [f"STAGE_GATE outputs: {exc}"]
    return []


def load_and_check(root: Path, mapping_rel: str) -> tuple[dict, str, list[str]]:
    """Read the mapping once and check exactly those bytes: (data, sha256, errors).

    Unlike `check`, an unreadable or misplaced mapping raises ValueError/OSError
    rather than being reported as an error line.
    """
    root = Path(root)
    data, digest = _load_mapping(root, mapping_rel)
    return data, digest, _check_data(root, data)


def validate_data_handoff(root: Path, session_id: str) -> None:
    """Raise ValueError unless the data session's handoff.json validates now."""
    _validate_handoff(Path(root), session_id)


def _check_data(root: Path, data: dict) -> list[str]:
    checker = _Checker(root)
    if set(data) != set(KEYS):
        checker.error(f"mapping keys must be exactly {', '.join(KEYS)}")
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        checker.error("schema_version must be the integer 1")
    checker.inputs(data.get("inputs"))
    checker.contexts_section(data.get("contexts"))
    checker.perturbations_section(data.get("perturbations"))
    checker.readouts_section(data.get("readouts"))
    checker.criteria_section(data.get("criteria"))
    checker.unmapped_section(data.get("unmapped"))
    checker.coverage()
    checker.sources.uncited()
    return checker.errors


# ---------------------------------------------------------------- criteria

def _runs(root: Path, runs_rel: str, data: dict) -> dict:
    parts = _parts(runs_rel)
    if parts[:2] != ORCHESTRATOR or len(parts) < 4:
        raise ValueError(f"runs file must be under runs/orchestrator/<purpose>/, not {runs_rel!r}")
    runs = load_json_yaml(state.artifact(root, runs_rel))
    if set(runs) != {"runs"} or not isinstance(runs["runs"], list):
        raise ValueError('runs file must be {"runs": [{"context", "perturbation", "trajectory"}, ...]}')
    contexts, perturbations = set(data["contexts"]), {p["id"] for p in data["perturbations"]}
    found, used, errors = {}, {}, []
    for n, run in enumerate(runs["runs"]):
        if not isinstance(run, dict) or set(run) != {"context", "perturbation", "trajectory"}:
            errors.append(f"runs[{n}] must have exactly context, perturbation, trajectory")
            continue
        if not isinstance(run["context"], str) or not isinstance(run["perturbation"], (str, type(None))):
            errors.append(f"runs[{n}]: context must be a string and perturbation a string or null")
            continue
        key = (run["context"], run["perturbation"])
        if run["context"] not in contexts or (key[1] is not None and key[1] not in perturbations):
            errors.append(f"runs[{n}]: scenario {key} is not defined by the mapping")
        if key in found:
            errors.append(f"runs[{n}]: scenario {key} has more than one run")
        trajectory = run["trajectory"]
        if _parts(trajectory)[:2] != TRAJECTORIES or len(_parts(trajectory)) < 4:
            errors.append(f"runs[{n}]: trajectory must be a saved run artifact under runs/boolean-dynamics-modeler/, "
                          f"not {trajectory!r}")
            continue
        try:
            state.artifact(root, trajectory)
        except ValueError as exc:
            errors.append(f"runs[{n}]: {exc}")
            continue
        if trajectory in used:
            errors.append(f"runs[{n}]: scenarios {used[trajectory]} and {key} use the same trajectory {trajectory}; "
                          "each scenario needs its own run")
            continue
        used[trajectory] = key
        found[key] = trajectory
    if errors:
        raise ValueError("; ".join(errors))
    return found


def criteria(root: Path, mapping_rel: str, runs_rel: str, approval_id: str) -> dict:
    """VALIDATION_CRITERIA entries and validation-declare inputs for the mapping's criteria.

    The mapping must carry a researcher `data_mapping` approval (`approval_id`) of exactly
    its current bytes; nothing is emitted for an unapproved or since-edited mapping.
    """
    root = Path(root)
    data, digest = _load_mapping(root, mapping_rel)  # check and build from the same bytes
    approvals.require_mapping_approval(root, approval_id, mapping_rel, digest)
    errors = _check_data(root, data)
    if errors:
        raise ValueError(f"{mapping_rel} fails check: " + "; ".join(errors))
    runs = _runs(root, runs_rel, data)
    declared = {item["id"]: item for item in data["inputs"]["sources"]}
    missing, entries, declarations = [], [], []

    def run(context, perturbation):
        if (context, perturbation) not in runs:
            missing.append(f"({context}, {perturbation if perturbation is not None else 'no perturbation'})")
            return None
        return runs[(context, perturbation)]

    for item in data["criteria"]:
        method = item["method"]
        if method == "scenario_contrast":
            test, ref = item["test"], item["reference"]
            # Fixed role order: control = the context without the perturbation.
            inputs = [run(test["context"], None), run(test["context"], test["perturbation"]),
                      run(ref["context"], None), run(ref["context"], ref["perturbation"])]
        else:
            inputs = [run(s["context"], s["perturbation"]) for s in item["scenarios"]]
        entries.append({"criterion_id": item["criterion_id"], "method": method, "inputs": inputs,
                        "options": item["options"]})
        refs = item["from"] if isinstance(item["from"], list) else [item["from"]]
        cites = [f"data {ref['proposal']} row {ref['row']}" if "proposal" in ref else
                 f"source {declared[ref['source']]['path']} sha256 {declared[ref['source']]['sha256'][:12]} "
                 f"at {ref['locator']}" for ref in refs]
        declarations.append({"Criterion": item["criterion_id"], "Method": method,
                             "Required evidence": f"{method} over {', '.join(map(str, inputs))}; mapping "
                                                  f"{mapping_rel} sha256 {digest} (approval {approval_id}); "
                                                  + "; ".join(cites)})
    if missing:
        raise ValueError("no run for scenario " + ", ".join(dict.fromkeys(missing)))
    return {"criteria": entries, "declarations": declarations}


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))  # mkstemp creates 0600; keep the file's mode
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def merge_into(root: Path, target_rel: str, entries: list[dict]) -> Path:
    """Append criteria entries to a VALIDATION_CRITERIA file; refuse duplicate criterion ids."""
    root = Path(root)
    path = state.artifact(root, target_rel)
    config = load_json_yaml(path)
    if set(config) != {"schema_version", "criteria"} or type(config["schema_version"]) is not int \
            or config["schema_version"] != 1 or not isinstance(config["criteria"], list):
        raise ValueError(f"{target_rel} must be {{\"schema_version\": 1, \"criteria\": [...]}}")
    existing = [c.get("criterion_id") for c in config["criteria"] if isinstance(c, dict)]
    new = [e["criterion_id"] for e in entries]
    dupes = sorted({i for i in new if i in existing or new.count(i) > 1})
    if dupes:
        raise ValueError(f"{target_rel} already declares criterion ids {', '.join(dupes)}")
    config["criteria"] = config["criteria"] + list(entries)
    _atomic_write(path, json.dumps(config, indent=2) + "\n")
    return path


# ---------------------------------------------------------------- CLI

def _split(value: str, n: int, form: str) -> list[str]:
    parts = value.split(":", n - 1)
    if len(parts) != n or not all(parts):
        raise ValueError(f"expected {form}, got {value!r}")
    return parts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("draft")
    d.add_argument("--purpose", required=True)
    d.add_argument("--data", nargs="+", default=[], metavar="SESSION:PROPOSAL:APPROVAL")
    d.add_argument("--source", action="append", default=[], metavar="ID:PATH",
                   help="a researcher-provided file under inputs/ (repeatable); its sha256 is computed")
    d.add_argument("--from", dest="from_mapping", metavar="OLD_MAPPING",
                   help="copy OLD_MAPPING onto the given network (after a re-export); excludes --data/--source")
    network = d.add_mutually_exclusive_group(required=True)
    network.add_argument("--network", metavar="NEKO_SESSION:BNET")
    network.add_argument("--standalone-network", metavar="STANDALONE_DECISION_ID:BNET")
    c = sub.add_parser("check")
    c.add_argument("mapping")
    c.add_argument("--stage-gate", metavar="JSON",
                   help="the STAGE_GATE JSON of the MaBoSS brief: also check the gate's network binding")
    g = sub.add_parser("criteria")
    g.add_argument("mapping")
    g.add_argument("--runs", required=True)
    g.add_argument("--approval", required=True, metavar="RECORD_ID",
                   help="id of the data_mapping stage_approval of exactly this mapping")
    g.add_argument("--out")
    g.add_argument("--merge-into")
    args = parser.parse_args(argv)
    root = project_root().resolve()
    try:
        if args.command == "draft":
            if args.network:
                network = tuple(_split(args.network, 2, "NEKO_SESSION:BNET"))
            else:
                decision, bnet = _split(args.standalone_network, 2, "STANDALONE_DECISION_ID:BNET")
                network = {"standalone_decision_id": decision, "bnet": bnet}
            if args.from_mapping:
                if args.data or args.source:
                    raise ValueError("draft --from copies the old mapping's inputs; do not combine it with "
                                     "--data or --source")
                path, notes = redraft(root, args.from_mapping, args.purpose, network)
                for note in notes:
                    print(note)
            else:
                data = [tuple(_split(v, 3, "SESSION:PROPOSAL:APPROVAL")) for v in args.data]
                sources = [tuple(_split(v, 2, "ID:PATH")) for v in args.source]
                path = draft(root, args.purpose, data, network, sources)
            print(f"mapping drafted: {path.relative_to(root).as_posix()} sha256={sha256_file(path)}")
            return 0
        if args.command == "check":
            errors = check(root, args.mapping, args.stage_gate)
            for error in errors:
                print(error, file=sys.stderr)
            if errors:
                return 1
            for pid, cid, node in overlaps(_load_mapping(root, args.mapping)[0]):
                print(f"note: perturbation {pid} overrides context {cid} on {node}")
            print(f"mapping check passed: {args.mapping}")
            return 0
        result = criteria(root, args.mapping, args.runs, args.approval)
        text = json.dumps(result, indent=2) + "\n"
        if args.out:
            parts = _parts(args.out)
            if not parts or ".." in parts or Path(args.out).is_absolute():
                raise ValueError("--out must be a repository-relative path")
            if (root / args.out).exists() or (root / args.out).is_symlink():
                raise ValueError(f"{args.out} exists; refusing to overwrite")
        if args.out:
            try:
                _write_new(root, root / args.out, text)
            except FileExistsError as exc:
                raise ValueError(f"{args.out} exists; refusing to overwrite") from exc
        if args.merge_into:  # after --out, so a failed --out write leaves the YAML untouched
            merge_into(root, args.merge_into, result["criteria"])
        print(text, end="")
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Dependency-free checks for NeKo history companions and readout isolation.

Backend 2.5.0 binds a ``curation_file`` companion to the exact model artifact
reference, including its original absolute path. Repository captures relocate
payload paths, so these checks compare every other artifact identity field and
the pinned companion bytes. They never import modelling libraries, read
historical paths, or approve a model.
"""
from __future__ import annotations

import json
import re

MAX_HISTORY_BYTES = 16 * 1024 * 1024
BOUND_FIELDS = ("session_id", "name", "suffix", "media_type", "size_bytes", "server", "role", "sha256")
CURATION_PATH_KEYS = {"neko-to-maboss": ("bnet_file", "curation_file"),
                      "neko-to-biomass": ("network_file", "curation_file")}
NAME = r"[A-Za-z][A-Za-z_0-9]*"


def check_binding(raw: bytes, model: dict, session: str, state_id) -> dict:
    """Require companion bytes to describe this model artifact and saved state."""
    if len(raw) > MAX_HISTORY_BYTES:
        raise ValueError("NeKo history companion exceeds 16 MiB")
    try:
        data = json.loads(raw)
    except ValueError:
        raise ValueError("NeKo history companion is not valid JSON") from None
    if not isinstance(data, dict) or (data.get("format"), data.get("schema_version")) != ("neko-export", 1):
        raise ValueError("expected a neko-export v1 history companion")
    mcp, export, history = data.get("mcp"), data.get("export"), data.get("history")
    if not all(isinstance(value, dict) for value in (mcp, export, history)):
        raise ValueError("history companion requires mcp, export and history objects")
    if type(state_id) is not int or state_id < 0:
        raise ValueError("curation-bearing handoff requires an integer history_state_id")
    if mcp.get("session_id") != session or type(mcp.get("state_id")) is not int or mcp["state_id"] != state_id:
        raise ValueError("history companion session/state differs from the handoff")
    if ((history.get("format"), history.get("schema_version")) != ("neko-history", 1)
            or history.get("current_state_id") != state_id
            or history.get("database_name") != mcp.get("database_name")):
        raise ValueError("history companion state or database identity mismatch")
    if history.get("working_state_matches_current") is not True:
        raise ValueError("history companion does not match a saved working state")
    artifact = export.get("artifact")
    if not isinstance(artifact, dict) or any(artifact.get(field) != model.get(field) for field in BOUND_FIELDS):
        raise ValueError("NeKo history companion is not bound to this model artifact")
    projection = export.get("library_projection")
    if projection is not None and (not isinstance(projection, dict)
            or projection.get("sha256") != model.get("sha256")
            or projection.get("file") != model.get("name")
            or projection.get("state_id") != state_id):
        raise ValueError("history companion projection differs from the model artifact/state")
    return data


def relocation_of(original: dict, imported: dict, path_keys) -> bool:
    """True when imported differs from original only in the named payload paths."""
    if not isinstance(original, dict) or not isinstance(imported, dict):
        return False
    expected = json.loads(json.dumps(original))
    for key in path_keys:
        if isinstance(expected.get(key), dict) and isinstance(imported.get(key), dict):
            expected[key]["path"] = imported[key].get("path")
    return expected == imported


def _bnd_bodies(text: str) -> dict[str, str]:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = "\n".join(line.split("//", 1)[0].split("#", 1)[0] for line in text.splitlines())
    return dict(re.findall(r"(?i:node)\s+(" + NAME + r")\s*\{([^{}]*)\}", text))


def check_readout_isolation(bnd_text: str, nodes: list[str], readouts: dict) -> None:
    """Readouts keep their declared rule and never regulate the biological core."""
    if not readouts:
        return
    if not isinstance(readouts, dict) or not set(readouts) <= set(nodes):
        raise ValueError("readout definitions must name nodes in the exported model")
    bodies = _bnd_bodies(bnd_text)
    if set(bodies) != set(nodes):
        raise ValueError("cannot verify readout isolation in these BND declarations")
    for name, definition in readouts.items():
        rule = definition.get("rule") if isinstance(definition, dict) else None
        if not isinstance(definition, dict) or definition.get("origin") != "readout" or not isinstance(rule, str):
            raise ValueError("readout definitions require origin=readout and an exact rule")
        logic = re.search(r"\blogic\s*=\s*([^;]+);", bodies[name])
        if logic is None or re.sub(r"\s", "", logic[1]) != re.sub(r"\s", "", rule):
            raise ValueError("readout definition differs from BND logic: " + name)
    for name in set(nodes) - set(readouts):
        references = set(re.findall(r"(?<![$@A-Za-z_0-9])" + NAME, bodies[name]))
        if references & set(readouts):
            raise ValueError("readout feeds back into core BND node: " + name)


def check_parent_scope(parent_nodes, parent_outputs, nodes, outputs, readouts) -> None:
    """Only declared readouts may extend the NeKo core; outputs follow PhysiCell import."""
    readouts = set(readouts or {})
    if readouts & set(parent_nodes):
        raise ValueError("readout provenance cannot reclassify NeKo core nodes")
    if set(parent_nodes) | readouts != set(nodes):
        raise ValueError("parent and current stage network nodes disagree")
    if set(parent_outputs) != set(outputs) - readouts:
        raise ValueError("parent and current stage output selections disagree")

"""Verify relocated NeKo history companions with the backend's own parser.

Backend 2.5.0 binds ``curation_file`` to the model artifact's original absolute
path, so ``verify_handoff_manifest`` rejects any relocated copy. Captures verify
the live original first, then check that each relocated reference differs only
in its path and that the copied companion bytes parse against the original
binding. Downstream specialists must import the original backend manifest.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

CURATION_NOTE = ('Backend 2.5.0 binds curation_file to the original model path; import the '
                 'original backend manifest. This copy is the immutable gate/approval record.')


def same_except_path(original, relocated) -> bool:
    return original.model_dump(exclude={'path'}) == relocated.model_dump(exclude={'path'})


def verify_relocated(original, relocated, model_field: str, curation_bytes: bytes) -> None:
    """Check a relocated manifest whose model/curation payloads were copied.

    ``original`` was already verified live; ``relocated`` points at the copies.
    """
    from mcp_biomodelling_servers.handoff import verify_handoff_artifact
    from mcp_biomodelling_servers.neko_provenance import parse_neko_provenance
    model, copied = getattr(original, model_field), getattr(relocated, model_field)
    if original.curation_file is None or relocated.curation_file is None:
        raise ValueError('curation-bearing handoff requires curation_file')
    if not same_except_path(model, copied) or not same_except_path(original.curation_file, relocated.curation_file):
        raise ValueError('relocation changed more than artifact paths')
    verify_handoff_artifact(copied)
    path = verify_handoff_artifact(relocated.curation_file)
    if path.read_bytes() != curation_bytes:
        raise ValueError('captured curation companion changed during validation')
    evidence = parse_neko_provenance(curation_bytes, relocated.curation_file, model)
    if evidence.mcp.state_id != relocated.history_state_id:
        raise ValueError('curation state differs from the handoff state')


def copy_curation(source: Path, reference: dict, reserved: set[str]):
    """Return (name, bytes, path) for a curation companion inside its session directory."""
    from scripts.codex.ode_artifacts import safe_file
    file = safe_file(source, Path(reference['path']).relative_to(source).as_posix())
    content = file.read_bytes()
    if hashlib.sha256(content).hexdigest() != reference.get('sha256') or len(content) != reference.get('size_bytes'):
        raise ValueError('curation companion hash or byte count mismatch')
    if file.name in reserved:
        raise ValueError('curation companion basename conflicts with capture contents')
    return file.name, content, file

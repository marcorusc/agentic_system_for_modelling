#!/usr/bin/env python3
"""Capture an existing approved NeKo Boolean export; no export or model execution."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.codex.artifact_capture import reject_symlinks, staged_capture
from scripts.codex.launcher_config import validate_session_id
from scripts.codex.ode_artifacts import digest, read_json, safe_file


def record_neko(project: Path, server_root: Path, manifest_path: Path, capture_id: str) -> dict:
    # Pure backend contract readers only; an absent backend fails explicitly.
    from mcp_biomodelling_servers.handoff import NeKoToMaBoSSHandoffManifest, bnet_node_names, verify_handoff_manifest
    project = project.resolve(strict=True)
    validate_session_id(capture_id)
    artifacts = server_root.absolute() / 'artifacts'
    reject_symlinks(artifacts)
    original = safe_file(artifacts, manifest_path.absolute().relative_to(artifacts).as_posix())
    raw = read_json(original)
    parsed = NeKoToMaBoSSHandoffManifest.model_validate(raw)
    session = validate_session_id(parsed.source.session_id)
    source = artifacts / session
    original = safe_file(source, original.relative_to(source).as_posix())
    network = safe_file(source, Path(parsed.bnet_file.path).relative_to(source).as_posix())
    basename = network.name
    if basename in {'original.handoff.json', 'import.handoff.json', 'relocation.json'}:
        raise ValueError('BNET basename conflicts with capture metadata')
    verify_handoff_manifest(parsed)
    if bnet_node_names(network) != parsed.network.nodes:
        raise ValueError('BNET target order disagrees with manifest nodes')
    original_bytes, network_bytes = original.read_bytes(), network.read_bytes()
    if json.loads(original_bytes) != raw or hashlib.sha256(network_bytes).hexdigest() != parsed.bnet_file.sha256:
        raise ValueError('source artifacts changed during validation')
    target = project / 'runs/network-curator' / session / 'boolean-handoffs' / capture_id
    imported = copy.deepcopy(raw)
    imported['bnet_file']['path'] = str(target / basename)
    with staged_capture(project, target) as stage:
        (stage / 'original.handoff.json').write_bytes(original_bytes)
        (stage / basename).write_bytes(network_bytes)
        (stage / 'import.handoff.json').write_text(json.dumps(imported, indent=2) + '\n', encoding='utf-8')
        staged = NeKoToMaBoSSHandoffManifest.model_validate(imported)
        staged.bnet_file.path = str(stage / basename)
        verify_handoff_manifest(staged)
        if bnet_node_names(stage / basename) != staged.network.nodes:
            raise ValueError('captured BNET target order mismatch')
        (stage / 'relocation.json').write_text(json.dumps({
            'original_manifest_sha256': hashlib.sha256(original_bytes).hexdigest(),
            'import_manifest_sha256': digest(stage / 'import.handoff.json'),
            'bnet_sha256': hashlib.sha256(network_bytes).hexdigest(),
            'source_manifest_path': str(original), 'source_bnet_path': str(network),
        }, indent=2) + '\n', encoding='utf-8')
        result = {'upstream_manifest': (target / 'import.handoff.json').relative_to(project).as_posix(),
                  'artifacts': [{'path': (target / p.name).relative_to(project).as_posix(), 'sha256': digest(p)}
                                for p in sorted(stage.iterdir())]}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--capture-id', required=True)
    args = parser.parse_args()
    try:
        result = record_neko(Path(__file__).resolve().parents[2], args.server_root, args.manifest, args.capture_id)
    except (ImportError, OSError, ValueError, KeyError, TypeError) as error:
        print(f'NeKo Boolean capture failed: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

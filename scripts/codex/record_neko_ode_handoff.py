#!/usr/bin/env python3
"""Preserve an exported NeKo ODE handoff and create a separately tracked import copy."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.codex.launcher_config import validate_session_id
from scripts.codex.ode_artifacts import digest, read_json, safe_file


def record_neko(project: Path, server_root: Path, manifest_path: Path, capture_id: str) -> dict:
    project = project.resolve(strict=True)
    manifest = read_json(manifest_path)
    session = validate_session_id(manifest['source']['session_id'])
    validate_session_id(capture_id)
    if manifest.get('handoff_type') != 'neko-to-biomass' or manifest['source'].get('server') != 'NeKo':
        raise ValueError('expected a NeKo-to-BioMASS export')
    source = server_root.absolute()/'artifacts'/session
    for component in (source, *source.parents):
        if component.is_symlink():
            raise ValueError('NeKo source root contains a symlink')
    original = safe_file(source, manifest_path.absolute().relative_to(source).as_posix())
    artifact = manifest['network_file']
    if artifact.get('server') != 'NeKo' or artifact.get('session_id') != session or artifact.get('role') != 'neko_ode_network':
        raise ValueError('NeKo network ownership mismatch')
    network = safe_file(source, Path(artifact['path']).relative_to(source).as_posix())
    if digest(network) != artifact.get('sha256'):
        raise ValueError('NeKo network hash mismatch')
    network_bytes, original_bytes = network.read_bytes(), original.read_bytes()
    # Validate before creating the destination, and recheck the copied bytes.
    import hashlib
    if hashlib.sha256(network_bytes).hexdigest() != artifact['sha256']:
        raise ValueError('NeKo network changed while copying')
    if json.loads(original_bytes) != manifest:
        raise ValueError('NeKo manifest changed while copying')
    target = project/'runs/network-curator'/session/'ode-handoffs'/capture_id
    for p in (target, *target.parents):
        if p == project: break
        if p.is_symlink(): raise ValueError('NeKo destination contains a symlink')
    target.mkdir(parents=True, exist_ok=False)
    (target/'original.handoff.json').write_bytes(original_bytes)
    (target/'network.json').write_bytes(network_bytes)
    imported = copy.deepcopy(manifest)
    imported['network_file']['path'] = str(target/'network.json')
    (target/'import.handoff.json').write_text(json.dumps(imported, indent=2)+'\n')
    provenance = {'original_manifest_sha256': digest(target/'original.handoff.json'),
                  'import_manifest_sha256': digest(target/'import.handoff.json'),
                  'network_sha256': artifact['sha256'], 'source_manifest_path': str(original),
                  'source_network_path': str(network)}
    (target/'relocation.json').write_text(json.dumps(provenance, indent=2)+'\n')
    return {'upstream_manifest': (target/'import.handoff.json').relative_to(project).as_posix(),
            'artifacts': [{'path': p.relative_to(project).as_posix(), 'sha256': digest(p)} for p in target.iterdir()]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--capture-id', required=True)
    a = parser.parse_args()
    try:
        result = record_neko(Path(__file__).resolve().parents[2], a.server_root, a.manifest, a.capture_id)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'NeKo ODE handoff recording failed: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__': raise SystemExit(main())

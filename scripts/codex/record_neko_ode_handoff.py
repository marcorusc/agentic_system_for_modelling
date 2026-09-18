#!/usr/bin/env python3
"""Preserve an exported NeKo ODE handoff and create a separately tracked import copy."""
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
from scripts.codex.ode_artifacts import SHA, digest, read_json, safe_file


def record_neko(project: Path, server_root: Path, manifest_path: Path, capture_id: str) -> dict:
    project = project.resolve(strict=True)
    validate_session_id(capture_id)
    artifacts = server_root.absolute() / 'artifacts'
    reject_symlinks(artifacts)
    # Validate the location before reading even the session identifier.
    original = safe_file(artifacts, manifest_path.absolute().relative_to(artifacts).as_posix())
    manifest = read_json(original)
    owner = manifest.get('source')
    if not isinstance(owner, dict) or owner.get('server') != 'NeKo' or manifest.get('handoff_type') != 'neko-to-biomass':
        raise ValueError('expected a NeKo-to-BioMASS export')
    session = validate_session_id(owner['session_id'])
    source = artifacts / session
    original = safe_file(source, original.relative_to(source).as_posix())
    artifact = manifest.get('network_file')
    if not isinstance(artifact, dict) or artifact.get('server') != 'NeKo' or artifact.get('session_id') != session or artifact.get('role') != 'neko_ode_network':
        raise ValueError('NeKo network ownership mismatch')
    network = safe_file(source, Path(artifact['path']).relative_to(source).as_posix())
    expected = artifact.get('sha256')
    if not isinstance(expected, str) or not SHA.fullmatch(expected) or digest(network) != expected:
        raise ValueError('NeKo network hash mismatch')
    network_bytes, original_bytes = network.read_bytes(), original.read_bytes()
    if hashlib.sha256(network_bytes).hexdigest() != expected:
        raise ValueError('NeKo network changed while copying')
    if json.loads(original_bytes) != manifest:
        raise ValueError('NeKo manifest changed while copying')
    target = project / 'runs/network-curator' / session / 'ode-handoffs' / capture_id
    with staged_capture(project, target) as stage:
        (stage / 'original.handoff.json').write_bytes(original_bytes)
        (stage / 'network.json').write_bytes(network_bytes)
        if digest(stage / 'network.json') != expected:
            raise ValueError('NeKo network changed while recording')
        if (stage / 'original.handoff.json').read_bytes() != original_bytes:
            raise ValueError('NeKo manifest changed while recording')
        imported = copy.deepcopy(manifest)
        imported['network_file']['path'] = str(target / 'network.json')
        (stage / 'import.handoff.json').write_text(json.dumps(imported, indent=2) + '\n', encoding='utf-8')
        provenance = {'original_manifest_sha256': digest(stage / 'original.handoff.json'),
                      'import_manifest_sha256': digest(stage / 'import.handoff.json'),
                      'network_sha256': expected, 'source_manifest_path': str(original),
                      'source_network_path': str(network)}
        (stage / 'relocation.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
        result = {
            'upstream_manifest': (target / 'import.handoff.json').relative_to(project).as_posix(),
            'artifacts': [
                {'path': (target / path.name).relative_to(project).as_posix(), 'sha256': digest(path)}
                for path in sorted(stage.iterdir())
            ],
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--capture-id', required=True)
    arguments = parser.parse_args()
    try:
        result = record_neko(Path(__file__).resolve().parents[2], arguments.server_root,
                             arguments.manifest, arguments.capture_id)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'NeKo ODE handoff recording failed: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

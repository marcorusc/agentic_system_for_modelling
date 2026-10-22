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
from scripts.capture.artifact_capture import boolean_artifact_root, staged_capture
from scripts.codex.launcher_config import validate_session_id
from scripts.codex.ode_artifacts import SHA, digest, read_json, safe_file
from scripts.capture.neko_curation import CURATION_NOTE, copy_curation
from scripts.curation_contract import check_binding


def record_neko(project: Path, server_root: Path | None, manifest_path: Path, capture_id: str, *,
                resource_metadata_file: Path | None = None, artifact_root: Path | None = None) -> dict:
    project = project.resolve(strict=True)
    validate_session_id(capture_id)
    # Backend 2.5.0 defaults to a per-server cache root rather than <server>/artifacts.
    artifacts = boolean_artifact_root(server_root, artifact_root)
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
    network_name = network.name
    if network_name in {'original.handoff.json', 'import.handoff.json', 'relocation.json', 'resource.json', 'resource.original.json'}:
        raise ValueError('NeKo network basename conflicts with capture metadata')
    expected = artifact.get('sha256')
    if not isinstance(expected, str) or not SHA.fullmatch(expected) or digest(network) != expected:
        raise ValueError('NeKo network hash mismatch')
    version = manifest.get('schema_version')
    reference = manifest.get('curation_file')
    # A missing version is the pre-versioned legacy form; it cannot carry curation.
    if version not in {None, '1.0', '2.0'} or (version == '2.0') != (reference is not None):
        raise ValueError('unsupported NeKo-to-BioMASS version or curation_file declaration')
    curation = None
    if reference is not None:
        # Backend 2.5.0 ODE v2.0: pinned history companion bound to the network.
        if not isinstance(reference, dict) or (reference.get('server'), reference.get('session_id'), reference.get('role')) != ('NeKo', session, 'neko_history'):
            raise ValueError('NeKo curation companion ownership mismatch')
        reserved = {'original.handoff.json', 'import.handoff.json', 'relocation.json', 'resource.json', 'resource.original.json', network_name}
        curation = copy_curation(source, reference, reserved)
        check_binding(curation[1], artifact, session, manifest.get('history_state_id'))
    network_bytes, original_bytes = network.read_bytes(), original.read_bytes()
    if hashlib.sha256(network_bytes).hexdigest() != expected:
        raise ValueError('NeKo network changed while copying')
    if json.loads(original_bytes) != manifest:
        raise ValueError('NeKo manifest changed while copying')
    target = project / 'runs/network-curator' / session / 'ode-handoffs' / capture_id
    with staged_capture(project, target) as stage:
        from scripts.capture.resource import record_resource
        record_resource(stage, resource_metadata_file)
        (stage / 'original.handoff.json').write_bytes(original_bytes)
        (stage / network_name).write_bytes(network_bytes)
        if digest(stage / network_name) != expected:
            raise ValueError('NeKo network changed while recording')
        if (stage / 'original.handoff.json').read_bytes() != original_bytes:
            raise ValueError('NeKo manifest changed while recording')
        imported = copy.deepcopy(manifest)
        imported['network_file']['path'] = str(target / network_name)
        if curation:
            (stage / curation[0]).write_bytes(curation[1])
            if digest(stage / curation[0]) != reference['sha256']:
                raise ValueError('NeKo curation companion changed while recording')
            imported['curation_file']['path'] = str(target / curation[0])
        (stage / 'import.handoff.json').write_text(json.dumps(imported, indent=2) + '\n', encoding='utf-8')
        provenance = {'original_manifest_sha256': digest(stage / 'original.handoff.json'),
                      'import_manifest_sha256': digest(stage / 'import.handoff.json'),
                      'network_sha256': expected, 'source_manifest_path': str(original),
                      'source_network_path': str(network)}
        if curation:
            provenance.update({'curation_sha256': reference['sha256'], 'source_curation_path': str(curation[2]),
                               'curation_binding': CURATION_NOTE})
        (stage / 'relocation.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
        result = {
            'upstream_manifest': (target / 'import.handoff.json').relative_to(project).as_posix(),
            'artifacts': [
                {'path': (target / path.name).relative_to(project).as_posix(), 'sha256': digest(path)}
                for path in sorted(stage.iterdir())
            ],
        }
        if curation:
            result['backend_import_manifest'] = str(original)
    from scripts.capture.index import register_capture
    register_capture(project, target)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    roots = parser.add_mutually_exclusive_group(required=True)
    roots.add_argument('--server-root', type=Path, help='Legacy installation containing artifacts/')
    roots.add_argument('--artifact-root', type=Path, help='Explicit per-server artifact directory containing session directories')
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--capture-id', required=True)
    parser.add_argument('--resource-metadata', type=Path, help='Explicit server/cache resource record with name, version, cache_timestamp; never inferred')
    arguments = parser.parse_args()
    try:
        result = record_neko(Path(__file__).resolve().parents[2], arguments.server_root,
                             arguments.manifest, arguments.capture_id, resource_metadata_file=arguments.resource_metadata,
                             artifact_root=arguments.artifact_root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'NeKo ODE handoff recording failed: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

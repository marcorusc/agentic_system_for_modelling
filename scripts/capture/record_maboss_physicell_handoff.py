#!/usr/bin/env python3
"""Capture and verify an existing MaBoSS export, preserving its typed lineage."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.capture.artifact_capture import staged_capture, reject_symlinks
from scripts.capture.index import register_capture
from scripts.codex.launcher_config import validate_session_id
from scripts.codex.ode_artifacts import safe_file, digest

def record_maboss(project, server_root, manifest_path, capture_id, *, parent_root=None):
    from mcp_biomodelling_servers.handoff import (MaBoSSToPhysiCellHandoffManifest,
        NeKoToMaBoSSHandoffManifest, verify_handoff_manifest, bnd_node_names, bnet_node_names)
    project = project.resolve(strict=True)
    validate_session_id(capture_id)
    root = server_root.absolute() / 'artifacts'
    reject_symlinks(root)
    original = safe_file(root, manifest_path.absolute().relative_to(root).as_posix())
    original_bytes = original.read_bytes()
    raw = json.loads(original_bytes)
    parsed = MaBoSSToPhysiCellHandoffManifest.model_validate(raw)
    session = validate_session_id(parsed.source.session_id)
    source = root / session
    safe_file(source, original.relative_to(source).as_posix())
    target = project / 'runs/boolean-dynamics-modeler' / session / 'physicell-handoffs' / capture_id
    imported = copy.deepcopy(raw)
    with staged_capture(project, target) as stage:
        (stage / 'original.handoff.json').write_bytes(original_bytes)
        def capture_ref(ref, allowed, prefix=''):
            file = safe_file(allowed, Path(ref['path']).relative_to(allowed).as_posix())
            content = file.read_bytes()
            if hashlib.sha256(content).hexdigest() != ref['sha256'] or len(content) != ref['size_bytes']:
                raise ValueError('artifact hash or byte count mismatch')
            name = Path(prefix) / file.name
            if name.as_posix() in {'original.handoff.json', 'import.handoff.json', 'relocation.json'} or (stage / name).exists():
                raise ValueError('artifact basename collision')
            (stage / name).parent.mkdir(parents=True, exist_ok=True)
            (stage / name).write_bytes(content)
            ref['path'] = str(target / name)
            return name
        bnd = capture_ref(imported['bnd_file'], source)
        capture_ref(imported['cfg_file'], source)
        if imported['simulation'].get('result_file'):
            capture_ref(imported['simulation']['result_file'], source)
        if imported.get('parent_manifest'):
            parent = imported['parent_manifest']
            allowed = parent_root.absolute() if parent_root else project
            reject_symlinks(allowed)
            parent_name = capture_ref(parent, allowed, 'parent/export')
            parent_raw = json.loads((stage / parent_name).read_bytes())
            parent_parsed = NeKoToMaBoSSHandoffManifest.model_validate(parent_raw)
            if parent_parsed.source.session_id != parent['session_id']:
                raise ValueError('parent manifest session mismatch')
            (stage / 'parent/original.handoff.json').write_bytes((stage / parent_name).read_bytes())
            network_name = capture_ref(parent_raw['bnet_file'], allowed, 'parent/network')
            if bnet_node_names(stage / network_name) != parent_parsed.network.nodes:
                raise ValueError('parent BNET node order mismatch')
            (stage / parent_name).write_text(json.dumps(parent_raw, indent=2) + '\n')
            parent['sha256'] = digest(stage / parent_name)
            parent['size_bytes'] = (stage / parent_name).stat().st_size
        if bnd_node_names(stage / bnd) != parsed.network.nodes:
            raise ValueError('BND nodes disagree with manifest')
        (stage / 'import.handoff.json').write_text(json.dumps(imported, indent=2) + '\n')
        staged = copy.deepcopy(imported)
        for ref in [staged['bnd_file'], staged['cfg_file'], staged.get('parent_manifest'), staged['simulation'].get('result_file')]:
            if ref:
                ref['path'] = str(stage / Path(ref['path']).relative_to(target))
        verify_handoff_manifest(MaBoSSToPhysiCellHandoffManifest.model_validate(staged))
        (stage / 'relocation.json').write_text(json.dumps({'source_manifest': str(original),
            'original_manifest_sha256': hashlib.sha256(original_bytes).hexdigest(),
            'import_manifest_sha256': digest(stage / 'import.handoff.json'),
            'policy': 'Only artifact paths and relocated parent manifest hashes/sizes change.'}, indent=2) + '\n')
    return register_capture(project, target)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--server-root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--capture-id', required=True)
    parser.add_argument('--parent-root', type=Path, help='Explicit trusted root for upstream manifest and its BNET; default project')
    args = parser.parse_args()
    try:
        print(json.dumps(record_maboss(args.project, args.server_root, args.manifest, args.capture_id, parent_root=args.parent_root), indent=2))
    except (ImportError, OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'MaBoSS capture failed: {error}\n')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())

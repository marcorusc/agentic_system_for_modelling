#!/usr/bin/env python3
"""Capture and verify an existing MaBoSS export, preserving its typed lineage."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.capture.artifact_capture import boolean_artifact_root, staged_capture, reject_symlinks
from scripts.capture.index import register_capture
from scripts.codex.launcher_config import validate_session_id
from scripts.codex.ode_artifacts import safe_file, digest
from scripts.capture.neko_curation import CURATION_NOTE, verify_relocated
from scripts.curation_contract import check_parent_scope


def verify_relocated_stage(staged, parent_original, parent_relocated, curation_bytes):
    """Verify a staged MaBoSS copy whose relocated NeKo parent carries curation.

    The backend verifier would reload that parent with path-bound curation and
    reject every relocation; the live original was verified before this point.
    """
    from mcp_biomodelling_servers.handoff import manifest_artifacts, verify_handoff_artifact
    from mcp_biomodelling_servers.boolean_readouts import verify_bnd_readouts
    for artifact in manifest_artifacts(staged):
        verify_handoff_artifact(artifact)
    if staged.readouts:
        verify_bnd_readouts(staged.bnd_file.path, staged.readouts, staged.network.nodes)
    verify_relocated(parent_original, parent_relocated, 'bnet_file', curation_bytes)
    if staged.lineage != [parent_relocated.source]:
        raise ValueError('source stage-parent identity mismatch')
    inherited = [entry for entry in staged.source_ancestry or [] if entry.source.server == 'NeKo']
    if inherited != (parent_relocated.source_ancestry or []):
        raise ValueError('MaBoSS source ancestry does not match its NeKo stage parent')


def record_maboss(project, server_root, manifest_path, capture_id, *, parent_root=None, artifact_root=None):
    from mcp_biomodelling_servers.handoff import (MaBoSSToPhysiCellHandoffManifest,
        NeKoToMaBoSSHandoffManifest, verify_handoff_manifest, bnd_node_names, bnet_node_names, handoff_artifact)
    project = project.resolve(strict=True)
    validate_session_id(capture_id)
    root = boolean_artifact_root(server_root, artifact_root)
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
        if parsed.schema_version != '1.0':
            from mcp_biomodelling_servers.import_lineage import copy_source_ancestry
            copy_source_ancestry(parsed.source_ancestry, stage / 'ancestry')
        parent_curation = None
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
            if not parsed.lineage or parent_parsed.source != parsed.lineage[0]:
                raise ValueError('parent provenance disagrees with declared stage lineage')
            # Only declared v2.1 readouts may extend the NeKo core.
            check_parent_scope(parent_parsed.network.nodes, parent_parsed.network.output_nodes,
                               parsed.network.nodes, parsed.network.output_nodes, parsed.readouts)
            if parsed.schema_version != '1.0':
                inherited = [item for item in parsed.source_ancestry if item.source.server == 'NeKo']
                if inherited != (parent_parsed.source_ancestry or []):
                    raise ValueError('current ancestry disagrees with the exact stage parent')
            if parent_parsed.schema_version != '1.0':
                from mcp_biomodelling_servers.import_lineage import copy_source_ancestry
                copy_source_ancestry(parent_parsed.source_ancestry, stage / 'ancestry')
            (stage / 'parent/original.handoff.json').write_bytes((stage / parent_name).read_bytes())
            network_name = capture_ref(parent_raw['bnet_file'], allowed, 'parent/network')
            if bnet_node_names(stage / network_name) != parent_parsed.network.nodes:
                raise ValueError('parent BNET node order mismatch')
            if parent_parsed.curation_file:
                # The live original (and its live parent) carries the exact binding.
                verify_handoff_manifest(parsed)
                parent_curation = capture_ref(parent_raw['curation_file'], allowed, 'parent/curation')
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
        if staged.get('parent_manifest'):
            # The published parent points at the final target, which deliberately
            # does not exist yet. Validate a disposable parent copy against the
            # staging payload; retain final paths/hashes in the published files.
            with tempfile.TemporaryDirectory(prefix='.validation-', dir=stage) as folder:
                checked_parent = copy.deepcopy(parent_raw)
                checked_parent['bnet_file']['path'] = str(stage / network_name)
                if parent_curation:
                    checked_parent['curation_file']['path'] = str(stage / parent_curation)
                checked_file = Path(folder) / Path(parent_name).name
                checked_file.write_text(json.dumps(checked_parent))
                staged['parent_manifest'] = handoff_artifact(checked_file, server='NeKo',
                    session_id=parent_parsed.source.session_id, role='parent_manifest').model_dump(mode='json')
                if parent_curation:
                    verify_relocated_stage(MaBoSSToPhysiCellHandoffManifest.model_validate(staged), parent_parsed,
                                           NeKoToMaBoSSHandoffManifest.model_validate(checked_parent),
                                           (stage / parent_curation).read_bytes())
                else:
                    verify_handoff_manifest(MaBoSSToPhysiCellHandoffManifest.model_validate(staged))
        else:
            verify_handoff_manifest(MaBoSSToPhysiCellHandoffManifest.model_validate(staged))
        relocation = {'source_manifest': str(original),
            'original_manifest_sha256': hashlib.sha256(original_bytes).hexdigest(),
            'import_manifest_sha256': digest(stage / 'import.handoff.json'),
            'policy': 'Only artifact paths and relocated parent manifest hashes/sizes change.'}
        if parent_curation:
            relocation['parent_curation_binding'] = CURATION_NOTE
        (stage / 'relocation.json').write_text(json.dumps(relocation, indent=2) + '\n')
    record = register_capture(project, target)
    # A curated NeKo parent is bound to its original paths: PhysiCell imports the original.
    return {**record, 'backend_import_manifest': str(original)} if parent_curation else record

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[2])
    roots = parser.add_mutually_exclusive_group(required=True)
    roots.add_argument('--server-root', type=Path, help='Legacy installation containing artifacts/')
    roots.add_argument('--artifact-root', type=Path, help='Explicit per-server artifact directory containing session directories')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--capture-id', required=True)
    parser.add_argument('--parent-root', type=Path, help='Explicit trusted root for upstream manifest and its BNET; default project')
    args = parser.parse_args()
    try:
        print(json.dumps(record_maboss(args.project, args.server_root, args.manifest, args.capture_id, parent_root=args.parent_root, artifact_root=args.artifact_root), indent=2))
    except (ImportError, OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'MaBoSS capture failed: {error}\n')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())

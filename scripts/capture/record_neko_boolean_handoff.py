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
from scripts.capture.artifact_capture import boolean_artifact_root, staged_capture
from scripts.capture.neko_curation import CURATION_NOTE, copy_curation, verify_relocated
from scripts.codex.launcher_config import validate_session_id
from scripts.codex.ode_artifacts import digest, read_json, safe_file


def source_lineage(source: Path, network: Path, raw: dict) -> tuple[bytes, Path] | None:
    """The export's sibling ``<bnet>.lineage.json`` source-lineage sidecar, if any.

    It must describe exactly this manifest's BNET and history companion; older
    exports without a sidecar are captured as before.
    """
    from mcp_biomodelling_servers.import_lineage import SourceExport
    candidate = network.with_name(network.name + '.lineage.json')
    if not candidate.exists():
        return None
    path = safe_file(source, candidate.relative_to(source).as_posix())
    data = path.read_bytes()
    try:
        record = SourceExport.model_validate_json(data).model_dump(mode='json')
    except ValueError as error:
        detail = error.errors()[0]['msg'] if hasattr(error, 'errors') else str(error)
        raise ValueError(f'invalid source-lineage sidecar {candidate.name}: {detail}') from None
    if record['artifact'] != raw['bnet_file'] or record.get('curation_file') != raw.get('curation_file'):
        raise ValueError('source-lineage sidecar describes another BNET or history companion')
    return data, path


def record_neko(project: Path, server_root: Path | None, manifest_path: Path, capture_id: str, *, resource_metadata_file: Path | None = None, artifact_root: Path | None = None) -> dict:
    # Pure backend contract readers only; an absent backend fails explicitly.
    from mcp_biomodelling_servers.handoff import NeKoToMaBoSSHandoffManifest, bnet_node_names, verify_handoff_manifest
    project = project.resolve(strict=True)
    validate_session_id(capture_id)
    artifacts = boolean_artifact_root(server_root, artifact_root)
    original = safe_file(artifacts, manifest_path.absolute().relative_to(artifacts).as_posix())
    raw = read_json(original)
    parsed = NeKoToMaBoSSHandoffManifest.model_validate(raw)
    session = validate_session_id(parsed.source.session_id)
    source = artifacts / session
    original = safe_file(source, original.relative_to(source).as_posix())
    network = safe_file(source, Path(parsed.bnet_file.path).relative_to(source).as_posix())
    basename = network.name
    if basename in {'original.handoff.json', 'import.handoff.json', 'relocation.json', 'resource.json', 'resource.original.json'}:
        raise ValueError('BNET basename conflicts with capture metadata')
    # Live verification of the original includes the 2.1 curation binding.
    verify_handoff_manifest(parsed)
    if bnet_node_names(network) != parsed.network.nodes:
        raise ValueError('BNET target order disagrees with manifest nodes')
    lineage_name = basename + '.lineage.json'
    reserved = {'original.handoff.json', 'import.handoff.json', 'relocation.json', 'resource.json', 'resource.original.json',
                basename, lineage_name}
    curation = copy_curation(source, raw['curation_file'], reserved) if parsed.curation_file else None
    lineage = source_lineage(source, network, raw)
    original_bytes, network_bytes = original.read_bytes(), network.read_bytes()
    if json.loads(original_bytes) != raw or hashlib.sha256(network_bytes).hexdigest() != parsed.bnet_file.sha256:
        raise ValueError('source artifacts changed during validation')
    target = project / 'runs/network-curator' / session / 'boolean-handoffs' / capture_id
    imported = copy.deepcopy(raw)
    imported['bnet_file']['path'] = str(target / basename)
    if curation:
        imported['curation_file']['path'] = str(target / curation[0])
    with staged_capture(project, target) as stage:
        from scripts.capture.resource import record_resource
        record_resource(stage, resource_metadata_file)
        if parsed.schema_version != '1.0':
            from mcp_biomodelling_servers.import_lineage import copy_source_ancestry
            copy_source_ancestry(parsed.source_ancestry, stage / 'ancestry')
        (stage / 'original.handoff.json').write_bytes(original_bytes)
        (stage / basename).write_bytes(network_bytes)
        if curation:
            (stage / curation[0]).write_bytes(curation[1])
        if lineage:
            # Identity record of the original export: copied unchanged, never relocated.
            (stage / lineage_name).write_bytes(lineage[0])
        (stage / 'import.handoff.json').write_text(json.dumps(imported, indent=2) + '\n', encoding='utf-8')
        staged = NeKoToMaBoSSHandoffManifest.model_validate(imported)
        staged.bnet_file.path = str(stage / basename)
        if curation:
            staged.curation_file.path = str(stage / curation[0])
            verify_relocated(parsed, staged, 'bnet_file', curation[1])
        else:
            verify_handoff_manifest(staged)
        if bnet_node_names(stage / basename) != staged.network.nodes:
            raise ValueError('captured BNET target order mismatch')
        relocation = {
            'original_manifest_sha256': hashlib.sha256(original_bytes).hexdigest(),
            'import_manifest_sha256': digest(stage / 'import.handoff.json'),
            'bnet_sha256': hashlib.sha256(network_bytes).hexdigest(),
            'source_manifest_path': str(original), 'source_bnet_path': str(network),
        }
        if curation:
            relocation.update({'curation_sha256': hashlib.sha256(curation[1]).hexdigest(),
                               'source_curation_path': str(curation[2]), 'curation_binding': CURATION_NOTE})
        if lineage:
            relocation.update({'source_lineage_sha256': hashlib.sha256(lineage[0]).hexdigest(),
                               'source_lineage_path': str(lineage[1])})
        (stage / 'relocation.json').write_text(json.dumps(relocation, indent=2) + '\n', encoding='utf-8')
        result = {'upstream_manifest': (target / 'import.handoff.json').relative_to(project).as_posix(),
                  'artifacts': [{'path': (target / p.relative_to(stage)).relative_to(project).as_posix(), 'sha256': digest(p)}
                                for p in sorted(stage.rglob('*')) if p.is_file()]}
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
    args = parser.parse_args()
    try:
        result = record_neko(Path(__file__).resolve().parents[2], args.server_root, args.manifest, args.capture_id, resource_metadata_file=args.resource_metadata, artifact_root=args.artifact_root)
    except (ImportError, OSError, ValueError, KeyError, TypeError) as error:
        print(f'NeKo Boolean capture failed: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

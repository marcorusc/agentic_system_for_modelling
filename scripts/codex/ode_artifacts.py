"""Repository ODE completion contract; no modelling tools or generated code execution."""
from __future__ import annotations

import csv
import math
import hashlib
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

SHA = re.compile(r"[0-9a-f]{64}\Z")
REVISION = re.compile(r"rev_[0-9a-f]{32}\Z")


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_file(base: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError('invalid artifact path')
    parts = PurePosixPath(relative)
    if parts.is_absolute() or '..' in parts.parts or relative != parts.as_posix():
        raise ValueError('artifact path must be canonical and relative')
    base = base.absolute()
    path = base / relative
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError('artifact path contains a symlink')
        if component == base:
            break
    if not path.is_file():
        raise ValueError(f'missing artifact: {relative}')
    return path


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'expected JSON object: {path.name}')
    return value


def validate_metadata(handoff: dict) -> dict:
    ode = handoff.get('ode')
    if not isinstance(ode, dict):
        raise ValueError('ODE result requires ode provenance')
    required = {'input_kind', 'document_version', 'revision', 'source_identifiers', 'evidence_paths',
                'export_status', 'simulation_paths'}
    if not required <= ode.keys():
        raise ValueError('ODE provenance is missing required fields')
    if ode['input_kind'] not in {'neko', 'standalone_text', 'reactions'}:
        raise ValueError('invalid ODE input_kind')
    if type(ode['document_version']) is not int or ode['document_version'] < 0:
        raise ValueError('ODE document_version must be a nonnegative integer')
    if ode['revision'] is not None and (not isinstance(ode['revision'], str) or not REVISION.fullmatch(ode['revision'])):
        raise ValueError('invalid ODE revision')
    for key in ('source_identifiers', 'evidence_paths', 'simulation_paths'):
        if not isinstance(ode[key], list) or any(not isinstance(v, str) or not v for v in ode[key]):
            raise ValueError(f'ODE {key} must be a string array')
    if ode['export_status'] not in {'pending', 'approved', 'exported'}:
        raise ValueError('invalid ODE export_status')
    if ode['input_kind'] == 'neko':
        if not handoff['derived_from_session_id'] or not ode.get('upstream_manifest'):
            raise ValueError('NeKo-derived ODE requires upstream lineage and manifest')
    else:
        if handoff['derived_from_session_id'] is not None:
            raise ValueError('standalone ODE cannot claim NeKo lineage')
        if ode.get('standalone_authorized') is not True:
            raise ValueError('standalone ODE requires explicit authorization')
        if ode['input_kind'] == 'standalone_text':
            if not isinstance(ode.get('source_sha256'), str) or not SHA.fullmatch(ode['source_sha256']):
                raise ValueError('standalone text requires source_sha256')
        elif not isinstance(ode.get('construction_request'), str) or not ode['construction_request'].strip():
            raise ValueError('reaction construction requires the bounded construction request')
    return ode


def verify_inventory(directory: Path) -> dict:
    inventory = read_json(safe_file(directory, 'integrity.json'))
    if not inventory:
        raise ValueError('empty revision integrity inventory')
    actual = {}
    for relative, expected in inventory.items():
        if not isinstance(expected, str) or not SHA.fullmatch(expected):
            raise ValueError('invalid integrity digest')
        file = safe_file(directory, relative)
        if digest(file) != expected:
            raise ValueError(f'revision integrity mismatch: {relative}')
        actual[relative] = expected
    files = set()
    for path in directory.rglob('*'):
        if path.is_symlink():
            raise ValueError('symlink inside revision')
        if path.is_file() and path.name != 'integrity.json':
            files.add(path.relative_to(directory).as_posix())
    if files != set(actual):
        raise ValueError('revision integrity inventory does not cover all files')
    return inventory


def validate_completion(handoff: dict, project: Path, files: dict[str, Path]) -> None:
    ode = validate_metadata(handoff)
    if not ode['revision']:
        raise ValueError('completed ODE construction requires a generated revision')
    revision_path = ode.get('revision_path')
    prefix = f"runs/ode-modeler/{handoff['session_id']}/"
    if not isinstance(revision_path, str) or not revision_path.startswith(prefix) or PurePosixPath(revision_path).name != ode['revision']:
        raise ValueError('revision path must belong to this ODE session and revision')
    required = ('integrity.json', 'model.txt', 'model_summary.json', 'snapshot.json',
                'request.json', 'generated_model/ode.py')
    for name in required:
        if revision_path + '/' + name not in files:
            raise ValueError(f'completed ODE requires listed revision artifact: {name}')
    directory = project / revision_path
    inventory = verify_inventory(directory)
    if any(revision_path + '/' + name not in files for name in inventory):
        raise ValueError('all revision files must be listed in the typed result')
    snapshot = read_json(directory / 'snapshot.json')
    document = snapshot.get('document', {})
    if not isinstance(document, dict):
        raise ValueError('ODE snapshot document must be an object')
    if document.get('version') != ode['document_version']:
        raise ValueError('stale ODE document version')
    if not isinstance(document.get('configuration'), dict) or not isinstance(document.get('evidence'), dict) or not isinstance(snapshot.get('coverage'), dict):
        raise ValueError('ODE snapshot requires configuration, evidence and coverage')
    summary = read_json(directory / 'model_summary.json')
    if not {'equations', 'parameters', 'initials', 'species'} <= summary.keys():
        raise ValueError('ODE model summary requires equations and numerical origins')
    if ode['input_kind'] == 'standalone_text':
        original = document.get('source_file', {}).get('sha256') if document.get('source_file') else None
        text_hash = hashlib.sha256((document.get('text') or '').encode()).hexdigest()
        if ode['source_sha256'] not in {original, text_hash}:
            raise ValueError('standalone source hash does not match snapshot')
    if ode['input_kind'] == 'neko':
        manifest_path = ode['upstream_manifest']
        manifest = read_json(safe_file(project, manifest_path))
        if not manifest_path.startswith(f"runs/network-curator/{handoff['derived_from_session_id']}/"):
            raise ValueError('upstream manifest is outside the source NeKo session')
        if manifest.get('handoff_type') != 'neko-to-biomass' or manifest.get('source', {}).get('session_id') != handoff['derived_from_session_id']:
            raise ValueError('wrong upstream ODE handoff type/session')
        artifact = manifest.get('network_file', {})
        if manifest.get('source', {}).get('server') != 'NeKo' or artifact.get('server') != 'NeKo' or artifact.get('session_id') != handoff['derived_from_session_id'] or artifact.get('role') != 'neko_ode_network':
            raise ValueError('upstream network ownership mismatch')
        network_path = Path(artifact.get('path', ''))
        try:
            network = safe_file(project, network_path.relative_to(project).as_posix())
        except ValueError as error:
            raise ValueError('record a project-contained NeKo network before ODE completion') from error
        if digest(network) != artifact.get('sha256'):
            raise ValueError('upstream network hash mismatch')
        parent = (project / manifest_path).parent
        if (parent / 'relocation.json').exists():
            relocation = read_json(safe_file(parent, 'relocation.json'))
            original_path = safe_file(parent, 'original.handoff.json')
            original = read_json(original_path)
            if relocation.get('original_manifest_sha256') != digest(original_path) or relocation.get('import_manifest_sha256') != digest(project / manifest_path) or relocation.get('network_sha256') != digest(network):
                raise ValueError('NeKo relocation hashes do not match')
            original['network_file']['path'] = artifact['path']
            if original != manifest:
                raise ValueError('relocation changed NeKo scientific provenance')
        upstream = document.get('upstream', {})
        if upstream != manifest:
            raise ValueError('snapshot upstream differs from recorded NeKo manifest')
    for relative in ode['evidence_paths']:
        # ODE claims and existing upstream edge reviews have distinct locations.
        allowed = [f"evidence/reports/{handoff['session_id']}/ode/"]
        if handoff['derived_from_session_id']:
            allowed.append(f"evidence/reports/{handoff['derived_from_session_id']}/")
        if not any(relative.startswith(p) for p in allowed):
            raise ValueError('evidence path belongs to a different session')
        safe_file(project, relative)
    for relative in ode['simulation_paths']:
        if relative not in files or not relative.startswith(prefix) or PurePosixPath(relative).name != 'simulation.json':
            raise ValueError('simulation claim requires a listed scenario report')
        report = files[relative]
        request_path = report.parent / 'request.json'
        request_relative = request_path.relative_to(project).as_posix()
        if request_relative not in files or read_json(request_path).get('revision') != ode['revision']:
            raise ValueError('simulation request must match the selected revision')
        numerical = read_json(report)
        if numerical.get('numerical_valid') is not True or not numerical.get('conditions') or not numerical.get('time_span'):
            raise ValueError('simulation requires successful actual numerical conditions')
        csv_files = [p for p in files.values() if p.parent == report.parent and p.name in {'species.csv', 'observables.csv'}]
        if len(csv_files) < 2:
            raise ValueError('simulation requires species and observable CSV trajectories')
        for csv_file in csv_files:
            with csv_file.open(newline='') as stream:
                rows = csv.DictReader(stream)
                if not rows.fieldnames or 'time' not in rows.fieldnames:
                    raise ValueError('trajectory requires time column')
                count = 0
                for row in rows:
                    count += 1
                    if any(not math.isfinite(float(value)) for name, value in row.items() if name != 'condition'):
                        raise ValueError('trajectory contains nonfinite values')
                if not count:
                    raise ValueError('empty trajectory')
    if ode['export_status'] in {'approved', 'exported'}:
        approval = ode.get('export_approval', {})
        decisions = safe_file(project, 'DECISIONS.md')
        if not isinstance(approval, dict):
            raise ValueError('ODE export approval must be an object')
        approval_path = approval.get('path')
        if not isinstance(approval_path, str) or approval_path not in files or not approval_path.startswith(prefix):
            raise ValueError('ODE export approval requires a listed immutable decision snapshot')
        approval_file = files[approval_path]
        if approval.get('sha256') != digest(approval_file):
            raise ValueError('ODE export approval snapshot hash mismatch')
        decision_id = approval.get('decision_id')
        if not isinstance(decision_id, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', decision_id):
            raise ValueError('ODE export approval requires a safe decision ID')
        block = (f"Decision: {decision_id}\nStatus: approved\nSession: {handoff['session_id']}\n"
                 f"Revision: {ode['revision']}\nAction: export_model_bundle")
        if block not in decisions.read_text() or block not in approval_file.read_text():
            raise ValueError('ODE final export lacks matching recorded researcher approval')
    if ode['export_status'] == 'exported':
        bundle = ode.get('bundle_path')
        if bundle not in files or not bundle.endswith('.zip'):
            raise ValueError('exported ODE requires a listed bundle')
        if not zipfile.is_zipfile(files[bundle]):
            raise ValueError('invalid ODE bundle ZIP')
        with zipfile.ZipFile(files[bundle]) as archive:
            if archive.testzip() is not None:
                raise ValueError('invalid bundle CRC')
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError('duplicate bundle members')
            for name in names:
                p = PurePosixPath(name)
                if p.is_absolute() or '..' in p.parts or '\\' in name:
                    raise ValueError('unsafe bundle member')
            for name, expected in inventory.items():
                if hashlib.sha256(archive.read('model/' + name)).hexdigest() != expected:
                    raise ValueError('bundle does not contain the approved revision')
            if not {'requirements.txt', 'run_simulation.py'} <= set(names):
                raise ValueError('bundle lacks reproduction entrypoints')

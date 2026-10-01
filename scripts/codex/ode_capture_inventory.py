"""Reconcile a recorded specialist inventory with its own successful server call."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.codex.artifact_capture import reject_symlinks
from scripts.codex.launcher_config import validate_session_id
from scripts.codex.ode_artifacts import _unique_object, digest, read_json, safe_file
from scripts.codex.validate_handoff import validate_handoff


def verified_inventory(project: Path, invocation: Path, session: str) -> tuple[list, dict]:
    validate_session_id(session)
    project = project.resolve(strict=True)
    invocation = invocation.absolute()
    parent = project / 'runs/ode-modeler' / session / 'specialist-invocations'
    if invocation.parent != parent:
        raise ValueError('invocation must belong to the exact ODE session')
    reject_symlinks(invocation)
    files = {name: safe_file(invocation, name) for name in ('handoff.json', 'provenance.json', 'events.jsonl', 'task.txt')}
    hashes = {name: digest(path) for name, path in files.items()}
    handoff, provenance = read_json(files['handoff.json']), read_json(files['provenance.json'])
    validate_handoff(handoff, project_root=project, expected_specialist='ode_modeler', expected_session_id=session)
    if handoff['status'] != 'needs_approval' or handoff['artifacts']:
        raise ValueError('expected an unrecorded ODE candidate; capture does not accept a scientific stage')
    if (provenance.get('specialist') != 'ode_modeler'
            or type(provenance.get('process_exit_code')) is not int or provenance['process_exit_code'] != 0
            or provenance.get('cancelled') is not False
            or provenance.get('handoff_parse_error') is not None
            or provenance.get('malformed_event_count') != 0
            or provenance.get('invocation_id') != invocation.name
            or provenance.get('event_stream') != 'events.jsonl'
            or provenance.get('prompt_sha256') != hashes['task.txt']):
        raise ValueError('invocation did not finish cleanly or provenance does not match')
    inventory = provenance.get('effective_mcp_inventory')
    if (not isinstance(inventory, dict) or inventory.get('biomass') is not True
            or any(type(v) is not bool or (k != 'biomass' and v) for k, v in inventory.items())
            or provenance.get('apps_enabled') is not False):
        raise ValueError('unsafe recorded specialist inventory')
    catalogue = None
    for line in files['events.jsonl'].read_text().splitlines():
        event = json.loads(line, object_pairs_hook=_unique_object)
        if not isinstance(event, dict):
            raise ValueError('invalid recorded event')
        item = event.get('item', {})
        if not isinstance(item, dict):
            raise ValueError('invalid recorded event item')
        if (event.get('type') != 'item.completed' or item.get('type') != 'mcp_tool_call'
                or item.get('server') != 'biomass' or item.get('tool') != 'list_generated_files'):
            continue
        # The latest matching session request must itself have succeeded.
        if item.get('arguments', {}).get('session_id') != session:
            continue
        result = item.get('result')
        if item.get('status') != 'completed' or item.get('error') is not None or not isinstance(result, dict) or result.get('isError', False):
            raise ValueError('recorded file inventory call failed')
        catalogue = result.get('structured_content', result.get('structuredContent'))
    if (not isinstance(catalogue, dict) or catalogue.get('server') != 'BioMASS'
            or catalogue.get('session_id') != session or catalogue.get('scope') != 'session'):
        raise ValueError('missing successful session-scoped BioMASS inventory from this invocation')
    entries, declared = handoff.get('server_artifacts'), catalogue.get('files')
    if not isinstance(entries, list) or not entries or not isinstance(declared, list):
        raise ValueError('missing explicit artifact inventories')
    if type(catalogue.get('count')) is not int or catalogue['count'] != len(declared):
        raise ValueError('server inventory count mismatch')
    by_path = {}
    for entry in declared:
        if (not isinstance(entry, dict) or entry.get('session_id') != session
                or not isinstance(entry.get('path'), str) or entry['path'] in by_path
                or type(entry.get('size_bytes')) is not int or entry['size_bytes'] < 0):
            raise ValueError('invalid or duplicate server inventory entry')
        by_path[entry['path']] = entry
    normalized, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('path'), str):
            raise ValueError('invalid specialist artifact entry')
        path = entry['path']; actual = by_path.get(path)
        if (actual is None or path in seen or entry.get('session_id', session) != session
                or entry.get('server', 'BioMASS') != 'BioMASS'
                or type(entry.get('size_bytes')) is not int or entry['size_bytes'] != actual['size_bytes']):
            raise ValueError('specialist and authoritative server inventories disagree')
        if actual.get('sha256') is not None and actual['sha256'] != entry.get('sha256'):
            raise ValueError('server and specialist hashes disagree')
        seen.add(path)
        normalized.append({**copy.deepcopy(entry), 'session_id': session})
    if seen != set(by_path):
        raise ValueError('specialist inventory omits server artifacts')
    for name, path in files.items():
        if digest(path) != hashes[name]:
            raise ValueError('invocation record changed during verification')
    references = [{'path': path.relative_to(project).as_posix(), 'sha256': hashes[name]} for name, path in files.items()]
    return normalized, {'invocation_id': invocation.name, 'records': references,
                        'normalization': 'session_id restored only from same-invocation server catalogue'}

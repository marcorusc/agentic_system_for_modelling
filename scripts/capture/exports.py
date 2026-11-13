"""Copy a specialist invocation's server exports out of the transient MCP artifact store.

Each specialist's inline MCP server lives only as long as its agent run, and some
exports are overwritten in place (NeKo always writes ``<session>/Network.sif``).
After a run, ``capture_exports`` scans that invocation's transcript for successful
results of the specialist's own export tools, reads the exported file paths
(structured ``file``-style fields first; NeKo's ``SIF/History/BNET exported: <path>``
text prefix only when no structured field is present), and copies each file that
lies inside ``<artifact root>/<Server>/<session>/`` (no symlinks) to
``runs/<specialist>/<session>/exports/<invocation_id>/<file name>`` with an
``exports.json`` manifest. Anything else is refused and reported, never copied.
No export results -> no ``exports/`` directory. An identical rerun is a no-op;
differing existing content fails closed. ode-modeler (record_ode_artifacts.py)
and data-analyst (no MCP exports) are skipped.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from scripts.capture.artifact_capture import reject_symlinks, staged_capture
from scripts.codex.launcher_config import validate_session_id

# specialist -> (server artifact directory, MCP tool-name prefix, {tool: ((field, format), ...)})
# A format of None means "use the result's own `format` field" (NeKo export_network).
EXPORT_TOOLS = {
    'network-curator': ('NeKo', 'neko', {
        'export_network': (('file', None), ('curation_file', 'curation')),
    }),
    'boolean-dynamics-modeler': ('MaBoSS', 'maboss', {
        'export_maboss_bnd_cfg': (('bnd_file', 'bnd'), ('cfg_file', 'cfg')),
        'export_maboss_handoff': (('manifest_file', 'handoff-manifest'),),
    }),
    'multicellular-configurator': ('PhysiCell', 'physicell', {
        'export_xml_configuration': (('file', 'xml'),),
        'export_cell_rules_csv': (('file', 'csv'),),
        'export_configuration_bundle': (('bundle', 'bundle'),),
    }),
}
NEKO_TEXT = re.compile(r'\A(SIF|History|BNET) exported: `?(/[^`\n]*?\.(?:sif|json|bnet))`?(?=[.\s]|\Z)')
MANIFEST = 'exports.json'


def artifact_root() -> Path:
    """Shared server artifact root, resolved as the 2.5.x servers do (artifact_manager.artifact_root)."""
    configured = os.environ.get('MCP_BIOMODELLING_ARTIFACT_ROOT')
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            raise ValueError('MCP_BIOMODELLING_ARTIFACT_ROOT must be absolute')
        return root
    cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))).expanduser()
    if not cache.is_absolute():
        cache = Path.home() / '.cache'
    return cache / 'mcp-biomodelling' / 'artifacts'


def _structured(value, depth=0):
    """Unwrap an MCP result (JSON text, CallToolResult dict, content list) to its structured payload."""
    if depth > 4:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, RecursionError):
            return None
    if isinstance(value, list):
        for block in value:
            if isinstance(block, dict) and block.get('type') == 'text':
                found = _structured(block.get('text'), depth + 1)
                if found is not None:
                    return found
        return None
    if not isinstance(value, dict) or value.get('isError') is True:
        return None
    for key in ('structuredContent', 'structured_content'):
        if isinstance(value.get(key), dict):
            return value[key]
    if 'server' in value and 'session_id' in value:
        return value
    return None


def _texts(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [b['text'] for b in value if isinstance(b, dict) and b.get('type') == 'text' and isinstance(b.get('text'), str)]
    return []


def _paths(tool, fields, payload, content):
    """Return [(format, path-string)] for one successful export result."""
    found = []
    if payload is not None:
        for field, fmt in fields:
            value = payload.get(field)
            path = value.get('path') if isinstance(value, dict) else value
            if isinstance(path, str) and path:
                fmt = fmt or payload.get('format')
                if field == 'curation_file' and payload.get('format'):
                    fmt = f"{payload['format']}-curation"
                found.append((str(fmt), path))
    if not found and tool == 'export_network':
        for text in _texts(content):
            match = NEKO_TEXT.match(text)
            if match:
                found.append((match[1].lower(), match[2]))
                break
    return found


def transcript_exports(transcript: Path, specialist: str) -> list[dict]:
    """Successful export results of this specialist's own server, in transcript order."""
    _, prefix, tools = EXPORT_TOOLS[specialist]
    name = re.compile(r'\Amcp__' + prefix + r'(?:-agent|_agent)?__(.+)\Z')
    reject_symlinks(Path(transcript))
    calls, found = {}, []
    # JSONL records end at '\n'; str.splitlines() would also split on U+0085/U+2028.
    for line in Path(transcript).read_text(encoding='utf-8').split('\n'):
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError('transcript events must be objects')
        message = event.get('message', {})
        content = message.get('content', []) if isinstance(message, dict) else []
        blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
        results = [b for b in blocks if b.get('type') == 'tool_result']
        for block in blocks:
            match = name.match(block.get('name', '') or '')
            if block.get('type') == 'tool_use' and match and match[1] in tools and isinstance(block.get('id'), str):
                calls[block['id']] = match[1]
            elif block.get('type') == 'tool_result' and block.get('tool_use_id') in calls and block.get('is_error') is not True:
                tool = calls[block['tool_use_id']]
                payload = _structured(block.get('content'))
                if payload is None and len(results) == 1:
                    payload = _structured(event.get('toolUseResult'))
                if isinstance(payload, dict) and payload.get('isError') is True:
                    continue
                for fmt, path in _paths(tool, tools[tool], payload, block.get('content')):
                    found.append({'tool': tool, 'format': fmt, 'source_path': path})
    return found


def _check_source(path: str, session_dir: Path) -> tuple[str | None, Path | None]:
    """Return (refusal reason or None, path)."""
    candidate = Path(path)
    if not candidate.is_absolute():
        return 'not an absolute path', None
    if '..' in candidate.parts:
        return 'path contains ..', None
    try:
        relative = candidate.relative_to(session_dir)
    except ValueError:
        return f'outside the server session artifact directory {session_dir}', None
    if not relative.parts:
        return 'not a file', None
    try:
        reject_symlinks(candidate)
    except ValueError:
        return 'path contains a symlink', None
    if os.path.lexists(candidate) and not candidate.is_file():
        return 'not a regular file', None
    return None, candidate


def capture_exports(project: Path, specialist: str, session: str, invocation: str, transcript: Path) -> dict | None:
    """Copy this invocation's exports; None when the specialist is excluded."""
    if specialist not in EXPORT_TOOLS:
        return None
    validate_session_id(session)
    validate_session_id(invocation)
    project = Path(project).resolve(strict=True)
    server, _, _ = EXPORT_TOOLS[specialist]
    session_dir = artifact_root().absolute() / server / session
    target = project / 'runs' / specialist / session / 'exports' / invocation
    relative_target = target.relative_to(project).as_posix()
    # Later results for the same file supersede earlier ones (the file holds the last write).
    latest = {}
    for item in transcript_exports(transcript, specialist):
        latest.pop(item['source_path'], None)
        latest[item['source_path']] = item
    rows, payloads, names = [], {}, {}
    for item in latest.values():
        reason, source = _check_source(item['source_path'], session_dir)
        if reason is None and source.name in names and names[source.name] != item['source_path']:
            reason = f'file name collides with {names[source.name]}'
        if reason is not None:
            rows.append({**item, 'rejected': True, 'reason': reason})
            continue
        names[source.name] = item['source_path']
        if not source.is_file():
            rows.append({**item, 'missing': True})
            continue
        content = source.read_bytes()
        rows.append({**item, 'dest_path': f'{relative_target}/{source.name}',
                     'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)})
        payloads[source.name] = content
    summary = {'path': None, 'copied': [r for r in rows if 'sha256' in r],
               'missing': [r for r in rows if r.get('missing')], 'rejected': [r for r in rows if r.get('rejected')]}
    if not rows:
        return summary
    reject_symlinks(target)
    if os.path.lexists(target):
        rows = _reuse_existing(target, rows, payloads)
        summary.update(copied=[r for r in rows if 'sha256' in r], missing=[r for r in rows if r.get('missing')])
    manifest = {'specialist': specialist, 'session_id': session, 'invocation_id': invocation, 'exports': rows}
    encoded = (json.dumps(manifest, indent=2) + '\n').encode('utf-8')
    summary['path'] = relative_target
    if os.path.lexists(target):
        existing = target / MANIFEST
        reject_symlinks(existing)
        if not existing.is_file() or existing.read_bytes() != encoded:
            raise ValueError(f'{relative_target}/{MANIFEST} differs from this capture; refusing overwrite')
        return summary
    with staged_capture(project, target) as stage:
        for file_name, content in payloads.items():
            (stage / file_name).write_bytes(content)
        (stage / MANIFEST).write_bytes(encoded)
    return summary


def _reuse_existing(target: Path, rows: list, payloads: dict) -> list:
    """Verify an earlier capture byte for byte; keep its copies when sources have since vanished."""
    manifest = target / MANIFEST
    reject_symlinks(manifest)
    try:
        previous = {row['source_path']: row for row in json.loads(manifest.read_text(encoding='utf-8'))['exports']}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f'existing {manifest} is unreadable ({error}); refusing overwrite') from error
    merged = []
    for row in rows:
        old = previous.get(row['source_path'])
        if row.get('missing') and old and 'sha256' in old:
            row = old  # verified below like any copied row
        if 'sha256' in row:
            dest = target / Path(row['dest_path']).name
            reject_symlinks(dest)
            if not dest.is_file() or hashlib.sha256(dest.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError(f'existing export {dest.name} differs from the server file; refusing overwrite')
            payloads.pop(dest.name, None)
        merged.append(row)
    return merged

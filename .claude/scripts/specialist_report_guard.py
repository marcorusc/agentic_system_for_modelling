#!/usr/bin/env python3
"""Agent-scoped Write guard for immutable specialist reports.

Configure with the fixed specialist name in the agent's PreToolUse hook. Session
identity must occur in the current invocation's MCP tool arguments/results (or be
explicitly bound using --session-id); report prose alone cannot authorize a path.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.capture.artifact_capture import reject_symlinks
from scripts.capture.index import SPECIALISTS
from scripts.codex.launcher_config import validate_session_id

PREFIXES = {'network-curator': 'neko', 'boolean-dynamics-modeler': 'maboss',
            'multicellular-configurator': 'physicell', 'ode-modeler': 'biomass'}

def transcript_sessions(path, specialist):
    """Bind current-session fields, never listed sessions or artifact lineage.

    Only matched role MCP calls count. Input session_id is top-level; results
    may unwrap MCP content/text/structuredContent but never arbitrary nested
    objects such as source_manifest, lineage, artifacts, or sessions arrays.
    """
    sessions, calls = set(), {}
    prefix = PREFIXES[specialist]
    def direct(value):
        server = value.get('server')
        if server is not None and str(server).lower() not in {prefix, prefix + '-agent', prefix + '_agent'}:
            return
        session = value.get('session_id')
        if session is not None:
            sessions.add(validate_session_id(session))
    def result(value, tool):
        if isinstance(value, str):
            try:
                result(json.loads(value), tool)
            except (json.JSONDecodeError, RecursionError):
                # Exact server return formats, tied to the creation operation;
                # UUID-looking text, paths and unrelated IDs are never scanned.
                pattern = None
                if tool == 'create_session':
                    pattern = r'^Session created: ([A-Za-z0-9][A-Za-z0-9._-]*)(?: \([^\n]*\))?\s*$'
                elif tool == 'create_network':
                    pattern = r'^Network created(?:: session=| \(session=)([A-Za-z0-9][A-Za-z0-9._-]*)(?:[ )]|$)'
                match = re.match(pattern, value) if pattern else None
                if match:
                    sessions.add(validate_session_id(match[1]))
        elif isinstance(value, dict):
            if value.get('isError') is True:
                return
            direct(value)
            for key in ('structuredContent', 'content', 'text'):
                if key in value:
                    wrapped = value[key]
                    if isinstance(wrapped, list):
                        for block in wrapped:
                            if isinstance(block, dict) and block.get('type') == 'text':
                                result(block.get('text'), tool)
                    else:
                        result(wrapped, tool)
        elif isinstance(value, list):
            for block in value:
                if isinstance(block, dict) and block.get('type') == 'text':
                    result(block.get('text'), tool)
    reject_symlinks(Path(path))
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError('transcript events must be objects')
        content = event.get('message', {}).get('content', [])
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                raise ValueError('transcript blocks must be objects')
            match = re.match(r'^mcp__' + prefix + r'(?:-agent|_agent)?__(.+)$', block.get('name', ''))
            if block.get('type') == 'tool_use' and match:
                identity = block.get('id')
                if not isinstance(identity, str) or not identity:
                    raise ValueError('MCP call requires an explicit tool use ID')
                calls[identity] = match[1]
                if isinstance(block.get('input'), dict):
                    direct(block['input'])
            elif block.get('type') == 'tool_result' and block.get('tool_use_id') in calls and block.get('is_error') is not True:
                result(block.get('content'), calls[block['tool_use_id']])
    return sessions

def validate(payload, project, specialist, expected_session=None):
    if specialist not in SPECIALISTS or payload.get('tool_name') != 'Write':
        raise ValueError('expected an agent-scoped specialist Write')
    request = payload.get('tool_input', {})
    path = Path(request.get('file_path', ''))
    if not path.is_absolute(): raise ValueError('report path must be absolute')
    reject_symlinks(path)
    relative = path.relative_to(project)
    if '..' in relative.parts or path.absolute() != path.resolve(strict=False):
        raise ValueError('report path must be canonical')
    if len(relative.parts) != 4 or relative.parts[:2] != ('runs', specialist) or relative.name != 'report.md':
        raise ValueError('only runs/<this specialist>/<session>/report.md is writable')
    session = validate_session_id(relative.parts[2])
    if expected_session:
        expected_session = validate_session_id(expected_session)
        if session != expected_session: raise ValueError('report session disagrees with invocation binding')
    elif session not in transcript_sessions(payload['transcript_path'], specialist):
        raise ValueError('report session is absent from this invocation MCP record')
    content = request.get('content')
    if not isinstance(content, str) or not content.strip(): raise ValueError('empty report')
    if path.exists(): raise ValueError('report is immutable; return subsequent reports in invocation output')
    path.parent.mkdir(parents=True, exist_ok=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('specialist', choices=sorted(SPECIALISTS))
    parser.add_argument('--session-id')
    args = parser.parse_args()
    try:
        project = Path(os.environ['CLAUDE_PROJECT_DIR']).resolve(strict=True)
        validate(json.load(sys.stdin), project, args.specialist, args.session_id)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'specialist report guard: {error}', file=sys.stderr); return 2
    return 0
if __name__ == '__main__': raise SystemExit(main())

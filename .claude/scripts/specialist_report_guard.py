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
    """Read explicit session_id values only from this specialist's MCP blocks."""
    sessions = set()
    call_ids = set()
    def collect(value):
        if isinstance(value, dict):
            if value.get('server') and str(value['server']).lower() != PREFIXES[specialist]:
                return
            for key, item in value.items():
                if key == 'session_id' and isinstance(item, str):
                    sessions.add(item)
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value: collect(item)
        elif isinstance(value, str):
            try: collect(json.loads(value))
            except (ValueError, RecursionError): pass
    prefix = PREFIXES[specialist]
    for line in Path(path).read_text().splitlines():
        event = json.loads(line)
        for block in event.get('message', {}).get('content', []) if isinstance(event.get('message', {}).get('content'), list) else []:
            if block.get('type') == 'tool_use' and re.match(r'^mcp__' + prefix + r'(?:-agent|_agent)?__', block.get('name', '')):
                call_ids.add(block.get('id')); collect(block.get('input'))
            elif block.get('type') == 'tool_result' and block.get('tool_use_id') in call_ids:
                collect(block.get('content'))
    return sessions

def validate(payload, project, specialist, expected_session=None):
    if specialist not in SPECIALISTS or payload.get('tool_name') != 'Write':
        raise ValueError('expected an agent-scoped specialist Write')
    request = payload.get('tool_input', {})
    path = Path(request.get('file_path', ''))
    if not path.is_absolute(): raise ValueError('report path must be absolute')
    reject_symlinks(path)
    relative = path.relative_to(project)
    if len(relative.parts) != 4 or relative.parts[:2] != ('runs', specialist) or relative.name != 'report.md':
        raise ValueError('only runs/<this specialist>/<session>/report.md is writable')
    session = validate_session_id(relative.parts[2])
    if expected_session:
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

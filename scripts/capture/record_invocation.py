#!/usr/bin/env python3
"""Persist a Claude SubagentStop transcript and measured usage without fabrication.

Session-bound invocations are registered in runs/index.json. Attempts without a
scientific session are preserved separately as technical records, never handoffs.
Ambiguous sessions fail closed and preserve the original Claude transcript.
"""
from __future__ import annotations
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.capture.artifact_capture import staged_capture, reject_symlinks
from scripts.capture.index import register_capture, SPECIALISTS
from scripts.codex.launcher_config import validate_session_id
from scripts.codex.launcher_process import sanitize_json_value

def session_ids(path, specialist):
    spec = importlib.util.spec_from_file_location('report_guard', Path(__file__).resolve().parents[2] / '.claude/scripts/specialist_report_guard.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.transcript_sessions(path, specialist)

def publish_invocation(project, target, files):
    """Permit identical hook retries, including recovery after an index failure."""
    try:
        with staged_capture(project, target) as stage:
            for name, content in files.items():
                (stage / name).write_bytes(content)
    except ValueError:
        # Publication is serialized by staged_capture. A concurrent identical
        # recorder can win the race; verify every byte before accepting its copy.
        reject_symlinks(target)
        if not target.is_dir():
            raise
        if {path.name for path in target.iterdir()} != set(files):
            raise ValueError('existing invocation artifacts differ; refusing overwrite')
        for name, content in files.items():
            path = target / name
            reject_symlinks(path)
            if not path.is_file() or path.read_bytes() != content:
                raise ValueError('existing invocation content changed; refusing overwrite')

def record(project, payload):
    if not isinstance(payload, dict): raise ValueError('hook payload must be an object')
    project = project.resolve(strict=True)
    specialist = payload.get('agent_type')
    if specialist not in SPECIALISTS:
        return {'status': 'ignored', 'reason': 'not a modelling specialist'}
    invocation = validate_session_id(payload['agent_id'])
    transcript = Path(payload['agent_transcript_path'])
    reject_symlinks(transcript)
    raw = transcript.read_bytes()
    events = [sanitize_json_value(json.loads(line)) for line in raw.splitlines() if line.strip()]
    sessions = session_ids(transcript, specialist)
    if transcript.read_bytes() != raw:
        raise ValueError('transcript changed while recording; preserve source and retry explicitly')
    if len(sessions) > 1:
        raise ValueError('invocation must identify exactly one scientific session; record manually with reviewed attribution')
    session = validate_session_id(sessions.pop()) if sessions else None
    if session is None:
        target = project / 'runs/orchestrator/unbound-invocations' / specialist / invocation
    else:
        target = project / 'runs' / specialist / session / 'invocation' / invocation
    calls, prompts, final, usage_rows, timestamps = [], [], [], {}, []
    for event in events:
        if not isinstance(event, dict): raise ValueError('transcript events must be objects')
        if event.get('timestamp'):
            time = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            if time.tzinfo is None: raise ValueError('transcript timestamp lacks timezone')
            timestamps.append(time)
        message = event.get('message', {})
        if not isinstance(message, dict): raise ValueError('transcript message must be an object')
        content = message.get('content', [])
        if event.get('type') == 'user' and isinstance(content, str): prompts.append(content)
        if message.get('usage') and message.get('id'):
            usage_rows[message['id']] = message['usage']
        if isinstance(content, list):
            text = []
            for block in content:
                if not isinstance(block, dict): raise ValueError('transcript blocks must be objects')
                if block.get('type') in {'tool_use', 'tool_result'}: calls.append(block)
                elif block.get('type') == 'text': text.append(block.get('text', ''))
            if event.get('type') == 'assistant' and text: final = text
            if event.get('type') == 'user' and text: prompts.extend(text)
    def total(key):
        values = [row.get(key) for row in usage_rows.values()]
        return sum(values) if values and all(type(v) is int and v >= 0 for v in values) else None
    usage = {'input_tokens': total('input_tokens'), 'output_tokens': total('output_tokens'),
             'cache_creation_input_tokens': total('cache_creation_input_tokens'),
             'cache_read_input_tokens': total('cache_read_input_tokens'),
             'tool_calls': len({c['id'] for c in calls if c['type'] == 'tool_use' and isinstance(c.get('id'), str)}),
             'wall_time_seconds': (max(timestamps)-min(timestamps)).total_seconds() if len(timestamps)>1 else None,
             'cost_usd': None, 'source': 'Claude agent transcript; elapsed timestamps, deduplicated message usage'}
    metadata = {'specialist': specialist, 'session_id': session,
        'invocation_id': invocation, 'source_transcript_sha256': hashlib.sha256(raw).hexdigest(),
        'credentials_redacted': True, 'usage': usage}
    if session is None:
        metadata.update(record_type='unbound-invocation', scientific_status='unresolved')
    files = {
        'transcript.jsonl': ''.join(json.dumps(event) + '\n' for event in events),
        'task.txt': '\n\n'.join(prompts) + '\n',
        'tool_calls.json': json.dumps(calls, indent=2) + '\n',
        'final_report.md': '\n\n'.join(final) + '\n',
        'invocation.json': json.dumps(metadata, indent=2) + '\n',
    }
    publish_invocation(project, target, {name: content.encode('utf-8') for name, content in files.items()})
    if session is None:
        return {'status': 'unbound', 'session_id': None,
                'invocation_path': target.relative_to(project).as_posix(),
                'systemMessage': 'Specialist attempt preserved without a scientific session. '
                                 'This technical record cannot authorize stage advancement.'}
    return register_capture(project, target, usage=usage)

def main():
    payload = None
    try:
        payload = json.load(sys.stdin)
        project = Path(os.environ['CLAUDE_PROJECT_DIR']).resolve(strict=True)
        print(json.dumps(record(project, payload), indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        message = f'invocation recording failed: {error}. Preserve the original Claude transcript; '
        message += 'recording requires repair before stage advancement.'
        print(message, file=sys.stderr)
        if isinstance(payload, dict) and payload.get('stop_hook_active') is True:
            # Exit 2 asks Claude to continue. Never trap a failed recorder in a
            # stop loop; an operational stop does not certify scientific success.
            print(json.dumps({'systemMessage': message}))
            return 0
        return 2
    return 0
if __name__ == '__main__': raise SystemExit(main())

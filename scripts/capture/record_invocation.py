#!/usr/bin/env python3
"""Persist a Claude SubagentStop transcript and measured usage without fabrication.

Each invocation is immutable and registered in runs/index.json. Hook payload must
identify agent_type, agent_id and agent_transcript_path; ambiguous model sessions
fail closed and preserve the original transcript in Claude's own storage.
"""
from __future__ import annotations
import argparse
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

def record(project, payload):
    specialist = payload.get('agent_type')
    if specialist not in SPECIALISTS:
        return {'status': 'ignored', 'reason': 'not a modelling specialist'}
    invocation = validate_session_id(payload['agent_id'])
    transcript = Path(payload['agent_transcript_path'])
    reject_symlinks(transcript)
    raw = transcript.read_bytes()
    events = [sanitize_json_value(json.loads(line)) for line in raw.splitlines() if line.strip()]
    sessions = session_ids(transcript, specialist)
    if len(sessions) != 1:
        raise ValueError('invocation must identify exactly one scientific session; record manually with reviewed attribution')
    session = validate_session_id(sessions.pop())
    target = project / 'runs' / specialist / session / 'invocation' / invocation
    calls, prompts, final, usage_rows, timestamps = [], [], [], {}, []
    for event in events:
        if event.get('timestamp'):
            time = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            if time.tzinfo is None: raise ValueError('transcript timestamp lacks timezone')
            timestamps.append(time)
        message = event.get('message', {})
        content = message.get('content', [])
        if event.get('type') == 'user' and isinstance(content, str): prompts.append(content)
        if message.get('usage') and message.get('id'):
            usage_rows[message['id']] = message['usage']
        if isinstance(content, list):
            text = []
            for block in content:
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
             'tool_calls': sum(c['type'] == 'tool_use' for c in calls),
             'wall_time_seconds': (max(timestamps)-min(timestamps)).total_seconds() if len(timestamps)>1 else None,
             'cost_usd': None, 'source': 'Claude agent transcript; elapsed timestamps, deduplicated message usage'}
    with staged_capture(project, target) as stage:
        (stage / 'transcript.jsonl').write_text(''.join(json.dumps(event) + '\n' for event in events))
        (stage / 'task.txt').write_text('\n\n'.join(prompts) + '\n')
        (stage / 'tool_calls.json').write_text(json.dumps(calls, indent=2) + '\n')
        (stage / 'final_report.md').write_text('\n\n'.join(final) + '\n')
        (stage / 'invocation.json').write_text(json.dumps({'specialist': specialist, 'session_id': session,
            'invocation_id': invocation, 'source_transcript_sha256': hashlib.sha256(raw).hexdigest(), 'credentials_redacted': True, 'usage': usage}, indent=2) + '\n')
    return register_capture(project, target, usage=usage)

def main():
    try:
        project = Path(os.environ['CLAUDE_PROJECT_DIR']).resolve(strict=True)
        print(json.dumps(record(project, json.load(sys.stdin)), indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'invocation recording failed: {error}', file=sys.stderr); return 2
    return 0
if __name__ == '__main__': raise SystemExit(main())

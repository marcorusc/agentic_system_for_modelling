#!/usr/bin/env python3
"""Generate a benchmark usage table from verified recorded invocation measurements."""
import argparse
import json
from pathlib import Path

def render(index):
    rows = ['| Specialist | Session | Invocation | Input tokens | Output tokens | Tool calls | Seconds | Cost USD |',
            '|---|---|---|---:|---:|---:|---:|---:|']
    for run in index.get('runs', []):
        if '/invocation/' not in run.get('capture_path', '') and '/specialist-invocations/' not in run.get('capture_path', ''):
            continue
        usage = run.get('usage', {})
        values = [run['specialist'], run['session_id'], Path(run['capture_path']).name]
        values.extend('unavailable' if usage.get(key) is None else str(usage[key]) for key in
                      ('input_tokens', 'output_tokens', 'tool_calls', 'wall_time_seconds', 'cost_usd'))
        rows.append('| ' + ' | '.join(values) + ' |')
    return '\n'.join(rows) + '\n'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('index', type=Path)
    args = parser.parse_args()
    print(render(json.loads(args.index.read_text())), end='')
if __name__ == '__main__': main()

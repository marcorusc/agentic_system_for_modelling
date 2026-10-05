"""Usage from recorded Codex execution events; missing measurements remain null."""
import json
import math
from pathlib import Path

TOOL_ITEMS = {'mcp_tool_call', 'command_execution', 'web_search', 'file_change'}

def usage_summary(directory: Path, provenance: dict):
    events_path = directory / 'events.jsonl'
    turns, tool_ids = [], set()
    has_stream = events_path.is_file()
    if has_stream:
        for line in events_path.read_text().splitlines():
            if not line.strip(): continue
            event = json.loads(line)
            if event.get('type') == 'turn.completed' and isinstance(event.get('usage'), dict):
                turns.append(event['usage'])
            item = event.get('item', {})
            if isinstance(item, dict) and item.get('type') in TOOL_ITEMS and isinstance(item.get('id'), str):
                tool_ids.add(item['id'])
    def total(key):
        values = [turn.get(key) for turn in turns]
        return sum(values) if values and all(type(v) is int and v >= 0 for v in values) else None
    elapsed = provenance.get('process_elapsed_seconds')
    if elapsed is not None and (type(elapsed) not in {float, int} or not math.isfinite(elapsed) or elapsed < 0):
        raise ValueError('invalid measured process elapsed seconds')
    return {'input_tokens': total('input_tokens'), 'output_tokens': total('output_tokens'),
            'cached_input_tokens': total('cached_input_tokens'),
            'tool_calls': len(tool_ids) if has_stream else None,
            'wall_time_seconds': elapsed, 'cost_usd': None,
            'source': 'Codex sanitized events.jsonl turn.completed usage and unique tool item IDs; measured process elapsed time'}

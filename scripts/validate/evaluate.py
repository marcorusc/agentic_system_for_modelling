#!/usr/bin/env python3
"""Evaluate declared artifact criteria; print results without changing model state.

Usage: python scripts/validate/evaluate.py --criteria VALIDATION_CRITERIA.yaml
The criteria file uses JSON-compatible YAML: {"schema_version":1,"criteria":[
{"criterion_id":"...","method":"ordered_peaks|canonical_cycles|boolean_structure",
 "inputs":["runs/.../artifact"],"options":{...}}]}. Thresholds, nodes, initial
states and expectations must be supplied explicitly from researcher-approved
criteria. Each trajectory is evaluated separately; a criterion passes only if all
its declared inputs pass. No statistical pooling or implicit tolerance is applied.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.validate.common import artifact, load_json_yaml, load_series
from scripts.validate.validate_cycles import ordered_peaks, classify_cycles
from scripts.validate.boolean_structure import analyze


def evaluate(root: Path, criteria_path: str) -> dict:
    path, provenance = artifact(root, criteria_path)
    config = load_json_yaml(path)
    if set(config) != {'schema_version', 'criteria'} or config['schema_version'] != 1 or not isinstance(config['criteria'], list):
        raise ValueError('criteria requires schema_version=1 and a criteria array')
    results, identifiers = [], set()
    for item in config['criteria']:
        if not isinstance(item, dict) or set(item) != {'criterion_id', 'method', 'inputs', 'options'}:
            raise ValueError('criterion requires criterion_id, method, inputs, options')
        identity = item['criterion_id']
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', identity) or identity in identifiers:
            raise ValueError('criterion IDs must be unique safe identifiers')
        identifiers.add(identity)
        if not isinstance(item['inputs'], list) or not item['inputs'] or len(set(item['inputs'])) != len(item['inputs']):
            raise ValueError('criterion requires distinct nonempty inputs')
        if not isinstance(item['options'], dict):
            raise ValueError('criterion options must be an object')
        result = {'criterion_id': identity, 'status': 'incomplete', 'method': item['method'], 'inputs': [], 'metrics': {}}
        try:
            passed = []
            for value in item['inputs']:
                source, entry = artifact(root, value)
                result['inputs'].append(entry)
                if item['method'] == 'boolean_structure':
                    ok, metrics = analyze(source, item['options'])
                else:
                    times, series = load_series(source)
                    if item['method'] == 'ordered_peaks':
                        ok, metrics = ordered_peaks(times, series, item['options'])
                    elif item['method'] == 'canonical_cycles':
                        ok, metrics = classify_cycles(times, series, item['options'])
                    else:
                        raise ValueError('unknown criterion method')
                passed.append(ok); result['metrics'][value] = metrics
            result['status'] = 'passed' if all(passed) else 'failed'
        except (ValueError, OSError, KeyError, TypeError, RecursionError) as error:
            result['error'] = str(error)
        results.append(result)
    return {'schema_version': 1, 'kind': 'artifact_validation', 'algorithm_version': '1', 'criteria': provenance, 'results': results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--criteria', required=True)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.project_root, args.criteria)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if all(r['status'] == 'passed' for r in report['results']) else 1


if __name__ == '__main__':
    raise SystemExit(main())

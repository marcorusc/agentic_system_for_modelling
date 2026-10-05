#!/usr/bin/env python3
"""Propose time scaling from explicit phase mappings; never approve a parameter.

Config is JSON-compatible YAML with schema_version=1, inputs=[relative CSV paths],
threshold, sample_count=1, target_duration, target_unit, source_time_unit, and
phases=[{name,node,on},...]. Mapping order, threshold and target are explicit.
The emulation takes at most one immediate phase exit per sampled tick and starts
in phase 0. A division occurs when the last phase exits. First partial cycle and
last incomplete cycle are excluded. Output scaling is target units per source
unit, so MaBoSS elapsed time = physical elapsed time / scaling. This is not a
PhysiBoSS simulation and does not incorporate finite transition rates or noise.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.validate.common import artifact, load_json_yaml, load_series, number


def propose(root: Path, config_path: str):
    path, provenance = artifact(root, config_path)
    config = load_json_yaml(path)
    if type(config.get('schema_version')) is not int or config.get('schema_version') != 1 or type(config.get('sample_count')) is not int or config['sample_count'] != 1:
        raise ValueError('calibration requires schema_version=1 and sample_count=1')
    threshold = number(config['threshold'], 'threshold')
    if not 0 < threshold <= 1:
        raise ValueError('threshold must lie in (0,1]')
    target = number(config['target_duration'], 'target_duration', positive=True)
    for field in ('target_unit', 'source_time_unit'):
        if not isinstance(config[field], str) or not config[field].strip():
            raise ValueError(f'{field} must be explicitly declared')
    phases = config['phases']
    if (not isinstance(phases, list) or len(phases) < 2 or any(not isinstance(p, dict) or set(p) != {'name', 'node', 'on'} or type(p['on']) is not bool or not isinstance(p['node'], str) or not p['node'] or not isinstance(p['name'], str) or not p['name'] for p in phases)
            or len({p['name'] for p in phases}) != len(phases)):
        raise ValueError('phases requires distinct named {name,node,on:boolean} mappings')
    if not isinstance(config['inputs'], list) or not config['inputs'] or len(set(config['inputs'])) != len(config['inputs']):
        raise ValueError('distinct nonempty input trajectories are required')
    inputs, trajectories, cycles, dwell = [], [], [], {p['name']: [] for p in phases}
    for value in config['inputs']:
        source, meta = artifact(root, value); inputs.append(meta)
        times, series = load_series(source)
        phase, entered, previous_division, observed = 0, times[0], None, []
        for i, time in enumerate(times):
            mapping = phases[phase]
            if (series[mapping['node']][i] >= threshold) == mapping['on']:
                dwell[mapping['name']].append(time - entered)
                if phase == len(phases) - 1:
                    if previous_division is not None: observed.append(time - previous_division)
                    previous_division = time
                phase, entered = (phase + 1) % len(phases), time
        cycles.extend(observed)
        trajectories.append({'path': value, 'complete_cycle_durations': observed})
    complete_inputs = all(item['complete_cycle_durations'] for item in trajectories)
    mean = statistics.mean(cycles) if cycles else None
    scaling = target / mean if mean and complete_inputs else None
    if scaling is not None:
        number(scaling, 'scaling', positive=True)
    return {'schema_version': 1, 'kind': 'calibration_proposal', 'status': 'proposed' if scaling is not None else 'incomplete',
            'configuration': provenance, 'inputs': inputs, 'trajectories': trajectories,
            'mean_cycle_duration': mean, 'source_time_unit': config['source_time_unit'],
            'target_duration': target, 'target_unit': config['target_unit'],
            'scaling': scaling,
            'all_inputs_have_complete_cycles': complete_inputs,
            'sample_count_source': 'researcher-declared configuration; not verifiable from CSV alone',
            'phase_dwell_mean': {name: statistics.mean(values) if values else None for name, values in dwell.items()},
            'requires_researcher_approval': True,
            'limitations': ['Immediate transitions, at most one exit per tick; phase-0 start.', 'Tick-averaged thresholding; finite rates and stochastic update intervals are not emulated.', 'Phase dwell means include boundary partial phase observations.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    try: result = propose(args.project_root, args.config)
    except (ValueError, OSError, KeyError, TypeError) as error: parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result['status'] == 'proposed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Cross-scenario readout contrast over saved trajectory artifacts (read-only).

A perturbation's readout drop is P(control) - P(perturbed). The criterion asks
whether the drop in a test context exceeds the drop in a reference context by
more than an explicit margin: test_drop - reference_drop > margin (strict).
Inputs are four trajectories in fixed role order. Readout statistics are the
final value or the mean of an explicit number of final points. No statistical
test, pooling or implicit tolerance is applied; the margin is researcher-approved.
"""
from __future__ import annotations
from scripts.validate.common import number

ROLES = ('test_control', 'test_perturbed', 'reference_control', 'reference_perturbed')
OPTIONS = {'readouts', 'margin', 'combine', 'statistic', 'tail_points'}


def _statistic(values: list[float], options: dict) -> float:
    if options['statistic'] == 'final':
        return values[-1]
    tail = values[-options['tail_points']:]
    return sum(tail) / len(tail)


def contrast(trajectories: list[dict[str, list[float]]], options: dict) -> tuple[bool, dict]:
    if len(trajectories) != len(ROLES):
        raise ValueError(f'scenario_contrast requires exactly four inputs in order: {", ".join(ROLES)}')
    if set(options) - OPTIONS or not {'readouts', 'margin', 'combine', 'statistic'} <= set(options):
        raise ValueError('scenario_contrast options are readouts, margin, combine, statistic and optional tail_points')
    readouts = options['readouts']
    if not isinstance(readouts, list) or not readouts or len(set(readouts)) != len(readouts) \
            or any(not isinstance(r, str) or not r for r in readouts):
        raise ValueError('readouts must be a nonempty list of distinct node names')
    margin = number(options['margin'], 'margin')
    if margin < 0:
        raise ValueError('margin must be nonnegative')
    if options['combine'] not in ('all', 'any'):
        raise ValueError('combine must be "all" or "any"')
    if options['statistic'] == 'final':
        if 'tail_points' in options:
            raise ValueError('tail_points applies only to statistic "tail_mean"')
    elif options['statistic'] == 'tail_mean':
        points = options.get('tail_points')
        if type(points) is not int or points < 1:
            raise ValueError('tail_mean requires a positive integer tail_points')
        if any(points > len(values) for series in trajectories for values in series.values()):
            raise ValueError('tail_points exceeds trajectory length')
    else:
        raise ValueError('statistic must be "final" or "tail_mean"')
    rows = {}
    for readout in readouts:
        if any(readout not in series for series in trajectories):
            raise ValueError(f'readout {readout!r} is missing from an input trajectory')
        values = dict(zip(ROLES, (_statistic(series[readout], options) for series in trajectories)))
        test_drop = values['test_control'] - values['test_perturbed']
        reference_drop = values['reference_control'] - values['reference_perturbed']
        difference = test_drop - reference_drop
        rows[readout] = {**values, 'test_drop': test_drop, 'reference_drop': reference_drop,
                         'difference': difference, 'passed': difference > margin}
    outcomes = [row['passed'] for row in rows.values()]
    passed = all(outcomes) if options['combine'] == 'all' else any(outcomes)
    return passed, {'input_roles': list(ROLES), 'margin': margin, 'combine': options['combine'],
                    'statistic': options['statistic'], 'readouts': rows}

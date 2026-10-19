"""Tick-averaged trajectory metrics promoted from the archived benchmark.

No node names or scientific thresholds are implicit. `canonical-v1` reproduces
its classifier: ON means value >= threshold; first observed ON in the interval
(including the onset tick) is ordered non-strictly; APC status is checked at the
previous mitotic offset or its immediately preceding tick. This is a discretized
classifier, not a claim about sub-tick transition order or biological validity.
"""
from __future__ import annotations
from scripts.validate.common import number


def first_peak(times, values, drop):
    number(drop, 'drop', positive=True)
    pending = None
    height = None
    for i in range(1, len(values)):
        value = values[i]
        if pending is not None:
            if value > height:
                pending = None
            elif height - value > drop:
                return times[pending]
        # The earliest pending peak dominates every equal or lower candidate:
        # any drop qualifying those also qualifies this peak. A strictly higher
        # sample invalidates it and every intervening lower candidate together.
        if pending is None and i < len(values) - 1 and value >= values[i - 1] and value > values[i + 1]:
            pending, height = i, value
    return None


def half_max_time(times, values, fraction):
    number(fraction, 'fraction', positive=True)
    if fraction > 1:
        raise ValueError('fraction must be <= 1')
    maximum = max(values)
    return next((t for t, v in zip(times, values) if maximum > 0 and v >= fraction * maximum), None)


def ordered_peaks(times, series, options):
    nodes = options['nodes']
    if not isinstance(nodes, list) or len(nodes) < 2 or len(set(nodes)) != len(nodes):
        raise ValueError('nodes must list at least two distinct outputs')
    comparators = options['comparators']
    if len(comparators) != len(nodes) - 1 or any(c not in ('<', '<=') for c in comparators):
        raise ValueError('one explicit < or <= comparator is required per adjacent node pair')
    metric = options['metric']
    if metric == 'first_peak':
        values = [first_peak(times, series[n], options['drop']) for n in nodes]
    elif metric == 'fraction_max':
        values = [half_max_time(times, series[n], options['fraction']) for n in nodes]
    else:
        raise ValueError('metric must be first_peak or fraction_max')
    passed = all(v is not None for v in values) and all(a < b if c == '<' else a <= b for a, b, c in zip(values, values[1:], comparators))
    return passed, {'times': dict(zip(nodes, values)), 'metric': metric}


def classify_cycles(times, series, options):
    threshold = number(options['threshold'], 'threshold')
    if not 0 < threshold <= 1:
        raise ValueError('threshold must lie in (0,1]')
    if options['sample_count'] != 1 or type(options['sample_count']) is not int:
        raise ValueError('canonical-v1 requires a single trajectory (sample_count=1)')
    order = options['activation_order']
    if len(order) != 3 or len(set(order)) != 3:
        raise ValueError('canonical-v1 requires three distinct ordered activation nodes')
    onset, reset = options['onset_node'], options['reset_node']
    on = {node: [v >= threshold for v in series[node]] for node in [*order, onset, reset]}
    events, last_off, reset_seen = [], 0, True
    for i in range(1, len(times)):
        if on[onset][i - 1] and not on[onset][i]:
            last_off, reset_seen = i, on[reset][i] or on[reset][i - 1]
        if not on[onset][i - 1] and on[onset][i]:
            starts = [next((j for j in range(last_off, i + 1) if on[n][j]), None) for n in order]
            if not reset_seen and events:
                kind = 'non_mitotic'
            elif starts[0] is None and starts[1] is None:
                kind = 'g1_skip'
            elif all(x is not None for x in starts) and starts == sorted(starts):
                kind = 'canonical'
            else:
                kind = 'out_of_order'
            events.append({'time': times[i], 'kind': kind})
    counts = {kind: sum(e['kind'] == kind for e in events) for kind in ('canonical', 'non_mitotic', 'g1_skip', 'out_of_order')}
    minimum = options['minimum_canonical']
    if type(minimum) is not int or minimum < 1:
        raise ValueError('minimum_canonical must be an explicitly positive integer')
    fraction = number(options['minimum_fraction'], 'minimum_fraction')
    if not 0 <= fraction <= 1:
        raise ValueError('minimum_fraction must lie in [0,1]')
    observed = counts['canonical'] / len(events) if events else 0
    return counts['canonical'] >= minimum and observed >= fraction, {'events': events, 'counts': counts, 'canonical_fraction': observed, 'classifier': 'canonical-v1'}


def replicate_seeds(sample_count: int, replicates: int, first_seed: int) -> list[int]:
    """Avoid overlapping seed+trajectory-index ranges; does not prove independence."""
    if any(type(v) is not int for v in (sample_count, replicates, first_seed)) or sample_count < 1 or replicates < 1 or first_seed < 0:
        raise ValueError('sample_count/replicates must be positive integers and first_seed nonnegative')
    if replicates > 10000 or first_seed + sample_count * replicates > 2**31:
        raise ValueError('seed plan exceeds bounded signed 32-bit range')
    return [first_seed + sample_count * i for i in range(replicates)]

# Artifact validation commands

These commands inspect saved artifacts only. They never call modelling servers,
change scientific state, approve a parameter, or execute a simulation. Record the
researcher's criterion choices before evaluation. Python's standard library is
sufficient. All configuration/input paths are relative to the project root;
`--project-root` supports disposable test projects.

## Declared criteria

Copy `templates/VALIDATION_CRITERIA.yaml` next to `VALIDATION_PLAN.md` when initializing
a model. The template deliberately contains no criteria. The supported YAML subset
is JSON syntax: quoted keys/strings, arrays and objects, no comments, aliases or
non-finite numbers. Each row in the validation plan references its `criterion_id`.

Run `python scripts/validate/evaluate.py --criteria VALIDATION_CRITERIA.yaml` and
save stdout through the orchestrator's authorized artifact capture. The report
contains the criteria digest, input digests, criterion IDs, metrics, and one of
`passed`, `failed`, `incomplete`. Missing inputs, malformed data, and resource-limit
failures are incomplete, never passing. Exit status is 1 if any criterion does
not pass. The empty template is rejected until explicit criteria are declared; it cannot pass vacuously.

Each `criteria` entry has exactly these fields:

```json
{
  "criterion_id": "V1",
  "method": "ordered_peaks",
  "inputs": ["runs/path/to/trajectory.nodes.csv"],
  "options": {}
}
```

The example is structural syntax only; fill in actual researcher-approved paths
and options. Multiple inputs are evaluated separately, and all must pass. A CSV
must have a `Time` column, unique node columns, strictly increasing nonnegative
times, finite values and probabilities in `[0,1]`.

Supported methods and required options:

| Method | Options |
|---|---|
| `ordered_peaks` | `nodes`: ordered distinct node names; `comparators`: `<` or `<=` for each adjacent pair; `metric`: `first_peak` with explicit positive `drop`, or `fraction_max` with `fraction` in `(0,1]` |
| `canonical_cycles` | `activation_order`: three distinct nodes; `onset_node`; `reset_node`; `threshold` in `(0,1]`; `sample_count`: 1; `minimum_canonical`: positive integer; `minimum_fraction` in `[0,1]` |
| `boolean_structure` | `analysis`: `fixed_points`, `reachable_attractors` or `readout_exclusivity`, or `reachable_readout_exclusivity`; explicit `max_states` in `[1,1000000]`; additional options below |

`first_peak` is the first local maximum followed by a drop **strictly greater**
than `drop` before any larger value. A plateau's last point is considered its
peak. The first sample and last sample cannot be peaks. `fraction_max` is the
first time at least `fraction * observed_maximum`; an all-zero trace has no time.
Missing peaks/times fail the ordering criterion.

`canonical_cycles` version `canonical-v1` preserves the archived benchmark
classifier, including non-strict ordering within a sampled tick. ON means value
at least the declared threshold. At each onset-node OFF→ON event, the classifier
looks for the first ON observation of each ordered activation node since the
last onset-node ON→OFF event (or the first sample). The three first observations
must occur in order, including the current tick. The reset node must have been ON
at the previous offset or its preceding tick for subsequent cycles. Categories
are `canonical`, `non_mitotic`, `g1_skip` and `out_of_order`. This cannot establish
sub-tick event order. The sample-count assertion is supplied from run provenance;
the CSV alone cannot prove it came from a single trajectory.

## Structural analysis

BNET rules use identifiers, `0`, `1`, `!`, `&`, `|` and parentheses. Unknown
regulators, duplicate targets and executable expressions are rejected. This tool
uses a dedicated parser, never `eval` or `exec`.

- `fixed_points` requires `expected_count` (nonnegative integer), enumerates all
  states and lists fixed points as ON-node lists.
- `reachable_attractors` requires `initial_state` assigning **every** node a JSON
  Boolean and `expected_count` (positive integer). It enumerates general
  asynchronous single-node updates and returns terminal strongly connected
  components. It does not compute stochastic occupancy or transition timing.
- `readout_exclusivity` requires `readout_nodes` containing at least two distinct
  known nodes. It checks that their **evaluated functions** are never simultaneously
  true over all states. This does not prove asynchronous readout-node values are
  exclusive during lagged updates. A failed proof includes a counterexample.

The implementation accepts 1–25 nodes and stops at the explicit state limit or
2,000,000 reachable edges. A stopped computation reports incomplete; it is not an
approximate proof.

## Replicate seed planning

`python scripts/validate/plan_seeds.py --sample-count N --replicates R --first-seed S`
prints starting seeds separated by `N`. This avoids overlapping ranges under the
observed engine convention `seed + trajectory index`. Verify that convention for
the engine version in use. Spacing is not a statistical-independence test, and the
output explicitly records `independence_verified: false`. No seed is selected
implicitly; the planned seeds still belong in the authorized simulation request.

## Time calibration proposal

`python scripts/validate/calibrate_cycle.py --config path/to/calibration.yaml`
accepts these explicit configuration fields:

- `schema_version`: 1; `inputs`: distinct single-trajectory CSV paths;
  `sample_count`: 1; `threshold` in `(0,1]`.
- `target_duration`: positive number; `target_unit` and `source_time_unit`:
  explicit nonempty unit strings. No unit conversion or unit inference occurs.
- `phases`: ordered `{ "name": "...", "node": "...", "on": true }`
  mappings; use `false` for an OFF-triggered exit. Names must be unique.

The emulator starts in phase 0, takes at most one immediate phase exit per tick,
and records division on exiting the final phase. It excludes the first partial
and final incomplete cycles. Scaling is `target_duration / mean_cycle_duration`,
in target units per source unit: MaBoSS elapsed time equals physical elapsed time
divided by scaling. Output is a **proposal requiring researcher approval**, or
`incomplete` with null scaling when any declared input has no complete cycles. It neither edits a
handoff nor simulates PhysiBoSS. Finite exit rates, stochastic update intervals
and sub-tick transitions are not modeled. Phase dwell summaries include boundary
phase observations and are reported separately from complete-cycle calibration.

`readout_exclusivity` checks rule functions and explicitly does not prove stored
asynchronous node exclusivity. Use `reachable_readout_exclusivity` with a full
`initial_state`, declared `readout_nodes`, and `max_states` to check actual node
values in all reachable asynchronous states, including the initial state. A resource
limit returns incomplete. Up to 25 nodes are supported within explicit state/edge bounds.

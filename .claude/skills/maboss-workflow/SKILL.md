---
name: maboss-workflow
description: "Operational guide for the MaBoSS MCP server — sessions, loading a BNET or NeKo handoff, inspecting nodes/rules/rates, restricting output nodes, summary readouts, running and analysing durable simulation runs, mutation studies, and debugging slow or hanging runs. Preloaded into the boolean-dynamics-modeler subagent; in the main session, delegate MaBoSS work to boolean-dynamics-modeler instead of loading this skill."
---

# MaBoSS Simulation Workflow

Operational snapshot for `mcp-biomodelling-servers` 2.5.2. Tool names and
parameters were checked against the live 2.5.2 schemas. Behaviour the schemas do
not describe follows the 2.5.x server documentation. Recheck this skill when the
server package is upgraded.

MaBoSS runs stochastic simulations of Boolean models. It's a complete tool
on its own — any BNET file can be loaded and simulated without ever
touching NeKo or PhysiCell. N nodes → up to 2^N possible states, so restrict
output nodes before running regardless of where the model came from.
Optionally imports a typed NeKo handoff instead of a bare BNET (see
`neko-workflow`), and optionally exports a handoff onward to
`physicell-workflow` if the task continues into tissue-level simulation.
The server simulates with the bundled `cmaboss` engine; no separate MaBoSS
executable is installed or needed.

## Recommended workflow (in order)

1. **Session:** `create_session()` — returns a `session_id`. Pass it
   explicitly with multiple models or parallel simulations.
2. **Load a model:** Prefer `import_neko_handoff(manifest_path)` (typed
   NeKo transfer). For a 2.1 manifest use the original server manifest path
   the orchestrator supplies; relocated project copies fail the `curation_file`
   binding check. Standalone BNET: `bnet_to_bnd_and_cfg(bnet_path)` →
   `build_simulation()`. Pass files by path only: never use `bnet_text` or
   `handoff_bundle` (routes for hosts that sandbox each server; this host
   shares one filesystem). A missing manifest or BNET is a blocker to report.
   If the load returns a heavy-workload warning (nodes × `max_time` ×
   `sample_count` / `thread_count` above 10⁸, e.g. pyMaBoSS's BNET defaults
   `max_time = 1000`, `sample_count = 10000`), quote it and change those
   settings only to values the orchestrator supplies.
3. **Inspect nodes — mandatory:** `get_maboss_nodes()` lists every valid
   node name. Required before any configuration step; downstream tools
   (`set_maboss_output_nodes`, `set_maboss_initial_state`,
   `simulate_mutation`) only accept these names.
   `get_maboss_nodes(selected_nodes=[...])` (at most 25) returns those nodes'
   rules, up/down rate expressions, referenced parameter values, unresolved
   references, output status and the current `model_revision`.
4. **Inspect rules and parameters:** `get_maboss_logical_rules(selected_nodes=[...])`
   returns readable rules (up to 100 nodes when omitted); `rule_limitation`
   flags nodes whose custom rate expressions mean the rule alone does not
   describe switching. `update_maboss_parameters()` with no args lists current
   values and the full set of valid keys, including sampling, time, thread and
   stationary-distribution settings.
5. **Tune:** `update_maboss_parameters(parameters={"sample_count": 1000, "thread_count": 4})`.
   Set `thread_count` early.
6. **Reduce output nodes — important:**
   `set_maboss_output_nodes(["Apoptosis", "Proliferation"])` restricts the
   result to the nodes that matter. Without this, MaBoSS enumerates all
   2^N states — a 30-node network goes from billions of rows to the
   2-5 output nodes selected. Always set this to the smallest
   biologically meaningful subset before running.
7. **Configure initial state — optional:** `get_maboss_initial_state()` →
   `set_maboss_initial_state(...)`.
   - One node: `[P(OFF), P(ON)]`.
   - Multiple nodes: `[{"state": [0, 0], "probability": 0.4}, {"state": [1, 0], "probability": 0.6}]`.
   - State-vector order must match the order of the `nodes` argument
     you pass; probabilities must sum to 1; only use returned node names.
8. **Run:** `run_simulation()` — preserves the run under a unique run ID and
   returns it. Read results with `get_simulation_result(run_id=...)`, never
   a `maboss://` resource (resources are unavailable to subagents).
9. **Analyse:** `get_simulation_result(run_id=...)` — final snapshot by
   default; `final_only=false` pages the trajectory (`offset`, `limit` ≤ 100).
10. **Visualise:** `visualize_network_trajectories(run_id=..., until=...)` —
    a new uniquely named PNG per variant; earlier plots are retained.
11. **Mutate:** `simulate_mutation(nodes, state)` — runs a mutant copy under its
    own run ID; the base model and latest ordinary run are unchanged.
12. **PhysiCell handoff:** `export_maboss_handoff(target_cell_type=...)` —
    snapshots model, parameters, output nodes, readout definitions, model
    revision, optional result, and complete NeKo lineage.

## Tool categories

- **Session management:** `create_session`, `list_sessions`, `list_artifact_sessions` (sessions with files on disk, including past server runs), `set_default_session`, `delete_session`
- **Pipeline:** `import_neko_handoff`, `bnet_to_bnd_and_cfg`, `build_simulation`, `run_simulation`
- **Handoff and export:** `import_neko_handoff`, `export_maboss_handoff`, `export_maboss_bnd_cfg`. `export_handoff_bundle` (inline copy of a manifest and its files) is not used here
- **Inspection (read-only):** `get_maboss_nodes` (with `selected_nodes` for rules/rates/revision), `get_maboss_initial_state`, `get_maboss_logical_rules`, `get_maboss_mutations`, `update_maboss_parameters` (no args)
- **Configuration:** `update_maboss_parameters` (global `parameters`, or per-node `rates` with `expected_revision`), `set_maboss_output_nodes`, `set_maboss_initial_state`, `change_maboss_rule` (validates the new rule and restores the previous one if invalid)
- **Summary readouts:** `edit_maboss_readouts` (`add` / `set_rule`; see below)
- **Analysis:** `get_simulation_result`, `simulate_mutation`, `visualize_network_trajectories`
- **Housekeeping:** `list_generated_files` (accepts a persisted full session ID after restart), `clean_generated_files`

## Key parameters for `update_maboss_parameters`

| Parameter | Type | Description |
|---|---|---|
| `sample_count` | int | Trajectories (larger = more precise, slower) |
| `max_time` | float | Simulation time horizon |
| `time_tick` | float | Discretisation step |
| `discrete_time` | int | 0/1 toggle for discrete time mode |
| `thread_count` | int | Parallel threads (environment-dependent) |

Stationary-distribution computation is never enabled automatically; it is an
explicit, approved setting.

## Model revisions, readouts and named rates

Every inspection with `selected_nodes` returns `model_revision`, a hash of the
effective BND/CFG content and readout definitions. It changes with rules,
numerical settings, initial states and output selection. Report it with every
result; approvals refer to one exact revision, and any later edit makes earlier
approvals and exports stale.

**Named rates (explicitly authorized values only):**
`update_maboss_parameters(rates=[{"node": "A", "up": 1.0, "down": 0.5}],
expected_revision=...)` (at most 25 nodes). Standard
`@logic ? coefficient : 0` / `@logic ? 0 : coefficient` forms keep their
logical conditions; only the coefficient changes, and values are inlined per
node so a shared parameter does not silently change other nodes. Custom
expressions whose coefficient cannot be identified are rejected — report the
limitation, never rewrite the expression. Global `parameters` and per-node
`rates` cannot be mixed in one call. Report the returned before/after values.

**Summary readouts (researcher-named nodes only):**
`edit_maboss_readouts(expected_revision=..., edits=[...])`, 1–20 records:
`{"operation": "add" | "set_rule", "node", "rule", "explanation",
"rate_up", "rate_down", "initial_probability_on"}`. Creation requires the
explicit rule, explanation, both rates and initial probability from the
authorization — never choose them yourself. Rules may use core node names,
`0`, `1`, `!`, `&`, `|` and parentheses; readouts cannot feed back into the
core or depend on other readouts. Name collisions, unresolved regulators and
malformed rules fail without changing the model. Adding a readout does not
select it as an output: call `set_maboss_output_nodes` explicitly if the
orchestrator names it. Readouts are stochastic simulated nodes with their own
update timing, not instantaneous observables; an exclusive Boolean expression
does not prove exclusive simulated readout states. Their provenance tag is
`readout`, distinct from core rules.

## Critical rules

- Always `create_session()` before any simulation tool.
- Generated files go to the session's directory under the configured
  artifact root; input paths such as `bnet_path` may be absolute or
  CWD-relative.
- Pass `session_id` explicitly for parallel simulations.
- `update_maboss_parameters` with no args lists all valid keys.
- Set `thread_count` early to speed up iteration.
- Keep an imported NeKo manifest, its BNET artifact and its `curation_file`
  history companion until the MaBoSS handoff is exported — integrity is
  rechecked against them before lineage is emitted.
- `export_maboss_bnd_cfg` is a standalone file export with no provenance;
  use `export_maboss_handoff` when PhysiCell needs typed provenance. Choose a
  new `artifact_prefix` for every retained handoff.

## Troubleshooting

- **Simulation hangs / never returns** → check whether
  `set_maboss_output_nodes` was called. Unrestricted runs above ~20 nodes
  enumerate a state space in the billions. Also check for an earlier
  heavy-workload warning: large `max_time` × `sample_count` runs can outlast
  the tool timeout. Report it; do not pick smaller values yourself.
- **Node name rejected** → re-run `get_maboss_nodes()` — names are
  sanitized during NeKo/BNET import.
- **Initial-state probabilities rejected** → confirm state-vector order
  matches the `nodes` argument and probabilities sum to exactly 1.
- **Edit rejected for revision** → another change happened since inspection;
  re-inspect and return the new revision rather than retrying blindly.
- **Run reported as incomplete** → engine failure and saving failure are
  reported separately; a saving failure is never retried automatically and
  earlier runs remain intact. Report the phase and diagnostic record.

## Durable runs, seeds and artifact analyses (backend 2.5.0)

Ordinary and mutant runs share one preservation path. Each run ID records the
full session ID, source model revision, run kind, requested mutations,
effective parameters/rates/initial states/output selection, readout
definitions, the exact BND/CFG sent to the engine and the outputs actually
produced. Mutation runs execute on a copy and never replace the latest
ordinary-run selection. Report every run ID you create.

`get_simulation_result(run_id=...)` and `visualize_network_trajectories(run_id=...)`
read saved artifacts without re-running MaBoSS, also after a server restart
(pass the owner `session_id` when known; a mismatched owner fails). Unknown,
ambiguous or tampered IDs fail without fallback. Omitting `run_id` selects the
latest ordinary run of the active session and returns the resolved ID — always
quote it. Responses are bounded (tables ≤ 100 states, pages ≤ 100 timepoints,
plots ≤ 1,000 timepoints); full tables stay in the run artifacts. `result.csv`
is a convenience alias, not the historical record. If a persisted rule clamp is
proposed instead of `simulate_mutation`, it is an explicit researcher-approved
rule change or refinement, never an automatic substitute. Restore/verify matched
WT and perturbation settings and record all differences.

The benchmark showed starts 0 and 1 shared 1999 of 2000 trajectory seeds. Plan
replicate starts at least sample_count apart using scripts/validate/plan_seeds.py,
record engine/version/thread settings, and empirically assess replicate variability.
Spacing avoids overlapping assumed consecutive seed intervals; it does not prove
statistical independence for every engine/version or threading implementation.

Use supported scripts/validate tools on captured artifacts for declared cycle
criteria, bounded exact fixed points/reachable terminal components and readout-function
exclusivity. Record update semantics and input hashes. Incomplete exploration is not
a proof. scripts/validate/README.md specifies the criteria contract. Capture the
researcher-approved PhysiCell handoff with
scripts/capture/record_maboss_physicell_handoff.py; keep upstream lineage intact.
MaBoSS→PhysiCell handoffs are version 2.1: they carry the model revision and
explicit readout definitions (an empty set is valid) and verify the NeKo parent
recursively.

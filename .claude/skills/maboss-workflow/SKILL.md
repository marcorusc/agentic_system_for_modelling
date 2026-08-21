---
name: maboss-workflow
description: "Use this skill whenever working with the MaBoSS MCP server to load, configure, or simulate Boolean models — session creation, loading a standalone BNET or a NeKo handoff, inspecting nodes/parameters, restricting output nodes before simulating, running simulations, analyzing or visualizing results, or mutation studies. Trigger this any time MaBoSS tools are called or the user mentions MaBoSS, Boolean model simulation, state-space explosion, or a BNET file — including when a simulation is slow, hangs, or never returns. Fully standalone; optionally imports typed provenance from neko-workflow and hands off to physicell-workflow for tissue-level simulation."
---

# MaBoSS Simulation Workflow

Operational snapshot for `mcp-biomodelling-servers` 2.3.0. Recheck this skill when
the server package is upgraded.

MaBoSS runs stochastic simulations of Boolean models. It's a complete tool
on its own — any BNET file can be loaded and simulated without ever
touching NeKo or PhysiCell. N nodes → up to 2^N possible states, so restrict
output nodes before running regardless of where the model came from.
Optionally imports a typed NeKo handoff instead of a bare BNET (see
`neko-workflow`), and optionally exports a handoff onward to
`physicell-workflow` if the task continues into tissue-level simulation.

## Recommended workflow (in order)

1. **Session:** `create_session()` — returns a `session_id`. Pass it
   explicitly with multiple models or parallel simulations.
2. **Load a model:** Prefer `import_neko_handoff(manifest_path)` (typed
   NeKo transfer). Standalone BNET: `bnet_to_bnd_and_cfg(bnet_path)` →
   `build_simulation()`.
3. **Inspect nodes — mandatory:** `get_maboss_nodes()` lists every valid
   node name. Required before any configuration step; downstream tools
   (`set_maboss_output_nodes`, `set_maboss_initial_state`,
   `simulate_mutation`) only accept these names.
4. **Inspect parameters:** `update_maboss_parameters()` with no args —
   current defaults and full set of valid keys.
5. **Tune:** `update_maboss_parameters({"sample_count": 1000, "thread_count": 4})`.
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
   - State-vector order must match `get_maboss_nodes()` order;
     probabilities must sum to 1; only use returned node names.
8. **Run:** `run_simulation()` — saves `result.csv` to the artifact
   directory.
9. **Analyse:** `get_simulation_result()` — Markdown probability table.
10. **Visualise:** `visualize_network_trajectories()` — PNG artifact.
11. **Mutate:** `simulate_mutation(nodes, state)` — one-off mutant copy.
12. **PhysiCell handoff:** `export_maboss_handoff(target_cell_type=...)` —
    snapshots model, parameters, output nodes, optional result, and
    complete NeKo lineage.

## Tool categories

- **Session management:** `create_session`, `list_sessions`, `set_default_session`, `delete_session`
- **Pipeline:** `import_neko_handoff`, `bnet_to_bnd_and_cfg`, `build_simulation`, `run_simulation`
- **Handoff:** `import_neko_handoff`, `export_maboss_handoff`
- **Inspection (read-only):** `get_maboss_nodes`, `get_maboss_initial_state`, `get_maboss_logical_rules`, `get_maboss_mutations`, `update_maboss_parameters` (no args)
- **Configuration:** `update_maboss_parameters`, `set_maboss_output_nodes`, `set_maboss_initial_state`
- **Analysis:** `get_simulation_result`, `simulate_mutation`, `visualize_network_trajectories`
- **Housekeeping:** `list_generated_files`, `clean_generated_files`

## Key parameters for `update_maboss_parameters`

| Parameter | Type | Description |
|---|---|---|
| `sample_count` | int | Trajectories (larger = more precise, slower) |
| `max_time` | float | Simulation time horizon |
| `time_tick` | float | Discretisation step |
| `discrete_time` | int | 0/1 toggle for discrete time mode |
| `thread_count` | int | Parallel threads (environment-dependent) |

## Critical rules

- Always `create_session()` before any simulation tool.
- File I/O is scoped to `<server>/artifacts/<session_id>/`.
- Pass `session_id` explicitly for parallel simulations.
- `update_maboss_parameters` with no args lists all valid keys.
- Set `thread_count` early to speed up iteration.
- Keep an imported NeKo manifest and its BNET artifact until the MaBoSS
  handoff is exported — integrity is rechecked against them before
  lineage is emitted.
- `export_maboss_bnd_cfg` is a standalone file export with no provenance;
  use `export_maboss_handoff` when PhysiCell needs typed provenance.

## Troubleshooting

- **Simulation hangs / never returns** → check whether
  `set_maboss_output_nodes` was called. Unrestricted runs above ~20 nodes
  enumerate a state space in the billions.
- **Node name rejected** → re-run `get_maboss_nodes()` — names are
  sanitized during NeKo/BNET import.
- **Initial-state probabilities rejected** → confirm state-vector order
  matches `get_maboss_nodes()` and probabilities sum to exactly 1.

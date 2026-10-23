---
name: maboss-workflow
description: Formulate and route governed MaBoSS import, configuration, simulation, mutation, rule-refinement, and handoff tasks through the isolated Boolean specialist.
---

# MaBoSS workflow

Never call MaBoSS tools from the orchestrator or this skill. Send the bounded
`task` to `specialist_dispatcher.start_boolean_dynamics_modeler`. Supply
`record_session_id` for an existing approved session and exact `approved_tools`
only for writes already authorized for this invocation.

Query `get_specialist_events` with its sequence cursor and `get_specialist_task`
until terminal. Consume only the validated handoff returned on `succeeded`, then
check its independent scientific status and approval requirements. Do not update
shared state while execution is active. Output remains under
`runs/boolean-dynamics-modeler/{maboss_session_id}/specialist-invocations/`.

## Task contract

Normally require an approved, exported NeKo handoff and pass its exact manifest and
session lineage. A standalone BNET requires an explicit rationale. Require a fresh
MaBoSS session for a new hypothesis.

The specialist must inspect exact node names, rules, parameters, initial states, and
mutations before configuration. Name the biologically necessary output nodes or ask
for a recommendation requiring researcher confirmation; unrestricted outputs can
cause exponential state-space growth. State explicit initial-state, parameter,
thread, seed, wild-type, and mutation requirements. Compare scenarios under matched
settings and treat simulations as model behavior rather than evidence.

Logical-rule changes are forbidden unless the invocation explicitly names
rule-refinement mode, the exact nodes, and a concrete `VALIDATION_PLAN.md` target.
Search only functions over existing incoming regulators, retain every tested
variant, and label the result `fitted-for-dynamics` unless exact literature supports
the form. Structural needs route back to NeKo.

Every inspection with `selected_nodes` returns a `model_revision` hash of the
effective rules, settings, initial states, outputs and readout definitions. Bind
review and approval to that exact revision; any later edit makes earlier approvals
and exports stale.

Summary readouts use `edit_maboss_readouts` (`add`/`set_rule`, at most 20, with
`expected_revision`). Approve it only for researcher-named readouts and inline
the exact rule, explanation, `rate_up`, `rate_down` and `initial_probability_on`.
Readouts may reference core nodes only, never feed back into the core and are
tagged `readout`; adding one does not select it as an output. They are stochastic
simulated nodes, so an exclusive expression does not prove exclusive simulated
states. Per-node rate coefficients use `update_maboss_parameters(rates=...,
expected_revision=...)` with explicitly approved values; standard conditional
logic is preserved, and unidentifiable custom expressions are rejected rather than
rewritten.

The typed MaBoSS-to-PhysiCell handoff is gated and may be requested only after
researcher approval of the dynamics. Require the complete typed result, upstream
lineage, settings, scenario summaries, warnings, artifacts, and export status.
Version 2.1 handoffs carry the model revision and readout definitions.

## CLI fallback

If the dispatcher is unavailable, the same bounded request may use
`python scripts/codex/run_specialist.py boolean_dynamics_modeler --prompt-file
<project-relative-task-file>`. Place that file in `.codex-tasks/`; add
`--record-session-id` and exact `--approve-tool` entries as applicable. Preserve
all scientific gates and validate the recorded result before synthesis.

## Durable runs, seeds and artifact analyses (backend 2.5.0)

Ordinary (`run_simulation`) and mutant (`simulate_mutation`) runs are preserved
under unique run IDs with the exact engine BND/CFG inputs, effective settings,
mutations, model revision and produced outputs. Mutant runs use a copy and keep the
base model and latest ordinary-run selection. Require every run ID in the handoff.
`get_simulation_result(run_id=...)` and `visualize_network_trajectories(run_id=...)`
read saved runs after restart without re-execution; plots never overwrite earlier
variants, and `result.csv` is only a convenience alias. If a persisted rule clamp
is proposed instead of a mutation run, it is an explicit researcher-approved rule
change or refinement, never an automatic substitute. Restore/verify matched WT and
perturbation settings and record all differences.

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
Operational semantics were checked against the live `mcp-biomodelling-servers`
2.5.1 schemas; revalidate after server upgrades.

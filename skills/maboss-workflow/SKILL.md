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

The typed MaBoSS-to-PhysiCell handoff is gated and may be requested only after
researcher approval of the dynamics. Require the complete typed result, upstream
lineage, settings, scenario summaries, warnings, artifacts, and export status.

## CLI fallback

If the dispatcher is unavailable, the same bounded request may use
`python scripts/codex/run_specialist.py boolean_dynamics_modeler --prompt-file
<project-relative-task-file>`. Place that file in `.codex-tasks/`; add
`--record-session-id` and exact `--approve-tool` entries as applicable. Preserve
all scientific gates and validate the recorded result before synthesis.

## Persistence, seeds and artifact analyses (backend 2.4.0)

The benchmark's simulate_mutation output was not persisted like run_simulation.
Require durable perturbation inputs/settings/results for reproducibility. If a
persisted rule-clamp workaround is necessary, it is an explicit researcher-approved
rule change or refinement, never an automatic mutation substitute. Restore/verify
matched WT and perturbation settings and record all differences.

Trajectory visualizations/result.csv can overwrite earlier output. Capture each
run/plot under its own immutable run identifier before another visualization or
simulation; preserve inputs, mutation, threads, sample count and seed with it.
Do not claim transient tables or overwritten plots establish reproducibility.

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

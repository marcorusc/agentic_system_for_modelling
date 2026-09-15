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

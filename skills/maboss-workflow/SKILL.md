---
name: maboss-workflow
description: Formulate and route governed MaBoSS import, configuration, simulation, mutation, rule-refinement, and handoff tasks through the isolated Boolean specialist.
---

# MaBoSS workflow

Never call MaBoSS tools from the orchestrator or this skill. Write a bounded task
file and invoke only:

`python scripts/codex/run_specialist.py boolean_dynamics_modeler --prompt-file <project-relative-task-file>`

For an existing run, add `--record-session-id <full-id>`. Output is recorded below
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

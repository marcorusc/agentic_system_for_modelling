---
name: physicell-workflow
description: Formulate and route governed PhysiCell and PhysiBoSS configuration, mapping, validation, and export tasks through the isolated multicellular specialist.
---

# PhysiCell and PhysiBoSS workflow

Never call PhysiCell tools from the orchestrator or this skill. Send the bounded
`task` to `specialist_dispatcher.start_multicellular_configurator`. Supply
`record_session_id` for an existing approved session and exact `approved_tools`
only for writes already authorized for this invocation.

Query `get_specialist_events` with its sequence cursor and `get_specialist_task`
until terminal. Consume only the validated handoff returned on `succeeded`, then
check its independent scientific status and approval requirements. Do not update
shared state while execution is active. Output remains under
`runs/multicellular-configurator/{physicell_session_id}/specialist-invocations/`.

## Task contract

State whether the task creates a fresh configuration hypothesis or modifies an
explicitly approved session. Provide the domain, dimensionality, substrates and
units, cell populations, parameters, interactions, and validation targets without
inventing missing values. The specialist must discover exact available signal and
behavior names before Cell Rules.

Configuration operations use patch semantics: omitted values remain unchanged.
Require only intended changes and prohibit accidental domain recreation. For an
existing XML, require validation, loading, component inspection, targeted edits,
summary, and a new session-scoped export.

PhysiBoSS integration requires an approved exported MaBoSS handoff. Preserve NeKo
and MaBoSS lineage; do not infer timing, mappings, signal names, behaviors, or
mutations. Every signal-node-behavior mapping is an explicit hypothesis requiring
researcher resolution when unspecified. Export Cell Rules CSV before XML when rules
exist.

The specialist configures and validates artifacts only. Neither it nor the
orchestrator may claim that PhysiCell simulation was executed or scientifically
validated.

## CLI fallback

If the dispatcher is unavailable, the same bounded request may use
`python scripts/codex/run_specialist.py multicellular_configurator --prompt-file
<project-relative-task-file>`. Place that file in `.codex-tasks/`; add
`--record-session-id` and exact `--approve-tool` entries as applicable. Preserve
all scientific gates and validate the recorded result before synthesis.

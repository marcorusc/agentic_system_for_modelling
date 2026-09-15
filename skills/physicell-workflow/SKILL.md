---
name: physicell-workflow
description: Formulate and route governed PhysiCell and PhysiBoSS configuration, mapping, validation, and export tasks through the isolated multicellular specialist.
---

# PhysiCell and PhysiBoSS workflow

Never call PhysiCell tools from the orchestrator or this skill. Write a bounded task
file and invoke only:

`python scripts/codex/run_specialist.py multicellular_configurator --prompt-file <project-relative-task-file>`

For an existing configuration, add `--record-session-id <full-id>`. Output is
recorded under
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

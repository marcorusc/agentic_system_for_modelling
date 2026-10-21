---
name: neko-workflow
description: Formulate and route governed NeKo network-construction, inspection, connectivity, history, and export tasks through the isolated network specialist.
---

# NeKo workflow

Never call NeKo tools from the orchestrator or this skill. Send the bounded
`task` to `specialist_dispatcher.start_network_curator`. Supply
`record_session_id` for an existing approved session and exact `approved_tools`
only for writes already authorized for this invocation.

Query `get_specialist_events` with its sequence cursor and `get_specialist_task`
until terminal. Consume only the validated handoff returned on `succeeded`, then
check its independent scientific status and approval requirements. Do not update
shared state while execution is active. Output remains under
`runs/network-curator/{neko_session_id}/specialist-invocations/`.

## Task contract

Require a fresh session for a new hypothesis unless reuse/branching was explicitly
approved. State the objective, seed genes, biological context, and exact authorized
scope. Before construction or connection work, provide explicit `path_policy`,
`reuse_policy`, `max_len`, `only_signed`, and `consensus`; never rely on defaults.

Read-only inspection may autonomously cover connectivity, requested-gene coverage,
history, references, candidate paths, and connector previews. Every topology
mutation requires explicit authorization for the invocation. Ask the specialist to
preview connector impact and compare history alternatives before repair or checkout.
Do not treat database annotations as adjudicated literature evidence.

SIF is a routine review artifact. BNET and the typed NeKo-to-MaBoSS handoff are
conclusive gated outputs: request them only after the researcher approved both
topology and literature review. Require a typed handoff, session-scoped SIF,
important-paths summary, bounded literature queue, effective policies, history
state, dimensions, warnings, and exact artifacts.

The operational tool semantics were checked against the live
`mcp-biomodelling-servers` 2.4.0 schemas and must be revalidated after server
upgrades. Expensive all-pairs or open-ended
connection strategies require size inspection and a non-mutating preview; prefer a
targeted strategy when it answers the scientific question.

## CLI fallback

If the dispatcher is unavailable, the same bounded request may use
`python scripts/codex/run_specialist.py network_curator --prompt-file
<project-relative-task-file>`. Place that file in `.codex-tasks/`; add
`--record-session-id` and exact `--approve-tool` entries as applicable. Preserve
all scientific gates and validate the recorded result before synthesis.


## NeKo-to-BioMASS export

When ODE formulation and topology/evidence export are explicitly approved, route
`export_biomass_handoff` through `specialist_dispatcher.start_network_curator`. Preserve references,
biological context and stable edge IDs in the dedicated `neko-to-biomass` handoff.
Follow `docs/ode-workflow.md`, including readiness and verified relocation capture.
This branch does not require BNET or Boolean-specific connectivity criteria.
Only the isolated ODE specialist receives BioMASS; the network specialist retains
NeKo alone. Existing topology policies and conclusive-export gates still apply.

## Semantics and caveats (backend 2.4.0)

State all five consequential policies before construction/repair: path_policy,
reuse_policy, max_len, only_signed, consensus. max_len limits the paths searched,
not the final edge count. discovered_paths reuse can introduce connections among
newly added nodes and grow the graph beyond a seed-only picture. Inspect connected
components and evidence, preview connector impact, and compare history alternatives
before any explicitly authorized repair; do not silently change policy to shrink it.

SIGNOR consensus=True does not imply independent multi-resource corroboration;
record its database-specific/no-op limitation. A SIF import constructs the supplied
network without the completion implied by older create_network prose. Preserve the
original identifiers/reference columns and inspect imported counts/history before
assuming equivalence. The benchmark exposed null complex labels during BNET export:
inspect and report offending labels, never silently relabel complexes. Relabelling
changes topology provenance and needs explicit approval and renewed review/export.

Capture approved exports with scripts/capture/record_neko_boolean_handoff.py or
record_neko_ode_handoff.py. Capture resource version/cache timestamp if supplied;
unknown metadata stays null, never inferred from the installed package version.
See scripts/capture/README.md. An SIF review export is not conclusive BNET approval.

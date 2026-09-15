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

The operational tool semantics correspond to `mcp-biomodelling-servers` 2.3.0 and
must be revalidated after server upgrades. Expensive all-pairs or open-ended
connection strategies require size inspection and a non-mutating preview; prefer a
targeted strategy when it answers the scientific question.

## CLI fallback

If the dispatcher is unavailable, the same bounded request may use
`python scripts/codex/run_specialist.py network_curator --prompt-file
<project-relative-task-file>`. Place that file in `.codex-tasks/`; add
`--record-session-id` and exact `--approve-tool` entries as applicable. Preserve
all scientific gates and validate the recorded result before synthesis.

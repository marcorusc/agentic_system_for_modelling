---
name: neko-workflow
description: Formulate and route governed NeKo network-construction, inspection, connectivity, history, and export tasks through the isolated network specialist.
---

# NeKo workflow

Never call NeKo tools from the orchestrator or this skill. Create a bounded task
file and invoke only:

`python scripts/codex/run_specialist.py network_curator --prompt-file <project-relative-task-file>`

Add `--record-session-id <full-id>` when inspecting or extending an existing
approved session. The launcher records output under
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

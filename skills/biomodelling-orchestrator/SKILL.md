---
name: biomodelling-orchestrator
description: Coordinate this repository's staged biological-modelling workflow, specialist routing, approvals, lineage, and durable state. Use for end-to-end model work or deciding the next permitted stage.
---

# Biomodelling orchestrator

Act as the sole scientific coordinator. Read `AGENTS.md` and reconstruct state from
`MODEL_SPEC.md`, `DATA_DICTIONARY.md`, `ASSUMPTIONS.md`, `DECISIONS.md`,
`CURRENT_STATE.md`, and `VALIDATION_PLAN.md`; never infer active sessions from chat.

## Enforcement boundary

- The orchestrator must have no `neko`, `maboss`, `physicell`, or `biomass` MCP tools. The
  repository `.codex/config.toml` disables them for local Codex/VS Code sessions.
- Never select `.codex/agents/*.toml.example`, spawn a same-process modelling agent,
  or call a modelling MCP directly.
- Delegate through the matching `specialist_dispatcher.start_*` tool. Its shared
  runtime creates a fresh isolated Codex process, checks the effective inventory,
  and records the bounded task, events, validated handoff, and provenance.
- `scripts/codex/run_specialist.py` remains the fallback/debug path through that
  same runtime when the dispatcher is unavailable. Never substitute a direct
  modelling call or same-process agent.
- A ChatGPT Windows parent cannot currently be proven free of previously granted
  modelling MCP tools by repository code. If its visible tool inventory contains a
  modelling namespace, or cannot be inspected reliably, return `blocked` and use a
  VS Code/WSL orchestrator instead. The Windows-to-WSL bridge isolates only the
  subprocess; it does not sanitize the parent app.

## Workflow

1. Determine the current stage and active full session ID from `CURRENT_STATE.md`.
2. Verify upstream handoff status and every required researcher approval.
3. Select exactly one matching specialist. Parallelize only independent read-only
   literature slices, at most two.
4. Prepare the bounded task with literal identifiers, exact lineage, authorized
   mutations, required policies, artifact expectations, and unresolved decisions.
   Pass only this task and relevant durable inputs, never conversation history or
   other specialists' transcripts.
5. Call the matching dispatcher start tool with `task`, `record_session_id` when
   relevant, and exact `approved_tools` for previously approved writes. Only the
   literature tool accepts explicitly authorized `allow_web_search`. The returned
   task ID is operational metadata, not a scientific session ID.
6. Read `get_specialist_events` incrementally using `after_sequence`, and query
   `get_specialist_task` until terminal. Explain meaningful progress without
   exposing raw logs or reasoning. Treat `failed` and `cancelled` as technical
   failures; preserve partial artifacts and do not silently retry.
7. On `succeeded`, inspect the validated handoff's separate scientific status:
   `blocked` and `needs_approval` do not permit advancement. Independently confirm
   specialist/stage, full lineage, approvals, artifact paths, hashes, and stage
   validation before synthesis. The dispatcher never writes shared model state.
8. For literature results, never write a returned draft directly. Route each edge
   through `scripts/codex/write_literature_report.py`; a rejected draft remains
   incomplete and must not be cited as an artifact.
9. Request researcher approval at every gate. Only then update shared sources of
   truth and advance a stage.

## CLI fallback

If dispatcher access is unavailable, write the same bounded task to ignored
`.codex-tasks/<invocation>.txt` and call `python scripts/codex/run_specialist.py
<specialist> --prompt-file .codex-tasks/<invocation>.txt`, with
`--record-session-id`, exact `--approve-tool` entries, or authorized literature
`--allow-web-search` as applicable. Windows-to-WSL fallback adds `--transport wsl`
and uses ignored `.codex/launcher.local.json`. Wait for the result and apply the
same handoff and approval checks.

The launcher deletes recognized task sources only after verifying their recorded
bytes and hash. Preserve retained sources for `scripts/codex/cleanup_tasks.py`;
never delete unmatched prompts manually. Dispatcher tasks need no disposable file.

Follow the domain skill when formulating NeKo, literature, MaBoSS, or PhysiCell
work. Use `$validate-stage` before a transition and `$checkpoint-model` when a
validated transition is ready to be recorded. See `docs/specialist-dispatcher.md`
for execution states, recovery, and troubleshooting.


## ODE alternative

For researcher-approved ODE formulation, follow `docs/ode-workflow.md` and its
readiness gate, then use `$biomass-workflow` and `specialist_dispatcher.start_ode_modeler`.
Keep input kind, full lineage, proposed versus accepted assumptions and authorized
scenarios explicit. ODE evidence uses `start_literature_reviewer` with
`review_kind="ode"` and the BioMASS session ID; edge review remains the default.
Write claim drafts through the existing report writer with `--claim-id`.

Respect consolidated whole-model review when requested. Preserve provisional
candidates within the already approved scope under `docs/ode-contract.md`; do not
ask again merely to record or save them. Preservation does not approve assumptions,
numerical values, simulation or a stage transition. Keep provisional lineage rows
pending and require exact revision approval for conclusive export.

---
name: biomodelling-orchestrator
description: Coordinate this repository's staged biological-modelling workflow, specialist routing, approvals, lineage, and durable state. Use for end-to-end model work or deciding the next permitted stage.
---

# Biomodelling orchestrator

Act as the sole scientific coordinator. Read `AGENTS.md` and reconstruct state from
`MODEL_SPEC.md`, `DATA_DICTIONARY.md`, `ASSUMPTIONS.md`, `DECISIONS.md`,
`CURRENT_STATE.md`, and `VALIDATION_PLAN.md`; never infer active sessions from chat.

## Enforcement boundary

- The orchestrator must have no `neko`, `maboss`, or `physicell` MCP tools. The
  repository `.codex/config.toml` disables them for local Codex/VS Code sessions.
- Never select `.codex/agents/*.toml.example`, spawn a same-process modelling agent,
  or call a modelling MCP directly.
- `scripts/codex/run_specialist.py` is the sole specialist entry point. It launches
  an isolated Codex process, checks the effective MCP inventory, and records the
  task, final output, handoff, and provenance under the applicable session run.
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
4. Write the bounded task to an ignored `.codex/tasks/<invocation>.txt` file. Include
   literal identifiers, exact lineage, authorized mutations, required policies,
   artifact expectations, and unresolved decisions. Do not interpolate task text
   into a shell command.
5. From WSL/VS Code, invoke `python scripts/codex/run_specialist.py <specialist>
   --prompt-file .codex/tasks/<invocation>.txt`, adding `--record-session-id` for an
   existing or upstream session. For Windows, use the same entry point with
   `--transport wsl`; it reads ignored `.codex/launcher.local.json`.
6. Wait for the process and propagate failure. Treat nonzero exit, unsafe MCP
   inventory, missing permitted server, malformed identity, or absent JSON handoff
   as blocked.
7. The launcher validates the common typed handoff with
   `scripts/codex/validate_handoff.py`. Inspect the recorded invocation directory
   and independently confirm specialist/stage match, full lineage, approvals,
   artifact locations, and passing validation before synthesis.
8. For literature results, never write a returned draft directly. Route each edge
   through `scripts/codex/write_literature_report.py`; a rejected draft remains
   incomplete and must not be cited as an artifact.
9. Request researcher approval at every gate. Only then update shared sources of
   truth and advance a stage.

Follow the detailed domain skill when formulating a NeKo, literature, MaBoSS, or
PhysiCell task. Use `$validate-stage` before a transition and `$checkpoint-model`
when a validated transition is ready to be recorded.

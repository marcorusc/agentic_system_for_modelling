---
name: checkpoint-model
description: Checkpoints the biological modelling project before compaction, clearing, stage transition, or session exit.
---

# Checkpoint the model

Coordinate the main session to:

1. Collect the latest specialist summaries.
2. Record every active full MCP session ID.
3. Record current NeKo history, MaBoSS settings, and PhysiCell workflow state when applicable.
4. Record artifact and handoff paths and hashes.
5. Record parameters, output nodes, initial states, mutations, mappings, and warnings.
6. Update `CURRENT_STATE.md`.
7. Append accepted and rejected choices to `DECISIONS.md`.
8. Update `runs/index.json`.
9. Run `git branch --show-current` before staging. Report the result. If it is
   empty or does not start with `model/`, do not commit; ask the user to create or
   switch to a dedicated local model branch. Never switch branches in this skill.
10. Inspect `git status` and the relevant diffs. Exclude unrelated pre-existing
   changes, secrets, caches, and generated files.
11. If durable state is complete and validation has passed, stage explicit
    task-relevant paths and create one local commit named
    `checkpoint(<stage>): <scientific state>`.
12. Record the content-checkpoint commit ID in `CURRENT_STATE.md` with one follow-up
    commit named `checkpoint(<stage>): record checkpoint`. Do not try to record that
    metadata commit's own ID inside itself.
13. Report missing provenance, unresolved biological decisions, the files committed,
    and the resulting commit ID or the reason no commit was created.

Do not push, pull, fetch, switch branches, rebase, amend, create tags or remotes,
rewrite history, clean the worktree, or delete sessions or artifacts. Do not create
an empty commit. State whether it is safe to run `/compact`, `/clear`, or end the
session.


## ODE state

Apply `docs/ode-contract.md` to `ode_modeler` / `biomass_ode`. Verify source kind,
lineage, document version, selected revision, complete captured inventory, evidence,
actual numerical settings and scenario results. Validate ODE evidence with explicit
`--review-kind ode`. Distinguish provisional workflow authorization from exact
session/revision conclusive-export approval; a candidate snapshot keeps the
scientific registry pending. Existing `runs/` and `evidence/` lifecycle scopes
already include ODE artifacts. Successful solves are not biological validation.
Preserve independent reviewer/auditor requirements; missing definitions remain blockers.

## Local Git checkpoints

Git provides a local, recoverable history of the project files; it does not replace
the scientific sources of truth, MCP history, or immutable run artifacts listed
above. Invoke the `checkpoint-model` skill at stage transitions and before
`/compact`, `/clear`, or session exit.

- Inspect `git status` and the relevant diffs before staging anything.
- Before staging, run `git branch --show-current` and report it. Model checkpoints
  must be created on a dedicated local branch whose name starts with `model/`. If
  the result is empty or names any other branch, do not commit and ask the user to
  create or switch branches; the checkpoint workflow must never switch branches
  itself.
- Update and validate the durable scientific state before creating the checkpoint.
- Stage explicit task-relevant paths only. Never sweep unrelated pre-existing user
  changes, secrets, caches, or generated files into a checkpoint.
- Use a concise message of the form `checkpoint(<stage>): <scientific state>`, then
  record that content-checkpoint commit ID in `CURRENT_STATE.md` with one follow-up
  metadata commit. Do not try to embed the metadata commit's own ID in itself.
- Local checkpoint commits are authorized by this workflow. Pushing, fetching,
  pulling, switching branches, rebasing, amending, force operations, tags, remotes,
  and destructive cleanup remain outside scope unless the user explicitly requests
  them.
- If provenance is incomplete, validation fails, or relevant changes cannot be
  separated safely from unrelated work, do not commit. Report the blocker and leave
  the worktree intact.

## Session registry

`CURRENT_STATE.md` must maintain a table of every specialist session created so far,
updated at stage 7 of the workflow (recording session IDs, parameters, artifacts) and
whenever a session is superseded:

| Specialist | Session ID | Stage | Status | Derived from | Handoff | Artifacts |
|---|---|---|---|---|---|---|
| network-curator | `neko_session_id` | topology | active / superseded | — | pending / approved / exported | `runs/network-curator/{id}/` |
| boolean-dynamics-modeler | `maboss_session_id` | boolean-dynamics | active / superseded | `neko_session_id` | pending / approved / exported | `runs/boolean-dynamics-modeler/{id}/` |
| multicellular-configurator | `physicell_session_id` | multicellular | active / superseded | `maboss_session_id` | — | `runs/multicellular-configurator/{id}/` |

`Handoff` tracks the conclusive, gated export each modelling stage produces for the
next: `pending` while results are under review, `approved` once the user has signed
off but before the export call is made, `exported` once the handoff artifact exists
on disk. A downstream specialist session may only be created against an upstream row
marked `exported` — a `boolean-dynamics-modeler` session requires an `exported`
`network-curator` row, and a `multicellular-configurator` session requires an
`exported` `boolean-dynamics-modeler` row.

Rules:

- Never overwrite a row in place when a session is superseded (e.g. topology
  revised, a new NeKo session created). Mark the old row `superseded` and add a new
  row — the registry itself is an append-only log, not just a snapshot of current
  state.
- `Derived from` records the upstream session ID a given session was built from
  (e.g. which `neko_session_id`'s SIF/BNET export a `maboss_session_id` started
  from), so lineage across the pipeline stays reconstructible after `/compact` or
  `/clear`.
- Before invoking any specialist, the orchestrator checks this table for the
  relevant `active` session ID rather than assuming one from chat context.
- If the table shows no `active` session for a specialist a task requires, that is
  itself a signal to create a fresh session (stage 4 of the workflow), not to guess
  an ID.

## Evidence records and executable checks

Follow review-literature-evidence for the required structured YAML footer, candidate
paths and immutable revisions. Read supporting PMIDs only from `supporting_pmids`;
excluded citations never support a decision. Each manual edge needs its own report.
Conditional approvals are structured records, resolved with `scripts/gate.py resolve`
against the exact evidence hash and allowlisted footer values, without mutating a model.

Use `scripts/state.py` JSON-file inputs for decision rows, registry additions and
supersession, handoff progress, validation results and checkpoint IDs. Do not edit
scientific tables by shell heredoc or unchecked string replacement. Missing/duplicate
rows and invalid transitions must fail. Diff state files before checkpointing.
Record timezone-aware ISO-8601 times; helpers use UTC with +00:00, preserving source
zone offsets separately. Never infer a date from a bare local clock or mix dates
across midnight without conversion.

The orchestrator may execute supported read-only artifact analyses in scripts/validate
(fixed points, reachable asynchronous attractors, readout exclusivity, declared
trajectory criteria). This does not authorize direct modelling MCP calls or changes
to a model. Bounded/incomplete analyses cannot pass a criterion. Only supported
validator output updates existing VALIDATION_PLAN rows via `state.py validation`.

## Context rules

- Keep the main context focused on synthesis and decisions.
- Use subagents for large searches, tool output, and specialist exploration.
- Do not paste full datasets, complete logs, or large result tables into chat.
- Before `/compact` or `/clear`, invoke the checkpoint skill.
- This applies to subagent delegation prompts as well as main chat: extract and
  inline only the relevant subset of a large source-of-truth file, rather than
  telling a specialist to read the full file itself.

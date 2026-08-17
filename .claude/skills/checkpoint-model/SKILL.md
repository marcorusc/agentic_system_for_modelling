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
9. Inspect `git status` and the relevant diffs. Exclude unrelated pre-existing
   changes, secrets, caches, and generated files.
10. If durable state is complete and validation has passed, stage explicit
    task-relevant paths and create one local commit named
    `checkpoint(<stage>): <scientific state>`.
11. Record the content-checkpoint commit ID in `CURRENT_STATE.md` with one follow-up
    commit named `checkpoint(<stage>): record checkpoint`. Do not try to record that
    metadata commit's own ID inside itself.
12. Report missing provenance, unresolved biological decisions, the files committed,
    and the resulting commit ID or the reason no commit was created.

Do not push, pull, fetch, switch branches, rebase, amend, create tags or remotes,
rewrite history, clean the worktree, or delete sessions or artifacts. Do not create
an empty commit. State whether it is safe to run `/compact`, `/clear`, or end the
session.

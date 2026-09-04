---
name: checkpoint-model
description: Checkpoint validated biological-model state before compaction, clearing, stage transition, or session exit, while preserving Git and provenance boundaries.
---

# Checkpoint the model

Collect validated specialist handoffs and record complete session IDs, upstream
lineage, history/configuration state, parameters, initial states, mutations,
mappings, warnings, artifact paths, and hashes in the authoritative project files.
Update `CURRENT_STATE.md`, append decisions to `DECISIONS.md`, and update the run
index when present.

Before Git mutation, inspect the branch, status, and relevant diffs. A model
checkpoint is permitted only on a local branch matching `model/*`; never switch
branches automatically. Stage only explicit task-relevant paths and exclude
pre-existing unrelated changes, secrets, caches, and generated clutter.

Preview disposable prompt cleanup with `python scripts/codex/cleanup_tasks.py`.
Confirm that every listed `verified` prompt points to a recorded invocation, then
run the same command with `--apply`. This command may remove only verified files
from `.codex-tasks/`, the legacy `.codex/tasks/` path, or the legacy root
`.codex-task-*.txt` convention. Preserve and report every `unmatched` prompt; it may
be the only record of an interrupted invocation.

When provenance and validation pass, create
`checkpoint(<stage>): <scientific state>`. Record that content commit ID in
`CURRENT_STATE.md` with one follow-up `checkpoint(<stage>): record checkpoint`
commit. Do not try to record the metadata commit's own ID inside itself.

Do not push, pull, fetch, rebase, amend, tag, change remotes, clean the general
worktree, or delete sessions/artifacts. The verified prompt cleanup above is the
only cleanup exception. Report missing provenance, unresolved decisions, unmatched
prompts, paths committed, resulting IDs, and whether it is safe to compact, clear,
or exit.

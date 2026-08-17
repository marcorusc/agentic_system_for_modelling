---
name: model-archive
description: Create a named, Git-backed archive of the current biological-model state. Use only when the user explicitly invokes /model-archive and supplies an archive name.
disable-model-invocation: true
argument-hint: "<name>"
allowed-tools: PowerShell(python .claude/scripts/model_lifecycle.py *)
---

# Archive the current model

1. Require a non-empty archive name from `$ARGUMENTS`; ask for one if absent.
2. Inspect `CURRENT_STATE.md` and ensure active specialist work is recorded. Stop
   if a consequential operation is still running or required handoffs are missing.
3. Summarize the scientific state in one short sentence.
4. Run `python .claude/scripts/model_lifecycle.py archive "<name>" --summary
   "<summary>"` from the repository root.
5. Report the archive tag and commit. Do not run `/model-restart` automatically.

The script stages only configured model-state paths and refuses to mix pre-staged
changes into its commit.

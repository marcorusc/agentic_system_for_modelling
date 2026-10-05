---
name: model-restart
description: Safely discard the current modelling direction and reset scientific state to pristine templates. Use only when the user explicitly invokes /model-restart.
disable-model-invocation: true
allowed-tools: PowerShell(python .claude/scripts/model_lifecycle.py *), Bash(python .claude/scripts/model_lifecycle.py *), Bash(python3 .claude/scripts/model_lifecycle.py *)
---

# Restart model development

1. Run `python .claude/scripts/model_lifecycle.py restart` from the repository
   root and show its preview verbatim.
2. Ask the user to confirm the listed reset. Do not infer confirmation from an
   earlier discussion.
3. After confirmation, run `python .claude/scripts/model_lifecycle.py restart
   --yes`.
4. Report the automatic recovery tag and restart commit.
5. Tell the user to run `/clear` before discussing the new model.

Never delete MCP sessions. The script first archives every recoverable, non-ignored
model-state file and preserves `.claude/`, `.model/`, `inputs/`, templates, and docs.

## Model lifecycle

This repository contains one biological model at a time. Model lifecycle is exposed
only through the user-invoked `/model-list`, `/model-archive`, `/model-restart`, and
`/model-restore` skills. The orchestrator must never invoke the three mutating skills
autonomously.

- `.model/config.json` is the authoritative allowlist of scientific-state paths.
- `inputs/`, `.claude/`, `.model/`, templates, documentation, and this file are
  infrastructure or source material and are never reset or restored from an archive.
- Named archives use annotated `model/archive/*` Git tags. Restart and restore create
  automatic `model/recovery/*` tags before replacing any state.
- Restores are path-scoped and must not switch branches, reset Git history, or roll
  back agent definitions.
- MCP session IDs in an archive are provenance, not resumable process state. Rebuild
  specialist runtime state from typed handoffs and artifacts.
- After restart or restore, instruct the user to run `/clear` so assumptions
  from the previous Claude conversation do not contaminate the loaded model state.

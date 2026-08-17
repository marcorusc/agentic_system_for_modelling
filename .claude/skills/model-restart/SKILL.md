---
name: model-restart
description: Safely discard the current modelling direction and reset scientific state to pristine templates. Use only when the user explicitly invokes /model-restart.
disable-model-invocation: true
allowed-tools: PowerShell(python .claude/scripts/model_lifecycle.py *)
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

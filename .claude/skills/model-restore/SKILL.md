---
name: model-restore
description: Restore a named biological-model archive without rolling back agent configuration or inputs. Use only when the user explicitly invokes /model-restore with an archive name.
disable-model-invocation: true
argument-hint: "<name>"
allowed-tools: PowerShell(python .claude/scripts/model_lifecycle.py *)
---

# Restore an archived model

1. Require an archive name from `$ARGUMENTS`. If absent, run `/model-list` logic
   and ask the user to select one.
2. Run `python .claude/scripts/model_lifecycle.py restore "<name>"` from the
   repository root and show its preview verbatim.
3. Ask the user to confirm the listed restore. Do not infer confirmation from an
   earlier discussion.
4. After confirmation, run `python .claude/scripts/model_lifecycle.py restore
   "<name>" --yes`.
5. Report the recovery tag, source archive, and restoration commit. Explain that
   MCP session IDs are historical and runtime state must be reconstructed.
6. Tell the user to run `/clear` before continuing the restored model.

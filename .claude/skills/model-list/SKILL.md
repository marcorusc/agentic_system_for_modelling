---
name: model-list
description: List the currently loaded biological-model attempt and named Git-backed archives. Use only when the user invokes /model-list or asks which model states are available.
disable-model-invocation: true
argument-hint: "[--all]"
allowed-tools: PowerShell(python .claude/scripts/model_lifecycle.py *)
---

# List model states

Run `python .claude/scripts/model_lifecycle.py list $ARGUMENTS` from the repository
root. Accept no arguments other than `--all`. Return the script output without
altering Git or project files.

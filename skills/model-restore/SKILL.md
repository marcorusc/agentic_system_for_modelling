---
name: model-restore
description: Preview and restore a named biological-model archive only when the user explicitly requests restoration and identifies the archive.
---

# Restore a model archive

Require an explicit archive name; if absent, use `$model-list` and ask the user to
choose. Run `python .claude/scripts/model_lifecycle.py restore <name>` and show the
preview. Stop for a new explicit confirmation of the exact restore. Only then run
the same command with `--yes`, using an argument vector rather than interpolated
shell text.

Report the recovery tag, source archive, and restoration commit. Explain that stored
MCP session IDs are provenance and runtime model state must be reconstructed from
approved handoffs and artifacts. Tell the researcher to clear conversation context
before continuing.

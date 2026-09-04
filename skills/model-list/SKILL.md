---
name: model-list
description: List the active biological-model attempt and named Git-backed archives without changing repository state.
---

# List model states

From the repository root, run `python .claude/scripts/model_lifecycle.py list`, with
only `--all` when the user supplied it. The existing script is provider-neutral and
is reused in place so the Claude implementation remains unchanged. Return its output
without altering Git, tags, model state, or MCP sessions.

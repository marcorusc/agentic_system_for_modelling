---
name: model-restart
description: Preview and safely restart biological-model state only when the user explicitly requests a restart; never infer destructive intent.
---

# Restart model development

1. Run `python .claude/scripts/model_lifecycle.py restart` and show its preview.
2. Stop for a new explicit confirmation of the exact preview. Earlier discussion is
   not confirmation.
3. Only after confirmation, run `python .claude/scripts/model_lifecycle.py restart
   --yes` using an argument vector.
4. Report the recovery tag and restart commit, and tell the researcher to clear
   conversation context before continuing.

Never delete MCP sessions. The lifecycle script preserves `.claude/`, `.codex/`,
`.model/`, `skills/`, `inputs/`, templates, and documentation.

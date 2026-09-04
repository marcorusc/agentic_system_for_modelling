---
name: model-archive
description: Create a named Git-backed archive of current biological-model state only when the user explicitly requests an archive and supplies its name.
---

# Archive model state

Require an explicit non-empty archive name. Inspect `CURRENT_STATE.md`; stop if
active consequential work is unrecorded or required handoffs are missing. Summarize
the scientific state in one sentence, then run `python
.claude/scripts/model_lifecycle.py archive <name> --summary <summary>` using an
argument vector, not interpolated shell text.

Report the archive tag and commit. Do not restart automatically. The existing
provider-neutral lifecycle script stages only configured model-state paths and
refuses to mix pre-staged changes.

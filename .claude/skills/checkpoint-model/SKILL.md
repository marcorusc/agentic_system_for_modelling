---
description: Checkpoints the biological modelling project before compaction, clearing, stage transition, or session exit.
---

# Checkpoint the model

Coordinate the main session to:

1. Collect the latest specialist summaries.
2. Record every active full MCP session ID.
3. Record current NeKo history, MaBoSS settings, and PhysiCell workflow state when applicable.
4. Record artifact and handoff paths and hashes.
5. Record parameters, output nodes, initial states, mutations, mappings, and warnings.
6. Update `CURRENT_STATE.md`.
7. Append accepted and rejected choices to `DECISIONS.md`.
8. Update `runs/index.json`.
9. Report missing provenance and unresolved biological decisions.

Do not delete sessions or artifacts. State whether it is safe to run `/compact`, `/clear`, or end the session.

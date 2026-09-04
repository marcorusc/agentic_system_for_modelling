# Codex enforcement mapping

This mapping records how the existing Claude-specific enforcement is preserved or
adapted for the local Codex workflow. The Claude files remain authoritative for
Claude Code and are not modified.

| Existing file or mechanism | Classification | Codex treatment |
| --- | --- | --- |
| `.claude/agents/literature-reviewer.md` `PreToolUse` hook | Unsupported as a portable cross-client boundary | Codex does not depend on this Claude event. The separate literature process is read-only. |
| `.claude/scripts/literature_file_guard.py` | Better implemented as an explicit validation script | Its strict resolved-path boundary is retained and strengthened in `scripts/codex/write_literature_report.py`, which also validates content and refuses overwrites. |
| `.claude/scripts/model_lifecycle.py` | Portable unchanged | Codex lifecycle skills call the existing provider-neutral script; no duplicate is maintained. |
| `.claude/scripts/test_model_lifecycle.py` | Portable unchanged | Run as part of the existing Python regression suite. |
| `.claude/scripts/test_literature_file_guard.py` | Portable regression for Claude behavior | Continue running it to prove the Claude guard remains intact. |
| `.claude/scripts/test_agent_mcp_access.py` | Claude-specific regression | Retained for Claude configuration; separate-process Codex isolation has its own tests. |
| `.claude/settings.json` and `.claude/settings.local.json` | Claude-only configuration | Preserved and ignored by the Codex workflow. |

Codex supports command hooks, but project/plugin hooks require local trust and do
not cover every specialized execution path. Therefore they are not used as the
literature write security boundary. The explicit writer has a smaller interface:
it derives `evidence/reports/{session_id}/{source}__{target}.md`, rejects any other
asserted output, validates the report contract, and creates the file exclusively.

Usage after validating a read-only specialist handoff:

```bash
python scripts/codex/write_literature_report.py \
  --session-id SESSION_ID \
  --source SOURCE \
  --target TARGET \
  --draft-file .codex/tasks/REPORT_DRAFT.md
```

The draft path is an input only. Report text must not be interpolated into the
shell command. Successful output is a JSON record containing the repository path,
SHA-256 digest, byte count, verdict, confidence, interaction type, and PMIDs.

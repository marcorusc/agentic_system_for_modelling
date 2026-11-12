# Data workflow

The `data-analyst` specialist retrieves and analyses data (DepMap, TCGA/GDC,
cBioPortal, GEO, PRIDE, Open Targets, researcher files, bulk RNA-seq, enrichment,
microscopy features). It works in a guarded session directory
`runs/data-analyst/<id>/`, produces hashed outputs plus a `manifest.json`, and returns
data-to-model proposals that need your approval. It never changes models or shared
state. Approved proposals are recorded by the orchestrator as `data-derived` decisions
and in `DATA_DICTIONARY.md`.

Guidance comes from vendored K-Dense skills in `vendor/scientific-agent-skills/`
(see `vendor/scientific-agent-skills/VENDOR.md` and `THIRD_PARTY_NOTICES.md`). Please
cite them when you use results. The agent is Claude-only until Codex parity.

## Setup

`python3 setup.py --with-data` creates `.venv-data`. `--with-cellprofiler` additionally
installs CellProfiler 4.2.8.1 into `.venv-cellprofiler` (Python 3.9). It requires system
packages providing `mysql_config` (for example `libmysqlclient-dev`) and a JDK. This
install was not verified on the development machine.

## Smoke test

```bash
python3 tests/integration/data_smoke.py
```

Offline, in a temporary repo copy (the real `.venv-data` is linked in, not copied; it
prints `SKIP: .venv-data not installed` and exits 0 when absent). It creates a session,
runs the vendored PyDESeq2 and GSEA scripts on a synthetic 4-vs-4 dataset, and checks
`deseq_dataset.h5ad` exists, `SET_UP`/`SET_DOWN` come out significant with the right NES
sign, `manifest.py verify` passes, the real SubagentStop recorder writes
`integrity.json` with `passed: true`, `validate_handoff` accepts a `needs_approval`
handoff, and a later edit to `DECISIONS.md` is detected. It ends with `DATA SMOKE PASSED`.

## Guard limits

The orchestrator guard (`.claude/scripts/data_orchestrator_guard.py`) is a tripwire
against accidental use, not a sandbox. For example `python3 -c` imports or copied
scripts are not caught. The `CLAUDE.md` policy is the primary control.

## Manual verification checklist

Inline subagent behaviour needs an interactive Claude Code session.

- [ ] `/agents` shows `data-analyst`.
- [ ] A data-analyst invocation can create a session and then run `ls`. This confirms
      the guard reads the right transcript field (`agent_transcript_path` versus
      `transcript_path`).
- [ ] A read-only task works end to end and `manifest.py verify` passes.
- [ ] `integrity.json`, written by the SubagentStop recorder, has `passed: true`.
- [ ] The main session running a vendored script is denied.
- [ ] The main session running `scripts/data/session.py` is denied.

## Threat model

The write guard, the protected-state snapshot and the recorder's integrity record defend against accidental and undisciplined writes. They do not defend against a deliberately adversarial agent forging provenance files: the agent runs user-level Python with no OS sandbox, so every on-disk anchor (integrity.json, runs/index.json, invocation records) is forgeable. OS-level confinement, such as the Claude Code sandbox filesystem write allowlist or a container, is the follow-up.

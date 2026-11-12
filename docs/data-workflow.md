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

`python3 scripts/setup.py --with-data` creates `.venv-data`. `--with-cellprofiler` additionally
installs CellProfiler 4.2.8.1 into `.venv-cellprofiler` (Python 3.9). It requires system
packages providing `mysql_config` (for example `libmysqlclient-dev`) and a JDK. This
install was not verified on the development machine.

## Smoke test

```bash
python3 tests/integration/data_smoke.py
```

Offline, in a temporary repo copy. The real `.venv-data` is not copied: the copy gets a
real `.venv-data/` directory with a copied `pyvenv.cfg` and a real `bin/` whose entries
are symlinks into the real venv (the data guard rejects a symlinked venv). It prints
`SKIP: .venv-data not installed` and exits 0 when `.venv-data` is absent. It creates a session,
runs the vendored PyDESeq2 and GSEA scripts on a synthetic 4-vs-4 dataset, and checks
`deseq_dataset.h5ad` exists, `SET_UP`/`SET_DOWN` come out significant with the right NES
sign, `manifest.py verify` passes, the real SubagentStop recorder writes
`integrity.json` with `passed: true`, `validate_handoff` accepts a `needs_approval`
handoff, and a later edit to `DECISIONS.md` is detected. It ends with `DATA SMOKE PASSED`.

## Provenance checks

- `sources.jsonl` paths are project-root-relative (`data-cache/sha256/<hex>`,
  `runs/data-analyst/<id>/raw/<name>`, `inputs/<file>`). `manifest.py verify` re-hashes
  every source against its ledger sha256 and requires the manifest `sources` to equal
  `sources.jsonl`, so an in-place edit of a downloaded file or a saved API response fails
  verification. Cache files are made read-only (0444); a cache hit is re-hashed and a
  modified entry is replaced with the freshly downloaded bytes.
- The protected-state snapshot covers the repository outside the session, except
  `.git`, `.venv-data`, `.venv-cellprofiler`, `data-cache`, `__pycache__` and
  `.claude/settings.local.json`. The last one is machine-local Claude Code permission
  state: approving a tool with "always allow" during a run writes it, so it is excluded
  and is not reported as tampering (`check_isolation.py` still inspects it for modelling
  allow rules).
- The snapshot records a pseudo-entry `.venv-data#dist-info` (hash of the sorted
  `.venv-data/lib/python*/site-packages/*.dist-info` names), so installing or removing a
  package in `.venv-data` during a run (for example `uv pip install`) is reported as a
  changed path.
- For vendored scripts the agent always passes explicit output paths inside
  `runs/data-analyst/<id>/outputs/...`; several defaults (`pydeseq2 --output results`,
  `pathway-enrichment --outdir enrichment_results`, `bulk-rnaseq --output-dir counts`)
  would write at the repository root and be reported as tampering.
- `check_isolation.py` also reports vendored skills copied into the user-level skills
  directory (`$CLAUDE_CONFIG_DIR/skills`, else `~/.claude/skills`), where the orchestrator
  would see them in every project. It does not delete them; removing or moving them is
  your decision.

## Guard limits

The orchestrator guard (`.claude/scripts/data_orchestrator_guard.py`) is a tripwire
against accidental use, not a sandbox. For example `python3 -c` imports or copied
scripts are not caught. The `CLAUDE.md` policy is the primary control.

## Manual verification checklist

Inline subagent behaviour needs an interactive Claude Code session. Items marked
**MERGE GATE** must pass before the branch is merged.

- [ ] (a) `/agents` shows `data-analyst`.
- [ ] (b) **MERGE GATE.** A data-analyst invocation can create a session and then run
      `ls`. This confirms the guard reads the right transcript field
      (`agent_transcript_path` versus `transcript_path`).
- [ ] (c) A read-only task works end to end and `manifest.py verify` passes.
- [ ] (d) `integrity.json`, written by the SubagentStop recorder, has `passed: true`.
- [ ] (e) **MERGE GATE.** The main session running a vendored script is denied.
- [ ] (f) The main session running `scripts/data/session.py` is denied.
- [ ] (g) Permissions: check whether a data-analyst running in the background can obtain
      Bash permission prompts at all (or whether unapproved commands are denied
      silently). Approving a prompt with "always" writes `.claude/settings.local.json`;
      that file is excluded from the snapshot, so the run's `integrity.json` must still
      report `passed: true` afterwards.

## Threat model

The write guard, the protected-state snapshot and the recorder's integrity record defend against accidental and undisciplined writes. They do not defend against a deliberately adversarial agent forging provenance files: the agent runs user-level Python with no OS sandbox, so every on-disk anchor (integrity.json, runs/index.json, invocation records) is forgeable. OS-level confinement, such as the Claude Code sandbox filesystem write allowlist or a container, is the follow-up.

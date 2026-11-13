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
runs the vendored PyDESeq2 and GSEA scripts on a synthetic 4-vs-4 dataset and proves:

- `deseq_dataset.h5ad` exists and `SET_UP`/`SET_DOWN` come out significant with the right NES sign;
- a session script renders `outputs/figures/volcano` and `gsea_dotplot` (PNG and SVG) with the
  vendored `publication.mplstyle`; each PNG carries a 300 dpi `pHYs` chunk (11811 px/m), each SVG
  is non-empty, and all are indexed in `outputs/index.json` with full figure metadata and `units: "none"`; the synthetic report has the Figures and Abbreviations sections;
- `manifest.py verify` passes;
- `handoff.py build --status needs_approval` writes `handoff.json` and prints
  `Handoff written: ... sha256=<hex>`;
- the real SubagentStop recorder writes `integrity.json` with `passed: true`, takes the report
  from the final `SubagentHandback` message into `report.md`, and `validate_handoff` accepts the handoff;
- after deleting `integrity.json`, `invocation/`, `report.md` and the index entry (hook never fired),
  `receive.py --transcript-root` recovers the capture, prints `RECEIVED <id> OK`, and `report.md`
  equals `final_report.md`;
- a later edit to `DECISIONS.md` is detected.

It ends with `DATA SMOKE PASSED`.

## Handoff, report and receive procedure

The agent finishes with `manifest.py build` and `verify`, writes `handoff_notes.json`
and runs `handoff.py build`, which generates `handoff.json` (artifact hashes, one
decision per proposal, status rules enforced). Its final message is the report and ends
with `Handoff: runs/data-analyst/<id>/handoff.json sha256=<64hex>`. The SubagentStop
recorder saves that final message as `report.md`; the agent never writes it.

Immediately after each data-analyst completion notification, before any state write,
the orchestrator runs:

```bash
python3 scripts/data/receive.py --session <id> --agent-id <agent-id>
```

If the integrity record or the `runs/index.json` registration is missing (the hook did
not fire), `receive.py` first checks that the agent transcript created exactly that
session (a wrong `--agent-id` is refused before anything is recorded), then recovers the
capture from the transcript. It runs `manifest.verify` and `validate_handoff`, requires
the recorded final report to end with `Handoff: runs/data-analyst/<id>/handoff.json
sha256=<hex>` matching the current `handoff.json`, and prints one row per decision
(`id | kind | layer | path | sha256 prefix`; note decisions show their artifact path),
`Handoff status: <status>` and `RECEIVED <id> OK`. Proposals are presented or acted on
only after `RECEIVED ... OK`. `receive.py` never edits shared state.

- `RECEIVE FAILED: <reason>`: relay the reason to the researcher verbatim, do not repair,
  rebuild or edit any file, and ask the researcher how to proceed. `failed`-status runs
  are expected to fail here.
- No session (for example `.venv-data` missing): the agent's final message reports
  `blocked` with the reason and remediation and has no `Handoff:` line. There is nothing
  to receive; skip `receive.py` and relay the reason.

### Recording an approved data product

After `RECEIVED ... OK` and the researcher's explicit decision:

1. Record the approval as a governance record (`python3 scripts/state.py record --input
   approval.json`), stage `data`:

   ```json
   {"id": "data-approval-1", "kind": "stage_approval", "stage": "data",
    "session_id": "<data session id>", "approved_by": "researcher",
    "authorization": "<exact quotation or durable request reference>",
    "outputs": ["P1"],
    "artifact": {"path": "runs/data-analyst/<id>/handoff.json", "sha256": "<hex>"}}
   ```

2. Register each approved product in `DATA_DICTIONARY.md` (`python3 scripts/state.py
   data-product --input product.json`). All keys are required strings; `path`/`sha256`
   are verified and `decision_id` must be the `id` of a governance record in
   `DECISIONS.md`:

   ```json
   {"name": "seed_genes_P1", "type": "gene list", "meaning": "...", "unit": "none",
    "identifiers": "HGNC symbol", "source_session": "<data session id>",
    "path": "runs/data-analyst/<id>/proposals/P1_seed_genes.csv", "sha256": "<hex>",
    "release": "<source release>", "decision_id": "data-approval-1", "notes": "..."}
   ```

Model use of an approved proposal is then tagged `data-derived` in `DECISIONS.md`
(data session ID, proposal id and SHA256).

Figures go in `outputs/figures/` (PNG 300 dpi plus SVG, indexed in `outputs/index.json`)
using the vendored `scientific-visualization` style. The vendored skill's `uv run` and
skill-directory instructions do not apply under the data guard; the `data-workflow`
skill gives the runnable form (saved session script run with `.venv-data/bin/python -E -s`,
`Agg` backend, vendored style and palettes by repository path, `palette_audit.py`).

### Figures and report

Every figure (an indexed `.png`/`.svg`/`.pdf` under `outputs/figures/`) needs `title`, a
`caption` of at least 80 characters, an `abbreviations` object, `sources` (each a `uri` from
`sources.jsonl`) and `script` (an existing file under `scripts/`); `manifest.py verify`
enforces this and the fields are hashed into the handoff through `manifest.json`. The final
report has the headings Question and scope, Sources, Methods, Results, Figures,
Abbreviations, Limitations, Proposals and decisions, then the `Handoff:` line. `receive.py`
fails with `RECEIVE FAILED: report is missing ...` if the Figures or Abbreviations heading or
the file name of any indexed figure is absent.

### Source notes

- cBioPortal datahub git-LFS/S3 downloads can fail; the agent falls back to the API and
  reconciles record counts.
- The DepMap portal requires human verification: download the release files yourself
  into `inputs/`; the agent registers them with `fetch.py --input`. Open Targets is for
  single-gene queries.
- Setup re-renders the `ode-modeler` agent only with `--with-biomass`.

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
      `ls`. Fixed in code; re-verify. Subagent PreToolUse events carry the main
      `transcript_path` plus `agent_id`, and the guard derives
      `<transcript without .jsonl>/subagents/agent-<agent_id>.jsonl` (R10).
- [ ] (c) A read-only task works end to end and `manifest.py verify` passes.
- [ ] (d) `integrity.json`, written by the SubagentStop recorder, has `passed: true`.
- [ ] (e) **MERGE GATE.** The main session running a vendored script is denied.
- [ ] (f) The main session running `scripts/data/session.py` is denied.
- [ ] (g) Permissions: check whether a data-analyst running in the background can obtain
      Bash permission prompts at all (or whether unapproved commands are denied
      silently). Approving a prompt with "always" writes `.claude/settings.local.json`;
      that file is excluded from the snapshot, so the run's `integrity.json` must still
      report `passed: true` afterwards.
- [ ] (h) A data run ends with `receive.py` → `RECEIVED … OK` and `report.md` written
      by the recorder.

## Threat model

The write guard, the protected-state snapshot and the recorder's integrity record defend against accidental and undisciplined writes. They do not defend against a deliberately adversarial agent forging provenance files: the agent runs user-level Python with no OS sandbox, so every on-disk anchor (integrity.json, runs/index.json, invocation records) is forgeable. OS-level confinement, such as the Claude Code sandbox filesystem write allowlist or a container, is the follow-up.

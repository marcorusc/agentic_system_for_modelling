# Data workflow

The `data-analyst` specialist retrieves and analyses data (DepMap, TCGA/GDC,
cBioPortal, GEO, PRIDE, Open Targets, researcher files, bulk RNA-seq, enrichment,
microscopy features). It works in a guarded session directory
`runs/data-analyst/<id>/`, produces hashed outputs plus a `manifest.json`, and returns
data-to-model proposals that need your approval. It never changes models or shared
state. Approved proposals are recorded by the orchestrator as `data-derived` decisions
and in `DATA_DICTIONARY.md`. For the design rationale and threat model, see
[data-analyst architecture](data-analyst-architecture.md) and the
[data-to-model handoffs architecture](data-to-model-handoffs-architecture.md).

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
- the data-to-model chain, with synthetic `seed_genes`, `perturbations` and `validation_targets`
  proposals in the same session: a `data` approval recorded through `state.py record`; the
  network-curator `DATA_INPUT` line is accepted by `gate.check_data_input` and a wrong proposal
  hash is refused;
- `mapping.py draft` on a synthetic BNET under `runs/network-curator/<s>/exports/`; the skeleton
  fails `check` on its `TODO` reasons, the completed mapping passes, and a `data_mapping`
  approval is recorded;
- the boolean-dynamics-modeler `DATA_INPUT` line (after a `STAGE_GATE` line naming the NeKo
  session) is accepted and a wrong mapping hash is refused (only the data part of the gate is
  called; the smoke records a synthetic exported, reviewed and approved NeKo session so the `STAGE_GATE` binds the BNET);
- synthetic trajectories and `runs.json` go through `mapping.py criteria --merge-into
  VALIDATION_CRITERIA.yaml`, and `scripts/validate/evaluate.py` passes the `scenario_contrast`
  criterion.

It ends with `DATA SMOKE PASSED`.

## Proposal schemas

Proposals of kind `seed_genes` (layer `neko`), `perturbations` and `validation_targets`
(layer `maboss`) must be CSV/TSV tables with fixed required columns, enum values and unique
ids, checked by `manifest.py verify` (`KIND_SCHEMAS`). Extra columns are allowed. The old
kind `mutations` is now `perturbations`. The column tables are in the `data-workflow` skill, section 7.

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
   are verified. `decision_id` must be the `id` of the step 1 record: a `stage_approval`
   with stage `data` and `session_id` equal to `source_session`, whose `artifact` is that
   session's `handoff.json` with an unchanged sha256. The product's `path` and `sha256`
   must be one of that handoff's `artifacts`; a proposal file additionally needs its
   proposal id (from `proposals/index.json`, itself unchanged since the handoff) in the
   record's `outputs`. Any other record is refused:

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

## Data to model handoffs

Approved proposals reach NeKo and MaBoSS through `DATA_INPUT` lines that the dispatch hook
(`.claude/scripts/stage_gate_guard.py`, calling `scripts/gate.py check_data_input`) checks
again from the durable records. Never paste data values into a brief.

**NeKo seeds.** After the `data` approval (its `outputs` list the proposal ids), line 1 of
the network-curator brief is:

```
DATA_INPUT {"data_session": "data-...", "proposals": {"P1": "<sha256>"}}
```

Each proposal must be a `seed_genes` proposal with target layer `neko`, be in the
`outputs` of a `stage_approval` for stage `data` and that session, and match both the
manifest and the file on disk; the handoff must still validate. When several data
approvals of the session exist, they are cumulative: a proposal is approved if any valid
`data` `stage_approval` of that data session, binding the current `handoff.json` sha256,
lists it in `outputs`; a later partial approval does not revoke an earlier one. There is no
revocation record: to withdraw a proposal, re-run the data analysis in a new session (new
handoff). The mapping approval is looked up by its exact `approval` id.

The curator finds each proposal file itself through `runs/data-analyst/<data_session>/manifest.json`
(the brief carries no path) and returns `blocked` if an id is missing or a hash differs.

**MaBoSS mapping.** `perturbations` and `validation_targets` are mapped to model terms in
`runs/orchestrator/<purpose>/mapping.json`, drafted by the orchestrator and decided by the
researcher (`scripts/data/mapping.py`):

| Command | Purpose |
|---|---|
| `draft --purpose P --data SESSION:PROPOSAL:APPROVAL ... --network NEKO_SESSION:BNET` | Skeleton with inputs, hashes and approvals filled in; one `unmapped` entry per proposal row with reason `TODO`. |
| `check MAPPING` | Exit 1 with one problem per line: bad paths or hashes, unapproved proposals, missing BNET nodes, rows neither mapped nor `unmapped` with a real reason, invalid criteria. |
| `criteria MAPPING --runs RUNS --approval RECORD_ID [--out FILE] [--merge-into VALIDATION_CRITERIA.yaml]` | Criteria entries from `runs.json` (scenario to saved trajectory CSV); refuses a mapping without a `data_mapping` approval of exactly its current bytes, and a scenario with no run. `--out` is written before the merge. The approval id appears in each declaration's "Required evidence" next to the mapping sha256. |

Rules enforced by `check`:
- the BNET is under `runs/network-curator/<session>/exports/` or
  `boolean-handoffs/<capture>/`;
- where the context and a perturbation fix the same node, the perturbation overrides the
  context; `check` prints each overlap as a `note:` line and does not fail;
- readout nodes must be among the MaBoSS output nodes approved for the run;
- criterion methods are `scenario_contrast`, `ordered_peaks` and `canonical_cycles`;
  `boolean_structure` is declared directly in `VALIDATION_CRITERIA.yaml`;
- `scenario_contrast` needs different test and reference contexts.

Rules enforced by `criteria`: `runs.json` is under `runs/orchestrator/`, trajectories are
saved artifacts under `runs/boolean-dynamics-modeler/`, and one trajectory cannot serve two
scenarios.

The researcher approves the checked mapping: a `stage_approval` with stage `data_mapping`,
the `mapping.json` path and sha256 as `artifact`, and `outputs` equal to the set of the
mapping's perturbation ids and criterion ids. Line 2 of the boolean-dynamics-modeler
brief, right after the `STAGE_GATE` line, is:

```
DATA_INPUT {"mapping": "runs/orchestrator/<p>/mapping.json", "sha256": "...", "approval": "<record id>"}
```

The hook requires the matching approval, a passing `mapping.py check` at dispatch time,
`inputs.network.neko_session` equal to the `STAGE_GATE` `upstream_session_id`, and
`inputs.network.sha256` equal to the BNET sha256 of the NeKo handoff that `STAGE_GATE`
approved. A `data_mapping` approval's `session_id` is the mapping's NeKo session and must
equal that `upstream_session_id`.

**Brief strictness.** For both specialists, any case-insensitive occurrence of
`DATA[_-]?INPUT` other than the single canonical line is refused: never mention it in
prose, backticks or quotes. A brief that mentions `runs/data-analyst` in any form, or a
data session id, without the `DATA_INPUT` line is refused. The hook fails closed: any
error denies the dispatch.

**After the run.** The modeler reports one trajectory path per `(context, perturbation)`
pair. The orchestrator writes `runs.json`, runs `mapping.py criteria ... --merge-into
VALIDATION_CRITERIA.yaml` (or declares the emitted entries with `state.py
validation-declare`), then `scripts/validate/evaluate.py`. Registry rows carry the lineage
(a NeKo session `Derived from` the data session with proposal ids and short hashes; a
MaBoSS row with the mapping path and short hash), and mapped states, perturbations and
readouts get the `data-derived` tag.

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

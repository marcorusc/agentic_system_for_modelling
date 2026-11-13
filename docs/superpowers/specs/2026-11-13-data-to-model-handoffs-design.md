# Data-to-model handoffs: NeKo and MaBoSS (sub-project 2)

Status: draft for researcher review · Date: 2026-11-13 · Branch: `feature/data-to-model-handoffs`
(stacked on `feature/data-analyst-agent` / PR #13; rebase onto `main` after #13 merges)
Builds on: [`docs/data-analyst-architecture.md`](../../data-analyst-architecture.md) (sub-project 1).

## 1. Purpose

Sub-project 1 made the data analyst produce hashed data products and proposals that the
researcher approves. Getting those approved proposals into the modelling layers is still
manual. In the live test (EGFR-family LUAD/BRCA, 2026-11-13):

- The orchestrator read the approved seed CSVs with an ad-hoc script and pasted the
  symbols into the network-curator brief. Nothing checked that they were the approved
  files, and the build decision cited the seed lists by name only, with no data session
  or hash.
- The GDSC session's Boolean-layer proposals (P1/P2 perturbation scenarios, P3–P5
  validation targets) were written in data terms: drug names, cohort contrasts, prose
  statements. MaBoSS needs model terms: exact node names from the exported network,
  ON/OFF states, readout nodes and machine-checkable criteria.
- To express contrast-type targets, the parallel session wrote a `scenario_contrast`
  validator: "readout drop under perturbation is larger in context A than in context B".

The researcher always reviews the data analyst's output and discusses with the
orchestrator how data enter the model. This design makes that discussion produce one
exact, checked, approved artifact, and makes the specialists consume exactly that.

### Scope

| In | Out |
|---|---|
| NeKo seeds; MaBoSS contexts, perturbations, readouts and validation criteria | BioMASS and PhysiCell inputs (a later sub-project) |
| Per-kind proposal schemas; the mapping file and its checker; `DATA_INPUT` dispatch checks; lineage; review checklists; porting `scenario_contrast` | Codex parity (sub-project 3, pending); MCP server changes |

### Success criteria

1. A network-curator dispatch that uses data seeds is refused unless its brief starts
   with a valid `DATA_INPUT` line naming approved proposals with matching hashes.
2. A boolean-dynamics-modeler dispatch that uses data is refused unless line 2 is a
   valid `DATA_INPUT` naming an approved mapping. The mapping must still pass
   `mapping.py check` and refer to the same NeKo upstream as the `STAGE_GATE` line.
3. `mapping.py check` rejects a missing node, a hash mismatch, an unapproved proposal, a
   proposal row neither mapped nor listed as unmapped with a reason, and invalid
   criteria.
4. Criteria generated from a mapping evaluate with `scripts/validate/evaluate.py`, and
   `scenario_contrast` is supported.
5. An offline smoke test exercises the whole data-to-MaBoSS path.

## 2. Decisions (researcher-approved, 2026-11-13)

| Topic | Decision |
|---|---|
| Layers | NeKo and MaBoSS |
| Who maps data terms to model terms | The orchestrator drafts a mapping file with the researcher; a script checks it; the researcher approves it |
| Enforcement | Typed proposals, the mapping, and `DATA_INPUT` dispatch checks (approach 1) |
| Validator | Port `scenario_contrast` from the live-test copy (with tests and review) |
| Codex | Pending, not in this sub-project |

## 3. Proposal schemas (data side)

`scripts/data/manifest.py verify` checks the required columns for these kinds. Extra
columns are allowed, so the analyst keeps its statistics. Values in required columns
must be non-empty unless marked optional.

| Kind | Required columns |
|---|---|
| `seed_genes` | `hgnc_symbol`, `tier` (`core`/`data`), `evidence` |
| `perturbations` | `scenario_id` (unique), `context`, `entity`, `entity_type` (`gene`/`compound`), `targets` (HGNC symbols, `;`-separated), `effect` (`inhibit`/`activate`/`loss`/`gain`), `evidence` |
| `validation_targets` | `target_id` (unique), `statement`, `test_context`, `reference_context`, `perturbation` (a `scenario_id` or an entity), `phenotype` (`proliferation`/`survival`/`migration`/`viability`/`other`), `expected` (`greater_drop`/`smaller_drop`/`decrease`/`increase`/`no_change`), `evidence_strength` (`strong`/`moderate`/`weak`/`exploratory`), `evidence` |

Kind and target-layer handling:
- The kind `mutations` is replaced by `perturbations` in `manifest.py`'s kind list and in
  the `data-workflow` skill. Existing kinds `initial_states`, `parameters` and
  `time_course` keep their current behaviour.
- `target_layer` must be `neko` for `seed_genes`, and `maboss` for `perturbations` and
  `validation_targets`.

## 4. Mapping file (orchestrator side, the discussion artifact)

`runs/orchestrator/<purpose>/mapping.json`, JSON, `schema_version: 1`:

```json
{
  "schema_version": 1,
  "inputs": {
    "data": [{"session": "data-…", "proposal": "P3", "path": "runs/data-analyst/…/proposals/P3_….csv",
              "sha256": "…", "approval": "data-approval-2"}],
    "network": {"neko_session": "…", "bnet": "runs/network-curator/<session>/exports/<inv>/<file>.bnet",
                "sha256": "…"}
  },
  "contexts":      {"LUAD_EGFR_canonical": [{"node": "EGFR", "state": 1}], "LUAD_EGFR_wt": []},
  "perturbations": [{"id": "S1", "from": {"proposal": "P1", "row": "S1"},
                     "model": [{"node": "EGFR", "state": 0}], "note": "erlotinib/gefitinib → EGFR off"}],
  "readouts":      [{"phenotype": "viability", "nodes": ["Proliferation", "Survival"]}],
  "criteria":      [{"criterion_id": "V1", "from": {"proposal": "P3", "row": "P3-V1"},
                     "method": "scenario_contrast",
                     "test": {"context": "LUAD_EGFR_canonical", "perturbation": "S1"},
                     "reference": {"context": "LUAD_EGFR_wt", "perturbation": "S1"},
                     "options": {"readouts": ["Proliferation"], "margin": 0.05, "combine": "all",
                                 "statistic": "tail_mean", "tail_points": 10}}],
  "unmapped":      [{"from": {"proposal": "P3", "row": "P3-V4"}, "reason": "…"}]
}
```

Rules:
- `state` is 0 or 1.
- Context and perturbation node lists apply fixed node states, as MaBoSS mutations. A
  scenario is a context plus an optional perturbation.
- `inputs.network.bnet` is the BNET exported with the approved NeKo→MaBoSS handoff and
  saved under `runs/network-curator/…/exports/` by `recover.py`. Node names are BNET
  names.

### 4.1 `scripts/data/mapping.py`

`draft --purpose P --data <session>:<proposal> … --network <neko_session>:<bnet path>`
writes a skeleton: `inputs` with hashes and approvals filled in, empty `contexts`,
`perturbations`, `readouts` and `criteria`, and one `unmapped` entry per proposal row
with reason `"TODO"`.

`check <mapping.json>` exits non-zero and lists every problem. It checks:
- every input path is repository-relative, exists, has no symlinks, and matches its
  `sha256`;
- every data proposal is listed in the proposal index of its session and in the outputs
  of the named approval record (a `stage_approval` for stage `data` in `DECISIONS.md`,
  whose artifact is that session's `handoff.json`);
- the data session's handoff still validates;
- every referenced node exists in the BNET's node list;
- every `from` references an existing proposal row;
- **every row of every input proposal is mapped exactly once or listed in `unmapped`
  with a non-empty, non-`TODO` reason**;
- context and perturbation ids are unique and every criterion refers to defined ones;
- criterion ids are unique, the methods are supported by `evaluate.py`, and the options
  validate with that method's own option checker;
- readout nodes used in criteria are declared under `readouts`.

`criteria <mapping.json> --runs <runs.json>` reads `runs.json`, which maps each
`(context, perturbation)` scenario to the saved MaBoSS trajectory CSV of the run that
simulated it. Paths must be saved run artifacts. It emits `VALIDATION_CRITERIA.yaml`
entries with `inputs` in each method's required order. For `scenario_contrast` the
order is `test_control`, `test_perturbed`, `reference_control`,
`reference_perturbed`, where "control" means the context without the perturbation.
The orchestrator declares them with `state.py validation-declare`. The command
refuses a scenario with no run.

## 5. Dispatch checks (`DATA_INPUT`)

- `scripts/gate.py check_data_input(root, specialist, value)`. The dispatch hook
  (`.claude/scripts/stage_gate_guard.py`) calls it for network-curator and
  boolean-dynamics-modeler.
- **network-curator:** the first line of the prompt may be
  `DATA_INPUT {"data_session": "data-…", "proposals": {"P1": "<sha256>", …}}`. Each
  proposal must:
  - be of kind `seed_genes` with target layer `neko`;
  - be among the outputs of a researcher `stage_approval` record for that data session;
  - have a sha256 equal to the manifest entry and to the file on disk.

  The data session's handoff must validate.
- **boolean-dynamics-modeler:** line 1 stays `STAGE_GATE {…}` (checked as today). Line 2
  may be `DATA_INPUT {"mapping": "runs/orchestrator/<p>/mapping.json", "sha256": "…", "approval": "<record id>"}`.
  - The mapping hash must match, and the approval record must be a `stage_approval`
    with stage `data_mapping` whose artifact is that mapping and hash.
  - `mapping.py check` must pass at dispatch time.
  - `inputs.network.neko_session` must equal the `STAGE_GATE` `upstream_session_id`.
- **No copying data into briefs:** for both specialists, a prompt that contains
  `runs/data-analyst/` but carries no `DATA_INPUT` line is refused, with a message
  pointing to the rule.
- **`state.py`** accepts `data_mapping` as a governance stage for `record`
  (`stage_approval`, `stage_review`), separate from the specialist `ROLES` map.

## 6. Lineage, provenance and review

- **Registry:** a NeKo session built from `DATA_INPUT` seeds is registered with
  `Derived from` = the data session ID, and its `Artifacts` cell cites the proposal ids
  and short hashes. A MaBoSS session keeps `Derived from` = the NeKo session, and its
  row cites the mapping path and short hash.
- **Provenance:** initial states, perturbation runs and readouts taken from a mapping
  get the `data-derived` tag in `DECISIONS.md`, citing the mapping, the data proposal id
  and the sha256.
- **Agent instructions** (`network-curator.md`, `boolean-dynamics-modeler.md`, and the
  `neko-workflow` and `maboss-workflow` skills):
  - Read data inputs only from the paths named in `DATA_INPUT` (or the mapping) and never
    alter them.
  - network-curator builds from the seed file's `hgnc_symbol` column, all tiers unless
    the brief restricts them, and reports which seeds were absent from the database.
  - boolean-dynamics-modeler simulates exactly the mapping's scenarios and reports the
    trajectory artifact for each `(context, perturbation)` pair.
- **Review:** the `validate-stage` skill and the `scientific-reviewer` and
  `reproducibility-auditor` agents get data-stage and mapping checklists.
  - Scientific: each mapping row is biologically justified; `unmapped` reasons are sound;
    margins and readouts fit the evidence strength; associations are not presented as
    mechanisms.
  - Reproducibility: hashes, approvals, the `DATA_INPUT` lines, registry lineage and
    criteria inputs are consistent.
- **`CLAUDE.md`:** a short paragraph covering:
  - the flow: approved proposals → `DATA_INPUT` for NeKo; mapping draft, discussion,
    check, approval (`data_mapping`) → `DATA_INPUT` for MaBoSS;
  - the rule that data are never pasted into briefs;
  - the lineage and provenance rules above.

## 7. `scenario_contrast` validator

Port `scripts/validate/scenario_contrast.py`, its registration in `evaluate.py`, its
README section and `tests/codex/test_scenario_contrast.py` from the live-test copy
(commit 31c4b00 in that worktree), unchanged unless review finds defects. Semantics:
- The readout drop is P(control) − P(perturbed).
- It passes when test_drop − reference_drop > margin, strictly.
- The statistic is `final`, or `tail_mean` over `tail_points`.
- `combine` is `all`/`any` over the readouts.
- There is no implicit tolerance; the margin is researcher-approved.

## 8. Testing

**Unit tests (stdlib):**
- Per-kind schema checks, with the `mutations`→`perturbations` rename.
- `mapping.py draft`/`check`/`criteria`. Every `check` rule has a failing case; a
  complete mapping passes; `criteria` refuses missing runs and orders
  `scenario_contrast` inputs correctly.
- `check_data_input` and the hook:
  - valid NeKo and MaBoSS cases pass;
  - refused: a missing `DATA_INPUT` with a data path in the prompt, a wrong hash, an
    unapproved proposal, a wrong kind or layer, a mapping whose network differs from
    `STAGE_GATE`, an unapproved mapping, and a mapping that fails `check`.
- `state.py` accepts the `data_mapping` stage.
- The ported `scenario_contrast` tests.

**Smoke test:** `tests/integration/data_smoke.py` is extended. Starting from synthetic
`seed_genes`, `perturbations` and `validation_targets` proposals and a synthetic BNET, it
runs:
1. the approval records;
2. `DATA_INPUT` checks for NeKo;
3. mapping `draft`, then filling it, then `check`;
4. the mapping approval;
5. the MaBoSS `DATA_INPUT` check;
6. criteria generated from synthetic trajectories;
7. `evaluate.py`, with `scenario_contrast` passing.

**Live (researcher):** seeds → NeKo via `DATA_INPUT`; then the mapping discussion, check
and approval; then MaBoSS scenarios and criteria evaluation.

## 9. Out of scope

- BioMASS and PhysiCell data inputs.
- Codex parity.
- MCP server changes.
- Automatic mapping, or any inference of node names or margins: the orchestrator drafts
  and the researcher decides.

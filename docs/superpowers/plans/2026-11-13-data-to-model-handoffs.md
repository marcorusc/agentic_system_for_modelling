# Data-to-model handoffs (sub-project 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Approved data proposals reach NeKo and MaBoSS only through typed, hash-checked `DATA_INPUT` dispatches. For MaBoSS this goes via a researcher-approved mapping file that is checked against the exported network.

**Architecture:**
- **Proposal schemas:** per-kind schemas in `scripts/data/manifest.py`.
- **Approval checks:** a shared approval resolver, `scripts/data/approvals.py`.
- **Mapping:** `scripts/data/mapping.py` with `draft`, `check` and `criteria`.
- **Dispatch checks:** `scripts/gate.py check_data_input`, called by the existing dispatch hook.
- **Validator:** the ported `scenario_contrast` method.
- **Docs and checklists:** updates for the agents, skills, reviewers and `CLAUDE.md`.

**Tech Stack:** Python 3.11+ stdlib with `unittest`; Claude Code hooks; no MCP server changes.

**Spec:** `docs/superpowers/specs/2026-11-13-data-to-model-handoffs-design.md`

## Global Constraints

- **Branch and location:**
  - Work in `/home/marcorusc/tests/claude_test/downloads/agentic_system_for_modelling` on `feature/data-to-model-handoffs` (based on `main` at 442723e).
  - Never touch the `agentic_system_data_test*` checkouts, the real `~/.claude`, or `~/.cache`.
  - Do not push.
- **Proposal kinds:** `seed_genes`, `initial_states`, `perturbations`, `validation_targets`, `parameters`, `time_course` (`mutations` is removed).
  - `seed_genes` must target `neko`.
  - `perturbations` and `validation_targets` must target `maboss`.
- **Required columns:**
  - `seed_genes`: `hgnc_symbol`, `tier` ∈ {core, data}, `evidence`.
  - `perturbations`: `scenario_id` (unique), `context`, `entity`, `entity_type` ∈ {gene, compound}, `targets` (HGNC symbols, `;`-separated), `effect` ∈ {inhibit, activate, loss, gain}, `evidence`.
  - `validation_targets`: `target_id` (unique), `statement`, `test_context`, `reference_context`, `perturbation`, `phenotype` ∈ {proliferation, survival, migration, viability, other}, `expected` ∈ {greater_drop, smaller_drop, decrease, increase, no_change}, `evidence_strength` ∈ {strong, moderate, weak, exploratory}, `evidence`.
  - Extra columns are allowed.
- **Mapping file:** `runs/orchestrator/<purpose>/mapping.json`, with `schema_version: 1` (integer) and exactly the keys `schema_version`, `inputs`, `contexts`, `perturbations`, `readouts`, `criteria`, `unmapped`.
  - Node `state` ∈ {0, 1}.
  - All paths are repository-relative.
- **`DATA_INPUT` lines:**
  - NeKo: line 1, `DATA_INPUT {"data_session": "...", "proposals": {"P1": "<sha256>"}}`.
  - MaBoSS: line 1 `STAGE_GATE {…}`, line 2 `DATA_INPUT {"mapping": "runs/orchestrator/<p>/mapping.json", "sha256": "...", "approval": "<record id>"}`.
- **Approvals:**
  - **Data proposals:** a `stage_approval` record with `stage: "data"`, `session_id` = the data session, and `artifact` = `runs/data-analyst/<session>/handoff.json` plus its current sha256. The proposal id must be in `outputs`.
  - **Mappings:** a `stage_approval` with `stage: "data_mapping"` whose `artifact` is the mapping path plus sha256. `outputs` holds the mapping's perturbation and criterion ids.
- **Hook convention** (`.claude/scripts/stage_gate_guard.py`): deny with a stderr message and exit 2.
- **Transcripts and JSONL** are split on `"\n"` only.
- **Commits:** focused, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Clarification of spec §4.1 (`validation-declare`):** `state.py validation-declare` only adds a `VALIDATION_PLAN.md` row (`Criterion`, `Method`, `Required evidence`). The executable entries live in `VALIDATION_CRITERIA.yaml`. So `mapping.py criteria` emits both the criteria entries and the matching declaration inputs, and can merge the entries into `VALIDATION_CRITERIA.yaml` with duplicate-id refusal.

## Review Focus

1. **The BNET node list ignores the header line `targets, factors`** (any spacing or case), blank lines and `#` comments; node = text before the first comma, stripped. This matches `scripts/validate/boolean_structure.py:84`. Pinned by Task 4 `test_bnet_nodes_skip_header_and_comments`.
2. **A brief that merely quotes a data path in prose** (e.g. "see runs/data-analyst/…") without `DATA_INPUT` is refused for network-curator and boolean-dynamics-modeler only. Other specialists, such as literature-reviewer, are unaffected. Pinned by Task 5 `test_data_path_without_data_input_refused` and `test_other_specialists_unaffected`.
3. **An approval that is valid but for a different data session**, or a handoff changed after approval, is refused by both `mapping.py check` and `check_data_input`. Pinned by Task 3 `test_wrong_session_and_changed_handoff_refused`.
4. **A proposal row both mapped and listed in `unmapped`**, or mapped twice, fails `check`. Pinned by Task 4 `test_row_mapped_twice_or_also_unmapped_rejected`.
5. **The `scenario_contrast` input order is `test_control, test_perturbed, reference_control, reference_perturbed`**, where "control" means the context without the perturbation. A swapped order gives the wrong sign. Pinned by Task 4 `test_criteria_scenario_contrast_input_order`.

---

### Task 1: Port the `scenario_contrast` validator

**Files:**
- Port from commit `31c4b00` (reachable in this repository): `scripts/validate/scenario_contrast.py`, the `scripts/validate/evaluate.py` hunk, the `scripts/validate/README.md` section, and `tests/codex/test_scenario_contrast.py`.

**Interfaces:**
- Produces: `scripts.validate.scenario_contrast.contrast(trajectories: list[dict[str, list[float]]], options: dict) -> tuple[bool, dict]`, plus `ROLES` and `OPTIONS`.
- `evaluate.py` accepts `"method": "scenario_contrast"` with exactly four inputs.

- [ ] **Step 1:** Run `git diff 31c4b00~1 31c4b00 -- scripts/validate tests/codex/test_scenario_contrast.py > /tmp/sc.patch && git apply --check /tmp/sc.patch`. Expected: it applies cleanly; otherwise port by hand.
- [ ] **Step 2: RED.** Apply only the test file and run `python3 -m unittest tests.codex.test_scenario_contrast -v`. Expected: FAIL (module missing).
- [ ] **Step 3:** Apply the rest. Run the same command. Expected: PASS. Then run `python3 scripts/run_tests.py`. Expected: all suites OK.
- [ ] **Step 4:** Commit `feat(validate): scenario_contrast criterion (ported from live test)`.

### Task 2: Per-kind proposal schemas

**Files:**
- Modify: `scripts/data/manifest.py` (`KINDS`; a new `KIND_SCHEMAS`; per-proposal CSV column checks in `verify`)
- Modify: `.claude/skills/data-workflow/SKILL.md` (§7 `proposals/index.json` template plus a new "Proposal schemas" subsection with the three column tables)
- Modify: `docs/data-workflow.md` (one paragraph)
- Test: `tests/data/test_manifest.py`

**Interfaces:**
- Produces: `manifest.KIND_SCHEMAS: dict[str, dict]` of the form `{kind: {"layer": "neko"|"maboss", "required": tuple[str, ...], "enums": dict[str, tuple[str, ...]], "unique": str|None, "list_columns": tuple[str, ...]}}` for the three kinds.
- Verify rules for proposals:
  - Proposals of these kinds must be CSV (`.csv` or `.tsv`) with every required column present and non-empty on every row.
  - Enum columns take allowed values only.
  - The unique column has no duplicates.
  - `targets` splits on `;` into non-empty items.
  - `target_layer` must match the schema's layer.
  - `mutations` is rejected as an unknown kind.

- [ ] **Step 1: Write failing tests:**
  - `test_seed_genes_schema_ok`;
  - `test_missing_required_column_rejected`;
  - `test_empty_required_value_rejected`;
  - `test_bad_enum_rejected`;
  - `test_duplicate_scenario_id_rejected`;
  - `test_wrong_layer_rejected`;
  - `test_mutations_kind_rejected`;
  - `test_extra_columns_allowed`;
  - `test_validation_targets_schema_ok`.
- [ ] **Step 2:** Run `python3 -m unittest tests.data.test_manifest -v`. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement. Update any fixture or the smoke test that uses kind `mutations`. Update the skill and docs.
- [ ] **Step 4:** Run `python3 scripts/run_tests.py` and `python3 tests/integration/data_smoke.py`. Expected: OK, and DATA SMOKE PASSED.
- [ ] **Step 5:** Commit `feat(data): typed proposal schemas for seed_genes, perturbations, validation_targets`.

### Task 3: Approval resolver and the `data_mapping` stage

**Files:**
- Create: `scripts/data/approvals.py`
- Modify: `scripts/state.py`. `validate_record` accepts `stage: "data_mapping"` for `stage_approval` and `stage_review`, via a new `GOVERNANCE_STAGES = set(ROLES.values()) | {"data_mapping"}`. The `data-product` check is refactored to use `approvals.require_data_approval`, with behaviour and messages unchanged.
- Test: `tests/data/test_approvals.py`, `tests/codex/test_state_data_product.py` (must stay green)

**Interfaces:**
- `approvals.load_record(root: Path, record_id: str) -> dict`: raises `ValueError` if the id is unknown. It uses `scripts.state.records` on `DECISIONS.md`.
- `approvals.require_data_approval(root: Path, record_id: str, session_id: str) -> dict`: requires `stage_approval`, stage `data`, a matching `session_id`, and an artifact path equal to `runs/data-analyst/<session_id>/handoff.json` whose sha256 matches the file now. Returns the record.
- `approvals.require_proposal_approved(root: Path, record: dict, session_id: str, proposal_id: str) -> dict`:
  - the proposal must be in the record's `outputs` and in the session's `proposals/index.json`;
  - its path and sha256 must be among the `handoff.json` artifacts;
  - returns the proposal entry plus `"path"` (repo-relative) and `"sha256"`.
- `approvals.require_mapping_approval(root: Path, record_id: str, mapping_rel: str, sha256: str) -> dict`: requires `stage_approval`, stage `data_mapping`, and an artifact path and sha256 equal to the arguments and to the file now.

- [ ] **Step 1: Write failing tests:**
  - `test_data_approval_ok`;
  - `test_stage_review_refused`;
  - `test_other_stage_refused`;
  - `test_wrong_session_and_changed_handoff_refused`;
  - `test_proposal_not_in_outputs_refused`;
  - `test_proposal_hash_not_in_handoff_refused`;
  - `test_mapping_approval_ok_and_mismatch_refused`;
  - `test_state_accepts_data_mapping_stage`.
- [ ] **Step 2:** Run `python3 -m unittest tests.data.test_approvals -v`. Expected: FAIL.
- [ ] **Step 3:** Implement. Refactor `state.py data-product` onto `require_data_approval` and `require_proposal_approved`.
- [ ] **Step 4:** Run `python3 scripts/run_tests.py`. Expected: OK, including `test_state_data_product`.
- [ ] **Step 5:** Commit `feat(data): shared approval resolver; data_mapping governance stage`.

### Task 4: `scripts/data/mapping.py`

**Files:**
- Create: `scripts/data/mapping.py`
- Test: `tests/data/test_mapping.py`

**Interfaces:**
- `bnet_nodes(path: Path) -> set[str]`: see Review Focus 1.
- `draft(root: Path, purpose: str, data: list[tuple[str, str, str]], network: tuple[str, str]) -> Path`:
  - `data` items are `(session, proposal, approval_record_id)`; `network` is `(neko_session, bnet_rel)`.
  - It writes `runs/orchestrator/<purpose>/mapping.json` and refuses to overwrite.
  - `inputs` is filled with paths and hashes, after the approvals are verified.
  - It adds one `unmapped` entry `{"from": {"proposal", "row"}, "reason": "TODO"}` per proposal row, where the row key is the `scenario_id`/`target_id`/`hgnc_symbol` value.
- `check(root: Path, mapping_rel: str) -> list[str]` implements every rule in spec §4.1, including:
  - every row is mapped exactly once or listed in `unmapped` with a reason other than empty or `TODO`;
  - perturbations map `perturbations` rows, and criteria map `validation_targets` rows;
  - `seed_genes` inputs are rejected in a mapping (they go to NeKo directly);
  - criterion option validation reuses each method's own checker. For `scenario_contrast`, call `contrast()` on four synthetic one-point trajectories built from the declared readouts, and treat any raised `ValueError` as an option error.
- `criteria(root: Path, mapping_rel: str, runs_rel: str) -> dict`:
  - `runs.json` has the form `{"runs": [{"context": id, "perturbation": id|null, "trajectory": path}]}`, where every trajectory path is an existing file under `runs/boolean-dynamics-modeler/`.
  - It returns `{"criteria": [<VALIDATION_CRITERIA entries>], "declarations": [{"Criterion", "Method", "Required evidence"}]}`.
  - It refuses a scenario with no run.
- CLI:
  - `mapping.py draft --purpose P --data S:P:REC … --network NEKO:BNET`
  - `mapping.py check M` (exit 1 and one error per line)
  - `mapping.py criteria M --runs R [--out F] [--merge-into VALIDATION_CRITERIA.yaml]`. The merge refuses duplicate `criterion_id`s and writes atomically.

- [ ] **Step 1: Write failing tests:**
  - `test_bnet_nodes_skip_header_and_comments`;
  - `test_draft_fills_inputs_and_unmapped`;
  - `test_draft_refuses_unapproved`;
  - `test_check_complete_mapping_passes`;
  - one test per rejection:
    - `test_hash_mismatch`;
    - `test_unknown_node`;
    - `test_missing_row_rejected`;
    - `test_row_mapped_twice_or_also_unmapped_rejected`;
    - `test_todo_reason_rejected`;
    - `test_undefined_context_rejected`;
    - `test_bad_method_or_options_rejected`;
    - `test_readout_not_declared_rejected`;
    - `test_seed_genes_input_rejected`;
  - `test_criteria_scenario_contrast_input_order`;
  - `test_criteria_missing_run_refused`;
  - `test_merge_refuses_duplicate_id`;
  - `test_cli_exit_codes`.
- [ ] **Step 2:** Run `python3 -m unittest tests.data.test_mapping -v`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `python3 scripts/run_tests.py`. Expected: OK.
- [ ] **Step 5:** Commit `feat(data): mapping draft/check/criteria for data-to-MaBoSS`.

### Task 5: `DATA_INPUT` dispatch checks

**Files:**
- Modify: `scripts/gate.py` (new `check_data_input(root, specialist, task) -> dict|None`)
- Modify: `.claude/scripts/stage_gate_guard.py` (call it for `network_curator` and `boolean_dynamics_modeler`)
- Test: `tests/codex/test_state_gate.py` or a new `tests/codex/test_data_input_gate.py`

**Interfaces:**
- **Parsing:** find a line starting with `DATA_INPUT ` among the prompt's first two lines (line 1 for network-curator, line 2 for boolean-dynamics-modeler) and parse its JSON object.
- **network-curator:** keys exactly `{"data_session", "proposals"}`. For each proposal:
  - `require_data_approval` (its record is the `stage_approval` found by session; if several, the newest; ambiguity is an error) and `require_proposal_approved`;
  - the kind must be `seed_genes` with layer `neko`;
  - the sha256 in the line must equal the resolved one;
  - the data session's `handoff.json` must pass `validate_handoff` now.
- **boolean-dynamics-modeler:** keys exactly `{"mapping", "sha256", "approval"}`.
  - `require_mapping_approval` must pass, and so must `mapping.check(...) == []`.
  - `inputs.network.neko_session` must equal the `STAGE_GATE` `upstream_session_id` on line 1.
  - The `STAGE_GATE` check itself is unchanged.
- **Refusal:** for either specialist, a prompt containing `runs/data-analyst/` with no `DATA_INPUT` line raises `ValueError("brief references data-analyst artifacts without a DATA_INPUT line; see CLAUDE.md")`.
- **No data:** returns `None` when there's no `DATA_INPUT` and no data path, leaving today's behaviour unchanged.
- **Hook order:** `check_task` (`STAGE_GATE`) first, then `check_data_input`.

- [ ] **Step 1: Write failing tests:**
  - `test_neko_data_input_ok`;
  - `test_neko_wrong_hash_refused`;
  - `test_neko_unapproved_proposal_refused`;
  - `test_neko_wrong_kind_or_layer_refused`;
  - `test_maboss_mapping_ok`;
  - `test_maboss_unapproved_mapping_refused`;
  - `test_maboss_mapping_failing_check_refused`;
  - `test_maboss_network_mismatch_with_stage_gate_refused`;
  - `test_data_path_without_data_input_refused`;
  - `test_other_specialists_unaffected`;
  - `test_no_data_unchanged`;
  - hook-level subprocess tests for one allow and one deny per specialist.
- [ ] **Step 2:** Run the focused tests. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `python3 scripts/run_tests.py`. Expected: OK.
- [ ] **Step 5:** Commit `feat(gate): DATA_INPUT checks for NeKo seeds and MaBoSS mappings`.

### Task 6: Agents, skills, reviewers and policy

**Files:**
- Modify:
  - `.claude/agents/network-curator.md`, `.claude/skills/neko-workflow/SKILL.md`;
  - `.claude/agents/boolean-dynamics-modeler.md`, `.claude/skills/maboss-workflow/SKILL.md`;
  - `.claude/skills/validate-stage/SKILL.md`;
  - `.claude/agents/scientific-reviewer.md`, `.claude/agents/reproducibility-auditor.md`;
  - `CLAUDE.md`;
  - `docs/data-workflow.md`, `docs/data-analyst-architecture.md` (roadmap: sub-project 2 implemented; a short flow section);
  - `docs/agentic-operations.md` (`mapping.py` and the `DATA_INPUT` procedure).
- Test: governance tests in `tests/codex/test_static_governance.py` and `.claude/scripts/test_agent_mcp_access.py` (keep green; add assertions only for new mandatory phrases).

**Interfaces (content to include):**
- **network-curator:** read seeds only from the `DATA_INPUT` proposal file paths (`hgnc_symbol`; all tiers unless the brief restricts them); never alter data files; report seeds absent from the database.
- **boolean-dynamics-modeler:** read the mapping named on the `DATA_INPUT` line; simulate exactly its scenarios (a context, plus each perturbation, plus the context without the perturbation as control); report one trajectory artifact path per `(context, perturbation)` pair, so the orchestrator can write `runs.json`.
- **Reviewer checklists** as in spec §6.
- **`CLAUDE.md`:** one short paragraph:
  - the flow;
  - never paste data into briefs;
  - `DATA_INPUT` formats;
  - mapping draft → discussion with the researcher → `mapping.py check` → `data_mapping` approval;
  - registry lineage and `data-derived` tags.

- [ ] **Step 1:** Edit the documents.
- [ ] **Step 2:** Run `python3 scripts/run_tests.py` and `python3 scripts/check_isolation.py --repository-only`. Expected: OK and passed.
- [ ] **Step 3:** Commit `docs: data-to-model handoff procedure for agents, reviewers and orchestrator`.

### Task 7: End-to-end smoke test

**Files:**
- Modify: `tests/integration/data_smoke.py`, `docs/data-workflow.md` (Smoke test section)

**Interfaces:**
- Add a stage after the existing data flow, run in the smoke test's temp repository:
  1. write synthetic `seed_genes`, `perturbations` and `validation_targets` proposals (rebuilding the manifest and handoff so they're approved artifacts) and a `stage_approval` (data) record through `state.py record`;
  2. call `gate.check_data_input` for a network-curator brief → it passes;
  3. write a synthetic BNET under `runs/network-curator/<s>/exports/<inv>/model.bnet` with nodes such as `EGFR`, `MAPK1`, `Proliferation`;
  4. run `mapping.py draft`, fill in the mapping programmatically, run `check` (expect no errors) and record the `data_mapping` approval;
  5. call `check_data_input` for a boolean-dynamics-modeler brief, with a `STAGE_GATE` line naming the NeKo session, but call the data part only (`STAGE_GATE` records are outside this smoke) → it passes;
  6. write synthetic trajectories (`Time` and readout columns, giving a larger drop in the test context), `runs.json`, then `mapping.py criteria --merge-into VALIDATION_CRITERIA.yaml`;
  7. run `scripts/validate/evaluate.py` → the `scenario_contrast` criterion passes.

  Print one `[ok]` line per step and keep `DATA SMOKE PASSED` last.

- [ ] **Step 1:** Implement.
- [ ] **Step 2:** Run `python3 tests/integration/data_smoke.py`. Expected: DATA SMOKE PASSED. If it fails because of code from Tasks 1–6, report BLOCKED with evidence.
- [ ] **Step 3:** Run `python3 scripts/run_tests.py` and `python3 scripts/check_isolation.py --repository-only`. Expected: OK.
- [ ] **Step 4:** Commit `test(data): smoke covers data-to-NeKo and data-to-MaBoSS handoffs`.

# Data-to-model handoffs: architecture and design rationale

**Document status:** describes the typed handoffs that carry approved data-analyst
proposals into NeKo and MaBoSS (Claude Code only, sub-project 2), tested with Claude Code
2.1.311 and `mcp-biomodelling-servers` 2.5.2. For day-to-day use, see
[data workflow](data-workflow.md); for the data analyst itself, see the
[data-analyst architecture](data-analyst-architecture.md). Where this document and the
code disagree, the code is authoritative.

## 1. Purpose and scope

The data analyst produces hashed proposals, and the researcher approves them. Getting
them into the models was manual. In a live test the orchestrator read approved seed CSVs
with an ad-hoc script and pasted the symbols into the network-curator brief. Nothing
checked that they were the approved files. The Boolean-layer proposals were also written
in data terms (drug names, cohort contrasts, prose), while MaBoSS needs exact node
names, ON/OFF states, readout nodes and machine-checkable criteria.

This sub-project makes the researcher's discussion with the orchestrator produce one
exact, checked, approved artifact, and makes the specialists consume exactly that.

**In scope:** NeKo seeds; MaBoSS contexts, perturbations, readouts and validation
criteria; per-kind proposal schemas; the mapping file and its checker; `DATA_INPUT`
dispatch checks; lineage; review checklists; the `scenario_contrast` validator.

**Not covered here:**
- BioMASS and PhysiCell data inputs;
- Codex parity (pending);
- MCP server changes, and automatic mapping (the researcher decides every row).

## 2. Key decisions and rationale

| Decision | Rationale |
|---|---|
| **Typed proposal schemas** per kind (`seed_genes`, `perturbations`, `validation_targets`), checked by `manifest.py verify`; `mutations` is removed; layers are fixed (`neko`, `maboss`) | Data-term prose cannot be mapped mechanically. Extra columns are allowed, so the analyst keeps its statistics. |
| **`DATA_INPUT` lines, never pasted data** | The motivating failure: the orchestrator pasted seed symbols into a brief, and the build decision cited seed lists by name only. A line naming session, proposal ids and hashes can be re-checked by the dispatch hook. |
| **One canonical `DATA_INPUT` line; refuse stray mentions** | Any other spelling of `DATA_INPUT`, a `runs/data-analyst` path, a bare data session id, or a session other than the one named is refused. This stops data leaking in through prose. |
| **Fail-closed hook** | `stage_gate_guard.py` exits 2 on any error, including import failures. Claude Code blocks a dispatch only on exit 2; exit 1 would let it proceed. |
| **Orchestrator-drafted mapping, discussed with the researcher, checked by script** | `CLAUDE.md` forbids silently selecting mappings, states or readouts. Node names and margins are never inferred. `mapping.py check` makes the result exact. |
| **The mapping approval binds the mapping sha256 and `outputs` equal perturbation ids plus criterion ids** | Otherwise `outputs` is decorative. Adding a criterion after approval needs re-approval. |
| **Mapping bound to the `STAGE_GATE`-approved BNET** | `inputs.network.sha256` must equal the BNET of the approved NeKo handoff, so a mapping cannot target a different export. A re-export needs a redrafted mapping. |
| **Cumulative data approvals** | Researchers approve stepwise. A proposal counts as approved if any valid `data` approval for the session, binding the current handoff hash, lists it. There is no revocation record. An earlier newest-wins rule was dropped. |
| **Perturbation overrides context on shared nodes** | A scenario is a context plus an optional perturbation, so overlaps need one rule. `mapping.py check` prints overlaps as notes. |
| **`boolean_structure` not allowed in mappings** | It validates network structure, not data-driven responses. It can still be declared directly in `VALIDATION_CRITERIA.yaml`. |
| **Criteria require the mapping approval** | `mapping.py criteria` needs `--approval` and verifies it, so unapproved mappings cannot create criteria. |
| **`scenario_contrast` validator ported** | Contrast-type targets ("drop is larger in context A than B") need it. Ported from the live-test copy with tests and review. |

## 3. Components

| Component | Role |
|---|---|
| `scripts/data/manifest.py` (`KIND_SCHEMAS`) | Required columns, enumerated values and unique keys per proposal kind; non-empty tables; kind-to-layer rules. |
| `scripts/data/approvals.py` | Finds and verifies `data` and `data_mapping` approvals in `DECISIONS.md`. |
| `scripts/data/mapping.py` | `draft`, `check`, `criteria` (and a merge into `VALIDATION_CRITERIA.yaml`). Imports the BNET node list and each method's option checker. |
| `scripts/gate.py` (`check_data_input`) | Parses and verifies the `DATA_INPUT` line for network-curator and boolean-dynamics-modeler. |
| `.claude/scripts/stage_gate_guard.py` | Dispatch hook: runs `check_task` then `check_data_input`; deny with stderr and exit 2. |
| `scripts/state.py` | Accepts `data_mapping` as a governance stage for `stage_approval` and `stage_review`. |
| `scripts/validate/scenario_contrast.py`, `evaluate.py` | Contrast validator and its registration. |
| Agent and skill instructions | `network-curator`, `boolean-dynamics-modeler`, `neko-workflow`, `maboss-workflow`, `validate-stage`, `scientific-reviewer`, `reproducibility-auditor`, and the `CLAUDE.md` rules. |
| `tests/integration/data_smoke.py` | Offline path from synthetic proposals to an evaluated `scenario_contrast`. |

## 4. Flow

The step-by-step procedure is in [data workflow](data-workflow.md). In outline:

1. **NeKo.** Seed proposals are approved (`stage` `data`). Line 1 of the network-curator
   brief is the `DATA_INPUT` line. The hook re-checks kind, layer, approval and hashes.
2. **Mapping.** After the NeKo-to-MaBoSS handoff is approved, the orchestrator runs
   `mapping.py draft`, fills it with the researcher row by row, and runs `check`.
3. **Mapping approval.** The researcher approves; a `data_mapping` `stage_approval` is
   recorded.
4. **MaBoSS.** Line 1 of the modeler brief is `STAGE_GATE`; line 2 is `DATA_INPUT` naming
   the mapping, its hash and the approval id. The hook re-runs `mapping.py check`.
5. **Criteria.** `mapping.py criteria --approval <id>` turns trajectories into criteria;
   `state.py validation-declare` declares them; `evaluate.py` evaluates them.

## 5. Contracts

- **Proposal kinds:**

  | Kind | Layer | Required columns (non-empty) |
  |---|---|---|
  | `seed_genes` | `neko` | `hgnc_symbol`, `tier` (`core`/`data`), `evidence` |
  | `perturbations` | `maboss` | `scenario_id` (unique), `context`, `entity`, `entity_type`, `targets`, `effect`, `evidence` |
  | `validation_targets` | `maboss` | `target_id` (unique), `statement`, `test_context`, `reference_context`, `perturbation`, `phenotype`, `expected`, `evidence_strength`, `evidence` |

- **Mapping file** `runs/orchestrator/<purpose>/mapping.json`: `schema_version: 1` and
  keys `inputs`, `contexts`, `perturbations`, `readouts`, `criteria`, `unmapped`. Node
  states are 0 or 1. Paths are repository-relative with no symlinks.
- **`mapping.py check`** fails on: a hash mismatch, a node missing from the BNET, a
  proposal not approved or not in the session index, a row neither mapped nor listed in
  `unmapped` with a real reason, unsupported methods or invalid options, and undeclared
  readouts. It exits non-zero and lists every problem.
- **NeKo `DATA_INPUT`** (line 1): `{"data_session", "proposals": {id: sha256}}`. Each
  proposal must be `seed_genes` for `neko`, approved, and equal to manifest and disk. The
  curator resolves ids through the session manifest and returns `blocked` on any
  mismatch.
- **MaBoSS `DATA_INPUT`** (line 2): `{"mapping", "sha256", "approval"}`. The approval is a
  `data_mapping` `stage_approval` for that mapping and hash. Its `session_id` is the NeKo
  session and must equal the `STAGE_GATE` upstream.
- **`scenario_contrast`:** drop is P(control) minus P(perturbed). It passes when
  test drop minus reference drop is strictly greater than the margin. The statistic is
  `final` or `tail_mean`; `combine` is `all` or `any`. There is no implicit tolerance.
- **Lineage:** a NeKo session built from seeds has `Derived from` = the data session and
  cites proposal ids and short hashes. A MaBoSS row cites the mapping path and short
  hash. Mapped states, perturbations and readouts get the `data-derived` tag.

## 6. Guardrails and threat model

- **Dispatch hook:** denies on any exception, any extra `DATA_INPUT` mention, a data
  path or session id without `DATA_INPUT`, a data session outside the one named, a
  proposal that is unapproved or of the wrong kind or layer, a hash mismatch, a mapping
  that fails `check`, and a mapping whose network differs from `STAGE_GATE`.
- **Approvals bind content:** the `data` approval binds the handoff hash; the
  `data_mapping` approval binds the mapping hash and the id set.
- **Instructions:** specialists read data only from the named artifacts and never alter
  them; the modeler simulates exactly the mapping's scenarios.
- **Review:** the reviewer agents have data-stage and mapping checklists (each row
  biologically justified, `unmapped` reasons sound, associations not presented as
  mechanisms).
- **Threat model:** the same as the data analyst. The controls catch accidental and
  undisciplined behaviour, not forged provenance files.

## 7. Known limitations

- **Plain-text data** with no path or session id cannot be detected.
- **Scoping is per session, not per path:** a brief may cite other files of the named
  data session.
- **Evasion spellings:** homoglyph spellings of `DATA_INPUT` and case-sensitive
  `subagent_type` matching are not caught.
- **False positives refuse:** text like `METADATA_INPUT` is refused. This is safe.
- **`mapping.py criteria` does not check** the approval's `session_id` or `outputs`; the
  dispatch gate does.
- **One `data_session` per NeKo `DATA_INPUT`.**
- **No revocation:** approvals are cumulative. Withdrawing a proposal needs a new data
  session and handoff.
- **Same-context, different-drug contrasts** are not supported by `scenario_contrast`
  mappings.
- **A re-export** of the NeKo BNET invalidates the mapping, which must be redrafted.
- **Mapping readout nodes** must be among the MaBoSS outputs approved for the run.

## 8. Roadmap

1. **Implemented:** the typed handoffs above.
2. **Later:** BioMASS and PhysiCell data inputs; Codex parity (pending, low priority);
   path-level scoping of data mentions; an explicit revocation record.

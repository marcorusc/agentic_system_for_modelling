# ODE artifact and evidence contract

## Availability and scope

The integration branch validates the richer `ode_modeler` result and records BioMASS artifacts through filesystem-only helpers. Phase 3 adds the shared CLI/dispatcher execution route and explicit ODE evidence mode. The artifact helpers do not call BioMASS, generate or execute a model, advance a scientific stage, or update shared scientific records. Phase 4 adds specialist instructions, profiles and optional setup. Live installation and client/process verification remain a Phase 5 gate before scientific ODE execution in this integration worktree; see [the workflow](ode-workflow.md).

New ODE results use the common `schema_version=1` envelope with `specialist=ode_modeler`, `stage=biomass_ode`, and **`ode.contract_version=2`**. Artifacts belong to `runs/ode-modeler/{session_id}/`. Historical unversioned ODE payloads and the experiment's `ode_dynamics_modeler` format require their original verifier. The new validator does not rewrite or alias them.

## ODE metadata

| Field | Meaning |
|---|---|
| `contract_version` | Integer 2 |
| `input_kind` | `neko`, `standalone_text`, or `reactions` |
| `document_version` | Nonnegative authoring version matching the captured snapshot |
| `revision` | Selected generated `rev_` identifier with 32 lowercase hex digits; null for an authoring draft |
| `source_identifiers`, `evidence_paths` | Source identifiers and exact session-scoped evidence paths |
| `simulation_paths` | Listed `simulation.json` paths for numerical results being claimed |
| `export_status` | `pending`, `provisional`, `approved`, or `exported`, as defined below |
| `upstream_manifest` | NeKo input: project-contained handoff identifying the exact source session |
| `standalone_authorized` | True for an explicitly authorized standalone workflow |
| `source_sha256` | Text input: original source hash matching the snapshot |
| `construction_request` | Reaction input: exact bounded authorized construction request |
| `revision_path` | Project-relative captured directory for the selected generated revision |
| `workflow_authorization` | Provisional bundle: decision ID, immutable approval snapshot path, SHA-256 |
| `export_approval` | Approved/exported revision: decision ID, immutable approval snapshot path, SHA-256 |
| `bundle_path` | Provisional/exported status: listed, verified ZIP |

`manifest.json` must contain the common identity fields and the identical `ode` object. A Markdown report and hashed artifact entries accompany it. Unknown scientific units stay explicitly unknown; the validator does not infer mechanisms or numerical assumptions.

## Read-only specialist and parent completion

Before project capture, a specialist may return a metadata-only `needs_approval`
result with `export_status=pending`, `artifacts=[]`, `simulation_paths=[]`, and
external inventories in `server_artifacts`. It omits project preservation claims
(`revision_path`, `bundle_path`, `workflow_authorization`, `export_approval`) until
verified copies exist. Actual server revision/version and performed operations
remain explicit. Parent recording work is distinct from scientific approval.

The current envelope requires nonempty `decisions_required` for `needs_approval`.
List operational work there with the prefix `Technical parent recording only`,
for example: “Capture and verify the inventory, record the already approved
preservation authority, and create the provisional completion; no new researcher
approval is requested.” Keep actual scientific decisions as separate entries.
The parent performs this recording work rather than sending it as an approval question.

The orchestrator uses the already approved task scope to record preservation
authority against the returned session ID, captures the inventory, and produces a
separate validated provisional completion with matching manifest/report and hashes.
The original specialist result remains immutable. A new-session invocation need not
stop solely to create the session-bound authority record; the researcher authorization
must already exist before it executes. This is the existing version-2 contract's
recording sequence, not an additional scientific gate.

## Preservation and acceptance

| `export_status` | Bundle requirement | Recorded authority |
|---|---|---|
| `pending` | No preserved bundle claim | Existing workflow prerequisites; no conclusive approval claim |
| `provisional` | Complete, verified bundle | Already approved bounded workflow |
| `approved` | No preserved bundle claim | Exact session/revision conclusive-export approval |
| `exported` | Complete, verified bundle | Exact session/revision conclusive-export approval |

The top-level `completed` status means the technical task and artifacts passed verification. It does not grant scientific acceptance. A verified candidate may instead use `needs_approval` with explicit outstanding decisions and `recommended_next_stage=null`. All generated-revision, simulation, approval and bundle claims receive artifact checks regardless of top-level status. A metadata-only draft must have an empty project artifact list and omit preservation claims such as `revision_path`. It may identify a server-generated revision before local capture, but that ID alone does not establish artifact verification.

Saving a candidate never changes the scientific registry's `Handoff` to `exported`. The orchestrator remains responsible for checking the approved scope, resolving scientific choices, and controlling stage transitions.

### Existing workflow authorization for provisional saving

The orchestrator records the **already approved** bounded workflow once in `DECISIONS.md`, including its scope and the researcher's instruction. It saves an immutable copy in the ODE session directory and records `decision_id`, `path` and `sha256` in `workflow_authorization`. The validator matches this block in both records:

```text
Decision: ode-draft-workflow-1
Status: approved
Session: FULL_BIOMASS_SESSION_ID
Action: preserve_ode_candidates
```

Do not request a fresh approval merely to populate this record or save a later candidate within that same scope. A new or expanded scientific scope still requires the applicable researcher decision. The session-bound record can authorize preservation of successive candidate revisions; it cannot approve their assumptions or authorize their simulation.

### Conclusive export approval

For `approved` or `exported`, `export_approval` references the immutable session-scoped decision snapshot. Both it and `DECISIONS.md` must contain:

```text
Decision: ode-final-export-1
Status: approved
Session: FULL_BIOMASS_SESSION_ID
Revision: rev_0123456789abcdef0123456789abcdef
Action: export_model_bundle
```

The block retains the source branch's meaning of conclusive export approval. A provisional export of the same tool is governed by the workflow record above. Later unrelated decisions may be appended without invalidating the snapshot. A different model revision needs the appropriate new scientific acceptance; an old approval does not transfer automatically.

These checks establish consistency, not proof of researcher identity or scientific truth. The orchestrator must derive the records from actual user authorization and apply the exact tool permissions when dispatching work.

## Artifact verification

A captured generated revision includes `integrity.json`, `model.txt`, `model_summary.json`, `snapshot.json`, `request.json`, and `generated_model/ode.py`, plus every other file in its complete inventory. The validator checks file hashes, session/revision ownership, matching authoring version, source lineage, and Python syntax without executing generated code.

A claimed successful simulation must refer to the selected revision, report successful typed numerical conditions and finite increasing time bounds, and include nonempty species and observable CSVs with finite numerical values. Both CSVs must contain actual data columns, cover every reported condition and the stated time bounds, and share the same increasing time grid. These checks do not establish biological validity, correct stoichiometry or quantitative agreement with data.

Provisional and conclusive ZIPs receive the same checks: valid ZIP/CRC, unique safe members, no symlinks or file/directory prefix conflicts, exact model file inventory including `integrity.json`, matching revision bytes, and required reproduction entrypoints. Integrity remains mandatory while scientific approval is pending.

## Capture helpers

Supply an explicit returned server inventory; do not discover scientific state by scanning arbitrary installations:

```text
python scripts/codex/record_ode_artifacts.py --server-root INSTALLATION --session-id SESSION --capture-id UNIQUE --inventory inventory.json
python scripts/codex/record_neko_ode_handoff.py --server-root NEKO_INSTALLATION --manifest EXPORTED_MANIFEST --capture-id UNIQUE
```

The BioMASS recorder validates session ownership, source scope, hashes and symlinks before publishing `runs/ode-modeler/{session}/captures/{capture}/`. The NeKo recorder preserves byte-identical original manifest and network files, creates a separate relocated import manifest, and records required original/relocation provenance under `runs/network-curator/{session}/ode-handoffs/{capture}/`.

Both helpers write and verify a hidden staging directory, then rename it once to the final capture name. A persistent per-target POSIX lock prevents cooperating recorders from replacing one another's capture. Existing captures are immutable; repeat invocation with the same ID is refused. Source files are untouched.

An interrupted operation can leave a hidden staging directory and a lock file. Neither is a published capture. Do not unlink persistent locks during normal operation or automatically delete failed scientific artifacts. A process killed after publication may leave a complete capture without having returned its receipt: inspect it rather than rerunning a modelling mutation. These helpers do not provide automatic recovery, power-loss durability, or protection against noncooperating processes modifying the destination concurrently.

## ODE claim evidence

Claim reviews retain the source branch's distinct `mechanism`, `kinetic-law` and `quantity` schema. Reports explicitly record source access, biological context, support/conflict, PMID/DOI, limitations and locations. Reported quantities keep their original text and units, with null for unavailable units; no conversion is inferred. A supported claim requires accessible supporting evidence.

The orchestrator writes one immutable report with:

```text
python scripts/codex/write_literature_report.py --session-id SESSION --claim-id CLAIM --draft-file draft.md
```

Reports live at `evidence/reports/{biomass_session_id}/ode/{claim_id}.md`. Existing edge-report arguments and behavior remain available. Completed ODE literature handoffs require `review_kind=ode` and explicit validation with `--review-kind ode` (or the matching validator argument). An unspecified review mode remains edge-only. The dispatcher and CLI transport `review_kind=ode` explicitly and require `record_session_id` for an ODE review. Invocation records are stored under `runs/ode-modeler/{biomass_session_id}/specialist-invocations/`; the expected mode and session are retained in provenance, including early failure records.

Evidence schema validation checks structure and declared access; it cannot establish that a citation supports the biological claim. Literature gathering still uses a bounded isolated reviewer and the existing source/approval rules.

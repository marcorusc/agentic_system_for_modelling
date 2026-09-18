# ODE formulation and BioMASS workflow

## Availability

The ODE route uses the richer `ode_modeler` contract and the dispatcher's shared
runtime. Phase 4 prepares skills, profiles and optional setup; live installation
and ODE process verification remain a Phase 5 deployment gate. Do not start
scientific ODE work in this integration worktree before that gate is verified.
A source profile or passing software fixture is not proof of installed readiness.
See [setup](automatic-setup.md) and [integration plan](integration/ode-dispatcher-plan.md).

## Formulation and inputs

Compare the objective, observables, available measurements, molecular-state
resolution, mechanisms, time scales and parameter uncertainty before recommending
Boolean dynamics, mechanistic ODEs, or both. Record the researcher's choice in
`MODEL_SPEC.md` and `DECISIONS.md`. Comparisons use separate sequential sessions
and representation provenance; sharing a topology requires approval. Successful
execution with hypothetical numbers establishes executability only.

| Input | Required provenance |
|---|---|
| NeKo graph | Approved topology/evidence, an exported `neko-to-biomass` handoff, exact upstream session and verified project copy |
| Standalone Text2Model | Explicitly authorized source, original text/hash and null upstream lineage |
| Reaction construction | Explicit bounded construction request, source identifiers and null upstream lineage |

The NeKo specialist performs `export_biomass_handoff` only under an approved export
workflow. Preserve edge IDs, references and biological context. BNET rules are not
biochemical reactions; signed edges do not establish molecular composition or
kinetic laws. BNET and Boolean connectivity constraints are not prerequisites for
the ODE handoff. Topology choices still retain their existing approval gates.

## Bounded authoring workflow

1. Resolve input and active lineage from durable files. For NeKo input, require
   the source registry row to have `Handoff=exported` and verify the graph handoff.
   Create a fresh BioMASS session for a new hypothesis through the ODE specialist.
2. Inspect exact identifiers, document version, evidence, configuration and coverage.
   Return unresolved mechanism, kinetic-law and quantity claims to the orchestrator
   for bounded literature review. The ODE specialist never delegates or searches.
3. Assemble the requested candidate within the approved drafting scope. Keep
   proposed mechanisms, molecular-state mappings, approximations, units and
   numerical assumptions distinct from accepted inputs. When the researcher requests
   a consolidated whole-model review, collect its unresolved choices together;
   do not turn ordinary candidate assembly into repeated per-reaction approvals.
4. Preview edits with the expected authoring version. Apply only edits within the
   authorized scope. Preserve stable IDs and source-edge coverage, including
   indirect/combined or unresolved edges. Never add dummy reactions or silently
   drop scientific scope. Inspect generated names before configuring quantities.
5. Whole-document, reaction-list or configuration replacement may clear settings.
   Preserve and reapply only previously approved values after inspecting the change.
   Validate, generate and inspect equations and quantity origins. Unknown units
   remain unknown; generated defaults remain proposed placeholders.
6. Preserve reproducible candidate snapshots within the already approved workflow.
   Use `export_status=provisional` and the workflow authorization record specified
   in [the artifact contract](ode-contract.md). This needs no repeated approval for
   each snapshot and grants no scientific acceptance or permission to simulate.
7. Run only requested scenarios with explicit time bounds, conditions and approved
   numerical choices. Placeholder use requires explicit approval of the actual
   values. Regenerate after authoring changes; any requested old revision must be
   identified as historical. Optional graph rendering may be skipped if unavailable.
8. Present the complete model and results for review. Conclusive bundle export and
   stage acceptance require the exact session/revision approval in the artifact
   contract. ODE-to-PhysiCell coupling, calibration and sensitivity analysis remain
   outside this integrated workflow.

## Dispatch and isolation

Codex uses `specialist_dispatcher.start_ode_modeler(task=..., approved_tools=...)`.
For an existing BioMASS session pass `record_session_id`; for a new session put the
upstream NeKo ID in the task, never in that argument. Include exact sources,
objective, input kind, authorized edits, evidence paths, proposed versus accepted
assumptions, requested scenarios and required artifacts. Exact tool permissions
express existing authorization and do not replace scientific decisions.

Read `get_specialist_events` with its sequence cursor and `get_specialist_task`
until terminal. Only `succeeded` exposes a validated handoff; its scientific status
may still be `blocked` or `needs_approval`. Preserve failed invocation artifacts.
Do not silently retry mutations after interruption or infer a live session from a
past process. Reconstruct from approved source artifacts in a fresh workflow when
that reconstruction is authorized. `restore_session` applies only to an explicitly
approved existing server session; a portable ZIP is not a server session snapshot.

CLI fallback uses the same runtime:

```text
python scripts/codex/run_specialist.py ode_modeler --prompt-file .codex-tasks/ode-task.txt
```

Add `--record-session-id` and exact `--approve-tool` entries only as applicable.
Claude delegates to `ode-modeler` with its inline BioMASS transport and local
`biomass-workflow` references. No other specialist or orchestrator may expose
BioMASS. Codex inventory preflight and execution share fixed overrides; Claude
inline isolation still requires client-level verification. Neither specialist
changes shared scientific files or advances stages.

## Returning a candidate before project capture

A new-session specialist invocation may run the complete authorized workflow through
server-side bundle export. Pass the actual researcher authorization and scope in the
task; bind its preservation record to the returned session ID during parent recording.
Do not require a bootstrap invocation solely to obtain that ID or assume session
continuity for the next workflow.

Before verified repository copies exist, the read-only specialist returns metadata-only
`needs_approval`, `ode.export_status=pending`, empty project `artifacts` and
`simulation_paths`, and the server inventory in `server_artifacts`. Omit project
capture/bundle/authority fields; include actual revision/version and report drafts.
Name parent recording work separately from scientific choices. The parent captures
and verifies files and writes a **separate** provisional completion with the matching
manifest, report, authorization snapshot and hashes. It preserves the original
specialist result. This finalization consumes the existing authorization and does
not ask for another decision just to preserve work.

The current envelope requires nonempty `decisions_required` for `needs_approval`.
List operational work there with the prefix `Technical parent recording only`,
for example: “Capture and verify the inventory, record the already approved
preservation authority, and create the provisional completion; no new researcher
approval is requested.” Keep actual scientific decisions as separate entries.
The parent performs this recording work rather than sending it as an approval question.

The server label `assumed` does not establish accepted science: distinguish proposed
mechanisms from those accepted by a recorded researcher decision. Small-subsystem
examples guide internal assembly, not external per-module approval cycles.

## Evidence review

Use the existing literature specialist with explicit `review_kind=ode` and the
full BioMASS session ID. Send at most 13 coherent literal claims, each with a stable
claim ID, kind (`mechanism`, `kinetic-law`, `quantity`), context, known PMIDs/DOIs,
and originating reaction/edge/quantity IDs. No NeKo SIF is needed for standalone
ODE work. At most two independent reviews may run concurrently across both modes.
PubMed is preferred; Codex web search needs explicit authorization. Without a
permitted backend return `blocked` rather than infer evidence.

Codex dispatches `start_literature_reviewer(..., review_kind="ode",
record_session_id=...)`; CLI fallback adds `--review-kind ode`. The reviewer returns
report drafts. The orchestrator validates/writes them through
`write_literature_report.py --session-id SESSION --claim-id CLAIM --draft-file DRAFT`.
Claude writes through its literature guard and reads the exact destination back.

Reports are immutable at `evidence/reports/{biomass_session_id}/ode/{claim_id}.md`;
invocation provenance belongs under `runs/ode-modeler/{biomass_session_id}/`.
Retry only missing reports. Explicit re-review uses a new claim ID and identifies
what it supersedes. The [evidence contract](ode-contract.md#ode-claim-evidence)
requires access limitations, source context, support/conflict and reported quantities
with original units or null. Review evidence for mechanisms and numerical values
separately. Import reviewed findings with stable evidence IDs and source links.

## Artifacts and validation

Use common envelope version 1, role `ode_modeler`, stage `biomass_ode`, and
`ode.contract_version=2`. The [artifact contract](ode-contract.md) is authoritative
for metadata, revision checks, provisional/conclusive authority and capture helpers.
Returned external files belong in `server_artifacts`, not the project artifact list.
The orchestrator captures only explicit returned inventories, writes the report and
matching manifest, and validates the completed project result before synthesis.
Preserve the immutable original specialist result and each completion capture.

Generated-revision claims require complete captured files and hashes. Simulation
claims additionally require matched revision requests, numerical conditions and
species/observable trajectories. Provisional and accepted bundles receive the same
integrity checks. The registry remains `pending` during review; a provisional
snapshot never sets `Handoff=exported` or advances the global stage.

The existing lifecycle allowlist already includes `runs/` and `evidence/`. Claude's
stage validation still requires the absent `scientific-reviewer` and
`reproducibility-auditor` definitions; report that blocker. Codex parent validation
is not independent scientific review. Syntax, numerical execution and biological
validity remain separate claims.

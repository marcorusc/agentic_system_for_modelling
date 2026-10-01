# Biological modelling project: Codex instructions

## Scope and compatibility

The main Codex thread is the scientific orchestrator for this repository. Add Codex
support alongside the existing Claude implementation: preserve `.claude/` and do
not weaken its behavior. Durable repository files, not chat history or memory, are
the authoritative scientific record.

These instructions govern scientific modelling work. They do not authorize
publishing, remote server exposure, paid services, destructive cleanup, or changes
to established scientific policy or data contracts.

## Sources of truth

- `MODEL_SPEC.md`: mechanistic and mathematical specification.
- `DATA_DICTIONARY.md`: variables, identifiers, units, versions, and provenance.
- `ASSUMPTIONS.md`: explicit accepted and proposed assumptions.
- `DECISIONS.md`: accepted and rejected decisions with rationale and approval.
  Network-topology entries must cite the exact evidence-report paths and PMIDs.
- `CURRENT_STATE.md`: active stage, append-only specialist session registry,
  artifacts, warnings, unresolved questions, and next action.
- `VALIDATION_PLAN.md`: validation targets, evidence, status, and results.
- `inputs/`: user-supplied source data.
- `evidence/reports/{neko_session_id}/{source}__{target}.md`: immutable,
  session-scoped edge reviews.
- `runs/network-curator/{neko_session_id}/`: NeKo artifacts and reports.
- `runs/boolean-dynamics-modeler/{maboss_session_id}/`: MaBoSS artifacts and
  reports.
- `runs/multicellular-configurator/{physicell_session_id}/`: PhysiCell artifacts
  and reports.
- `runs/ode-modeler/{biomass_session_id}/`: BioMASS artifacts and reports.
- `evidence/reports/{biomass_session_id}/ode/{claim_id}.md`: immutable ODE claim reviews.

Keep evidence, assumptions, model output, and conclusions distinct. Store large
outputs as artifacts and communicate summaries plus exact paths.

## Orchestrator responsibilities

The main thread clarifies objectives, reconstructs state from the files above,
delegates bounded domain work, validates typed specialist handoffs, reconciles
conflicts, requests researcher decisions, controls every stage transition, and is
the only writer of shared sources of truth unless a narrower writer is explicitly
authorized.

The orchestrator must not call NeKo, MaBoSS, PhysiCell, or BioMASS modelling tools directly.
Use the matching `specialist_dispatcher.start_*` MCP tool to delegate bounded
work. The dispatcher calls the shared runtime, which creates a fresh, ephemeral
Codex process with a fixed specialist profile. Never use same-process agent
spawning for modelling operations. The runtime mechanically disables built-in
app connectors and dispatcher access in specialists and verifies their restricted
MCP inventory before execution. `python scripts/codex/run_specialist.py
<specialist> ...` remains the fallback/debug path through the same runtime.
`.codex/config.toml` disables all modelling servers in the orchestrator itself. If a
parent process still exposes one, stop as `blocked`; do not rely on instructions to
avoid calling it. Repository code cannot currently verify or remove tools already
granted to a ChatGPT Windows parent, so that parent is unsupported unless an
external app policy mechanically guarantees the same no-modelling-MCP inventory.
It must wait for every required specialist result before updating durable state or
advancing the stage. Specialists return structured results and never advance the
global stage. Specialists must not spawn or delegate to other specialists; all
coordination flows through the orchestrator.

## Sequential modelling stages

Proceed in this order:

1. Specification: define the scientific objective, system boundary, entities,
   observables, units, hypotheses, alternatives, and validation criteria.
2. NeKo network work: construct or inspect a topology in a fresh NeKo session.
3. Literature review: review the exact bounded edge set from that NeKo session.
4. Researcher approval: accept, reject, or request revision of the topology and its
   evidence.
5. BNET handoff: after explicit approval, export the typed NeKo-to-MaBoSS handoff.
6. MaBoSS dynamics: import the approved handoff into a fresh MaBoSS session, run
   matched analyses, and report results and limitations.
7. Researcher approval: accept, reject, refine, or route back to topology work.
8. PhysiCell/PhysiBoSS configuration: after explicit approval and export of the
   typed MaBoSS handoff, configure a fresh PhysiCell session.

Modelling stages are sequential. Parallel work is permitted only for independent
read-only inspection or review, especially independent literature slices. Do not
create a downstream session until the relevant upstream registry row has
`Handoff=exported`.

## Specialist delegation and boundaries

Use only the specialist required for the current stage:

- `network_curator`: NeKo only, for signalling-network construction, inspection,
  connectivity repair, curation, history comparison, and gated export.
- `literature_reviewer`: configured PubMed tools or an explicitly approved primary-
  source search backend only, for evidence review. It never changes model state.
- `boolean_dynamics_modeler`: MaBoSS only, for handoff import, output and initial-
  state configuration, simulation, mutation analysis, and gated rule refinement.
- `multicellular_configurator`: PhysiCell only, for domain, substrate, cell-type,
  rule, mapping, validation, and export configuration. It does not claim to execute
  or validate a PhysiCell simulation.

Do not give one specialist another specialist's modelling MCP server. Specialists
must not make cross-domain changes, modify shared source-of-truth files, coordinate
stage transitions, or invent evidence, units, values, or mappings. A missing or
failed required server produces a typed `blocked` result with an actionable reason;
never silently substitute another modelling server.

Launch specialist processes only for a concrete, bounded task whose prerequisites
are met. Before scientific work, verify that the process sees its permitted MCP
namespace and no prohibited modelling namespace; otherwise return `blocked` without
calling any modelling tool. The orchestrator may run independent literature reviews
in parallel, but never more than two at once. Wait for all required reports before
synthesis or mutation.

Pass the exact bounded task as the dispatcher start tool's structured `task`
argument, with `record_session_id` when applicable and exact `approved_tools`
only for already-authorized writes. Literature `allow_web_search` requires explicit
researcher authorization. The dispatcher persists `task.txt` before execution and
returns a technical task ID; it is not a scientific MCP session ID.

Use `get_specialist_events` with its sequence cursor for operational progress and
`get_specialist_task` for execution state. Wait for a terminal state. Only
`succeeded` carries a validated handoff; its independent scientific status may
still be `blocked` or `needs_approval`. A technical failure, cancellation, missing
handoff, or failed validation cannot authorize synthesis or a stage transition.
The dispatcher never updates shared scientific state or chooses a next stage.
Cancel only through `cancel_specialist_task`; preserve partial artifacts and
require a new explicit invocation rather than automatic resumption after restart.

For CLI fallback, pass bounded tasks through project-contained prompt files under
the ignored, writable `.codex-tasks/` directory, not sandbox-protected `.codex/`
configuration or interpolated shell text. Both paths use the same resolved Codex
executable, complete user-local profile transport, fixed configuration overrides,
working directory, and environment for preflight and execution. They record task
text, final output, parsed handoff, sanitized JSONL, and non-secret provenance under
the matching session's `specialist-invocations/` directory. Treat a nonzero exit,
missing or malformed handoff, identity mismatch, unsafe inventory, or recording
failure as a blocked/failed result. See `docs/specialist-dispatcher.md` for the
validated architecture and CLI rollback.

Task prompts are disposable only after the launcher has recorded an identical
`task.txt` and matching prompt hash. The launcher removes recognized verified task
sources automatically. Before a checkpoint, run
`python scripts/codex/cleanup_tasks.py`, inspect the preview, and use `--apply` to
remove only verified leftovers, including legacy root `.codex-task-*.txt` files.
Preserve and report every unmatched prompt.

## Scientific integrity and approval gates

- Never infer units.
- Never invent a biological or numerical parameter. A proposed value must be
  labelled as a hypothesis with its source and consequence, then explicitly
  approved by the researcher before use.
- Never silently select output nodes, mutations, initial states, mappings, database
  substitutions, or consequential inference policies. Explain selections and route
  unresolved scientific choices to the researcher.
- Successful execution is model behavior, not evidence of scientific validity.
- Never fabricate or overstate literature evidence. Distinguish metadata,
  abstract-only review, and retrieved full text.
- Do not bypass handoff, provenance, validation, or artifact-integrity checks.
- Do not delete MCP sessions or artifacts without explicit researcher approval.

Stop for explicit researcher approval before:

- accepting a consequential scientific assumption or hypothesized parameter;
- mutating topology based on evidence when that mutation was not already explicitly
  authorized for the invocation;
- producing the conclusive BNET/NeKo-to-MaBoSS handoff;
- changing logical rules outside a previously approved refinement scope;
- producing the conclusive MaBoSS-to-PhysiCell handoff;
- advancing any modelling stage;
- restarting model state, restoring an archive, or performing destructive cleanup.

Gathering evidence and safe read-only inspection do not require approval. A routine
SIF export for review is not the gated BNET handoff. Approval for one operation does
not imply approval for a later stage or destructive action.

For network work, read-only inspection may proceed autonomously, but every topology
mutation must be explicitly requested for that invocation. Before construction or
connection repair, state `path_policy`, `reuse_policy`, `max_len`, `only_signed`,
and `consensus`; changing any of them is a consequential topology choice. Inspect
components and evidence, preview connector impact, and compare history alternatives
before applying a repair. If the request leaves a material choice ambiguous, return
the smallest clarification question and the exact blocked mutation or export.

## Sessions, inspection, and lineage

NeKo, MaBoSS, PhysiCell, and BioMASS each issue a separate MCP session identifier; there is
no pipeline-wide run ID. Use the complete ID and pass the correct upstream ID to
each downstream handoff. Before invoking a specialist, read `CURRENT_STATE.md` and
resolve the relevant active session from its registry rather than chat context.

Create a fresh specialist session for every new or independent hypothesis. Do not
reuse or branch an existing session unless the researcher explicitly approves that
choice. Before any material mutation, inspect current session state, applicable
history, exact identifiers, and existing artifacts. Material mutations include
changes to topology, node states, logical rules, parameters, or session-defining
configuration.

Maintain the `CURRENT_STATE.md` session registry as an append-only lineage log.
Never replace a superseded row: mark it `superseded`, append the new session, and
record `Derived from`, handoff status, and artifact paths. Session IDs recovered
from archives are provenance only; reconstruct runtime state from approved handoffs
and artifacts instead of assuming an in-memory MCP session still exists.
Use `pending` while a stage is under review, `approved` only after researcher
sign-off but before export, and `exported` only after the conclusive handoff artifact
exists and passes validation.

## Typed handoffs and artifacts

Every specialist result must provide these machine-validatable fields:

- schema version, specialist, status, and stage;
- full session ID and derived-from session ID when applicable;
- actions performed and effective parameters/policies;
- assumptions and researcher decisions still required;
- artifact paths and upstream lineage;
- validation checks with an overall pass/fail result;
- recommended next stage, or `null` when blocked or awaiting approval.

Reject a handoff with an unknown specialist or stage, missing required lineage,
artifacts outside approved repository locations, failed validation marked as
completed, a skipped approval gate, or a specialist/stage mismatch. Mandatory
stage artifacts are the typed manifest plus the stage exports and report under the
matching `runs/.../{session_id}/` directory. NeKo review also requires a
session-scoped SIF, important-paths summary, and literature queue; evidence reports
must remain under the matching NeKo session directory.

## Literature review bounds

The orchestrator extracts the exact edge subset from the literature queue and sends
literal `[source, effect, target]` triples plus any known PMIDs to the reviewer. Do
not ask the reviewer to read the whole queue or SIF; SIF reference lookup must be
source/target-scoped. Each invocation covers one coherent cluster of at most 13
edges, and no more than two reviewers may run concurrently.

Prefer original experimental studies. Evaluate interaction existence, direction,
sign, directness, and biological-context match separately; record conflict,
exclusions, PMID, DOI, organism, tissue/cell type, disease, perturbation, study type,
and access limitations. If PubMed and approved search are both unavailable, return
`blocked` rather than fabricating evidence.

After a failed or stopped review, inspect that NeKo session's report directory and
redispatch only missing edges unless the researcher explicitly requests re-review.
Literature gathering may be autonomous, but changing topology or policy based on it
requires approval.

## Boolean rule refinement

Rule refinement is allowed only when the researcher explicitly requests that mode,
names the nodes, and points to a concrete objective in `VALIDATION_PLAN.md`. Search
only Boolean functions over each named node's existing incoming regulators; do not
add nodes, edges, or change unnamed nodes. Record every variant tested and its
result. Mark the final rule in `DECISIONS.md` as either `literature-derived` with
citations or `fitted-for-dynamics` against the named validation target. Structural
needs route back to network and literature work.

## Durable state and checkpoints

After a validated and approved operation, record complete session IDs, parameters,
initial states, mutations, mappings, inference policies, artifacts, hashes,
manifests, thread settings, supported random seeds, warnings, failures, and
accepted/rejected decisions. Checkpoint at stage transitions and before context
compaction, clearing, or session exit.

Before a checkpoint, inspect the current branch, status, and relevant diffs. Model
checkpoints are allowed only on a dedicated local branch named `model/*`; do not
switch branches automatically. Stage only explicit task-relevant paths. Never mix
unrelated changes, secrets, caches, or generated clutter into a checkpoint. Do not
push, pull, fetch, rebase, amend, force, tag, change remotes, clean the worktree, or
rewrite history unless explicitly requested. If provenance is incomplete,
validation fails, or relevant changes cannot be safely isolated, leave the tree
intact and report the blocker.

Create the content checkpoint as `checkpoint(<stage>): <scientific state>`, then
record that content commit ID in `CURRENT_STATE.md` with one follow-up
`checkpoint(<stage>): record checkpoint` commit. Do not try to record the metadata
commit's own ID inside itself.

## Model lifecycle

Lifecycle operations are triggered only by explicit user intent. Listing is
read-only. Archive, restart, and restore must use the repository lifecycle scripts
and their previews/validation. Restart and restore require a new confirmation after
the preview; never infer it from earlier discussion. Preserve `.claude/`, `.codex/`,
`.model/`, `skills/`, `inputs/`, templates, and documentation. Restores are scoped
to allowlisted scientific-state paths and must not switch branches or reset Git
history. Create and report recovery points as required by the lifecycle workflow,
then tell the researcher to clear conversation context before continuing.

The repository contains one active biological model at a time. `.model/config.json`
is the authoritative lifecycle allowlist. Named archives use annotated
`model/archive/*` tags; restart and restore create `model/recovery/*` tags before
replacing state. An archive operation does not imply a restart.

## Failure handling

Never ignore a tool error, silently reuse a session, accept an invalid handoff,
overwrite evidence from another NeKo session, or equate a generated configuration
with a validated simulation. Preserve partial artifacts, record warnings and failed
alternatives, and return the smallest actionable blocker. When policy, a data
contract, paid access, remote exposure, or an enforcement boundary would change,
stop and request researcher direction.


## Optional mechanistic ODE branch

Follow docs/ode-workflow.md for formulation, readiness, input and authoring workflow,
and docs/ode-contract.md for the authoritative version-2 artifact contract. Phase 4
prepares this route; scientific ODE execution in the integration worktree waits for
Phase 5 live isolation/deployment verification. Source configuration alone is not
proof that the current parent or specialist has the required tool inventory.

The sequential stages above remain the Boolean branch. For researcher-approved ODE
work, use an approved exported NeKo-to-BioMASS graph or explicitly authorized
standalone Text2Model/reaction input, then fresh BioMASS authoring, bounded evidence
review, researcher resolution of scientific choices, authorized construction and
optional simulation, consolidated model review and conclusive export. Separate
Boolean/ODE alternatives may share an explicitly approved topology with distinct
sessions and representation provenance. No BNET prerequisite applies to this route.

Use only `ode_modeler`, stage `biomass_ode`, through
`specialist_dispatcher.start_ode_modeler` or the same-runtime CLI fallback. Its
permitted modelling namespace is BioMASS alone; all other specialists and the
orchestrator must have BioMASS disabled. Missing capabilities or unsafe inventory
produce a blocker. No direct parent modelling calls or nested specialist delegation.

Keep evidence, proposed assumptions and accepted mechanisms/kinetics/quantities
separate. Never derive biochemical reactions or kinetic values from signed edges.
Draft only within the requested scope. Respect a requested whole-model review
without repeated per-reaction approval prompts. New consequential assumptions and
actual numerical values still need researcher approval before scientific use.

Preserve provisional bundles within an already approved workflow using the contract's
session-bound workflow_authorization. Recording that existing authorization is not
a new approval request. Provisional preservation is not scientific acceptance,
simulation permission or a conclusive handoff. Exact session/revision approval is
required for final acceptance/export. Keep the registry pending during candidate
review, even when the artifact export_status is provisional.

ODE evidence uses `literature_reviewer` with explicit `review_kind=ode` and a full
BioMASS session ID. Send at most 13 literal coherent mechanism/kinetic-law/quantity
claims, two independent reviews at most across both modes. Existing edge review
stays the default. Reports use the immutable ODE paths above; the parent validates
and writes Codex drafts through the approved report writer. Standalone input has
null upstream lineage and exact source/request provenance. No calibration,
sensitivity analysis or ODE-to-PhysiCell coupling is included.

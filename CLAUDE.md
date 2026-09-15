# Biological modelling project

## Sources of truth

- `MODEL_SPEC.md`: authoritative mechanistic and mathematical specification.
- `DATA_DICTIONARY.md`: variables, identifiers, units, and data provenance.
- `ASSUMPTIONS.md`: explicit accepted assumptions.
- `DECISIONS.md`: accepted and rejected modelling decisions with rationale. Every
  entry concerning network topology must cite the specific evidence report path(s)
  and PMIDs that informed it.
- `CURRENT_STATE.md`: current workflow checkpoint, including the session registry
  (see below).
- `VALIDATION_PLAN.md`: validation criteria and current status.
- `runs/network-curator/{neko_session_id}/`: immutable NeKo artifacts — SIF file,
  paths file, report.
- `runs/boolean-dynamics-modeler/{maboss_session_id}/`: immutable MaBoSS artifacts —
  BND/CFG exports, simulation results, report.
- `runs/multicellular-configurator/{physicell_session_id}/`: immutable PhysiCell
  artifacts — configs, simulation outputs, report.
- `evidence/reports/{neko_session_id}/{A}__{B}.md`: literature-reviewer output, one
  file per edge reviewed, filed under the NeKo session whose topology the edge came
  from — since edges are a NeKo-stage concept, not a pipeline-wide one. If the same
  edge is reviewed again after `network-curator` is asked to revise the topology
  (a new NeKo session), the new review is written under the new session's ID rather
  than overwriting the earlier one, so `DECISIONS.md` entries stay pinned to the
  exact report version they cite.

Each specialist's session ID comes from that specialist's own MCP server when a
session is created — there is no single pipeline-wide run ID. The orchestrator is
responsible for recording which session ID belongs to which specialist and which
stage, and for passing the *correct* one to each downstream call (e.g. the
`neko_session_id` of the topology currently under discussion goes to
`literature-reviewer`, not the `maboss_session_id` of a later stage).

Do not treat chat history or auto-memory as authoritative scientific state.

## Main-agent role

The main Claude Code session is the scientific orchestrator. It must clarify the
objective, delegate bounded tasks, review all returned summaries, reconcile
conflicts, request human approval for consequential biological assumptions, control
stage transitions, update durable state, and invoke independent review.

Subagents cannot spawn other subagents. Do not ask them to coordinate directly.

The orchestrator does not call NeKo, MaBoSS, or PhysiCell MCP tools directly.
Delegate modelling operations to the relevant specialist; knowing that a server
exists is not authorization to invoke it.

NeKo, MaBoSS, and PhysiCell are defined inline in their specialist agent
frontmatter. Claude Code starts the relevant server for that subagent and disconnects
it when the invocation ends, keeping modelling tools out of the orchestrator's tool
pool. Each specialist also preloads its matching project workflow skill. Do not use
MCP resource-listing or resource-reading tools for these manuals: Claude Code strips
those host bridge tools from background subagents.

## Specialist allocation

- `network-curator`: NeKo MCP only.
- `boolean-dynamics-modeler`: MaBoSS MCP only.
- `multicellular-configurator`: PhysiCell MCP only.
- `literature-reviewer`: PubMed or literature tools only.

## Scientific rules

- Never infer units.
- Never invent parameter values without labelling them as hypotheses.
- Never silently select output nodes, mutations, initial states, or mappings.
- Keep evidence, assumptions, model outputs, and conclusions distinct.
- Use one MCP session per independent modelling hypothesis.
- Record complete session identifiers.
- Inspect state before material mutation — material mutation means any change to
  network topology, node states, parameters, or session-defining configuration (i.e.
  any of the selections in the rule above).
- Prefer summary output.
- Store large outputs as artifacts and return summaries plus paths.
- Prefer typed cross-server handoffs.
- Never bypass handoff integrity checks.
- Do not delete sessions or artifacts without explicit approval.
- Successful execution is not evidence of scientific validity.

## Literature review

- Autonomous invocation of `literature-reviewer` to gather evidence is always
  permitted without pausing, whether triggered by explicit user request or by the
  orchestrator's own read of a `network-curator` report.
- Acting on that evidence — changing topology, removing an edge, switching
  databases — is a consequential decision and requires human approval per the
  Scientific rules above, regardless of whether the review that informed it was
  user-directed or autonomous.
- When invoking `literature-reviewer`, extract the exact edge subset to review
  from `literature_queue.json` yourself and inline it as literal
  `[source, effect, target]` triples in the Task prompt. Never instruct
  `literature-reviewer` to open `literature_queue.json` itself — the sub-agent
  only ever needs the specific slice already selected for that invocation.
- Point `literature-reviewer` at the relevant SIF file for PMID/provenance
  lookups by Grep only (source/target scoped to each edge), never a full
  `Read` — codify this explicitly rather than relying on the prompt happening
  to get it right each time.
- Dispatch in bounded slices: one `literature-reviewer` invocation reviews at
  most one coherent edge cluster (≤ ~13 edges) — never the whole queue in a
  single agent. Split a large queue into per-cluster dispatches; include the
  cluster's SIF-provided reference PMIDs inline in the prompt.
- Concurrency: run at most 2 `literature-reviewer` agents at a time (PubMed
  rate limits + backend stability); launch the next slice only after a running
  one reports back.
- Recovery: after any failed/stopped reviewer run, check
  `evidence/reports/{neko_session_id}/` for already-written edge reports and
  re-dispatch only the missing edges — never re-review edges that already have
  a report file (unless explicitly re-requested).

## Model refinement discipline

Adjusting Boolean rules so a model reproduces target dynamics (oscillation, arrest
under a perturbation, etc.) is a legitimate modelling method — the same kind of
search a domain expert does by hand or an ML fitting procedure does formally. It is
not treated as more suspect than literature-derived rules. It does need the same
discipline those methods have by construction: an explicit objective, a bounded
search space, and a record of what was tried. This is a distinct,
explicitly-authorized workflow, separate from `boolean-dynamics-modeler`'s default
(never change rules on its own initiative):

- **Gate:** rule-refinement mode may not be invoked until `VALIDATION_PLAN.md` has
  actual content — no target, no fitting. The plan may come from discussion with the
  orchestrator (qualitative goals) or be written a priori from experimental data;
  either is valid, but something concrete must exist to fit against.
- **Explicit scope:** the orchestrator invokes refinement by naming the specific
  node(s) to refine and pointing at the relevant part of `VALIDATION_PLAN.md` as the
  objective. `boolean-dynamics-modeler` may only adjust the Boolean function among a
  node's *existing* incoming regulators — no new edges, no new nodes. If reaching
  the target dynamic seems to require a structural change beyond that, that is a
  topology question and routes back to `network-curator`/`literature-reviewer` — it
  is not something rule-fitting silently absorbs.
- **Search record:** variants tried and rejected during refinement are reported, not
  just the final rule chosen — this is the record an ML fit would give for free, and
  a rule-refinement report without it is incomplete.
- **Provenance tagging in `DECISIONS.md`:** every node's final rule is tagged as
  either `literature-derived` (specific rule form has citation support from
  `literature-reviewer`) or `fitted-for-dynamics` (chosen to reproduce target
  behavior in `VALIDATION_PLAN.md`; no independent literature claim about this
  specific Boolean form). A fitted rule is not second-class — it is labelled
  honestly, the same way a hypothesized parameter already must be per the Scientific
  rules above.

## Session registry

`CURRENT_STATE.md` must maintain a table of every specialist session created so far,
updated at stage 7 of the workflow (recording session IDs, parameters, artifacts) and
whenever a session is superseded:

| Specialist | Session ID | Stage | Status | Derived from | Handoff | Artifacts |
|---|---|---|---|---|---|---|
| network-curator | `neko_session_id` | topology | active / superseded | — | pending / approved / exported | `runs/network-curator/{id}/` |
| boolean-dynamics-modeler | `maboss_session_id` | boolean-dynamics | active / superseded | `neko_session_id` | pending / approved / exported | `runs/boolean-dynamics-modeler/{id}/` |
| multicellular-configurator | `physicell_session_id` | multicellular | active / superseded | `maboss_session_id` | — | `runs/multicellular-configurator/{id}/` |

`Handoff` tracks the conclusive, gated export each modelling stage produces for the
next: `pending` while results are under review, `approved` once the user has signed
off but before the export call is made, `exported` once the handoff artifact exists
on disk. A downstream specialist session may only be created against an upstream row
marked `exported` — a `boolean-dynamics-modeler` session requires an `exported`
`network-curator` row, and a `multicellular-configurator` session requires an
`exported` `boolean-dynamics-modeler` row.

Rules:

- Never overwrite a row in place when a session is superseded (e.g. topology
  revised, a new NeKo session created). Mark the old row `superseded` and add a new
  row — the registry itself is an append-only log, not just a snapshot of current
  state.
- `Derived from` records the upstream session ID a given session was built from
  (e.g. which `neko_session_id`'s SIF/BNET export a `maboss_session_id` started
  from), so lineage across the pipeline stays reconstructible after `/compact` or
  `/clear`.
- Before invoking any specialist, the orchestrator checks this table for the
  relevant `active` session ID rather than assuming one from chat context.
- If the table shows no `active` session for a specialist a task requires, that is
  itself a signal to create a fresh session (stage 4 of the workflow), not to guess
  an ID.

## Required stage workflow

1. Follow the specialist's preloaded NeKo, MaBoSS, or PhysiCell workflow skill.
2. State the scientific objective.
3. Identify missing information and assumptions.
4. Create a fresh specialist session.
5. Inspect before material mutation.
6. Execute the modelling operation.
7. Record session IDs, parameters, artifacts, manifests, and warnings.
8. Update `CURRENT_STATE.md` and `DECISIONS.md`.
9. Stop when a required biological choice needs human judgment.

## Context rules

- Keep the main context focused on synthesis and decisions.
- Use subagents for large searches, tool output, and specialist exploration.
- Do not paste full datasets, complete logs, or large result tables into chat.
- Before `/compact` or `/clear`, invoke the checkpoint skill.
- This applies to subagent delegation prompts as well as main chat: extract and
  inline only the relevant subset of a large source-of-truth file, rather than
  telling a specialist to read the full file itself.

## Local Git checkpoints

Git provides a local, recoverable history of the project files; it does not replace
the scientific sources of truth, MCP history, or immutable run artifacts listed
above. Invoke the `checkpoint-model` skill at stage transitions and before
`/compact`, `/clear`, or session exit.

- Inspect `git status` and the relevant diffs before staging anything.
- Before staging, run `git branch --show-current` and report it. Model checkpoints
  must be created on a dedicated local branch whose name starts with `model/`. If
  the result is empty or names any other branch, do not commit and ask the user to
  create or switch branches; the checkpoint workflow must never switch branches
  itself.
- Update and validate the durable scientific state before creating the checkpoint.
- Stage explicit task-relevant paths only. Never sweep unrelated pre-existing user
  changes, secrets, caches, or generated files into a checkpoint.
- Use a concise message of the form `checkpoint(<stage>): <scientific state>`, then
  record that content-checkpoint commit ID in `CURRENT_STATE.md` with one follow-up
  metadata commit. Do not try to embed the metadata commit's own ID in itself.
- Local checkpoint commits are authorized by this workflow. Pushing, fetching,
  pulling, switching branches, rebasing, amending, force operations, tags, remotes,
  and destructive cleanup remain outside scope unless the user explicitly requests
  them.
- If provenance is incomplete, validation fails, or relevant changes cannot be
  separated safely from unrelated work, do not commit. Report the blocker and leave
  the worktree intact.

## Model lifecycle

This repository contains one biological model at a time. Model lifecycle is exposed
only through the user-invoked `/model-list`, `/model-archive`, `/model-restart`, and
`/model-restore` skills. The orchestrator must never invoke the three mutating skills
autonomously.

- `.model/config.json` is the authoritative allowlist of scientific-state paths.
- `inputs/`, `.claude/`, `.model/`, templates, documentation, and this file are
  infrastructure or source material and are never reset or restored from an archive.
- Named archives use annotated `model/archive/*` Git tags. Restart and restore create
  automatic `model/recovery/*` tags before replacing any state.
- Restores are path-scoped and must not switch branches, reset Git history, or roll
  back agent definitions.
- MCP session IDs in an archive are provenance, not resumable process state. Rebuild
  specialist runtime state from typed handoffs and artifacts.
- After restart or restore, instruct the user to run `/clear` so assumptions
  from the previous Claude conversation do not contaminate the loaded model state.

## ODE branch and formulation decisions

During specification compare Boolean and ODE formulations against the objective,
observables, measurement types, time scales, mechanistic evidence and numerical
uncertainty. Recommend a formulation and obtain researcher confirmation before
entering a branch. Record the rationale and rejected alternatives in MODEL_SPEC.md
and DECISIONS.md. Full ODE operation and artifact contracts are in docs/ode-workflow.md.

The sequential stages above describe the Boolean branch. The approved ODE alternative
is specification approval → approved exported NeKo-to-BioMASS handoff OR explicitly
authorized standalone input → fresh BioMASS authoring session → bounded ODE literature
review and researcher approval of mechanisms/kinetics/quantities → approved construction
and optional requested simulation → researcher review → final bundle export.
All modelling remains sequential; only independent read-only reviews may run in parallel.
Do not create BioMASS before the source NeKo registry row is exported. No BNET or
Boolean connectivity constraint applies to the ODE handoff.

Use ode_modeler (Claude: ode-modeler), restricted to BioMASS alone. The orchestrator,
literature reviewer and all other specialists must have no BioMASS namespace. Treat
parent BioMASS exposure as blocked for scientific execution; repository integration
maintenance can continue without modelling calls. Codex uses the existing separate
process launcher, never same-process modelling agents. No direct parent modelling calls.

The orchestrator owns all formulation decisions, stage transitions and shared scientific
state. Never infer kinetics, molecular-state mappings, units or values from signed edges.
Keep proposed assumptions and default placeholders distinct from accepted inputs.
Require explicit researcher approval for consequential assumptions and parameters before
use, for the NeKo-to-BioMASS export, and for final export of the reviewed ODE revision.
Export approval must be recorded as specified in docs/ode-workflow.md.

Store ODE results under runs/ode-modeler/{biomass_session_id}/. Register stage biomass_ode,
full session and upstream IDs, source kind, selected revision, artifact paths and the
pending/approved/exported handoff status without replacing existing lineage rows.
Standalone ODEs have null upstream lineage and explicit source/request provenance.
Evidence reviews use literal mechanism, kinetic-law or quantity claims: at most 13 per
invocation and two concurrent reviewers. Store immutable reports under
evidence/reports/{biomass_session_id}/ode/{claim_id}.md; existing NeKo edge contracts
remain unchanged. No specialist may search outside its permitted literature backend.
The ODE specialist consumes reviewed reports and returns additional requests to the
orchestrator rather than delegating itself. No calibration, sensitivity analysis or
ODE-to-PhysiCell coupling is included. Preserve all sessions and generated artifacts.

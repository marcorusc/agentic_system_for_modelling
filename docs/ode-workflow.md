# ODE formulation and BioMASS workflow

## Choosing a formulation

During specification compare the biological objective, state resolution, observables,
measurement types, time scales, mechanistic detail and parameter uncertainty. Boolean
models can address qualitative regulatory states; ODEs can represent continuous
quantities and kinetic trajectories when their mechanisms and numerical assumptions
are justified. Neither is the default scientific answer. Explain the recommendation,
limitations and missing data; obtain researcher confirmation and record the choice in
MODEL_SPEC.md and DECISIONS.md before entering a branch. A request to compare both
creates separate sequential hypotheses with their own sessions, never a shared ID.

The existing Boolean branch remains NeKo topology, bounded edge literature review,
researcher approval, NeKo-to-MaBoSS export, MaBoSS dynamics, approval and typed
PhysiCell export. ODE adds an alternative after specification:

1. For a network-derived model, complete NeKo topology review and obtain approval
   for `export_biomass_handoff(biological_context=...)`. Require the exact exported
   registry row and `neko-to-biomass` manifest. BNET, signed-only edges and connectivity
   are not ODE handoff prerequisites; topology policies still need explicit approval.
2. For explicitly requested standalone work, preserve the source Text2Model hash or
   bounded reaction construction request, with null upstream session lineage.
3. Create a fresh BioMASS authoring session through the ODE specialist. Import approved
   input, inspect the model and return bounded evidence/mechanism questions. Session
   creation is not approval of reaction kinetics or numerical defaults.
4. Route ODE claims to literature_reviewer, reconcile reports and obtain approval for
   proposed assumptions, molecular-state mappings, kinetics and quantities before use.
5. Author approved reactions, inspect versioned previews, configure approved quantities,
   validate, generate and inspect equations. Preserve unresolved coverage and all prior
   generated revisions. After authoring edits regenerate; do not silently simulate an
   old revision. An explicitly requested historical revision is reported as historical.
6. Optionally run explicitly authorized scenarios with explicit time bounds. Record
   all actual condition values, parameter origins, units (including unknown/null),
   outcomes and limitations. Hypothetical placeholder use needs explicit opt-in and
   approval of the actual values; successful solves do not establish biological validity.
7. Present the generated model and results for researcher review. Only after approval
   of the selected revision request `export_model_bundle`. The branch ends here; no
   ODE-to-PhysiCell handoff, calibration or sensitivity analysis is implemented.

## Specialist interface

Codex: `python scripts/codex/run_specialist.py ode_modeler --prompt-file
.codex-tasks/ode-task.txt`. For existing BioMASS sessions add `--record-session-id`.
For new sessions put the upstream NeKo ID in the prompt, not that CLI option.
Claude: delegate to `ode-modeler`. Both load `biomass-workflow`. Only BioMASS is
available to the modelling specialist. It cannot search literature, edit shared state,
spawn another specialist, or advance the global stage.

The common version-1 result envelope adds `specialist=ode_modeler`,
`stage=biomass_ode`, and an `ode` object:

| Field | Required meaning |
|---|---|
| `input_kind` | `neko`, `standalone_text`, or `reactions` |
| `document_version` | Nonnegative BioMASS authoring version |
| `revision` | Generated `rev_...` ID, or null for an authoring draft |
| `source_identifiers` | Source/citation identifiers, an array |
| `evidence_paths` | Exact immutable project evidence reports, an array |
| `export_status` | `pending`, `approved`, or `exported` |
| `simulation_paths` | Listed `simulation.json` files for claimed runs, an array |
| `upstream_manifest` | For NeKo input: original project copy of the ODE handoff |
| `standalone_authorized` | True for explicitly authorized standalone work |
| `source_sha256` | For text input: original source hash matching the snapshot |
| `construction_request` | For reaction input: exact bounded authorized request |
| `revision_path` | For completed results: project-relative generated revision directory |
| `export_approval` | For approved/exported status: decision_id, immutable approval snapshot path and sha256 |
| `bundle_path` | For exported status: listed verified ZIP |

Blocked/failed results can omit ODE metadata when no session was established.
`needs_approval` results include metadata, draft report content and outstanding work;
`artifacts` contains only valid project paths. Returned external server inventory goes
in `server_artifacts`, never in the completed project's artifact list.

The orchestrator creates `runs/ode-modeler/{session_id}/manifest.json` containing the
usual identity fields and the identical `ode` object. It writes a Markdown report,
records artifact hashes in a separate completion result, and validates that result
with the common validator. The original specialist draft and invocation are immutable.
A new invocation does not overwrite an old completion: keep versioned result/report
copies and the current manifest with its prior copy in the prior completion capture.

For final export the researcher decision is recorded in DECISIONS.md with this exact
block (replace identifiers), accompanied by rationale and the researcher's instruction:

```text
Decision: ode-export-1
Status: approved
Session: FULL_BIOMASS_SESSION_ID
Revision: rev_0123456789abcdef0123456789abcdef
Action: export_model_bundle
```

Copy the approved decision record into an immutable approval Markdown artifact under
this ODE session and list it in the completion artifacts. export_approval.path names
that snapshot and export_approval.sha256 hashes it. The same exact decision block
must remain in DECISIONS.md; later appended decisions do not invalidate the snapshot.
The snapshot hash and exact session/revision prevent accidental reuse of another
revision's approval. The orchestrator alone records the researcher's decision; the
validator checks consistency, not researcher identity or biological truth.

## ODE evidence mode

Use `literature_reviewer --review-kind ode --record-session-id <biomass-session-id>`
with a project-contained prompt file. Include at most 13 literal claims in a coherent
cluster, each with claim ID, kind (mechanism/kinetic-law/quantity), context, known
PMIDs/DOIs, and originating reaction/edge/quantity identifiers. No more than two
independent reviews run concurrently. Existing edge-review invocations default to
`review_kind=edge` and keep their existing contract. No available PubMed or explicitly
authorized web backend yields a typed blocked result.

ODE review results use `review_kind=ode`, stage=literature_review, the BioMASS session
ID and null derived_from_session_id. Invocation provenance is stored under the ODE
session's specialist-invocations directory. Evidence is written once per claim at
`evidence/reports/{biomass_session_id}/ode/{claim_id}.md`. Retry only missing reports.
A requested re-review uses a new claim ID and identifies the report it supersedes.

Codex's orchestrator invokes `python scripts/codex/write_literature_report.py
--session-id <id> --claim-id <claim> --draft-file <draft>`; Claude's reviewer writes
through its extended guard and reads the report back. Neither writes shared state.
Reports use this layout; Sources and Reported quantities are literal JSON arrays:

```markdown
## ODE claim: binding_mechanism
**Claim:** The specified species form the proposed complex in the stated context.
**Kind:** mechanism
**Verdict:** insufficient evidence
**Confidence:** low
**Biological context:** Organism, cell type, stimulus, compartment and scope.

### Evidence summary
State what was and was not established.
### Sources
[]
### Conflicts
No sources retrieved; no conclusion about agreement.
### Reported quantities
[]
### Open questions
Which primary experiment establishes the complex composition?
```

Each source object requires pmid/doi (at least one, absent identifiers null), location,
access (`metadata`, `abstract`, `full-text`, `unavailable`), limitations, context,
finding, and stance (`supports`, `contradicts`, `context`, `excluded`). A supported
claim needs accessible supporting evidence. Each quantity requires name, value as
reported text, units as reported text or null, source (a listed PMID/DOI), and location.
Supported quantity claims require quantities. Summarize evidence without overstating
access; review existence, mechanism, approximation and numerical value independently.
Import reviewed findings into BioMASS `set_evidence` with stable IDs and source links;
record report paths in the handoff and mechanism/quantity decisions.

## Artifact recording and reproducibility

BioMASS writes to its installation's artifacts directory. The orchestrator supplies
an explicit returned file inventory (path, session_id, sha256 for each file) to:

```text
python scripts/codex/record_ode_artifacts.py --server-root <installed-BioMASS-directory> --session-id <id> --capture-id <unique-id> --inventory <inventory.json>
```

The recorder verifies scope, hashes and symlinks and preserves originals. Each capture
is under `runs/ode-modeler/{id}/captures/{capture-id}/`, preserving relative paths.
The completed result lists every generated revision file, including integrity.json,
model.txt, model_summary.json, snapshot.json, request.json and generated_model/ode.py.
The snapshot retains configuration, evidence, coverage and upstream provenance.
Simulation claims require requests for that same revision, numerical scenario reports
and both species and observable CSVs. Exported bundles must contain that exact revision
and reproduction entrypoints. Project evidence reports remain separate artifacts.

For the approved NeKo export, first run `scripts/codex/record_neko_ode_handoff.py
--server-root <installed-NeKo-directory> --manifest <exported-manifest>
--capture-id <unique-id>`. It records the network, byte-identical original manifest,
separate import manifest and relocation hashes under the upstream NeKo session.
Pass its returned upstream_manifest to the ODE specialist. It does not export or
approve topology; the NeKo specialist must already have performed the approved export.

Keep NeKo handoff manifests byte-identical. If relocation is required for import,
create a separate relocated manifest and retain its original hash, source manifest,
and network artifact hash in the report; never rewrite the original manifest. The
snapshot's imported manifest is the one identified by upstream_manifest. Include both
original and relocated copies under the NeKo session and validate their relationship.

Archive/checkpoint already includes runs and evidence; no lifecycle allowlist expansion
is needed. Reconstruct from preserved authoring text/configuration/evidence in a fresh
session after a restart. `restore_session` is only for an explicitly approved existing
BioMASS session whose authoring snapshot still exists; a portable bundle is not itself
a server session snapshot.

## Local activation and limitations

Run setup with `--client both --environment-mode reuse --env-prefix <existing-env>
--with-biomass`. Reuse mode never installs packages or takes ownership of the environment.
BioMASS stays optional for existing installations. Verify capabilities rather than
package version alone: the local ODE wheel and older distribution both identify as 2.3.0.
Graph rendering is optional. The Codex project parent must disable all four modelling
servers and the client must be restarted after configuration changes. Repository
configuration cannot remove BioMASS tools already granted to a desktop parent.

Claude's existing validate-stage skill requires scientific-reviewer and
reproducibility-auditor definitions that are not present. Preserve that requirement;
report its blocker instead of claiming end-to-end independent validation is available.

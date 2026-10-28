# Checked agentic operations

These helpers implement Point A of the 2026-10-05 diagnostic. They do not approve
scientific choices or repair missing server capabilities. Run from the repository
root with Python 3.11+; handoff capture uses the configured modelling environment
for its pure artifact-contract validators. No helper below calls modelling MCPs.

## Setup, isolation and PubMed

`python3 scripts/check_isolation.py --repository-only` is the CI check.
Without that flag it also checks `~/.claude.json`; supply `--codex-config PATH`
to inspect a user Codex configuration. Setup checks skill snapshots against the
installed/pinned backend version. An unsafe registration or permission is a failure.
The four Claude transports use distinct `neko-agent`, `maboss-agent`,
`physicell-agent`, `biomass-agent` names and remain specialist-inline only.

The guard's `--preview` lists planned paths. Its explicit `--apply` removes only
modelling registrations at global/current-project scope and matching local grants;
unrelated projects and PubMed remain intact. Private backups are saved under
ignored `.setup/backups/isolation/`. To add PubMed to an existing isolated profile,
pass `--literature-profile PATH`; custom transports/explicit disabled choices are
preserved. Fresh setup uses `https://pubmed.mcp.claude.com/mcp` and restricts Codex
to the seven read-only PubMed tools. Web search remains separately authorized,
disabled by default, with no silent fallback after an endpoint failure.

Codex supports remote URL MCP transport ([official configuration example](https://developers.openai.com/learn/docs-mcp)).
The dispatcher resolves its configured Codex home; that may differ from the desktop
chat's home. A working chat connector does not configure a subprocess. Verify the
actual profile, transport and restricted inventory. The bounded connectivity check is
`python3 scripts/setup_support/probe_pubmed.py --python /path/to/modelling/python`
(initialization and tool listing only). Restart clients after changing
registration: static checks cannot revoke tools already granted to a running client
or prove specialist authentication/connectivity. Keep the existing ODE readiness gate.

## State updates

`python3 scripts/state.py OPERATION --input request.json` reads a JSON file and
atomically updates one checked Markdown source of truth. The input is data, not
shell text. Do not interpolate researcher prose into commands. The helper rejects
missing/duplicate rows, malformed tables, traversal, symlinks and bad transitions.
Timestamps are timezone-aware UTC ISO-8601. Preserve original source timezone offsets
in provenance; convert before comparing dates across midnight.

| Operation | Input |
|---|---|
| `decision` | Decision, Alternatives considered, Rationale, Evidence, Approved by; Date generated |
| `registry-add` | Exact seven CURRENT_STATE registry columns; full unique session ID, matching role/stage, active status |
| `registry-supersede` | `session_id`; retains the historical row |
| `registry-handoff` | `session_id`, `handoff`; pending → approved → exported only; export includes verified `artifact` |
| `record` | One structured governance record described below |
| `validation-declare` | Criterion, Method, Required evidence; creates a unique pending criterion |
| `validation` | Supported artifact-validator JSON output; only updates already declared criterion IDs |
| `checkpoint` | Full content-commit SHA and `summary`; no self-referential metadata commit |

An artifact reference is `{"path":"repository/relative/file","sha256":"..."}`.
Hashes are verified, not accepted as annotations. A validation result contains
criteria and input hashes; a changed input invalidates recording. These are
record-keeping guarantees, not cryptographic proof that a researcher approved a
record or that a report is scientifically correct. Inspect diffs before checkpointing.

## Exact downstream gates

Record governance JSON with `state.py record`. Records are append-only fenced JSON
blocks marked `<!-- governance-record -->` in DECISIONS.md, avoiding a competing
approval database. Every record has a unique `id`, `kind`, `stage`, and full
`session_id` (except standalone authorization).

Before downstream dispatch, independent review must finish; persist both reports in
`runs/orchestrator/reviews/<session>/`. Separate researcher approval is still required
before producing a conclusive export. A `stage_review` contains:

- `outcome`: approved, approved_with_limitations, revision_required or blocked;
- `artifact`: exact reviewed handoff path/hash;
- `scientific-reviewer` and `reproducibility-auditor`: report path/hash references.

Then record the researcher's `stage_approval` with `approved_by: "researcher"`,
`authorization` (exact quotation or durable request reference), `artifact`,
`downstream_stage`, and the exact ordered `outputs` list. A review recommendation
does not confer approval. Never invent authorization to satisfy the schema. Pending
scientific choices remain pending even if technical verification succeeds.

Run and quote:

```bash
python3 scripts/gate.py check boolean-dynamics FULL_NEKO_SESSION --outputs NODE_A NODE_B
python3 scripts/gate.py check multicellular FULL_MABOSS_SESSION --outputs READOUT_A READOUT_B
python3 scripts/gate.py check biomass_ode FULL_NEKO_SESSION --outputs NODE_ID_1 NODE_ID_2 ...
```

NeKo-to-BioMASS graphs carry no output selection, so for `biomass_ode` the
approval's `outputs` are every `node_id` in the exported `network_file`: the
researcher approves the whole graph's species scope. The ODE dispatch itself is
governed by the [ODE contract](ode-contract.md); the Claude dispatch hook enforces
`STAGE_GATE` only for the MaBoSS and PhysiCell specialists.

The checker requires the expected active upstream row with Handoff exactly
`exported`, a valid typed handoff and captured dependencies, matching outputs,
completed independent reviews and subsequent researcher approval. Changed hashes,
missing artifacts, a superseded session, or a later blocking review fail closed.

Boolean handoffs support versions 1.0, 2.0 and 2.1. Version 2.0 adds verified
source ancestry with embedded file snapshots; it does not grant approval of
derivatives. Version 2.1, written by `mcp-biomodelling-servers` 2.5.0, adds a
required `curation_file` NeKo history companion to NeKo-to-MaBoSS manifests and
the MaBoSS model revision plus explicit readout definitions (possibly empty) to
MaBoSS-to-PhysiCell manifests. Only declared readouts may extend the NeKo core.
NeKo-to-BioMASS 2.0 likewise names a `curation_file`. Capture and retain every
referenced file; approval binds to the exact NeKo state or MaBoSS revision.
The backend binds each `curation_file` to the model file's original absolute path,
so downstream import tools reject relocated copies: for these versions give the
importing specialist the recorder's `backend_import_manifest` (the original server
manifest, whose hash `relocation.json` records), while the project capture remains
the record that the gate and approvals bind to.
Before dispatching such an import, confirm that the manifest handed over is the
captured original:

```bash
python3 scripts/capture/verify_import_manifest.py --capture CAPTURE_DIR --manifest ORIGINAL_BACKEND_MANIFEST
```

Pass that manifest as `manifest_path`. Backend 2.5.2 also offers
`export_handoff_bundle` and a `handoff_bundle` import argument, plus `sif_text` and
`bnet_text` inputs, for hosts that give each server a private filesystem. All
specialists here share one host filesystem, so this project does not use them: a
bundle import reads copies from the consumer's `handoff-blobs/` store instead of
the original paths verified above, the bundle carries every referenced file
inline through the agent's context, and inline text replaces the preserved source
file as the recorded input. A
"manifest does not exist" error is a transport blocker to report.

The NeKo Boolean recorder also copies and hashes the `*.bnet.lineage.json`
source-lineage sidecar when the export produced one.
`scripts/boolean_contract.py` uses the backend's pure contract reader to validate
this metadata without following historical paths. If system Python lacks that
package, it uses the existing workstation Python selection from
`.setup/dispatcher.local.json` or `.setup/local.json`. An unavailable/old contract
package, invalid ancestry or timeout blocks dispatch; no dependency is installed
automatically. Current artifact paths must still remain inside the repository.
The Boolean capture commands accept explicit per-server `--artifact-root` storage
as well as the legacy installation `--server-root`; see
[capture instructions](../scripts/capture/README.md).

For a v2 MaBoSS source derivative, a registry `Derived from` NeKo session may match
the current session's verified **direct** source parent. Transitive historical
ancestors cannot satisfy that binding. This does not replace the current session's
review, exported status, exact artifact hash, ordered outputs or researcher approval.
An accepted typed stage parent retains its stricter matching node/output contract.

The bounded dispatch task begins with one literal line:

```text
STAGE_GATE {"upstream_session_id":"FULL_SESSION","outputs":["NODE_A","NODE_B"]}
```

Claude's Agent/Task PreToolUse hook and the Codex runtime check durable state rather
than trusting this prompt assertion. Codex checks new Boolean downstream sessions
before starting the child. Existing-session inspection without a valid gate is
restricted to audited non-creating tools: some backend methods named as reads
actually call `ensure_session` and can create sessions. Broader access needs the
gate. ODE authoring continues to use its own approved-source/readiness contract.

An explicitly authorized standalone source uses a `standalone_approval` record:
`id`, `kind`, target `stage`, researcher authorization, exact source `artifact` and
declared `outputs`. Its task envelope uses `standalone_decision_id` instead of
upstream_session_id. It records null upstream lineage rather than inventing a
handoff. This exception must be explicitly authorized, never inferred from a failed
import or missing artifact.

Conditional topology decisions use `kind: "conditional_approval"`, exact session,
researcher authorization, literal `edge: [source,effect,target]`, `evidence` path/hash, and `conditions` mapping supported
footer fields to string allowlists, for example `{"verdict":["supported"]}`.
`python3 scripts/gate.py resolve DECISION_ID` validates the evidence and returns
satisfied/unsatisfied plus supporting PMIDs. It never mutates topology, exports a
handoff, or authorizes an operation outside the recorded scope.

## Evidence and provenance

Edge reports end in exactly one fenced `yaml` block using JSON syntax. Ordinary
YAML aliases/tags/unquoted fields are deliberately unsupported so the guards need
no parser dependency. Example footer syntax (illustrative identifiers/citations):

```yaml
{"verdict":"supported","interaction_type":"activation","confidence":"high","supporting_pmids":["12345678"],"excluded_pmids":[],"edge":["A","activation","B"],"neko_session_id":"FULL_SESSION"}
```

Use the verdict/type/confidence enums in `scripts/evidence_contract.py` and the
literal effect from the bounded review task; footer identity and
lists must match Markdown sections and canonical filenames. Supporting/excluded
PMIDs must be disjoint, and a supported verdict requires a supporting PMID.
The report body still records context, perturbation,
access limits and separate existence/direction/sign/directness judgments. Metadata
or abstract access is not full-text review. No PMID is evidence merely because it
appears in a report.

Candidate edges use `evidence/reports/<session>/candidates/A__B.md`; reviewed topology
edges use the session root. Re-review requires explicit `.r2.md`, `.r3.md`, etc.,
with an existing preceding revision. Codex's writer uses exclusive creation; the
Claude hook checks no-overwrite before Write. Keep review slices non-overlapping;
the Claude preflight check is not an atomic replacement for the underlying Write.
Every manual edge needs a dedicated report before inclusion; arbitrary backend
imports are not rewritten or retrospectively validated by these report helpers.
With backend 2.5.0, apply an approved manual edge or effect change through
NeKo `edit_interactions` rather than a hand-edited SIF: NeKo records its manual
origin, rationale and supplied PMIDs in the network history, separately from
database evidence. A missing PMID stays empty; it is never filled in.

Use provenance tags database-default, literature-derived, manual-literature,
fitted-for-dynamics and readout as defined in CLAUDE.md. Orchestrator-authored inputs
live under `runs/orchestrator/<purpose>/`, with CHANGES.md containing original
path/hash, exact ordered edits, evidence/PMIDs, authorization, output path/hash and
reproducible command or patch. Biological values are not inferred from signed edges.

## Capture and validation

See [capture commands](../scripts/capture/README.md) for one-command handoff/package
capture, guarded reports, immutable invocation records, resource metadata, index
recovery and usage tables. The server still chooses its original artifact root;
these repository helpers capture exports without fixing category B server behavior.
Missing usage/resource fields remain null, not invented. Artifact copy and index
publication are separate recoverable operations.

See [validation commands](../scripts/validate/README.md) for explicit criteria,
safe bounded Boolean analyses, trajectory metrics, seed planning and time-scaling
proposals. Initialize VALIDATION_CRITERIA.yaml only when starting a model. The
orchestrator may run these read-only artifact checks; this grants no modelling MCP
access, mutation or numerical-parameter approval. Store results under
`runs/orchestrator/validation/`, then update declared plan rows with state.py.

Readout Boolean-function exclusivity and asynchronous stored-node exclusivity are
different claims; use the appropriate analysis with explicit initial state and
update semantics. Spaced seeds avoid assumed consecutive overlap but do not prove
Monte Carlo independence. Calibration emulates a declared phase mapping and emits
a proposal requiring approval; it does not validate a PhysiCell simulation.
Every multicellular stage still needs both independent reviews before closure.

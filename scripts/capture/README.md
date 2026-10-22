# Provider-neutral artifact and invocation capture

These commands read existing artifacts and publish immutable repository copies.
They do not run a modelling server, create scientific sessions, approve a model,
or update the session registry. Use the configured modelling Python environment
for Boolean handoff commands: they import the backend's pure contract validators.
Legacy `scripts/codex/record_*` imports and entry points remain compatible.

```bash
python scripts/capture/record_neko_boolean_handoff.py --server-root /installation/NeKo --manifest /installation/NeKo/artifacts/SESSION/export.handoff.json --capture-id CAPTURE
python scripts/capture/record_maboss_physicell_handoff.py --server-root /installation/MaBoSS --manifest /installation/MaBoSS/artifacts/SESSION/export.handoff.json --capture-id CAPTURE
python scripts/capture/record_neko_boolean_handoff.py --artifact-root /cache/mcp-biomodelling/artifacts/NeKo --manifest /cache/mcp-biomodelling/artifacts/NeKo/SESSION/export.handoff.json --capture-id CAPTURE
python scripts/capture/record_maboss_physicell_handoff.py --artifact-root /cache/mcp-biomodelling/artifacts/MaBoSS --manifest /cache/mcp-biomodelling/artifacts/MaBoSS/SESSION/export.handoff.json --capture-id CAPTURE
python scripts/capture/record_physicell_config.py --source-root /installation/PhysiCell/artifacts/SESSION --xml /installation/PhysiCell/artifacts/SESSION/settings.xml --session-id SESSION --capture-id CAPTURE
```

For Boolean handoffs, supply exactly one of `--server-root` (legacy installation
with an `artifacts/` directory) or `--artifact-root` (the explicit **per-server**
directory containing session directories). With `MCP_BIOMODELLING_ARTIFACT_ROOT`,
append `/NeKo` or `/MaBoSS` to that configured shared root. Capture never infers a
trusted directory from a manifest or environment variable. Existing path,
symlink, hash and no-overwrite checks apply to either storage layout.

The MaBoSS recorder uses the project as its default trusted parent-artifact root.
For an upstream NeKo manifest still in the backend installation, pass an explicit
`--parent-root` containing that manifest and its BNET. It preserves the original
manifest, copies and validates the upstream BNET, and changes paths and relocated
parent-manifest digests in the import copy. It preserves declared lineage rather
than inventing a missing parent. Standalone exports retain their null parent.

Boolean v2 handoffs add `source_ancestry`, separate from the accepted stage parent
in `parent_manifest`/`lineage`. Each import records its source digest, relationship
(`standalone`, `byte-identical`, or `edited-derivative`) and verified snapshots of
its source and ancestors. Capture retains the embedded snapshots unchanged and
also writes their bytes under `ancestry/<sha256>`, included in `runs/index.json`.
Historical paths inside snapshots are labels: capture never opens them. Copies
remain verifiable after the original source files disappear. Existing v1 handoffs
are still accepted; ODE formats are unchanged. All capture files remain under the
existing `runs/` lifecycle allowlist, so archives preserve them with the model.

Backend 2.5.0 adds curation-bearing versions: NeKo→MaBoSS **2.1** and
NeKo→BioMASS **2.0** require a `curation_file` (NeKo history companion), and
MaBoSS→PhysiCell **2.1** requires `model_revision` and explicit `readouts`
(may be `{}`). Recorders copy and hash the companion (top level, or under
`parent/curation/` for a MaBoSS parent) and record `curation_sha256` in
`relocation.json`. The backend binds each companion to the model artifact's
*original absolute path*, so its own verifier, and therefore MaBoSS, BioMASS and
PhysiCell import tools, reject every relocated copy. For these versions pass
the original backend manifest (`backend_import_manifest` in the recorder
output) to the downstream import tool; the project capture remains the
immutable gate/approval record. Recorders verify the live original first and
then the copies against the original binding; `gate.py` checks the copied
companion bytes, state and every non-path identity field. Readouts are the only
nodes permitted beyond the NeKo parent core; they may not reclassify core nodes
or appear in core BND rules. Older 1.0/2.0 documents are unchanged. The ODE
recorder accepts `--artifact-root` like the Boolean recorders, because 2.5.0
servers write to `~/.cache/mcp-biomodelling/artifacts/<Server>` by default.

Before dispatching an import from `backend_import_manifest`, confirm it is the
exact captured original and that its payloads are unchanged:

```sh
python3 scripts/capture/verify_import_manifest.py \
  --capture runs/network-curator/SESSION/boolean-handoffs/CAPTURE \
  --manifest /cache/mcp-biomodelling/artifacts/NeKo/SESSION/export.handoff.json
```

It compares the manifest bytes with `original.handoff.json`, the hash and source
path in `relocation.json`, and the size/SHA-256 of every referenced payload; it is
read-only and grants no approval. When a NeKo Boolean export has a sibling
`<bnet>.lineage.json` source-lineage sidecar, the recorder validates it with the
backend model, requires it to describe exactly this manifest's BNET and history
companion, copies it unchanged (its paths are identity labels) and records
`source_lineage_sha256`.

A source derivative can retain a NeKo ancestor while having no accepted stage
parent. That source record never grants approval of its changed nodes or rules.
The current model still requires independent review and exact-revision researcher
approval before downstream dispatch. When a stage parent is declared, its source,
node/output selections and inherited v2 ancestry must match the current handoff.

The PhysiCell recorder takes an explicit root for resolving relative input paths.
All enabled `filename`/`*_filename` inputs must resolve inside that root. Disabled
sections are excluded; missing active inputs, escapes, symlinks, filename collisions,
and XML entity declarations fail. Original XML bytes are preserved; the separate
`package/config/PhysiCell_settings.xml` has relative input paths. Launch from the
`package` directory. Capture validates XML and artifact integrity; it does not
claim that a PhysiCell simulation ran or that its configuration is scientifically
valid. Only `filename` and `*_filename` dependencies are recognized. Other input
conventions can escape this scan and require an explicit implementation/review,
not a claim of complete dependency validation.

NeKo ODE and BioMASS inventory capture are also available at
`record_neko_ode_handoff.py` and `record_ode_artifacts.py`, with their existing CLI
arguments and contract checks. Every session-bound recorder appends verified artifact
hashes to `runs/index.json`. Per-target publication and index replacement are atomic
for cooperating POSIX processes. They are **separate transactions**: an interrupted
index write can leave a complete capture without an index row. Recover it using:

```bash
python scripts/capture/index.py --recover-capture /project/runs/SPECIALIST/SESSION/CATEGORY/CAPTURE
```

Recovery verifies paths and current hashes, refuses to alter an already indexed
capture, and never recopies or overwrites artifacts. Recovery of an unindexed
capture establishes the hashes present at recovery time; it cannot prove the
contents were unchanged since a crash. Preserve backend manifests for comparison.
Do not delete persistent `.capture.lock` files while processes could use them.

For database-resource provenance, NeKo recorders accept `--resource-metadata FILE`.
This must be an explicit server/cache record containing `name`, `version`, and
`cache_timestamp` (timezone-aware ISO 8601); unknown fields may be null. Original
bytes and their digest are preserved with the capture. Without such a record the
index reports these fields as null and records that the backend did not supply
metadata. Backend 2.5.0 records only the resource database name (W2-D007); it
cannot supply resource versions or acquisition times automatically.

## Claude reports and invocation records

Each modelling agent gets a fixed-name `PreToolUse` Write hook:

```yaml
hooks:
  PreToolUse:
    - matcher: Write
      hooks:
        - type: command
          command: 'python3 "$CLAUDE_PROJECT_DIR/.claude/scripts/specialist_report_guard.py" network-curator'
```

Use the matching agent name for each agent. `Write` must be allowed by that agent
and removed from its `disallowedTools`. Only its own
`runs/<specialist>/<session>/report.md` is writable. The session must appear in the
current invocation's modelling MCP calls/results. Reports cannot be overwritten;
later full reports remain in their separate invocation records. The guard may use
`--session-id` only when the dispatcher has an explicit session binding.

The project `SubagentStop` command is:

```text
python3 "$CLAUDE_PROJECT_DIR/.claude/scripts/record_specialist_invocation.py"
```

The hook requires Claude's `agent_type`, `agent_id`, and `agent_transcript_path`
fields. Nonmodelling agents are ignored. A unique modelling-session identity is
required for scientific attribution; ambiguous identities fail with an actionable
error, preserving the original Claude transcript. The immutable `invocation/<agent_id>/` record
contains the task text, sanitized transcript, tool arguments/results, final full
report, source transcript digest, and usage summary. Common credential fields are
redacted using the same sanitizer as the Codex runtime.

Attempts that stop before creating a scientific session are preserved under
`runs/orchestrator/unbound-invocations/<specialist>/<agent_id>/`, with a null session
and unresolved scientific status. These technical records are not added to the
scientific capture index or session registry and cannot authorize advancement.
They retain the same sanitized transcript, report and measured usage fields.

Identical stop-event retries verify every artifact byte and reuse the existing
record, recovering a missing index entry when applicable. Changed transcripts or
artifacts fail without overwriting the original. On a recording error the first
stop hook exits 2 with repair instructions. If `stop_hook_active` is already true,
it exits 0 and emits the recording failure as a visible system message to prevent
repeated blocked continuations. This permits process termination only: the
orchestrator must preserve the original transcript and repair recording/attribution
before accepting the result or advancing a stage.

Token counts are summed by unique assistant-message ID. Tool calls are counted from
the transcript. Wall time is the elapsed span of timezone-aware transcript events;
it is not billing duration. Unavailable token measurements, pricing/cost, and missing
time data are null. Generate the benchmark table without guessing these values:

```bash
python scripts/capture/usage_summary.py runs/index.json
```

Codex runtime invocations also register their existing immutable
`specialist-invocations/<invocation_id>/` records. Usage comes from recorded
`turn.completed` events and unique tool-item IDs; elapsed time comes from the
measured child-process duration. Pre-session `_blocked`/`_unresolved` records
remain preserved without inventing a scientific session or an index entry. Index
failures propagate through the runtime's existing recording-failure handling.

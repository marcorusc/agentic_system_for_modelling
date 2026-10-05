# Provider-neutral artifact and invocation capture

These commands read existing artifacts and publish immutable repository copies.
They do not run a modelling server, create scientific sessions, approve a model,
or update the session registry. Use the configured modelling Python environment
for Boolean handoff commands: they import the backend's pure contract validators.
Legacy `scripts/codex/record_*` imports and entry points remain compatible.

```bash
python scripts/capture/record_neko_boolean_handoff.py --server-root /installation/NeKo --manifest /installation/NeKo/artifacts/SESSION/export.handoff.json --capture-id CAPTURE
python scripts/capture/record_maboss_physicell_handoff.py --server-root /installation/MaBoSS --manifest /installation/MaBoSS/artifacts/SESSION/export.handoff.json --capture-id CAPTURE
python scripts/capture/record_physicell_config.py --source-root /installation/PhysiCell/artifacts/SESSION --xml /installation/PhysiCell/artifacts/SESSION/settings.xml --session-id SESSION --capture-id CAPTURE
```

The MaBoSS recorder uses the project as its default trusted parent-artifact root.
For an upstream NeKo manifest still in the backend installation, pass an explicit
`--parent-root` containing that manifest and its BNET. It preserves the original
manifest, copies and validates the upstream BNET, and changes paths and relocated
parent-manifest digests in the import copy. It preserves declared lineage rather
than inventing a missing parent. Standalone exports retain their null parent.

The PhysiCell recorder takes an explicit root for resolving relative input paths.
All enabled `filename`/`*_filename` inputs must resolve inside that root. Disabled
sections are excluded; missing active inputs, escapes, symlinks, filename collisions,
and XML entity declarations fail. Original XML bytes are preserved; the separate
`package/config/PhysiCell_settings.xml` has relative input paths. Launch from the
`package` directory. Capture validates XML and artifact integrity; it does not
claim that a PhysiCell simulation ran or that its configuration is scientifically
valid. Unknown input conventions need an explicit implementation, not manual omission.

NeKo ODE and BioMASS inventory capture are also available at
`record_neko_ode_handoff.py` and `record_ode_artifacts.py`, with their existing CLI
arguments and contract checks. Every successful recorder appends verified artifact
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
metadata. Backend 2.4.0 cannot supply missing resource versions automatically.

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
required; ambiguous or missing identities fail with an actionable error, preserving
the original Claude transcript. The immutable `invocation/<agent_id>/` record
contains the task text, sanitized transcript, tool arguments/results, final full
report, source transcript digest, and usage summary. Common credential fields are
redacted using the same sanitizer as the Codex runtime.

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

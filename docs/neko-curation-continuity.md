# NeKo curation continuation: observed limitations

2026-09-15. This records live findings after the dispatcher migration smoke test.
The earlier test established single-invocation construction, not continuity of
in-memory modelling state between fresh specialist processes.

## Session lifetime

The network profile launches `mcp-neko-server` by command over stdio. Each ephemeral
specialist therefore gets its own server. Installed `NeKoSessionManager.__init__`
creates an empty in-memory `_sessions` dictionary; `list_artifact_sessions` scans
exports and explicitly distinguishes them from live sessions.

Task `38e361a836184c60896fd61c410ba63a` returned blocked when status/history/connectivity
for `d63363b6-59b4-47cf-adae-6b9110e438fd` reported Unknown NeKo session. No repair or
reconstruction was attempted in that invocation.

The researcher then approved a fresh reconstruction from the same 60 genes and
exact SIGNOR policies, with an exact-match gate and same-invocation read-only scout.
Task `67f603a312ef4a1a9fc154de8f6af761` created descendant
`22b9aa48-d173-49d5-b9a8-f6c3c03f7e16`. Its final handoff failed validation (below).
The parent independently verified that its 8200-byte SIF is byte-identical to the
original, SHA-256 `3a8a690db5f522e18e340e9526b03e1b7b66664b0d442de3ae95ee16d1dc6cb8`.
This verifies export bytes only, not a complete accepted live-state handoff.
Artifacts and failure metadata remain under the descendant's run directory.

Durable session serialization/restoration or a separately designed local persistent
server would be needed for continuing the same mutable session across invocations.
Neither is implemented or authorized by this diagnosis. No server exposure or
root modelling-tool access was introduced.

## Preview scope

Installed `preview_connection_impact(method="hubs")` ranks degrees in existing
network edges. It does not search for new connector genes. The `relax_max_len` and
`unsigned` alternatives call whole-network `complete_connection` on a copy. There
are no endpoint/group arguments or explicit per-call path/reuse policy arguments.
The visible read-only alternatives inspect current-network paths, not bounded
resource connector candidates. No targeted repair proposal has been established.

A useful follow-up capability would accept explicit source/target component sets,
policies and bounds, and return candidate paths, genes, edges, references and
component-impact estimates without mutating state. It needs its own implementation
and validation; no new scientific repair policy is accepted here.

## Final-output redaction bug and fix

The rejected specialist output contained a report string with `authorization:`.
Whole-document regex redaction inserted unescaped quotes into that JSON string.
Parsing then selected an embedded draft manifest, which lacked the required full
handoff fields. This is a serialization failure, not a failed NeKo construction.

The shared executor now parses the handoff in memory, recursively sanitizes values,
and serializes the sanitized object as JSON. Unstructured failures still use text
redaction. Sensitive keys and embedded credentials remain redacted. Original failed
invocation files and task status are unchanged; no scientific acceptance is inferred.
Regression tests cover nested report content, fenced JSON, retained root fields,
credential removal, and text-only failures. The full SDK-enabled repository suite
passed after the fix. An initial ad hoc unittest invocation hit a test-path import
error; the canonical repository runner completed successfully.

The already-running dispatcher retains its imported runtime until reloaded. This
fix is available to new processes; no live post-fix modelling invocation was run.

## Scientific progress

Three additional immutable reports were validated for GMNN→CDT1 and
TNFSF10→TNFRSF10A/TNFRSF10B under the original session's evidence directory.
Nine of 151 original edges have evidence reports; 142 remain. Evidence acceptance,
node semantics, six bimodal signs and connectivity remain unresolved. No repair,
BNET handoff, or downstream model has been accepted.

# NeKo Phase 7 timeout diagnosis

Date: 2026-09-15. Read-only diagnosis of the original failed invocation; no retry,
new session, database change, model reduction, or package patch was performed.

## Confirmed findings

- The recorded `create_network` request used `list_of_initial_genes=[]` and the
  supplied SIF. There were **zero initial seeds**. The imported source graph had
  90 nodes and 387 functional edges.
- In the installed NeKo MCP `server.py`, the SIF branch constructs
  `Network(sif_file=..., resources=...)`. `complete_connection` occurs only in the
  separate seed-construction branch. No all-pairs seed connection search ran.
- `Network._populate` initializes the resource universe before parsing the SIF.
  OmniPath loads through `PostTranslational.get`. The SIF path therefore still
  depends on database/resource initialization even without topology expansion.
- `_load_network_from_sif` calls `check_gene_list_format` for edge endpoints and
  `mapping_node_identifier` when adding nodes. These call the identifier mapper.
- The existing local reviewed-human mapping cache has 20,431 rows and a matching
  SHA256. Only 10 of the 90 model labels match its primary-symbol keys exactly;
  80 do not. Examples include `G0G1_entry`, `Replication`, `CyclinA`, and `Casp3`.
  A cache miss does not establish that a name is biologically invalid.
- Missing ordinary labels enter `to_uniprot`'s per-identifier live REST fallback.
  Its result cache is process-local and includes unsuccessful results. Thus this
  is potentially many unique lookups, not necessarily one request per edge.
- UniProt fallback requests have 10-second per-request timeouts, a 20-second job
  polling budget, and an HTTP retry adapter configured for five retries. The
  polling deadline is established after submission; these are not a single strict
  total deadline for a label.
- The local OmniPath configuration specifies `timeout=600` and `num_retries=3`.
  The observed MCP client deadline was 300 seconds. A slow resource operation can
  therefore outlive the enclosing tool call.
- The original server artifact directory contains only `session_meta.json`.
  No exported network was recovered. Original Codex/NeKo processes have exited;
  the session identifier is provenance, not evidence of recoverable runtime state.

## Diagnosis and limits

The seed-count hypothesis is ruled out for this invocation. The strongest current
suspects are resource initialization and accumulated live identifier translation,
including requests for model-specific states that are not gene symbols.
The retained record contains a client timeout, not a server stack trace or timed
sub-step log. It does **not** establish which suspect caused the original timeout.
Do not report either as proven. Existing cache files alone do not prove that the
specific resource request was a cache hit.

This also exposes a fidelity concern independent of speed: automatic translation
of an existing Boolean model's symbols needs explicit round-trip checks. Reducing
the graph or renaming its nodes would change the benchmark; merely increasing the
timeout would not establish source fidelity.

## Next debugging step

Before a new import, add or enable timed, non-secret diagnostics around resource
initialization, SIF parsing, and identifier lookups in an isolated diagnostic
execution. Determine which operation blocks and whether external requests occur.
A source-preserving SIF import mode that avoids unnecessary resource downloads and
live translation is a potential upstream improvement, not an implemented fix.
Do not change mapping policy or substitute a database silently. Any eventual retry
must be a new explicitly scoped invocation; retain this failure and its artifacts.

## Source locations inspected

Installed package root:
`/home/marcorusc/miniforge3/envs/mcp_modelling/lib/python3.14/site-packages/`

- `mcp_biomodelling_servers/NeKo/server.py`: create_network SIF/seed branches.
- `neko/core/network.py`: _populate, _load_network_from_sif, add_node.
- `neko/core/tools.py`: check_gene_list_format, mapping_node_identifier.
- `neko/inputs/identifier_mapping.py`: cache validation and REST fallback.
- `neko/inputs/_db/omnipath.py`: resource acquisition.
- `/home/marcorusc/.config/omnipathdb.ini`: timeout and retry settings only.

Original request, checks, session, and artifact hashes:
[specialist-dispatcher-phase7-validation.json](specialist-dispatcher-phase7-validation.json).

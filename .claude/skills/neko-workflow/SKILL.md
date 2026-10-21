---
name: neko-workflow
description: "Operational guide for the NeKo MCP server — session/network creation, connectivity auditing, connection strategies (connect_targeted_nodes, bridge_components, apply_global_connection), history navigation, export, and debugging exploded or disconnected networks. Preloaded into the network-curator subagent; in the main session, delegate NeKo work to network-curator instead of loading this skill."
---

# NeKo Signalling Network Workflow

Operational snapshot for `mcp-biomodelling-servers` 2.5.0. Tool names and
parameters were checked against the live 2.5.0 schemas (released package with
NeKo `nekomata` 1.10.2). Behaviour the schemas do not describe follows the 2.5.0
server documentation. Recheck this skill when the server package is upgraded.

NeKo builds and curates molecular signalling networks (OmniPath and similar
databases). It's a complete tool on its own — most tasks end at network
construction, curation, and inspection or export. If the task continues into
Boolean-model simulation, `export_neko_handoff` hands off to
`maboss-workflow`; that step is optional, not a requirement.

## Recommended execution order

1. **Initialize:** `create_session()` → `set_default_params(max_len=2,
   path_policy='one_shortest', reuse_policy='discovered_paths',
   only_signed=True, consensus=True)`. Always create a session before
   creating a network; pass `session_id` explicitly with multiple networks.
2. **Build:** `create_network([...list_of_initial_genes...], database='omnipath')`
3. **Curate:** `remove_bimodal_interactions()` → `remove_undefined_interactions()`
4. **Audit connectivity:** `analyze_connectivity()` — isolated (0-edge) nodes
   + full connected-component partition, in one call.
   - Disconnected → `preview_connection_impact()` → apply a connection tool
     (see cost guide below).
   - Validating a requested gene set (not general connectivity) →
     `analyze_gene_set(genes=[...])` instead — separates connectivity from
     the requested genes from connectivity added by intermediates.
5. **Inspect history** after topology changes: `list_network_history(offset=0,
   limit=25)` (pages of at most 100 states) → `compare_network_states(state_a,
   state_b, limit=25)` → `navigate_network_history(action='checkout',
   state_id=...)` only once the diff confirms it's the right state.
6. **Inspect network:** `list_genes_and_interactions(verbosity='preview')`
7. **Authorized interaction edits — only when explicitly requested:**
   `status()` → `edit_interactions(...)`; see the section below.
8. **Export:**
   - `export_neko_handoff(biological_context=..., output_nodes=[...])` —
     typed MaBoSS transfer, default choice. Records sanitized Boolean
     nodes, declared outputs, package versions, history state, artifact
     digests and a typed history companion (`curation_file`).
   - `export_network(format='bnet')` — standalone BNET only, no provenance.
     Fails unless the network is fully connected; run
     `analyze_connectivity()` first. `format='sif'` has no such requirement.
   - `export_network(format='history')` — all retained snapshots, structured
     explanations and branch relationships for reproducibility review. It is
     not a handoff and approves nothing.

## Tool categories

- **Sessions:** `create_session`, `list_sessions`, `list_artifact_sessions` (sessions with files on disk, including past server runs), `set_default_session`, `delete_session`, `status`, `reset_network`
- **Construction:** `create_network`, `add_nodes` (batch, optional cheap direct-neighbour autoconnect; reports refused and already-present nodes), `remove_gene`, `remove_interaction`
- **Authorized curation:** `edit_interactions` (atomic `add` / `set_effect` batches between existing nodes)
- **Connectivity diagnostics:** `analyze_connectivity` (isolated nodes + component partition), `analyze_gene_set` (requested-gene resolution, internal/boundary edges), `preview_connection_impact` (non-mutating scout)
- **Connection strategies:** `connect_targeted_nodes`, `bridge_components`, `apply_global_connection` — see the [strategy reference](https://github.com/sysbio-curie/Neko/blob/development/docs_mkdocs/strategies/index.md)
- **Inspection:** `list_genes_and_interactions`, `find_paths`, `get_references`, `filter_interactions`
- **History:** `list_network_history`, `navigate_network_history`, `compare_network_states`, `set_network_history_limit`
- **Export and handoff:** `export_network` (SIF/BNET/history), `list_bnet_files`, `export_neko_handoff`, `export_biomass_handoff`

## Authorized interaction edits (`edit_interactions`)

Use only for edges the orchestrator explicitly names as researcher-authorized,
literature-supported curation (provenance tag `manual-literature`; each edge has
its own candidate report). The tool records the edit; it grants no approval.

1. `status(session_id=...)` → note `network_id` and `state_id`.
2. `edit_interactions(session_id=..., expected_network_id=...,
   expected_state_id=..., edits=[...])` with 1–20 records:
   `{"operation": "add" | "set_effect", "source", "target", "effect",
   "rationale", "evidence": {"summary", "pmids": [...], "citations": [...]}}`.
   `effect` is one of `stimulation`, `inhibition`, `bimodal`, `form complex`,
   `undefined`.
3. Take `rationale`, `summary`, PMIDs and citations from the authorization and
   its evidence report without strengthening them. Never invent or "complete" a
   PMID; an edge without one still needs a citation and stays manually curated.
4. Both endpoints must already exist. The batch is atomic: a missing endpoint,
   conflicting edge or stale `expected_*` identity fails the whole batch with no
   partial edit. Do not add nodes or run connection tools to make an edit fit —
   return that as a topology question.
5. Report the returned canonical endpoints/effects, unchanged count, resulting
   `state_id` and the history URI. Any earlier export or approval refers to the
   older state; the edited topology needs fresh review and export.

## Connection strategy cost guide

Choose the cheapest strategy that could plausibly close the gap; escalate
only if it fails. Costs assume seed/group sizes of a few dozen genes.

| Tool | Strategy | Cardinality | Relative cost | Notes |
|---|---|---|---|---|
| `add_nodes` | `autoconnect=True` | new node(s) → existing network | Very low | Direct-neighbour edges only (maxlen=1); no multi-step search |
| `connect_targeted_nodes` | `connect_to_upstream_nodes` | specific node(s) | Low, bounded by `max_len` (upstream depth, default 1) | Cascades upstream from given nodes only |
| `connect_targeted_nodes` | `connect_subgroup` | one node list | Moderate, ~O(pairs) | Pairwise search within the group only |
| `bridge_components` | — (`comp_a`, `comp_b`, `mode`) | group A ↔ group B | Moderate-high | Also silently runs `connect_subgroup` on every node outside A/B |
| `apply_global_connection` | `connect_network_radially` | whole network | Moderate-high, bounded by `max_len` | Expands from existing seed nodes, not all pairs |
| `apply_global_connection` | `connect_as_atopo` | whole network, output-anchored | High, open-ended | Runs radial/complete connection then loops upstream until fully connected — **not** bounded by `max_len` alone |
| `apply_global_connection` | `complete_connection` | whole network | **Highest — O(N²) over every pair** | Usual cause of a blown-up network (e.g. `max_len=2`, 20+ seed genes → hundreds of edges) |

**Large-network guard:** check `status()` before `complete_connection` or
`connect_as_atopo`. Above ~50 nodes, prefer `connect_targeted_nodes` or
`bridge_components`, or run `preview_connection_impact()` first.

## Critical rules

- **Session first:** `create_session` before `create_network`.
- **Pass policies explicitly:** `create_network`, `connect_targeted_nodes`,
  and `bridge_components` declare their own fixed defaults (`max_len` 2, 1,
  and 2; `create_network` also defaults to `one_shortest` /
  `discovered_paths`), so `set_default_params` may not reach them. Pass
  `max_len` and the policy values on those calls.
- **Scout before you shoot:** `preview_connection_impact()` before any
  heavy connection tool — check against the cost guide above.
- **Output names:** `export_neko_handoff` translates original NeKo names
  to sanitized BNET names. Specify `output_nodes` explicitly — if
  omitted, MaBoSS must select outputs itself before it can run.
- **Token frugality:** use `verbosity='summary'` in iterative
  inspection/edit loops.

## Troubleshooting

- **Network exploded to hundreds of edges** → check `list_network_history()`
  for `complete_connection`/`connect_as_atopo`; `navigate_network_history`
  back to before that step and retry with a cheaper strategy.
- **Disconnected, unclear why** → `analyze_connectivity()` for the
  partition, then `analyze_gene_set()` on the originally requested genes.
- **Comparing history states before reverting** → `compare_network_states()`
  first; don't checkout blind.


## NeKo-to-BioMASS export

When ODE formulation and topology/evidence export are explicitly approved, route
`export_biomass_handoff` through `network-curator`. Preserve references,
biological context and stable edge IDs in the dedicated `neko-to-biomass` handoff.
Follow `docs/ode-workflow.md`, including readiness and verified relocation capture.
This branch does not require BNET or Boolean-specific connectivity criteria.
Only the isolated ODE specialist receives BioMASS; the network specialist retains
NeKo alone. Existing topology policies and conclusive-export gates still apply.

## Semantics and caveats (backend 2.5.0)

State all five consequential policies before construction/repair: path_policy,
reuse_policy, max_len, only_signed, consensus. max_len limits the paths searched,
not the final edge count. discovered_paths reuse can introduce connections among
newly added nodes and grow the graph beyond a seed-only picture. Inspect connected
components and evidence, preview connector impact, and compare history alternatives
before any explicitly authorized repair; do not silently change policy to shrink it.

`consensus` uses resource-specific sign flags. For SIGNOR they compare grouped
sign-record totals; tied flags do not establish a sign and missing consensus
fields resolve to undefined. It never implies multiple databases or higher
confidence. A SIF import reports the imported topology separately from any
explicit later construction and runs no connection completion; preserve the
original identifiers/reference columns and inspect imported counts/history before
assuming equivalence. Counts use the canonical node inventory, including
label-only nodes.

`find_paths` separates errors and warnings from paths, reports the requested
length/direction scope and shows at most `max_paths` (default 20, maximum 100).
No path within `maxlen` does not establish disconnected components. BNET export
failures name the offending node IDs/rows: report them, never silently relabel
complexes or other nodes. Relabelling changes topology provenance and needs
explicit approval and renewed review/export.

History states carry structured explanations (operation, effective policies,
inclusion reason, manual evidence). Imported or pruned history reports its gaps;
do not claim a complete history the server does not report. Resource identity is
the database name recorded at construction (W2-D007); no database release,
download time or dataset fingerprint is tracked.

Capture approved exports with scripts/capture/record_neko_boolean_handoff.py or
record_neko_ode_handoff.py. NeKo→MaBoSS handoffs are version 2.1 and NeKo→BioMASS
2.0; both name a `curation_file` history companion that must stay with the
manifest. Capture resource version/cache timestamp only if explicitly supplied;
unknown metadata stays null, never inferred from the installed package version.
See scripts/capture/README.md. An SIF review export is not conclusive BNET approval.

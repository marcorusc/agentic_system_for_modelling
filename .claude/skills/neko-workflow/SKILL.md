---
name: neko-workflow
description: "Operational guide for the NeKo MCP server — session/network creation, connectivity auditing, connection strategies (connect_targeted_nodes, bridge_components, apply_global_connection), history navigation, export, and debugging exploded or disconnected networks. Preloaded into the network-curator subagent; in the main session, delegate NeKo work to network-curator instead of loading this skill."
---

# NeKo Signalling Network Workflow

Operational snapshot for `mcp-biomodelling-servers` 2.4.0. Tool names and
parameters were checked against the live 2.4.0 schemas (installed build `2.4.0+wave1.20261016`). Behaviour the schemas do
not describe is carried over from the 2.3.0 snapshot. Recheck this skill when the
server package is upgraded.

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
5. **Inspect history** after topology changes: `list_network_history()` →
   `compare_network_states(state_a, state_b)` →
   `navigate_network_history(action='checkout', state_id=...)` only once
   the diff confirms it's the right state.
6. **Inspect network:** `list_genes_and_interactions(verbosity='preview')`
7. **Export:**
   - `export_neko_handoff(biological_context=..., output_nodes=[...])` —
     typed MaBoSS transfer, default choice. Records sanitized Boolean
     nodes, declared outputs, package versions, history state, artifact
     digests.
   - `export_network(format='bnet')` — standalone BNET only, no provenance.
     Fails unless the network is fully connected; run
     `analyze_connectivity()` first. `format='sif'` has no such requirement.

## Tool categories

- **Sessions:** `create_session`, `list_sessions`, `list_artifact_sessions` (sessions with files on disk, including past server runs), `set_default_session`, `delete_session`, `status`, `reset_network`
- **Construction:** `create_network`, `add_nodes` (batch, optional cheap direct-neighbour autoconnect), `remove_gene`, `remove_interaction`
- **Connectivity diagnostics:** `analyze_connectivity` (isolated nodes + component partition), `analyze_gene_set` (requested-gene resolution, internal/boundary edges), `preview_connection_impact` (non-mutating scout)
- **Connection strategies:** `connect_targeted_nodes`, `bridge_components`, `apply_global_connection` — see the [strategy reference](https://github.com/sysbio-curie/Neko/blob/development/docs_mkdocs/strategies/index.md)
- **Inspection:** `list_genes_and_interactions`, `find_paths`, `get_references`, `filter_interactions`
- **History:** `list_network_history`, `navigate_network_history`, `compare_network_states`, `set_network_history_limit`
- **Export and handoff:** `export_network` (SIF/BNET), `list_bnet_files`, `export_neko_handoff`, `export_biomass_handoff`

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

## Semantics and caveats (backend 2.4.0)

State all five consequential policies before construction/repair: path_policy,
reuse_policy, max_len, only_signed, consensus. max_len limits the paths searched,
not the final edge count. discovered_paths reuse can introduce connections among
newly added nodes and grow the graph beyond a seed-only picture. Inspect connected
components and evidence, preview connector impact, and compare history alternatives
before any explicitly authorized repair; do not silently change policy to shrink it.

SIGNOR consensus=True does not imply independent multi-resource corroboration;
record its database-specific/no-op limitation. A SIF import constructs the supplied
network without the completion implied by older create_network prose. Preserve the
original identifiers/reference columns and inspect imported counts/history before
assuming equivalence. The benchmark exposed null complex labels during BNET export:
inspect and report offending labels, never silently relabel complexes. Relabelling
changes topology provenance and needs explicit approval and renewed review/export.

Capture approved exports with scripts/capture/record_neko_boolean_handoff.py or
record_neko_ode_handoff.py. Capture resource version/cache timestamp if supplied;
unknown metadata stays null, never inferred from the installed package version.
See scripts/capture/README.md. An SIF review export is not conclusive BNET approval.

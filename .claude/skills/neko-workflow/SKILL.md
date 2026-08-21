---
name: neko-workflow
description: "Use this skill whenever working with the NeKo MCP server to build, curate, or export molecular signalling networks — session/network creation, connectivity auditing, connection strategies (connect_targeted_nodes, bridge_components, apply_global_connection), network history navigation, or network export. Trigger this any time NeKo tools are called or the user mentions NeKo, signalling networks, OmniPath-based network building, Boolean network export, or BNET files — including when a network has exploded in size, is disconnected, or needs debugging. Fully standalone; optionally hands off to maboss-workflow when the task continues into Boolean-model simulation."
---

# NeKo Signalling Network Workflow

Operational snapshot for `mcp-biomodelling-servers` 2.3.0. Recheck this skill when
the server package is upgraded.

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

## Tool categories

- **Sessions:** `create_session`, `list_sessions`, `set_default_session`, `delete_session`, `status`, `reset_network`
- **Construction:** `create_network`, `add_nodes` (batch, optional cheap direct-neighbour autoconnect), `remove_gene`, `remove_interaction`
- **Connectivity diagnostics:** `analyze_connectivity` (isolated nodes + component partition), `analyze_gene_set` (requested-gene resolution, internal/boundary edges), `preview_connection_impact` (non-mutating scout)
- **Connection strategies:** `connect_targeted_nodes`, `bridge_components`, `apply_global_connection` — see the [strategy reference](https://github.com/sysbio-curie/Neko/blob/development/docs_mkdocs/strategies/index.md)
- **Inspection:** `list_genes_and_interactions`, `find_paths`, `get_references`, `filter_interactions`
- **History:** `list_network_history`, `navigate_network_history`, `compare_network_states`, `set_network_history_limit`
- **Handoff:** `export_neko_handoff`

## Connection strategy cost guide

Choose the cheapest strategy that could plausibly close the gap; escalate
only if it fails. Costs assume seed/group sizes of a few dozen genes.

| Tool | Strategy | Cardinality | Relative cost | Notes |
|---|---|---|---|---|
| `add_nodes` | `autoconnect=True` | new node(s) → existing network | Very low | Direct-neighbour edges only (maxlen=1); no multi-step search |
| `connect_targeted_nodes` | `connect_to_upstream_nodes` | specific node(s) | Low, bounded by `depth` | Cascades upstream from given nodes only |
| `connect_targeted_nodes` | `connect_subgroup` | one node list | Moderate, ~O(pairs) | Pairwise search within the group only |
| `bridge_components` | `connect_component` (A, B) | group A ↔ group B | Moderate-high | Also silently runs `connect_subgroup` on every node outside A/B |
| `apply_global_connection` | `connect_network_radially` | whole network | Moderate-high, bounded by `max_len` | Expands from existing seed nodes, not all pairs |
| `apply_global_connection` | `connect_as_atopo` | whole network, output-anchored | High, open-ended | Runs radial/complete connection then loops upstream until fully connected — **not** bounded by `max_len` alone |
| `apply_global_connection` | `complete_connection` | whole network | **Highest — O(N²) over every pair** | Usual cause of a blown-up network (e.g. `max_len=2`, 20+ seed genes → hundreds of edges) |

**Large-network guard:** check `status()` before `complete_connection` or
`connect_as_atopo`. Above ~50 nodes, prefer `connect_targeted_nodes` or
`bridge_components`, or run `preview_connection_impact()` first.

## Critical rules

- **Session first:** `create_session` before `create_network`.
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

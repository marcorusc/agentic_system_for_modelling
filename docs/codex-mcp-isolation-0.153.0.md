# Codex 0.153.0 MCP isolation validation

Date: 2026-09-03

## Runtime identity

- Reloaded VS Code extension: `openai.chatgpt@26.825.51511`.
- Live extension runtime: `$HOME/.vscode-server/extensions/openai.chatgpt-26.825.51511-linux-x64/bin/linux-x86_64/codex`.
- Extension-bundled runtime version: `codex-cli 0.151.0-alpha.7.2`.
- Test CLI: `$HOME/.local/bin/codex`.
- Test CLI target: `$HOME/.codex/packages/standalone/releases/0.153.0-x86_64-unknown-linux-musl/bin/codex`.
- Test CLI version: `codex-cli 0.153.0`.
- `/usr/local/bin/codex` version: `codex-cli 0.153.0`.

The extension app-server and the standalone test CLI are distinct executables. A
full VS Code reload started a new extension app-server, but the current extension
still bundles its own alpha runtime rather than the standalone 0.153.0 binary.

## Same-process custom-child matrix

The matrix used three inert stdio MCP servers. Each exposed exactly one read-only
tool: `mcp__neko__probe_neko`, `mcp__maboss__probe_maboss`, or
`mcp__physicell__probe_physicell`. Successful calls, rather than agent claims about
their tool list, established visibility.

| Parent state | Process | NeKo | MaBoSS | PhysiCell |
| --- | --- | --- | --- | --- |
| all enabled | parent | visible/call succeeded | visible/call succeeded | visible/call succeeded |
| all enabled | complete NeKo child | visible/call succeeded | visible/call succeeded | visible/call succeeded |
| all enabled | complete MaBoSS child | visible/call succeeded | visible/call succeeded | visible/call succeeded |
| all enabled | complete PhysiCell child | visible/call succeeded | visible/call succeeded | visible/call succeeded |
| all disabled | parent | absent | absent | absent |
| all disabled | complete NeKo child | absent | absent | absent |
| all disabled | complete MaBoSS child | absent | absent | absent |
| all disabled | complete PhysiCell child | absent | absent | absent |

Complete child transport definitions therefore neither narrow an enabled parent nor
enable the permitted server independently of a disabled parent.

Child tables containing only inherited definitions and explicit `enabled`
overrides were also tested for all three modelling servers. Codex 0.153.0 rejected
each definition before child startup as `invalid transport`; partial transport
tables are not supported as merge-only child overrides.

Result: **same-process custom-agent MCP isolation failed**. Same-process specialist
files remain inactive, and prompt-only isolation is not accepted as enforcement.

## Separate-process profile validation

The fallback launches a new `codex exec` process through
`scripts/codex/run_specialist.py`. Each process used Codex 0.153.0, a user-local
complete profile, a read-only sandbox, and fixed command-line `enabled` overrides
for all three modelling servers.

### `network_curator`

Visible NeKo tools:

- `mcp__neko__add_nodes`
- `mcp__neko__analyze_connectivity`
- `mcp__neko__analyze_gene_set`
- `mcp__neko__apply_global_connection`
- `mcp__neko__bridge_components`
- `mcp__neko__compare_network_states`
- `mcp__neko__connect_targeted_nodes`
- `mcp__neko__create_network`
- `mcp__neko__create_session`
- `mcp__neko__export_neko_handoff`
- `mcp__neko__export_network`
- `mcp__neko__filter_interactions`
- `mcp__neko__find_paths`
- `mcp__neko__get_references`
- `mcp__neko__list_artifact_sessions`
- `mcp__neko__list_bnet_files`
- `mcp__neko__list_genes_and_interactions`
- `mcp__neko__list_network_history`
- `mcp__neko__list_sessions`
- `mcp__neko__navigate_network_history`
- `mcp__neko__preview_connection_impact`
- `mcp__neko__remove_bimodal_interactions`
- `mcp__neko__remove_gene`
- `mcp__neko__remove_interaction`
- `mcp__neko__remove_undefined_interactions`
- `mcp__neko__reset_network`
- `mcp__neko__set_default_params`
- `mcp__neko__set_default_session`
- `mcp__neko__set_network_history_limit`
- `mcp__neko__status`

Visible MaBoSS tools: none. Visible PhysiCell tools: none.

### `boolean_dynamics_modeler`

Visible MaBoSS tools:

- `mcp__maboss__bnet_to_bnd_and_cfg`
- `mcp__maboss__build_simulation`
- `mcp__maboss__change_maboss_rule`
- `mcp__maboss__create_session`
- `mcp__maboss__export_maboss_bnd_cfg`
- `mcp__maboss__export_maboss_handoff`
- `mcp__maboss__get_maboss_initial_state`
- `mcp__maboss__get_maboss_logical_rules`
- `mcp__maboss__get_maboss_mutations`
- `mcp__maboss__get_maboss_nodes`
- `mcp__maboss__get_simulation_result`
- `mcp__maboss__import_neko_handoff`
- `mcp__maboss__list_artifact_sessions`
- `mcp__maboss__list_generated_files`
- `mcp__maboss__list_sessions`
- `mcp__maboss__run_simulation`
- `mcp__maboss__set_default_session`
- `mcp__maboss__set_maboss_initial_state`
- `mcp__maboss__set_maboss_output_nodes`
- `mcp__maboss__simulate_mutation`
- `mcp__maboss__update_maboss_parameters`
- `mcp__maboss__visualize_network_trajectories`

Visible NeKo tools: none. Visible PhysiCell tools: none.

### `multicellular_configurator`

Visible PhysiCell tools:

- `mcp__physicell__add_physiboss_input_link`
- `mcp__physicell__add_physiboss_model`
- `mcp__physicell__add_physiboss_output_link`
- `mcp__physicell__add_single_cell_rule`
- `mcp__physicell__add_single_cell_type`
- `mcp__physicell__add_single_substrate`
- `mcp__physicell__analyze_biological_scenario`
- `mcp__physicell__analyze_loaded_configuration`
- `mcp__physicell__apply_physiboss_mutation`
- `mcp__physicell__configure_cell_parameters`
- `mcp__physicell__configure_physiboss_settings`
- `mcp__physicell__create_session`
- `mcp__physicell__create_simulation_domain`
- `mcp__physicell__export_cell_rules_csv`
- `mcp__physicell__export_xml_configuration`
- `mcp__physicell__get_available_cycle_models`
- `mcp__physicell__get_help`
- `mcp__physicell__get_maboss_context`
- `mcp__physicell__get_simulation_summary`
- `mcp__physicell__get_workflow_status`
- `mcp__physicell__import_maboss_handoff`
- `mcp__physicell__list_all_available_behaviors`
- `mcp__physicell__list_all_available_signals`
- `mcp__physicell__list_artifact_sessions`
- `mcp__physicell__list_generated_files`
- `mcp__physicell__list_loaded_components`
- `mcp__physicell__list_sessions`
- `mcp__physicell__load_xml_configuration`
- `mcp__physicell__set_default_session`
- `mcp__physicell__set_maboss_context`
- `mcp__physicell__set_substrate_interaction`
- `mcp__physicell__validate_xml_file`

Visible NeKo tools: none. Visible MaBoSS tools: none.

### `literature_reviewer`

Visible NeKo tools: none. Visible MaBoSS tools: none. Visible PhysiCell tools:
none. No PubMed or other approved structured literature backend is currently
configured, so structured evidence review correctly returns `blocked` unless the
launcher is explicitly given its literature-only web-search option.

## Enforcement decision

The separate-process profile design passed the real-server namespace checks. It is
the only enabled specialist execution path for this repository on Codex 0.153.0.
The launcher also parses `codex mcp list --json` before every launch and stops before
model execution if the permitted server is disabled/missing or a prohibited
modelling server is enabled.
The user-local profiles contain machine-specific transports and are intentionally
untracked. The tracked examples contain placeholders only.

---
name: physicell-workflow
description: "Use this skill whenever working with the PhysiCell MCP server to build, inspect, or edit a tissue/agent-based simulation configuration — domain, substrate, and cell-type setup, cell-parameter and substrate-interaction patches, signal-behavior rules, or XML and cell-rules export. Trigger this any time PhysiCell tools are called or the user mentions PhysiCell, agent-based tissue simulation configuration, PhysiBoSS, or cell rules CSV. Fully standalone; optionally integrates an intracellular Boolean model through a maboss-workflow handoff."
---

# PhysiCell Simulation Configuration Workflow

Operational snapshot for `mcp-biomodelling-servers` 2.3.0. The tool names below
were verified against the installed PhysiCell MCP server. Recheck this skill when
the server package is upgraded.

PhysiCell configures agent-based tissue simulations: domain, substrates, cell
types, and signal-behavior rules. It's a complete tool on its own — pure
tissue-level modelling needs no intracellular model at all. PhysiBoSS
integration (an optional intracellular Boolean model per cell type) is an
add-on; see `maboss-workflow` if the model being imported needs explaining.

Use one session per model; pass `session_id` explicitly with multiple
configurations active.

## Choose the workflow

**New configuration:**
1. `create_session()`
2. `analyze_biological_scenario()` — record the modelling objective.
3. `create_simulation_domain()` — space, mesh, dimensionality, time.
4. `add_single_substrate()` once per substrate.
5. `add_single_cell_type()` once per cell population.
6. `list_all_available_signals()` / `list_all_available_behaviors()` — get
   exact names before writing rules that reference them.
7. Configure each cell type and its substrate interactions.
8. Add signal-behavior rules.
9. Optionally integrate intracellular MaBoSS models via PhysiBoSS.
10. `get_simulation_summary()`, then export the XML and rules CSV.

**Existing configuration:**
1. `validate_xml_file()`
2. `load_xml_configuration()`
3. `analyze_loaded_configuration()` + `list_loaded_components()`
4. Apply targeted changes using the same configuration tools.
5. Recheck `get_simulation_summary()`, export to a new session artifact.

## Repeatable operations and patch semantics

- `add_single_substrate()` — once per substrate
- `add_single_cell_type()` — once per cell type
- `configure_cell_parameters()` — once per cell type (repeatable to revise)
- `set_substrate_interaction()` — once per cell-type/substrate pair
- `add_single_cell_rule()` — once per signal-behavior relationship
- PhysiBoSS input links, output links, and mutations — each repeatable

These tools use **patch semantics**: omitted values are preserved, not
reset to defaults.

- `configure_cell_parameters()` preserves omitted volume, motility, and
  death parameters. Motility only toggles when `motility_enabled` is
  supplied explicitly.
- `set_substrate_interaction()` preserves omitted secretion/uptake rates,
  secretion target, and net export rate.
- `configure_physiboss_settings()` preserves omitted timing,
  stochasticity, scaling, start-time, and inheritance settings.

Provide only the values that should change; each patch call needs at
least one value.

## PhysiBoSS integration

Preferred typed workflow:
1. Export a `maboss-to-physicell` handoff from MaBoSS (see `maboss-workflow`).
2. `import_maboss_handoff()` — verifies and copies the NeKo/MaBoSS
   lineage, attaches the model atomically.
3. `configure_physiboss_settings()` — timing and inheritance.
4. `add_physiboss_input_link()` — PhysiCell signals → Boolean nodes.
5. `add_physiboss_output_link()` — Boolean nodes → cell behaviors.
6. `apply_physiboss_mutation()` — optional fixed-node perturbations.

Standalone files with no handoff manifest: `set_maboss_context()` +
`add_physiboss_model()`.

- Importing manifests for different target cell types preserves a
  separate MaBoSS context per target.
- Replacing an existing target model requires `replace_existing=true`
  and resets that target's PhysiBoSS settings, mappings, and mutations.

Use node names as returned by the MaBoSS server, and signal/behavior
names as returned by the PhysiCell discovery tools — not interchangeable.
MaBoSS parameters and output nodes are retained as context but **not**
auto-translated into PhysiBoSS timing or mappings — call
`configure_physiboss_settings()` and the link tools explicitly.

## Tool-based session inspection

Use MCP tools rather than MCP resources when inspecting a configuration:

- `get_workflow_status()` — progress and recommended next steps.
- `get_simulation_summary()` — consolidated domain, substrate, cell-type,
  cell-rule, and PhysiBoSS state.
- `get_maboss_context()` — stored intracellular-model context by target cell type.
- `list_loaded_components()` — components found after loading existing XML.
- `list_generated_files()` — XML/CSV artifacts for the active session.
- `list_artifact_sessions()` — persisted artifact directories after a restart.

These names were verified as callable tools in `mcp-biomodelling-servers` 2.3.0.
Use configuration tools, not inspection tools, to change state.

## Inspection and export

- `get_workflow_status()` / `get_simulation_summary()` — complete workflow state
- `get_maboss_context()` — all stored target-cell contexts, or one via `cell_type`
- `list_generated_files()` — session-scoped XML/CSV artifacts
- `export_xml_configuration()` — PhysiCell settings XML
- `export_cell_rules_csv()` — CBHG cell-rules file, when rules exist

Files are confined to `PhysiCell/artifacts/<session_id>/`. Use
`list_artifact_sessions()` to rediscover files after a server restart.

## Troubleshooting

- **Rule or interaction call rejected** → re-run
  `list_all_available_signals()` / `list_all_available_behaviors()`.
- **PhysiBoSS settings disappeared after a second import** → check
  whether `replace_existing=true` was used — it resets settings by
  design. Use the link tools to add to an existing model instead of
  re-importing.
- **Can't find files from an earlier session** → `list_artifact_sessions()`;
  files survive a server restart even if the session object doesn't.

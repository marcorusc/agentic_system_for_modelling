---
name: physicell-workflow
description: "Operational guide for the PhysiCell MCP server — domain, substrate, and cell-type setup, parameter and substrate-interaction patches, signal-behavior rules, PhysiBoSS integration, and XML/cell-rules export. Preloaded into the multicellular-configurator subagent; in the main session, delegate PhysiCell work to multicellular-configurator instead of loading this skill."
---

# PhysiCell Simulation Configuration Workflow

Operational snapshot for `mcp-biomodelling-servers` 2.5.1. Tool names and
parameters were checked against the live 2.5.1 schemas (released package with
`physicell-settings` 0.6.3). Behaviour the schemas do not describe follows the
2.5.0 server documentation. Recheck this skill when the server package is upgraded.

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
4. `list_loaded_components(component_type='substrates')` — the configuration
   always holds at least one substrate. If none was specified, the library's
   required default is materialized with origin `library_default`; report its
   name, units and values and never call it biologically neutral.
   `add_single_substrate()` once per biological substrate (the default is
   preserved; a duplicate name fails). Its `units` argument is a cosmetic
   label defaulting to "dimensionless"; set it from the specification rather
   than leaving the default to stand in for a unit.
5. `add_single_cell_type()` once per cell population;
   `get_available_cycle_models()` lists valid `cycle_model` keys.
6. `list_all_available_signals()` / `list_all_available_behaviors(cell_type=...)`
   — get exact names before writing rules that reference them. With
   `cell_type`, phase-exit behaviors follow that cell's configured cycle;
   aliases appear only when the backend provides them.
7. Configure each cell type and its substrate interactions.
8. Add signal-behavior rules.
9. Optionally integrate intracellular MaBoSS models via PhysiBoSS.
10. Optionally `configure_simulation_inputs()` for approved user parameters
    or an existing initial-cell CSV (see below).
11. `get_simulation_summary()`, then export the XML and rules CSV, or a
    portable `export_configuration_bundle()`.

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
  supplied explicitly. `cycle_transitions=[{"from_phase", "to_phase",
  "rate", "fixed_duration"}]` edits existing phase pairs of the selected
  cycle model only; it never converts a duration-based cycle to a
  transition-rate policy. Explicit zero and `false` are meaningful.
- `set_substrate_interaction()` preserves an omitted secretion or uptake
  rate (the only two rates it sets).
- `configure_physiboss_settings()` preserves omitted timing,
  stochasticity, scaling, start-time, and inheritance settings.
  `time_stochasticity` accepts finite nonnegative fractions, including zero.

Provide only the values that should change. Calling
`configure_cell_parameters(cell_type=...)` with no changes inspects the
stored values. Configuration tools return the values actually stored and the
model identity; compare them with the request instead of assuming the request
was applied.

## User parameters and initial-cell CSV (`configure_simulation_inputs`)

- No `parameters`/`cells_csv` means inspection: `inspect_parameters=[...]`
  returns those parameters plus the stored `number_of_cells` and CSV setup.
- Updates: `parameters=[{"name", "type": "int"|"double"|"bool"|"string",
  "value", "units", "description"}]` (at most 25). Type, value and units must
  come from the approved specification — never infer units.
- Registering an existing CSV: `cells_csv=<absolute path>` with explicit
  `csv_enabled=true|false`. The file (≤ 16 MiB, columns `x,y,z,type`, no BOM
  or quoted fields) is captured with its hash. Headerless files use numeric
  cell-type IDs; a matching header selects cell-type names.
- Enabling CSV does not change cell counts or generate placement; with the
  standard template, CSV cells can be additive to `number_of_cells`. Storing
  `number_of_cells` or `random_seed` does not prove the target executable
  reads them — report that as an open compatibility question.

## PhysiBoSS integration

Preferred typed workflow:
1. Export a `maboss-to-physicell` handoff from MaBoSS (see `maboss-workflow`).
2. `import_maboss_handoff()` — verifies and copies the NeKo/MaBoSS
   lineage, attaches the model atomically. Use the original server manifest
   path the orchestrator supplies; relocated copies fail the curation binding. Version 2.1 manifests carry the
   MaBoSS model revision and readout definitions; only declared readouts may
   extend the NeKo core. Report the imported revision and readout names.
3. `configure_physiboss_settings()` — timing and inheritance.
4. `add_physiboss_input_link()` — PhysiCell signals → Boolean nodes.
5. `add_physiboss_output_link()` — Boolean nodes → cell behaviors; optional
   integer `steepness` (omission preserves the library default).
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

- `get_simulation_summary()` — session progress, configured substrates,
  cell types, rules, and PhysiBoSS models, completed steps, and export
  readiness. (`get_workflow_status()` is an alias for it.)
- `get_maboss_context()` — stored intracellular-model context by target cell type.
- `list_loaded_components()` — stored components of created or loaded
  configurations, including substrate origin (`library_default`, `imported`,
  `explicit_configuration`).
- `configure_cell_parameters(cell_type=...)` / `configure_simulation_inputs()`
  with no changes — stored cell settings, user parameters and CSV setup.
- `list_generated_files()` — XML/CSV artifacts for the active session.
- `list_artifact_sessions()` — persisted artifact directories after a restart.

Use configuration tools, not inspection tools, to change state.

## Inspection and export

- `get_simulation_summary()` — complete workflow state
- `get_maboss_context()` — all stored target-cell contexts, or one via `cell_type`
- `list_generated_files()` — session-scoped XML/CSV artifacts
- `export_xml_configuration()` — PhysiCell settings XML
- `export_cell_rules_csv()` — CBHG cell-rules file, when rules exist
- `export_configuration_bundle(working_directory=...)` — a unique ZIP with the
  XML, enabled initial-cell CSV, cell-rule CSVs and per-cell BND/CFG inputs,
  a manifest (configuration revision, dependency hashes, substrate origins,
  verified upstream lineage) and working-directory instructions. Relative
  source inputs need the original executable `working_directory`; the XML
  directory is never assumed. Missing or unknown external inputs fail before
  publication.

Exports are written to the session's artifact directory. Use
`list_artifact_sessions()` to rediscover files after a server restart. A bundle
contains no executable: it is not a simulation run, not a compatibility check
and not scientific approval.

## Troubleshooting

- **Rule or interaction call rejected** → re-run
  `list_all_available_signals()` / `list_all_available_behaviors()`.
- **PhysiBoSS settings disappeared after a second import** → check
  whether `replace_existing=true` was used — it resets settings by
  design. Use the link tools to add to an existing model instead of
  re-importing.
- **Can't find files from an earlier session** → `list_artifact_sessions()`;
  files survive a server restart even if the session object doesn't.

## Boolean to phenotype mapping (verified source semantics)

For Boolean activity x (or the smoothed activity probability), let
H=(2*x)^n/(1+(2*x)^n), where n is link steepness. PhysiBoSS computes:

- activation: base_value + (value-base_value)*H
- inhibition: base_value + (value-base_value)*(1-H)

Thus inhibition uses value at OFF and approaches base_value at ON. With smoothing=0
and n=10, H(1)=1024/1025, leaving 1/1025 (~0.0976%) of the inhibited range. This is
finite-Hill leakage, not exact Boolean switching. Never assume n=10 gives zero rate;
any alternative steepness is an approved numerical choice, passed as the integer
`steepness` of `add_physiboss_output_link` (the engine reads an integer). Compare
the stored values each tool returns with the request and read the exported XML
back before acceptance; the 2.4.0 benchmark's multi-field patch reported success
while apoptosis retained its default. Flag missing capabilities instead of
silently editing scientific XML or inventing a value.

MaBoSS elapsed time = PhysiCell update interval / scaling. Scaling therefore relates
the explicitly declared time units; it is not a dimensionless biological default.
The behavior "cycle entry" is phase-0 exit. Discover exact behavior names and phase
indices from the selected cycle model rather than inferring synonyms.

Worked pattern (illustrative, not a parameter authorization): define mutually
exclusive E/A/B readouts without regulatory targets. Map E activation to G1->S,
A activation to S->G2, B activation to G2->M, and B inhibition to M exit/division.
Explicitly identify which configured phases implement those transitions; approve
values, base values, steepness, smoothing and base cycle rates. Prove the intended
readout exclusivity on declared update semantics and assess asynchronous lag: a proof
about readout Boolean functions alone is not a proof that stored asynchronous readout
nodes are mutually exclusive. Configure all phase exits and verify exported rates.

Use scripts/validate/calibrate_cycle.py with an explicit mapping, target cycle time
and units. It emits proposed scaling, never grants acceptance. Record the approved
proposal artifact and hashes in the handoff provenance. Calibration emulates the
phase mapping; it does not execute PhysiCell. Capture the final XML package through
scripts/capture/record_physicell_config.py and review enabled dependencies.

Source checked: MathCancer/PhysiCell commit
69a23dbe7eaac4f41dc9548ad85072eff7921a03, addons/PhysiBoSS/src/utils.h
(update), maboss_network.cpp (time_to_update/scaling), and
core/PhysiCell_signal_behavior.cpp (cycle entry/phase-0 exit). Recheck after upgrades.

---
name: physicell-workflow
description: Formulate and route governed PhysiCell and PhysiBoSS configuration, mapping, validation, and export tasks through the isolated multicellular specialist.
---

# PhysiCell and PhysiBoSS workflow

Never call PhysiCell tools from the orchestrator or this skill. Send the bounded
`task` to `specialist_dispatcher.start_multicellular_configurator`. Supply
`record_session_id` for an existing approved session and exact `approved_tools`
only for writes already authorized for this invocation.

Query `get_specialist_events` with its sequence cursor and `get_specialist_task`
until terminal. Consume only the validated handoff returned on `succeeded`, then
check its independent scientific status and approval requirements. Do not update
shared state while execution is active. Output remains under
`runs/multicellular-configurator/{physicell_session_id}/specialist-invocations/`.

## Task contract

State whether the task creates a fresh configuration hypothesis or modifies an
explicitly approved session. Provide the domain, dimensionality, substrates and
units, cell populations, parameters, interactions, and validation targets without
inventing missing values. The specialist must discover exact available signal and
behavior names before Cell Rules.

Configuration operations use patch semantics: omitted values remain unchanged.
Require only intended changes and prohibit accidental domain recreation. For an
existing XML, require validation, loading, component inspection, targeted edits,
summary, and a new session-scoped export.

PhysiBoSS integration requires an approved exported MaBoSS handoff. Preserve NeKo
and MaBoSS lineage; do not infer timing, mappings, signal names, behaviors, or
mutations. Every signal-node-behavior mapping is an explicit hypothesis requiring
researcher resolution when unspecified. Export Cell Rules CSV before XML when rules
exist.

Configuration tools return the values actually stored; require the specialist
to report them and compare them with the request. Every configuration holds at
least one substrate: a library default (origin `library_default`) is
materialized when none was specified and must be reported with its units and
values, never called biologically neutral. Cycle edits (`cycle_transitions`)
target existing phase pairs only; output-link `steepness` is an integer;
fractional `time_stochasticity` is allowed. Use
`list_all_available_behaviors(cell_type=...)` for cycle-specific phase exits.

`configure_simulation_inputs` stores explicitly typed user parameters (type,
value and units from the specification) or registers an existing `x,y,z,type`
CSV with explicit `csv_enabled`. It does not change cell counts or generate
placement, and a stored `number_of_cells`/`random_seed` does not prove the target
executable reads it. `export_configuration_bundle` packages XML, enabled CSV,
cell rules and per-cell BND/CFG with hashes and working-directory instructions;
relative inputs need the original `working_directory`. A bundle is neither a
simulation run nor approval. Approve each of these writes only for the invocation
that needs it.

The specialist configures and validates artifacts only. Neither it nor the
orchestrator may claim that PhysiCell simulation was executed or scientifically
validated.

## CLI fallback

If the dispatcher is unavailable, the same bounded request may use
`python scripts/codex/run_specialist.py multicellular_configurator --prompt-file
<project-relative-task-file>`. Place that file in `.codex-tasks/`; add
`--record-session-id` and exact `--approve-tool` entries as applicable. Preserve
all scientific gates and validate the recorded result before synthesis.

## Boolean to phenotype mapping (verified source semantics)

For Boolean activity x (or the smoothed activity probability), let
H=(2*x)^n/(1+(2*x)^n), where n is link steepness. PhysiBoSS computes:

- activation: base_value + (value-base_value)*H
- inhibition: base_value + (value-base_value)*(1-H)

Thus inhibition uses value at OFF and approaches base_value at ON. With smoothing=0
and n=10, H(1)=1024/1025, leaving 1/1025 (~0.0976%) of the inhibited range. This is
finite-Hill leakage, not exact Boolean switching. Never assume n=10 gives zero rate;
any alternative steepness is an approved numerical choice, passed as the integer
`steepness` of `add_physiboss_output_link`. Compare returned stored values with the
request and read exported XML back before acceptance; the 2.4.0 benchmark's
multi-field patch reported success while apoptosis retained its default. Flag
missing capabilities instead of silently editing scientific XML or inventing a value.
Operational semantics were checked against the live `mcp-biomodelling-servers`
2.5.1 schemas; revalidate after server upgrades.

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

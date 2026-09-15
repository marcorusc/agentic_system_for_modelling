# ODE integration validation — 2026-09-15

The BioMASS integration is implemented for Codex and Claude. The existing local
`mcp_modelling` environment was reused without package installation. The scientific
model remains at specification, with no active modelling sessions registered.
Software fixtures used isolated temporary storage; the external MCP repository was
not modified.

## Implemented

- An isolated Codex `ode_modeler` profile and Claude `ode-modeler` definition,
  with matching BioMASS skills and versioned server authoring references.
- Researcher-confirmed formulation selection and an alternative ODE workflow,
  preserving the Boolean/MaBoSS/PhysiCell branch and existing approval gates.
- ODE claim reviews, immutable evidence reports, scoped literature invocation
  provenance, and support for unavailable-backend blocked results.
- Typed ODE completion validation, verified artifact recording, NeKo handoff
  relocation with preserved originals, and immutable export-approval snapshots.
- Optional BioMASS setup and environment reuse, capability-based version checks,
  stable transport PATHs, a writable Numba cache, and bounded startup probes.

The operational contract and commands are in [ODE workflow](ode-workflow.md).

## Automated checks

`python scripts/run_tests.py` passes 171 tests: 120 Codex/contract tests,
19 Claude tests, and 32 setup tests. Coverage includes isolated inventories,
wrong handoff types/lineage, standalone provenance, stale revisions, changed hashes,
failed simulations, unsafe paths, immutable evidence and approvals, bounded probe
cleanup, and environment reuse without package installation.

Run the opt-in real software fixture with the modelling environment's interpreter:

```bash
/path/to/mcp_modelling/bin/python -B tests/integration/biomass_smoke.py
```

Its eight checks pass: syntax/generation, enzyme simulation, exported-bundle
reproduction, verified project capture, typed completion, nonmutating edit preview,
stale-version rejection, and placeholder rejection. Reproduced trajectories match
with `rtol=1e-7`, `atol=1e-8`. These tolerances are software regression criteria;
the example values are not accepted scientific parameters for a project model.

The plugin manifest, both BioMASS skills and Git whitespace checks pass.

## Local activation and isolation

Both clients were configured with `--environment-mode reuse --with-biomass`.
Configuration backups and execution receipts are retained in ignored `.setup/`.
The local Codex plugin was refreshed from the repository marketplace.

| Server | Startup and tool inventory | Tools |
|---|---|---:|
| NeKo | Passed, including export_biomass_handoff | 33 |
| MaBoSS | Passed | 24 |
| PhysiCell | Passed | 34 |
| BioMASS | Passed | 22 |

Codex effective configuration checks pass for every modelling specialist: each
has exactly its own modelling server enabled. The orchestrator has none enabled.
This verifies the CLI configuration boundary; it does not establish absence of
previously granted tools in an already-running desktop conversation.

Detailed local receipts are `.setup/validation/regression.log`,
`.setup/validation/biomass-smoke.json`, `.setup/validation/setup-activation.json`,
`.setup/validation/environment-check.json`, and `.setup/report.json`. These are local
setup records, not scientific-stage evidence.

## Remaining runtime limits

Restart Codex and Claude and begin a fresh conversation to load the changed profiles
and plugin. The sandboxed MCP stdio inventory probe stalled; the same read-only probe
succeeded outside the sandbox. Startup probes now have bounded request waits and
bounded timeout cleanup. No modelling MCP was called by the orchestrator.

Claude inline tool isolation still requires inspection within the running client;
CLI server listing alone cannot prove that boundary. A follow-up configuration
inspection found all four modelling servers registered globally in Claude, with no
relevant disabling entries in the inspected settings. Keep them out of the project's
parent tool inventory while retaining specialist access, then verify the actual
runtime inventories. Restarting alone does not resolve this configuration concern.
Its pre-existing validate-stage
skill requires `scientific-reviewer` and `reproducibility-auditor`, whose definitions
are absent. That requirement is preserved and must be reported as a blocker to
independent scientific stage validation.

The final Codex inventory reports no enabled PubMed backend and no explicitly enabled
web search. Literature review therefore returns a typed blocked result until a backend
is configured or web search is explicitly authorized. Claude already has a PubMed
connection configured; adapting that connection to Codex's isolated literature
profile is a possible fix, subject to authentication and tool compatibility checks.
No live literature search, LLM-driven biological task,
calibration, sensitivity analysis or ODE-to-PhysiCell coupling was performed.

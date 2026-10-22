# Changelog

## 1.0.0 — 2026-10-21

First tagged release. Tested with `mcp-biomodelling-servers` **2.5.0**
(NeKo `nekomata` 1.10.2, PhysiCell Settings 0.6.3, bundled cmaboss, BioMASS 0.14).

### Highlights

- **Marketplace plugin launch, kept isolated.** Specialists start their servers
  with the marketplace plugins' own command,
  `uvx --from mcp-biomodelling-servers==2.5.0 mcp-<server>-server`, inline in each
  specialist only. The tracked agent definitions ship this portable launch; setup's
  new `--environment-mode plugin` writes absolute paths and needs only
  [uv](https://docs.astral.sh/uv/). The `neko`/`maboss`/`physicell`/`biomass`
  plugins themselves must **not** be enabled in this project: Claude Code connects
  an enabled plugin's servers to the main session, giving the orchestrator
  modelling tools. Setup and `scripts/check_isolation.py` fail if they are enabled
  in project, local or user settings.
- **Wave 1 governance and provenance** (merged as PR #6): durable capture and
  indexing of modelling artifacts, guarded specialist reports and invocation
  records, `scripts/state.py` / `scripts/gate.py` stage approvals bound to exact
  reviewed outputs, structured immutable edge evidence, read-only artifact
  validators (`scripts/validate/`), shared PubMed access and the setup isolation
  guard. See `docs/agentic-operations.md` and `docs/wave1-pr-review.md`.
- **Wave 2 adoption of the 2.5.0 servers** (`docs/wave2-design-decisions.md`):
  - NeKo `edit_interactions` for explicitly authorized `manual-literature` edges
    between existing nodes, never hand-edited SIF; paged history and history export.
  - MaBoSS `edit_maboss_readouts` for researcher-named `readout` nodes, per-node
    rates via `update_maboss_parameters(rates=…, expected_revision=…)`, durable run
    IDs for ordinary and mutant runs, and run-scoped results and plots.
  - PhysiCell `configure_simulation_inputs` (typed user parameters with units,
    existing initial-cell CSV) and `export_configuration_bundle`; stored-value
    readback and required-substrate origin.
  - Approvals bind to the exact NeKo state or MaBoSS `model_revision`; any later
    interaction, rule, readout or rate edit supersedes them.

### Handoff contracts

- `gate.py` and the capture recorders accept NeKo→MaBoSS and MaBoSS→PhysiCell
  1.0/2.0/**2.1** and NeKo→BioMASS 1.0/**2.0**. Unknown versions are rejected,
  and 1.0 documents cannot carry the new fields.
- The `curation_file` NeKo history companion is copied, hashed and checked against
  the handoff's session, state and every non-path identity field.
- MaBoSS 2.1 requires `model_revision` and explicit `readouts`. Each readout must
  match its BND rule and may not feed core nodes. Readouts are the only nodes
  allowed beyond the NeKo parent.
- **Workflow change:** 2.5.0 binds each companion to the model file's original
  absolute path, so import tools reject relocated copies. Specialists import the
  recorder's `backend_import_manifest`; the project capture stays the record that
  gates and approvals bind to.
- `scripts/capture/verify_import_manifest.py` confirms, before dispatch, that the
  backend manifest handed to a specialist is byte-identical to the captured
  original and that its payloads are unchanged. All three recorders return
  `backend_import_manifest` when a curation binding applies.
- The NeKo Boolean recorder captures the `<bnet>.lineage.json` source-lineage
  sidecar unchanged when present, after checking it describes exactly this BNET and
  history companion.
- `gate.py check biomass_ode` now works for real NeKo→BioMASS manifests: the
  approval's `--outputs` must name every `node_id` of the exported graph (the
  whole-graph scope), in addition to the hash, companion, review and registry
  checks. Previously this stage could never pass.
- The ODE recorder accepts `--artifact-root`. 2.5.0 servers write to
  `~/.cache/mcp-biomodelling/artifacts/<Server>` by default.

### Setup

- `setup/dependencies.toml` pins 2.5.0 / `nekomata` 1.10.2.
- No MaBoSS executable or system Graphviz is required. Setup no longer
  auto-discovers `dot`, conda installs only Python, and `--graphviz-path` remains
  an optional override.
- Plugin mode verifies the resolved server version, reports dependency drift from
  the tested pins as warnings, and probes every server through the exact launch.
  Settings saved from another mode are not carried over.
- The source-install example (`setup/backend-sources.integration.json`) pins the
  `v2.5.0` and official NeKo `v1.10.2` release commits.
- CI installs the released backend set from `setup/dependencies.toml`, and a new
  job starts all four servers through the uvx plugin launch.
  `setup/requirements-wave1-review.txt` (unreleased Wave 1 sources) is removed.

### Prompts and skills

- All operational skills are snapshots of 2.5.0, checked against the live tool
  schemas. The 2.4.0 prompt audit is merged; literature review keeps Wave 1's
  per-edge search caps.
- The README now documents the `scientific-reviewer` and `reproducibility-auditor`
  agents behind `/validate-stage`, and the portable transports.
- The Codex plugin manifest version is now `1.0.0`. Setup refreshes installed
  copies.

### Upgrading

- Re-run setup after pulling: `python scripts/setup.py --client claude
  --environment-mode plugin` (uv only), or select a **new** `--env-prefix` for a
  managed 2.5.0 environment. An existing 2.4.0 environment cannot be upgraded in
  place. Restart Claude Code / Codex afterwards.
- Disable any `neko@marcorusc`, `maboss@marcorusc`, `physicell@marcorusc` or
  `biomass@marcorusc` plugin enabled at user scope before working in this project.
- Historical artifacts keep their original versions and remain readable. New
  manifests from 2.5.0 servers need this release's gate and recorders.

### Known limitations

- Headless runs (`claude -p`, SDK) and untrusted folders skip inline subagent MCP
  servers. Verify specialists interactively (`/agents`, then a read-only task).
- Codex: the parent-isolation check blocks enabled servers named `neko`, `maboss`,
  `physicell` or `biomass` in `codex mcp list`. Whether Codex lists servers from an
  installed plugin there is unverified, so do not `codex plugin add` the modelling
  plugins for this project.
- The plugin launch pins only the server package. For an exact installed snapshot
  (`resolved-requirements.txt`), use a managed environment.
- Deferred Wave 2 items remain deferred: the NeKo→MaBoSS import investigation
  (B-MB-2), MaBoSS_test integration, new analysis algorithms and the broader
  testing campaign.

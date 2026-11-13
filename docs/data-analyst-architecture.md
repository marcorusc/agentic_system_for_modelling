# Data-analyst specialist: architecture and design rationale

**Document status:** describes the `data-analyst` specialist and the cross-specialist
capture changes introduced with it (Claude Code only), tested with Claude Code 2.1.311
and `mcp-biomodelling-servers` 2.5.2. For day-to-day use, see
[data workflow](data-workflow.md); for the overall system, see the
[architecture](agentic-biomodelling-architecture.md). Where this document and the code
disagree, the code is authoritative.

## 1. Purpose and scope

The modelling stages had no data layer: `inputs/` only held files the researcher
supplied. The `data-analyst` specialist retrieves public and researcher-supplied data
(e.g. TCGA via GDC/cBioPortal, GEO, PRIDE, DepMap and GDSC files in `inputs/`) and
analyses it. Its results come back as hashed **data products** and **proposals**
(e.g. NeKo seed genes, Boolean perturbation scenarios and validation targets). The
researcher reviews and approves them before they reach a model.

It is **cross-cutting, not a pipeline stage**: it can be invoked at any point, and its
products feed the specification, topology and dynamics stages.

**Not covered here:**
- BioMASS and PhysiCell data inputs;
- Codex parity;
- OS-level sandboxing.

## 2. Key decisions and rationale

| Decision | Rationale |
|---|---|
| **Vendored scientific skills** under `vendor/scientific-agent-skills/` (12 skills from K-Dense-AI/scientific-agent-skills at a pinned commit, byte-identical except one documented fix, hash-locked) | Claude Code cannot scope a skill to one subagent. Files in `.claude/skills/` are visible to the orchestrator, and preloading all guides would cost about 40k tokens per invocation. Vendoring keeps them out of skill discovery. A small preloaded `data-workflow` skill indexes them, and the agent reads only what it needs. |
| **Bash under guard hooks**, not a data MCP server | The skills are script-based. Guarded Bash was fastest to build; a dedicated MCP server remains possible later. |
| **Data-to-model choices are proposals** | `CLAUDE.md` forbids silently selecting seeds, states, mutations or parameters. Every proposal needs researcher approval and is tagged `data-derived` in `DECISIONS.md`. |
| **Associations are not mechanisms** | Co-alteration or co-expression never establishes an edge. Candidate edges go to `literature-reviewer`. |
| **Mechanical handoff** (`scripts/data/handoff.py`) | In live tests, LLM-written envelopes failed validation (string `schema_version`, wrong paths, `blocked` status carrying proposals). The envelope is now generated from the manifest; the agent only supplies narrative notes. |
| **Recorder-written reports** for all specialists | Claude Code 2.1.311 rejects subagent Writes to `^(REPORT\|SUMMARY\|FINDINGS\|ANALYSIS).*\.md$` (undocumented, not configurable). Specialists return their report as the final message, and the SubagentStop recorder writes the immutable `report.md`. |
| **Post-run recovery step** | SubagentStop fired for only 2 of 8 background runs in live tests. `recover.py` (modelling specialists) and `receive.py` (data analyst) record a missing capture from the subagent transcript. |
| **Exports saved after every run** | Each specialist's inline MCP server stops with its run, so a NeKo session never outlives the agent run that created it. `recover.py` copies each run's exports into the repository. network-curator always exports SIF and history. NeKo networks can be rebuilt only from a saved SIF. |
| **Complete figure and report descriptions** | Researchers found one-line captions and undefined abbreviations hard to interpret. Figure metadata and the report's Figures and Abbreviations sections are enforced. |

## 3. Components

| Component | Role |
|---|---|
| `.claude/agents/data-analyst.md` | Agent definition: tools Read/Grep/Glob/Write/Bash; no MCP, Skill, Agent or Edit; preloads `data-workflow`; guard hooks on Bash and Write. |
| `.claude/skills/data-workflow/SKILL.md` | Session lifecycle, command rules, an index of vendored guides, data-source notes (DepMap verification wall, cBioPortal API fallback, PDF/Excel source documents, ledger `terms`), required figure sets and recipe, report template. |
| `vendor/scientific-agent-skills/` | Vendored guides with `VENDOR.md`, `VENDOR.lock.json`, upstream `LICENSE.md`/`CITATION.cff`. Licences and citation are in `THIRD_PARTY_NOTICES.md` and the README. |
| `scripts/data/session.py` | Creates `runs/data-analyst/<id>/` and the protected-state snapshot. Prints the binding line `Data session created: <id> (snapshot sha256=…)`. |
| `scripts/data/fetch.py`, `ledger.py` | Content-addressed download cache (`data-cache/sha256/…`, read-only entries, re-hashed on reuse) and an append-only source ledger (`sources.jsonl`; `terms` must be quoted or `unverified`). |
| `scripts/data/manifest.py` | Hashes scripts, outputs, proposals and sources. Checks units on numeric columns, figure metadata, per-session sources, and that no file is unlisted. |
| `scripts/data/handoff.py` | Builds `handoff.json` mechanically and enforces the status rules. |
| `scripts/data/receive.py` | Orchestrator step after each data run: recovery, manifest verification, handoff validation, report checks, decision table. |
| `scripts/capture/recover.py`, `exports.py`, `transcripts.py` | Recovery of missing SubagentStop captures for the modelling specialists, and export saving. |
| `.claude/scripts/data_guard.py` | The data analyst's Bash allowlist and Write confinement. |
| `.claude/scripts/data_orchestrator_guard.py` | Main-session tripwire against running vendored code or data tools. |
| `scripts/state.py data-product` | Registers an approved product in `DATA_DICTIONARY.md`. |
| `scripts/data/environment.py`, `setup.py --with-data` | Pinned `.venv-data` (Python 3.12), checked against the lock. Optional `--with-cellprofiler`. |

## 4. Flow

1. **Brief.** The orchestrator writes a bounded brief that lists every upstream artifact
   the analyst may read, with path and sha256.
2. **Session.** The analyst runs `session.py new`. This binds the session for the guard
   and snapshots protected state.
3. **Analysis.** All work is saved scripts run with `.venv-data/bin/python -E -s`.
   Downloads go through `fetch.py` or `ledger.record_api`. Outputs, figures and
   proposals are indexed with units and metadata.
4. **Handoff.** `manifest.py build`/`verify`, then `handoff.py build`. The final message
   is the report and ends with `Handoff: runs/data-analyst/<id>/handoff.json sha256=<hex>`.
5. **Receive.** The orchestrator runs `receive.py` immediately after the completion
   notification and before any state write. It recovers a missing capture, verifies the
   manifest, validates the handoff, checks the report's Handoff line and its Figures and
   Abbreviations sections, then prints the decisions.
6. **Approval.** The researcher approves. The orchestrator records a `stage_approval`
   (stage `data`, artifact = `handoff.json`) and registers products with
   `state.py data-product`, which requires that exact approval.

**Modelling specialists** (network-curator, boolean-dynamics-modeler,
multicellular-configurator, ode-modeler) follow the same post-run rule: the orchestrator
runs `recover.py` after each completion notification, before registry or state writes.

## 5. Contracts

- **Session layout** under `runs/data-analyst/<id>/`: `identity.json`, `sources.jsonl`,
  `scripts/`, `raw/`, `outputs/` (with `index.json`), `proposals/` (with `index.json`),
  `manifest.json`, `handoff_notes.json`, `handoff.json`, `integrity.json`, `report.md`,
  `invocation/`.
- **Status rules:**

  | Situation | Status |
  |---|---|
  | Any proposal, including partial results with blocked parts | `needs_approval` (blocked parts become decision items) |
  | Outputs only, nothing blocked | `completed` |
  | Nothing produced | `blocked` (must state why) |
  | Verification failure | `failed` |

- **Validator:** proposal decisions are matched to proposals by id, path and sha256.
  `report.md` must equal the recorded final report.
- **Integrity anchor:** the recorder's invocation record registered in `runs/index.json`.
  `integrity.json` is a convenience copy and is never trusted on its own.
- **Exports:** saved to `runs/<specialist>/<session>/exports/<invocation>/` with
  `exports.json` (source path, sha256, size). Only files from that session's server
  artifact folder are accepted. A capture is never amended; a rerun is checked against
  the saved copies.
- **NeKo restore** happens only on explicit authorisation:
  - `create_network(sif_file=<saved SIF>)` into a new session, with node and edge counts
    verified (SIF `#` comment lines excluded);
  - the old session id is never passed to NeKo;
  - the new session is registered as derived from the old one and needs fresh approvals;
  - earlier literature reports are cited, never copied.

## 5a. Data-to-model handoffs

Sub-project 2 is implemented. Approved proposals reach the models in two typed paths:

| Layer | Proposal kind | Path |
|---|---|---|
| NeKo | `seed_genes` | `DATA_INPUT` on line 1 of the network-curator brief names the proposals and hashes. |
| MaBoSS | `perturbations`, `validation_targets` | The orchestrator drafts `runs/orchestrator/<p>/mapping.json` with `mapping.py`, the researcher decides it, `mapping.py check` passes, and a `data_mapping` approval is recorded. `DATA_INPUT` on line 2 of the boolean-dynamics-modeler brief names the mapping. |

The dispatch hook checks both lines against the durable records. Criteria generated from
the mapping and the modeler's trajectories are evaluated by `evaluate.py`, including
`scenario_contrast`. See [data workflow](data-workflow.md) for the procedure.

## 6. Guardrails and threat model

- **Data guard:**
  - Bash is limited to `.venv-data/bin/python -E -s <script>` (session scripts, vendored
    scripts, and `scripts/data/{session,fetch,manifest,handoff}.py`) plus plain `ls` and
    `head`, on a single line with no shell metacharacters.
  - Write is limited to the active session directory, never to recorder-owned or
    script-owned files.
  - The session is bound from the subagent's own transcript, derived from `agent_id`.
    Transcripts are split on `\n` only, because Claude Code leaves U+0085/U+2028
    unescaped inside JSON strings.
- **Orchestrator tripwire:** the main session cannot run vendored scripts, `.venv-data`,
  or the data tools that create or modify sessions. Read-only verification
  (`manifest.py verify`, `vendor_lock.py verify`, `receive.py`, `recover.py`) is allowed.
- **Tamper check:** a protected-state snapshot (file hashes plus a digest of the
  installed `.venv-data` distributions) is taken at session start and verified by the
  recorder. Machine-local `.claude/settings.local.json` is excluded.
- **Threat model:** these controls catch accidental and undisciplined writes (buggy
  scripts, an agent ignoring instructions). They do not stop a deliberately adversarial
  agent, which can forge provenance files with user-level Python. That would need
  OS-level confinement, which is a possible follow-up.
- **Isolation check:** `check_isolation.py`, also run by setup verification, rejects
  vendored skills installed under the user's skills directory.

## 7. Known limitations

- **SubagentStop is unreliable** for background subagents in Claude Code 2.1.311.
  Recovery depends on the orchestrator running `recover.py`/`receive.py`.
- **A run that binds more than one session** gets no export capture (the recorder's
  one-session-per-invocation rule).
- **Legacy pre-2.5 managed-environment export locations** (inside `site-packages`) are
  refused and reported, not captured.
- **DepMap downloads** sit behind human verification. Files must be placed in `inputs/`;
  single-gene queries can use Open Targets.
- **CellProfiler** (`--with-cellprofiler`, 4.2.8.1 on Python 3.9) is pinned but not
  install-verified; it needs `mysql_config` and a JDK.
- **Data-analyst checkpoints** can commit large `raw/` downloads. Whether to keep these
  out of git is an open decision.

## 8. Roadmap

1. **Sub-project 2 (implemented):** typed data-to-model handoffs for NeKo (seed proposals
   via `DATA_INPUT`) and MaBoSS (a researcher-approved mapping to model nodes, checked
   against the exported network; `scenario_contrast` criteria). See section 5a.
2. **Later:** BioMASS and PhysiCell data inputs; Codex parity (pending, low priority); a
   possible data MCP server or OS-level sandbox.

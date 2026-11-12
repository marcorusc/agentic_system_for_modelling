# Data-analyst specialist: core agent design (sub-project 1)

Status: draft for researcher review · Date: 2026-11-12 · Branch: `feature/data-analyst-agent`

## 1. Purpose

The framework has no data layer: `inputs/` only holds files the researcher supplies.
This sub-project adds a **`data-analyst` specialist** for Claude Code. It retrieves
public and researcher-supplied data, analyzes it, and returns **versioned, hashed data
products** plus **proposals** for the modelling layers. Examples of proposals: NeKo seed
genes, MaBoSS initial states and validation targets, BioMASS time courses, PhysiCell
parameters.

The data analyst is **cross-cutting, not a pipeline stage**. It may be invoked at any
point, and its products are consumed by other stages through typed handoffs.

### Roadmap (separate specs)

| # | Sub-project | Status |
|---|---|---|
| 1 | Core data agent, Claude side (this document) | design |
| 2 | Integration with modelling layers: layer-specific proposal schemas and typed handoffs (NeKo seeds first, then MaBoSS, BioMASS, PhysiCell), `gate.py` data-product checks, reviewer/auditor checklists | later |
| 3 | Codex parity: a dispatcher profile for a writable, network-enabled specialist, `AGENTS.md`, launcher allowlist | later |

### Success criteria

1. The orchestrator (main session) cannot run the vendored scientific skills or the data
   environment. The guard hook denies it, and it has no skill listing for them.
2. `data-analyst` can execute only allowlisted commands, can write only inside its
   active session directory, and any change outside that directory is detected and
   fails the handoff.
3. A data session produces `manifest.json` and `report.md`. Every source, script and
   output is hashed, and `manifest.py verify` passes.
4. `scripts/codex/validate_handoff.py` accepts a valid `data_analyst` handoff and rejects
   a tampered one.
5. An offline end-to-end smoke test passes: synthetic counts → DESeq2 → enrichment →
   seed-gene proposal returned as `needs_approval`.
6. Vendored skills are cited and their licenses honored (§4).

## 2. Decisions taken (researcher-approved, 2026-11-12)

| Topic | Decision |
|---|---|
| Role | Cross-cutting producer of versioned data products; typed handoffs to consumers |
| Execution | Bash with guard hooks (option a). A dedicated data MCP server may come later |
| Data→model choices | Always proposals; researcher approval recorded in `DECISIONS.md` with a new `data-derived` tag |
| Data-derived edges | Associations are hypotheses; candidate edges go to `literature-reviewer` |
| Skill placement | Vendored outside skill discovery (`vendor/`), indexed by one preloaded `data-workflow` skill; orchestrator must not use them |
| Skill set | `depmap`, `database-lookup`, `gget`, `bulk-rnaseq`, `pydeseq2`, `pathway-enrichment`, `cellprofiler`, `statistical-analysis`, `scikit-learn`, `uncertainty-and-units` |
| Read-only shell | `ls` and `head` are allowed in addition to the pinned Python |
| CellProfiler | Optional install (`--with-cellprofiler`), not part of the default environment |

**Rationale for `vendor/` over `.claude/skills/`.** Claude Code has no documented way to
make a project skill visible to only one subagent. `disable-model-invocation: true`
hides a skill from the main session but also prevents preloading it into subagents.
Preloading all 10 SKILL.md files would also cost about 40k tokens on every invocation. A
non-discovered `vendor/` directory plus one small preloaded index skill keeps the
orchestrator unaware of the skills and lets the agent read only the guides it needs.
It also gives Codex (sub-project 3) the same files.

## 3. Components

### 3.1 Vendored skills: `vendor/scientific-agent-skills/`

```
vendor/scientific-agent-skills/
  LICENSE.md            # upstream MIT license, verbatim
  CITATION.cff          # upstream citation file, verbatim
  VENDOR.md             # upstream URL, commit 2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5,
                        # vendoring date, skill list with per-skill license,
                        # local modifications, re-sync procedure
  depmap/ database-lookup/ gget/ bulk-rnaseq/ pydeseq2/ pathway-enrichment/
  cellprofiler/ statistical-analysis/ scikit-learn/ uncertainty-and-units/
```

- Skills are copied **byte-for-byte** from the pinned commit. Local modifications are
  allowed only when they fix a verified defect. Each one is:
  1. listed in `VENDOR.md` with rationale and the upstream issue link, if one is filed;
  2. marked in the modified file with a `# Local modification (agentic_system_for_modelling, YYYY-MM-DD): …` comment;
  3. covered by a test.
- Initial local modification: `pydeseq2/scripts/run_deseq2_analysis.py`. `save_results`
  converts `pandas.Series` values in `adata.uns` (e.g. `trend_coeffs`) to `dict` before
  `write_h5ad`. Verified on 2026-11-12 with pydeseq2 0.5.4 and anndata 0.13.4: without
  this change the script crashes after writing the CSVs, so no plots or manifest are
  produced.
- `vendor/` must never be placed under `.claude/skills/` or `skills/`.
  `check_isolation.py` enforces this.

### 3.2 Attribution

- `THIRD_PARTY_NOTICES.md` (repository root) contains:
  - each vendored skill with its declared license (MIT; BSD-2/BSD-3 for `gget`,
    `scikit-learn`; **CC-BY-4.0** for `depmap`, author Kuan-lin Huang) and author;
  - the full upstream MIT text;
  - the modification statements required by CC-BY-4.0 and Apache-2.0, pointing to
    `VENDOR.md`.
- A README "Citation and third-party skills" section asks users to cite:
  - the preferred citation: Kassis T., Agarwal V., He Y., Patel D., et al., *Scientific
    Agent Skills: A Library of Procedural Knowledge for Research Agents* (K-Dense; full
    reference copied from upstream `CITATION.cff`);
  - the repository `K-Dense-AI/scientific-agent-skills` at commit `2d2065f`.
- `data-analyst` reports list which vendored skills guided the session, so individual
  analyses can be cited too.

### 3.3 `data-workflow` skill

`skills/data-workflow/SKILL.md` is canonical. `.claude/skills/data-workflow/` is a copy,
following the existing `neko-workflow` pattern. It is the only skill preloaded into
`data-analyst` and contains:

1. Session lifecycle: create with `session.py`, work, finalize with `manifest.py build`
   and `manifest.py verify`, return the handoff.
2. Command rules: the allowlist (§5.1), with every analysis written as a script in
   `scripts/` and then executed.
3. Task → vendored-guide index. For example, "DepMap dependencies → read
   `vendor/scientific-agent-skills/depmap/SKILL.md`, then the needed references"; "TCGA
   → `database-lookup/references/tcga-gdc.md`, `cbioportal.md`".
   - Read the guide's `SKILL.md` first and load references only on demand.
   - Vendored scripts are invoked by path, never copied.
4. DepMap access notes:
   - The portal catalogue may return a verification page. Use researcher-downloaded files
     from `inputs/`, referenced by hash.
   - For single-gene queries, the Open Targets `depMapEssentiality` endpoint can be used.
5. Scientific rules, restated from `CLAUDE.md`:
   - never infer units or identifiers;
   - never invent values;
   - associations are not mechanisms;
   - every data→model choice is a proposal;
   - report limitations;
   - record releases.
6. Report and handoff templates (§6).

### 3.4 Agent definition: `.claude/agents/data-analyst.md`

| Field | Value |
|---|---|
| `tools` | `Read`, `Grep`, `Glob`, `Write`, `Bash` |
| `disallowedTools` | `Edit`, `Skill`, `Agent`, `mcp__*` (the `Agent` deny prevents delegation) |
| `mcpServers` | none |
| `skills` | `data-workflow` |
| `model` | `inherit` |
| `permissionMode` | `acceptEdits` (as with existing specialists) |
| `maxTurns` | 105 (as with `network-curator`) |
| `hooks.PreToolUse` | `Bash` → `data_guard.py bash`; `Write` → `data_guard.py write` |

The agent body follows the style of the existing specialists. It covers the authority
boundary (no shared-state edits, no stage advancement, no approvals), the
`needs_approval` discipline for proposals, and the requirement to return one typed
handoff (§6.3).

### 3.5 Scripts: `scripts/data/`

| Script | Responsibility |
|---|---|
| `session.py new --purpose TEXT [--derived-from ID]` | Creates `runs/data-analyst/<id>/` and its subdirectories, plus `identity.json` (purpose, UTC start, derived-from, protected-state snapshot §5.3). Prints exactly `Data session created: <id>` as its final line. |
| `fetch.py --session ID --url URL --release TEXT [--terms TEXT]` | Downloads into `data-cache/sha256/<hash>`, a content-addressed, gitignored cache that is reused across sessions. Writes `raw/<name>.source.json` and appends to the session's `sources.jsonl`. Refuses HTML when tabular data was expected, mirroring the depmap helper. |
| `ledger.py` (importable) | `record_api(session, url, params, response_path, release)` for API calls made inside analysis scripts. It saves the raw response in `raw/` and appends to `sources.jsonl`. |
| `manifest.py build --session ID` / `verify --session ID` | Builds `manifest.json` from `identity.json`, `sources.jsonl`, `scripts/`, `outputs/index.json` and `proposals/index.json`. `verify` checks hashes, required fields, units on numeric outputs and safe paths. |

Session IDs have the form `data-<YYYYMMDDTHHMMSSZ>-<8 hex>` and satisfy
`validate_session_id`.

### 3.6 Environment

- `setup.py --with-data` creates `.venv-data` (Python 3.12, via uv or the existing
  environment modes) from:
  - `setup/data-requirements.txt`: pinned direct dependencies, e.g. `pydeseq2==0.5.4`,
    `gseapy==1.3.1`, `decoupler`, `scikit-learn`, `statsmodels`, `scipy>=1.11`, `pandas`,
    `numpy`, `matplotlib`, `pint`, `uncertainties`, `gget`, `requests`;
  - `setup/data-requirements.lock`: a fully resolved lock file.
- Exact pins are decided in the implementation plan and verified by installation.
- `--with-cellprofiler` optionally adds CellProfiler. The `cellprofiler` guide states that
  it must be installed first, and the agent returns `blocked` if it is missing.
- `setup.py --check` reports the data environment status. `.venv-data/` and `data-cache/`
  are added to `.gitignore`.

### 3.7 Orchestrator-side changes

- **`CLAUDE.md` / `AGENTS.md` policy:**
  - data retrieval and analysis are delegated to `data-analyst`;
  - the orchestrator does not run vendored scripts or `.venv-data`;
  - approvals of proposals are recorded with the `data-derived` tag, citing the data
    session ID, proposal id and SHA256;
  - data-analyst invocations never run concurrently with other specialists or with
    state writes (§5.3).
  - Two existing sentences are amended explicitly rather than contradicted:
    - "Guarded report Write is their only local authoring exception" gains: "data-analyst
      may also author scripts, outputs and proposals inside its own guarded session
      directory".
    - "Each MCP issues its own ID" gains: "data-analyst IDs are issued by
      `scripts/data/session.py`".
- **Session registry:**
  - `scripts/state.py` `ROLES` gains `"data-analyst": "data"`;
  - data sessions are registered in the `CURRENT_STATE.md` lineage table like any other
    specialist session;
  - a proposal's `Handoff` value follows the existing `pending → approved` transition.
- **Main-session guard:** a `settings.json` PreToolUse `Bash` hook runs
  `.claude/scripts/data_orchestrator_guard.py`. It denies a command that references
  `vendor/scientific-agent-skills` or `.venv-data` when the hook input has no `agent_id`,
  or when `agent_type` ≠ `data-analyst`.
- **Provenance tag:** `data-derived` is added to the `DECISIONS.md` template and the
  documented tag list.
- **Indexes and validators:**
  - `data-analyst` is added to `scripts/capture/index.py` `SPECIALISTS` and to the
    `record_specialist_invocation.py` SubagentStop flow.
  - The SubagentStop flow also runs the tamper check (§5.3).
  - `scripts/codex/validate_handoff.py` gains the `data_analyst` specialist and the
    `data` stage. Required completed artifacts are `manifest.json`, `report.md`, and at
    least one file under `outputs/` or `proposals/`.
- **`check_isolation.py` additionally asserts:**
  - `data-analyst` declares no MCP servers;
  - no vendored skill exists under `.claude/skills/` or `skills/`;
  - the main-session guard hook is registered.

## 4. Licensing obligations (summary)

| License | Skills | Obligation honored by |
|---|---|---|
| MIT | most | upstream `LICENSE.md` kept; notice in `THIRD_PARTY_NOTICES.md` |
| BSD-2/BSD-3 | `gget`, `scikit-learn` | notice retained in `THIRD_PARTY_NOTICES.md` |
| CC-BY-4.0 | `depmap` | attribution (author, source, license link) + indication of changes (`VENDOR.md`) |

(`pymc`/`pymoo`, which are Apache-2.0, are not vendored in this sub-project.)

## 5. Guardrails

### 5.1 Bash allowlist (`data_guard.py bash`)

A command is allowed only if it is a single simple command in one of these forms:

1. `.venv-data/bin/python -E -s <script> [args…]`, where `<script>` resolves (no
   symlinks, no `..`) to:
   - `runs/data-analyst/<active>/scripts/*.py`,
   - `vendor/scientific-agent-skills/*/scripts/*.py`, or
   - `scripts/data/*.py`;
2. `ls [options] [paths…]` or `head [options] [paths…]`.

`-E -s` ignores `PYTHON*` environment variables and the user site-packages. `-I` is not
used because it also drops the script's own directory from `sys.path`. Six vendored
scripts (in `bulk-rnaseq` and `uncertainty-and-units`) import helper modules from that
directory, so they would fail. Script directories hold only pinned vendored code or
agent-written scripts. Downloaded data never lands there: it goes to `data-cache/` and
`raw/`.

Rejected: pipes, `;`, `&&`, `||`, backgrounding, `$( )`, backticks, redirections, globs
that escape the repository, environment-variable prefixes, and any other executable.
The `<active>` session is bound from the transcript: it is the most recent
`Data session created: <id>` line returned by an allowed `session.py new` call in the
current invocation. Prose cannot authorize a path. Before a session exists, only
`session.py new`, `ls` and `head` are allowed.

### 5.2 Write guard (`data_guard.py write`)

`Write` is allowed only to paths under `runs/data-analyst/<active>/`, with no symlinks
and no `..`. `identity.json` and `manifest.json` may only be written by scripts, never
through the Write tool.

### 5.3 Tamper check

Hooks control what is *invoked*, but executed Python can write anywhere. Therefore:

1. `session.py new` records in `identity.json` the `git status --porcelain=v1 -z` output
   and SHA256 values of tracked and untracked files outside the allowed zones. The
   allowed zones are `runs/data-analyst/<active>/` and `data-cache/`. `.venv-data/` is
   excluded from checking.
2. The SubagentStop flow recomputes the snapshot. Any difference marks the invocation
   record **failed**, lists the changed paths, and makes `validate_handoff` reject the
   session.
3. `.git/` is excluded from the snapshot.
4. **No concurrency.** A data-analyst invocation must not run concurrently with other
   specialists or with orchestrator state writes, because their legitimate changes
   would otherwise be reported as tampering. The orchestrator policy in §3.7 states
   this.

### 5.4 Network and secrets

- Network access is allowed, but only to documented database APIs and download
  endpoints named in the vendored guides, or to URLs the researcher supplies. General web
  search or scraping is not allowed; this is consistent with `CLAUDE.md`, under which web
  search needs explicit researcher authorization.
- All file downloads go through `fetch.py`, and API calls inside scripts use
  `ledger.record_api`.
- The reproducibility auditor (sub-project 2 checklist) compares scripts with
  `sources.jsonl`.
- No credentials are handled; licensed or registration-only sources (e.g. COSMIC) are out
  of scope.
- Researcher files in `inputs/` are read-only and referenced by SHA256.

## 6. Data-product contract

### 6.1 Session layout

```
runs/data-analyst/<session_id>/
  identity.json      # session.py: purpose, start, derived_from, protected snapshot
  sources.jsonl      # fetch.py / ledger.py append-only source ledger
  manifest.json      # manifest.py build
  report.md          # agent-written
  scripts/           # every executed analysis script
  raw/               # raw API responses; *.source.json pointers to data-cache
  outputs/           # tables/figures + index.json (description, units, identifiers)
  proposals/         # proposal files + index.json
```

### 6.2 `manifest.json` (schema_version 1)

```json
{
  "schema_version": 1,
  "specialist": "data_analyst",
  "stage": "data",
  "session_id": "data-20261112T091500Z-a3f9c2e1",
  "derived_from_session_id": null,
  "environment": {"python": "3.12.x", "lock_sha256": "…"},
  "vendored_skills_used": ["pydeseq2", "pathway-enrichment"],
  "sources": [{"kind": "download|api|input", "uri": "…", "release": "…",
               "retrieved_at": "2026-11-12T09:15:00+00:00", "sha256": "…", "terms": "…"}],
  "scripts": [{"path": "scripts/01_de.py", "sha256": "…"}],
  "outputs": [{"path": "outputs/de.csv", "sha256": "…", "description": "…",
               "units": {"log2FoldChange": "log2 ratio", "padj": "dimensionless"},
               "identifiers": "HGNC symbol"}],
  "proposals": [{"id": "P1", "target_layer": "spec|neko|maboss|biomass|physicell",
                 "kind": "seed_genes|initial_states|mutations|validation_targets|parameters|time_course",
                 "path": "proposals/P1_seed_genes.csv", "sha256": "…",
                 "method": "…", "thresholds": {"padj": 0.05}, "status": "proposed"}]
}
```

`verify` requirements:
- every numeric table output declares `units`, per column or `"dimensionless"`;
- every output declares an `identifiers` type, or `"none"`;
- every source has `release` (or `"unversioned"` plus `retrieved_at`) and `sha256`.

### 6.3 Handoff

The envelope is the same as for existing specialists: `schema_version`,
`specialist=data_analyst`, `status`, `stage=data`, `session_id`,
`derived_from_session_id`, `actions`, `assumptions`, `decisions_required`, `artifacts`
(path + sha256), `validation.checks`, `validation.passed`, `recommended_next_stage`.

| Situation | Status |
|---|---|
| Any proposal present | `needs_approval`: one `decisions_required` entry per proposal; `recommended_next_stage: null` |
| Analysis only, verified | `completed` |
| Missing environment, unreachable source, missing input | `blocked` (with remediation) |
| Tamper-check or `verify` failure | `failed` |

After approval, the orchestrator records a `DECISIONS.md` entry tagged `data-derived`
with the session ID, proposal id and SHA256. How each layer consumes an approved proposal
is sub-project 2.

### 6.4 `report.md` sections

1. Question and scope
2. Sources (release, date, terms)
3. Methods (scripts, parameters, seeds, vendored guides used)
4. Results
5. Limitations, e.g. "co-essentiality is association, not mechanism"
6. Proposals and the decisions required from the researcher

## 7. Testing

Unittest suites go under `tests/data/` and run via `scripts/run_tests.py`.

- `data_guard.py`:
  - allowlist accept/reject cases, including injection attempts (`;`, `$( )`, pipes,
    symlinked scripts, `..`, other sessions' paths);
  - session binding from a fixture transcript;
  - write-path enforcement.
- `data_orchestrator_guard.py`: main-session deny; data-analyst allow; unrelated commands
  pass.
- `session.py`: ID format, layout, snapshot; tamper detection on a modified protected
  file.
- `fetch.py`: uses a local HTTP server fixture; covers cache addressing, ledger entries
  and HTML rejection.
- `manifest.py`: build/verify round trip; rejects missing units, changed hash, or a
  missing source hash.
- `validate_handoff.py`: accepts a valid `data_analyst` handoff; rejects a tampered one.
- `check_isolation.py`: new assertions.
- Vendored pydeseq2 fix: regression test (h5ad write with a Series in `uns`).
- Offline end-to-end smoke test (`tests/integration/data_smoke.py`, needs `.venv-data`):
  1. synthetic counts with planted signal;
  2. vendored DESeq2 and GSEA scripts, using a local GMT so the test runs offline;
  3. a seed-gene proposal;
  4. `manifest.py verify` passes;
  5. the handoff validates as `needs_approval`.
- Manual verification (documented, since inline subagent behavior needs an interactive
  session): `/agents` shows `data-analyst`; a read-only task works; the main session is
  denied when it tries to run a vendored script.

## 8. Out of scope

- Layer-specific proposal schemas and consumer handoffs; `gate.py` data checks;
  reviewer/auditor checklists (sub-project 2).
- Codex dispatcher support (sub-project 3).
- A data MCP server.
- Licensed or credentialed data sources.
- Running PhysiCell or calibration tools (`tellurium`, `pymoo`, `pymc` are not vendored).
- Upstream contribution of the pydeseq2 fix. An issue may be filed separately with the
  researcher's approval.

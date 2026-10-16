# Improvement plan: automated multiscale modelling workspace (NeKo → MaBoSS → PhysiBoSS)

**Status:** proposed · **Date:** 2026-10-05 · **Basis:** final end-to-end test, model `toy-cell-cycle`, 2026-10-02
(branch `model/toy-cell-cycle`)

This plan turns every problem met during the final test into an action. The actions fall into three groups, by where
the fix lives:

- **A. Agentic system:** agent definitions, skills, `CLAUDE.md`, settings, project scripts, and the orchestrator's
  procedures. Fixed in this repository.
- **B. MCP servers:** the tool layer in `mcp-biomodelling-servers` 2.4.0 (NeKo, MaBoSS, PhysiCell servers): tool
  schemas, tool documentation, artifact handling, provenance.
- **C. Modelling software:** the scientific libraries underneath (NeKo/nekomata, MaBoSS engine, PhysiBoSS add-on,
  PhysiCell core).

**Sources.** Benchmark log `docs/audits/2026-10-02-toy-cell-cycle-benchmark/README.md` (findings B-001…B-043, with
timeline and costs). Independent stage reviews and reproducibility audits (topology and Boolean-dynamics stages).
Specialist hand-back reports. A read-only Claude Code setup health check (2026-10-05). Every action cites the findings
it closes; the appendix maps each finding to its actions.

**Priority:**
- **P1:** breaks a guarantee or blocks automation. Fix before calling the system "fully automated".
- **P2:** forces manual work, risks wrong results, or loses provenance.
- **P3:** friction or cosmetic.

**Effort:** S < ½ day · M ½–2 days · L > 2 days.

---

## 1. Executive summary

The pipeline produced a validated multiscale model end to end: SIGNOR network → literature review → Boolean model
fitted to target dynamics → PhysiBoSS configuration. Its scientific safeguards worked. Specialists never changed a
model or exported anything without an explicit instruction. They stopped and asked when blocked. The two independent
reviewers caught real errors, including the orchestrator's own.

It is **not yet fully automated**. Four kinds of gaps forced manual intervention:

1. **Every artifact was copied and hashed by hand.** Each specialist output landed in `site-packages`, so the
   orchestrator copied and hashed it manually: about 20 % of orchestration effort.
2. **Three software bugs and limitations had to be worked around.**
   - The NeKo complex-label bug blocked the MaBoSS export.
   - The PhysiCell MCP silently ignored a parameter patch.
   - The PhysiBoSS link semantics are documented wrongly.
3. **Three capabilities are missing,** so the model had to be edited outside the tools, which broke typed lineage.
   - There is no NeKo tool to add or re-sign a single edge.
   - There is no MaBoSS tool to add readout nodes.
   - There are no PhysiCell tools for initial cells, cycle rates or link steepness.
4. **Isolation and approval are not enforced mechanically.**
   - The modelling servers are registered for the whole user account, so the orchestrator can reach them.
   - Stage gates depend on the orchestrator's discipline, and the gate slipped once.

### Top 10 actions (cross-category, in order)

| # | Action | Closes | Pri | Effort |
|---|---|---|---|---|
| 1 | C-NK-1: fix the NeKo SIF-import complex label (`network.py:338`) and add a regression test | B-017 | P1 | S |
| 2 | A-ISO-1: remove the user-scope NeKo, MaBoSS, PhysiCell and BioMASS registrations; keep agent-inline servers only, plus a setup guard | B-001, B-002, B-030, B-035 | P1 | S |
| 3 | B-SH-1: configurable artifact root, set per agent to `runs/<specialist>/` | B-005, B-043 | P1 | M |
| 4 | B-PC-1: fix the PhysiCell MCP multi-field patch bug; read values back after each patch | B-041 | P1 | S |
| 5 | A-GATE-1: stage-gate helper that blocks downstream dispatch unless an approval row names the exact upstream session | B-024, B-028 | P1 | M |
| 6 | B-NK-1 + B-MB-1: tools to add or re-sign a single edge (NeKo) and to add readout nodes (MaBoSS), each with lineage | B-010, B-016, B-039 | P1 | L |
| 7 | B-PC-2/3/4: PhysiCell tools for initial cells, user parameters, cycle rates and output-link steepness; correct the `base_value` docs | B-038, B-040 | P1 | M |
| 8 | A-CAP-1: one Claude-side capture-and-verify command for every handoff type (NeKo→MaBoSS, MaBoSS→PhysiCell, PhysiCell package) | B-005, B-020, B-025 | P2 | M |
| 9 | A-VAL-1: executable validation criteria (promote the analysis scripts to a supported validator) | B-032, B-036, B-034 | P2 | M |
| 10 | A-EVD-1: structured evidence footer plus write-once edge reports | B-011, B-013, B-015 | P2 | S |

---

## 2. Release blockers: definition of done for "fully automated"

The system can be called fully automated when a re-run of the `toy-cell-cycle` benchmark (§7) meets all of the
following:

- [ ] No orchestrator `cp`/`sha256sum` of server artifacts. Artifacts land in `runs/` and are indexed automatically.
- [ ] No hand-edited SIF, BNET or XML. Every model change goes through a tool and is recorded in typed lineage.
- [ ] The typed lineage chain NeKo → MaBoSS → PhysiCell is intact. No `lineage: []` and no `parent_manifest: null`
      unless the model is truly standalone.
- [ ] The orchestrator cannot see or call modelling tools.
- [ ] No downstream session can be created without a recorded approval of the exact upstream session.
- [ ] Validation criteria are executed by a script, not judged from prose.
- [ ] The PhysiBoSS export runs unmodified in a stock `template_BM` project.

---

## A. Agentic system (this repository)

### A1. Isolation and permissions

| ID | Pri | Problem (evidence) | Action | Where | Acceptance test |
|---|---|---|---|---|---|
| A-ISO-1 | P1 | NeKo, MaBoSS, PhysiCell and BioMASS are registered at **user scope**, so the orchestrator could load and call their tools. MaBoSS "Connection closed" / "failed to connect" events suggest the user-scope and agent-inline servers with the same names collide (B-001, B-030, B-035) | Remove the user-scope entries (`claude mcp remove -s user neko`, etc., after recording their config in `setup/`). Rely only on the agent-inline `mcpServers`. Rename the inline servers (e.g. `neko-agent`) so no name can collide | `~/.claude.json` (user); `.claude/agents/*.md`; `scripts/setup.py` | Orchestrator `ToolSearch("neko")` returns nothing; each specialist still lists its own tools; no "failed to connect" notice in specialists |
| A-ISO-2 | P1 | `.claude/settings.json` pre-allows ~50 `mcp__neko__*` and `mcp__maboss__*` tools project-wide, including for the orchestrator (B-002) | Remove the MCP allow rules from project settings; specialists already run with `permissionMode: acceptEdits` and their own `tools:` list. If prompts appear, scope approvals per agent instead | `.claude/settings.json` | Orchestrator has no allow rule for modelling tools; specialist runs complete without prompts |
| A-ISO-3 | P2 | Nothing detects isolation regressions | Add a setup and CI guard: fail if any modelling server is registered at user or project scope, or if a project allow rule names `mcp__neko__`, `mcp__maboss__`, `mcp__physicell__` or `mcp__biomass__` | `scripts/codex/check_environment.py` (or a new `scripts/check_isolation.py`); `tests/` | Guard fails on the current machine before A-ISO-1 and passes after |

### A2. Artifact capture, persistence and records

| ID | Pri | Problem (evidence) | Action | Where | Acceptance test |
|---|---|---|---|---|---|
| A-CAP-1 | P2 | The Claude path has no documented capture step. `record_neko_boolean_handoff.py` lives under `scripts/codex/` and there is no MaBoSS→PhysiCell or PhysiCell-package equivalent. The orchestrator copied and hashed 6 sessions by hand (B-005, B-020) | Move the capture scripts into `scripts/capture/` and make them provider-neutral. Add `record_maboss_physicell_handoff.py` and `record_physicell_config.py`. Each one validates, relocates, hashes, and appends to `runs/index.json`. Document them in each workflow skill and in `CLAUDE.md` stage 7 | `scripts/`; skills; `CLAUDE.md` | Every handoff in the benchmark is captured with one command; `runs/index.json` is written by script, not by hand |
| A-CAP-2 | P2 | Specialists cannot write, so their full reports (not just orchestrator summaries) are not persisted. Run directories end up mixing specialist and orchestrator authorship (audit N1, N4, N5) | Give each specialist a guarded `Write`, limited to `runs/<specialist>/<session_id>/report.md` by a PreToolUse hook modelled on `literature_file_guard.py`. Keep orchestrator-derived files under `runs/orchestrator/` only | `.claude/agents/*.md`; `.claude/scripts/` | Each session directory contains `report.md` written by the specialist; orchestrator files never land in specialist directories |
| A-CAP-3 | P2 | Tool-call records (arguments, history states, verification outputs) are not persisted, so lineage depends on chat summaries (audit N1, N2) | Persist the subagent invocation record (prompt, tool-call list, final report) per session; on the Claude side, a SubagentStop hook can copy the transcript excerpt into `runs/<specialist>/<id>/invocation/` | `.claude/settings.json` hooks; `scripts/` | Auditor can verify NeKo history states and call arguments from files alone |
| A-CAP-4 | P3 | `pypath_log/` is untracked in the repo root. The `.capture.lock` files are designed never to be deleted, yet show up as untracked noise (B-004) | Add `pypath_log/` and `**/.*.capture.lock` to `.gitignore`, or point pypath's log directory into `.setup/cache` | `.gitignore` | `git status` is clean after a full run |
| A-CAP-5 | P3 | Per-invocation cost and time are measured only by hand in the benchmark log | Add a usage summary per subagent (tokens, tool calls, wall time) to `runs/index.json`, taken from the task-notification metadata | orchestrator procedure / hook | Benchmark table generated automatically |

### A3. Stage gates and approvals

| ID | Pri | Problem (evidence) | Action | Where | Acceptance test |
|---|---|---|---|---|---|
| A-GATE-1 | P1 | The orchestrator started MaBoSS before the user had ratified the relabel, the export and the output nodes. The auditor caught it afterwards (B-024) | Script `scripts/gate.py check <downstream-stage> <upstream-session>`. It passes only if the registry row is `exported` **and** `DECISIONS.md` has a user-approved row naming that session ID and its declared outputs. The orchestrator must run it (and quote its output) before every downstream dispatch | `scripts/`; `CLAUDE.md` § Session registry | Gate refuses the benchmark's premature MaBoSS dispatch; passes after ratification |
| A-GATE-2 | P2 | `validate-stage` ran in parallel with the downstream stage, so blocking findings arrived late (B-028). The multicellular stage was delivered **without** an independent review | Make `validate-stage` a precondition of A-GATE-1: an `approved*` review outcome must be recorded first. Add a PhysiCell checklist to the reviewer and auditor definitions | `.claude/skills/validate-stage/SKILL.md`; reviewer/auditor agents | Gate fails without a recorded review; the multicellular stage gets reviewed before closure |
| A-GATE-3 | P3 | "Conditional approval" rows (e.g. "add only if evidence supports") are resolved by orchestrator judgment | Record conditional approvals with machine-checkable conditions (e.g. `verdict ∈ {supported}`) and resolve them by script against the evidence footer (A-EVD-1) | `DECISIONS.md` convention; `scripts/` | Benchmark's conditional rows resolve automatically |

### A4. Evidence and literature workflow

| ID | Pri | Problem (evidence) | Action | Where | Acceptance test |
|---|---|---|---|---|---|
| A-EVD-1 | P2 | Reports are free-form Markdown. The orchestrator took PMIDs from the *Excluded* section by mistake (B-015) | Require a fenced YAML footer in each report: `verdict`, `interaction_type`, `confidence`, `supporting_pmids`, `excluded_pmids`, `edge`, `neko_session_id`. Validate it in the guard on Write | `.claude/agents/literature-reviewer.md`; `.claude/scripts/literature_file_guard.py`; `scripts/codex/write_literature_report.py` | Guard rejects a report without a valid footer; orchestrator reads PMIDs from the footer only |
| A-EVD-2 | P2 | Edge reports are not write-once; a reviewer rewrote its own report (B-011, B-013) | Apply the ODE no-overwrite check to edge reports. Allow explicit revision only as `{A}__{B}.r2.md` | `literature_file_guard.py` | Second Write to the same path is denied |
| A-EVD-3 | P2 | Batched `get_article_metadata` and full-text calls exceed the tool-result cap and spill to files. Grep on spilled files can hide long lines (B-012) | Change the reviewer rule from "as few calls as possible" to batches of ≤ 8 PMIDs, abstracts first, full text only on demand | `literature-reviewer.md`; `review-literature-evidence` skill | No spill files in a benchmark run |
| A-EVD-4 | P2 | Candidate (not-yet-existing) edges have no defined report location, and a manual edge (CDK2⊣E2F1) rested on another edge's report (B-014; audit N4) | Define `evidence/reports/{neko_session_id}/candidates/{A}__{B}.md`. Require a dedicated report for every manual edge before it can enter a SIF/BNET | `CLAUDE.md` § Literature review; guard | Every `manual-literature` edge has its own report |
| A-EVD-5 | P3 | One-search-per-edge cap makes PMID-less candidate edges expensive (~28k tokens/edge) | Allow 2 searches for PMID-less candidate edges; encourage `find_related_articles` seeded from sibling-edge PMIDs | reviewer agent | Cost per candidate edge drops below ~15k tokens |

### A5. Provenance scheme and state files

| ID | Pri | Problem (evidence) | Action | Where | Acceptance test |
|---|---|---|---|---|---|
| A-PRV-1 | P2 | `CLAUDE.md` allows only `literature-derived` / `fitted-for-dynamics` rule tags. The run needed three more: `database-default`, `manual-literature`, `readout` (B-033) | Extend the tag scheme in `CLAUDE.md` § Model refinement discipline with definitions for all five tags (rules and edges); require every final rule **and** every manual edge to carry one | `CLAUDE.md` | Auditor checklist passes with no "untagged" finding |
| A-PRV-2 | P2 | Orchestrator-authored inputs (`runs/orchestrator/…`) are not a defined location. Lineage of SIF/BNET edits is held only in hand-written CHANGES.md (B-016) | Define `runs/orchestrator/<purpose>/` in `CLAUDE.md` § Sources of truth with a required `CHANGES.md` schema (base artifact + sha256, edits, evidence, output + sha256). Becomes rare once B-NK-1/B-MB-1 land | `CLAUDE.md` | Auditor can rebuild every orchestrator input from base + CHANGES |
| A-PRV-3 | P2 | State edits by shell heredoc dropped text silently (unquoted heredoc with backticks; string replacements that matched nothing) (B-031) | Provide `scripts/state.py` (append decision row, add or supersede registry row, update validation row, add checkpoint) with schema checks; forbid ad-hoc shell edits of state files in `CLAUDE.md` | `scripts/`; `CLAUDE.md` § Context rules | All state updates in the benchmark go through the helper; a bad replacement raises instead of passing silently |
| A-PRV-4 | P3 | Server timestamps are UTC while records use local +09:00, so dates mismatch across midnight (B-019) | Record timezone-aware ISO times everywhere; state the convention in `CLAUDE.md` | `CLAUDE.md`; helpers | No date mismatches in the audit |
| A-PRV-5 | P3 | The SIGNOR/OmniPath resource version and download date are not recorded (audit N7) | Capture the resource version or cache timestamp in the NeKo capture record (needs B-NK-6) | capture script | Index shows the resource version per NeKo session |

### A6. Validation tooling

| ID | Pri | Problem (evidence) | Action | Where | Acceptance test |
|---|---|---|---|---|---|
| A-VAL-1 | P2 | Criteria such as "first peak" and "canonical cycle" were prose. Reviewer and orchestrator classified the same trajectories differently (6/3 vs 3/1 canonical) (B-032, B-036) | Turn `runs/orchestrator/analysis/validate_cycles.py` into a supported tool `scripts/validate/` with criteria declared in YAML next to `VALIDATION_PLAN.md`. Each `VALIDATION_PLAN` row references a criterion ID that the script evaluates | `scripts/validate/`; `VALIDATION_PLAN.md` template | `VALIDATION_PLAN` status updated by script output only |
| A-VAL-2 | P2 | Exact analyses (fixed points, reachable attractors, readout exclusivity) were ad-hoc orchestrator scripts, outside the delegation rules | Move them into a supported tool, preferably a MaBoSS MCP tool (B-MB-6) or a reviewer-usable script. Decide in `CLAUDE.md` whether the orchestrator may run structural analyses on artifacts | `scripts/` or MCP; `CLAUDE.md` | Attractor/exclusivity results produced by the specialist or a sanctioned script |
| A-VAL-3 | P2 | Seed replicates were not independent: seed 0 vs seed 1 shared 1,999 of 2,000 trajectories (B-034) | State the seed semantics in `maboss-workflow`; the validator chooses replicate seeds ≥ sample_count apart | skill; validator | Replicate ensembles differ at the level of Monte-Carlo error |
| A-VAL-4 | P3 | Time-scale calibration for PhysiBoSS was an ad-hoc script | Ship `calibrate_cycle.py` as a supported step of the MaBoSS→PhysiCell handoff (emulates the phase mapping) | `scripts/validate/`; `physicell-workflow` | Scaling derived and recorded automatically in the handoff |

### A7. Skills, `CLAUDE.md` and agent definitions

| ID | Pri | Problem (evidence) | Action | Where | Acceptance test |
|---|---|---|---|---|---|
| A-SKL-1 | P2 | The `/model-*` lifecycle skills pre-approve only `PowerShell(python …)`, which doesn't exist on Linux/WSL (B-003) | Add `Bash(python .claude/scripts/model_lifecycle.py *)` to `allowed-tools` alongside PowerShell | `.claude/skills/model-{archive,list,restart,restore}/SKILL.md` | `/model-archive toy-cell-cycle` runs without a permission prompt on Linux |
| A-SKL-2 | P2 | `physicell-workflow` doesn't document the PhysiBoSS link semantics (inhibition uses `base_value` when the node is ON; Hill steepness 10 ⇒ ~0.1 % leakage) or the behaviour names ("cycle entry" = phase-0 exit) (B-038) | Add a "Boolean → phenotype mapping" section with the exact formulas (`addons/PhysiBoSS/src/utils.h:110-128`), the scaling definition (MaBoSS time = Δt/scaling) and a worked cell-cycle mapping | skill | A specialist configures the benchmark's four links correctly with no orchestrator explanation |
| A-SKL-3 | P2 | `maboss-workflow` is silent on mutant persistence, plot overwrite and seed semantics (B-025, B-034) | Document them and the workarounds (persisted perturbation runs, per-run PNG copies) until B-MB-3/4 land | skill | — |
| A-SKL-4 | P2 | `neko-workflow` doesn't explain `max_len` × `reuse_policy` growth, `consensus` with SIGNOR, SIF re-import behaviour, or the complex-node caveat (B-007, B-008, B-018, B-017) | Add these as "Semantics and caveats"; keep the version snapshot current | skill | Curator no longer has to guess these |
| A-SKL-5 | P3 | Skills say "snapshot for 2.3.0"; the installed server is 2.4.0 (B-023) | Add a version check to setup that fails when a skill snapshot ≠ installed server version; refresh the skills | `scripts/setup.py`; skills | Setup warns on drift |
| A-SKL-6 | P3 | Agent definitions tell specialists to read whole state files, while `CLAUDE.md` says to inline only the relevant subset (B-006) | Pick one convention. Recommended: the orchestrator inlines, and specialists read only files named in the prompt | `.claude/agents/*.md`; `CLAUDE.md` | Consistent guidance |
| A-SKL-7 | P3 | Always-loaded `CLAUDE.md` is 16.5k chars (≈ 4.1k tokens est.) and `AGENTS.md` 20k. The ODE-branch section (≈ 2.3k chars) and long procedural sections load every session | Move task-specific procedures (ODE branch, lifecycle details, checkpoint procedure) into their skills. Keep universal rules and prohibitions in `CLAUDE.md` | `CLAUDE.md` → skills | `CLAUDE.md` < 10k chars; no rule lost (diff reviewed) |
| A-SKL-8 | P3 | `CLAUDE.md` has no guidance for model *extension* across stages (readout nodes, PhysiBoSS phase mapping, time calibration) | Add a short "Multiscale mapping" section: readout layer pattern, exclusivity proof requirement, calibration step | `CLAUDE.md` or `physicell-workflow` | — |

### A8. Orchestrator procedure (lessons from the orchestrator's own errors)

| ID | Pri | Problem (evidence) | Action | Where |
|---|---|---|---|---|
| A-ORC-1 | P2 | PMIDs taken from the wrong section (B-015); heredoc substitution (B-031); missed replacement left a CDK2 tag empty (caught by audit) | Use A-EVD-1 / A-PRV-3 helpers exclusively; assert every replacement; diff state files before checkpoint | `CLAUDE.md` § Context rules |
| A-ORC-2 | P2 | Downstream work started before ratification (B-024) | Enforced by A-GATE-1 | — |
| A-ORC-3 | P3 | MaBoSS artifacts outside `runs/` were found only by reading package source | Covered by B-SH-1 / A-CAP-1 | — |

---

## B. MCP servers (`mcp-biomodelling-servers` 2.4.0)

### B-SH. Shared across servers

| ID | Pri | Problem (evidence) | Action | Acceptance test |
|---|---|---|---|---|
| B-SH-1 | P1 | Artifacts are written to `<env>/site-packages/mcp_biomodelling_servers/<Server>/artifacts/<id>/` (`artifact_manager.py:35-50`). Not portable; stale sessions pile up (22 NeKo / 9 MaBoSS / 13 BioMASS) (B-005) | Read an artifact root from an env var (`MCP_BIOMODELLING_ARTIFACT_ROOT`, per server) and default to the user cache dir, never site-packages. The workspace sets it per agent to `${CLAUDE_PROJECT_DIR}/runs/<specialist>/` | All benchmark artifacts appear under `runs/` with no copying |
| B-SH-2 | P2 | `lineage` stays empty when a session starts from an exported SIF or BNET (B-021, B-039) | Accept an optional `parent_manifest` / `derived_from` argument on SIF/BNET imports. Record the source file digest in history and in the exported manifest lineage | rev1b and R3 manifests list their parents |
| B-SH-3 | P3 | Timestamps are UTC without stating it consistently (B-019) | Emit timezone-aware ISO 8601 everywhere | — |
| B-SH-4 | P3 | Server/tool docstrings drift from behaviour (B-018, B-038) | Contract tests asserting docstring claims for key tools | — |

### B-NK. NeKo MCP server

| ID | Pri | Problem (evidence) | Action | Acceptance test |
|---|---|---|---|---|
| B-NK-1 | P1 | No tool to add a single interaction or change its sign. Closing known gaps needed hand-edited SIFs (B-010, B-016) | `add_interaction(source, target, effect, references, rationale, provenance_tag)` and `set_interaction_effect(source, target, effect, rationale)`, both recorded in history and in the BNET/handoff (per-edge provenance tag) | rev1's 5 manual edges and the re-sign done entirely through tools |
| B-NK-2 | P2 | `create_network` docstring says it always calls `complete_connection`; with `sif_file` it doesn't (B-018) | Fix the docstring; report "imported N nodes/M edges, no completion" in the result | — |
| B-NK-3 | P2 | `consensus=True` is accepted silently with `database='signor'`, where it is effectively a no-op (B-008) | Warn or reject; document the per-database meaning | Tool returns a warning |
| B-NK-4 | P2 | Network growth under `max_len` + `discovered_paths` is not explainable (16 added-to-added edges) (B-007) | Record, per edge, which seed–seed path introduced it (`inclusion_reason`), queryable through `list_genes_and_interactions` | Curator can justify every added node |
| B-NK-5 | P3 | `find_paths` "No paths found" prints UniProt IDs (B-009); `analyze_connectivity.total_node_count` counts by UniProt and misses label-only nodes (18 vs 19) (B-022) | Map IDs back to symbols; count by label | — |
| B-NK-6 | P3 | No resource version/date in the session or manifest (audit N7) | Add the resource name, version and cache date to `status()` and the handoff | — |
| B-NK-7 | P2 | `export_neko_handoff` fails with a generic error on null labels (B-017) | Until C-NK-1 ships, validate labels before export and name the offending nodes in the error | Error names `COMPLEX:CDC27_…` |

### B-MB. MaBoSS MCP server

| ID | Pri | Problem (evidence) | Action | Acceptance test |
|---|---|---|---|---|
| B-MB-1 | P1 | Nodes cannot be added; extending the model (readout layer) forced a standalone BNET, which broke lineage (B-039) | `add_readout_node(name, rule)` (no downstream targets allowed) or a general `add_node` gated by mode; keep the upstream manifest so the export carries lineage | R3 built in the NeKo-imported session; PhysiCell manifest lineage = [NeKo, MaBoSS] |
| B-MB-2 | P1 | First `import_neko_handoff` in one invocation returned "Connection closed" (server restart, orphan session). It may relate to the name collision in A-ISO-1 (B-030) | Reproduce after A-ISO-1. If it persists, add crash logging and make imports atomic, so a failure never leaves an orphan session | No orphan sessions in 3 benchmark re-runs |
| B-MB-3 | P2 | `simulate_mutation` persists nothing; mutant results exist only as a chat table (B-025; audit B1) | Persist mutant runs like `run_simulation` (run directory, input BND/CFG with the mutation, trajectories, fixed points), or add `mutations=` to `run_simulation`. Remove the need for the `rule = 0` perturbation hack | V4 runs reproducible from `runs/` |
| B-MB-4 | P2 | `visualize_network_trajectories` always overwrites `network_trajectory.png`; `result.csv` is overwritten each run (B-025; audit N4) | Name plots and results per run ID; return the path | — |
| B-MB-5 | P2 | No per-node rate control via tools; all rates fixed at 1 (readouts lag the core) | `set_node_rates(node, up, down)` recorded in the run manifest | — |
| B-MB-6 | P2 | No exact analysis tools; fixed points, attractors and exclusivity proofs were done outside the specialist | `find_fixed_points()`, `reachable_attractors(initial_state, max_states)`, `check_invariant(expr)` for small models (≤ ~25 nodes) | Specialist reproduces the orchestrator's exact results |
| B-MB-7 | P3 | `get_maboss_logical_rules` prints `(!X & f) \| (X & f)` (B-026) | Return the simplified BNET-style rule | — |
| B-MB-8 | P3 | Defaults `thread_count=1`, `sample_count=10000`, `max_time=1000`, `statdist_traj_count=0` (empty statdist) (B-027) | Document; consider statdist on for small models | — |
| B-MB-9 | P3 | Exported CFG marks core nodes `is_internal=True` silently | Report it in the export result | — |

### B-PC. PhysiCell MCP server

| ID | Pri | Problem (evidence) | Action | Acceptance test |
|---|---|---|---|---|
| B-PC-1 | P1 | `configure_cell_parameters(apoptosis_rate=0, necrosis_rate=0, motility_enabled=False)` reported success, but apoptosis stayed at the default in the XML (B-041) | Fix the multi-field patch. After every patch, read the stored values back from the config object and return them | Same call yields `death_rate 0` in the export |
| B-PC-2 | P1 | `add_physiboss_output_link` docs say `base_value` = "value when node inactive" for both actions; PhysiBoSS uses it when the node is **active** for `inhibition`. `steepness` cannot be set (default 10 ⇒ leakage) (B-038) | Correct the docs (quote the formula); add a `steepness` parameter (default 10, recommend ≥ 50 for switch-like links) | Link (d) in the benchmark configured without manual XML edits |
| B-PC-3 | P1 | No tools for initial cells or user parameters (`number_of_cells`, `random_seed`, cells.csv), although `physicell_config` supports them (B-040) | `set_initial_cells(cell_type, n \| positions_csv)` and `set_user_parameter(name, type, value)` | 50 cells + seed set through tools |
| B-PC-4 | P1 | No tool for cycle transition rates or `fixed_duration` flags; the orchestrator zeroed the built-in rates by XML edit | `set_cycle_transition_rate(cell_type, from, to, rate, fixed_duration)` (library method exists: `cell_types.set_cycle_transition_rate`) | Built-in rates set to 0 through the tool |
| B-PC-5 | P2 | Export references BND/CFG by absolute site-packages paths (B-043) | `export_project(folder)` producing a self-contained `config/` (XML + BND/CFG + cells.csv + rules) with relative paths and a manifest | Export runs unchanged in `template_BM` |
| B-PC-6 | P2 | `time_stochasticity` is typed `int`; PhysiBoSS reads a double (B-037) | Type as float ≥ 0 | 0.5 accepted |
| B-PC-7 | P2 | A default `substrate` is inserted silently, with inconsistent unit labels, and `ready_for_export` stays false without `add_single_substrate` (B-042) | Make the placeholder explicit (named `placeholder`, consistent units), report it, and fix the status logic | Status true for a substrate-free model |
| B-PC-8 | P2 | No validation that a "Boolean-only" cycle is consistent (every phase exit has a link, base rates overridden) | `validate_physiboss_mapping(cell_type)`: lists phases without links, links to unknown nodes or behaviours, non-zero base rates | Flags the raw v2 export, passes the package |
| B-PC-9 | P3 | `list_all_available_behaviors` omits the synonym "exit from cycle phase 0" | List synonyms | — |
| B-PC-10 | P3 | `import_maboss_handoff` doesn't carry upstream lineage when the MaBoSS manifest has a parent | Pass lineage through (after B-SH-2) | — |

---

## C. Modelling software (NeKo, MaBoSS, PhysiBoSS/PhysiCell)

| ID | Pri | Component | Problem (evidence) | Action | Acceptance test |
|---|---|---|---|---|---|
| C-NK-1 | **P1** | NeKo (`neko/core/network.py:338`) | In the SIF-import branch of `add_node`, `Genesymbol = genesymbol`, which is `None` for `COMPLEX:` IDs (`mapping_node_identifier` returns `[complex, None, complex]`). `export_bnet` then rejects the null label. **Every SIGNOR network with complexes that is revised via SIF re-import cannot be exported** (B-017) | One-line fix: `"Genesymbol": complex_string or genesymbol or node` (matching the database branch, ~l.365). Add a regression test: SIF with a `COMPLEX:` node → `export_bnet` succeeds and the label is sanitized | Test passes; benchmark rev1 exports without relabelling |
| C-NK-2 | P2 | NeKo | SIF import records no source digest or parent session (B-021) | Store the source path and sha256 in network history and expose them to the MCP manifest (supports B-SH-2) | — |
| C-NK-3 | P3 | NeKo | `consensus` semantics for single-resource databases undocumented (B-008); path-inclusion reasons not tracked (B-007) | Document; keep the path that introduced each edge (supports B-NK-4) | — |
| C-NK-4 | P3 | NeKo | Messages print UniProt IDs instead of symbols (B-009) | Translate in messages | — |
| C-MB-1 | P2 | MaBoSS / pyMaBoSS | Per-trajectory RNG streams appear to be seed + trajectory index, so seed k and k+1 share almost all trajectories (B-034) | Document. Optionally hash `(seed, index)` for independent streams, or add a `seed_stride` option | Seed 0 vs 1 differ at Monte-Carlo level |
| C-MB-2 | P2 | MaBoSS engine / server | "Connection closed" on import (B-030), cause unknown | Investigate with engine logs after A-ISO-1; file upstream if it is an engine crash | Root cause recorded |
| C-PB-1 | P2 | PhysiBoSS (`addons/PhysiBoSS/src/utils.h:110-128`) | Output Hill steepness default 10 gives ~0.1 % leakage of the active value; for "trigger when OFF" links this is a non-zero rate. Inhibition applies `base_value` when the node is ON, which is easy to misread (B-038) | Document the formulas in the PhysiBoSS docs. Consider an explicit `switch` mode (exact value/base) or a higher default steepness for Boolean links | Docs updated; option available |
| C-PB-2 | P3 | PhysiBoSS | An output mapping takes a single node, so logical combinations (A AND NOT B) need readout nodes in the network | Feature request: allow a Boolean expression in `intracellular_name` (or a derived-output section) | — |
| C-PB-3 | P3 | PhysiBoSS | `time_stochasticity` semantics (log-normal SD of the update interval, `maboss_network.h:52`) are undocumented | Document | — |
| C-PC-1 | P3 | PhysiCell | A fixed-duration link with rate 0 relies on 1/0 = inf (never exits) (`PhysiCell_phenotype.cpp:303-309`). It works, but implicitly | Document, or guard rate 0 explicitly | — |

---

## 5. Things to keep (they worked; protect them with tests)

- **Authority boundaries.** Specialists never mutated or exported without explicit instruction. They used
  `clarification_required` blocks when blocked: 3 NeKo, 4 MaBoSS and 1 PhysiCell invocation, zero violations.
- **Exact-match verification gates** before a conclusive export (expected topology JSON) caught nothing wrong and
  cost little. Keep them.
- **Ephemeral sessions with SIF re-import** worked as designed: 2–4 min per revision.
- **Independent scientific reviewer and reproducibility auditor:** highest-value quality lever, at 85–140k tokens
  each (B-029). Keep them mandatory; run them before the downstream stage (A-GATE-2).
- **Typed handoff verification** (`record_neko_boolean_handoff.py`, MaBoSS/PhysiCell manifest checks) worked on the
  first try.

## 6. Roadmap

| Phase | Goal | Actions | Est. effort |
|---|---|---|---|
| **0: Quick wins (1–2 days)** | Remove known breakages | C-NK-1, A-ISO-1, A-ISO-2, A-SKL-1, A-CAP-4, B-PC-1, B-NK-2, B-PC-6, A-EVD-2, A-EVD-3 | ~2 d |
| **1: Automation blockers (1–2 weeks)** | No manual capture, no hand edits | B-SH-1, A-CAP-1, B-NK-1, B-MB-1, B-PC-2/3/4/5, B-SH-2 (+ C-NK-2), A-GATE-1, A-GATE-2 | ~8–10 d |
| **2: Correctness and provenance (1 week)** | Durable, reproducible records | A-EVD-1, A-EVD-4, A-PRV-1/2/3, A-CAP-2/3, B-MB-3/4, A-VAL-1/3, B-PC-8, A-SKL-2/3/4 | ~5 d |
| **3: Enhancements** | Richer analysis and ergonomics | B-MB-5/6, A-VAL-2/4, B-NK-4/5/6, A-SKL-5/6/7/8, C-MB-1, C-PB-1/2/3, remaining P3 items | as capacity allows |

Dependencies:
- C-NK-1 before re-testing the NeKo exports.
- A-ISO-1 before B-MB-2 / C-MB-2.
- B-SH-1 simplifies A-CAP-1.
- B-SH-2 / C-NK-2 enable B-PC-10.
- A-EVD-1 enables A-GATE-3.

## 7. Regression test: re-run the `toy-cell-cycle` benchmark

After phases 0–1, re-run the same scenario in a fresh workspace: ER+ cell cycle, SIGNOR seeds, targeted review,
rev1 edits, refinement, R3 readouts, PhysiBoSS package. Measure against the 2026-10-02 baseline:

| Metric | Baseline 2026-10-02 | Target |
|---|---|---|
| Manual artifact copies/hashes by orchestrator | 8 sessions (3 NeKo, 4 MaBoSS, 1 PhysiCell) | 0 |
| Hand-edited model files (SIF/BNET/XML) | 4 (rev1 SIF, rev1b SIF, R3 BNET, PhysiCell XML) | 0 |
| Typed lineage breaks | 3 (rev1b, R3, PhysiCell) | 0 |
| Software workarounds | 3 (complex relabel, apoptosis re-patch, XML steepness/rates) | 0 |
| Gate violations caught post hoc | 1 | 0 (blocked a priori) |
| Orchestrator self-errors | 3 (PMIDs, heredoc, missed tag) | 0 |
| Wall clock to validated Boolean model | ~87 min | ≤ 60 min |
| Subagent tokens to validated Boolean model | ≈ 1.36 M | ≤ 1.0 M |

Add the scenario as `tests/benchmarks/toy_cell_cycle/` with its decisions scripted (answers to the 5 user-question
batches), so it can run as a nightly or manual end-to-end check.

## 8. Open items in the current model (not system fixes)

- The multicellular stage has no independent review yet: run `validate-stage` on PhysiCell session
  `9686a467-8de2-4d11-a1b1-f6ed90efc77c`.
- V7 (multicellular behaviour) awaits the user's PhysiBoSS run.
- `/model-archive toy-cell-cycle` has not been run yet. It is a user-only command, and A-SKL-1 affects it.

---

## Appendix: finding → action traceability

| Finding | Short description | Actions |
|---|---|---|
| B-001 | Modelling servers at user scope (isolation) | A-ISO-1, A-ISO-3 |
| B-002 | Project allow rules for modelling tools | A-ISO-2, A-ISO-3 |
| B-003 | Lifecycle skills PowerShell-only | A-SKL-1 |
| B-004 | `pypath_log/` untracked | A-CAP-4 |
| B-005 | Artifacts in site-packages; manual capture | B-SH-1, A-CAP-1 |
| B-006 | Conflicting context-reading guidance | A-SKL-6 |
| B-007 | `max_len` growth unexplained | B-NK-4, C-NK-3, A-SKL-4 |
| B-008 | `consensus` no-op with SIGNOR | B-NK-3, C-NK-3, A-SKL-4 |
| B-009 | UniProt IDs in messages | B-NK-5, C-NK-4 |
| B-010 | No add-interaction tool | B-NK-1 |
| B-011 | Edge reports not write-once | A-EVD-2 |
| B-012 | PubMed result overflow | A-EVD-3 |
| B-013 | Report rewrite / Grep read-back | A-EVD-2 |
| B-014 | No location for candidate-edge reviews | A-EVD-4 |
| B-015 | PMIDs from excluded section | A-EVD-1, A-ORC-1 |
| B-016 | Hand-edited SIF outside provenance | B-NK-1, A-PRV-2 |
| B-017 | NeKo null complex label blocks export | C-NK-1, B-NK-7, A-SKL-4 |
| B-018 | `create_network` docstring wrong | B-NK-2, B-SH-4 |
| B-019 | UTC vs local timestamps | A-PRV-4, B-SH-3 |
| B-020 | Envelope validator unusable on Claude path | A-CAP-1 |
| B-021 | Empty NeKo lineage on SIF import | B-SH-2, C-NK-2 |
| B-022 | Connectivity node count by UniProt | B-NK-5 |
| B-023 | Skill version drift | A-SKL-5 |
| B-024 | Downstream started before ratification | A-GATE-1, A-ORC-2 |
| B-025 | MaBoSS plots/mutants not persisted | B-MB-3, B-MB-4, A-SKL-3 |
| B-026 | Redundant rule printing | B-MB-7 |
| B-027 | MaBoSS defaults / empty statdist | B-MB-8 |
| B-028 | validate-stage ran in parallel | A-GATE-2 |
| B-029 | Reviewers high value (positive) | §5 |
| B-030 | MaBoSS "Connection closed" | A-ISO-1, B-MB-2, C-MB-2 |
| B-031 | Heredoc corrupted state edits | A-PRV-3, A-ORC-1 |
| B-032 | Prose V2 definition | A-VAL-1 |
| B-033 | Tag scheme too narrow | A-PRV-1 |
| B-034 | Seeds not independent | A-VAL-3, C-MB-1 |
| B-035 | maboss "failed to connect" notice | A-ISO-1 |
| B-036 | Canonical-cycle classifier disagreement | A-VAL-1 |
| B-037 | `time_stochasticity` int-typed | B-PC-6, C-PB-3 |
| B-038 | Output-link `base_value` docs wrong; no steepness | B-PC-2, A-SKL-2, C-PB-1 |
| B-039 | Readout nodes break lineage | B-MB-1, B-SH-2 |
| B-040 | No initial-cell/user-param tools | B-PC-3 |
| B-041 | Apoptosis patch silently ignored | B-PC-1 |
| B-042 | Default substrate / ready_for_export | B-PC-7 |
| B-043 | Absolute model paths in XML | B-PC-5, B-SH-1 |
| Audit N1/N2 | Invocation records and verification outputs not persisted | A-CAP-2, A-CAP-3 |
| Audit N4/N5 | Mixed authorship in run dirs; manual edge without own report | A-CAP-2, A-EVD-4 |
| Audit N7 | Resource version not recorded | A-PRV-5, B-NK-6 |
| Review L4 / sign constraint | Rule forms limited by database signs (CDC20) | B-NK-1 (re-sign with evidence), A-SKL-4 |
| Multicellular stage | Delivered without independent review | A-GATE-2, §8 |
| Setup health 2026-10-05 | Settings parse OK; agent and skill frontmatter valid; single native install; `CLAUDE.md` ≈ 4.1k tokens est. always loaded | A-SKL-7 (no other setup defects beyond B-001/B-002/B-003) |

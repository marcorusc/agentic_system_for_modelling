# Data-analyst fixes (post live test) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the data-analyst handoff mechanical and verifiable, have the recorder write `report.md` for every specialist, port the two test-copy fixes, close the remaining issues, and add plotting support.

**Architecture:**
- `handoff.py` generates `handoff.json` from the manifest and an agent notes file.
- `receive.py` is the orchestrator's single entry point after a data run: it recovers a missing capture, verifies the manifest and validates the handoff.
- The SubagentStop recorder materialises `report.md` from the final message for all specialists.
- The validator enforces status rules and matches decisions to proposals by id.
- Two more vendored skills and a required-figures section cover plots.

**Tech Stack:** Python 3.11+ stdlib with `unittest` (framework); `.venv-data` (Python 3.12) for scientific code; Claude Code agents and hooks.

**Spec:** `docs/superpowers/specs/2026-11-12-data-analyst-fixes-design.md` (amends `docs/superpowers/specs/2026-11-12-data-analyst-agent-design.md`)

## Global Constraints

- All base-plan Global Constraints still hold:
  - names `data-analyst` / `data_analyst` / stage `data`;
  - session ID regex `^data-\d{8}T\d{6}Z-[0-9a-f]{8}$`;
  - UTC `+00:00` timestamps;
  - agent Python form `.venv-data/bin/python -E -s <script>`;
  - stdlib `unittest` tests run by `python3 scripts/run_tests.py`;
  - hooks deny with stderr + exit 2.
- `handoff.json` schema: `schema_version` is the integer `1`; artifact paths are repo-relative `runs/data-analyst/<id>/...`; `recommended_next_stage: null`.
- Status rules (spec §3.1):
  - proposals → `needs_approval`;
  - outputs only → `completed`;
  - nothing produced → `blocked`;
  - verification failure → `failed`.
- Agent's final-message last line: exactly `Handoff: runs/data-analyst/<id>/handoff.json sha256=<64hex>`.
- Recorder's final report source: the last `SubagentHandback` `input.message`, else the last assistant text.
- `report.md`: written by the recorder only. Rules: absent → write; identical → no-op; different → keep first and record `report_md: "kept-first"`.
- Data-guard Write-protected names: `identity.json`, `manifest.json`, `integrity.json`, `sources.jsonl`, `handoff.json`, `report.md`, plus the `invocation/` dir.
- Data-guard script allowlist (R12): `session.py`, `fetch.py`, `manifest.py`, `handoff.py`.
- Orchestrator guard: deny `handoff.py build` in the main session; allow `scripts/data/receive.py`.
- Ledger `terms`: `""`, `"unverified"`, or `"quoted: <verbatim source text>"`.
- New vendored skills: `scientific-visualization`, `seaborn` from upstream commit `2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5`; `VENDORED_SKILLS` grows to 12.
- Data env additions: `seaborn==0.13.2`; matplotlib pinned to `3.11.2` if it resolves, else the resolved version, recorded in the lock header comment.
- Figures: `outputs/figures/*.png` (300 dpi) plus `.svg`; index `units: "none"`; caption in `description`.
- Test-copy patches to port: `/home/marcorusc/tests/claude_test/skill-tests/issue1-guard-binding.patch` and `/home/marcorusc/tests/claude_test/skill-tests/issue2-recorder-handback.patch`.

## Review Focus

1. **Transcript discovery for worktrees and underscores.** Claude Code project directories are the repo path with non-alphanumerics replaced by `-` (e.g. `/home/u/agentic_system_data_test` → `-home-u-agentic-system-data-test`). `receive.py` must find the right project dir for paths containing `_` and `.`, and fail clearly on 0 or ≥2 matches. Pinned by Task 5 `test_project_slug_with_underscores`.
2. **Pre-existing `report.md` from older guarded writes or a prior invocation.** The recorder must never overwrite it. Pinned by Task 2 `test_existing_different_report_kept_first`.
3. **`handoff.py build` on a stale or unverified manifest.** It must run `manifest.verify` first and refuse any status except `failed` when verify reports errors. Pinned by Task 3 `test_stale_manifest_refused`.
4. **Notes `artifact` escaping the session** (`../`, absolute paths, symlinks). It must be rejected. Pinned by Task 3 `test_notes_artifact_escape_rejected`.
5. **Main-session tripwire regression.** `python3 scripts/data/receive.py ...` must be allowed; `python3 scripts/data/handoff.py build ...` must be denied; `manifest.py verify` must stay allowed. Pinned by Task 3 `test_orchestrator_handoff_build_denied` and Task 5 `test_orchestrator_receive_allowed`.

---

### Task 1: Port test-copy fixes #1 and #2

**Files:**
- Modify: `.claude/scripts/data_guard.py`, `.claude/scripts/test_data_guard.py`, `scripts/capture/record_invocation.py`, `tests/codex/test_provider_neutral_capture.py`, `docs/data-workflow.md` (R10 wording)

**Interfaces:**
- Produces: `data_guard._event_transcript(event: dict) -> str | None`; `AGENT_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")`. The recorder's final report prefers `SubagentHandback`.

- [ ] **Step 1:** Apply both patches with `git apply --3way`. If they don't apply cleanly, port by hand; the hunks are small. Confirm the two ported tests exist: `test_cli_binds_from_agent_id_subagent_transcript` and `test_invocation_capture_prefers_subagent_handback_report`.
- [ ] **Step 2: RED check.** Temporarily revert the code hunks only (keep the tests). Run `python3 -m unittest discover -s .claude/scripts -p "test_data_guard.py" -v` and `python3 -m unittest tests.codex.test_provider_neutral_capture -v`. Expected: both ported tests FAIL. Restore the code.
- [ ] **Step 3:** Run both commands again. Expected: PASS.
- [ ] **Step 4:** In `docs/data-workflow.md`, fix the binding description: subagent PreToolUse events carry the main `transcript_path` plus `agent_id`, and the guard derives `<transcript without .jsonl>/subagents/agent-<agent_id>.jsonl`. Mark checklist item (b) as "fixed in code; re-verify".
- [ ] **Step 5:** Run `python3 scripts/run_tests.py`. Expected: all OK. Commit `fix(data): bind subagent transcript via agent_id; capture SubagentHandback report`.

### Task 2: Recorder writes report.md for all specialists

**Files:**
- Modify: `scripts/capture/record_invocation.py`, `.claude/scripts/data_guard.py` (add `report.md` to `PROTECTED_NAMES`), `.claude/agents/{network-curator,boolean-dynamics-modeler,multicellular-configurator,ode-modeler,data-analyst}.md`, `CLAUDE.md`
- Test: `tests/codex/test_recorder_report_md.py`, `.claude/scripts/test_data_guard.py`

**Interfaces:**
- Produces: `record_invocation.materialize_report(project: Path, specialist: str, session: str, final_report: bytes) -> str`, returning `"written" | "identical" | "kept-first"`. `record()` includes `"report_md": <that value>` in its returned dict and the invocation metadata, for bound sessions only.
- For data-analyst, `materialize_report` is called after `data_integrity` and after `publish_invocation`.

- [ ] **Step 1: Write failing tests:**
  - `test_report_written_for_bound_session` (network-curator fixture, mirroring the existing capture tests);
  - `test_identical_report_noop`;
  - `test_existing_different_report_kept_first` (`report.md` bytes unchanged; result `"kept-first"`);
  - `test_unbound_invocation_writes_no_report`;
  - `test_data_analyst_report_after_integrity` (integrity `passed: true` and `report.md` equals `invocation/<id>/final_report.md`);
  - `test_write_report_md_denied` in `test_data_guard.py`.
- [ ] **Step 2:** Run `python3 -m unittest tests.codex.test_recorder_report_md -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Write atomically (temp file plus `os.replace`), and refuse if the session dir or the target is a symlink. Update the five agent definitions: replace the "write report.md through guarded Write" instruction with "Return the full report as your final message; the recorder saves it as `runs/<specialist>/<session>/report.md`. Do not Write report files (Claude Code blocks subagent Writes to report-style .md names)." Keep each file's other content unchanged. In `CLAUDE.md`, rewrite the "Guarded report Write is their only local authoring exception" sentence and "Specialists write guarded immutable report.md" to say that specialists return the report as their final message and the SubagentStop recorder writes the immutable `report.md`.
- [ ] **Step 4:** Run the new tests, then `python3 scripts/run_tests.py` (existing agent/CLAUDE.md governance tests must still pass; adjust only assertions that quote the replaced sentences, and say which in the report). Expected: all PASS.
- [ ] **Step 5:** Commit `feat(capture): recorder writes report.md from the final message for all specialists`.

### Task 3: handoff.py and guard updates

**Files:**
- Create: `scripts/data/handoff.py`
- Modify: `.claude/scripts/data_guard.py` (`DATA_SCRIPTS` += `handoff.py`; `PROTECTED_NAMES` += `handoff.json`), `.claude/scripts/data_orchestrator_guard.py` (deny `handoff.py`, as with `manifest.py build`; `DATA_TOOLS`, `DATA_MODULE_RE` and `DATA_TEXT_RE` gain `handoff`)
- Test: `tests/data/test_handoff.py`, `.claude/scripts/test_data_guard.py`, `.claude/scripts/test_data_orchestrator_guard.py`

**Interfaces:**
- Consumes: `manifest.verify(root, session_id) -> list[str]`, `common.session_dir`, `common.sha256_file`.
- Produces: `handoff.build(root: Path, session_id: str, status: str, notes_rel: str) -> tuple[Path, str]`, returning (path, sha256). CLI: `handoff.py build --session ID --status S --notes REL`. Its last stdout line is `Handoff written: runs/data-analyst/<id>/handoff.json sha256=<hex>`; exit 1 with the reason on refusal.
- Notes schema: keys ⊆ `{actions, assumptions, validation_checks, decisions, blocked}`. Lists of strings, except `decisions` = `[{id, question, artifact?}]` and `blocked` = `[{what, why, remediation}]`. Decision ids must match `^D\d+$`.
- Generated fields: as spec §3.1.

- [ ] **Step 1: Write failing tests:**
  - `test_needs_approval_with_proposals` (asserts `schema_version == 1`, repo-relative paths, hashes equal file bytes, one decision per proposal carrying `path`/`sha256`, and that validation checks start with "manifest.py verify: passed");
  - `test_completed_without_proposals`;
  - `test_completed_with_proposals_refused`;
  - `test_blocked_with_outputs_refused`;
  - `test_blocked_items_become_decisions`;
  - `test_stale_manifest_refused` (change an output after `manifest.py build`);
  - `test_failed_status_allows_verify_errors`;
  - `test_notes_unknown_key_rejected`;
  - `test_notes_artifact_escape_rejected` (`../x`, absolute path, symlink);
  - `test_last_line_format`;
  - guard tests `test_handoff_script_allowed`, `test_write_handoff_json_denied`, `test_orchestrator_handoff_build_denied`.
- [ ] **Step 2:** Run the focused tests. Expected: FAIL.
- [ ] **Step 3:** Implement the code and the guard changes.
- [ ] **Step 4:** Run the focused tests, then `python3 scripts/run_tests.py`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(data): mechanical handoff.json builder`.

### Task 4: Validator rules

**Files:**
- Modify: `scripts/codex/validate_handoff.py` (`_data_session_checks` and its dispatch)
- Test: `tests/codex/test_validate_handoff_data.py`

**Interfaces:**
- Consumes: the recorder-written `report.md` (Task 2) and `handoff.json` (Task 3).
- Rules (spec §3.3):
  - data checks run for any status when `artifacts` is non-empty;
  - `blocked` or `completed` with manifest proposals → error;
  - every decision is an object with non-empty `id` and `question`;
  - proposal decisions are matched by `id` and must carry the manifest `path` and `sha256`;
  - each proposal must have a decision;
  - `report.md` must equal `invocation/<integrity.invocation_id>/final_report.md` for `completed`/`needs_approval`.

- [ ] **Step 1: Write failing tests:**
  - `test_blocked_with_proposals_rejected`;
  - `test_decision_missing_question_rejected`;
  - `test_proposal_decision_matched_by_id` (right count, wrong ids → rejected);
  - `test_proposal_decision_sha_mismatch_rejected`;
  - `test_missing_report_md_rejected`;
  - `test_report_md_mismatch_rejected`;
  - `test_handoff_py_output_validates` (end to end: fixture session, `manifest.py build`, recorder `record()`, `handoff.py build` → `validate_handoff` accepts).
- [ ] **Step 2:** Run `python3 -m unittest tests.codex.test_validate_handoff_data -v`. Expected: new tests FAIL.
- [ ] **Step 3:** Implement. Existing fixtures that hand-build envelopes may need a `report.md` and decision ids; update the fixtures, not the rules.
- [ ] **Step 4:** Run the focused tests, then `python3 scripts/run_tests.py`. Expected: PASS.
- [ ] **Step 5:** Commit `fix(handoff): data status rules, id-matched decisions, recorder report check`.

### Task 5: receive.py and orchestrator procedure

**Files:**
- Create: `scripts/data/receive.py`
- Modify: `.claude/scripts/data_orchestrator_guard.py` (explicitly allow `scripts/data/receive.py`), `CLAUDE.md` (receive procedure and the #11 brief rule)
- Test: `tests/data/test_receive.py`, `.claude/scripts/test_data_orchestrator_guard.py`

**Interfaces:**
- Consumes: `record_invocation.record(project, payload)`, `manifest.verify`, `validate_handoff.validate_handoff(handoff_dict, project=...)` (use the module's existing entry signature).
- Produces:
  - `receive.project_slug(root: Path) -> str`: `re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))`;
  - `receive.find_transcript(root: Path, agent_id: str, transcript_root: Path) -> Path`;
  - `receive.receive(root: Path, session_id: str, agent_id: str, transcript_root: Path | None) -> dict`;
  - CLI `receive.py --session ID --agent-id AID [--transcript-root DIR]`: on success, prints a table `id | kind | layer | path | sha256[:12]` then `RECEIVED <session> OK`; exit 1 with the reason otherwise.
- The default transcript root is `$CLAUDE_CONFIG_DIR/projects` if set, else `~/.claude/projects`. Search `<root>/<slug>/*/subagents/agent-<AID>.jsonl`; exactly one match is required.
- Recovery runs only when `integrity.json` is missing or the invocation is not registered in `runs/index.json`. It uses the synthetic payload `{"agent_type": "data-analyst", "agent_id": AID, "agent_transcript_path": <found>, "stop_hook_active": false, "hook_event_name": "SubagentStop"}`.

- [ ] **Step 1: Write failing tests:**
  - `test_receive_happy_path`;
  - `test_recovers_missing_capture` (delete `integrity.json` and the index entry first; a transcript fixture sits under a temp transcript root);
  - `test_no_transcript_match_fails`;
  - `test_two_transcript_matches_fail`;
  - `test_project_slug_with_underscores`;
  - `test_invalid_handoff_fails` (e.g. tampered output);
  - `test_orchestrator_receive_allowed` (guard: main session `python3 scripts/data/receive.py --session X --agent-id Y` → exit 0).
- [ ] **Step 2:** Run the focused tests. Expected: FAIL.
- [ ] **Step 3: Implement.** Add to `CLAUDE.md`, in the data paragraph:
  - after each data-analyst completion notification, run `python3 scripts/data/receive.py --session <id> --agent-id <agentId>`;
  - never present or act on proposals before it prints `RECEIVED … OK`;
  - data briefs list every upstream artifact the analyst may read, with path and sha256.
- [ ] **Step 4:** Run the focused tests, then `python3 scripts/run_tests.py`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(data): orchestrator receive step with capture recovery`.

### Task 6: state.py data-product and ledger terms

**Files:**
- Modify: `scripts/state.py` (new operation `data-product`, target `DATA_DICTIONARY.md`), `scripts/data/ledger.py` (`validate_entry` terms rule)
- Test: `tests/codex/test_state_data_product.py` (or the existing state test module, if one exists), `tests/data/test_fetch.py`

**Interfaces:**
- `data-product` input keys (exact): `name, type, meaning, unit, identifiers, source_session, path, sha256, release, decision_id, notes`.
- Row mapping onto the existing table header `| Name | Type | Biological meaning | Unit | Source | Version | Notes |`:
  - Source = `` `<source_session>` `<path>` sha256 `<sha256[:12]>` ``;
  - Version = `release`;
  - Notes = `identifiers: <identifiers>; decision <decision_id>; <notes>`.
- Errors: path missing or sha mismatch; `source_session` not matching `SESSION_RE`; `decision_id` not found in `DECISIONS.md`; duplicate `name`.
- Ledger: `terms` must be `""`, `"unverified"`, or start with `"quoted: "` followed by non-empty text.

- [ ] **Step 1: Write failing tests:**
  - `test_data_product_row_added`;
  - `test_data_product_duplicate_rejected`;
  - `test_data_product_hash_mismatch_rejected`;
  - `test_data_product_unknown_decision_rejected`;
  - `test_terms_free_text_rejected`;
  - `test_terms_quoted_accepted`.

  Update existing fixtures that pass free-text `terms`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement, following `state.py`'s existing locked/atomic update pattern.
- [ ] **Step 4:** Run `python3 scripts/run_tests.py`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(state): data-product registration; constrain ledger terms`.

### Task 7: Plotting skills, environment and workflow documentation

**Files:**
- Create: `vendor/scientific-agent-skills/{scientific-visualization,seaborn}/` (verbatim from the pinned commit; the clean checkout is at `/home/marcorusc/tests/claude_test/downloads/scientific-agent-skills`)
- Modify: `scripts/data/vendor_lock.py` (`VENDORED_SKILLS` += the 2 names), `vendor/scientific-agent-skills/{VENDOR.lock.json,VENDOR.md}`, `THIRD_PARTY_NOTICES.md` (both skills; BSD-3 text for seaborn), `setup/data-requirements.txt` and `.lock`, `scripts/data/environment.py` (`IMPORT_PROBE` adds `seaborn, matplotlib`), `.claude/skills/data-workflow/SKILL.md`, `.claude/agents/data-analyst.md`, `docs/data-workflow.md`, `README.md` (citation section lists 12 skills)
- Test: `tests/data/test_vendor.py` (counts and notices), `tests/setup/test_data_setup.py` (probe string)

**Interfaces:**
- `data-workflow` SKILL.md changes:
  1. **Lifecycle** ends: `manifest.py build` → `manifest.py verify` → write `handoff_notes.json` → `handoff.py build` → final message with the report and the exact `Handoff:` line. Drop "Write report.md".
  2. **New "Figures" section:** spec §6 table and rules verbatim, with the style path `vendor/scientific-agent-skills/scientific-visualization/assets/publication.mplstyle`.
  3. **Index** rows for `scientific-visualization` and `seaborn`.
  4. **Data-source notes:**
     - cBioPortal datahub LFS/S3 failure → API fallback with count reconciliation (#7);
     - DepMap: human verification → files in `inputs/` + `fetch.py --input`; Open Targets for single genes (#10);
     - `terms` rule (#6).
- `data-analyst.md`: handoff section replaced. Summarize the status rules and require the `handoff.py build` route; hand-written JSON envelopes are forbidden.
- `docs/data-workflow.md`:
  - receive procedure;
  - recorder-written reports;
  - #5 note (setup re-renders `ode-modeler` only with `--with-biomass`);
  - the checklist adds (h): "a data run ends with `receive.py` → `RECEIVED … OK` and `report.md` written by the recorder".

- [ ] **Step 1: Write failing tests:** `VENDORED_SKILLS` has 12 entries including both new names; the lock verifies; notices contain "seaborn" and "scientific-visualization" plus the BSD-3 marker sentence; the setup probe includes seaborn.
- [ ] **Step 2:** Run `python3 -m unittest discover -s tests/data -v`. Expected: FAIL.
- [ ] **Step 3:** Vendor (copy only; never execute upstream code from the checkout), rebuild the lock, update the documents, add the pins and regenerate the lock with `uv pip compile --python-version 3.12`, then install into `.venv-data` with `python3 scripts/setup.py --client claude --environment-mode plugin --with-data --non-interactive`. Revert any regenerated `.claude/agents/*` transport changes, which setup makes on this machine.
- [ ] **Step 4:** Run `.venv-data/bin/python -E -s -c "import seaborn, matplotlib; print(seaborn.__version__, matplotlib.__version__)"`, then `python3 scripts/run_tests.py` and `python3 scripts/check_isolation.py --repository-only`. Expected: versions printed; all PASS.
- [ ] **Step 5:** Commit `feat(data): vendor plotting skills; figures, handoff and source guidance`.

### Task 8: Smoke test update

**Files:**
- Modify: `tests/integration/data_smoke.py`, `docs/data-workflow.md` (Smoke test section)

**Interfaces:**
- Consumes everything above.

- [ ] **Step 1: Update the smoke script.**
  - After GSEA, a session script renders `outputs/figures/volcano.{png,svg}` and `outputs/figures/gsea_dotplot.{png,svg}` with `publication.mplstyle` (via `.venv-data/bin/python -E -s`), listed in `outputs/index.json` with `units: "none"` and captions.
  - Write `handoff_notes.json` and run `handoff.py build --status needs_approval`.
  - Record via `record()`, then delete `integrity.json` and the index entry, and run `receive.py` with `--transcript-root` pointing to a temp root that holds the synthetic transcript under the computed slug. Assert `RECEIVED … OK`, that `report.md` exists, and that it equals `final_report.md`.
  - Keep the tamper negative check.
  - Assert both figures exist and are non-empty, and that the PNG is 300 dpi (read the pHYs chunk, or assert via Pillow if it is available in `.venv-data`; otherwise check the pHYs bytes with stdlib).
- [ ] **Step 2:** Run `python3 tests/integration/data_smoke.py`. Expected: `DATA SMOKE PASSED`. If it fails because of earlier-task code, report BLOCKED with evidence; do not weaken assertions.
- [ ] **Step 3:** Run `python3 scripts/run_tests.py` and `python3 scripts/check_isolation.py`. Expected: PASS.
- [ ] **Step 4:** Commit `test(data): smoke covers handoff.py, receive recovery, recorder report and figures`.

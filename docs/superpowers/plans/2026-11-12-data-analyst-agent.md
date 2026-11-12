# Data-analyst specialist (sub-project 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a guarded, Claude-side `data-analyst` specialist that retrieves and analyzes data with vendored K-Dense scientific skills and returns hashed data products and `needs_approval` proposals.

**Architecture:**
- Vendored skills live in `vendor/scientific-agent-skills/`, outside skill discovery. One preloaded `.claude/skills/data-workflow` skill indexes them.
- Stdlib-only helpers in `scripts/data/` handle session creation, protected-state snapshots, fetching/ledger and manifests.
- Two Claude hooks enforce boundaries:
  - `.claude/scripts/data_guard.py`, in the agent's own frontmatter;
  - `.claude/scripts/data_orchestrator_guard.py`, in project settings.
- Existing validators (`validate_handoff`, invocation recorder, `state.py`, `check_isolation`) learn the new specialist.

**Tech Stack:**
- Python 3.11+ stdlib with `unittest` for framework code and tests;
- a uv-managed `.venv-data` (Python 3.12) for scientific packages;
- Claude Code subagent frontmatter and hooks.

**Spec:** `docs/superpowers/specs/2026-11-12-data-analyst-agent-design.md`

## Global Constraints

- **Names:**
  - Claude agent `data-analyst`; handoff `specialist` value `data_analyst`; handoff/manifest `stage` value `data`;
  - session root `runs/data-analyst/<session_id>/`.
- **Session ID** regex: `^data-\d{8}T\d{6}Z-[0-9a-f]{8}$`. It must also pass `scripts.codex.launcher_config.validate_session_id`.
- **Timestamps:** ISO-8601 UTC with `+00:00` offset, e.g. `2026-11-12T09:15:00+00:00`.
- **Vendored skills:**
  - upstream `https://github.com/K-Dense-AI/scientific-agent-skills`, commit `2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5`, path `vendor/scientific-agent-skills/`;
  - the 10 skills: `depmap database-lookup gget bulk-rnaseq pydeseq2 pathway-enrichment cellprofiler statistical-analysis scikit-learn uncertainty-and-units`.
  - Vendored files are byte-identical to upstream except entries listed in `VENDOR.lock.json` `modified`.
- **Data environment:** `.venv-data/` at repo root, Python 3.12, built from `setup/data-requirements.lock`. Direct pins include `pydeseq2==0.5.4`, `gseapy==1.3.1`, `anndata==0.13.4`. CellProfiler is optional (`--with-cellprofiler`) and goes in a separate `.venv-cellprofiler/`.
- **Python invocation** allowed for the agent: `.venv-data/bin/python -E -s <script> …` (never `-I`; see spec §5.1).
- **Allowed agent shell commands:** that Python form, `ls`, and `head` only.
- **Hook conventions** (match `stage_gate_guard.py`): read the JSON event from stdin; deny by printing a reason to stderr and exiting `2`; allow with exit `0`.
- **Test style:**
  - framework tests are stdlib `unittest`, need no third-party packages, and run under `python3 scripts/run_tests.py`;
  - `.claude/scripts/test_*.py` hold hook tests, and `tests/data/` (new suite) holds `scripts/data` tests.
- **Shared-state rule:** the data agent never edits `CLAUDE.md`, `DECISIONS.md`, `CURRENT_STATE.md`, `DATA_DICTIONARY.md` or other specialists' runs. Only the orchestrator writes shared state.
- **Codex:** no `skills/data-workflow` or Codex profile in this sub-project (sub-project 3). `AGENTS.md` only states that the data agent is Claude-only for now. The spec §3.3 mention of `skills/data-workflow` is deferred because top-level `skills/` holds the dispatcher-facing Codex variants, which differ from `.claude/skills/`.

## Review Focus

1. **Orchestrator guard false positives.** `git add vendor/scientific-agent-skills/...`, `cat`/`ls`/`grep` on vendored files, and checkpoint commits must still work from the main session. Only *execution* of vendored scripts or of `.venv-data` executables is denied. Pinned by Task 6 tests `test_git_and_read_commands_on_vendor_allowed`.
2. **Quoted shell metacharacters.** `python -E -s script.py "$(rm -rf x)"` must be denied even though `$(` sits inside quotes, because the guard checks the raw string before tokenizing. Pinned by Task 6 `test_quoted_substitution_denied`.
3. **Symlink escape from the session directory.** A script may create `runs/data-analyst/<id>/outputs/link -> /outside`. A later Write to `outputs/link/x` must be denied, and `manifest.py verify` must reject symlinked artifacts. Pinned by Task 6 `test_write_through_symlink_denied` and Task 5 `test_symlinked_output_rejected`.
4. **Unlisted outputs.** A file dropped in `outputs/` but missing from `outputs/index.json` must fail `verify`, so no unhashed result can ride along. Pinned by Task 5 `test_unlisted_output_rejected`.
5. **Snapshot cost and scope.** Snapshots must skip `.git/`, `.venv-data/`, `.venv-cellprofiler/`, `data-cache/`, `__pycache__/` and the active session directory. Otherwise every invocation hashes gigabytes, or flags the agent's own work. Pinned by Task 3 `test_snapshot_excludes_heavy_and_own_dirs`.

---

### Task 1: Vendor the skills with attribution

**Files:**
- Create: `vendor/scientific-agent-skills/{LICENSE.md,CITATION.cff,VENDOR.md,VENDOR.lock.json}` plus the 10 skill directories
- Create: `scripts/data/__init__.py` (empty), `scripts/data/vendor_lock.py`
- Create: `THIRD_PARTY_NOTICES.md`
- Modify: `README.md` (new section "Citation and third-party skills"; add a `data-analyst` row to the Agents table marked "Claude only")
- Modify: `scripts/run_tests.py` (add `"tests/data"` to `SUITES`)
- Test: `tests/data/test_vendor.py`

**Interfaces:**
- Produces: `scripts.data.vendor_lock.VENDORED_SKILLS: tuple[str, ...]` (the 10 names, in the Global Constraints order); `VENDOR_ROOT = Path("vendor/scientific-agent-skills")`; `UPSTREAM_COMMIT: str`; `build_lock(vendor_root: Path, modified: dict[str, dict]) -> dict`; `verify_lock(vendor_root: Path) -> list[str]` (error strings, empty = OK).
- `VENDOR.lock.json` schema: `{"upstream": url, "commit": sha, "files": {relpath: sha256}, "modified": {relpath: {"upstream_sha256", "local_sha256", "reason", "date"}}}`. `files` holds the upstream hash for every file. For modified files, the current bytes must match `local_sha256`.

- [ ] **Step 1: Write failing tests** in `tests/data/test_vendor.py`:
  - `test_all_skills_present`: each of `VENDORED_SKILLS` has `SKILL.md` whose frontmatter `name:` equals the directory name.
  - `test_lock_verifies`: `verify_lock(VENDOR_ROOT) == []`.
  - `test_tampered_file_detected`: copy the vendor tree to a temp dir, append a byte to `depmap/SKILL.md`, and assert one error naming that path.
  - `test_pydeseq2_modification_recorded`: `"pydeseq2/scripts/run_deseq2_analysis.py"` is in `modified`, and the file contains `# Local modification (agentic_system_for_modelling, 2026-11-12)`.
  - `test_notices_cover_every_skill`: `THIRD_PARTY_NOTICES.md` contains each skill name, `CC-BY-4.0`, `Kuan-lin Huang`, `2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5`, and `Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents`.
  - `test_not_under_skill_discovery`: no `VENDORED_SKILLS` name exists under `.claude/skills/` or `skills/`.
- [ ] **Step 2:** Run `python3 -m unittest discover -s tests/data -v`. Expected: FAIL (module/dirs missing).
- [ ] **Step 3: Vendor.**
  - `git clone` upstream into a temp dir outside the repo and `git checkout 2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5`.
  - Copy the 10 `skills/<name>/` dirs, `LICENSE.md` and `CITATION.cff` into `vendor/scientific-agent-skills/`.
  - Apply the pydeseq2 fix in `save_results`: replace `dds.to_picklable_anndata().write_h5ad(dds_path)` with an `adata` variable whose `uns` `pandas.Series` values become `value.to_dict()` before `write_h5ad`, and put the marker comment above it. This is the same fix verified on 2026-11-12.
  - Implement `vendor_lock.py` with a CLI: `build --modified-reason PATH=REASON` and `verify`.
  - Generate `VENDOR.lock.json`, computing `upstream_sha256` from the clean upstream copy.
- [ ] **Step 4: Write documents.**
  - `VENDOR.md`: upstream URL, commit, date 2026-11-12, a table of skill/license/author taken from each SKILL.md frontmatter, local modifications with rationale, and the re-sync procedure (re-clone at a new commit, re-copy, re-apply listed modifications, `vendor_lock.py build`, run `tests/data`).
  - `THIRD_PARTY_NOTICES.md`: per-skill license and author; full upstream MIT text; CC-BY-4.0 attribution for `depmap` with the license URL `https://creativecommons.org/licenses/by/4.0/` and "modified: no"; a pointer to `VENDOR.md` for changes.
  - README section with the preferred citation (authors and title copied from upstream `CITATION.cff` `preferred-citation`) plus repo and commit.
- [ ] **Step 5:** Run `python3 -m unittest discover -s tests/data -v` and `python3 scripts/run_tests.py`. Expected: all PASS.
- [ ] **Step 6: Commit** `feat(data): vendor K-Dense scientific skills with attribution and lock`.

### Task 2: Data environment and setup flags

**Files:**
- Create: `setup/data-requirements.txt`, `setup/data-requirements.lock`, `setup/data-requirements-cellprofiler.txt`
- Create: `scripts/data/environment.py`
- Modify: `scripts/setup.py` (`parser()` adds `--with-data` and `--with-cellprofiler` (the latter implies the former); `execute()` calls the data environment after the existing environment verification and before configuration writes; in `--check` mode only checks)
- Modify: `.gitignore` (add `.venv-data/`, `.venv-cellprofiler/`, `data-cache/`)
- Test: `tests/setup/test_data_setup.py`

**Interfaces:**
- Produces:
  - `scripts.data.environment.DATA_ENV = Path(".venv-data")`, `CP_ENV = Path(".venv-cellprofiler")`;
  - `data_python(root: Path) -> Path` (returns `root/.venv-data/bin/python`);
  - `lock_sha256(root: Path) -> str`;
  - `ensure(root: Path, uv: str, *, check: bool, with_cellprofiler: bool) -> dict`, returning `{"passed": bool, "errors": list[str], "python": str|None, "lock_sha256": str, "cellprofiler": str|None}`.
- `ensure` commands, run via `subprocess.run(..., check=True)` and only when `check` is false:
  - `uv venv .venv-data --python 3.12`;
  - `uv pip sync --python .venv-data/bin/python setup/data-requirements.lock`;
  - then a verification import, `.venv-data/bin/python -E -s -c "import pydeseq2, gseapy, anndata, decoupler, sklearn, statsmodels, pint, uncertainties, gget"`.
- With CellProfiler: `uv venv .venv-cellprofiler --python <version required by the pinned CellProfiler>` plus `uv pip install --python .venv-cellprofiler/bin/python -r setup/data-requirements-cellprofiler.txt`. The verified executable is `.venv-cellprofiler/bin/cellprofiler --version`.

- [ ] **Step 1: Write failing tests**, mocking `subprocess.run` and following `tests/setup/test_biomass_setup.py` patterns:
  - `test_parser_accepts_data_flags`;
  - `test_cellprofiler_implies_data`;
  - `test_ensure_runs_expected_commands`: assert the exact uv argv sequence above;
  - `test_check_mode_runs_no_install`: only the import probe runs;
  - `test_missing_uv_is_error`: `uv` is taken from `resolved["uv_path"]` when set, else `shutil.which("uv")`; when neither exists, the error text contains `uv is required for --with-data`;
  - `test_gitignore_has_data_dirs`.
- [ ] **Step 2:** Run `python3 -m unittest tests.setup.test_data_setup -v`. Expected: FAIL.
- [ ] **Step 3: Write requirements.**
  - `data-requirements.txt` has direct exact pins: `pydeseq2==0.5.4`, `gseapy==1.3.1`, `anndata==0.13.4`, plus `decoupler`, `scikit-learn`, `statsmodels`, `scipy`, `pandas`, `numpy`, `matplotlib`, `pint`, `uncertainties`, `gget`, `requests`, each pinned to the version resolved today.
  - Generate the lock with `uv pip compile --python-version 3.12 setup/data-requirements.txt -o setup/data-requirements.lock`.
  - `data-requirements-cellprofiler.txt` pins the newest CellProfiler release that installs on Linux. Record its required Python in a comment on line 1, e.g. `# python=3.X`, and have `ensure` read that comment.
- [ ] **Step 4:** Implement `environment.py` and the `setup.py` wiring. Add `report["data_environment"]` and extend `errors` on failure.
- [ ] **Step 5:** Run the tests above and `python3 scripts/run_tests.py`. Expected: PASS.
- [ ] **Step 6: Real install check.** Run `python3 scripts/setup.py --client claude --environment-mode plugin --with-data --non-interactive`, then `.venv-data/bin/python -E -s -c "import pydeseq2; print(pydeseq2.__version__)"`. Expected: `0.5.4`. If the full setup cannot run on this machine, call `scripts.data.environment.ensure` directly and record which path was used in the commit message.
- [ ] **Step 7: Commit** `feat(data): pinned .venv-data environment and setup --with-data`.

### Task 3: Sessions and protected-state snapshot

**Files:**
- Create: `scripts/data/common.py`, `scripts/data/snapshot.py`, `scripts/data/session.py`
- Test: `tests/data/test_session.py`

**Interfaces:**
- `scripts.data.common`:
  - `SESSION_RE`;
  - `RUNS_ROOT = Path("runs/data-analyst")`;
  - `project_root() -> Path`: `CLAUDE_PROJECT_DIR` if set, else `Path(__file__).resolve().parents[2]`;
  - `session_dir(root: Path, session_id: str) -> Path`: validates the ID and returns an existing directory, else raises `ValueError`;
  - `utc_now() -> str` (`+00:00` form);
  - `sha256_file(path: Path) -> str`;
  - `reject_symlinks(path: Path, root: Path) -> None`: raises `ValueError` if any component from `root` down is a symlink.
- `scripts.data.snapshot`:
  - `EXCLUDED_DIRS = (".git", ".venv-data", ".venv-cellprofiler", "data-cache", "__pycache__")`;
  - `take(root: Path, session_id: str) -> dict[str, str]`: relpath → sha256 for regular files, excluding `EXCLUDED_DIRS` at any depth and `runs/data-analyst/<session_id>/`; symlinks are recorded as `"symlink:" + target`;
  - `diff(before: dict, after: dict) -> list[str]`: sorted relpaths added, removed or changed.
- `scripts/data/session.py new --purpose TEXT [--derived-from ID]` creates `runs/data-analyst/<id>/{scripts,raw,outputs,proposals}/` and writes `identity.json`:

  ```json
  {"schema_version": 1, "session_id": "…", "purpose": "…", "created_at": "…+00:00",
   "derived_from_session_id": null, "protected_snapshot": {}}
  ```

  - Its last stdout line is exactly `Data session created: <id> (snapshot sha256=<64hex>)`, where the digest is the SHA256 of `json.dumps(protected_snapshot, sort_keys=True, separators=(",", ":"))`.
  - `--derived-from` must match `SESSION_RE` and name an existing session.
  - The ID is `data-` + UTC `%Y%m%dT%H%M%SZ` + `-` + `secrets.token_hex(4)`.
- `snapshot.verify_session(root: Path, session_id: str, expected_digest: str | None) -> dict` returns `{"passed": bool, "changed": list[str], "identity_intact": bool}`. `identity_intact` is false if the recomputed digest of the stored snapshot differs from `expected_digest` (when given).

- [ ] **Step 1: Write failing tests** (temp project root via `CLAUDE_PROJECT_DIR`):
  - `test_new_session_layout_and_id`: regex match, 4 subdirs, identity fields, final stdout line format;
  - `test_snapshot_excludes_heavy_and_own_dirs`: files in `.git/x`, `.venv-data/x`, `data-cache/x`, `a/__pycache__/x` and the session dir are absent from the snapshot; `DECISIONS.md` is present;
  - `test_tamper_detected`: modify `DECISIONS.md` after `new`, and `verify_session(...)["changed"] == ["DECISIONS.md"]`;
  - `test_identity_rewrite_detected`: change `protected_snapshot` in `identity.json`, and `identity_intact` is False when the original digest is given;
  - `test_derived_from_must_exist`.
- [ ] **Step 2:** Run `python3 -m unittest tests.data.test_session -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `common.py`, `snapshot.py` and `session.py` (argparse, `main() -> int`).
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(data): data sessions with protected-state snapshot`.

### Task 4: Fetching and the source ledger

**Files:**
- Create: `scripts/data/ledger.py`, `scripts/data/fetch.py`
- Test: `tests/data/test_fetch.py`

**Interfaces:**
- Consumes: `common.session_dir`, `common.sha256_file`, `common.utc_now`.
- `scripts.data.ledger`:
  - `append(session: Path, entry: dict) -> None`: validates keys `kind ∈ {download, api, input}`, `uri`, `release` (non-empty str), `retrieved_at`, `sha256` (64 hex), `terms` (str, may be empty), and `path`. It appends one JSON line to `sources.jsonl`.
  - `record_api(session: Path, *, url: str, params: dict, response: bytes | str, release: str, name: str, terms: str = "") -> dict`: writes `raw/<name>`, refusing to overwrite, and appends an `api` entry whose `uri` is the URL with the urlencoded sorted params.
  - `record_input(session: Path, path: Path, root: Path, *, release: str = "researcher-supplied", terms: str = "") -> dict`: the path must be under `root/inputs/`. Appends an `input` entry with its sha256; no copy is made.
- `scripts/data/fetch.py --session ID (--url URL --name NAME | --input PATH) --release TEXT [--terms TEXT] [--expect binary|tabular|json] [--max-bytes N]`:
  - URL mode streams to `data-cache/tmp-*`, then renames to `data-cache/sha256/<hex>`, reusing an existing entry.
  - It writes `raw/<name>.source.json` (`uri`, `release`, `retrieved_at`, `sha256`, `cache_path`, `content_type`, `terms`) and appends a `download` entry with `path` = cache path.
  - `--expect tabular|json` rejects `text/html` content types or bodies starting (after whitespace, case-insensitive) with `<!doctype` or `<html`, exiting non-zero with `received HTML, expected <kind>`.
  - The default `--max-bytes` is `5_000_000_000`, and the timeout is 120 s.

- [ ] **Step 1: Write failing tests** using a `http.server.ThreadingHTTPServer` fixture on 127.0.0.1:
  - `test_download_cached_and_ledgered`: the cache file exists at its sha256 path, and one ledger line has kind `download`;
  - `test_second_download_reuses_cache`;
  - `test_html_rejected_when_tabular_expected`: no ledger line is written;
  - `test_record_api_writes_raw_and_ledger`;
  - `test_input_outside_inputs_rejected`;
  - `test_ledger_rejects_missing_release`.
- [ ] **Step 2:** Run `python3 -m unittest tests.data.test_fetch -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `ledger.py` and `fetch.py` (stdlib `urllib.request`).
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(data): fetch helper with content-addressed cache and source ledger`.

### Task 5: Manifest build and verify

**Files:**
- Create: `scripts/data/manifest.py`
- Test: `tests/data/test_manifest.py`

**Interfaces:**
- Consumes: Tasks 3–4 files (`identity.json`, `sources.jsonl`), `vendor_lock.VENDORED_SKILLS`, `environment.lock_sha256`.
- Agent-authored inputs:
  - `outputs/index.json`: a list of `{"path": "outputs/…", "description": str, "units": dict[str,str] | "dimensionless" | "none", "identifiers": str}`;
  - `proposals/index.json`: a list of `{"id": "P<n>", "target_layer": "spec|neko|maboss|biomass|physicell", "kind": "seed_genes|initial_states|mutations|validation_targets|parameters|time_course", "path": "proposals/…", "method": str, "thresholds": dict}`.
  - Either index may be absent, which means an empty list.
- Produces:
  - `build(root: Path, session_id: str, skills: list[str]) -> dict`, which writes `manifest.json` in the spec §6.2 shape: `status` forced to `"proposed"`; `environment.python` from `platform.python_version()`; `environment.lock_sha256`; `scripts` = every `scripts/**/*.py`.
  - `verify(root: Path, session_id: str) -> list[str]`.
  - CLI: `manifest.py build --session ID [--skills ...]` and `manifest.py verify --session ID`, with exit code 1 and one error per line on failure.
- `verify` rules (each an error string):
  - identity fields match;
  - every listed path exists, is a regular file, has no symlink component, and its hash matches;
  - every file under `outputs/` and `proposals/` other than the two `index.json` files is listed;
  - every `scripts/**/*.py` is listed;
  - for `.csv`/`.tsv` outputs, every column whose non-empty values all parse as `float` must appear in the `units` dict, unless `units` is the string `"dimensionless"`;
  - non-tabular outputs need `units` (`"none"` is allowed);
  - `identifiers` is a non-empty string;
  - sources follow `ledger.append` rules;
  - `vendored_skills_used` ⊆ `VENDORED_SKILLS`;
  - proposal ids are unique and match `^P\d+$`, and layers/kinds are in the enums.

- [ ] **Step 1: Write failing tests** (fixture session built with `session.py`):
  - `test_round_trip_passes`;
  - `test_changed_output_hash_rejected`;
  - `test_unlisted_output_rejected`;
  - `test_symlinked_output_rejected`;
  - `test_numeric_column_without_unit_rejected`: a CSV with column `padj` and units `{"log2FoldChange": "log2 ratio"}` yields an error mentioning `padj`;
  - `test_unknown_skill_rejected`;
  - `test_bad_proposal_kind_rejected`;
  - `test_status_always_proposed`.
- [ ] **Step 2:** Run `python3 -m unittest tests.data.test_manifest -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `manifest.py` (stdlib `csv` for column checks).
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(data): data-product manifest build/verify`.

### Task 6: Guard hooks

**Files:**
- Create: `.claude/scripts/data_guard.py`, `.claude/scripts/data_orchestrator_guard.py`
- Modify: `.claude/settings.json` (add a `PreToolUse` entry, matcher `"Bash"`, command `python3 "$CLAUDE_PROJECT_DIR/.claude/scripts/data_orchestrator_guard.py"`; keep existing hooks)
- Test: `.claude/scripts/test_data_guard.py`, `.claude/scripts/test_data_orchestrator_guard.py`

**Interfaces:**
- Consumes: `scripts.data.common` (`SESSION_RE`, `reject_symlinks`, `project_root`).
- `data_guard.py`:
  - `transcript_data_session(transcript: Path) -> tuple[str, str] | None`: scans JSONL transcript events for Bash `tool_use` blocks whose `input.command` is an allowed `session.py new` command. It returns `(session_id, digest)` parsed from the matching `tool_result` text's last line `^Data session created: (\S+) \(snapshot sha256=([0-9a-f]{64})\)$`, and only from error-free results. It raises `ValueError` if more than one session was created. Mirror the event traversal in `specialist_report_guard.transcript_sessions`.
  - `check_bash(command: str, root: Path, active: str | None) -> None` raises `ValueError(reason)`:
    1. Reject if the raw string contains any of `; | & < > $ \` \n \r` or the two-character sequence `$(`.
    2. `shlex.split`.
    3. `ls`/`head`: every non-option argument must resolve inside `root`.
    4. Python: `argv[0]` must resolve to `root/.venv-data/bin/python`, `argv[1:3] == ["-E", "-s"]`, and `argv[3]` (after `reject_symlinks` and `resolve()`) must be under `runs/data-analyst/<active>/scripts/`, `vendor/scientific-agent-skills/*/scripts/` or `scripts/data/`, and end in `.py`.
    5. Before a session exists (`active is None`), only `scripts/data/session.py new …`, `ls` and `head` are allowed. A second `session.py new` is denied.
    6. For `scripts/data/{fetch,manifest}.py`, the `--session` value must equal `active`.
  - `check_write(file_path: str, root: Path, active: str | None) -> None`: the path must be inside `runs/data-analyst/<active>/` with no symlink component. The basename must not be `identity.json`, `manifest.json`, `integrity.json` or `sources.jsonl`.
  - CLI: `data_guard.py bash|write`. It reads the event (`tool_input.command` / `tool_input.file_path`, `transcript_path`), exits 2 with `Data analyst <tool> blocked: <reason>` on violation, and exits 0 otherwise.
- `data_orchestrator_guard.py`:
  - Allow if `event.get("agent_type") == "data-analyst"`.
  - Otherwise deny (exit 2) when a token resolves into `.venv-data/` or `.venv-cellprofiler/`; or when a token whose basename matches `^python[0-9.]*$` (or `uv`, `uvx`) is followed by a token under `vendor/scientific-agent-skills/`; or when `argv[0]` itself is a path under `vendor/scientific-agent-skills/`.
  - All other commands pass, including `git`, `cat`, `ls` and `grep` on vendored paths.

- [ ] **Step 1: Write failing tests:**
  - `test_python_session_script_allowed`;
  - `test_vendor_script_allowed`;
  - `test_other_session_script_denied`;
  - `test_quoted_substitution_denied`: `… script.py "$(rm -rf x)"`;
  - `test_pipe_and_redirect_denied`;
  - `test_minus_I_denied`;
  - `test_system_python_denied`;
  - `test_ls_outside_root_denied`;
  - `test_only_session_new_before_session`;
  - `test_second_session_denied`;
  - `test_fetch_with_wrong_session_denied`;
  - `test_write_inside_session_allowed`;
  - `test_write_identity_denied`;
  - `test_write_through_symlink_denied`;
  - `test_transcript_binding_ignores_prose`: an assistant text message containing the creation line does not bind a session;
  - orchestrator guard: `test_main_session_vendor_execution_denied` (`python3 vendor/scientific-agent-skills/depmap/scripts/depmap_data.py`); `test_venv_data_denied`; `test_git_and_read_commands_on_vendor_allowed` (`git add vendor/scientific-agent-skills`, `cat vendor/scientific-agent-skills/VENDOR.md`); `test_data_analyst_allowed`; `test_unrelated_command_allowed`.
- [ ] **Step 2:** Run `python3 -m unittest discover -s .claude/scripts -p "test_data_*.py" -v`. Expected: FAIL.
- [ ] **Step 3:** Implement both guards and register the orchestrator hook in `.claude/settings.json`.
- [ ] **Step 4:** Run the tests and `python3 scripts/run_tests.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(data): data-analyst and orchestrator guard hooks`.

### Task 7: Agent definition, workflow skill, policy and isolation checks

**Files:**
- Create: `.claude/agents/data-analyst.md`, `.claude/skills/data-workflow/SKILL.md`, `docs/data-workflow.md`
- Modify: `CLAUDE.md`, `AGENTS.md`, `scripts/check_isolation.py` (`check()`), `.claude/scripts/test_agent_mcp_access.py` (a data-analyst test class; `AGENTS` dict unchanged)
- Test: `tests/setup/test_isolation_data.py`, additions in `.claude/scripts/test_agent_mcp_access.py`

**Interfaces:**
- Agent frontmatter, exact:

  ```yaml
  name: data-analyst
  description: Use for bounded data retrieval and analysis (DepMap, TCGA/GDC, cBioPortal, GEO, PRIDE, Open Targets, researcher inputs, bulk RNA-seq, enrichment, microscopy features) producing hashed data products and data-to-model proposals for researcher approval.
  model: inherit
  tools: [Read, Grep, Glob, Write, Bash]
  disallowedTools: [Edit, Skill, Agent, 'mcp__*']
  permissionMode: acceptEdits
  maxTurns: 105
  skills: [data-workflow]
  color: cyan
  hooks: PreToolUse Bash → python3 "$CLAUDE_PROJECT_DIR/.claude/scripts/data_guard.py" bash; PreToolUse Write → … data_guard.py write
  ```

  Use block-list YAML matching `network-curator.md` formatting. Do not add an `mcpServers` key.
- The agent body covers:
  - the authority boundary (no shared-state edits, no stage advancement, no approvals, no delegation);
  - one session per invocation;
  - the analysis-as-saved-script rule;
  - `needs_approval` whenever proposals exist;
  - `blocked` with remediation if `.venv-data` or a source is missing;
  - the handoff envelope fields (spec §6.3);
  - "associations are not mechanisms; candidate edges go to the orchestrator for literature-reviewer".
- `data-workflow` SKILL.md frontmatter:
  - `name: data-workflow`;
  - a description stating it is preloaded into `data-analyst` and that the main session delegates instead of loading it.
- `data-workflow` sections, per spec §3.3:
  1. Session lifecycle with exact commands;
  2. Command rules (the allowlist), plus a script header template that adds the repo root to `sys.path` (`Path(__file__).resolve().parents[4]`) so scripts can import `scripts.data.ledger`;
  3. A task→vendored-guide index table covering all 10 skills, with the TCGA references `database-lookup/references/tcga-gdc.md` and `cbioportal.md`;
  4. DepMap access notes (verification page; `inputs/` route via `fetch.py --input`; Open Targets `depMapEssentiality` GraphQL for single genes);
  5. Scientific rules, plus the network scope: only documented database APIs and download endpoints from the vendored guides, or researcher-supplied URLs; no general web search or scraping;
  6. `outputs/index.json`, `proposals/index.json` and `report.md` templates (spec §6.4 headings);
  7. The citation reminder (list vendored guides used in `manifest.py build --skills`).
- `CLAUDE.md` edits:
  - In "Main-agent role and isolation", add a paragraph:
    - data work is delegated to `data-analyst`;
    - the orchestrator never runs `vendor/scientific-agent-skills` scripts or `.venv-data`;
    - data-analyst invocations never run concurrently with other specialists or state writes;
    - the orchestrator registers each approved data product in `DATA_DICTIONARY.md` (name, identifiers, units, source release, data session ID).
  - Amend "Guarded report Write is their only local authoring exception" with "; data-analyst may also author scripts, outputs and proposals inside its own guarded session directory".
  - Amend the runs line "Each MCP issues its own ID" with "; data-analyst IDs are issued by scripts/data/session.py".
  - In the provenance-tag list, add `data-derived`: an approved data-analyst proposal, citing data session ID, proposal id and SHA256; an association, never a mechanism claim.
- `AGENTS.md`: one paragraph saying the data analyst is Claude-only until Codex parity, and that Codex orchestrators must not run vendored scripts or `.venv-data`.
- `check_isolation.check()` adds these errors:
  - `.claude/agents/data-analyst.md` exists and its header contains `mcpServers`, or lacks any of `'mcp__*'`, `Skill`, `Agent` and `Edit` in `disallowedTools`;
  - any `VENDORED_SKILLS` directory exists under `.claude/skills/` or `skills/`;
  - `.claude/settings.json` has no PreToolUse Bash hook whose command contains `data_orchestrator_guard.py`.
- `docs/data-workflow.md`: a short user-facing overview plus the manual verification checklist from spec §7 (`/agents` shows `data-analyst`; a read-only task works; the main session is denied when running a vendored script).

- [ ] **Step 1: Write failing tests:**
  - `test_data_analyst_has_no_mcp_and_denies_mcp`;
  - `test_data_analyst_preloads_data_workflow`;
  - `test_data_analyst_hooks_reference_data_guard`;
  - `test_isolation_flags_mcp_on_data_analyst`, `test_isolation_flags_vendored_skill_in_claude_skills`, `test_isolation_flags_missing_orchestrator_hook` (temp copies, as in `tests/setup/test_isolation_pubmed.py`);
  - `test_claude_md_mentions_data_derived_and_delegation`: asserts the substrings `data-derived`, `data-analyst may also author`, `scripts/data/session.py`.
- [ ] **Step 2:** Run `python3 scripts/run_tests.py`. Expected: the new tests FAIL.
- [ ] **Step 3:** Write the agent, skill, docs and policy edits, and the `check_isolation` additions.
- [ ] **Step 4:** Run `python3 scripts/run_tests.py` and `python3 scripts/check_isolation.py`. Expected: PASS, no errors.
- [ ] **Step 5: Commit** `feat(data): data-analyst agent, data-workflow skill and isolation policy`.

### Task 8: Validators, registry and invocation integrity

**Files:**
- Modify:
  - `scripts/codex/validate_handoff.py` (`SPECIALIST_STAGES["data_analyst"] = "data"`; `SAFE_NEXT_STAGES["data"] = {None, "researcher_approval"}`; `ARTIFACT_ROOTS["data_analyst"] = ("runs/data-analyst",)`; a new `_data_session_checks`);
  - `scripts/capture/index.py` (`SPECIALISTS` adds `'data-analyst'`);
  - `scripts/capture/record_invocation.py` (`session_ids` dispatch plus an integrity record);
  - `scripts/state.py` (`ROLES["data-analyst"] = "data"`);
  - `.claude/scripts/specialist_report_guard.py` (only if `SPECIALISTS` reuse breaks its `choices`/`PREFIXES`: exclude `data-analyst` from its choices).
- Test: `tests/codex/test_validate_handoff_data.py`, `tests/data/test_record_invocation_data.py`

**Interfaces:**
- Consumes: `snapshot.verify_session`, `manifest.verify`, `data_guard.transcript_data_session`.
- `record_invocation.session_ids(path, specialist)`: for `data-analyst`, returns `{session_id}` from `transcript_data_session`, or an empty set. Other specialists are unchanged.
- In `record()`, when the specialist is `data-analyst` and a session is bound, call `transcript_data_session(transcript)` again to obtain the digest. Then call `snapshot.verify_session(project, session, digest)`. Write `runs/data-analyst/<id>/integrity.json` as `{"schema_version": 1, "session_id", "invocation_id", "checked_at", "passed", "changed", "identity_intact"}`. `passed` is false if `changed` is non-empty or `identity_intact` is false. Include the same object as `integrity` in the invocation metadata.
- `validate_handoff._data_session_checks(handoff, project)` runs for `data_analyst` when the status is `completed` or `needs_approval`. It raises `HandoffValidationError` when:
  - `integrity.json` is missing or `passed` is not true;
  - `scripts.data.manifest.verify` returns errors (joined into the message);
  - the manifest has proposals but the status is `completed` (`"proposals require needs_approval"`);
  - the status is `needs_approval` but `decisions_required` has fewer entries than there are proposals.
- For `completed`, the existing `_completed_artifacts` path also applies. Required files are `manifest.json`, a `.md` report, and at least one artifact under `outputs/` or `proposals/`.

- [ ] **Step 1: Write failing tests:**
  - `test_valid_data_handoff_accepted` (completed, no proposals);
  - `test_proposals_require_needs_approval`;
  - `test_needs_approval_with_proposals_accepted`;
  - `test_failed_integrity_rejected`;
  - `test_manifest_error_rejected`;
  - `test_recorder_writes_integrity_and_detects_tamper`: a fixture transcript with a Bash `session.py new` result, then modify `DECISIONS.md`, call `record(project, payload)`, and assert `integrity.json` has `passed: false` and `changed: ["DECISIONS.md"]`;
  - `test_recorder_ignores_unbound_data_invocation`;
  - `test_state_registry_accepts_data_analyst`.
- [ ] **Step 2:** Run `python3 scripts/run_tests.py`. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement the changes listed in Files and Interfaces.
- [ ] **Step 4:** Run `python3 scripts/run_tests.py`. Expected: all suites PASS, including the pre-existing ~520 tests.
- [ ] **Step 5: Commit** `feat(data): validate data_analyst handoffs and record invocation integrity`.

### Task 9: Offline end-to-end smoke test

**Files:**
- Create: `tests/integration/data_smoke.py`
- Modify: `docs/data-workflow.md` (how to run it)

**Interfaces:**
- Consumes: everything above. Requires `.venv-data`; if it is missing, print `SKIP: .venv-data not installed` and exit 0.
- Runs with system `python3 tests/integration/data_smoke.py` in a temp copy of the repo (`shutil.copytree`, ignoring `.git`, `.venv-*` and `data-cache`, with a symlink-free reference to the real `.venv-data` via `--data-python`). All scientific steps go through `.venv-data/bin/python -E -s`.

- [ ] **Step 1: Write the smoke script.** Steps:
  1. `session.py new --purpose smoke`.
  2. Write `scripts/01_synthetic.py` into the session. It creates:
     - `outputs/counts.csv`: 600 genes `GENE0001…GENE0600` in a 4-vs-4 negative-binomial design (seed 1; `GENE0001–0030` ×2.5 up and `GENE0031–0060` ×0.4 down);
     - `outputs/metadata.csv`;
     - `raw/sets.gmt`: 20 sets of 30 genes, where `SET_UP` = up genes and `SET_DOWN` = down genes.

     It records the GMT with `ledger.append` (kind `input`, uri `synthetic:sets.gmt`, release `synthetic`, path `raw/sets.gmt`, its sha256).
  3. Run vendored `pydeseq2/scripts/run_deseq2_analysis.py --counts … --metadata … --design "~condition" --contrast condition treated control --output <session>/outputs/de --plots`. Assert `outputs/de/deseq_dataset.h5ad` exists; this is the regression check for the local pydeseq2 fix.
  4. Run vendored `pathway-enrichment/scripts/run_enrichment.py gsea --deseq2 outputs/de/deseq2_results_unshrunken.csv --libraries <session>/raw/sets.gmt --min-size 15 --permutations 200 --seed 123 --threads 1 --outdir <session>/outputs/gsea`. Assert the significant terms include ones containing `SET_UP` (NES > 0) and `SET_DOWN` (NES < 0).
  5. Write `proposals/P1_seed_genes.csv` (top 10 up genes) and both index files. `outputs/index.json` must list **every** file under `outputs/`, including the DESeq2 and GSEA products (CSV, PNG, H5AD, JSON), with units for every numeric column (e.g. `baseMean`, `log2FoldChange`, `lfcSE`, `stat`, `pvalue`, `padj`, `NES`, `FDR q-val`), because `verify` rejects unlisted files.
  6. `manifest.py build --session <id> --skills pydeseq2 pathway-enrichment`, then `manifest.py verify`; assert exit 0.
  7. Simulate the recorder: call `snapshot.verify_session` and write `integrity.json` as Task 8 does.
  8. Build a `needs_approval` handoff with one `decisions_required` entry, and assert that `validate_handoff` accepts it.
  9. Print `DATA SMOKE PASSED`.
- [ ] **Step 2:** Run `python3 tests/integration/data_smoke.py`. Expected: `DATA SMOKE PASSED`. If an assertion fails, fix the owning task's code, not the assertion.
- [ ] **Step 3:** Run `python3 scripts/run_tests.py` and `python3 scripts/check_isolation.py`. Expected: PASS.
- [ ] **Step 4: Commit** `test(data): offline end-to-end data-analyst smoke test`.

### Task 10: Manual interactive verification (researcher present)

Inline subagent hooks are not exercised by headless runs (see CHANGELOG "Known limitations").

- [ ] **Step 1:** In an interactive `claude` session in the repo, check that `/agents` lists `data-analyst`.
- [ ] **Step 2:** Dispatch `data-analyst` with "Create a data session for 'smoke check', list `vendor/scientific-agent-skills`, then return a blocked handoff explaining no analysis was requested". Expected: a session directory is created, `integrity.json` has `passed: true`, and the handoff validates.
- [ ] **Step 3:** From the main session, ask Claude to run `python3 vendor/scientific-agent-skills/depmap/scripts/depmap_data.py`. Expected: denied by `data_orchestrator_guard.py`.
- [ ] **Step 4:** Record the results in `docs/data-workflow.md` under "Verification log" with the date. Commit `docs(data): record interactive verification`.

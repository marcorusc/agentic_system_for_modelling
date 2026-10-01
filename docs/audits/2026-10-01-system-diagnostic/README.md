# Whole-system code diagnostic — 2026-10-01

## Verdict

The integrated system is ready for the next **publication and controlled client-test
step**, using the tested source revisions. The diagnostic fixed two workflow
blockers and one portability defect. The selected software suites pass, and a fresh
installation starts all four modelling servers successfully.

This is a risk-based code review and software diagnostic, not exhaustive verification
of every implementation line, a new scientific modelling exercise, or proof of live
Claude isolation. The remaining deployment and architecture limits below still
apply. No changes were pushed and no main branch was updated in this step.

## Findings and fixes

| Priority | Finding and consequence | Resolution |
|---|---|---|
| P1 | NeKo, MaBoSS and PhysiCell raised ordinary Python exceptions for expected input/session/backend failures. MCP 2.2 masks them, leaving specialists with generic errors and no useful recovery instructions. The broader bounded baseline had 70 failing protocol tests. | Backend `f0c4a808fd28a3e4a622f64b00b53e18f44ca23e` translates the servers' expected exception classes to `ToolError` at registration. It supports sync/async handlers and preserves schemas, annotations and direct Python calls. All 70 cases now pass. |
| P1 | Claude's mandatory stage-validation workflow referred to `scientific-reviewer` and `reproducibility-auditor`, but neither agent existed. Following that workflow could not complete independent review. | Integration `5d82db1` adds both read-only definitions, with no modelling, write, shell, web or delegation access. They report findings to the orchestrator; they cannot approve a stage. The auditor explicitly distinguishes recorded hashes from independently recomputed hashes. |
| P2 | Claude transport tests assumed the author's environment path and an unconfigured ODE placeholder. A valid setup in a different environment could fail the repository suite. | `5d82db1` verifies transport consistency and server identity instead, and tests generated configuration using another path containing spaces. It also verifies that required reviewers exist and have the read-only tool list. |
| Release prerequisite | Step 3 source setup had only been tested with mocked installation. The source manifest also still pointed to the backend before the error fix. | `ab4a9d9` pins the corrected backend. A fresh, separate environment was built from committed Git snapshots; source receipts, installed bytes, imports, dependency consistency and four-server startup/tool discovery all passed. |

Expected backend exceptions currently mean `ValueError`, `RuntimeError`, `OSError`
and `KeyError`, consistent with these servers' existing error conventions. Other
exceptions remain subject to SDK masking; regressions explicitly check `TypeError`
and `AttributeError` in both protocol modes. This is not a general claim that every
programming mistake is identifiable by its exception class. BioMASS already has
its own guarded registration and did not need this change.

## System assessment

| Area reviewed | Assessment | Boundary that remains |
|---|---|---|
| Dispatcher and shared runtime | Fixed role routing, strict tool schemas, no caller-supplied shell/profile/server override, one modelling worker and at most two literature workers. Technical success requires validation and recording. | It deliberately does not select scientific stages or interpret researcher intent. A technically successful result can still be scientifically blocked. |
| Specialist deployment and context | Fresh ephemeral Codex processes; identical preflight/execution profile transport; apps disabled, bounded MCP inventory, explicit web-search policy, read-only child sandbox. CLI fallback uses the same runtime. | Fresh context prevents conversation-history inheritance. Specialists can still read accessible repository files; this is not an OS-level data compartment. MCP servers are trusted external processes with their own write privileges. |
| Parent/client isolation | Source configuration and regression checks preserve the disabled modelling-server boundary in the Codex parent. | Current desktop tool grants cannot be revoked or fully verified by this repository. Claude inline server isolation and inheritance require a live client inspection. This diagnostic launched no real LLM specialists. |
| Handoffs and capture | Identity, session lineage, allowed paths, hashes and mandatory artifacts are checked. ODE revision/bundle/simulation contracts add representation-specific checks. Capture publication is atomic for cooperating recorders. | Generic artifact checks do not establish biological correctness, all BND/CFG semantics, or approval history. Registry/decision reconciliation remains the orchestrator's responsibility. Atomic publication is not a power-loss or hostile-writer guarantee. |
| Provenance and recovery | Exact task recording, parsed results, sanitized event records, immutable captures, cancellation and restart failure handling preserve inspectable outcomes. Failed tasks are not automatically resumed. | Redaction is pattern-based; prompts and raw invocation records can contain private scientific material. Treat them as project records, not universally safe publication data. |
| Network and Boolean preservation | NeKo preserves exported reference comments on SIF import. MaBoSS keeps per-run inputs, raw outputs and full trajectories with hashes, while retaining its legacy final snapshot. | These preserve evidence/results; they do not validate the biological references or harmonize Boolean and ODE meanings, times or units. |
| ODE workflow | Rich `ode_modeler` route, explicit assumptions, whole-candidate review, provisional/conclusive distinction, capture ownership and matched simulation-revision checks are coherent. | No automatic derivation of reactions from signed edges, calibration, sensitivity analysis or ODE-to-PhysiCell bridge is claimed. |
| Scientific review | Claude now has the agents its validation skill requires. Codex keeps its documented parent-led validation route. | Codex review is not independent of its orchestrator. Claude reviewers' actual tool inventory and execution remain to be tested. Changing review policy requires a separate decision. |
| Lifecycle | Archive/restart/restore code and tests retain scoped state paths, integrity manifests, previews, confirmations and recovery points. | No lifecycle operation was performed on an active project during this review. |
| Setup and dependencies | Both clients can use the same verified source installation. Clean exact commits, committed build snapshots, receipts and recursive-copy guards reduce drift. | Source pins cover two repositories, not every transitive dependency. Default released-package installation does not gain unpublished fixes merely because package versions match. |
| CI and maintainability | Repository tests cover SDK protocol, isolation/configuration, fake child processes, failure paths, artifact capture and lifecycle. Separate SDK CI configuration prevents those tests disappearing behind a missing SDK. | CI was inspected, not run remotely. Optional backend-reader tests need an environment containing the backend; current generic CI does not establish the complete pinned-backend installation. |

### Permissions and efficiency

Keep the approved workflow-sized tasks. A specialist should perform the authorized
construction/inspection/export sequence in one invocation and return durable
artifacts. A later repair can import those artifacts in a fresh session. Persistent
MCP sessions are not needed to solve this orchestration problem.

Tool approval lists constrain available writes, but they are not an independent
record of human consent and do not encode the full scientific scope. The
orchestrator must connect them to explicit researcher decisions. Existing approved
scope should be reused; changing scope or crossing a scientific gate still needs
the corresponding decision. The diagnostic did not add per-equation approval gates
or relax existing scientific policy.

The system uses LLMs effectively for bounded specialist reasoning and uses code for
repeatable integrity checks. More agents would not, by itself, improve this design.
The next useful improvements are less manual completion work and better measurement:

1. A deterministic stage-completion helper that assembles validated capture,
   manifest and state-update proposals for parent review, without granting approval.
2. Per-invocation usage summaries from recorded usage events: input, cached input,
   output, elapsed time, retries and tool calls. Missing usage must remain unknown.
   There is no verified total token/cost figure for the historical conversation.
3. Explicit optional execution deadlines/budgets. Cancellation exists, but a quiet
   child can otherwise continue indefinitely; a heartbeat is not proof of progress.
4. Small role-specific context packages and tests for irrelevant-context leakage.
   Fresh processes alone do not prove that prompts and file reads are minimal.
5. CI for installation from the published backend revisions and their pure contract
   readers, plus a documented live Claude inventory/reviewer acceptance check.

These are follow-up design choices, not silently implemented policy changes.

## Validation and reproducibility

See [machine-readable validation](validation.json), [fresh installation](installation.json)
and the [installed source/file receipt](installed-source-receipt.json).

| Check | Result |
|---|---|
| Repository suites in existing Python 3.14 environment | **375 passed**, no skips: 280 Codex, 21 Claude, 74 setup |
| Same repository suites in fresh Python 3.13.13 source environment | **375 passed**, no skips; repeated validation, not 375 additional distinct cases |
| Backend bounded baseline before fix | 482 passed, **70 failed** |
| Same backend cases after fix | **552 passed** |
| Final backend suite including 28 new registration cases | **580 passed**, 12 upstream pyparsing deprecation warnings |
| NeKo offline reference round-trip tests in fresh environment | **9 passed** |
| Fresh source installation | Exact source receipts and installed-byte checks, `pip check`, imports and all four entry points passed |
| Installed MCP discovery | NeKo 33 tools; MaBoSS 24; PhysiCell 34; BioMASS 22; required capabilities present |
| Source hygiene | Diff checks passed; new backend helper/tests and app modules pass Ruff; source backends clean; original checkouts unchanged |
| Scientific-state boundary | Six source-of-truth files, inputs, runs and evidence have no diff from main; experiment states were not merged |

The source revisions are MCP `f0c4a808fd28a3e4a622f64b00b53e18f44ca23e`
and NeKo `94579ac506aeb87545ca9b709d8c5fc316a9f552`.
The separate test environment is `/tmp/biomodelling-diagnostic-20261001/environment`.
No shared environment or client configuration was changed. The saved
[dependency resolution](resolved-requirements.txt) is an audit snapshot, not a
portable lockfile: source URLs refer to temporary committed build snapshots.

Reproduce the project suites from the integration root with the selected environment's
Python using `python -B scripts/run_tests.py` and `PYTHONDONTWRITEBYTECODE=1`.
For the backend diagnostic, use its development environment from the backend root:

```sh
MPLBACKEND=Agg PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider tests \
  --ignore=tests/test_biomass_workflow.py \
  --ignore=tests/test_biomass_editing.py \
  --ignore=tests/test_biomass_authoring_resources.py
```

This selection is **not the full backend suite**. The first broad attempt excluded
only workflow/editing files and inadvertently included real BioMASS generation and
simulation documentation fixtures in `test_biomass_authoring_resources.py`. That
run completed with 509 passes and 70 failures before the selection was corrected.
It used temporary fixtures and changed no project scientific state. Subsequent
backend runs exclude all three files. Fresh installation verification only used
MCP initialization and tool discovery, never a modelling tool call.

Logs: [existing-environment project](project-tests.log),
[fresh-environment project](fresh-project-tests.log),
[backend](backend-tests.log), [NeKo](neko-tests.log), and
[pre-fix failed cases](baseline-failures.txt). Historical failed results have not
been relabelled as passes. No remote CI, Python/client matrix, new live specialist
isolation test, or biological validation is claimed.

## Next step and branch disposition

1. Publish the reviewed dedicated backend branches so the exact commits can be
   obtained by another checkout. Preserve their original source branches.
2. Publish the architecture integration branch and update this project's main from
   that reviewed code. Keep `model/cell-cycle-core` and
   `model/cell-cycle-dispatcher-smoke` as separate experiments; do not merge their
   active model records into main.
3. For the planned Claude test, install the pinned sources into a dedicated
   environment and configure Claude for it with BioMASS enabled. The checked-in
   source manifest assumes sibling worktree paths; adjust local paths while
   preserving the exact commits if using another layout.
4. First inspect live parent/specialist inventories and invoke the two reviewers on
   bounded existing artifacts. Then perform the user's modelling test. Report
   client failures separately from scientific outcomes.
5. A conventional package release can later replace local-source installation once
   the preservation and error-contract fixes are actually published in its contents.

The diagnostic is complete. Publication and the live Claude test are the next
steps; neither is represented as completed here.

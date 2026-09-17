# Audit validation and reproducibility

Date: 2026-09-17. Baseline commit: `d5316cedd5d5ed566684a4408a46b5d31706fd22`.
These checks inspect infrastructure and saved results; no scientific model was created, mutated or rerun for the audit.

## Current regression results

| Environment / check | Result | Interpretation |
|---|---|---|
| Default Python 3.14.4, `python3 scripts/run_tests.py` | Exit 0: Codex 134 discovered, 129 passed, 5 skipped; Claude 19 passed; setup 27 passed | 175 passed, 5 SDK-dependent tests skipped; not a complete SDK-enabled pass |
| Modelling environment Python 3.14.6, MCP SDK 2.0.0, same runner | Stopped with Ctrl-C after progress ceased following `test_calls_and_validation_errors` | Incomplete suite; no current full-SDK pass claimed |
| Same SDK environment, that single test, 35-second timeout and traceback at 20 seconds | Test assertion result `ok`, then timeout exit 124 | Reproduced stall during asynchronous runner teardown, after assertions |

The [single-test output](sdk-test-stall.txt) places the wait in `asyncio.runners.Runner.close`, invoked by `unittest.IsolatedAsyncioTestCase._tearDownAsyncioRunner`. This localizes the symptom. It does not prove whether the cause is repository lifecycle code, MCP SDK background tasks, Python/environment behaviour, or their interaction. It also does not establish that ordinary modelling runs suffer the same teardown defect.

Reproduction from the repository root:

```bash
timeout 35s /home/marcorusc/miniforge3/envs/mcp_modelling/bin/python - <<'PY'
import faulthandler, sys, unittest
faulthandler.dump_traceback_later(20)
sys.path.insert(0, 'tests/codex')
suite = unittest.defaultTestLoader.loadTestsFromName(
    'test_dispatcher_server.ServerTests.test_calls_and_validation_errors'
)
result = unittest.TextTestRunner(verbosity=2).run(suite)
faulthandler.cancel_dump_traceback_later()
raise SystemExit(not result.wasSuccessful())
PY
```

Earlier passing phase and ODE validation records remain unchanged. They used earlier runtime snapshots, and cannot replace the current result. No runtime repair was attempted in this audit.

## Native helper startup

A native collaboration helper requested for independent read-only software review failed before work began:

```text
Fatal error: Failed to initialize session: required MCP servers failed to initialize:
specialist_dispatcher: handshaking with MCP server failed: connection closed:
initialize response: connection closed: initialize response
```

A nonblocking read-only lock probe confirmed `.dispatcher/manager.lock` was held by another process. `TaskManager.__init__` rejects a second owner. A competing startup is therefore a plausible diagnosis, not a confirmed root cause from the generic error. No scientific child was launched to investigate it and no dispatcher owner was interrupted.

## Metrics checks

- Unique invocation IDs: 49; no duplicate provenance record accepted.
- Numeric usage events: 42; missing usage remains unestimated.
- JSONL parse failures in scanned final invocation streams: 0.
- Dispatcher task records: 42; 39 succeeded technically, 2 cancelled, 1 failed.
- Cached-input counters remain a subset of input; reasoning-output counters are not added again.
- The collector saves paths and hashes, never raw prompt or reasoning text.
- Serialized tool-result character counts describe saved JSON representations, not unique content or billed tokens.
- Simulation-call durations come from paired operational event timestamps and exclude model preparation/reporting.

## Repository integrity

The audit adds documentation, a metrics collector and its output, and this test evidence only. Existing untracked network/probe artifacts, logs and the Windows Zone.Identifier file were left intact. No scientific source-of-truth file, architecture code, installed profile or model artifact was changed.

The task-cleanup preview checked 190 records and found no verified leftovers or unmatched task prompts; no deletion was performed. Report links, metrics arithmetic and audit-file hashes were checked. See [artifact-hashes.json](artifact-hashes.json) for this package's file digests.

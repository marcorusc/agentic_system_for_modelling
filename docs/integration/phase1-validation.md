# Phase 1 — reliable integration baseline

Date: 2026-09-17. Branch: `codex/modelling-architecture-integration`.
Starting commit: `9ea06e7` (prepared integration worktree).

## Scope and authorization

The researcher approved Phase 1: port the heartbeat-test fix, diagnose the asynchronous shutdown stall, verify the baseline and create one implementation commit. Python/MCP dependency changes were reserved for a separate discussion. Phase 2 and its policy/contract choices remain pending.

## Changes

- Port the heartbeat synchronization from experiment commit `4583c0ce3f77b2c79f82c9b6f139e1e51602f645`. A heartbeat may precede the tool-start event, so wait for both before asserting the current activity and testing cancellation. Improve the deadline failure message.
- Bound each regression suite to 120 seconds. A timeout is a failure, even if individual tests already printed `ok`; run the remaining suites and return a nonzero overall status. On POSIX, terminate the suite's process group to stop fixtures that inherit that group as well. Other platforms terminate the direct suite process.
- Add regressions for process-group targeting and a real stalled subprocess suite followed by a healthy suite. Preserve failure propagation and minimum-Python checks.

## Shutdown diagnosis

The earlier audit correctly recorded a stalled SDK test but could not attribute it. This investigation narrows the observed failure to the execution sandbox. It does **not** establish an SDK or dispatcher shutdown defect.

The following minimal test imports neither MCP nor repository code:

```python
import asyncio
import logging
import unittest

logging.basicConfig(level=logging.DEBUG)

class ShutdownTest(unittest.IsolatedAsyncioTestCase):
    async def test_thread(self):
        self.assertEqual(await asyncio.to_thread(lambda: 1), 1)

unittest.main(verbosity=2)
```

Run this under a shell timeout. In the restricted environment, it prints `ok` and stalls during runner teardown. Debug logging identifies the failed wake-up operation in `asyncio/selector_events.py`, `_write_to_self`:

```text
DEBUG:asyncio:Fail to write a null byte into the self-pipe socket
    csock.send(b'\0')
PermissionError: [Errno 1] Operation not permitted
```

The minimal stall reproduced under Python 3.14.4 and 3.14.6. The debug reproduction exited with shell timeout status 124 after eight seconds. With Python 3.14.6 outside the socket-restricted sandbox, the same minimal test passed and exited normally (one test, 0.031 seconds).

A diagnostic timer also found the runner waiting on `shutdown_default_executor`, with its future already finished; allowing the event loop to wake let teardown finish. This diagnostic was temporary, not added as a runtime workaround.

The unchanged SDK protocol tests then passed outside the restricted sandbox: four tests in 1.971 seconds, including a real stdio client/server disconnect and lease reacquisition. No scientific MCP service was invoked. The fixture's missing-profile failures are intentional negative tests.

**Resolution:** run SDK protocol checks in an environment that permits Python's local wake-up socket, and bound the test job. Preserve the dispatcher lifecycle code and installed versions. Do not bypass specialist isolation or scientific approval gates to address this test-environment limitation.

## Validation

| Environment | Codex | Claude | Setup | Total | Process exit |
|---|---:|---:|---:|---:|---:|
| Default Python 3.14.4, no MCP SDK, restricted sandbox | 127 passed, 4 skipped | 19 passed | 26 passed | 172 passed, 4 skipped | 0 |
| Existing modelling Python 3.14.6, MCP 2.0.0, AnyIO 4.14.2, outside socket restriction | 131 passed | 19 passed | 26 passed | 176 passed, 0 skipped | 0 |

Commands, from the integration worktree:

```text
python3 -B scripts/run_tests.py
/home/marcorusc/miniforge3/envs/mcp_modelling/bin/python -B scripts/run_tests.py
```

Both commands were additionally wrapped in a 150-second shell timeout for this investigation. The production runner's per-suite timeout is 120 seconds. Focused heartbeat/integration tests (four), test-runner tests (five), and SDK protocol tests (four) also passed. The intentional stalled-suite regression uses a three-second limit and confirms a subsequent suite executes.

The four skips in the default environment are the existing SDK protocol tests: tool schemas, invalid calls, queryable worker failure, and stdio disconnect. They are all executed in the SDK run. The nested one-test healthy fixture printed by the timeout regression is not an additional repository test in these totals.

See [machine-readable results](phase1-validation.json). Full local logs are identified there with hashes; they are temporary diagnostic files, not packaged evidence. The committed counts, environment and reproduction above are the durable record.

## Preserved boundaries and remaining limits

- All six scientific-state hashes match the preparation receipt and dispatcher baseline. Model directories contain only `.gitkeep`.
- The original experiment remains on `model/cell-cycle-core` at `8f0e0af6efb02f363b39449f7136847611070af5`, with no tracked diff.
- No dispatcher/runtime, routing, `.codex/`, `.claude/`, dependency requirement or global profile changes. No packages installed or scientific sessions created.
- These are software/protocol fixture results, not live specialist inventory or biological-model validation. The existing CI matrix for Python 3.11/3.13 was not executed locally; no remote CI run is claimed.
- Native Windows timeout cleanup stops the direct suite process; POSIX process-group cleanup is the path verified here. A fixture that deliberately creates a separate process group, such as the SDK stdio launcher, is outside this timeout signal; normal SDK disconnect cleanup passed, but forced-timeout cleanup of detached fixtures is not established by this phase. A sandbox that denies local wake-up sockets still cannot reliably run these asyncio protocol tests.
- Phase 2 contract names, historical compatibility and provisional bundle policy still require discussion.

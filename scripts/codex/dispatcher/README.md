# Specialist dispatcher (local stdio)

This package provides a technical MCP interface to the existing isolated runtime.
It does not read or update scientific state or select stages. See
[architecture and migration gates](../../../docs/specialist-dispatcher.md).

Requires Linux/WSL, Python 3.11+, and the official MCP SDK 2.x. Reuse a compatible
existing environment or install `requirements.txt` into a dedicated environment.
Run from the project root:

```sh
python -m scripts.codex.dispatcher.server
```

The entry point uses stdio only and binds no network port. Its stdout is reserved
for MCP; launcher diagnostics go to stderr. The process uses existing user-local
specialist profiles and Codex executable resolution. The Windows CLI bridge stays
available; the dispatcher itself runs inside WSL.

Tools:

- `start_network_curator(task, record_session_id?, approved_tools?)`
- `start_literature_reviewer(task, record_session_id?, allow_web_search?, review_kind="edge")`
- `start_boolean_dynamics_modeler(task, record_session_id?, approved_tools?)`
- `start_multicellular_configurator(task, record_session_id?, approved_tools?)`
- `start_ode_modeler(task, record_session_id?, approved_tools?)`
- `get_specialist_task(task_id)`
- `get_specialist_events(task_id, after_sequence=0, limit=50)`
- `list_specialist_tasks(limit=50)`
- `cancel_specialist_task(task_id)`

Unknown arguments and tool names are rejected. A task ID identifies operational
execution; it is not a scientific session ID. Start calls return before child
execution. Use the event cursor until a terminal execution state is reached.
Only `succeeded` carries a validated handoff; inspect its independent scientific
status before considering any next stage.

One manager can own a project's `.dispatcher/` directory. On disconnect, it asks
workers to stop. Restart marks interrupted tasks failed without rerunning them.
It never deletes scientific sessions. Preserve `.dispatcher/` and the referenced
invocation directories when troubleshooting. A failed task may have useful partial
artifacts but cannot authorize a downstream stage.

Run `python scripts/run_tests.py` with the SDK installed to include real MCP client
and stdio tests. The stdlib-only job skips protocol tests; a separate CI job
installs the SDK and runs the full suite. Real model calls are never part of CI.
The runner fails a suite after 120 seconds and continues the remaining suites.
If a protocol test prints `ok` but hangs during shutdown, check whether the host
sandbox denies Python's local asyncio wake-up socket. A minimal reproduction and
the verified environment are in the [integration baseline report](../../../docs/integration/phase1-validation.md).
Individual `ok` lines do not establish successful process termination.

The live isolation and equivalence gate passed in Phase 4. Phase 5 routes
specialist work through this dispatcher; `scripts/codex/run_specialist.py` remains
the supported fallback/debug interface. Scientific approval gates are unchanged.
Phases 6–7 verified same-conversation
progress and a real 60-gene construction in this WSL workspace. The parent verified
and persisted its review artifacts; biological approval remains pending. See
[troubleshooting and recovery](../../../docs/specialist-dispatcher.md#troubleshooting-and-recovery).

## ODE integration route

Integration Phase 3 adds `start_ode_modeler` through the same runtime as the CLI.
It uses the fixed `biomodel-ode-modeler` profile and permits only BioMASS. The
profile must already exist; missing configuration fails before child execution.
The other specialists disable BioMASS, including installations without an optional
BioMASS transport. No additional scientific workflow is activated by this endpoint.
Profile/skill/setup integration is Phase 4 work; the original dispatcher's live
migration checks above are historical and do not establish live ODE readiness.

Literature review defaults to `review_kind="edge"`. Use `review_kind="ode"` for
bounded mechanism, kinetic-law and quantity claims, together with the BioMASS
`record_session_id`. Both modes use the same literature profile, no modelling
servers, and the same shared limit of two reviewers. PubMed is preferred; web
search requires explicit authorization. Without either backend, the runtime
returns a recorded scientific `blocked` result without starting a child.
A handoff with the wrong review kind or session is rejected.

The CLI equivalent accepts `--review-kind ode --record-session-id <session>`
for `literature_reviewer`; the Windows-to-WSL bridge forwards both arguments.
Other roles reject `--review-kind`. Technical records retain the requested mode
and session even if preflight fails. ODE review invocations use `runs/ode-modeler/`;
edge review invocations retain `runs/network-curator/`. Evidence reports keep
their contract-defined locations under `evidence/reports/`.

See the [ODE contract](../../../docs/ode-contract.md) and
[Phase 3 validation](../../../docs/integration/phase3-validation.md) for the
software test coverage and remaining live-verification limits.

## Workstation startup

The project MCP entry invokes `launch.py` from the project root. That small
bootstrap replaces itself with the SDK interpreter; it does not wrap specialist
execution. It uses existing `.setup/local.json` settings (`env_prefix` and
`codex_home`). Explicit overrides can be placed in ignored
`.setup/dispatcher.local.json`, using `.codex/dispatcher.example.json` as a template.
No workstation path is committed. A configured native Codex home takes precedence
over an inherited Windows home for this server process and all of its children.

Root configuration keeps NeKo, MaBoSS, PhysiCell, and the discovered optional
BioMASS server disabled. Specialist command overrides disable the dispatcher and
built-in app connectors, preventing either from expanding a specialist's MCP
inventory. This is applied to both the inventory check and child execution.

Rollback: set `mcp_servers.specialist_dispatcher.enabled=false` in the project
configuration, retain disabled modelling servers, and use the existing CLI.
Do not delete profiles, tasks, sessions, or invocation artifacts to roll back.

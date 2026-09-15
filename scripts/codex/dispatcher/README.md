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
- `start_literature_reviewer(task, record_session_id?, allow_web_search?)`
- `start_boolean_dynamics_modeler(task, record_session_id?, approved_tools?)`
- `start_multicellular_configurator(task, record_session_id?, approved_tools?)`
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

The live isolation and equivalence gate passed in Phase 4. Phase 5 routes
specialist work through this dispatcher; `scripts/codex/run_specialist.py` remains
the supported fallback/debug interface. Scientific approval gates are unchanged.

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

# Specialist dispatcher migration

## Phase 0 — baseline (2026-09-15)

Implementation follows the supplied **Specialist Dispatcher Architecture** plan,
sequentially. Orchestrator routing may change only after Phase 4 isolation and
equivalence checks pass. Each completed phase receives its own commit.

- Starting commit: `dfee97fd46581fbcf4561a7e089ea5ab3e62b048` on `main`.
- Working branch: `codex/specialist-dispatcher`.
- Unrelated untracked files preserved: `inputs/287D_PS_stats.txt:Zone.Identifier`,
  `pypath_log/`, and `runs/network-curator/`.
- Baseline: `python3 scripts/run_tests.py` passed 100 Codex, 19 Claude, and
  26 setup tests (145 total).
- Required runtime: Python 3.11+, Codex CLI 0.153.0+.
- Inspected environment: Python 3.14.4, Codex CLI 0.154.0; the default Python
  interpreter does not have the MCP SDK installed.
- Reviewed launcher, configuration, provenance, streaming, profile examples,
  plugin manifest, launcher documentation, and regression suite.
- Plugin currently contributes skills only; it bundles no MCP transports.
- Root configuration disables NeKo, MaBoSS, and PhysiCell with inert transports.

## Preserved launcher invariants

Every invocation creates a fresh `codex exec --ephemeral` process with a bounded
task, a fixed specialist profile, and a read-only sandbox. There is no resumption
or forwarding of orchestrator history or other specialist transcripts.

The same resolved executable, environment, working directory, profile transport,
and fixed MCP overrides are used for inventory preflight and execution. Unexpected
enabled servers fail closed. Each modelling role gets exactly its own server;
literature gets an approved backend and no modelling server. Exact tool approvals
remain scoped to the permitted server; destructive tools stay disabled.

JSONL events retain existing redaction and malformed-event checks. A zero process
exit alone is insufficient: identity, lineage, typed handoff validation, and
provenance recording must pass. Scientific handoff status remains distinct from
technical execution state.

Artifacts remain under `runs/<specialist>/<session>/specialist-invocations/`,
with `_launcher-runs` staging. The CLI and Windows-to-WSL bridge remain supported.
Disposable task-file cleanup remains available for the CLI fallback.

## Migration gates

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Baseline and invariants | Passed |
| 1 | Shared runtime, unchanged CLI protections | Pending |
| 2 | Persistent task manager and fake-worker tests | Pending |
| 3 | Local MCP server and protocol tests | Pending |
| 4 | Root isolation, live specialist smoke tests, CLI equivalence | Pending |
| 5 | Orchestrator and skill routing | Gated on Phase 4 |
| 6 | Same-conversation ChatGPT observability | Pending |
| 7 | Bounded real scientific operation | Pending |
| 8 | Cleanup and preferred-path documentation | Gated on real operation |

No scientific state, scientific policy, Claude implementation, or routing changes
are part of Phase 0.

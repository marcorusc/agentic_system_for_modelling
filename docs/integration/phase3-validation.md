# Phase 3 — shared ODE execution route

Completed on 2026-09-18 under the researcher's approval to add `start_ode_modeler`,
transport ODE evidence mode through the shared runtime, and test isolation and CLI
equivalence before activating orchestrator routing. Starting commit:
`038dd134d50b0f191596bd2f5d3151ca98b8562f`.

## Implemented behavior

- `start_ode_modeler` uses the existing shared runtime, fixed
  `biomodel-ode-modeler` profile and BioMASS-only MCP inventory. Apps and dispatcher
  access remain mechanically disabled. Unexpected enabled servers fail preflight.
- Literature review accepts explicit `review_kind=ode` with a required BioMASS
  session ID. Existing requests default to `edge`. Validation checks the returned
  mode and session. CLI and Windows-to-WSL arguments carry the same mode.
- ODE evidence invocations are recorded under `runs/ode-modeler/`; edge evidence
  retains `runs/network-curator/`. Task records and provenance preserve the selected
  mode; provenance also retains the requested session on early failure/cancellation.
- The shared one-modelling-worker and two-literature-worker limits remain in force.
  ODE evidence and edge evidence share the literature limit. Cancellation/restart
  never authorize automatic model mutation or resumption.
- BioMASS remains optional for existing roles. Setup explicitly retains its four
  supported profiles until Phase 4 adds optional ODE profiles and dependencies.

## Verification results

| Environment | Codex | Claude | Setup | Total |
|---|---:|---:|---:|---:|
| Existing MCP SDK environment | 245 passed | 19 passed | 27 passed | **291 passed** |
| Default Python, no MCP SDK | 240 passed, 5 skipped | 19 passed | 27 passed | **286 passed, 5 skipped** |

Both complete processes exited 0. The common runner bounds each suite to 120
seconds; the outer command was bounded to 180 seconds. The SDK run used the
previously verified environment outside the sandbox that blocks asyncio wake-up
sockets. No packages or dependency versions changed. See the [machine-readable
record](phase3-validation.json) for versions, timings, temporary log paths and hashes.

Coverage includes:

- Real MCP SDK stdio discovery of all nine tools, strict schemas, start/query/event/
  list/cancel requests, mode forwarding and clean disconnect. Public callers cannot
  supply arbitrary executables, profiles or transport settings.
- Fixture inventory isolation for all five roles, enabled-server aliases, duplicate
  or malformed inventories, missing permitted servers, and prohibited BioMASS in
  every other specialist. Preflight and execution use identical transport overrides.
- Actual fake-Codex child processes through both CLI and dispatcher for every role,
  edge review, ODE review with PubMed, and authorized web search. Tests compare fixed
  profiles, commands, exact task text, effective inventory and provenance; invocation
  IDs remain distinct. These children never connect to modelling servers or an LLM.
- Complete synthetic ODE artifacts, a provisional bundle awaiting scientific
  approval, and a completed ODE claim report survive validation and recording.
  Wrong role/session/review mode, old ODE contract version, tampered artifacts,
  malformed JSONL, nonzero exit and recording failure cannot publish success.
- ODE and ODE evidence child cancellation, missing-profile and early-cancellation
  provenance, no-backend literature blockers, and PubMed preference over authorized
  search. Backendless review records a scientific blocker without starting a child.
- Windows-to-WSL argument construction and CLI forwarding; no Windows process was
  executed. Existing Claude and setup tests still pass.

## Findings fixed during integration

1. Credential redaction erased `standalone_authorized` and
   `workflow_authorization`, rejecting valid ODE results. It now recognizes the
   typed public boolean and decision snapshot, while recursively redacting
   credentials. Paths with spaces and extra public metadata remain compatible with
   the accepted artifact contract. Malformed credential-bearing values are redacted.
2. Early CLI failures lost the requested scientific session because only the
   dispatcher registry retained it. Every provenance branch now records
   `record_session_id` alongside `review_kind`.
3. The first full run exposed three setup failures: iterating the enlarged runtime
   role registry implicitly required an ODE template before Phase 4. Setup now has
   an explicit supported-role list. A regression test verifies it does not install
   or rewrite an existing optional ODE profile. Both full suites were rerun.

An independent software reviewer reproduced the provenance and sanitizer-contract
issues, then verified all six focused reproduction checks after the fixes. Two
software agents implemented separate launcher and dispatcher changes. An additional
reviewer launch failed during the required dispatcher MCP handshake; review was
completed by reusing an existing software agent. That host/client startup failure
was not diagnosed or claimed fixed by these runtime tests.

## Scope and limits

The six scientific state files still match the preparation hashes; `runs/`,
`evidence/` and `inputs/` contain only their placeholders. The original experiment
remains on `model/cell-cycle-core` at `8f0e0af` with no tracked changes. No scientific
session, model, data or scientific decision was created by this phase.

Orchestrator instructions, skill routing, specialist profiles, installed plugin
configuration and global settings remain unchanged. A missing ODE profile fails
closed. This phase verifies software boundaries with fixtures and the MCP protocol;
it does **not** establish live BioMASS startup, actual LLM tool visibility/context
isolation, modelling capability, biological validity or Windows deployment.
Usage/token telemetry and broader retrospective recovery/permission work remain
separately scoped. No remote CI was run.

Phase 4 discussion is next: richer ODE skills and references, Codex/Claude
integration, optional setup, and capability checks. ODE orchestrator activation
must retain the applicable isolation gates; Phase 5 supplies combined verification.

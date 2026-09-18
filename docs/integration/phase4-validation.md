# Phase 4 validation — ODE skills, profiles and optional setup

Completed on 2026-09-18 under the researcher's approval to proceed with Phase 4.
The integration branch is `codex/modelling-architecture-integration`, starting at
`9c335b56f125e819c6fde1a4640f26f8f0f1016c`. The pinned feature source remains
`1e8f9a43c4fc249e43d94c71316fc798ee7ad01d`.

## Result

The richer `ode_modeler` workflow now has Codex and Claude definitions, a shared
BioMASS skill, local authoring references and optional setup support. Live ODE
activation still requires Phase 5 deployment and isolation verification. The
original experiment and the six scientific state files are unchanged.

- Three input routes remain explicit: exported NeKo graph, standalone Text2Model,
  and bounded reaction construction.
- ODE claims use the existing isolated literature role with `review_kind=ode`;
  edge review remains the default. Claude's guarded report writes check the same
  claim content and destination contract.
- Provisional server bundles can be preserved within the authorized workflow.
  A read-only specialist returns metadata-only `pending`; the parent verifies
  captures and creates a separate provisional completion. Actual scientific
  acceptance and conclusive export retain their exact revision approval gates.
- Optional `--with-biomass` adds the ODE profile and actual capability checks.
  `--environment-mode reuse` verifies an existing environment without installing
  into it. The package pin and default non-ODE setup remain unchanged.
- Custom Graphviz locations are saved explicitly. Profiles do not inherit the
  calling IDE's entire PATH. App connectors, the dispatcher and other modelling
  domains remain disabled in specialist definitions.

## Verification

| Environment | Codex | Claude | Setup | Total |
|---|---:|---:|---:|---:|
| Existing MCP SDK | 257 passed | 19 passed | 59 passed | **335 passed** |
| Default Python, no MCP SDK | 252 passed, 5 skipped | 19 passed | 58 passed, 1 skipped | **329 passed, 6 skipped** |

Both full jobs exited 0. Five default skips are the existing official-SDK dispatcher
protocol tests; the sixth is the new real SDK teardown test against a disposable
fake JSON-RPC server. The SDK environment ran every test. It used Python 3.14.6,
MCP 2.0.0 and AnyIO 4.14.2 outside the known restrictive asyncio sandbox; default
Python 3.14.4 ran under the sandbox. No package or dependency version changed.

After the full suites, the final technical-recording wording passed all 18 profile
and setup migration tests. Plugin validation and all 11 changed skill validations
passed. Two pre-existing Claude skill headers lacked explicit names; these were
added and revalidated. `git diff --check` passed. Exact timings, temporary log hashes,
source-reference hashes and preservation checks are in the
[machine-readable report](phase4-validation.json).

### Review findings fixed

1. An unsafe literature inventory did not previously fail overall readiness. It
   now fails; a safely isolated reviewer without a search backend is degraded.
2. Optional setup initially started servers both before and after configuration.
   It now reuses the same verified capability report within that setup invocation.
3. The MCP SDK starts stdio servers in separate sessions. A probe timeout could
   leave one alive even after killing the probe's process group. The whole-probe
   deadline now permits SDK cleanup first. The Linux fallback snapshots owned
   descendants and checks PID birth identity before stopping them. Tests cover a
   detached server and helper, an unrelated process, PID reuse and actual SDK
   teardown of an endless paginated tools/list fixture.
4. Stable server PATH initially discarded valid nonstandard Graphviz directories.
   Setup now records the chosen `dot` entry point and preserves its directory,
   including symlinks to differently named binaries. Tests verify both generated
   clients and reuse from a later shell.
5. An installed ODE profile could retain the source branch's blanket final-export
   rule alongside new provisional guidance. Migration replaces that exact known
   sentence, retains unrelated settings, and reports recognizable unfamiliar
   restrictions. A byte-verified source fixture and idempotence tests cover it.
6. The workflow initially described a provisional result before local capture,
   which the artifact validator correctly rejects. Instructions now distinguish
   the intermediate metadata-only result and separate parent completion. Existing
   authority is bound to the returned session without a forced bootstrap turn.
   Because the current envelope requires `decisions_required` for `needs_approval`,
   technical recording is explicitly labelled there and is not sent to the
   researcher as another scientific approval request.
7. Capability checks now include session creation and the dedicated NeKo-to-BioMASS
   export. Missing capabilities fail before optional configuration writes.

### Independent forward walkthrough

An independent software reviewer exercised the current validator and fake runtime
with temporary fixtures for three cases:

| Case | Verified outcome |
|---|---|
| New NeKo-derived whole-model candidate | Complete authorized server workflow; valid metadata-only result; separately valid captured provisional completion |
| Existing authorized candidate snapshot | Captured files can be verified without simulation or an assumed live session; a later correction uses authorized fresh reconstruction |
| ODE claims with no permitted search backend | Dispatcher succeeds technically with scientific `blocked`; no specialist process or evidence report |

The exercise reproduced and resolved the empty `decisions_required` rejection.
It did not run a scientific model or use a live LLM specialist. New native review
agents encountered a required-dispatcher handshake failure, so independent reviews
used existing software agents; this does not establish deployment readiness.

## Preservation and limits

All ten reference files across the two clients match the pinned source byte for
byte. The six scientific files match preparation hashes; `runs/`, `inputs/` and
`evidence/` contain only `.gitkeep`. The experiment remains on `model/cell-cycle-core`
at `8f0e0af6efb02f363b39449f7136847611070af5` with no tracked diff.

The source plugin version is `0.1.0+codex.20260918022344`; its manifest and existing
marketplace were validated. No installed plugin, global profile, package environment
or scientific session was changed. The parent configuration still disables all
four modelling servers. The current desktop dispatcher still belongs to the
original experiment checkout.

Claude's missing independent scientific reviewer/auditor definitions remain a
stage-validation blocker. Its pre-tool report guard is not atomic with the later
Write call; readback and nonoverlapping claim ownership remain necessary. Process
cleanup covers still-owned Linux descendants, not arbitrary orphaned daemons or
an operating-system sandbox. Setup's capability probes do not prove an LLM's actual
tool inventory, client authentication or scientific correctness.

## Next discussion

Phase 5 should verify deployment and actual isolated contexts for this worktree,
then exercise bounded software fixtures and artifact reproduction. Separate
capability inventory, live context isolation, and execution results in its report.
Choose the client scope and temporary configuration strategy before changing an
installed environment. Broader telemetry, durable finalization and independent
scientific-review roles remain separately scoped retrospective work.

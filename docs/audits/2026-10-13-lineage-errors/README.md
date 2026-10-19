# Boolean lineage and error-handling follow-up — 2026-10-13

The researcher requested discussion and resolution of the two Wave 1 limitations,
then explicitly approved: **"Implement the versioned lineage extension; retain
support for existing v1 handoffs."** Remaining Wave 2 capabilities are not included.

## Changes and commits

| Repository | Commit | Change |
|---|---|---|
| MCP servers, `codex/wave1-shared-infrastructure` | `7dc31cd` | Explicit masking of unexpected non-domain failures in the shared tool wrapper |
| MCP servers, same branch | `ecc1ac9` | Portable v2 Boolean source ancestry, v1 compatibility and NeKo/MaBoSS/PhysiCell propagation |
| Agentic system, existing `model/toy-cell-cycle` branch | `139be87` | Explicit artifact roots, portable capture and exact-revision v2 gates |

Each implementation commit has a detailed rationale, scope and validation message.
The final improvement-plan/audit update is a separate documentation commit.
The MCP worktree remains `/tmp/agentic-wave1-20261013/mcp`; its commits persist on
the named branch in the original repository. Nothing was merged, pushed,
published or installed in clients.

The eight pre-existing error-masking failures now pass. NeKo, MaBoSS and PhysiCell
return generic messages for unexpected non-domain exceptions while retaining
tracebacks in server logs. Expected domain failures, explicit ToolError/MCPError,
successful structured results and cancellation retain their behavior. BioMASS's
separate registration wrapper was outside this repair.

V2 separates source ancestry from the accepted stage parent. Imports snapshot exact
source/ancestor bytes and original parent JSON with verified ownership, membership,
relationships, hashes and bounded traversal. Copied history remains verifiable
after original files disappear. Initial imports still require valid live parent
paths; saved history never grants approval of a changed model. Current-stage
node/output constraints and exact-revision researcher approval remain enforced.

Capture preserves original snapshots and adds digest-addressed files inside
existing `runs/` lifecycle paths. It accepts explicit per-server cache roots while
retaining the legacy installation-root option. V2 metadata validation uses the
pure backend reader, with the existing configured Python available to system-Python
hooks. No modelling server is started by that validation. An old/unavailable
contract package fails explicitly until the feature is installed.

## Validation

| Check | Result | Evidence |
|---|---|---|
| Initial masking fix plus server error/schema/initialization suites | 398 passed, 12 existing warnings | [log](masking-tests.log) |
| Final affected MCP suite, including masking and v1/v2 lineage | 632 passed, 12 existing pyMaBoSS warnings | [log](mcp-tests.log) |
| Complete `tests/codex` repository suite against new pure contracts | 353 passed, 688 subtests passed | [log](agentic-tests.log) |
| Independent review | One P2 finding, resolved before final tests | [original review](independent-review.md) |
| Preservation | Eight pristine templates; original checkout heads/statuses and archive unchanged | [record](verification.json) |

The independent review found that digest reuse could hide a missing/changed live
typed-parent artifact during an initial byte-identical import. `_Evidence.read`
now verifies declared live paths even when identical bytes were already cached.
Six regressions cover v1/v2 parents with missing, modified or outside-root BNETs.
Existing capture-then-delete-originals tests still pass. The review report is an
unaltered snapshot from before that fix and references an intermediate log; the
final logs above supersede those intermediate test counts.

Integration also caught and resolved v1 response serialization adding an unwanted
null field, changed stale-parent diagnostics, and recursive v2 capture validation
following final paths before atomic publication. Capture now validates a temporary
parent against staged payloads and publishes manifests with final paths/hashes.

Tests use synthetic fixtures and offline backend stubs. They do not initialize the
archived cell-cycle model, call scientific MCP tools, or establish scientific
validity. Protocol tests ran with normal asyncio outside the socketpair-restricted
sandbox and `MPLBACKEND=Agg`. No selector workaround was used for acceptance.
Installed modelling dependencies were unchanged; temporary pytest dependencies
were reused from Wave 1. The full engine-heavy MCP suite and live benchmark were
not rerun. ODE ancestry and other Wave 2 feature work remain outside this follow-up.

## Reproduction

Python: `/home/marcorusc/miniforge3/envs/mcp_modelling/bin/python`.

From the MCP worktree:

```bash
MPLBACKEND=Agg PYTHONPATH=/tmp/agentic-wave1-20261013/test-deps \
  timeout -k 5 90 /home/marcorusc/miniforge3/envs/mcp_modelling/bin/python \
  -m pytest -q --tb=short \
  tests/test_artifact_manager.py tests/test_shared_foundation.py \
  tests/test_source_import_handlers.py tests/test_import_record_persistence.py \
  tests/test_handoff_contracts.py tests/test_neko_session_manager.py \
  tests/test_maboss_session_manager.py tests/test_physicell_session_manager.py \
  tests/test_cross_server_output_schemas.py tests/test_neko_mcp_errors.py \
  tests/test_maboss_mcp_errors.py tests/test_physicell_mcp_errors.py \
  tests/test_physicell_concurrency.py tests/test_server_initialization.py \
  tests/test_maboss_preservation.py tests/test_tool_registration.py \
  tests/test_boolean_lineage_v2.py
```

From the agentic repository, expose only the MCP contract package on the test
import path. The temporary `contract-overlay/mcp_biomodelling_servers` symlink
points to the feature worktree's package. This avoids the MCP repository's `tests`
package shadowing this repository's namespace test package; the initial broad
import path caused four collection errors, not code failures.

```bash
MPLBACKEND=Agg \
PYTHONPATH=/tmp/agentic-wave1-20261013/contract-overlay:/tmp/agentic-wave1-20261013/test-deps \
  timeout -k 5 120 /home/marcorusc/miniforge3/envs/mcp_modelling/bin/python \
  -m pytest -q --tb=short tests/codex
```

The configured-interpreter regression exercises the same validator through a
subprocess, as a system-Python hook would, without starting any MCP server.
The lifecycle allowlist already includes `runs/`; no lifecycle policy or archive
format change was needed. The existing archive still points to
`badb32b74f40eee96d49d1f9d18f41ca9c7c9773`.

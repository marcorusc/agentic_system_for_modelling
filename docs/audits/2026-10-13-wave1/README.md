# Wave 1 verification — 2026-10-13

The two limitations discussed after this baseline were addressed in the separately
approved [Boolean lineage/error-handling follow-up](../2026-10-13-lineage-errors/README.md).
This record retains the original Wave 1 results.

Approved scope: NeKo identifiers, PhysiCell Settings XML consistency, and shared
MCP storage/import-provenance/timestamp infrastructure. Wave 2 remains unapproved.
See the [implementation record](../../improvement-plan-2026-10-05.md).

## Source and preservation

| Repository | Original commit | Feature branch head |
|---|---|---|
| Neko | `f9b8d8cb7b5ca82f6111b8d96610596c2193574a` | `99176abe2c6bd8555fc3c2e0eb01fe89347d3c61` |
| PhysiCell_Settings | `902f08dfc8370ceb028b8ff665afbc99c227bf84` | `5e41c53a9d7101ffbb52424484fb273312ee9703` |
| mcp-biomodelling-servers | `85510616836e7f76d7651976f47bc3c18fda904e` | `12d442e2aa57499708bc8dddb665c7f78181c126` |

Each source repository retains its original checkout and branch. Worktrees are
`/tmp/agentic-wave1-20261013/neko`, `physicell-settings`, and `mcp`. Source commits
remain available on named `codex/wave1-*` branches even if temporary directories
are later removed. Nothing was pushed, merged, published or installed.

The [verification JSON](verification.json) records unchanged original heads/statuses,
unchanged NeKo notebook hashes, all eight pristine modelling templates, archive
commit identity, feature branch cleanliness and log hashes. No scientific model
was initialized in the agentic workspace. Tests use synthetic fixtures and
throwaway artifacts, not the archived biological model.

## Results

| Check | Result | Evidence |
|---|---|---|
| NeKo targeted offline suite | 79 passed | [log](neko-tests.log) |
| NeKo original-method comparison | 13 failed, 2 passed among 15 new cases | Baseline substitution executed only in memory; original source untouched |
| PhysiCell Settings full suite | 82 passed, 30 subtests passed | [log](settings-tests.log) |
| Intermediate death-rate fix | 72 passed, 2 subtests passed | Commit `f2d6246` message |
| Intermediate cycle fix | 77 passed, 8 subtests passed | Commit `803f86b` message |
| MCP affected suite | 554 passed, 12 existing deprecation warnings | [log](mcp-tests.log) |
| Separate unchanged-base error-masking suite | 20 passed, 8 failed | [baseline log](baseline-error-masking.log) |
| Complete MCP suite | Incomplete: 180-second timeout; 667 collected | Engine-heavy BioMASS suite exceeded the bound; not reported as a pass |
| Source compilation / diff checks | Passed | Final reviewed files compiled; all three feature branches clean |

The MCP error-masking failures reproduce on both the original base and feature
code. TypeError/AttributeError details appear in returned errors where the tests
expect them to be masked. This is a pre-existing installed-SDK/registration
contract mismatch, not a new Wave 1 regression. Its source and tests were left
unchanged. Future maintenance should investigate it without weakening the tests.

An initial larger integration run aborted inside Tcl when a GUI plotting backend
was selected. The final coordinator run used `MPLBACKEND=Agg`, normal asyncio and
no selector monkeypatch. Worker-only sandbox protocol attempts also encountered
denied socketpair wakeups; their polling workaround results are not the final
acceptance evidence. Final coordinator protocol tests ran outside that restrictive
sandbox with temporary artifact roots supplied by the test fixture.

## Reproduction

Python: `/home/marcorusc/miniforge3/envs/mcp_modelling/bin/python` (3.14.6).
Installed modelling dependencies were not modified. `pytest` was initially absent;
test-only packages were installed into `/tmp/agentic-wave1-20261013/test-deps`.
A worker also assembled pytest from an existing local cache. Full invocations and
intermediate logs remain in `/tmp/agentic-wave1-20261013/control`.

From the PhysiCell Settings worktree:

```bash
PYTHONPATH=/tmp/agentic-wave1-20261013/test-deps \
  /home/marcorusc/miniforge3/envs/mcp_modelling/bin/python -m pytest -q tests
```

From the MCP worktree, the final affected suite was:

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
  tests/test_maboss_preservation.py
```

The separate baseline was run from the unchanged MCP checkout, without bytecode
or pytest cache writes:

```bash
PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg \
  PYTHONPATH=/tmp/agentic-wave1-20261013/test-deps \
  timeout -k 5 60 /home/marcorusc/miniforge3/envs/mcp_modelling/bin/python \
  -m pytest -p no:cacheprovider -q --tb=short tests/test_tool_registration.py
```

NeKo requires network guards before dependency imports because installed OmniPath
can probe a server during import. The initial probe failed DNS; final verification
blocked DNS/socket connections and requests before importing source code. The
worker's guarded runner explicitly verified source imports and then ran:

```text
tests/test_sif_identifiers.py
tests/test_identifier_mapping.py
tests/test_core.py
tests/test_modify_node_name.py
tests/test_chebi_mapping.py
tests/test_network.py::test_aliases_share_one_canonical_visualizer_node
tests/test_network.py::test_gene_symbol_conversion_prefers_custom_network_nodes
tests/test_network.py::test_gene_symbol_conversion_preserves_unknown_identifier
tests/test_network.py::test_sif_import_merges_opposite_signs
```

The checkout identifies as NeKo 1.10.0; installed distribution metadata is 1.10.1.
The logged tests load checkout source explicitly. The new regression module has
15 parametrized cases; the original method was compiled from `git show` and
substituted in memory to demonstrate the failures. No dependency upgrade was used.

## Boundaries for subsequent work

- Library support for B-PC-1/2/4/6 is implemented, but the MCP controls/readback and
  original live invocation still require Wave 2 verification.
- Source sidecars and immutable import events retain verified ordinary-import
  ancestry; they do not alter accepted handoff v1 or grant scientific approval.
  B-SH-2 remains partial until a separately designed cross-stage contract and
  capture/lifecycle integration are implemented.
- Legacy artifacts remain inspectable; no automatic migration or restoration is
  performed. Clients must be updated/configured after a release decision.
- No new readout tools, interaction edits, mapping validators, portable project
  export, RNG changes, exact-switch coupling or simulation defaults were included.
- The full scientific benchmark, stock PhysiBoSS execution and release deployment
  are outstanding. Passing configuration tests does not establish scientific validity.

## Delegation note

Three coding workers were used. Nested-agent startup from the main workspace
failed because its required dispatcher permits a single owner. Workers instead
ran in the isolated coding worktrees with MCP servers and app tools disabled;
project enforcement was not weakened. The launch method was checked against local
CLI help and the [official Codex execution recipe](https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex).
The coordinator reviewed their output and added durable import-event records,
atomic publication, ownership checks and complete parameter descriptions.

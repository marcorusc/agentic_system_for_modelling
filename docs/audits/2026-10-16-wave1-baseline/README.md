# Persistent integrated Wave 1 baseline — 2026-10-16

The researcher authorized establishing this baseline before discussing Wave 2.
The three packages are installed in
`/home/marcorusc/miniforge3/envs/mcp_modelling` and verified together. This is a
local software baseline, not scientific acceptance of a model or a public release.

## Sources and integration

Persistent working directories are under
`/home/marcorusc/projects/github/agentic_system_for_modelling/.setup/wave1-baseline/checkouts/`.
Each repository uses its own `codex/wave1-baseline` branch. The source branches
survived disappearance of the old `/tmp/agentic-wave1-20261013/` worktrees.

| Repository | Integrated source | Installed distribution |
|---|---|---|
| Neko | `30c3f2e31614e874f2267bb1919eb2500da97eff` | `nekomata==1.10.1+wave1.20261016` |
| PhysiCell_Settings | `2967933300a292e5e66332349cb9ff7bf10f8780` | `physicell-settings==0.6.2+wave1.20261016` |
| mcp-biomodelling-servers | `2a18cb56727b5d56b3f4b302a67dbfe3f7a5b7d6` | `mcp-biomodelling-servers==2.4.0+wave1.20261016` |

Agentic integration was tested at `e4b5d8a`; this audit adds documentation only.
All three persistent source worktrees were clean after build and validation.
The original sibling checkouts retain their heads and worktree changes, including
the three modified NeKo notebooks. No original branch was merged, no history was
rewritten, and nothing was pushed or published.

Integration found one material dependency issue: the identifier feature branch
was based on NeKo 1.10.0 and lacked the SIF reference fix already installed in
1.10.1. Merge `fcdbde3` combines `99176ab` with `94579ac` from
`codex/preserve-sif-references`, preserving both histories and their tests.
Commit `30c3f2e` identifies that integrated package with a local version suffix.

Settings commit `2967933` aligns distribution and runtime version metadata.
MCP commits `91290e7` and `2a18cb5` identify the local build and align all four
server descriptors, including their package/runtime pins. Four metadata test
failures exposed the initially stale descriptors; all passed after correction.
These local versions are not on PyPI: use the retained wheels and installed
entrypoints, not a public `uvx` download of the local descriptor version.

Included behavior is the approved Wave 1 library work, shared artifact storage,
Boolean v2 lineage with v1 compatibility, exact-model approval/capture integration,
and shared unexpected-error masking. ODE lineage and remaining Wave 2 tools are
outside this baseline. Earlier scope details remain in the
[Wave 1](../2026-10-13-wave1/README.md) and
[lineage/error](../2026-10-13-lineage-errors/README.md) audits.

## Verification

| Check | Result |
|---|---|
| Combined NeKo identifier/reference tests, provider access blocked before imports | 88 passed |
| PhysiCell Settings complete test directory | 82 passed; 30 subtests |
| Affected MCP contracts/storage/servers plus packaging/runtime compatibility | 648 passed; 12 existing pyMaBoSS deprecation warnings |
| Agentic `tests/codex tests/setup`, using installed validation wheels | 442 passed; 731 subtests |
| Fresh installed stdio processes in validation and active environments | All four initialize and list tools successfully |
| Installed Python source files compared with wheel content | 132 files matched |
| Active environment `pip check`, before and after installation | Passed |
| Static repository isolation | Passed; live parent inventory not verified |

Fresh active processes report MCP version `2.4.0+wave1.20261016` and expose
33 NeKo, 24 MaBoSS, 34 PhysiCell and 22 BioMASS tools. The protocol checks made
zero modelling tool calls, blocked external networking and used disposable
artifact roots; no scientific sessions were created. They verify fresh installed
entrypoints, not a previously loaded desktop tool inventory or simulation behavior.
No modelling server processes were running before installation.

The engine-heavy complete MCP suite and live scientific benchmark were not run.
The main environment changed only the three named packages; MaBoSS/BioMASS engine
dependencies and numerical defaults were unchanged. Build/test dependencies live
in the separate `validation-env` with system site packages.

Commands below run from the agentic repository root unless a subshell changes
directory. The copied `reproduction/` helpers are the exact helpers used; restore
them into the baseline directory if needed. Logs and JSON results accompany this
document. Normal async execution required a host context permitting local sockets;
tests used `MPLBACKEND=Agg` for headless plotting.

```bash
BASE="$PWD/.setup/wave1-baseline"
PY="$BASE/validation-env/bin/python"
ACTIVE=/home/marcorusc/miniforge3/envs/mcp_modelling/bin/python

# Build from the recorded checkouts without resolving scientific dependencies.
"$PY" -m pip wheel --no-deps --no-build-isolation --wheel-dir "$BASE/wheels" \
  "$BASE/checkouts/Neko" "$BASE/checkouts/PhysiCell_Settings" \
  "$BASE/checkouts/mcp-biomodelling-servers"
"$PY" -m pip install --no-deps --no-index --force-reinstall "$BASE"/wheels/*.whl

"$PY" "$BASE/run-neko-tests.py"
(cd "$BASE/checkouts/PhysiCell_Settings" && "$PY" -m pytest -q --tb=short tests)
(cd "$BASE/checkouts/mcp-biomodelling-servers" && \
  MPLBACKEND=Agg timeout -k 5 90 "$PY" -m pytest -q --tb=short \
  tests/test_artifact_manager.py tests/test_shared_foundation.py \
  tests/test_source_import_handlers.py tests/test_import_record_persistence.py \
  tests/test_handoff_contracts.py tests/test_neko_session_manager.py \
  tests/test_maboss_session_manager.py tests/test_physicell_session_manager.py \
  tests/test_cross_server_output_schemas.py tests/test_neko_mcp_errors.py \
  tests/test_maboss_mcp_errors.py tests/test_physicell_mcp_errors.py \
  tests/test_physicell_concurrency.py tests/test_server_initialization.py \
  tests/test_maboss_preservation.py tests/test_tool_registration.py \
  tests/test_boolean_lineage_v2.py tests/test_package_metadata.py \
  tests/test_runtime_compatibility.py tests/test_mcp_v2_deprecations.py)
MPLBACKEND=Agg timeout -k 5 120 "$PY" -m pytest -q --tb=short tests/codex tests/setup
python3 scripts/check_isolation.py --repository-only
"$PY" "$BASE/smoke-installed.py"
"$ACTIVE" "$BASE/smoke-installed.py"
"$ACTIVE" -m pip check
```

## Installation, preservation and recovery

The configured environment was updated from the three validated local wheels
using `pip install --no-deps --no-index --force-reinstall`. Fresh entrypoints
used by the configured clients then passed the protocol checks above.
New artifacts use the shared configurable server-namespaced root, with user-cache
storage as the default; existing package-local artifacts remain discoverable.
No artifact migration or deletion was performed.

All **965** pre-existing artifact files retained their SHA-256 hashes (NeKo 63,
MaBoSS 422, PhysiCell 7, BioMASS 473). The archive
`model/archive/toy-cell-cycle-2026-10-05` still resolves to
`badb32b74f40eee96d49d1f9d18f41ca9c7c9773`.
All eight lifecycle state files match pristine templates. All eleven checked NeKo
notebooks match the preceding audit, including the three user-modified notebooks.

`verification.json` records full source commits, wheel hashes, package changes,
preservation checks and evidence hashes. `installed-packages.json` additionally
records installed Python file hashes. The baseline directory retains build logs,
pre/post environment inventories, legacy artifact hashes, and rollback wheels.
Before installation, all 130 Python files in the rollback wheels were checked
against the previously installed code and matched.

The `.setup/` directory is ignored by Git: it is persistent local storage, not a
backup. Source commits remain on named branches in the original repositories;
this tracked audit preserves their identities and reconstruction evidence.
Retain the wheel directories for exact binary reinstall/rollback.

To reinstall the baseline, or to roll back **when explicitly requested**, use one
of these commands from the repository root, with modelling processes stopped:

```bash
# Reinstall this baseline.
/home/marcorusc/miniforge3/envs/mcp_modelling/bin/python -m pip install \
  --no-deps --no-index --force-reinstall .setup/wave1-baseline/wheels/*.whl

# Roll back the three packages; this does not remove artifacts or revert sources.
/home/marcorusc/miniforge3/envs/mcp_modelling/bin/python -m pip install \
  --no-deps --no-index --force-reinstall .setup/wave1-baseline/rollback/*.whl
```

Rollback has not been executed. Older code is not guaranteed to understand newly
created v2 handoffs. Wave 2 remains deferred for discussion with the researcher.

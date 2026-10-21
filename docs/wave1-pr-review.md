# Wave 1 PR review and release ordering

The maintenance PR starts from upstream main and carries the Point A and approved
Boolean lineage/capture changes with their individual commit messages. Scientific
checkpoints, archive/recovery manifests and model reset commits are excluded.
The original model branch and installed local baseline remain unchanged.
Historical audit records describe that local baseline, not the PR commit IDs.

As of 2026-10-19, the companion changes have merged: official
[NeKo #37](https://github.com/sysbio-curie/Neko/pull/37),
[NeKo fork #4](https://github.com/marcorusc/Neko/pull/4),
[PhysiCell Settings #7](https://github.com/marcorusc/PhysiCell_Settings/pull/7), and
[MCP servers #11](https://github.com/marcorusc/mcp-biomodelling-servers/pull/11).
The corresponding new packages and MCP Registry entry have not been published.

`setup/requirements-wave1-review.txt` pins all three companion repositories to
exact merged commits, including the final companion review fixes. The additional
CI job installs these sources in an isolated job
and runs the complete repository regression runner, including backend-dependent
capture tests that would otherwise be skipped. Existing dependency-light jobs
remain useful independently. CI verifies installed Git revisions as well as
package versions, so an older build with the same version cannot satisfy the
source-integration check.

| Companion | Pinned merged revision | Source package version |
|---|---|---|
| NeKo fork | `0cccd28946b25cf31d612291feeaaf70195c118f` | 1.10.2 |
| PhysiCell Settings | `75485757b040cc9ea336d458d65c94e02cb4aff4` | 0.6.3 |
| MCP servers | `0e3f7fcd542d3d8047d27e04a6e9765b59e06b49` | 2.5.0 |

Official NeKo's merged revision `673875d09e4c49c97d0d760d3ea85bd2603efc82`
contains the identifier fix but still declares 1.10.1. MCP 2.5.0 requires NeKo
1.10.2 or newer. The source-only integration environment therefore retains the
merged fork's 1.10.2 metadata; it does not bypass dependency resolution or pretend
the official 1.10.1 package contains the unreleased change. Switch to the official
release when it exists and revalidate the complete installation.

## Deployment prerequisite before merge

Resolved for release 1.0.0 (2026-10-21): MCP 2.5.0, NeKo 1.10.2 and PhysiCell
Settings 0.6.3 are published on PyPI (official `sysbio-curie/Neko` tag `v1.10.2`,
`ff16c87`). `setup/dependencies.toml`, the release-version tests, the operational
skill snapshots and the source-install example now pin that released set, and CI
installs it from PyPI instead of `setup/requirements-wave1-review.txt` (removed).
The historical text below describes the state before publication.


The normal setup manifest still pins the published MCP 2.4.0 / NeKo 1.10.1 pair.
Do not use that default setup path to deploy the v2 contract changes in this PR.
Before marking this PR ready, publish the reviewed library releases, publish MCP
2.5.0, and update `setup/dependencies.toml`, its release-version tests, operational
skill snapshots and the source-install manifest together. This avoids pointing
ordinary users at packages that do not yet exist. Until then, the exact-source
CI installation is the review route and the existing installed local baseline
is the workstation route. No release tag or package publication is authorized by
this PR maintenance work. The PR is open for review, not a draft; passing source
integration checks does not establish readiness of the default installation path.

The review work has not started Wave 2 or executed a biological model.

## Copilot review fixes (2026-10-19)

- `8d298b4`: preserve session-free Claude attempts separately, prevent repeated
  stop-hook blocking, accept byte-identical retries and recover missing index
  entries. Changed artifacts and ambiguous attribution still fail. Unbound records
  and recording failures cannot authorize scientific advancement.
- `418eb71`: reject XML DTDs through the parser for every supported encoding;
  retain benign UTF-16 source bytes and values.
- `bd87e69`: restore the portable literature-hook interpreter and document manual
  overrides while preserving automatic environment substitution.
- `717148f`: replace quadratic peak rescans with one forward pass. Compare against
  the original classifier over 65,535 trajectory/threshold combinations and bound
  indexed reads linearly on the reported oscillating trace.

Focused validation passed: 43 provider-neutral capture tests, 17 artifact-validation
tests and 28 setup-module tests. Tests use temporary artifacts and never invoke a
modelling MCP tool. Full merged-source integration passed **371 Codex, 22 Claude
and 90 setup tests (483 total)**; dependency consistency and installed-source
verification also passed. Environment details and the sandbox limitation are in the
[improvement plan](improvement-plan-2026-10-05.md).

## Historical local review-candidate validation (2026-10-16)

- NeKo: 88 focused offline regressions passed.
- PhysiCell Settings: 82 tests and 30 subtests passed.
- MCP: 648 affected tests passed, with 12 existing pyMaBoSS deprecation warnings.
- MCP configured Ruff checks and mypy (15 modules) passed; wheel/sdist release checks passed.
- Agentic full regression runner: 353 Codex, 22 Claude and 89 setup tests passed.
- Fresh PR-wheel stdio entrypoints initialize and list tools for all four servers;
  no modelling tool calls or scientific sessions are involved.

The full engine-heavy MCP suite is delegated to existing CI; local results above
are not a claim of full simulation or live benchmark validation.

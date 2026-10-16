# Wave 1 PR review and release ordering

The maintenance PR starts from upstream main and carries the Point A and approved
Boolean lineage/capture changes with their individual commit messages. Scientific
checkpoints, archive/recovery manifests and model reset commits are excluded.
The original model branch and installed local baseline remain unchanged.
Historical audit records describe that local baseline, not the PR commit IDs.

Review the NeKo identifier/reference PR and PhysiCell Settings XML PR first,
then MCP storage/lineage/error handling and this agentic integration. Proposed
package versions are NeKo 1.10.2, PhysiCell Settings 0.6.3 and MCP 2.5.0.
These are candidates, not published releases.

`setup/requirements-wave1-review.txt` pins all three companion repositories to
exact commits. The additional CI job installs these sources in an isolated job
and runs the complete repository regression runner, including backend-dependent
capture tests that would otherwise be skipped. Existing dependency-light jobs
remain useful independently.

## Deployment prerequisite before merge

The normal setup manifest still pins the published MCP 2.4.0 / NeKo 1.10.1 pair.
Do not use that default setup path to deploy the v2 contract changes in this PR.
Before marking this PR ready, publish the reviewed library releases, publish MCP
2.5.0, and update `setup/dependencies.toml`, its release-version tests, operational
skill snapshots and the source-install manifest together. This avoids pointing
ordinary users at packages that do not yet exist. Until then, the exact-source
CI installation is the review route and the existing installed local baseline
is the workstation route. No release tag or package publication is authorized by
opening these draft PRs.

The review work has not started Wave 2 or executed a biological model.

## Local review-candidate validation

- NeKo: 88 focused offline regressions passed.
- PhysiCell Settings: 82 tests and 30 subtests passed.
- MCP: 648 affected tests passed, with 12 existing pyMaBoSS deprecation warnings.
- MCP configured Ruff checks and mypy (15 modules) passed; wheel/sdist release checks passed.
- Agentic full regression runner: 353 Codex, 22 Claude and 89 setup tests passed.
- Fresh PR-wheel stdio entrypoints initialize and list tools for all four servers;
  no modelling tool calls or scientific sessions are involved.

The full engine-heavy MCP suite is delegated to existing CI; local results above
are not a claim of full simulation or live benchmark validation.

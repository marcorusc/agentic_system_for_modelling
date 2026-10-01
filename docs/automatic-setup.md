# Automatic local setup

Run inside Linux or WSL with Python 3.11+ and Git installed:

```text
python scripts/setup.py
```

The guided command detects Codex and Claude, asks which client to configure when
needed, and asks for missing executable paths. It creates a dedicated modelling
environment, generates client configuration, and verifies the result. It never
installs or signs into a coding client automatically.

```text
python scripts/setup.py --client codex
python scripts/setup.py --client claude
python scripts/setup.py --client both
python scripts/setup.py --client codex --dry-run
python scripts/setup.py --check --non-interactive
python scripts/setup.py --config setup/input.example.json --non-interactive
```

Use an absolute script path when invoking from outside the repository. Native
Windows/macOS setup is rejected; run the Windows workflow inside WSL. This does
not install WSL or configure a Windows-to-WSL desktop bridge. A desktop parent
still needs the externally enforced isolation described in `AGENTS.md`.

## Detection and environment

Explicit command-line paths override the JSON input, which overrides saved local
settings. Executables are then discovered on PATH or in standard user directories.
Only selected clients must be installed; discovered clients are checked using
`--version`. Missing requirements are reported together where possible.

The default environment lives at `.setup/environment`. Auto mode chooses Conda
when available, otherwise Python's virtualenv support. Override it with
`--manager conda` or `--manager venv`; `--manager-path` identifies Conda or the
Python interpreter used to create the environment. `--env-prefix` selects another
new environment location. Conda installs Python 3.11, pip, and Graphviz from
conda-forge. Venv requires Graphviz's `dot` already available on PATH and uses the
selected Python interpreter. Use `--graphviz-path /absolute/path/to/dot` when
Graphviz is outside the standard locations; the equivalent JSON/saved setting is
`graphviz_path`. Setup resolves `dot` during planning, preferring the selected
environment's `bin/dot`, and persists its directory in server PATH alongside stable
system directories. It does not copy the calling IDE's full PATH. Setup does not
run sudo or alter system packages.

`setup/dependencies.toml` pins `mcp-biomodelling-servers==2.3.0`, matching the
repository's workflow snapshots. The upstream package installs its modelling
libraries; `dot` is a separate native requirement. The package's installation
instructions and declared dependencies are maintained at
[the upstream repository](https://github.com/marcorusc/mcp-biomodelling-servers).

The first install resolves transitive dependencies from PyPI and saves the actual
versions to `resolved-requirements.txt` inside the environment. This is an installed
version snapshot, not a committed cross-platform lock with artifact hashes. Later
runs reuse the environment and validate it; they do not silently upgrade it.
To upgrade, select a new environment prefix. If the pinned release is unavailable,
setup fails rather than substituting another release. A local source checkout of
that same version can be supplied with `--package-source /path/to/source`.

An adjacent ownership marker lets setup resume an interrupted environment install.
An existing environment without that marker is rejected. No existing environment
is removed. Package installation may require network access and native build
prerequisites; failures include redacted subprocess diagnostics.

## Reuse and optional BioMASS

The default `--environment-mode managed` retains the owned-environment behavior
above. Use `--environment-mode reuse --env-prefix <existing-env>` to verify an
existing environment without calling an installer or creating an ownership marker.
Reuse does not require discovering Conda or a venv manager and cannot be combined
with `--package-source`. The existing Python, package/import, executable, dependency
and Graphviz requirements still apply; reusable does not mean unverified.

Add `--with-biomass` to configure the optional `ode_modeler` / `ode-modeler` profile
and require the BioMASS authoring, import, evidence, simulation and bundle-export
capabilities, plus NeKo's dedicated BioMASS handoff export. Check mode uses the
same selection. These choices persist in ignored local settings as
`environment_mode` and `biomass` (`enabled` or `disabled`); CLI/input settings take
precedence over the saved values. Default installations do not require BioMASS.

```text
python scripts/setup.py --client both --environment-mode reuse --env-prefix <existing-env> --with-biomass --dry-run
python scripts/setup.py --client both --environment-mode reuse --env-prefix <existing-env> --with-biomass
python scripts/setup.py --check --non-interactive
```

The dry run checks the plan and profile rendering; it does not prove server
capabilities. Actual optional setup verifies capabilities before writing client
configuration and reuses that result for the same run's diagnostics, avoiding a
second startup of each server. Capability failure leaves client configuration
untouched. Managed installation may already have created its environment; reuse
never installs into the selected environment. Missing capabilities produce a
blocker instead of silently falling back to another backend or release.

The package pin remains unchanged. Different local builds can share that version,
so setup checks actual tools rather than using the version as an ODE capability
proxy. Setup probes only initialize and list tools; no model sessions or tool calls
are created. Temp-directory Numba caches reduce writes into a reused installation.
Configured BioMASS uses `.setup/cache/biomass-numba`; startup libraries can still
have other cache effects, so this is not a filesystem sandbox.

## Managed configuration

Codex profiles are generated under `CODEX_HOME` or `~/.codex`. Override this with
`--codex-home`, and export the same `CODEX_HOME` when subsequently launching Codex.
Setup preserves unrelated TOML values, although comments and formatting in these
profiles are normalized. Transport paths and environment variables are updated;
unknown enabled MCP servers cause an error. All non-ODE profiles explicitly
disable BioMASS; app connectors and dispatcher access are disabled in specialist
profiles. Existing ODE/literature instructions receive the version-2 contract
guidance when optional ODE setup is selected. The known source profile's obsolete
blanket final-export restriction is migrated to provisional-preservation guidance;
other researcher instructions and settings are preserved. Recognizable custom
blanket export restrictions are reported for reconciliation instead of silently
rewritten. The parent project's disabled modelling
servers remain disabled. The local modelling plugin is registered and installed
when missing. Setup refreshes a stale or disabled installed copy to the exact
repository manifest version, then verifies its enabled state, source, marketplace,
and version from Codex's structured JSON output. Check mode reports drift without
changing it.

Claude's three base modelling agent files, plus `ode-modeler` when selected,
receive updated command, CONDA_PREFIX, and PATH fields. The literature-reviewer Python hook receives the environment's Python
path. Agent bodies, tool permissions, skills, and scientific rules are preserved.
The adapter accepts the repository's existing inline YAML structure and rejects
unsupported layouts instead of guessing. These Claude edits are machine-specific;
review them before committing or sharing a checkout.

Each changed file is backed up under `.setup/backups`, then replaced atomically.
Identical files are not rewritten. This is atomic per file, not a transaction over
all files; if a later step fails, backups and completed changes remain available
and rerunning setup resumes work. Symlink configuration targets are rejected.

Local settings, generated-file hashes, and the latest completed diagnostic report
are stored under ignored `.setup/`. Keep JSON input files containing personal paths
there too. Setup never stores authentication tokens in its input or state schema.

## Verification and exit status

`--dry-run` reports prerequisites and planned file destinations without installing,
writing configuration, or starting MCP servers. It does run client version checks.
`--check` verifies an existing installation without repairing it. Setup checks:

- Python imports, installed server version, pip dependency consistency, executable
  files, and Graphviz availability;
- MCP initialization and paginated tool listings for each server, without creating
  scientific sessions or calling modelling tools;
- expected domain tools and absence of other domains' sentinel tools;
- Codex plugin presence and the existing specialist/parent inventory checks;
- Claude CLI MCP-list availability and exact managed configuration paths.

Standalone Codex diagnostics can include the optional profile with
`python scripts/codex/check_environment.py --with-biomass --expected-branch <branch>`.
A safe literature profile with no backend is degraded; a profile exposing a
prohibited modelling server fails isolation.

Diagnostic subprocesses have timeouts. MCP probes have a whole-operation deadline
inside the outer watchdog so SDK cleanup can run first. On Linux, watchdog fallback
also stops still-owned descendants, including detached child sessions, after checking
process identity. MCP startup probes run in temporary working directories. Startup imports may have library-specific cache effects; setup does
not claim an operating-system sandbox for server processes.

Exit 0 means the requested installation checks passed; exit 2 means something is
missing, incompatible, stale, or failed. This is not scientific approval. Client
login is reported as unverified, and clients must be restarted after path changes.
Claude inline-agent isolation still needs client-level inspection. Literature
requires separately configured PubMed, or explicitly authorized web search for
Codex; setup does not invent a PubMed backend or enable search consent.

## Development

`python scripts/run_tests.py` includes setup regression tests using temporary
repositories and mocked installers/clients. Live package installation, authentication,
and platform-specific MCP smoke testing are separate deployment checks.


The Phase 4 integration tests use temporary setup fixtures and leave installed
profiles, package environments and the active plugin untouched. Phase 5 deployment
verification must establish actual client/process isolation before scientific ODE
work begins; source configuration and tools/list checks alone do not establish
what an LLM invocation can see or perform.

## Pinned local backend development sources

For the post-smoke integration, use `--backend-sources` with a version-1 JSON
manifest containing exactly `nekomata` and `mcp-biomodelling-servers`. Each entry
requires `name`, `version`, `path` and a full Git `commit`. Relative paths resolve
from the manifest's directory. The selected checkout must be its repository root,
clean, and at that commit. The MCP package version must also match
`setup/dependencies.toml`. See `setup/backend-sources.integration.json` for the
current local source revisions; adjust its paths for your checkout layout.

Preview configuration for both clients, supplying an external Codex home if needed:

```sh
python scripts/setup.py --client both --with-biomass \
  --backend-sources setup/backend-sources.integration.json \
  --env-prefix "$PWD/.setup/integration-environment" --dry-run
```

Remove `--dry-run` to install into a new setup-managed environment and configure
both clients. Setup installs both packages together from temporary Git archives,
not editable checkouts; ignored files cannot become build inputs. Normal dependency
resolution can still use the package index. The source pins do not lock every
transitive dependency; `resolved-requirements.txt` records the actual resolution.

The environment's `.setup-backend-sources.json` records selected commits, pip's
local snapshot origin and hashes of installed distribution files (excluding pyc).
`--check` and `--environment-mode reuse` verify that receipt and installed bytes
before configuration writes. They do not install or repair packages. Keep the
manifest and source checkouts available for these checks. A source change requires
a new environment prefix. The legacy `--package-source` option cannot be combined
with `--backend-sources`; it remains a version-only development path.

The receipt detects recorded-file drift; it is not an adversarial attestation or a
proof of scientific correctness. These local backend commits are not releases and
still have the SDK compatibility findings in `docs/integration/post-smoke/`.
Source setup does not claim those release blockers are resolved, and does not
install into the shared modelling environment implicitly.

Setup rejects a Codex home or plugin-cache location that overlaps the plugin
source before rendering/writing configuration or invoking plugin installation.
This check also follows existing symlink aliases. Use a separate home/cache;
placing a temporary home inside this repository can make plugin copying recurse.

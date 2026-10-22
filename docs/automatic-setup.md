# Automatic local setup

Run inside Linux or WSL with Python 3.11+ and Git installed:

```text
python scripts/setup.py
```

The guided command detects Codex and Claude, asks which client to configure when
needed, and asks for missing executable paths. By default it creates a dedicated
modelling environment; with `--environment-mode plugin` it instead uses the
marketplace plugins' uvx launch and needs only uv (see [Plugin mode](#plugin-mode-uv-only)).
It generates client configuration and verifies the result. It never installs or
signs into a coding client automatically.

```text
python scripts/setup.py --client claude --environment-mode plugin
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
new environment location. Conda installs Python 3.11 and pip from conda-forge; venv
uses the selected Python interpreter. The released servers bundle the MaBoSS engine
(cmaboss) and Graphviz (PyGraphviz wheels), so neither a MaBoSS executable nor a
system Graphviz is required. `--graphviz-path /absolute/path/to/dot` (JSON/saved
setting `graphviz_path`) remains an optional override: when supplied, its directory
is added to server PATH alongside stable system directories. Setup never
auto-discovers `dot`, does not copy the calling IDE's full PATH, and does not run
sudo or alter system packages.

`setup/dependencies.toml` pins the released pair
`mcp-biomodelling-servers==2.5.0` and `nekomata==1.10.2`. The MCP release includes
BioMASS support and the Wave 2 interfaces (NeKo interaction curation and history
export, MaBoSS readouts, rates and durable runs, PhysiCell inputs and configuration
bundles). Setup passes both pins to pip and checks both installed versions before
any client configuration writes, including in reuse mode and `--check`. Historical
workflow snapshots retain their original versions. Other modelling libraries are
resolved from the upstream package dependencies. The package's installation
instructions and declared dependencies are maintained at
[the upstream repository](https://github.com/marcorusc/mcp-biomodelling-servers).

The first install resolves transitive dependencies from PyPI and saves the actual
versions to `resolved-requirements.txt` inside the environment. This is an installed
version snapshot, not a committed cross-platform lock with artifact hashes. Later
runs reuse the environment and validate it; they do not silently upgrade it.
To upgrade from an older setup, select a new environment prefix, for example
`--env-prefix "$PWD/.setup/environment-mcp-2.5.0-neko-1.10.2"`. An old ownership
marker or changed dependency pins require a new prefix; reuse mode verifies an
existing environment and cannot upgrade it. If the pinned release is unavailable,
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
with `--package-source`. The existing Python, package/import, executable and
dependency requirements still apply; reusable does not mean unverified.

## Plugin mode (uv only)

The MCP repository publishes each server as a Claude Code, Codex and Agent Plugins
1.0 plugin in the `marcorusc` marketplace
(`claude plugin marketplace add marcorusc/mcp-biomodelling-servers`). **Do not enable
those plugins for this project.** An enabled plugin connects its MCP servers to the
main session, which would give the orchestrator modelling tools; plugin-shipped
agents also cannot declare their own MCP servers. The isolation check fails when
`neko`, `maboss`, `physicell` or `biomass` plugins are enabled in project, local or
user Claude settings, or when `mcp__plugin_<server>_…` tools are allowed project-wide.

Instead, `--environment-mode plugin` gives each specialist the plugin's own launch,
inline and visible only to that specialist:

```text
uvx --from mcp-biomodelling-servers==2.5.0 mcp-<server>-server
```

[uv](https://docs.astral.sh/uv/) is the only prerequisite: no Conda, venv, MaBoSS
or Graphviz installation. Setup discovers `uvx` on PATH or in `~/.local/bin`
(override with `--uv-path`, saved as `uv_path`), resolves the launch once so the
first specialist start does not download packages, checks the resolved server
version, and probes each server's tool inventory through that exact launch. Plugin
mode cannot be combined with `--env-prefix`, `--manager`, `--manager-path`,
`--package-source` or `--backend-sources`; values saved from another mode are not
carried over.

```text
python scripts/setup.py --client claude --environment-mode plugin --with-biomass
```

The plugin pins only `mcp-biomodelling-servers`; its other dependencies follow that
package's declared ranges and can drift as upstream releases appear. Setup reports a
resolved version that differs from a tested pin (for example `nekomata`) as a
warning in the report rather than failing. Use a managed environment when an exact
installed snapshot (`resolved-requirements.txt`) matters more than install
simplicity. Capture helpers that read handoff contracts need the package too; in
plugin mode run them with the same release, for example
`uvx --from mcp-biomodelling-servers==2.5.0 python scripts/capture/<helper>.py …`.

The tracked agent definitions ship this launch with a bare `uvx`, so a checkout with
uv on PATH works before setup runs. Setup rewrites it to the absolute `uvx` path and
a fixed PATH, because desktop clients often start without the login shell's PATH.

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
receive a regenerated transport block: command, CONDA_PREFIX and PATH for an
environment, or the absolute `uvx`, the plugin arguments and PATH in plugin mode.
The literature-reviewer Python hook receives the environment's Python path; plugin
mode keeps the portable `python3` (the hook uses only the standard library). Agent bodies, tool permissions, skills, and scientific rules are preserved.
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

- Python imports, installed server version, pip dependency consistency and
  executable files (plugin mode: the resolved launch's server version, with
  dependency drift reported as warnings);
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
uses `https://pubmed.mcp.claude.com/mcp` by default in the isolated Codex profile,
while preserving custom/disabled transports. Web search still requires explicit
researcher authorization. Test remote availability independently with
`python3 scripts/setup_support/probe_pubmed.py --python /path/to/modelling/python`;
it performs only initialization and tools/list under a process watchdog. A healthy
chat connector alone does not configure the dispatcher profile.

Setup and CI run the isolation/snapshot guard. Use `scripts/check_isolation.py`
for read-only inspection and its explicit preview/apply migration to remove unsafe
user/current-project modelling registrations after private backup. Never register
modelling servers globally to work around a specialist failure. See
[agentic operations](agentic-operations.md).

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

Ordinary setup uses the released PyPI packages. For reproducible source builds or
backend development, use `--backend-sources` with a version-1 JSON
manifest containing exactly `nekomata` and `mcp-biomodelling-servers`. Each entry
requires `name`, `version`, `path` and a full Git `commit`. Relative paths resolve
from the manifest's directory. The selected checkout must be its repository root,
clean, and at that commit. Both package versions must also match
`setup/dependencies.toml`. The example `setup/backend-sources.integration.json`
now pins the released MCP 2.5.0 (`v2.5.0`) and NeKo 1.10.2 (`v1.10.2`) source revisions. Adjust its paths
to clean checkouts at those exact commits; a newer checkout is not interchangeable.
The NeKo revision comes from [sysbio-curie/Neko](https://github.com/sysbio-curie/Neko),
so an older personal fork may need that upstream revision fetched first.

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
proof of scientific correctness. The audits in `docs/integration/post-smoke/`
describe earlier source snapshots and retain their historical findings. The current
release pair still requires environment and capability checks; source setup does
not install into the shared modelling environment implicitly.

Setup rejects a Codex home or plugin-cache location that overlaps the plugin
source before rendering/writing configuration or invoking plugin installation.
This check also follows existing symlink aliases. Use a separate home/cache;
placing a temporary home inside this repository can make plugin copying recurse.

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
selected Python interpreter. Setup does not run sudo or alter system packages.

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

## Managed configuration

Codex profiles are generated under `CODEX_HOME` or `~/.codex`. Override this with
`--codex-home`, and export the same `CODEX_HOME` when subsequently launching Codex.
Setup preserves unrelated TOML values, although comments and formatting in these
profiles are normalized. Transport paths and environment variables are updated;
unknown enabled MCP servers cause an error. The parent project's disabled modelling
servers remain disabled. The local modelling plugin is registered and installed
when missing. Setup refreshes a stale or disabled installed copy to the exact
repository manifest version, then verifies its enabled state, source, marketplace,
and version from Codex's structured JSON output. Check mode reports drift without
changing it.

Claude's three modelling agent files receive updated command, CONDA_PREFIX, and
PATH fields. The literature-reviewer Python hook receives the environment's Python
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

Diagnostic subprocesses have timeouts. MCP startup probes run in temporary working
directories. Startup imports may have library-specific cache effects; setup does
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

# Codex specialist-agent compatibility status

The four tracked `*.toml.example` files preserve the specialist instructions without
committing machine-specific launch commands. No active same-process specialist files
are installed in this directory.

## Codex 0.153.0 limitation

Isolation testing against Codex 0.153.0 found:

- A partial custom-agent server table such as `[mcp_servers.neko] enabled = true`
  is rejected before layering with `invalid transport`.
- A complete permitted-server table in the custom agent does not introduce that
  server when it is disabled in the parent session.
- Disabling prohibited servers in the custom agent does not remove them when they
  are enabled in the parent session.

Consequently, same-process custom agents cannot enforce the required per-agent
NeKo/MaBoSS/PhysiCell isolation. Do not install or select the adjacent examples as
active custom agents. They are retained only as conversion references.

The enforced workflow uses separate user-local Codex profiles and launches a fresh
`codex exec` process through `scripts/codex/run_specialist.py`. See
`.codex/profiles/README.md`. The launcher applies fixed command-line overrides for
all three modelling servers, requires the permitted server, disables destructive
tools, and uses a read-only sandbox.

## Retesting a future same-process implementation

To prepare an isolated test workspace for a future Codex version:

1. Copy each `*.toml.example` file to the same name without `.example`.
2. In each local copy, add the complete user-local transport table for its permitted
   server (`neko`, `maboss`, `physicell`, or optional `pubmed`). Copy `command`,
   `args`, `env`, and `cwd` values from that workstation's Codex configuration as
   applicable; do not add them to the tracked example.
3. Set `enabled = true`. For the three modelling servers, set `required = true`,
   `default_tools_approval_mode = "writes"`, and disable destructive tools such as
   `delete_session` and `clean_generated_files` when the server exposes them.
4. Keep the inert `enabled = false` entries for all prohibited modelling servers.
5. Restart Codex and run the full parent-enabled/parent-disabled isolation matrix.

Never commit generated local overlays: they may contain private executable paths or
environment values. A future Codex version must demonstrate both that the permitted
server is visible independently of parent state and that all prohibited modelling
servers are absent before same-process agents can replace the separate-process
launcher.

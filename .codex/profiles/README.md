# Separate-process specialist profiles

Codex 0.153.0 cannot narrow or independently enable MCP servers for a same-process
custom child. The supported project workflow therefore runs each modelling
specialist as a separate `codex exec` process through the dispatcher shared
runtime. `scripts/codex/run_specialist.py` remains the CLI fallback.

The tracked `*.example` files contain no real executable paths. For each workstation,
copy them to the user's Codex home with these exact names:

- `~/.codex/biomodel-network-curator.config.toml`
- `~/.codex/biomodel-literature-reviewer.config.toml`
- `~/.codex/biomodel-boolean-dynamics-modeler.config.toml`
- `~/.codex/biomodel-multicellular-configurator.config.toml`
- Optional ODE: `~/.codex/biomodel-ode-modeler.config.toml` (only with BioMASS configured)

Replace only the permitted server's placeholder transport with the complete local
`command`, `args`, `env`, and `cwd` values as applicable. Never commit those local
profiles. The launcher also applies fixed highest-precedence `enabled` overrides:
exactly one of `neko`, `maboss`, `physicell`, and optional `biomass` is enabled for a
modelling role; all four are disabled for literature review. Existing roles do not
require BioMASS to be installed. Destructive session and artifact
cleanup tools are disabled for every modelling process.

The literature profile may additionally define a complete `pubmed` transport. If
present, the launcher enables only `search_articles`, `get_article_metadata`,
`convert_article_ids`, `get_full_text_article`, and `find_related_articles`. If it
is absent, literature review requires the explicit `--allow-web-search` flag or
returns a typed blocked result. Web access from a parent process is never assumed.

The repository `.codex/config.toml` deliberately replaces modelling transports with
disabled inert commands in the orchestrator. To preserve that fail-closed parent
boundary, the launcher reads only the permitted complete transport from the
user-local specialist profile and supplies it as a highest-precedence argument to
both MCP preflight and specialist execution. It never prints or stores that
transport.

Before starting the model, the launcher runs `codex mcp list --json` with the same
profile and fixed overrides. It mechanically rejects a missing permitted modelling
server or any enabled prohibited modelling server. A required permitted server that
cannot start then causes `codex exec` itself to fail.

Because specialist execution is non-interactive, a bounded invocation that has
already received the required researcher approval must name each authorized write
tool with a repeated `--approve-tool <tool-name>` argument. The launcher translates
only those names into per-tool `approval_mode="approve"` overrides for the permitted
server. It rejects malformed names and permanently refuses to approve
`delete_session`, `clean_generated_files`, or `close_session`; all unlisted writes retain the
profile's `default_tools_approval_mode="writes"` behavior and therefore fail closed
under non-interactive execution.

Run a read-only tool-inventory preflight after installing or upgrading Codex. A
specialist must stop with `blocked` if its permitted namespace is absent or any
prohibited modelling namespace is visible.

The dispatcher receives the bounded task directly and uses these same profiles.
Fixed runtime overrides also disable `specialist_dispatcher` and built-in app
connectors (`features.apps=false`) in children. See
`docs/specialist-dispatcher-phase4-validation.json` for the passed live namespace
checks, including the explicitly authorized literature web-search inventory test.

The ODE profile uses the canonical `ode_modeler` role and `biomass_ode` stage with
`ode.contract_version=2`; see `skills/biomass-workflow/SKILL.md` and
`docs/ode-contract.md`. Candidate preservation within existing workflow authority
is provisional; final scientific acceptance remains separate. Literature profiles
accept explicit `review_kind=ode` with a BioMASS session ID, while the default
`edge` mode keeps its NeKo provenance. Install or refresh profiles only through
the explicitly requested setup operation; tracked templates alone do not activate
a local modelling environment.

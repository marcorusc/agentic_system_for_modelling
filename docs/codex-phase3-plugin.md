# Phase 3 local Codex plugin architecture

## Package

The repository root is a local plugin source. `.codex-plugin/plugin.json` discovers
the provider-neutral workflow skills under `skills/`. The manifest intentionally
contains no `mcpServers`, apps, hooks, executable paths, credentials, or marketplace
entry. Phase 3 validates the source package but does not install or publish it.

The plugin contributes instructions only. Its modelling skills never call NeKo,
MaBoSS, or PhysiCell and never spawn same-process custom agents. Every specialist
task must pass through `scripts/codex/run_specialist.py`.

## Orchestrator boundary

`.codex/config.toml` supplies disabled inert definitions for `neko`, `maboss`, and
`physicell`. This mechanically removes direct modelling MCP access from trusted
project Codex/VS Code sessions after reload.

The launcher reads the permitted complete transport from an untracked user-local
profile and supplies it at command-line precedence to both `codex mcp list --json`
and `codex exec`. The same resolved executable and inherited environment are used
for the version check, preflight, and execution. Codex 0.153.0 or newer is required.

Repository code cannot inspect or revoke modelling tools already granted to the
parent ChatGPT Windows app. Consequently, ChatGPT Windows orchestration is blocked
unless an external app/admin policy can prove that the parent has no modelling MCP
access. The Windows-to-WSL bridge below isolates the child only; it is not a parent
security boundary.

## Native WSL and VS Code

Write each bounded task to an ignored project file, for example
`.codex/tasks/network-inspection.txt`, then pass the filename as its own argument:

```text
python scripts/codex/run_specialist.py network_curator --prompt-file .codex/tasks/network-inspection.txt
```

Use `--record-session-id` when an existing or upstream full session ID is known.
Add `--allow-web-search` only for `literature_reviewer`.

## Windows-to-WSL bridge

Copy `.codex/launcher.example.json` to the ignored
`.codex/launcher.local.json`. Set the local WSL distribution, absolute WSL project
path, Python executable, and the Codex 0.153.0-or-newer executable. Do not commit the
local file. The small Windows bridge requires Python 3.10 or newer; native execution
inside WSL additionally uses Python's `tomllib` and therefore requires Python 3.11
or newer.

From Windows, invoke the same entry point with `--transport wsl`:

```text
python scripts/codex/run_specialist.py literature_reviewer --transport wsl --prompt-file .codex/tasks/review.txt --allow-web-search --record-session-id <neko-session-id>
```

The bridge constructs a `wsl.exe` argument vector and invokes the native launcher
inside the configured project. It does not construct a shell command, so task text
and identifiers are not shell-interpolated. The inner native process records
`transport=windows-wsl` in provenance and returns its exact exit code through WSL.

## Recorded invocation

After execution, the launcher parses the last assistant message as a JSON handoff
and writes these files beneath the applicable established session directory:

```text
specialist-invocations/<timestamp-and-uuid>/
├── task.txt
├── specialist-output.txt
├── handoff.json
└── provenance.json
```

Provenance includes the role, profile name, transport, timestamps, Codex version and
binary digest, effective modelling-server enablement, web-search flag, prompt hash,
and process exit code. It excludes executable paths, profile transports, environment
values, and credentials. Literature invocations are recorded under their upstream
NeKo session in `runs/network-curator/`.

Nonzero specialist exit codes are propagated. A successful process with no JSON
handoff, a mismatched role, unsafe MCP inventory, or an unrecordable result returns a
launcher failure instead of being treated as completed.

## Literature web-search validation

The explicit subprocess search path was tested on 2026-09-03 with PMID 10647931.
The first attempt placed `--search` after `exec`; Codex 0.153.0 rejected it with exit
code 2, and the launcher propagated and recorded that failure. The corrected
launcher places the global option before `exec`.

The second invocation retrieved the primary PubMed record inside the isolated
literature process and returned:

- PMID: `10647931`
- title: `The hallmarks of cancer`
- journal/year: `Cell` (2000)
- DOI: `10.1016/S0092-8674(00)81683-9`
- source: `https://pubmed.ncbi.nlm.nih.gov/10647931/`

Its recorded provenance showed Codex 0.153.0, `web_search_enabled=true`, exit code
0, and `neko=false`, `maboss=false`, `physicell=false`. The temporary validation
run was moved out of `runs/` after inspection so it cannot be mistaken for a real
NeKo session or scientific evidence report.

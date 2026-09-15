# Code review improvement plan

Scope: implement the September 2026 code-review recommendations without changing
scientific decisions, approval gates, model state, or the Claude implementation.
The existing untracked `plan.md` is a separate compatibility plan and is preserved.

1. Reproduce and close specialist inventory, handoff artifact, and evidence-path
   validation gaps. Add negative tests and valid on-disk artifact fixtures.
2. Keep draft specialist output distinct from completed stage artifacts. Document
   the strict completion checks and the orchestrator's responsibility to assemble
   and verify the final artifacts after read-only specialist work.
3. Extract launcher configuration, process streaming, and provenance helpers into
   focused modules while preserving the CLI and existing helper imports.
4. Provide one standard-library test command and a GitHub Actions workflow using
   Python 3.11 and 3.13. Declare Python 3.11+ as the supported runtime.
5. Clarify the existing Claude/Codex stage-validation difference in documentation;
   do not claim that the missing independent review agents are implemented.
6. Run all suites, CLI smoke checks, and diff checks. Record results here.

Validation uses temporary repositories and subprocess fixtures, without starting
modelling MCP servers or performing scientific operations.

Status: complete.

## Results

- Specialist inventory rejects all unexpected enabled MCP names. Literature
  launches without a configured PubMed transport explicitly disable inherited
  PubMed access.
- Completed handoffs require existing, nonempty, hashed, session-scoped artifacts,
  matching manifest identity, and the documented stage exports. Drafts remain
  distinct. Evidence filenames cannot redirect writes through a symlink.
- Launcher helpers are separated into configuration, process, and provenance
  modules. The CLI and public helper imports are retained. An AST comparison
  confirmed extracted definitions are unchanged except for the intended fixes.
- `python scripts/run_tests.py` runs both suites. The GitHub Actions workflow uses
  the same command on Python 3.11 and 3.13, with read-only repository permission.
- Python 3.11+ requirements and existing validation responsibilities are documented.

Verification: 100 Codex tests, 19 Claude tests, and 26 setup tests passed locally
on Python 3.13.13 and Python 3.14.4.
Launcher, preflight, and handoff validator CLI help smoke checks passed, along with
`git diff --check`. The launcher regression verifies that unbacked completion is
rejected while its invocation and rejection reason remain recorded.

The CI matrix has not run remotely. Live MCP behavior and scientific validity were
not tested. Independent scientific reviewer/auditor agents remain unimplemented;
this work documents the existing workflows without changing their policy.
The scientific-state files, `.claude/`, and existing untracked work are preserved.

---
name: review-literature-evidence
description: Formulate and route bounded primary-source evidence reviews through the isolated literature process, using configured PubMed or explicitly enabled web search.
---

# Review literature evidence

Never assume parent ChatGPT web access and never call modelling MCPs. Prepare a
bounded `task` containing the full NeKo session ID, biological context, and literal
`[source, effect, target]` triples with known PMIDs. Each invocation covers one
coherent cluster of at most 13 edges.

Call `specialist_dispatcher.start_literature_reviewer` with that task and
`record_session_id`. A configured PubMed transport is preferred; set
`allow_web_search=true` only after explicit researcher authorization and only when
that fallback is intended. The isolated process never inherits parent web access.
With neither backend, it returns a recorded blocked handoff without starting a
backendless specialist. All modelling MCPs, app connectors, and dispatcher access
are disabled in the child.

Use `get_specialist_events` with its sequence cursor and `get_specialist_task`
until terminal. On `succeeded`, inspect the handoff's separate scientific status
before accepting evidence; a recorded `blocked` result remains blocked. The
invocation belongs under the upstream NeKo session's run directory. Never update
shared state or synthesize incomplete required review slices while workers run.

For every claim, separately assess existence, direction, sign, directness, and
context match. Prefer original experiments; record reviews and predictions
separately. Capture PMID, DOI, organism, tissue/cell type, disease, perturbation,
study type, conflicts, exclusions, and retrieval limitations. Distinguish metadata,
abstract-only, and retrieved full text. Do not infer support from titles or
co-mention, fabricate evidence, or exceed copyright limits.

Return proposed immutable edge-report content and paths under
`evidence/reports/{neko_session_id}/{source}__{target}.md`; the orchestrator, not the
reviewer subprocess, validates and writes reports. Save each returned draft to an
ignored project-contained file without shell interpolation, then invoke only:

`python scripts/codex/write_literature_report.py --session-id <neko-session-id>
--source <source> --target <target> --draft-file <draft>`

The writer derives the destination, validates the required headings, edge identity,
verdict, interaction type, confidence, and PMID/DOI citation fields, and refuses an
existing file. Treat any validation or write error as an incomplete edge; do not
edit the report directly or claim a `Full report` path.

## CLI fallback

If the dispatcher is unavailable, use `python scripts/codex/run_specialist.py
literature_reviewer --prompt-file <task> --record-session-id <neko-session-id>`.
Place the bounded task under `.codex-tasks/`. Add `--allow-web-search` only with
explicit authorization; Windows-to-WSL fallback adds `--transport wsl`. Backend
isolation, immutable report writing, and scientific approval gates are identical.


## ODE claim mode

For mechanism, kinetic-law or quantity review, pass explicit `review_kind="ode"`
to `specialist_dispatcher.start_literature_reviewer` and provide the full BioMASS
`record_session_id`. Require at most 13 coherent literal claims with stable IDs,
context, known PMIDs/DOIs and originating reaction/edge/quantity IDs. Standalone ODE
work needs no NeKo SIF. Both review modes share the two-reviewer limit and existing
PubMed/authorized-search rules. No modelling tools, including BioMASS, are permitted.

Use the evidence contract in `docs/ode-contract.md`. Review mechanisms and reported
quantities separately; preserve source access limits and unknown units. Return
`review_kind=ode`, the BioMASS session ID and null derived-from ID. The orchestrator
writes each immutable draft using the same writer with `--claim-id <claim>` instead
of `--source`/`--target`. Reports belong at
`evidence/reports/{biomass_session_id}/ode/{claim_id}.md`; invocation records belong
under `runs/ode-modeler/{biomass_session_id}/`. Retry missing reports only. An explicit
re-review uses a new claim ID and identifies the superseded report.

CLI fallback adds `--review-kind ode --record-session-id <biomass-session-id>`.
Unspecified mode remains edge review; wait for all required reports before synthesis.

## Structured, immutable evidence and bounded retrieval

Use PubMed by default, including Codex's isolated configured transport at
https://pubmed.mcp.claude.com/mcp. Missing/failed access is blocked; web search still
requires explicit researcher authorization. Chat connector availability alone does
not establish that an isolated process can use the backend.

Deduplicate supplied PMIDs; retrieve metadata/abstracts in batches of at most eight.
Retrieve full text only when needed, at most eight PMIDs per retrieval batch. For an
edge with supplied references allow one search; a PMID-less candidate may use two
bounded searches and one related-article lookup seeded from a sibling edge PMID.
Do not loop indefinitely or rely on truncated/spilled results as complete evidence.

Every edge report ends with a fenced `yaml` footer containing a JSON object (the
strict, dependency-free JSON-compatible YAML subset) with exactly these fields:
`verdict`, `interaction_type`, `confidence`, `supporting_pmids`, `excluded_pmids`,
`edge` (literal [source,effect,target]) and `neko_session_id`. PMIDs are strings;
lists must be disjoint and exactly match the Supporting and Excluded sections.
Use only supporting_pmids to justify a decision. Valid enums and a complete example
are in docs/agentic-operations.md and scripts/evidence_contract.py.

Canonical reports are write-once. Proposed edges use
`evidence/reports/<session>/candidates/<source>__<target>.md`; each manual edge needs
its own dedicated report before topology inclusion. Explicit re-review creates
`.r2.md`, `.r3.md`, etc.; the preceding revision must exist. Codex writes via
write_literature_report.py with --candidate and/or --revision N as applicable.
Read the written file back; failed validation leaves that review incomplete.

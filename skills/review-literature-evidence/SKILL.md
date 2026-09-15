---
name: review-literature-evidence
description: Formulate and route bounded primary-source evidence reviews through the isolated literature process, using configured PubMed or explicitly enabled web search.
---

# Review literature evidence

Never use parent ChatGPT web access by assumption and never call modelling MCPs.
Write a bounded task file containing a full NeKo session ID, biological context, and
literal `[source, effect, target]` triples with known PMIDs. Limit one invocation to
one coherent cluster of at most 13 edges.

Use only the separate launcher:

- Configured PubMed path: `python scripts/codex/run_specialist.py
  literature_reviewer --prompt-file <task> --record-session-id <neko-session-id>`
  The ignored user-local literature profile must contain the complete `pubmed`
  transport. The launcher detects it, permits only the five structured review
  tools, and records `literature_backend=pubmed`.
- Explicit native web-search path: add `--allow-web-search`. This flag is accepted
  only for `literature_reviewer` and enables search inside that subprocess when no
  PubMed server is available. It is not inherited from the parent.
- Windows-to-WSL: also add `--transport wsl`; ignored local launcher configuration
  supplies the machine-specific bridge values.

The launcher disables all modelling MCPs and records the review invocation under
the upstream `runs/network-curator/{neko_session_id}/` session directory. If neither
PubMed nor explicitly enabled search is available, require a typed `blocked` result.

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

## ODE claim review mode

When explicitly invoked with review_kind=ode, use the ODE report contract in
docs/ode-workflow.md instead of the edge-specific input/output instructions above.
Require the full BioMASS session ID and at most 13 literal coherent claims with stable
claim IDs, kind, context and known citations. No NeKo session or SIF is needed for
standalone ODE work. Assess mechanisms, kinetic approximations and quantity evidence
separately. Return review_kind=ode in the common literature result. Never call BioMASS
or another modelling MCP. The orchestrator coordinates at most two independent reviews.

Codex invocation: scripts/codex/run_specialist.py literature_reviewer --review-kind ode
--record-session-id <biomass-session-id> --prompt-file <bounded-task>. The reviewer
returns report drafts; the orchestrator writes them with write_literature_report.py
--claim-id <claim> and validates completion. Claude writes the same report format through
its guard and reads each exact path back. ODE reports are immutable at
evidence/reports/{biomass_session_id}/ode/{claim_id}.md. Invocation provenance belongs
under the BioMASS session's runs/ode-modeler directory. Missing backend returns blocked;
after failure redispatch only missing claims. Existing edge mode is unchanged.

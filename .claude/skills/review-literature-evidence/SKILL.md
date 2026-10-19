---
name: review-literature-evidence
description: Reviews PubMed evidence for biological interactions and model assumptions using an explicit evidence matrix.
---

# Review literature evidence

For every claim:

1. Define the precise claim.
2. Record entities, direction, and sign.
3. Define organism, tissue, disease, cell type, perturbation, and time-scale constraints.
4. Search identifiers and synonyms.
5. Prioritize original experimental studies.
6. Record reviews separately as background.
7. Do not treat co-mention as mechanistic support.
8. Evaluate edge existence, direction, sign, directness, and context match separately.
9. Record conflicting evidence.
10. State when only an abstract was reviewed.
11. Return a JSON-compatible evidence matrix and concise narrative.

Suggested fields:

```json
{
  "claim_id": "",
  "source": "",
  "target": "",
  "claimed_effect": "",
  "pmid": "",
  "study_type": "",
  "organism": "",
  "biological_context": "",
  "supports_edge": null,
  "supports_direction": null,
  "supports_sign": null,
  "directness": "",
  "limitations": [],
  "confidence": ""
}
```


## ODE claim mode

With explicit `review_kind=ode`, follow `docs/ode-contract.md` for ODE claims rather
than the edge-specific shape above. Require a full BioMASS session ID and at most
13 coherent literal claims with stable IDs, mechanism/kinetic-law/quantity kind,
context and known citations. No NeKo SIF is needed for standalone ODEs. At most two
reviews may run concurrently across both modes. Never call BioMASS or any other
modelling MCP. Missing permitted literature backend yields a blocker.

Write immutable reports through the literature guard at
`evidence/reports/{biomass_session_id}/ode/{claim_id}.md` and read them back.
Record source access, context, conflicts and reported quantities with original
units or null. Return `review_kind=ode`, the BioMASS session ID, null upstream ID
and exact report paths. Retry missing reports only; an explicitly requested
re-review uses a new claim ID and identifies what it supersedes.

## Literature review

- Autonomous invocation of `literature-reviewer` to gather evidence is always
  permitted without pausing, whether triggered by explicit user request or by the
  orchestrator's own read of a `network-curator` report.
- Acting on that evidence — changing topology, removing an edge, switching
  databases — is a consequential decision and requires human approval per the
  Scientific rules above, regardless of whether the review that informed it was
  user-directed or autonomous.
- When invoking `literature-reviewer`, extract the exact edge subset to review
  from `literature_queue.json` yourself and inline it as literal
  `[source, effect, target]` triples in the Task prompt. Never instruct
  `literature-reviewer` to open `literature_queue.json` itself — the sub-agent
  only ever needs the specific slice already selected for that invocation.
- Point `literature-reviewer` at the relevant SIF file for PMID/provenance
  lookups by Grep only (source/target scoped to each edge), never a full
  `Read` — codify this explicitly rather than relying on the prompt happening
  to get it right each time.
- Dispatch in bounded slices: one `literature-reviewer` invocation reviews at
  most one coherent edge cluster (≤ ~13 edges) — never the whole queue in a
  single agent. Split a large queue into per-cluster dispatches; include the
  cluster's SIF-provided reference PMIDs inline in the prompt.
- Concurrency: run at most 2 `literature-reviewer` agents at a time (PubMed
  rate limits + backend stability); launch the next slice only after a running
  one reports back.
- Recovery: after any failed/stopped reviewer run, check
  `evidence/reports/{neko_session_id}/` for already-written edge reports and
  re-dispatch only the missing edges — never re-review edges that already have
  a report file (unless explicitly re-requested).

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

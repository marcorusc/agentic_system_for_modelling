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

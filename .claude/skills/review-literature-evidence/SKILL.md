---
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

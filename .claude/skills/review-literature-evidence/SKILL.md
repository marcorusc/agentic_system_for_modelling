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

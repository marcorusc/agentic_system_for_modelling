# Assumptions

Explicit accepted assumptions. Each lists evidence and the consequence if false.

| ID | Assumption | Evidence | Status | Consequence if false |
|---|---|---|---|---|
| A1 | EML4::ALK is constitutively active in H3122 (V1) / H2228 (V3); no extracellular ligand input in the first cut | user paper (no-stimulus design); ref 2 Methods | accepted (D5, D9) | ligand axis must be added (HRG, D5-later) |
| A2 | Condensate disassembly does **not** abolish catalytic output (decoupling) | user paper Fig 8, S8H–J; overrides ref 2 hexanediol (off-target, authors' own limitation) | accepted (D2) | add `SIGNALOSOME` term to output rules; T4/T5 would fail |
| A3 | The condensate is abstracted as a single Boolean state node; physical properties (size, number, wall thickness, dynamics, morphology) are not modelled | user paper Figs 2, 6, 7 (physical readouts) | accepted (D1) | a different model class is required for those observables |
| A4 | Drug effects are binary (present/absent); dose–response is not modelled | corpus dose series (ALE 50–200 nM; SHP2i 0.5–10 µM) | accepted (D9) | multi-state or ODE layer needed |
| A5 | The core signalosome scaffold (SHC1, GAB1, PTPN11, GRB2, IRS2, PIK3R1) is shared by V1 and V3 | user paper Fig 1B, Fig 6 | accepted (D1) | variant-specific scaffold nodes; topology revision |
| A6 | Variant-conditional rewiring (V1→MAPK/PI3K-AKT dominant; V3→IFN/ISG dominant) is encoded as rule-level gates on shared scaffold outputs, not as separate scaffold entities | user paper Fig 1B, 4, 5 | accepted (D3, D6) | two-session fallback (D3) |
| A7 | TKI-induced bypass upregulation (ERBB3/ERBB2/EGFR/FAK) is a compensatory response to ALK-output suppression, not a constitutive parallel input | ref 4 Figs 1–2, 9B (loss of negative feedback) | accepted (D1) | bypass nodes become constitutive inputs; T8–T12 interpretation changes |
| A8 | `BBP398` (SHP2i) acts by removing PTPN11 from the core, i.e. `BBP398 ⊣ PTPN11` | user paper Fig 8 (SHP099/BBP-398 disrupt condensates) | accepted (D1) | SHP2i edge must be rewired to its true target |

# Validation plan

Committed targets (D4): T1–T12. A target is **met** when the simulated context
reproduces the expected Boolean state of all listed outputs. These targets gate
rule refinement: no rule may be fitted to reproduce a target that is not listed here.

| # | Context (fixed inputs) | Expected model state | Evidence (source → figure) | Status | Result |
|---|---|---|---|---|---|
| T1 | V1 + ALECTINIB | `SIGNALOSOME`=1; `ERK1`=0; `AKT1`=0 | user paper → Fig 2C, S3B–C (ALE-enlarged, signal-depleted; pAKT/pERK down 50–200 nM) | pending | — |
| T2 | V1 + LORLATINIB | `SIGNALOSOME`=0; `ERK1`=0; `AKT1`=0 | user paper → Fig 2; ref 2 → Fig 3E–F | pending | — |
| T3 | V3 + LORLATINIB | `SIGNALOSOME`=0; ALK-catalytic arm off | user paper → Fig 2; ref 2 → Fig 3 | pending | — |
| T4 | V1 + BBP398 | `SIGNALOSOME`=0; `ERK1`=1; `AKT1`=1 (decoupling, D2) | user paper → Fig 8, S8H–J | pending | — |
| T5 | V3 + BBP398 | `SIGNALOSOME`=0; signalling arm maintained (decoupling, D2) | user paper → Fig 8, S8H–J | pending | — |
| T6 | V3 + ALECTINIB or LORLATINIB | `IFIT1`=1; `STAT1`=1 (TKI-refractory IFN program) | user paper → Fig 4B–I, Fig 5 | pending | — |
| T7 | V1, no drug | `IFIT1`=0 (no IFN/ISG dominance) | user paper → Fig 4 | pending | — |
| T8 | V1 or V3 + any TKI | `ERBB3`=1 (adaptive bypass upregulation) | user paper → Fig 8L–M; ref 4 → Figs 1–2 | pending | — |
| T9 | V1 + LORLATINIB | `ERK1`=0; `AKT1`=0; `VIABILITY`=0 (V1 ALKi-sensitive) | ref 4 → Figs 1, 3–4 (pALK abolished; monotherapy cytotoxic) | pending | — |
| T10 | V3 + LORLATINIB | `ERBB3`=1; `AKT1`=1; `VIABILITY`=1 (bypass-dependent) | ref 4 → Figs 4G–J, 6 (pERBB3-Y1289 2× up, pAKT maintained) | pending | — |
| T11 | V3 + LORLATINIB + ERBBi | `ERK1`=0; `AKT1`=0; `APOPTOSIS`=1 | ref 4 → Figs 3–4, S5–S7 (dual collapse + apoptosis, EML4-ALK+ specific) | pending | — |
| T12 | V3 + LORLATINIB + AKTi | `APOPTOSIS`=1 (re-sensitization) | ref 4 → Figs 6, 9 (AKT VIII + LOR cytotoxic; LOR-R line re-sensitized) | pending | — |

**Out of scope:** HRG-dependent targets (D5); quantitative IC50/fold/%-apoptosis
values (provenance only, see `DATA_DICTIONARY.md`); condensate size/morphology
targets (not representable in Boolean form).

**Method (all rows):** MaBoSS context simulation with fixed inputs per context;
read the listed output nodes; compare to expected state. One MCP session per
independent modelling hypothesis; session IDs recorded in `CURRENT_STATE.md`.

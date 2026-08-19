# Model specification

> **STATUS: FINALIZED (stage `specification`) — approved by researcher 2026-08-19.**
> Decision references `Dn` point to `DECISIONS.md`; assumptions `An` to
> `ASSUMPTIONS.md`; validation targets `Tn` to `VALIDATION_PLAN.md`.
> **No modelling operation has been executed yet.** Next stage: `topology`.

## Biological question

How does a shared core EML4::ALK signalosome (condensate) drive *divergent*,
variant-dependent oncogenic signalling (V1 → RAS-MAPK/PI3K-AKT; V3 → IFN/ISG), and
how do ALK-TKIs (alectinib vs lorlatinib/ceritinib) and SHP2 inhibition differentially
act on (i) condensate assembly vs (ii) catalytic signalling output vs (iii) adaptive
bypass (ERBB3/ERBB2/EGFR/FAK/AKT) — so that we can recapitulate the corpus findings
(T1–T12) and predict which perturbations/combinations should or should not restore
or collapse signalling in each variant (scenarios D6)?

## Scope and system boundary (D1)

- **Modelled (core, ~29 nodes):**
  - *Abstractions:* `ALK_CAT`, `ALK_CONFORM`, `SIGNALOSOME`, `VIABILITY`, `APOPTOSIS`.
  - *Core scaffold:* SHC1, GAB1, PTPN11, GRB2, IRS2, PIK3R1.
  - *V1-pref module:* RAS, RAF1, ERK1, PIK3CA, AKT1.
  - *V3-pref module:* STAT1, IFIT1.
  - *Bypass:* ERBB3, ERBB2, EGFR, FAK.
  - *Recurrent marker:* NAMPT.
  - *Inputs:* ALECTINIB, LORLATINIB, CERITINIB, BBP398, V1_ON, V3_ON.
- **Named-but-unmodelled (first cut):** GUK1, PLCG2, CBL/CBLB, SOCS3, PD-L1, PDK1,
  MYC, HRG (D5), HSP90/CDC37 arm, proteasome arm, cell-cycle/DDR arm, PAK1,
  CTNND1, BCAR1/3.
- **Not representable (Boolean first cut, A3):** condensate size/number/morphology,
  radial scaffold positions, FRAP/flow properties, quantitative dose–response (A4).

## Entities and variables

As listed above (see `DATA_DICTIONARY.md` for aliases and provenance).
Variant = V1 (EML4 ex13–ALK ex20) or V3 (EML4 ex6–ALK ex20), selected by the
`V1_ON`/`V3_ON` inputs (D3).

## Mechanistic hypotheses (encoded as rules)

- **H1 — Shared core assembly (A5).** `SIGNALOSOME = 1` requires `ALK_CONFORM` +
  SHC1 + GAB1 + PTPN11, modulated by GRB2/IRS2/PIK3R1. (User paper Figs 6, 7.)
- **H2 — Variant-conditional output (A6).** Core feeds different output modules by
  variant: V1 → RAS-MAPK + PI3K-AKT; V3 → JAK-STAT/IFN-ISG. Gated at rule level by
  `V1_ON`/`V3_ON`. (User paper Figs 1B, 4, 5.)
- **H3 — Decoupling of assembly and catalysis (A2, D2).** Catalytic output (ERK1,
  AKT1) requires `ALK_CAT` + effectors, **not** `SIGNALOSOME`. Condensate
  disassembly does not abolish output. (User paper Fig 8; overrides ref 2 hexanediol.)
- **H4 — Conformation-specific drug action (D10).**
  - `ALECTINIB ⊣ ALK_CAT`; `ALECTINIB → ALK_CONFORM` (preserves/stabilizes).
  - `LORLATINIB ⊣ ALK_CAT`; `LORLATINIB ⊣ ALK_CONFORM`.
  - `CERITINIB ⊣ ALK_CAT`; `CERITINIB ⊣ ALK_CONFORM`.
  - `BBP398 ⊣ PTPN11` (A8) → `SIGNALOSOME` off, catalytic arm intact.
  (Ref 2 Figs 3–6; user paper Fig 2.)
- **H5 — Adaptive bypass feedback (A7).** TKI suppression of ALK output upregulates
  ERBB3/ERBB2/EGFR/FAK; these sustain ERK1/AKT1/Viability. (User paper Fig 8; ref 4
  Figs 1–2, 9B.)
- **H6b — Bypass sustains fate.** Dual ALK + ERBB (or AKT) inhibition collapses
  ERK1/AKT1 and engages APOPTOSIS in EML4-ALK+ contexts. (Ref 4 Figs 3–8, S5–S16.)
- **H7 — Recurrent marker.** `ALK_CAT → NAMPT` (variant-agnostic upregulation).
  (User paper Figs 5, 8.)
- **H8 — Variant-dependent therapeutic sensitivity.** V1 is more ALKi-sensitive
  (monotherapy collapses fate); V3 is more ERBB3/AKT-bypass-dependent (requires dual
  inhibition). (Ref 4 Figs 1, 3–8; user background ref 3.) A *prediction* target as
  much as a recapitulation.

## Mathematical or logical model (D9, D10)

- **Form:** qualitative Boolean network, MaBoSS. One simulation = one context
  (variant × drug(s)). No ODE/kinetics, no invented parameters, no units beyond `{0,1}`.
- **Rule provenance:** each rule tagged `literature-derived` (cited) or
  `fitted-for-dynamics` (reproduces a Tn target) at finalization.
- **Update mode / MaBoSS mechanics:** to be decided at the boolean-dynamics stage
  (not fixed at specification).
- **State space:** ~29 nodes; controlled by restricting to output nodes of interest
  and MaBoSS attractor/mutation analysis.

## Inputs

Per context (one simulation = one run): `V1_ON`/`V3_ON` (D3); `ALECTINIB`,
`LORLATINIB`, `CERITINIB` `∈ {0,1}`; `BBP398 ∈ {0,1}`. Constitutively active ALK,
no ligand (A1, D5). **HRG out of scope** for the first cut (D5) — connect later.

**Candidate intervention scenarios (D6):**
1. ALE vs LOR in V1 and V3.
2. LOR + SHP2i (`BBP398`).
3. LOR + ERBBi.
4. LOR + AKTi.
5. LOR + ERBBi + AKTi (V3).
6. Resistance mutations `F1174L`, `R1275Q` via MaBoSS mutation analysis
   (`K1150M`, `D1270N` follow-up).

## Outputs and observables

**Model outputs (Boolean):** `ERK1`, `AKT1`, `STAT1`, `IFIT1`, `ERBB3`, `ERBB2`,
`EGFR`, `FAK`, `NAMPT`, `VIABILITY`, `APOPTOSIS`, `SIGNALOSOME`.

**Validation:** see `VALIDATION_PLAN.md` (T1–T12, all committed, D4).

## Units

Logical `{0,1}` only (D9). Quantitative figure values are provenance records
(`DATA_DICTIONARY.md`), never model parameters.

## Known limitations

- Boolean abstraction cannot represent condensate size/number/morphology (A3).
- Dose–response collapsed to on/off (A4).
- Constitutive ALK, no ligand (A1; HRG deferred, D5).
- Acute (4 h) vs prolonged (72 h) dynamics are not one timescale; prolonged arms
  (proteome/DDR) out of scope first cut.
- HSP90 arm + proteasome arm represented only as named nodes / single inputs.
- Node list is the approved D1 core, not an exhaustive map of the paper.
- Ref-5 growth-factor-perception claim is **not** in the corpus (D7).

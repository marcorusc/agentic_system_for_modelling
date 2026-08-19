# Data dictionary

## Evidence corpus (inputs/)

| Name | Type | Biological meaning | Unit | Source | Version | Notes |
|---|---|---|---|---|---|---|
| `EA paper_v16_JS.pdf` | PDF (86 pp) | User's own unpublished manuscript: EML4::ALK variant signalosomes — core scaffold, variant rewiring, decoupling, TKI conformation effects, NAMPT/GUK1 | — | Bayliss + Gingras labs | v16 draft (2026) | primary validation source; figures cited as "user paper" |
| `embr.202153693.pdf` | PDF (27 pp) | Sampson et al. 2021 EMBO Rep (ref 2): condensate biophysics, active-conformation requirement, TKI conformation split (3AOX/4MKC/4CLI) | — | DOI 10.15252/embr.202153693 | published 2021 | evidence for D2 (tension), D10 |
| `s41419-024-07272-7.pdf` | PDF (21 pp) | **Sampson et al. 2024 Cell Death & Disease (ref 4)**: ERBB3/AKT adaptive resistance, HRG, LOR-tolerant line, combinations | — | DOI 10.1038/s41419-024-07272-7 | published 2024 | **NOT** the ref-5 Nat Commun paper (D7) |

## Node aliases (model → biology)

| Model node | Biological meaning | Notes |
|---|---|---|
| `ALK_CAT` | EML4::ALK catalytic (kinase) activity | modelling abstraction (D10); V1 = EML4 ex13–ALK ex20, V3 = EML4 ex6–ALK ex20 |
| `ALK_CONFORM` | Assembly-competent active conformation (αC-helix / K1150–E1167 salt bridge) | ref 2 Figs 5–6; not a physical entity |
| `SIGNALOSOME` | EML4::ALK condensate assembly state (present/absent) | A3: Boolean abstraction, no size/morphology |
| `ERK1` | ERK1/2 output (pT202/Y204) | representative node |
| `AKT1` | AKT1/2/3 output (pS473) | representative node |
| `IFIT1` | IFN/ISG program (IFIT1/2/3/5, MX1/2, ISG15) | V3 module representative |
| `BBP398` | SHP2 inhibitor class (SHP099 / BBP-398) | A8 |
| `V1_ON` / `V3_ON` | Variant selector inputs | D3 |
| `VIABILITY` / `APOPTOSIS` | Cell-fate outputs (proliferation vs death) | from ref 4 viability/apoptosis readouts |

## Quantitative anchors (provenance only — never model parameters, per D9)

| Value | Context | Source → figure |
|---|---|---|
| ALE condensate Feret Ø: V1 542→790 nm; V3 606→870 nm | V1/V3 + ALECTINIB vs DMSO | user paper → Fig 2C |
| Condensate wall ~106→~75 nm under ALE | ALE shell morphology | user paper → Fig 2 |
| pTyr sites gained: V1 870 vs V3 1913 | V1/V3 active fusion | user paper → Fig 5 |
| Doses: ALE 100 nM, LOR 100 nM, CER 500 nM (4 h); SHP2i 0.5–10 µM (4 h); ganetespib 20/40 nM | acute treatments | user paper Methods; ref 2 Table 1 |
| pERBB3-Y1289 ~2× up under LOR in H2228 (V3) vs H3122 (V1) | LOR 4 h | ref 4 → Figs 4G–J |
| LOR-R H2228: LOR IC50 ~5× higher; SAP IC50 ~3× lower; AKT VIII re-sensitizes (LOR IC50 9.983 vs 75.96 µM) | chronic LOR 500 nM | ref 4 → Figs 7–8 |

Cell lines: NCI-H3122 (endogenous V1), NCI-H2228 (endogenous V3b), BEAS2B
(inducible), HEK293 (transient), LOR-R-H2228 (chronic LOR-tolerant).

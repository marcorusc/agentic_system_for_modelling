# Decisions log

Append-only. Every material modelling decision with rationale, evidence, and approval.
Decisions concerning network topology additionally cite evidence-report paths and
PMIDs once the literature reviewer has filed them (see D8; pending reports under
`evidence/reports/`).

---

## D1 — Scope cut for the first model (2026-08-19)

**Decision:** the first MaBoSS run uses a core network of ~29 nodes:
`ALK_CAT`, `ALK_CONFORM`, `SIGNALOSOME`, core scaffold (`SHC1`, `GAB1`, `PTPN11`,
`GRB2`, `IRS2`, `PIK3R1`), V1-pref module (`RAS`, `RAF1`, `ERK1`, `PIK3CA`, `AKT1`),
V3-pref module (`STAT1`, `IFIT1`), bypass (`ERBB3`, `ERBB2`, `EGFR`, `FAK`), `NAMPT`,
drug inputs (`ALECTINIB`, `LORLATINIB`, `CERITINIB`, `BBP398`), variant selectors
(`V1_ON`, `V3_ON`), fate (`VIABILITY`, `APOPTOSIS`).
**Named-but-unmodelled (first cut):** GUK1, PLCG2, CBL, CBLB, SOCS3, PD-L1, PDK1,
MYC, HRG, HSP90/CDC37 arm, proteasome arm, cell-cycle/DDR arm, PAK1, CTNND1,
BCAR1/3.
**Rationale:** state-space tractability + interpretability; the set covers all 8
committed validation targets (D4) and all 6 intervention scenarios (D6).
**Evidence:** user paper (`inputs/EA paper_v16_JS.pdf`) Figs 1–8; ref 2
(`inputs/embr.202153693.pdf`) Figs 1–7; ref 4 (`inputs/s41419-024-07272-7.pdf`)
Figs 1–8.
**Approved by:** researcher, 2026-08-19.

## D2 — Decoupling of assembly and catalysis (2026-08-19)

**Decision:** output rules (`ERK1`, `AKT1`) do **not** require `SIGNALOSOME = 1`.
We follow the user's own paper (SHP2i disassembles condensates while pAKT/pERK
persist) over ref 2's hexanediol result (V3 foci dissolution abolished pERK/pAKT),
because hexanediol has known off-target kinase/phosphatase effects — flagged by the
ref 2 authors themselves as a limitation.
**Consequence if false:** one-rule change (add `SIGNALOSOME` term to the output
rules); re-evaluate at the boolean-dynamics stage if validation targets T4/T5 fail.
**Evidence:** user paper Fig 8, S8H–J; ref 2 Fig 2E + limitations.
**Approved by:** researcher, 2026-08-19 ("follow my paper").

## D3 — Variant representation (2026-08-19)

**Decision:** one network with `V1_ON` / `V3_ON` selector inputs gating the
variant-conditional wiring at rule level. Fallback if rules become unmanageable:
two separate NeKo sessions (one per variant).
**Approved by:** researcher, 2026-08-19 ("start with one network first").

## D4 — Committed validation targets (2026-08-19)

**Decision:** commit to candidate targets 1–6, 10, 11 (recorded as rows T1–T12 in
`VALIDATION_PLAN.md`); HRG target (12) out of scope per D5. These are the targets
that gate rule refinement.
**Approved by:** researcher, 2026-08-19 ("totally fine by me what you chose").

## D5 — HRG out of scope for the first cut (2026-08-19)

**Decision:** no HRG ligand input in the first cut (matches the user paper's
no-stimulus design); HRG to be connected later if the core model validates.
**Approved by:** researcher, 2026-08-19.

## D6 — First intervention-scenario batch (2026-08-19)

**Decision:** (1) ALE vs LOR in V1 and V3; (2) LOR + SHP2i (`BBP398`);
(3) LOR + ERBBi; (4) LOR + AKTi; (5) LOR + ERBBi + AKTi (V3);
(6) resistance mutations `F1174L`, `R1275Q` via MaBoSS mutation analysis
(`K1150M`, `D1270N` as follow-up).
**Evidence:** user paper Fig 8; ref 2 Figs 3, 6; ref 4 Figs 3–8.
**Approved by:** researcher, 2026-08-19.

## D7 — Reference 5 status (2026-08-19)

**Decision:** Gonzalez-Martinez et al. 2024 (Nat Commun, "Oncogenic EML4-ALK
assemblies suppress growth factor perception and modulate drug tolerance") is NOT
in the evidence corpus. Its evidence will be fetched from PubMed via the
`literature-reviewer` later. Until then: the growth-factor-perception claim is not
modelled, and `inputs/s41419-024-07272-7.pdf` must never be cited for it (that file
is ref 4 — Sampson et al. 2024, Cell Death & Disease, DOI 10.1038/s41419-024-07272-7).
**Approved by:** researcher, 2026-08-19 ("ref 5 can be fetched from pubmed later").

## D8 — NeKo database selection (2026-08-19)

**Decision:** use the **OmniPath** database for NeKo network construction.
SIGNOR is down / unreachable on 2026-08-19.
**Approved by:** researcher, 2026-08-19 (direct instruction).

## D9 — Model form (2026-08-19)

**Decision:** qualitative Boolean network in MaBoSS. Drug / variant contexts are
fixed input nodes per simulation (one simulation = one context). No ODE/kinetics,
no invented parameters, no units beyond `{0,1}`. Every rule form will be tagged
`literature-derived` or `fitted-for-dynamics` when finalized.
**Rationale:** pipeline design (NeKo → MaBoSS → PhysiCell); matches the corpus'
qualitative acute-treatment design.
**Approved by:** researcher, 2026-08-19 (accepted pipeline + scope).

## D10 — Conformation as explicit nodes (2026-08-19)

**Decision:** split ALK into `ALK_CAT` (catalytic activity) and `ALK_CONFORM`
(assembly-competent conformation). ALECTINIB inhibits `ALK_CAT` but preserves
`ALK_CONFORM`; LORLATINIB/CERITINIB inhibit both. This is what makes the
alectinib vs lorlatinib vs SHP2i results (T1–T5) reproducible in one network.
**Evidence:** ref 2 Figs 3–6 (conformation/stabilization; PDB 3AOX/4MKC/4CLI);
user paper Fig 2 (ALE-enlarged, signal-depleted condensates).
**Approved by:** researcher, 2026-08-19 (accepted model design).

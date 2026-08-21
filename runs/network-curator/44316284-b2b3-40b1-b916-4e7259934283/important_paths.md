# Important paths — EML4::ALK core (D1 core, OmniPath)

NeKo session `44316284-b2b3-40b1-b916-4e7259934283` — axis/path inspection
results as reported by `network-curator` (2026-08-21). Source SIF: `Network.sif`
(73 nodes, 781 edges; 735 signed stim/inhib, 46 `bimodal`, 0 `undefined`).

| Axis | Query | DB support | Representative route |
|---|---|---|---|
| H1 scaffold | ALK→SHC1/PTPN11→GAB1/GRB2 | direct signed edges | `ALK→SHC1→GAB1→PIK3R1`; `ALK→PTPN11→GRB2→KRAS` |
| H2a V1 RAS-MAPK | ALK→ERK1 | present (4.4k routes) | `ALK→SHC1→GRB2→KRAS→RAF1→…→MAPK3` |
| H2a V1 PI3K-AKT | ALK→AKT1 | present (4.8k routes) | `ALK→SHC1→PIK3CA→PIK3R1→AKT1`; `SHC1→AKT1` |
| H2b V3 JAK-STAT | ALK→STAT1 | present (3.0k routes) | `ALK→JAK3→…→STAT1`; `ALK→STAT3→STAT1` |
| H2b V3 ISG | STAT1→IFIT1 | **absent** (IFIT1 isolated) | — (DB gap) |
| H5 bypass | ERBB3→AKT1 / EGFR→ERK1 | present (8.6k/12.1k routes) | `ERBB3→PIK3CA→PIK3R1→AKT1`; `EGFR→KRAS→…→ERK1` |
| H7 marker | ALK→NAMPT | **no direct edge**; via `MYC` only | `ALK→…→MYC→NAMPT` |
| H4 drug action | ALE/LOR/CER/BBP398→ALK_CAT/ALK_CONFORM/PTPN11 | **not representable** (drug nodes + ALK split) | — (Boolean layer) |
| H3 decoupling | ERK1/AKT1 require ALK_CAT, not SIGNALOSOME | **not representable** (abstract nodes) | — (Boolean layer) |
| H6b fate | dual-inhibition→APOPTOSIS | **not representable** (abstract fate node) | — (Boolean layer) |

## Not representable at the NeKo stage (database-derived edges only)

- **Abstract/conceptual nodes (D10, A3):** `ALK_CAT`, `ALK_CONFORM`, `SIGNALOSOME`,
  `VIABILITY`, `APOPTOSIS` — not knowledge-base entities; the DB has one `ALK`.
  Consequence: H1 gate, H3 decoupling, H6b cannot be edges; they are Boolean rules.
- **Drug nodes:** `ALECTINIB`, `LORLATINIB`, `CERITINIB`, `BBP398` — H4's
  conformation-specific split is a modelling abstraction that splits ALK into two
  nodes; impossible in a gene-based DB.
- **Variant selectors:** `V1_ON`, `V3_ON` (D3) — pure Boolean gates.
- **H1–H8 rule-level wiring generally** (AND/OR gates, variant-conditional routing,
  decoupling, drug–conformation action, adaptive bypass feedback, dual-inhibition→
  apoptosis, variant-dependent sensitivity): Boolean rules per MODEL_SPEC. NeKo
  supplies the substrate; MaBoSS assembles the logic.

## Notable database gaps (wiring required at the Boolean layer)

- `STAT1→IFIT1` (V3 ISG axis, T6/T7): `find_paths STAT1→IFIT1` → "No paths found";
  IFIT1 is present but isolated.
- `ALK→NAMPT` (H7): no direct edge; only route is `ALK→…→MYC→NAMPT` with `MYC`
  D1-listed as named-but-unmodelled; NAMPT otherwise isolated.

## Alias note

The network stores ERK1 as `MAPK3` (and ERK2 as `MAPK1`); gene-set checkers report
`ERK1` as "missing" purely as an alias-resolution quirk — the node is present and
reachable.

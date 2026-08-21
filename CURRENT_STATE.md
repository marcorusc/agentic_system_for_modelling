# Current state

## Scientific objective

A Boolean (MaBoSS) model of EML4::ALK variant signalosome signalling in NSCLC that
(a) recapitulates the researcher's findings across three papers (shared core
scaffold, variant-conditional output, decoupling of condensate assembly and
catalysis, conformation-specific ALK-TKI action, ERBB3/AKT adaptive bypass) against
the committed targets T1–T12, and (b) simulates the D6 intervention scenarios
(ALKi ± SHP2i, ALKi + ERBBi/AKTi, resistance mutations) to generate experimentally
testable predictions.

## Active stage

`topology` (stage `specification` complete — decisions D1–D10 approved 2026-08-19).

## Completed work

- 2026-08-19: Extracted full mechanistic / node / observable inventory from all
  three `inputs/` papers (user paper, ref 2 Sampson 2021, ref 4 Sampson 2024 CDD).
  Identified file-identity correction: `s41419-024-07272-7.pdf` is ref 4, not the
  ref-5 Nat Commun paper (D7).
- 2026-08-19: Drafted and finalized `MODEL_SPEC.md`; recorded decisions D1–D10 in
  `DECISIONS.md`, assumptions A1–A8 in `ASSUMPTIONS.md`, committed targets T1–T12 in
  `VALIDATION_PLAN.md`, and provenance/aliases/quantitative anchors in
  `DATA_DICTIONARY.md`.
- 2026-08-21: Topology stage — `network-curator` built the D1 core network in
  fresh NeKo session `44316284-b2b3-40b1-b916-4e7259934283` on **OmniPath** (D8)
  with policy `max_len=2`, `path_policy='one_shortest'`,
  `reuse_policy='discovered_paths'`, `only_signed=True`, `consensus=True`:
  **73 nodes, 781 edges** (735 signed stim/inhib, 46 `bimodal`, 0 `undefined`).
  H1/H2a/H2b (JAK-STAT) and ERBB/EGFR bypass scaffolds are DB-supported
  (`important_paths.md`); H1–H8 rule wiring, drugs, variant gates, and fate are
  not representable as NeKo edges (Boolean-layer work). NeKo history: state 0
  (initial) → state 1 (`complete_connection`), state_count=2. SIF exported for
  review; BNET/MaBoSS handoff NOT exported (gated on researcher sign-off).

## Session registry

| Specialist | Session ID | Stage | Status | Derived from | Handoff | Artifacts |
|---|---|---|---|---|---|---|
| network-curator | `44316284-b2b3-40b1-b916-4e7259934283` | topology | active | — | pending | `runs/network-curator/44316284-b2b3-40b1-b916-4e7259934283/` |

## Current artifacts and handoffs

- `inputs/`: 3 evidence papers + their `:Zone.Identifier` metadata.
- `runs/network-curator/44316284-b2b3-40b1-b916-4e7259934283/`: `Network.sif`
  (73 nodes / 781 edges, per-edge PMID provenance), `session_meta.json`,
  `important_paths.md`, `literature_queue.json` (P1: 325 unannotated edges;
  P2: 46 `bimodal` + 7 hypothesis-specific; P3: 3 Boolean-layer wirings);
  sha256 hashes recorded in `runs/index.json`.
- `evidence/`: no reports yet (literature-reviewer pass pending after topology build).

## Accepted conclusions

_(none yet — no model has been run.)_

## Warnings and failed approaches

- **SIGNOR database is down / unreachable on 2026-08-19** → use **OmniPath** for the
  NeKo stage (D8).
- **File-identity correction:** `s41419-024-07272-7.pdf` = Sampson 2024 Cell Death
  & Disease (ref 4), NOT the ref-5 Nat Commun paper. Do not cite ref 5 from it (D7).
- Hexanediol (ref 2) vs SHP2i (user paper) give opposite results for V3
  condensate→signalling coupling; resolved in favour of the user's own paper (D2/A2),
  re-test at dynamics stage via T4/T5.
- **Topology gaps (2026-08-21, session `44316284-…`):** `IFIT1` (T6/T7) and
  `NAMPT` (H7) are isolated in the substrate (`STAT1→IFIT1`, `ALK→NAMPT` absent
  from OmniPath) — wire at the Boolean layer. 46 `bimodal` edges have ambiguous
  direction; 325 of 781 edges lack PMID provenance (queue: `literature_queue.json`).
  ERK1 is stored as `MAPK3`, ERK2 as `MAPK1` (alias quirk — nodes present).

## Unresolved questions

- Ref-5 (Gonzalez-Martinez 2024 Nat Commun) evidence not yet in corpus — to be
  fetched from PubMed via `literature-reviewer` later (D7).
- MaBoSS update mode (synchronous vs asynchronous) and exact rule forms — deferred to
  the boolean-dynamics stage.
- Whether the core 29-node set reproduces T1–T12, or whether D1 named-but-unmodelled
  nodes must be promoted — deferred to the dynamics stage.

## Next action

Researcher decision on the built 73-node substrate: (a) keep as-is, (b) prune to
the D1 core, or (c) rebuild with `max_len=1`; plus approve/defer removal of the
46 `bimodal` edges and acknowledge IFIT1/NAMPT/H1–H8 as Boolean-layer wiring.
Then `literature-reviewer` over the P1/P2 queue (unannotated provenance,
contested edges) before requesting sign-off on the SIF. BNET/MaBoSS handoff
stays gated until that sign-off.

## Checkpoint

- Content checkpoint commit ID: `701e859`
  (`checkpoint(specification): EML4::ALK signalosome model specified — decisions
  D1-D10 approved, validation targets T1-T12 committed`), 2026-08-19.
  Staged: 6 scientific-state files, `runs/index.json`, 3 `inputs/` evidence PDFs.
  Excluded (untracked, generated): `inputs/*:Zone.Identifier`, `pypath_log/`.

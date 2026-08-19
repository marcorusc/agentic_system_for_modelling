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

## Session registry

| Specialist | Session ID | Stage | Status | Derived from | Handoff | Artifacts |
|---|---|---|---|---|---|---|
| _(none yet — NeKo session to be created)_ | | | | | | |

## Current artifacts and handoffs

- `inputs/`: 3 evidence papers + their `:Zone.Identifier` metadata.
- `runs/`: none yet (no NeKo session).
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

## Unresolved questions

- Ref-5 (Gonzalez-Martinez 2024 Nat Commun) evidence not yet in corpus — to be
  fetched from PubMed via `literature-reviewer` later (D7).
- MaBoSS update mode (synchronous vs asynchronous) and exact rule forms — deferred to
  the boolean-dynamics stage.
- Whether the core 29-node set reproduces T1–T12, or whether D1 named-but-unmodelled
  nodes must be promoted — deferred to the dynamics stage.

## Next action

Create a fresh `network-curator` NeKo session (**OmniPath** per D8), build the
approved D1 core network (~29 nodes) with the H1–H8 wiring, export a SIF for review
(BNET/MaBoSS handoff stays gated), then run the `literature-reviewer` over the
contested edges (variant-conditional wiring, TKI→bypass, decoupling) before
requesting researcher sign-off on topology.

## Checkpoint

- Content checkpoint commit ID: _(to be filled after the `checkpoint-model` skill
  records it)_

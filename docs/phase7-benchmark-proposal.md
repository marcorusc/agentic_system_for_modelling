# Phase 7 benchmark proposal — pending researcher approval

## Requested objective

The researcher proposed a cancer cell-cycle model compared with published models,
prioritizing substantial literature and experimental support over a particular cancer.
This document proposes a benchmark; it does not approve a scientific assumption,
mutate topology, create a session, or advance the specification stage.

## Candidate references

**Recommended for cell-cycle mechanisms: Sizek et al. (2019).** The 87-node model
connects growth signaling, cell-cycle regulation, and apoptosis. The authors report
comparisons with 34 knockout and 11 overexpression phenotypes. S1 Table documents
rules and their experimental support; S4 Table lists perturbation comparisons.
It is a general mammalian model addressing oncogenic PI3K, not a calibrated model
of a specific patient or cancer cell line. Some results use biased asynchronous
updates; MaBoSS equivalence must be demonstrated, not assumed.
Source: https://doi.org/10.1371/journal.pcbi.1006402
Access: publisher full text inspected; supplementary files not yet audited.

**Alternative for cancer-specific drug-response validation: Zañudo et al. (2021).**
The paper reports experimental testing of predicted combinations in ER-positive
breast cancer. Its authors supply MCF7 and T47D model rules and reproduction code.
This is attractive if drug response and proliferation are the priority; detailed
phase-by-phase cell-cycle validation would require checking its observable coverage.
Sources: https://pubmed.ncbi.nlm.nih.gov/34257082/
and https://github.com/jgtz/BreastCancerModelv2
Access: abstract and author repository documentation inspected.

## Proposed validation design

1. Audit exact source files, license, version, identifiers, rules, and evidence.
   Pin their hashes before import. Record unavailable supporting datasets.
2. Specify the biological scope and mathematical semantics in a reviewable draft.
   Distinguish reproduction of the reference from experimental validation.
3. Build a validation matrix identifying which experiments informed construction
   and which can serve as independent tests. Do not describe reused fitting data
   as independent validation. No claim of clinical validity or exhaustive review.
4. Predefine candidate baseline cycling/arrest outcomes and published perturbations.
   Confirm exact nodes, interventions, initial states, update scheme, and acceptance
   criteria from sources before requesting approval to run them. Do not invent
   physical units, rates, or a conversion from update steps to hours.

## Bounded dispatcher smoke operation

After specification approval and the explicit transition to network work, propose a
fresh NeKo session containing an exact source-derived topology for inspection.
Before launch, verify the supported import and signed-edge semantics and obtain
approval for that exact import. No automated connection repair or expansion is
proposed. Path-search policies are not applicable to an exact import unless the
chosen tool requires them; any such requirement must be resolved before execution.

The immediate operation should produce the existing review artifacts and a valid
handoff, with exact lineage and hashes, without advancing global state automatically.
A successful network smoke test is not completion of the biological validation.
Literature edge review, researcher approval, BNET export, and MaBoSS analyses retain
their separate existing gates. Phase 8 cleanup remains gated on the real operation.

## Next decision

Approve the Sizek reference as the starting benchmark for cell-cycle mechanisms,
or choose the breast-cancer alternative. Then audit source materials and prepare
the exact specification and import proposal. No scientific model is accepted yet.

## Researcher-supplied PhysiBoSS reference

The researcher identified their published Sizek-derived implementation:
Ruscone et al. (2024), Building multiscale models with PhysiBoSS, an agent-based
modeling tool. https://doi.org/10.1093/bib/bbae509
The full text describes a MaBoSS analysis and added phase readouts connected to
PhysiCell. It reports wild-type, PLK1/FOXO3 loss, and p110 activation examples.
Use this adaptation as a candidate reproduction reference, retaining Sizek as
upstream mechanistic provenance. Reproduction remains distinct from independent
experimental validation. No stage transition or mutation is authorized by this note.

### Version discrepancy to resolve before selecting parameters

- Article cell-cycle integration text: scaling 40, intracellular_dt 1 minute.
- Figure 2 caption: scaling 41, intracellular_dt 2.5.
- Current tutorial XML inspected on 2026-09-15: scaling 37.5,
  intracellular_dt 2.5, maximum simulation time 2880 minutes.

Current XML source:
https://raw.githubusercontent.com/PhysiBoSS/PhysiBoSS/master/sample_projects_intracellular/boolean/tutorial/config/cell_cycle/PhysiCell_settings.xml
Tutorial landing page: https://physiboss.github.io/tutorial/

The moving master branch is not yet a pinned reproduction artifact. Resolve the
paper-associated release/commit or supplementary archive, then hash the BND, CFG,
XML, initialization files, and analysis notebook together. Do not mix versions or
silently choose among these timing settings. The article confirms that a MaBoSS
adaptation exists; it does not establish equivalence with every Sizek update scheme.

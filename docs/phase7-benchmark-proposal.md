# Phase 7 — de novo construction benchmark

## Direction approved by the researcher

Construct a network from a biological gene pool comparable to Sizek, formulate a
Boolean model through the existing evidence and approval workflow, and compare its
behavior with Sizek and the researcher's PhysiBoSS implementation. This replaces
the earlier direct-SIF import approach. The failed import and timeout diagnosis
remain preserved as historical evidence; they are not the route forward.

Reference topology and logical functions are comparison material, not construction
inputs. The network specialist receives the approved genes, context, database, and
policies, without the reference SIF, BND, desired edges, or desired Boolean rules.
Keep reference outcomes in the orchestrator's evaluation record; do not ask evidence
reviewers to find support for desired conclusions. Any later fitting to reference
outcomes must be explicitly declared, approved, and separated from held-out tests.

## Reviewable gene pool

[Component map](phase7-gene-pool.csv): every one of the 90 labels in the pinned
PhysiBoSS reference has a proposed mapping or an explicit reason for exclusion.
[Draft request](phase7-construction-request.json): exact 60-gene first-pass pool
and proposed policies. All proposed symbols occur in the local reviewed-human
identifier table. This checks identifier availability, not biological equivalence.

Important naming checks:

- Model PDK1 in PI3K/AKT signaling is proposed as **PDPK1**, not the PDK1 gene.
  [NCBI PDPK1](https://www.ncbi.nlm.nih.gov/gene/5170).
- Caspase-activated DNase (CAD) is proposed as **DFFB**, not the CAD gene.
  [NCBI DFFB](https://www.ncbi.nlm.nih.gov/gene/1677).
- APC/C coactivator Cdh1 is proposed as **FZR1**, not CDH1/E-cadherin.
  [Primary FZR1/Cdh1 study](https://pubmed.ncbi.nlm.nih.gov/31318984/).

The source S1 Table's component descriptions were inspected for context:
https://doi.org/10.1371/journal.pcbi.1006402.s015
This is component mapping, not an adjudicated edge-evidence review.

Material representation choices are still **proposed**: examples include Cyclin A/B/E
as CCNA2/CCNB1/CCNE1, AKT states represented by AKT1, and PI3K activity represented
by PIK3CA. Multiple activity or transcript states collapse to one seed gene; this
does not imply that they should collapse to one variable in the later model.
Families and complexes with unresolved scope (ERK, MEK, RAF, RAS, SOS, IAPs, ORC,
mTOR complexes, APC/C, pre-replication complex, and RTK) are held out of the initial
pool. Their resolution is necessary before claiming comparable biological scope.
Growth-factor inputs, small molecules, replication states, and phase readouts are
not supplied as gene names. No receptor identity is invented.

## Proposed first construction

- Biological scope: human cell-cycle/growth/apoptosis mechanisms; no specific cancer
  line or patient calibration is claimed.
- Database: SIGNOR, to start from curated causal interactions.
- `path_policy=one_shortest`; `reuse_policy=none`; `max_len=1`;
  `only_signed=true`; `consensus=false`.
- `sif_file=null`; the explicit approved gene list is the input.
- Create a fresh session and record effective database/version/policies.
- First inspect requested-gene coverage, missing genes, components, signs, source
  references, and history. Do not silently drop missing genes or remove conflicts.
- Direct-edge-only construction introduces no intermediate connector genes. It may
  produce disconnected components; that is a finding to review, not permission to
  repair. Any later `max_len=2` expansion requires a separate impact proposal.

These policies, mappings, exclusions, and the transition to network work require
researcher approval. This document does not launch a specialist or advance state.

## Execution and validation sequence

1. Approve specification, gene mapping, and the exact first-pass request.
2. Construct and inspect the fresh network through the dispatcher; persist SIF,
   report, important-paths summary, literature queue, typed manifest, and handoff.
3. Review exact edge clusters, at most 13 edges per literature invocation, and
   obtain researcher approval of topology and evidence.
4. Export the gated NeKo-to-MaBoSS handoff. Define rule inference, outputs, initial
   states, rates, and perturbations explicitly before dynamics.
5. Compare predeclared qualitative cycling/arrest/apoptosis outcomes and selected
   published perturbations. Establish comparable update semantics and observables
   first. Model agreement is distinct from independent experimental validation.
6. After its own approval gate, compare PhysiBoSS configurations. The approved
   scaling **37.5** belongs to the reference comparison; it is not automatically a
   valid calibration for a newly inferred model. Simulation execution is outside
   the multicellular configuration specialist's claimed capabilities.

Phase 7's first technical success criterion is a real validated network operation
with observable progress, persisted artifacts, and no automatic global stage
advancement. Completing that check does not complete the biological comparison.
Phase 8 remains gated on a successful real operation.

## Reference provenance and current status

Sizek et al. (2019): https://doi.org/10.1371/journal.pcbi.1006402
Ruscone et al. (2024): https://doi.org/10.1093/bib/bbae509
Pinned comparison revision: `7180dffc72d3ce021b2eff385ff49735de5f02d8`.
[Reference file hashes and approved scaling](phase7-reference-manifest.json).
The old source-derived SIF is retained only as evidence of the superseded test.
Shared scientific state remains at specification. No new session has been created
for the revised approach. Next decision: review the 60-gene first-pass mapping and
SIGNOR policies, including the explicit omissions and isoform assumptions above.

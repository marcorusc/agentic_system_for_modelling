# MaBoSS_test: evaluation and possible MCP integration

Prepared: 2026-10-20.
Status: independent evaluation and design discussion, **not an implementation specification**.
Upstream: https://github.com/sysbio-curie/MaBoSS_test

This document is self-contained and may be copied into a fork/clone of MaBoSS_test.
It does not require access to the conversation or the agentic-modelling repository.

## Researcher direction

The researcher will fork and clone MaBoSS_test, examine its usefulness with another
agent, and decide whether and how to extend it. This work is separate from the
current MCP-server updates and may proceed in parallel.

The motivating idea is to make MaBoSS_test a reusable library for stating and
evaluating biological expectations, exposed through the MaBoSS MCP server.
This is a direction to investigate, not a decision to implement every feature below.
An outcome of “retain only a small useful subset” or “do not adopt this backend”
is legitimate if supported by evidence.

For now:

- Defer new standalone MaBoSS post-analysis scripts and the previously proposed
  direct MCP implementation of additional analysis algorithms.
- Preserve existing supported validators; do not delete or migrate them merely
  because this evaluation has started.
- Do not modify the MaBoSS engine or pyMaBoSS package. The researcher is not their
  maintainer. Use their supported APIs and identify upstream requirements separately.
- Do not make MCP integration or package publication part of the initial evaluation.
- Do not treat illustrative conditions or thresholds as approved biological claims.

## Why this discussion started

A modelling-workflow audit proposed fixed-point enumeration, reachable-attractor
analysis and invariant checks through the MaBoSS MCP server (item B-MB-6).
The agentic workspace already has bounded BNET-based structural validators.
Rather than introduce another analysis implementation immediately, the researcher
identified MaBoSS_test as a possible home for reusable model-validation semantics.

There are two related but distinct needs:

| Need | Example question | Evidence required |
|---|---|---|
| Evaluate simulated behavior | Does a perturbation increase a specified outcome probability at a specified time? | Suitable simulation results and explicit comparison criteria |
| Establish a structural property | Can any reachable state violate a stated condition? | A complete analysis under declared transition semantics, or a counterexample |

An adapter must not turn the first kind of result into a claim of the second kind.
Determine whether this package should address one or both needs; do not assume
that integrating it automatically implements the original B-MB-6 proposal.

## What was inspected

Primary source:
[MaBoSSTestCase.py](https://github.com/sysbio-curie/MaBoSS_test/blob/master/maboss_test/MaBoSSTestCase.py).
Inspected GitHub file blob: `b670adaec12b2f9189b0d2c2ab8baf577a0d694c`.
This is a file-content identifier, not a repository commit.

The inspected `setup.py` declared version `1.0.0a4` and a dependency on `maboss`.
Source:
[setup.py](https://github.com/sysbio-curie/MaBoSS_test/blob/master/setup.py).
These observations describe the inspected source, not the latest published
package or a guarantee about the future clone. Record the clone's commit and
reconcile differences before designing changes.

No package installation, engine execution or runtime reproduction was performed
for this brief. Findings below come from reading source and need focused validation.

The class extends Python `unittest.TestCase` and provides:

- `assertStateProbabilityEvolution`: compare a state probability between baseline
  and mutated simulations at their final reported time.
- `assertStableStateProbabilityEvolution`: compare probabilities associated with
  simulation-reported stable states.
- `assertStableStateProbability`: compare such a probability with a reference.
- `assertNodesDependencies`: check expected node values among reported stable
  states satisfying a condition.
- Helpers for initial conditions, output selection, mutation and result extraction.

The existing vocabulary uses dictionaries of node assignments and directions such
as increase/decrease/stable. It is not a general temporal-logic language or an
exhaustive model checker.

## Findings to validate before building an adapter

| Source observation | Implication | Suggested focused check |
|---|---|---|
| `getProbtrajStates` and `getStableStates` use probability values as dictionary keys. | Different states with equal probabilities can overwrite one another. | Preserve two equally probable states and verify both selection and aggregation. |
| Several verbose assertion paths catch failures and print messages; invalid-node and no-match paths can return early. | Normal function return cannot reliably mean that a condition passed. | Distinguish failed expectation, invalid input, missing evidence and successful evaluation independently of verbosity. |
| Assertion methods launch simulations internally and some select outputs on copied models. | A direct wrapper could run new experiments or change evidence projection unexpectedly. | Evaluate saved evidence without invoking the engine; make execution and output requirements explicit. |
| Comparisons truncate probabilities to a specified decimal precision. | Rounding behavior is being used where numerical tolerance, biological effect size and sampling uncertainty need separate meanings. | Characterize existing boundary behavior before proposing replacement semantics. |
| Mutable working simulations are reset on normal completion, but some paths return or raise earlier. | Repeated calls may retain previous mutations or settings; this needs reproduction. | Test sequential calls after invalid input and failed assertions, checking isolation. |

Also examine partial-state conditions, all-OFF conditions, empty fixed-point
results and absent output nodes. Do not silently interpret unavailable evidence
as probability zero. A statement that no sampled state violated a condition is
not proof that no reachable state can violate it.

## Candidate architecture

```mermaid
flowchart LR
    A[Researcher-defined condition] --> B[MaBoSS MCP adapter]
    B --> C[Select suitable persisted runs]
    B --> D[Explicitly authorized simulation]
    D --> C
    C --> E[MaBoSS_test evaluator]
    E --> F[Structured outcome and evidence report]
```

This is a proposal for discussion:

- **MaBoSS_test:** condition definitions, input validation, evaluation algorithms
  and structured outcomes. A compatible unittest facade may call the same evaluator.
- **MCP server:** model/session/run selection, authorized simulation execution,
  artifact persistence and concise tool responses. Keep domain algorithms in the
  chosen library rather than duplicating them in the adapter.
- **Agentic workflow:** gather researcher expectations, record approval and assess
  evidence against the scientific validation plan. It does not invent thresholds.

Prefer separating evaluation from execution. Saved results should be usable when
they contain the required evidence. If an evaluation needs additional simulations,
report the missing evidence and proposed experiment instead of silently running it.
A standalone convenience API could still compose execution and evaluation when
explicitly requested; its design is an open question.

## Related MCP work already approved

These are accepted requirements being assigned separately; do not assume they
are already implemented or released.

| Work item | Relevant integration expectation |
|---|---|
| W2-D008: summary readouts | Create summary nodes and edit their rules without feedback into the biological core; preserve ancestry and model revision. Readouts are simulated nodes, not instantaneous expressions. |
| W2-D009: rate access | Inspect configured expressions/parameters and explicitly edit selected-node rates through tools, preserving logical conditions and unrelated settings. |
| W2-D010: persistent runs | Save ordinary and mutant runs with unique IDs, exact executed inputs and generated outputs. Support historical inspection/plotting without overwriting artifacts or changing the base model. |

Repository: https://github.com/marcorusc/mcp-biomodelling-servers

Coordinate a result-input contract with that agent after deciding the package
scope. Avoid coupling MaBoSS_test to MCP transport, mutable session globals or one
specific artifact directory layout. Keep model revision, run identity and evidence
references available for reports.

## Questions to resolve with the researcher

1. **Useful first cases:** Which concrete biological questions justify maintaining
   this package? Start with a few representative conditions from actual workflows.
2. **Evidence scope:** Final-time probabilities, time series, reported fixed
   points, individual trajectories, comparisons across runs—which are needed first?
   Node marginals alone cannot determine a general joint-state probability.
3. **Condition vocabulary:** How are partial states, Boolean combinations, time
   windows, thresholds, comparisons and references expressed unambiguously?
   Any declarative syntax should be safely parsed, not executed as arbitrary code.
4. **Uncertainty:** What distinguishes numerical tolerance, meaningful effect size
   and statistical uncertainty? What makes a comparison inconclusive?
   Decimal truncation alone does not resolve stochastic uncertainty.
5. **Run comparability:** Which differences in initial conditions, perturbations,
   model revisions, outputs and simulation settings are intentional or disqualifying?
   No seed or replication policy should be silently chosen.
6. **Outcomes:** How should pass, fail, inconclusive, invalid input and execution
   errors be represented? What happens when no state satisfies the premise of a
   dependency check?
7. **Compatibility:** Which existing Python/unittest calls must retain behavior?
   Which misleading or incorrect behaviors require a documented change?
8. **Exact analyses:** Keep these outside the first release, or define a separate
   backend later? General asynchronous BNET analysis can differ from configured
   MaBoSS dynamics with zero rates, clamps or custom expressions.
9. **Distribution and integration:** What public API and supported versions should
   the MCP server depend on? Settle this after verifying package usefulness.

Temporal statements need particular care: “eventually activates on each
trajectory” differs from “activation probability exceeds a threshold at one
reported time.” Specify the intended statement and available evidence first.

## Suggested evaluation sequence

1. Inspect the clone, its instructions, documentation, examples and tests. Record
   its revision and identify differences from the source observations above.
2. Present a capability inventory: working behavior, reproducible defects, missing
   functionality and existing alternatives worth considering.
3. Choose representative conditions with the researcher and trace the data needed
   to evaluate each. Keep expected values and acceptance criteria explicit.
4. Propose the smallest useful public evaluation API and structured result format.
   Demonstrate their meaning with small fixtures, without claiming scientific validity.
5. Decide whether to extend the package, narrow its role or choose another route.
6. Only after scope agreement, prepare separate library and MCP implementation
   assignments, acceptance tests and compatibility notes.

Candidate acceptance checks for a future implementation include equal-probability
state preservation, deterministic handling of invalid/missing evidence, evaluation
without an engine call, run/model isolation, correct partial-state aggregation,
explicit time selection, uncertainty-aware outcomes under an agreed policy, and
an end-to-end saved-run evaluation through the MCP adapter.

## Starter message for the agent in the cloned repository

> Read this brief and the repository instructions. First assess whether MaBoSS_test
> is a useful foundation for declarative biological-model checks and eventual
> MaBoSS MCP integration. Verify the source findings against this checkout and
> inspect its examples, tests and public API. Present the smallest useful scope,
> defects with evidence, compatibility questions and decisions needed from me.
> This is initially an evaluation and discussion task: do not begin broad feature
> implementation, change MaBoSS/pyMaBoSS, publish packages, or replace existing
> workflow validators. Distinguish simulation evidence from exhaustive proofs.

## Decision log for the new discussion

Keep this section with the copied document. Record decisions and rejected
alternatives here so the handoff remains independent of chat history.

| Decision | Status | Rationale / evidence |
|---|---|---|
| Evaluate MaBoSS_test separately before assigning its extension | Accepted researcher direction | Determine usefulness and scope with the agent in the fork/clone |
| Integrate with the MaBoSS MCP server | Candidate direction | Detailed interface and implementation remain undecided |
| Add temporal conditions or exhaustive structural analyses | Undecided | Requires separate semantics, evidence and resource-limit discussion |

# Modelling system retrospective: capability, reliability and efficiency

**Date:** 17 September 2026. **Audited code:** `d5316cedd5d5ed566684a4408a46b5d31706fd22`, branch `model/cell-cycle-core`.

## Executive assessment

The system demonstrated the intended technical capability: isolated specialists constructed and curated a network, produced Boolean and mechanistic ODE representations, and executed both. The dispatcher architecture is worth retaining. Its main weaknesses are the amount of manual orchestration needed to finish a task, excessive context traffic, fragile artifact delivery, and the translation of researcher authorization into individual tool permissions.

**My assessment: a functioning, guarded research prototype that still needs active supervision.** The session supports confidence in several specific controls, particularly MCP namespace restriction, lineage recording, and preservation of failed alternatives. It does not establish unattended operational reliability, hermetic isolation, or biological correctness.

The LLM contributed useful scientific reasoning, but also spent substantial effort behaving as a file copier, state reconstructor, permission negotiator and report serializer. Improving those interfaces is a higher priority than adding more agents or asking for more reasoning.

This report separates observed incidents, source-code findings, and proposed improvements. It does not change scientific policy, model state, architecture or installed profiles.

## 1. Scope and evidence

The assessment uses this conversation, the six scientific source-of-truth files, dispatcher/runtime code, saved stage artifacts, 49 invocation provenance records, 42 dispatcher task records, and historical isolation/regression results. The inventory includes infrastructure probes and unsuccessful attempts, so its counts are not a scientific success-rate benchmark.

[metrics.json](metrics.json) contains per-invocation usage, duration, status, tool-result sizes, paths and source hashes. [collect_metrics.py](collect_metrics.py) reproduces that inventory without copying prompts, credentials or reasoning content into the report. It deduplicates invocation IDs and excludes duplicate temporary launcher directories without final provenance.

Important limits:

- Parent-thread token usage, all forked-conversation history, and usage lost with interrupted processes are not fully accounted for.
- Historical isolation tests and current source inspection establish specific controls, not a penetration test or proof against a hostile specialist/server.
- This was one evolving scientific example, with substantial human steering. It is not an independent evaluation suite.
- Current user-local configuration is not sufficient to reconstruct historical effective model settings.

## 2. What the system actually achieved

| Area | Demonstrated result | Remaining limit |
|---|---|---|
| Dispatcher implementation | Sequential architecture migration, live restricted-process checks, technical/scientific status separation, CLI fallback through the same runtime | Desktop activation and single-project ownership remain operational dependencies |
| Network construction | Approved gene-based SIGNOR construction, targeted curation, trial/rollback, final 62-gene/159-edge source topology | Database coverage and interaction semantics require judgement |
| Literature | Bounded primary-source reviews, immutable reports, explicit access and context limitations | Evidence is incomplete and some interpretations remain disputed |
| Boolean model | 62 unchanged rules executed in two MaBoSS fixtures | Logical rules/rates are an accepted representation, not fitted biology |
| Mechanistic ODE model | 305 reaction records, 188 states, 427 parameter entries, 421 independent parameters; two BioMASS fixtures executed | Placeholder values and accepted approximations; unresolved functional coverage |
| Comparison | Saved outputs and a reproducible side-by-side figure | No common calibrated time/amplitude scale and no biological model ranking |
| PhysiCell/PhysiBoSS | Isolation/infrastructure coverage only in this experiment | No downstream simulation demonstrated |

All four synthetic simulations completed. ODE outputs were finite; the tiny negative minimum, approximately −8.52×10⁻¹⁵, was retained. Boolean probabilities were finite and normalized within rounding tolerance. These are appropriate technical acceptance checks for the final scope you specified. They do not require experimental data. See the [technical experiment report](../../comparisons/technical-smoke-test-2026-09-17/README.md).

The original ambition to compare against published Sizek-based biology was narrowed to technical feasibility. That narrowing was legitimate. The architecture should have made the selected objective explicit earlier, rather than repeatedly treating a software smoke test as preparation for biological validation.

## 3. Where the session became difficult

### 3.1 Initial objective and orchestration errors

Several detours were my orchestration errors, not missing modelling capabilities:

1. **Reference topology versus de novo construction.** The first attempt imported the published SIF, although the useful experiment was to build from a comparable gene pool and then compare. You corrected this direction. The import also timed out after 300 seconds; that timeout does not prove that the seed count alone was the cause.
2. **Session continuity.** I initially treated an unknown live NeKo session as a continuity defect. Your intended design was already coherent: execute a complete bounded workflow through export, then import the artifact in a fresh session for later work. The repository now records that correction. Persistent live server sessions are not a required fix.
3. **Connector preview.** I initially focused too much on limitations of a dedicated preview tool. Existing targeted connection tools, inspection, history checkout and rollback were sufficient to make progress. A better dedicated preview remains a convenience, not a prerequisite.
4. **Evidence scope.** An evidence report should resolve ambiguous signs, uncertain mechanisms and connector choices. Treating every existing edge as a mandatory review backlog would have expanded this experiment unnecessarily.
5. **Approval granularity.** Repeated small approval packages delayed actual topology/model progress. Your request for one complete ODE candidate was the correct adjustment.
6. **Test scope.** Once you requested only executable models with placeholders, I should have treated that as an authorized technical experiment with an explicit fixture, without repeatedly importing the requirements of biological calibration.

These errors suggest a missing compact contract at the start of each job: objective, mode, approved inputs, permitted transformations, exact deliverables, and stopping conditions.

### 3.2 NeKo: useful capabilities, surprising semantics

The initial 60-gene network had 151 edges and disconnected genes/components. The tools could inspect those components and trial connectors. The difficult part was controlling and interpreting the resulting topology.

A bounded two-edge connector trial grew a 61-node/151-edge baseline to **182 nodes and 616 edges**. Of 465 added edges, 86 lay on the requested cross-group paths and 379 were collateral. The candidate also included eight bimodal effects and one complex-formation effect despite signed-only selection. The baseline was restored exactly and the broad candidate was not accepted.

That is a concrete mismatch between an intuitive request—connect these groups—and the wider topology returned by the backend. It is not evidence that all bounded path searches inherently need hundreds of collateral edges. The interface needs to distinguish candidate path discovery, closure over the enlarged network, and the exact patch selected for acceptance. Fixed backend path/reuse policies should be exposed as capabilities instead of requiring the orchestrator to invent configurable arguments that the method does not offer.

SIF continuation preserved topology only with a complete node list; isolated nodes and reference annotations are not fully represented by SIF. Imported references became the literal SIF placeholder. Hashed sidecars preserved the original evidence, but this is an avoidable interchange weakness. A canonical network bundle should include nodes, typed edges, annotations, source versions and policies; SIF can remain an export inside that bundle.

### 3.3 Literature: access and authorization friction

PubMed was not configured in the specialist environment. Your explicit authorization of primary-source web search allowed work to proceed. Some reviews then blocked because the child could not verify that its own launch had enabled that fallback. A separate launch-proof artifact and a replacement invocation resolved the issue.

That was a capability-transport problem: a permission already granted by the researcher and applied by the launcher was not clearly available to the specialist as trusted runtime metadata. It should be injected by the runtime, rather than rediscovered by the LLM.

Reviews were bounded and explicit about full-text versus abstract/indexed evidence. That is a strength. However, literature review was also the largest measured specialist input-token category. Repeated retrieval, broad page content and repeated source-of-truth reads need a source cache and compact evidence packets.

There is confirmed configuration drift: the installed literature profile still refers to `docs/ode-workflow.md`, while the implemented document is `docs/ode-specialist.md`. Source templates, installed profiles and plugin copies need a version/hash check.

### 3.4 BioMASS: the hard part was mechanistic representation

Signed gene edges do not specify reactions, molecular states, stoichiometry, kinetic laws, units or parameters. The separate BioMASS role and graph handoff correctly respected that distinction. The LLM was useful in proposing state-specific mechanisms, recognizing indirect effects, and separating evidence from hypothetical closure terms.

Important limitations surfaced:

- A CASP8 dimerization template generated an incorrect monomer balance in the first candidate. Inspection caught it and the generated revision was corrected with an explicit two-monomer reaction. Generation success alone was therefore insufficient.
- The backend's single-owner species mapping could not fully express a complex containing products of multiple genes. A separate molecular-composition register was necessary. This should be a first-class many-to-many mapping.
- The complete candidate retained four endpoint mismatches and nine unresolved interpretations. The final accounting was 84 represented edges, 62 indirect/combined, four mismatched, nine unresolved. An edge linked to a reaction is not automatically functionally represented.
- The candidate lacks some machinery needed to claim an autonomous biological cell cycle, including replication completion/division reset. This is a model-scope limitation, not a failure to execute the ODE engine.
- Reconstructing an approved model required repeated submission of large evidence and reaction records. Loading an immutable model bundle should be a deterministic backend operation.

Your consolidated approval covered the symbolic candidate. The later all-zero/all-one fixtures and unit placeholder parameters tested execution only. They did not resolve the scientific limitations above.

### 3.5 Reporting failed after useful modelling work had finished

This happened more than once. A network connector trial completed and rolled back, then stalled while reporting. The full ODE refinement generated/exported its model but suffered a websocket idle timeout before delivering its final handoff. Both original tasks remained cancelled, preserving the distinction between backend work and validated task completion.

Independent read-only recovery audits salvaged the exports without silently rerunning mutations. That is good provenance practice, but an expensive recovery path: the ODE recovery audit alone consumed 2.17 million recorded input tokens and about 15.9 minutes of specialist process time.

The system currently depends too heavily on one large final LLM message. It needs durable intermediate receipts for export/generation, followed by a small final manifest. Recovery should validate those receipts mechanically and only request scientific judgement for actual ambiguity.

### 3.6 Final smoke-test permissions and output contracts

The first ODE smoke attempt failed because I omitted `build_reactions` from the approved tool list needed to restore shared parameter aliases. The permission boundary worked; my tool-dependency planning was incomplete. That avoidable attempt consumed approximately 1.07 million input tokens and 3.9 minutes.

The corrected invocation then rejected redundant overrides of dependent parameters. Removing the duplicates preserved the approved values and sharing. An optional `visualize_model` call was denied; it was unnecessary to complete the requested simulations. These are examples of work that a validated workflow recipe should plan before an LLM starts a long job.

MaBoSS introduced a separate output issue: `result.csv` contained the final snapshot, while the full trajectory remained in a temporary raw file. The configured interval was 0–100, but the saved trajectory had 99 labels, 0–98. We preserved the raw trajectory and disclosed that discrepancy instead of inventing an endpoint. The API should explicitly distinguish final distributions, trajectories, actual time grids and durable export locations.

## 4. Specialist deployment and context isolation

### What is well isolated

The modelling specialists are fresh `codex exec` processes launched through fixed profiles. They are not same-conversation assistants inheriting the parent's dialogue. The runtime constructs a bounded task, starts a fresh invocation, restricts the permitted MCP server, disables built-in app connectors and recursive dispatcher access, and validates the configured inventory before execution. Unexpected enabled MCP names are rejected.

This is a meaningful improvement over asking an agent that sees every modelling tool to voluntarily use only one. Earlier tests exposed built-in connector leakage outside `codex mcp list`; explicitly disabling apps closed that known route.

### What is not isolated

| Boundary | Actual protection | Practical limitation |
|---|---|---|
| Parent conversation | Fresh invocation; no parent dialogue supplied by the launcher | Task text and repository files can still carry broad context |
| MCP domains | Matching server only; unknown enabled server names rejected; apps/dispatcher disabled | Configuration checks are not a trust audit of server implementation |
| Direct filesystem writes | Read-only child sandbox | Domain servers legitimately create artifacts through their own tool interfaces |
| Filesystem reads | Shared project and readable environment | No per-specialist mount or input-file allowlist; other reports/logs are accessible |
| Tool authorization | Exact named approval overrides; deletion/cleanup tools disabled | Not an argument-level proof that every mutation matches an approved scientific change |
| Scientific policy | Detailed instructions, typed handoffs, parent checks and approval records | Important parts still depend on LLM compliance and review |
| Identity/configuration | Fixed role, executable hash, inventory and task hash recorded | Effective model, reasoning effort and full profile hashes are missing from invocation provenance |

**Answer to “is each specialist's context well isolated?”:** the conversation and tool domain are separated; the information environment is shared. That is suitable for cooperative specialists on one trusted project, but should not be described as hermetic isolation or a multi-tenant security boundary.

`--ephemeral` prevents normal Codex rollout persistence; it is not itself a filesystem-isolation feature. This launcher deliberately records its own invocation logs. The runtime's shared working directory and inherited environment are visible in source. OpenAI's [non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode) also distinguishes ephemeral persistence, sandbox settings, required MCP startup and structured output.

### Deployment reliability and the new audit failure

During this audit, a native read-only helper agent failed to initialize its required `specialist_dispatcher` connection. No helper work occurred. This was separate from the successful scientific child-process route.

The manager enforces one dispatcher owner per project using an exclusive lock; the lock was held during the audit. That makes a second dispatcher startup a plausible explanation for the helper failure, but its generic initialization message does not establish the cause. Missing runtime dependencies or another startup problem cannot be excluded from that message alone.

The single-owner lease protects live jobs from a second manager's recovery logic. Keep that safety property. Improve client attachment and diagnostics: distinguish “another owner exists,” “SDK missing,” “bad environment,” and “server crashed.” A helper that does not need the dispatcher should not have to initialize it. If multiple clients are supported, they should attach to one owner rather than instantiate competing managers.

## 5. Robustness: strengths and unfinished guarantees

### Controls that earned confidence

- Isolation tests preceded routing migration; subsequent BioMASS support extended the restricted inventories.
- The dispatcher persists exact task text before work and records identity, configuration facts and failure artifacts.
- Execution state and scientific status are separate. Technical delivery of a blocked/failed scientific result is not relabelled scientific success.
- Completed artifact validation checks hashes, session paths, required exports, lineage identity and malformed results; missing files cannot establish completion.
- Restart handling fails interrupted work instead of automatically repeating mutations. Cancellation and exclusive ownership have regression coverage.
- Rejected topology alternatives, original failed handoffs and corrected model revisions were preserved.
- The six scientific state files remained parent-owned. Boolean and ODE representations retained separate provenance from a shared source topology.

### Why this is not yet an unattended platform

- **Completion depends on the parent.** Across the 42 dispatcher records, 39 are technically succeeded, two cancelled and one failed. The 39 successful deliveries contain 22 `needs_approval`, 15 `blocked` and two `failed` scientific statuses—zero `completed`. Some were intentionally blocked probes; others needed parent-side artifact persistence. These counts must not be interpreted as a 0% scientific success rate. They reveal an overloaded completion contract.
- **Approval and persistence are conflated.** `needs_approval` can mean scientific judgement is needed, or merely that a read-only child cannot write a report. The latter should be an artifact-finalization state owned by deterministic infrastructure.
- **Validation is partly structural.** Hashes and schema validation do not establish correct SIF semantics, Boolean truth tables, stoichiometry, evidence quality or a valid approval history. The parent performed additional checks, but those are not all reusable automated validators.
- **Review independence is limited.** The orchestrator often both synthesized the model and judged it. Existing documentation explicitly says Codex lacks the independent scientific/reproducibility review required by the separate Claude workflow; those Claude agent definitions are also missing. This experiment did not fix that legacy gap.
- **Liveness is not progress.** Heartbeats show that a process exists; they do not distinguish productive modelling from a reporting stall. There is no general per-job execution/output/token budget in the request contract.
- **Portability is partial.** The live result establishes this WSL environment. It is not a native Windows certification.

Current regression recheck results and their limits are recorded in [validation.md](validation.md). Historical passing tests remain evidence, but are not substituted for current results.

## 6. Tokens, latency and avoidable overhead

### Measured specialist usage

| Recorded scope | Invocations with usage / all records | Input tokens | Of which cached | Output tokens |
|---|---:|---:|---:|---:|
| All saved invocation records | 42 / 49 | 42,631,005 | 38,935,680 | 407,540 |
| Literature | 14 / 16 | 23,071,526 | 21,145,984 | 175,935 |
| ODE | 5 / 6 | 10,196,189 | 9,591,936 | 106,335 |
| Network | 18 / 22 | 7,935,375 | 6,978,048 | 110,337 |
| Boolean | 3 / 3 | 1,348,789 | 1,179,136 | 13,880 |
| Multicellular probes | 2 / 2 | 79,126 | 40,576 | 1,053 |

These are accumulated usage counters from saved JSONL events, not the size of one prompt or a claim that all tokens were unique. Cached input is included in input, not added to it. Approximately **91.3% was cached**, leaving **3,695,325 uncached input tokens** in this measured set. Recorded reasoning-output counters total 40,172 and are not added again to output.

Seven provenance records lack usable final usage events. The interrupted full ODE refinement is among the omissions. Parent-thread reasoning, approval discussions, software implementation and this audit are also outside these totals. Therefore these numbers are a partial accounting, not the total bill for the conversation. Subscription usage and dollars cannot be inferred reliably from them.

### The final smoke experiment

| Invocation | Input / cached input | Output | Child process duration |
|---|---:|---:|---:|
| ODE attempt blocked by missing tool grant | 1,066,612 / 995,200 | 5,563 | 234.9 s |
| Successful ODE two-fixture job | 1,419,285 / 1,300,096 | 10,345 | 429.2 s |
| Successful Boolean two-fixture job | 1,232,548 / 1,134,336 | 12,852 | 455.5 s |
| Total for these three child jobs | 3,718,445 / 3,429,632 | 28,760 | 1,119.6 s |

The four simulation tool calls themselves occupied approximately **16.4 seconds** of dispatcher-observed wall time: 13.75 seconds for the ODE calls and 2.63 seconds for Boolean calls. Native MaBoSS core runtimes were approximately 1.04 and 1.24 seconds. The remaining time includes reconstruction, configuration, checking, model calls, export and reporting—not all waste, but clearly the dominant cost. These sums exclude parent persistence, plotting and approval time.

The ODE bundle was exported at 05:13:46 UTC; the specialist finished at 05:17:04. More than three minutes followed the export. The earlier complete-draft invocation took 29.2 minutes and 4.59 million input tokens. Long final reporting is a material operational risk.

### Where the context traffic came from

The successful ODE smoke invocation emitted **5,035,989 serialized characters in completed MCP results**. Two `configure_model` results were about 0.99 million characters each; inspection and reaction submission each returned approximately 0.8 million. This measures JSON serialization of saved results, not unique biological content, exact wire bytes or tokenizer counts; duplicate text/structured representations may contribute.

The Boolean invocation emitted about 350,538 serialized result characters; the two visualization responses accounted for approximately 270,281. Images should be file/resource references for routine orchestration, with content loaded only when visual inspection is useful.

The bounded task prompts were relatively small—about 4.6 KB for the first whole ODE candidate. The larger problem was repeated tool-state output and the accumulated multi-call context, not simply an excessively long initial task. Broad document rereads and large final JSON reports added further traffic.

Current user-local defaults select `gpt-6-astra` with high reasoning effort; specialist profiles do not pin those fields. Invocation provenance does not record the effective values, so this snapshot cannot prove which model/effort every historical run used. Record both before attempting cost optimization or model comparisons.

## 7. Permissions: retain the boundaries, reduce the negotiation

The restriction on domain tools in the parent and other specialists is valuable. The missing `build_reactions` grant demonstrates a control doing its job, not a reason to grant every write tool. Likewise, destructive cleanup should remain unavailable during ordinary modelling.

The cumbersome part is manually translating one authorized workflow into a list of primitive tool names. Replace that fragile translation with a reviewed capability plan:

1. Identify the approved input artifact hashes and requested deliverables.
2. Resolve a versioned workflow recipe and all required tools before launch.
3. Check tool/schema availability and parameter constraints without creating model state.
4. Issue a runtime-readable authorization receipt for that bounded job.
5. Execute, validate the actual changes against the scope, and persist outputs.

The researcher should approve scientific consequences: topology, mechanistic assumptions, new experiments or changes of scope. Routine hashing, copying, reconstruction from an explicitly approved artifact, and already-authorized fixture execution should not generate new scientific approval questions.

Two explicit modes would help: **technical experiment** and **scientific modelling**. Both retain lineage and honest labelling. The former can use researcher-authorized synthetic fixtures without claiming biological meaning; the latter requires the appropriate evidence, units, quantity provenance and validation design. These modes are proposed architecture, not a relaxation silently applied by this report.

## 8. Are we using the LLM effectively?

**Partly. The reasoning capability is useful; its deployment is inefficient.**

Good uses observed here included reconciling ambiguous interaction signs, distinguishing phosphorylation from activation, proposing explicit molecular states and reactions, identifying missing mechanisms, explaining evidence limitations, and comparing the meaning of Boolean probabilities with ODE amounts.

Poor uses included resending complete reaction/evidence collections to reconstruct identical state, manually assembling manifests and copy scripts, inferring missing tool dependencies, rediscovering launch permissions, repeatedly reading long histories, and serializing enormous final responses. These should be deterministic operations with compact results.

More agents alone would amplify this overhead. Useful additional delegation would be independent read-only criticism of a completed mechanism draft, limited evidence retrieval, and reproducibility review. The author should not be the only critic. Parallelism should follow the dependency graph: independent evidence slices can run concurrently, while topology mutations and acceptance remain controlled. Independent Boolean/ODE execution could be parallelized in a future explicitly revised policy; the current sequential rules and manager limits do not authorize it automatically.

Different model/effort settings might suit routine extraction versus difficult mechanism synthesis, but that needs an evaluation on these actual tasks. The first efficiency improvement should be smaller tool responses and deterministic artifact operations, not an untested assumption that a cheaper model will handle the same fragile workflow reliably.

## 9. Prioritized changes

| Priority | Change | Concrete acceptance criterion |
|---|---|---|
| P0 | Compact backend responses with artifact references, pagination and requested field selection | Replaying the same approved smoke job preserves all outputs while eliminating repeated full-model dumps; measured token and payload reduction |
| P0 | Deterministic artifact finalizer and durable operation receipts | Killing the child after export still leaves independently verifiable outputs; no extra LLM job needed only to copy/hash/persist them |
| P0 | Workflow capability/dependency preflight | Missing `build_reactions` is detected before any session is created; no surprise approval denial halfway through an approved recipe |
| P0 | Resolve dispatcher client ownership/startup diagnostics and the current SDK test stall | Two supported clients behave predictably; unnecessary helpers do not fail on dispatcher initialization; bounded protocol tests terminate |
| P1 | Canonical rich network/model checkpoint import/export | Fresh-session round trip retains isolates, annotations, reaction/species mappings, aliases and artifact lineage exactly |
| P1 | Backend semantic regression fixtures | Catch CASP8 two-monomer loss, connector collateral expansion, signed-effect ambiguity and MaBoSS trajectory/snapshot confusion |
| P1 | Separate execution, artifact and scientific-decision status | A completed export awaiting automatic persistence is distinguishable from a model awaiting researcher approval |
| P1 | Trusted job context and approval ledger | Child receives the effective backend/mode/permissions and exact approved artifact revisions; no self-verification permission loop |
| P1 | Usage and configuration observability | Each task records model, effort, profile/tool-schema hashes, input/cache/output usage, tool durations and finalization time; interrupted usage marked incomplete |
| P1 | Consolidated decisions and independent read-only review | One full candidate/change package per consequential choice; checks independently flag planted semantic defects |
| P2 | Profile/plugin drift checks and a compact active-state view | Installed references resolve; source and installed versions are visible; specialists retrieve only relevant current state plus cited history |
| P2 | Reusable evaluation suite and resource budgets | Track task completion, researcher corrections, retries, token cost and elapsed time across multiple networks and failure injections |

“P0” means the next operational work, not that every item is a security vulnerability. Most changes belong in the dispatcher/backend interfaces rather than longer prompt instructions.

### A simpler target workflow

```mermaid
flowchart LR
    A[Research objective and approved scope] --> B[Validated workflow and capability plan]
    B --> C[Fresh specialist with bounded inputs]
    C --> D[Domain tools and durable operation receipts]
    D --> E[Automatic artifact persistence and checks]
    E --> F[Compact result and independent review]
    F --> G[Researcher decision when needed]
```

Keep the fresh-process specialist design, artifact-based continuation, domain separation and researcher control of scientific decisions. Simplify the machinery around them. Avoid solving these problems by adding persistent live sessions, granting every specialist every tool, or demanding more frequent user approvals.

## 10. Recommended next implementation slice

The most useful bounded follow-up would replay the **same already-defined technical experiment** through improved interfaces, with no new biology:

1. Add compact responses and immutable bundle loading.
2. Preflight the complete tool dependency set.
3. Persist outputs and manifests automatically with durable export receipts.
4. Return a small typed result separating execution, persistence and scientific status.
5. Compare artifact identity, numerical outputs, token usage, permission interruptions and elapsed time against this recorded baseline.

This gives an objective measure of architectural improvement. A successful target is identical approved model content and equivalent recorded results, with fewer manual interventions and substantially less context traffic. It is more informative than adding another complex model immediately.

## Evidence map

- [Dispatcher design and phase validation](../../specialist-dispatcher.md); [ODE isolation extension](../../ode-specialist.md).
- [Handoff contract and explicit validation limitations](../../handoff-validation.md).
- [Artifact-based continuation, preview correction and serialization incident](../../neko-curation-continuity.md).
- [Current scientific state and incident chronology](../../../CURRENT_STATE.md); [researcher decisions](../../../DECISIONS.md).
- [Final ODE review and coverage](../../../runs/ode-dynamics-modeler/41d7191b-abc5-41d0-bac0-74d6392f0b8a/model-review.md).
- [Smoke-test protocol, results and reproduction artifacts](../../comparisons/technical-smoke-test-2026-09-17/README.md).
- [Launcher restrictions](../../../scripts/codex/launcher_config.py), [execution/provenance](../../../scripts/codex/specialist_runtime/executor.py), [operational event projection](../../../scripts/codex/specialist_runtime/events.py), [dispatcher ownership/concurrency](../../../scripts/codex/dispatcher/manager.py).
- [Measured operational inventory](metrics.json) and [current audit validation](validation.md).

**Overall conclusion:** the experiment proved that this architecture can support substantive modelling work and execute both representations. It also showed that stronger reasoning is not the main missing ingredient. The next gains should come from precise tool contracts, smaller results, automatic artifact handling, explicit authorization scope, and independent checks at meaningful decision points.

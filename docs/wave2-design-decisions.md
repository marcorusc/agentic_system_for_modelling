# Wave 2 design discussion and decision record

Discussion opened: 2026-10-20 (researcher timezone: Asia/Tokyo).
Status: recording accepted requirements and remaining proposals; implementation
dispatch waits until the researcher finishes the discussion and assigns agents.

This records software-design choices for the remaining improvement-plan items.
It is separate from `DECISIONS.md`, which records decisions about an active
scientific model. No scientific session, topology, parameter or stage is approved
by this document. The original diagnostic tables remain historical evidence;
each implementation task will need reconciliation against the accepted source.

## Accepted scope and process

| ID | Researcher decision | Consequence |
|---|---|---|
| W2-D001 | We may modify the MCP servers, NeKo and PhysiCell Settings. We must not modify MaBoSS or pyMaBoSS packages, which the researcher does not maintain. | Implement MaBoSS-related capabilities in the MCP layer using supported existing APIs and configuration. Any requirement that actually needs an engine/package change must be identified separately and cannot be assigned as an implementation task within this scope. |
| W2-D002 | Discuss each area, record decisions, then the researcher will distribute implementation among agents. | Proposals below remain pending until explicitly accepted. Do not dispatch implementation agents or change package code during the discussion. |
| W2-D003 | Permit explicitly approved, literature-supported manual interactions even when absent from the selected database, provided their manual origin is recorded. Include PubMed IDs when available. | Preserve resource-backed construction separately. Manual provenance is mandatory; a PMID is optional and must never be invented. A missing PMID does not make an interaction database-derived. Keep scientific use subject to explicit authorization. |
| W2-D004 | Accept the compact-tool approach proposed for Wave 2. | Prefer extending coherent existing interfaces, one focused interaction editor with explicit add/effect-change operations, concise schemas and bounded results. Measure context/discovery effects; retain specialist isolation and consider client-supported task subsets/deferred discovery. No arbitrary tool-count limit or unrestricted generic executor is approved. |
| W2-D005 | Assign the interaction-curation work to agents working on NeKo and the MCP servers. | NeKo owns validated mutations and durable provenance; MCP owns exposure, truthful responses and interface efficiency. The researcher will distribute the work after discussion. |
| W2-D006 | Include explanations of automatic topology growth for reproducibility and verifiability. Track how the topology emerged through NeKo's existing history, state checkout, graph export and visualization capabilities. | Extend the existing state graph and metadata rather than introducing a parallel history system. Record why interactions were introduced, preserve branches and bind explanations to exact states. Reuse existing MCP history interfaces where possible. |
| W2-D007 | Track only the database name for resource identity in Wave 2. Defer version and download-time tracking and other detailed resource metadata until needed. | Record the selected resource, such as SIGNOR or OmniPath. Do not add resource-release discovery, acquisition/cache timestamps, dataset fingerprinting or database-snapshot capture in this work. This narrows B-NK-6 and supersedes the broader resource-metadata proposal. |
| W2-D008 | Keep summary readout-node creation and modification of their Boolean rules in the MaBoSS MCP server. These nodes summarize effects rather than introduce biological routes. | Provide a bounded readout extension using existing MaBoSS/pyMaBoSS APIs. Preserve the biological core, upstream ancestry and exact-revision approval. Output selection remains distinct; transition-rate access is covered separately by W2-D009. |
| W2-D009 | Provide tool-based inspection and explicit editing of activation/deactivation rates for named MaBoSS nodes, including readouts. Agents should not need to inspect model files to obtain rate information. | Return concise, structured rate information from the active model, preserve existing settings unless explicitly edited, and record effective configuration in simulation inputs. Reuse coherent interfaces where practical; implementation stays in the MCP repository. |
| W2-D010 | Persist ordinary and mutation simulations through shared run storage, support explicit run selection for inspection/plotting, and prevent plot/result overwrites. | Extend existing MCP tools and preservation helpers. Preserve exact executed inputs, generated outputs and run identity; keep the base model unchanged by mutation experiments; permit historical inspection after restart without rerunning simulations. |
| W2-D011 | Defer B-MB-2, the NeKo-to-MaBoSS import/handoff reliability investigation; the researcher will investigate later. | Do not assign this investigation now or mark the historical failure resolved. Move the discussion to B-MB-6. |
| W2-D012 | Redirect B-MB-6 discussion toward extending MaBoSS_test and integrating it with the MaBoSS MCP server; defer separate new MaBoSS post-analysis scripts while assessing this route. | Preserve existing validators. The detailed MaBoSS_test extension, semantics and integration contract remain pending discussion; no implementation or migration is assigned yet. |
| W2-D013 | Separate MaBoSS_test evaluation into its own discussion; the researcher will fork/clone the repository and transfer a standalone brief to another agent. | Use the portable evaluation brief below. This work may proceed in parallel; no MaBoSS_test implementation is dispatched from this discussion. |
| W2-D014 | Expose existing PhysiCell Settings support for output steepness, cycle transitions and fractional time stochasticity through the PhysiCell MCP server. | Extend coherent existing tools where practical, preserve omitted defaults and return stored values. The researcher may assign this bounded work to the MCP-maintenance agent. |
| W2-D015 | Focus the current discussion on implementation; defer the broader testing campaign and mapping-validation feature discussion. | Do not make benchmark reruns or new analysis/testing features prerequisites for discussing implementation. Necessary developer checks remain part of coherent changes; existing validation and scientific approval gates remain intact. |
| W2-D016 | Provide typed user-parameter editing/inspection and configuration of existing initial-cell CSV files through PhysiCell MCP; defer placement generation. | Reuse supported Settings APIs, return stored values and make combined count/CSV initialization visible. Do not automatically alter cell counts when enabling CSV or assume arbitrary user parameters are interpreted by the executable. |
| W2-D017 | Export a portable PhysiCell configuration bundle containing XML and its supported input dependencies, with provenance and portable references. | MCP owns packaging/session provenance using Settings serialization. Preserve session state and previous exports; exclude executables, compilation and engine installation. |
| W2-D018 | Preserve the required substrate for PhysiCell compatibility. The researcher reports that an empty substrate configuration crashes the software and breaks dependent interaction/parameter lookups. The revised default-visibility and readiness proposal is accepted for assignment to the Settings and MCP agents. | Withdraw the proposed empty-substrate export mode. Keep the required default and dependent configuration consistent, expose its origin/values and recognize it in readiness bookkeeping. Distinguish “no biological substrate of interest” from zero substrate entries. |
| W2-D019 | Implement compact MCP inspection improvements for PhysiCell stored parameters/behavior names and MaBoSS readable rules/effective configuration/output visibility. | Extend existing tools with targeted results. Preserve model rules, numerical defaults and scientific selections; do not automatically enable stationary-distribution calculations or change output nodes. |
| W2-D020 | Implement the bounded NeKo diagnostics/documentation cleanup for B-NK-2/3/5/7. | Distinguish import from construction, document actual resource-specific consensus semantics, report identifiers/counts/path outcomes correctly and identify invalid export labels. Split ownership between NeKo and MCP; preserve topology policies, defaults and identifier mappings. |

Authority: the researcher's message on 2026-10-20 stating the maintenance boundary
and requesting discussion and a decision record before distributing the work.
W2-D003–005 follow the subsequent approval: "yes, as long as it is mentioned that
it was manually added (and maybe populate the field with the pubmed id when
available)" and "I also approve you suggestion for wave 2", with work assigned
to agents responsible for NeKo and MCP servers.
W2-D006 follows the researcher's confirmation that topology-growth explanations
are required and that NeKo already supports network-state history, checkout and
state-graph export/visualization.
W2-D007 follows the researcher's instruction to track "just ... the database name
and that's it" and defer version/download-time work to avoid unnecessary effort.
W2-D008 follows the researcher's clarification that a readout summarizes effects,
can be added and have its Boolean rule modified, and "should stay in the MaBoSS
mcp server".
W2-D009 follows the researcher's acceptance of rate configuration with the condition
that rate information be accessed through tools rather than inspecting CFG files,
to reduce agent work and context use.
W2-D010 follows the researcher's acceptance of the shared persistence, run-selection
and unique-plot proposal and request to record it for assignment to the MCP agent.
W2-D011 follows the researcher's request to skip the handoff investigation for now
and discuss B-MB-6 instead.
W2-D012 records the researcher's proposed MaBoSS_test direction and preference to
defer separate post-analysis development if this route is adopted. The inspection
supports discussing that route; it does not establish feature completeness.

Changes to PhysiCell/PhysiBoSS engines, random-stream algorithms, publication,
scientific defaults and additional repositories are not authorized by this scope.
Necessary agentic-workflow integration changes should be identified in task plans
and discussed explicitly. Decisions about software capabilities do not waive
researcher approval for their use on a scientific model.

## Discussion agenda

| Area | Items to examine | Decision status |
|---|---|---|
| NeKo editing and provenance | B-NK-1: explicit interaction additions/sign changes. B-NK-2/3/5/7: truthful diagnostics and identifier handling. B-NK-4/6 and remaining C-NK provenance/documentation work: explain network growth and expose resource metadata. | Manual-edge policy and compact editing accepted (W2-D003–005); topology-growth history accepted (W2-D006); database-name-only identity accepted (W2-D007); diagnostics/documentation cleanup accepted (W2-D020). Reconcile assignments with the agents' current implementations. |
| MaBoSS reproducibility and readouts | B-MB-1: readout semantics and lineage. B-MB-2: investigate import failures. B-MB-3/4: persistent mutation runs and unique artifacts. B-MB-5/6: existing-engine rate configuration and analysis capabilities. Remaining metadata/documentation items. | Readout editing, rate access and persistent runs accepted (W2-D008–010); B-MB-7/8/9 inspection improvements accepted (W2-D019). Import investigation deferred (W2-D011); analysis moved to separate MaBoSS_test evaluation (W2-D012/013). No MaBoSS/pyMaBoSS package changes. |
| PhysiCell configuration | Remaining MCP portions of B-PC-1/2/4/6, initial cells/user parameters, portable project export, substrate handling and mapping validation. Reconcile already completed library and lineage work before assigning tasks. | Configuration extensions, user parameters/CSV, portable bundles and required-substrate visibility accepted (W2-D014/016–018); B-PC-1/9 inspection scope accepted (W2-D019). Broader testing and mapping-validation discussion deferred (W2-D015). |
| Analysis ownership | Decide whether existing artifact-validation calculations remain orchestrator checks, are also exposed through MCP, or need a shared implementation. Define the approved scope before any ODE extension. | Separate MaBoSS_test evaluation (W2-D012/013); preserve existing validators and defer new standalone post-analysis development. Detailed replacement/integration scope remains undecided. |
| Release boundary | Decide whether the selected Wave 2 fits the next coordinated release or follows a separate Wave 1 release. Resolve official NeKo metadata and dependency alignment before publication. | Resolved 2026-10-21: the MCP-side Wave 2 work shipped in `mcp-biomodelling-servers` 2.5.0 (NeKo 1.10.2, PhysiCell Settings 0.6.3). Wave 1 and the Wave 2 workflow adoption ship together as agentic-system release 1.0.0 against that backend set. The researcher's request: "a new version of the mcp servers have been release which includes all the features … let's work on a new release of this agentic system." Deferred items (W2-D011–013, D015) remain deferred. |

## First proposal: explicit NeKo interaction editing (B-NK-1)

Status: manual-edge policy and compact interface approach **accepted** under
W2-D003–005. The scope does not include new custom-node semantics or evidence-free
hypotheses; implementation details must preserve the boundaries below.

Problem: the benchmark required hand-edited SIF files to add specific interactions
and change a sign. The inspected MCP interface exposes removal but lacks matching
dedicated addition/sign-change tools. NeKo already has a low-level `add_edge`
method; whether it needs a stronger public mutation API is an implementation
question, not permission to bypass its internal consistency requirements.

Implementation requirements and scope boundaries:

1. Provide distinct operations for adding an interaction and changing the
   effect of an existing interaction through one focused editing interface.
   Separate operations do not require separate tool names.
   Do not silently overwrite a conflicting edge.
2. Require explicit source/target identifiers resolving unambiguously to existing
   nodes. Missing endpoints require a separate explicit node-addition operation;
   editing an edge must not silently expand or reconnect the network.
3. Require rationale and explicit provenance/evidence information. Preserve the
   original evidence separately from the justification for the edit. Mark manual
   additions explicitly and record PubMed IDs when available. Exact field names
   are implementation details to align across packages; existing provenance
   categories must not be silently redefined. Evidence-free hypotheses remain
   outside the approved scope.
4. Preserve the before/after edge state and edit history, keep library node/edge
   representations consistent, and invalidate exports/approvals tied to an older
   model revision. Editing alone never exports or approves a new handoff.
5. Keep each operation within the researcher's explicitly authorized mutation
   scope. An API capability is not scientific permission to use it autonomously.

The initial editing scope uses existing endpoints; custom-node admission is a
separate design question. Approval of manual interactions does not authorize
automatic node creation or connection completion.

## Database restrictions and tool discoverability discussion (2026-10-20)

Researcher concerns: original NeKo behavior may reject nodes/interactions absent
from its database; adding many MCP tools may impair discovery and consume context.
These concerns led to the revised approach accepted in W2-D003–005 below.

### Source inspection findings

Inspected the accepted official NeKo revision
[`673875d09e4c49c97d0d760d3ea85bd2603efc82`](https://github.com/sysbio-curie/Neko/blob/673875d09e4c49c97d0d760d3ea85bd2603efc82/neko/core/network.py):

- Ordinary `add_node` checks the resource database and returns `False` if no
  accepted identifier is present. Its SIF-import path allows unmapped labels.
- Low-level `add_edge` derives the sign from supplied interaction fields and
  appends/consolidates the supplied edge. It does not look up the exact directed
  interaction in the resource database. Resource-driven connection methods are
  a different path from directly supplying an edge.
- `add_edge` calls `add_node` for missing endpoints without checking its Boolean
  result. This must not be exposed as a validated manual-curation interface.
  A focused regression should establish the behavior on a rejected endpoint.

Inspected the accepted MCP revision
[`0e3f7fcd542d3d8047d27e04a6e9765b59e06b49`](https://github.com/marcorusc/mcp-biomodelling-servers/blob/0e3f7fcd542d3d8047d27e04a6e9765b59e06b49/NeKo/server.py):

- `add_nodes` increments its success counter without checking `add_node`'s return
  value. A database rejection can therefore be counted as an addition. Record this
  as a correctness issue to verify and address in a later authorized task.
- `NeKo/server.py` has 27 static `@tool` declarations. This is a source count,
  not a measurement of the tool schemas loaded by a particular client or a total
  server inventory: imported modules also register tools, including history tools.

### Revised approach accepted in principle (W2-D003–005)

Separate the scientific provenance policy from the MCP interface:

- Retain resource-backed construction behavior. Provide a separately explicit,
  researcher-authorized curation operation for literature-supported interactions
  absent from that resource. Such an edge must not acquire a database provenance
  label. Manual-origin identification is required and available PubMed IDs should
  be retained. Custom nodes and evidence-free hypotheses remain outside this scope.
- Use one focused interaction-editing tool (working name `edit_interactions`) with a small, strictly typed set
  of operations such as `add` and `set_effect`, instead of one new tool per edit.
  Preserve operation-specific authorization and validation. Do not collapse
  unrelated capabilities into an unrestricted generic executor or remove existing
  tools as part of this proposal.
- Measure schema size, representative result size, tool-selection errors and
  required call count before and after any interface change. Fewer names alone
  do not establish lower context use or better discovery.
- Keep specialist server isolation. Consider task-specific exposure of tool
  subsets where the client supports it, with essential inspection available and
  no expansion of mutation permissions. This is an integration proposal, not an
  assertion that the current runtime filters every task's tool set.
- Prefer concise schemas, clear names and bounded/paginated results. On-demand
  tool loading is client-dependent and cannot be assumed from MCP support alone.

Sources for the discovery tradeoff: [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
defines discovery and schemas; [Anthropic's tool-use engineering discussion](https://www.anthropic.com/engineering/advanced-tool-use)
describes context costs, overlapping-tool selection failures and deferred loading.
No client-specific token measurement or live modelling operation was performed.

## Topology emergence through existing history (B-NK-4; W2-D006)

Status: **accepted requirement**; implementation remains for the assigned agents.

Source inspection confirms NeKo already provides `save_state`, `checkout`,
`undo`/`redo`, `compare_states`, `list_states`, `history_graph`, `history_digraph`
and `history_html`. `NetworkState` contains node/edge snapshots, metadata and
parent/child relationships. The MCP server already exposes
`list_network_history`, `navigate_network_history`, `compare_network_states`,
`set_network_history_limit` and an HTML/SVG history resource. Reuse these interfaces.

Extend the existing history with structured explanations tied to each state and
its parent transition:

- Exact nodes/interactions added, removed or changed, including effect changes.
- The operation and effective construction policies/parameters that caused the
  change, not only the supplied arguments when defaults were omitted.
- The selected seed-to-seed path or other actual inclusion reason responsible
  for each automatically added interaction. Allow multiple supporting reasons
  where applicable; never invent a unique path after the fact.
- Manual-origin labels, rationale and available supporting references for manual
  changes, preserved separately from original database evidence.
- Branch relationships and the current state, so checkout and subsequent edits
  retain distinct alternative histories.

Current automatic metadata records method names and display-formatted arguments;
some representations are truncated. Keep concise labels for visualization, but
store the authoritative structured details without display truncation in the
history artifact. Explanations should link from the existing visualization and
inspection results, with large details available separately rather than inserted
into every tool response.

Implementation acceptance criteria:

1. Construct a small fixture, apply a connection operation and a manual edge,
   then verify each changed edge is attributable to its actual operation, path
   or manual rationale in the corresponding state transition.
2. Checkout the preceding state and create an alternative branch. Compare both
   branches and verify exact topology, identifiers and associated evidence; check
   consistency of both DataFrame and object representations after navigation.
3. Export a human-readable state graph and machine-readable history with the
   required snapshots/metadata. Load the supported saved representation and
   verify the same graph relationships and topology/provenance for retained
   states. A visualization alone is not sufficient restoration evidence.
4. Historical/imported states without reconstructable inclusion reasons report
   that limitation explicitly. If history was pruned, preserve/report available
   ancestry and gaps; do not claim a complete history. Existing retention behavior
   is not silently changed or used to authorize deletion.

State recovery and replay are distinct: recovering a stored topology does not
prove that rerunning construction against a changed database produces it. Under
W2-D007, resource identity is deliberately limited to the database name. Do not
expand this history work into database versioning, acquisition tracking or
dataset capture; reproducibility claims must reflect that chosen scope.
History navigation/export never transfers scientific approval to a changed model.

## Resource identity: database name only (B-NK-6; W2-D007)

Status: **accepted reduced scope**.

Record the actual selected database name (for example, SIGNOR or OmniPath) with
the network/history and expose it through existing inspection/export metadata.
Use the name associated with construction, rather than relabelling an existing
network if mutable session defaults subsequently change. The selected resource
does not imply that imported or manually curated edges came from that database.

Deferred: provider release/version discovery, download/load/cache timestamps,
resource-data fingerprints and database snapshots. Do not implement empty-field
plumbing for these deferred additions merely to satisfy the original wider plan.

The accepted topology history, effective construction parameters, manual-origin
labels and available PMIDs remain required. Existing artifact hashes, handoff
integrity checks and established timestamps remain unchanged; this scope decision
only limits new resource-identity tracking.

## NeKo and MCP implementation allocation

The researcher reports having handed the accepted NeKo/MCP work to their two
repository agents. This discussion thread has not dispatched implementation agents.

| Owner | Responsibility | Acceptance evidence |
|---|---|---|
| NeKo agent | Provide validated interaction editing; preserve explicit manual origin, supplied references and rationale, prior edge state and revision history. Check failed endpoint additions and keep internal representations consistent. Preserve existing database construction behavior. | An interaction absent from the resource can be added between existing nodes when explicitly requested; manual origin and supplied PMIDs survive supported persistence/export paths. Invalid endpoints fail without dangling edges or partial edits. Missing PMIDs remain empty, never fabricated. |
| MCP-server agent | Expose the approved editing operations compactly through the NeKo API; validate exact operation inputs; return the actual resulting change and revision. Correct the node-addition success report when the library returns `False`. Preserve provenance in returned records and appropriate handoff metadata/sidecars. | No false success after a refused node addition; precise edit responses and provenance; stale-revision/approval protections remain effective; representative tool-discovery, schema-size and result-size comparisons are recorded. |
| NeKo agent — history extension | Extend existing state snapshots/metadata with structured topology-emergence explanations, effective parameters, path attribution and manual evidence. Preserve state navigation, branching and visualization. | Fixture-level change attribution, branch/checkout consistency and supported history export/reload checks described in W2-D006. |
| MCP-server agent — history integration | Extend existing history/inspection/export interfaces with concise explanations and references to durable full history artifacts. Preserve state/session identity and report incomplete history. | History can be inspected and exported without a duplicate history tool family; saved artifacts identify exact states and preserve available provenance across branches. |
| NeKo/MCP agents — resource identity | Carry the database name actually used through the existing network/history and inspection/export interfaces. | SIGNOR/OmniPath selection remains correctly labelled after later session-default changes; manual edges retain their distinct origin. No additional resource-version, acquisition-time or dataset-tracking feature is introduced. |

Agree on the library API and provenance representation before integrating the MCP
wrapper. Test the combined workflow after both changes land. A format such as BNET
that cannot represent all edge metadata must retain it in an accompanying typed
artifact, rather than silently dropping the manual-origin designation. Existing
consumers need a documented compatible path.

## MaBoSS summary readouts (B-MB-1; W2-D008)

Status: **accepted**, for implementation in the MCP-server repository using
supported MaBoSS/pyMaBoSS capabilities. No changes to those packages are authorized.

Selecting existing output nodes does not add model variables. This feature instead
adds explicitly requested summary nodes and permits editing their Boolean rules.
The researcher accepted this responsibility in the MaBoSS stage because these
nodes summarize the biological core rather than extend its biological routes.

Implementation scope:

1. Keep readouts distinguishable from core nodes, with `readout` provenance,
   exact rules and a recorded explanation. The initial bounded design uses
   existing core nodes as regulators and permits no feedback into the core.
   Preserve core rules and reject attempts to use the readout editor for general
   biological topology changes.
2. Support creation and rule updates through a compact interface. Validate names,
   collisions, rule syntax and referenced identifiers before committing a change;
   invalid operations must leave the model intact.
3. Record before/after revisions and retain verified upstream NeKo ancestry.
   A readout edit does not inherit scientific approval for the changed model;
   invalidate stale exports/approvals and preserve the existing review/export gates.
4. Persist the readout definitions and effective initial-state/rate configuration
   through supported save/load and export paths. These are simulated nodes with
   stochastic update timing, not instantaneous calculated expressions. Do not
   assume expression exclusivity proves simulated readout-state exclusivity.
5. Creation or editing in a scientific model still requires explicit authorization
   for the named nodes and rules. Do not silently select numerical rates or initial
   states. Tool-based rate inspection/editing is covered by W2-D009.

Acceptance evidence: create a summary node in an imported-model fixture, update
its rule, and verify that core rules remain unchanged; reject invalid or out-of-scope
edits without partial mutation; preserve definitions, upstream ancestry and model
revision through supported persistence and downstream handoff; reject stale approval.
Validate downstream references to the exported readout names without claiming to
execute a PhysiCell simulation.

The MCP agent should identify any required agentic-policy/validator integration
before implementation. This decision authorizes the bounded feature design, not
unrestricted topology editing or changes to unrelated scientific gates. Computed
observables remain a separate analysis topic.

## MaBoSS rate inspection and configuration (B-MB-5; W2-D009)

Status: **accepted**, owned by the MCP-server agent.

Provide compact structured inspection of activation/deactivation rates for
explicitly selected nodes, including readouts. Obtain information from the active
model/configuration through supported APIs; do not require the calling agent to
open BND/CFG files. Those files remain reproducibility artifacts.

Implementation requirements:

1. Identify the session/model revision and return each requested node's configured
   up/down rate expressions, referenced parameter values and unresolved references,
   if any. Distinguish expressions from constant coefficients; do not report an
   instantaneous numerical rate without the state and inputs needed to evaluate it.
   Keep normal results limited to requested nodes and relevant parameters.
2. Support explicit up/down rate configuration for named nodes through supported
   package APIs. Preserve logical activation/deactivation conditions when changing
   their rate coefficients; a coefficient edit must not silently replace a
   conditional expression with unconditional switching. If a custom expression
   cannot be edited unambiguously, report that limitation rather than guessing.
3. Validate requested changes before mutation, preserve unspecified settings,
   avoid unintended changes to other nodes through shared parameters, and return
   before/after values read back from the active model. Reject invalid operations
   without partial changes. Scientific values still require researcher authorization.
4. Preserve effective rate configuration and its model revision in saved simulation
   inputs and associated run metadata. Apply existing stale-approval/export checks.
5. Prefer extending coherent existing inspection/configuration interfaces over
   proliferating tools. Exact names/schema are implementation choices; arbitrary
   expression-authoring capabilities are not required by this decision.

Acceptance evidence: targeted inspection matches the active model; an authorized
rate edit reads back correctly and survives supported persistence/export; other
nodes and logical conditions remain unchanged; invalid or ambiguous edits fail
without mutation. Compare representative response sizes with raw model-file
inspection rather than claiming an unmeasured performance improvement.

## Persistent MaBoSS runs and plots (B-MB-3/4; W2-D010)

Status: **accepted**, for assignment by the researcher to the MCP-server agent.
No MaBoSS/pyMaBoSS package changes or new analysis algorithms are required.

Source inspection found that ordinary runs already call
`MaBoSS/services/artifacts.py:preserve_simulation_result`, which preserves unique
exact engine inputs, raw outputs, state/node tables and an artifact inventory.
The caller still writes a shared `result.csv`; mutation runs do not use that
preservation helper; plotting writes a shared `network_trajectory.png`.
Extend this foundation rather than building a separate storage system.

Implementation requirements:

1. Use shared persistence for ordinary and mutation simulations. Keep existing
   simulation entry points where practical. Each invocation has a unique run ID
   associated with its full session ID, source model revision and run kind.
2. Preserve exact BND/CFG inputs sent to the engine, generated outputs and artifact
   integrity metadata. Record requested mutations and effective simulation
   configuration, including rates, initial conditions, outputs and supported seed/
   thread settings. Preserve only outputs actually produced; missing optional
   outputs must not be represented as successful analyses.
3. Run mutations on a copy, retaining the base simulation and its configuration.
   Save the actual mutated engine inputs, not merely a mutation description.
   Mutation runs must not silently replace the latest ordinary-result selection.
4. Extend result inspection and plotting to accept an explicit run ID. Saved
   historical runs must remain inspectable and plottable after later runs or a
   server restart, without recreating a scientific session or rerunning a model.
   Reuse existing inspection/listing interfaces to make run IDs discoverable.
5. Make unique run artifacts authoritative. Any retained legacy latest-result
   convenience file is not the historical record. Never overwrite historical
   results or plots; associate each plot with its source run and rendering options.
   Support multiple plot variants for a run without collisions.
6. Where omission of a run ID preserves legacy latest-ordinary-result behavior,
   always return the resolved run ID. Never silently substitute another run when
   an explicit ID is missing or belongs to a different session. Preserve existing
   path/integrity boundaries when loading saved artifacts.
7. Return concise structured summaries: session/run IDs, completion status,
   mutations where applicable and artifact references. Retrieve detailed tables
   only on request with bounded responses.
8. Make failures explicit. Do not report a completed reproducible run until its
   required artifacts are safely published. Distinguish engine failure from
   persistence failure, preserve available diagnostic/partial evidence with its
   incomplete status, and leave earlier successful runs intact. Never implicitly
   retry a simulation merely because saving failed.

Acceptance evidence:

- Two ordinary runs and two mutant runs retain distinct, retrievable artifacts
  and exact inputs; mutant execution leaves the base model unchanged.
- Later model edits do not relabel historical results as belonging to the new
  model revision. Saved readout/rate configuration reflects the executed model.
- Explicitly inspect and plot both run kinds after restart without an engine run.
  Multiple plot options preserve earlier artifacts and identify their source.
- Invalid/cross-session IDs, engine failures and injected persistence failures
  cannot produce false success, overwrite earlier runs or silently change selection.
- Existing ordinary-run callers retain documented compatibility, while compact
  responses expose run identity without embedding full trajectories by default.

Coordinate metadata and revision handling with W2-D008/009. Changes to result
schemas and tool annotations must describe the actual persistence behavior and
retain a documented compatibility path. This assignment does not authorize
publication, automatic scientific execution or deletion of existing artifacts.

## Bounded Boolean analysis (B-MB-6): discussion opened

Status: **redirected to MaBoSS_test design discussion under W2-D012**. The earlier
proposal below is retained as context, not an implementation assignment. B-MB-2
is deferred under W2-D011, not completed or included in this proposal.

The existing `scripts/validate/boolean_structure.py` already implements bounded
logical fixed-point enumeration, reachable terminal strongly connected components
under general asynchronous single-node updates, readout-function exclusivity and
reachable stored-readout-state exclusivity. These operate on BNET artifacts, not
the complete configured MaBoSS rate model. They have explicit state/edge bounds;
resource exhaustion is incomplete, not proof. A general invariant-expression
interface is not currently implemented.

Proposal for discussion: provide one focused MCP analysis interface with a small
set of explicit operations, concise results and saved detailed reports. Reuse a
single maintained analysis implementation rather than creating divergent copies
in the orchestrator and server. The MCP distribution must not depend on an
external agentic-system checkout. Shared implementation ownership and migration
of existing script callers need agreement before assignment.

Separate analysis discovery from validation against an expected count. Tie results
to exact rule/configuration artifacts, initial-state scope, update semantics and
completion status. Explain that logical fixed points and asynchronous terminal
components do not provide stochastic probabilities or timing.

Before claiming results describe a configured MaBoSS model, verify that its
rate/constraint semantics match the analysed transition relation. Zero rates,
clamps or custom rate expressions must not be silently ignored. A rules-only
analysis may be explicitly labelled as such; unsupported configured-model claims
must be rejected rather than presented as proofs.

## MaBoSS_test integration direction (W2-D012)

Status: **separate evaluation workstream under W2-D013**; detailed scope and
contract pending. The researcher will fork/clone MaBoSS_test and assess usefulness
with another agent before assigning implementation.

The researcher has cloned MaBoSS_test and requested transfer of the portable
handoff. It now lives in that repository at `docs/maboss-test-evaluation-and-integration-brief.md`
(local checkout: `/home/marcorusc/projects/github/MaBoSS_test`).
The brief remains self-contained. Its original content is also preserved in this
repository's commit `21da56d`.

Researcher-proposed upstream:
https://github.com/sysbio-curie/MaBoSS_test

Source inspection of `maboss_test/MaBoSSTestCase.py` (GitHub file blob
`b670adaec12b2f9189b0d2c2ab8baf577a0d694c`) found Python unittest-style assertions
for state-probability changes under mutations, stable-state probability checks
and node dependencies among simulation-reported stable states. Conditions are
structured Python dictionaries with direction/threshold arguments; this is not
currently a general temporal-logic or exhaustive model-checking implementation.

Relevant integration issues observed in source, not runtime-tested:

- Assertions invoke simulations internally and may change outputs on their copied
  models. An adapter must not silently rerun a model or choose scientific settings.
- Several paths print failures or return early rather than emit a reliable typed
  outcome; missing/invalid evidence must remain distinguishable from a passed test.
- State collections use probabilities as dictionary keys, so equal-probability
  states can overwrite one another. Preserve state identity independently of
  probability before relying on aggregation or dependency tests.
- Comparisons truncate values to a decimal precision. Numerical tolerances,
  statistical uncertainty and biological acceptance thresholds need explicit,
  separately defined semantics.

Recommended architecture for discussion:

1. MaBoSS_test owns reusable condition definitions, validation, evaluation and
   structured outcomes; retain a compatible unittest facade where practical.
2. MCP owns authorized simulation orchestration, W2-D010 run persistence and
   selection, and compact exposure of evaluations bound to exact inputs/results.
3. Permit evaluation of suitable stored results without simulation. Report missing
   timepoints, joint-state information or required outputs rather than synthesizing
   them or interpreting absence as zero.
4. Persist the condition, evidence run IDs, evaluation settings and detailed report.
   Distinguish pass/fail/inconclusive from invalid input or execution error.
5. Keep simulation-based evidence distinct from exhaustive structural proofs.
   Fixed-point completeness, reachable-attractor enumeration and general invariant
   proofs remain separate possible extensions, not capabilities established by
   this integration.

Defer new standalone analysis scripts and the earlier proposal to relocate their
algorithms into the MCP package. Keep existing supported validators available until
any replacement is explicitly scoped, tested and accepted. No MaBoSS/pyMaBoSS
package modifications are included; a future assignment would target MaBoSS_test
and the MCP repository, with agentic-workflow integration scoped separately.

## PhysiCell MCP exposure of existing library capabilities (W2-D014/015)

Status: **accepted for researcher assignment to the MCP-maintenance agent**.
Authority: the researcher accepted the proposal to expose existing Wave 1 library
capabilities while prioritizing implementation before a new testing campaign.

Scope:

- B-PC-2: expose optional output-mapping `steepness` through the MCP interface.
  Correct action-dependent descriptions of mapping parameters against the
  supported library/PhysiBoSS behavior. Do not automatically raise steepness,
  promise an exact Boolean switch or change omitted defaults.
- B-PC-4: expose cycle transition rates and optional `fixed_duration`, using the
  library's public API. Explicit zero and false values are meaningful. Do not
  silently choose a cycle model, transition, duration policy or scientific rate.
- B-PC-6: accept finite nonnegative fractional `time_stochasticity`, including zero,
  consistently with the corrected library API. Preserve defaults when omitted.
- Prefer coherent extensions of existing tools over duplicate tool families.
  Read back and return the stored values for these operations, so an agent does
  not need to inspect XML to determine what was applied.

Use the accepted PhysiCell Settings capabilities; do not assume their merged
source is already installed or published. Identify any genuinely missing library
capability separately. Package publication and scientific model configuration are
not authorized by this maintenance assignment.

Initial cells/user parameters (B-PC-3) are covered separately by W2-D016.
Portable export (B-PC-5) is covered separately by W2-D017.
Substrate handling (B-PC-7) is covered by W2-D018; parameter inspection/readback
and behavior-name discovery (B-PC-1/9) are covered by W2-D019. Mapping validation (B-PC-8) and
the broader benchmark/testing campaign are deferred. This does not remove existing
runtime input validation, artifact integrity checks or scientific approval gates.

## User parameters and existing initial-cell CSV files (B-PC-3; W2-D016)

Status: **accepted**, ready for assignment to the MCP-maintenance agent.
Authority: the researcher explicitly approved typed parameter editing/inspection
and existing CSV configuration, with placement generation deferred.

Implementation scope:

1. Create/update named user parameters through the supported library API with
   explicit type and value, supplied units and an optional description. Inspect
   selected parameters through tools and return stored values after updates.
   Preserve unrelated settings and distinguish omission from explicit zero/false.
   Do not infer scientific units or values.
2. Register an existing initial-cell positions CSV and enable/disable its loading.
   Preserve the supplied file as an identified artifact for later portable export;
   do not require the agent to read or edit XML. Respect existing artifact/path
   boundaries and report missing files or unsupported input formats clearly.
3. Report the CSV configuration together with any configured cell-count parameter.
   Do not silently change counts when enabling CSV, nor claim that CSV replaces
   procedural placement in every PhysiCell executable.
4. Use the same typed-parameter interface for parameters such as `number_of_cells`
   or a template-supported `random_seed`. Distinguish successfully storing a
   parameter from confirming that the target executable interprets it.
5. Prefer coherent extensions of existing configuration/inspection interfaces.
   This is MCP work using existing Settings capabilities; any additional required
   library change should be identified separately.

The inspected standard PhysiCell template creates `number_of_cells` cells for
each cell type, then calls the CSV loader. This is template-specific behavior,
not a universal promise about PhysiCell projects:
https://github.com/MathCancer/PhysiCell/blob/master/sample_projects/template/custom_modules/custom.cpp

CSV-only initialization therefore requires an explicit compatible count setting
when using such a template. Do not assume a count means the total across cell types.
The initial implementation does not generate positions, clusters or random
distributions, choose geometry/seeds, or provide implicit per-cell-type count
semantics. Placement generation is deferred for separate discussion.

Coordinate file references with the portable-export design (B-PC-5; W2-D017).
Broader testing remains deferred under
W2-D015; runtime input checks and existing scientific authorization remain required.

## Portable PhysiCell configuration bundle (B-PC-5; W2-D017)

Status: **accepted**, ready for assignment to the MCP-maintenance agent.
Authority: the researcher explicitly approved the configuration-bundle proposal,
excluding executable/build packaging.

Export the configuration and its supported input dependencies as a uniquely named,
self-contained bundle for an existing compatible PhysiCell/PhysiBoSS executable.
An illustrative layout is:

```text
export/
  config/
    PhysiCell_settings.xml
    boolean_models/
      tumour.bnd
      tumour.cfg
    cells.csv
    cell_rules.csv
  manifest.json
  README.md
```

Include only applicable files; names and internal layout are implementation
choices. Support distinct Boolean models for multiple cell types without filename
collisions or incorrect reference substitution.

Implementation requirements:

1. Collect referenced BND/CFG files, enabled initial-cell CSV files, cell rules and
   other explicitly supported input dependencies. Coordinate CSV ownership and
   preservation with W2-D016. Do not copy arbitrary directories.
2. Rewrite supported references in the exported copy to portable paths resolved
   according to the target configuration's path semantics. Document the required
   working directory and expected executable/template compatibility in README.
   Do not assume paths are resolved relative to the XML location.
3. Preserve the active session configuration and original source artifacts.
   Packaging changes file locations, not scientific model settings.
4. Record source session/model identity, upstream lineage, dependency inventory
   and file hashes in the manifest. Preserve existing artifact-integrity and
   scientific export gates; a packaging manifest does not grant model approval.
5. Report missing required inputs and unsupported external references explicitly.
   Do not label an incomplete bundle self-contained or ready to run. Leave
   existing exports intact and avoid publishing a partial bundle as complete.
6. Create a unique export destination; never silently overwrite a previous bundle.
   Return concise bundle/manifest locations and unresolved requirements.

MCP owns packaging and session provenance; reuse PhysiCell Settings for
configuration serialization. Identify any missing library API separately.
The feature excludes executable distribution, compilation, engine installation,
automatic simulation execution and claims of successful scientific validation.
The broader testing campaign remains deferred under W2-D015.

## Required default substrate: revised B-PC-7 discussion (W2-D018)

Status: **accepted for researcher assignment to the PhysiCell Settings and MCP
agents**. Following the compatibility correction, the researcher confirmed they
will hand this revised proposal to those two agents.

The researcher clarified that the target PhysiCell software requires a substrate:
omitting even the default causes crashes and missing-substrate references in
interactions/parameters. Do not implement the previously discussed empty-substrate
mode or disable the required default insertion on that basis. The original
diagnostic's “substrate-free” readiness goal must mean no biologically specified
diffusing substrate, not an empty executable configuration.

Revised proposal:

- Retain the required default entry and its existing name for compatibility.
  Identify its default/template origin through inspection metadata rather than
  renaming it automatically or claiming it represents a researcher-selected species.
- Make the effective default and its parameters visible before export, keeping
  configuration, dependent cell settings and MCP status synchronized. Export
  should not be the first point at which the agent discovers the default.
- Base substrate-step readiness on the actual valid configuration, including a
  known required default. Do not require an extra `add_substrate` call merely to
  satisfy workflow bookkeeping. Overall export approval and other gates remain.
- Preserve imported substrates and their references. Adding a biological substrate
  must not silently delete or rename the default; replacement/removal requires
  explicit intent and coherent handling of dependent references. Never leave zero
  substrate entries in the supported configuration.
- Do not call the default inert or biologically neutral without evidence.
  Report its effective units and parameters; do not silently normalize units,
  change numerical defaults or convert values as part of this visibility fix.

Ownership: Settings maintains the required default and dependent
configuration consistency; MCP exposes its origin/values and consistent readiness.
This is a focused configuration/status proposal, not an engine modification or
an expansion of the deferred testing campaign.

## Compact MCP inspection improvements (W2-D019)

Status: **accepted**, ready for assignment to the MCP-maintenance agent.
Authority: the researcher explicitly approved the proposed inspection package.

| Item | Accepted implementation |
|---|---|
| B-PC-1, inspection/readback scope | Inspect selected stored cell settings through tools and return actual stored values after updates. Preserve explicit zero/false and do not confuse an echoed request with successful application. Coordinate with W2-D014/016/018 rather than adding duplicate inspection interfaces. |
| B-PC-9 | Expose supported behavior names and aliases, including cycle-exit behaviors, through existing discovery interfaces. Use the supported backend vocabulary and cell/model context; do not invent aliases or claim unsupported phase names are usable. |
| B-MB-7 | Return readable Boolean rules with equivalent semantics, without changing the underlying model. Prefer the actual logical rule over redundant transition-expression formatting; if a custom configuration cannot be represented faithfully as a simple Boolean rule, report the limitation rather than guessing. |
| B-MB-8 | Report effective simulation configuration through tools, including relevant sampling, thread, time and stationary-distribution settings. Describe disabled outputs accurately; do not automatically enable stationary-distribution computation or change defaults. |
| B-MB-9 | Report selected output versus internal nodes through inspection and export summaries. Bind export descriptions to the exported configuration, not stale session labels. Do not change output selections or imply that an internal node is absent from the model. |

Prefer concise structured responses for requested nodes/settings and coherent
extensions of existing tools. Keep source model/session/revision identity clear
where relevant and distinguish stored values from unknown/unavailable values.
This package changes visibility and presentation, not biological rules or
scientific configuration. It is separate from the deferred testing campaign and
does not authorize MaBoSS/pyMaBoSS changes or new analysis algorithms.

## NeKo diagnostics and documentation (B-NK-2/3/5/7; W2-D020)

Status: **accepted**, ready for researcher assignment to the NeKo and MCP agents.
Authority: the researcher explicitly approved the four-item cleanup proposal.
Reconcile with current agent branches before implementation to avoid duplicate work.

| Item | Accepted implementation | Owner |
|---|---|---|
| B-NK-2 | Correct construction/import documentation and responses. A SIF import does not automatically run connection completion; report actual imported counts and any separately performed additions or completion. | MCP |
| B-NK-3 | Document actual resource-specific consensus behavior and align tool descriptions with it. Remove blanket claims that consensus always means multiple databases or higher confidence. Preserve the current scientific policy and defaults. | NeKo semantics/documentation; MCP tool descriptions |
| B-NK-5 | Return readable labels alongside stable identifiers where available; count the canonical node inventory, including label-only nodes; distinguish no path from invalid endpoints or execution errors. | NeKo identity/path reporting; MCP counts and structured outcomes |
| B-NK-7 | Identify offending nodes and invalid/missing labels in export failures, with actionable correction guidance. Preserve valid mappings and do not silently relabel a scientific model. | NeKo diagnostic details; MCP error presentation |

Correction to the historical diagnostic: the inspected SIGNOR adapter calculates
consensus stimulation/inhibition flags by comparing grouped sign-record totals.
Do not implement an unconditional “SIGNOR consensus is a no-op” warning.
Confirm the implementation in the agent's target revision and document its actual
semantics, including how ties or missing consensus information are handled.
This assignment does not approve changing how consensus is computed.

The inspected MCP path interface captures printed library output and can count
a warning as a path-output line. Prefer structured library results where practical
and keep any public compatibility wrapper; at minimum never present diagnostics
as discovered paths. Report the requested path-length/direction scope accurately.
Do not infer disconnected components merely because no path exists within a bound.

Canonical node identity must drive counts and graph membership. Neither non-null
UniProt identifiers alone nor unique display labels are sufficient in general.
Preserve missing-identifier and ambiguity information rather than inventing
mappings or merging nodes with colliding labels.

Use existing interfaces where practical. No new topology mutation, resource
tracking beyond W2-D007, automatic repair, consensus-policy change or broader
testing campaign is included. Necessary developer checks remain part of the work.

## Implementation handoff format

Once each item is decided, record its accepted behavior, affected repository,
compatibility constraints, evidence/approval requirements, acceptance tests and
dependencies on other items. The researcher will use those bounded tasks to
distribute the implementation. Unresolved proposals must not be presented as
accepted requirements.

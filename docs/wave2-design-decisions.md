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

Authority: the researcher's message on 2026-10-20 stating the maintenance boundary
and requesting discussion and a decision record before distributing the work.
W2-D003–005 follow the subsequent approval: "yes, as long as it is mentioned that
it was manually added (and maybe populate the field with the pubmed id when
available)" and "I also approve you suggestion for wave 2", with work assigned
to agents responsible for NeKo and MCP servers.
W2-D006 follows the researcher's confirmation that topology-growth explanations
are required and that NeKo already supports network-state history, checkout and
state-graph export/visualization.

Changes to PhysiCell/PhysiBoSS engines, random-stream algorithms, publication,
scientific defaults and additional repositories are not authorized by this scope.
Necessary agentic-workflow integration changes should be identified in task plans
and discussed explicitly. Decisions about software capabilities do not waive
researcher approval for their use on a scientific model.

## Discussion agenda

| Area | Items to examine | Decision status |
|---|---|---|
| NeKo editing and provenance | B-NK-1: explicit interaction additions/sign changes. B-NK-2/3/5/7: truthful diagnostics and identifier handling. B-NK-4/6 and remaining C-NK provenance/documentation work: explain network growth and expose resource metadata. | Manual-edge policy and compact editing approach accepted (W2-D003–005). Topology-growth explanations through existing history accepted (W2-D006). Resource identity fields and remaining diagnostics still need discussion. |
| MaBoSS reproducibility and readouts | B-MB-1: readout semantics and lineage. B-MB-2: investigate import failures. B-MB-3/4: persistent mutation runs and unique artifacts. B-MB-5/6: existing-engine rate configuration and analysis capabilities. Remaining metadata/documentation items. | Pending; MCP changes only, no MaBoSS/pyMaBoSS package changes. |
| PhysiCell configuration | Remaining MCP portions of B-PC-1/2/4/6, initial cells/user parameters, portable project export, substrate handling and mapping validation. Reconcile already completed library and lineage work before assigning tasks. | Pending. |
| Analysis ownership | Decide whether existing artifact-validation calculations remain orchestrator checks, are also exposed through MCP, or need a shared implementation. Define the approved scope before any ODE extension. | Pending. |
| Release boundary | Decide whether the selected Wave 2 fits the next coordinated release or follows a separate Wave 1 release. Resolve official NeKo metadata and dependency alignment before publication. | Pending. |

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
prove that rerunning construction against a changed database produces it. Record
the resource/input identity needed to assess replay, and report missing inputs.
The exact resource metadata fields are the next discussion item (B-NK-6).
History navigation/export never transfers scientific approval to a changed model.

## NeKo and MCP implementation allocation

These requirements are recorded for later assignment; no implementation agents
have been dispatched as part of this discussion.

| Owner | Responsibility | Acceptance evidence |
|---|---|---|
| NeKo agent | Provide validated interaction editing; preserve explicit manual origin, supplied references and rationale, prior edge state and revision history. Check failed endpoint additions and keep internal representations consistent. Preserve existing database construction behavior. | An interaction absent from the resource can be added between existing nodes when explicitly requested; manual origin and supplied PMIDs survive supported persistence/export paths. Invalid endpoints fail without dangling edges or partial edits. Missing PMIDs remain empty, never fabricated. |
| MCP-server agent | Expose the approved editing operations compactly through the NeKo API; validate exact operation inputs; return the actual resulting change and revision. Correct the node-addition success report when the library returns `False`. Preserve provenance in returned records and appropriate handoff metadata/sidecars. | No false success after a refused node addition; precise edit responses and provenance; stale-revision/approval protections remain effective; representative tool-discovery, schema-size and result-size comparisons are recorded. |
| NeKo agent — history extension | Extend existing state snapshots/metadata with structured topology-emergence explanations, effective parameters, path attribution and manual evidence. Preserve state navigation, branching and visualization. | Fixture-level change attribution, branch/checkout consistency and supported history export/reload checks described in W2-D006. |
| MCP-server agent — history integration | Extend existing history/inspection/export interfaces with concise explanations and references to durable full history artifacts. Preserve state/session identity and report incomplete history. | History can be inspected and exported without a duplicate history tool family; saved artifacts identify exact states and preserve available provenance across branches. |

Agree on the library API and provenance representation before integrating the MCP
wrapper. Test the combined workflow after both changes land. A format such as BNET
that cannot represent all edge metadata must retain it in an accompanying typed
artifact, rather than silently dropping the manual-origin designation. Existing
consumers need a documented compatible path.

## Implementation handoff format

Once each item is decided, record its accepted behavior, affected repository,
compatibility constraints, evidence/approval requirements, acceptance tests and
dependencies on other items. The researcher will use those bounded tasks to
distribute the implementation. Unresolved proposals must not be presented as
accepted requirements.

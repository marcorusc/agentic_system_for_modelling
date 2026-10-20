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

Authority: the researcher's message on 2026-10-20 stating the maintenance boundary
and requesting discussion and a decision record before distributing the work.
W2-D003–005 follow the subsequent approval: "yes, as long as it is mentioned that
it was manually added (and maybe populate the field with the pubmed id when
available)" and "I also approve you suggestion for wave 2", with work assigned
to agents responsible for NeKo and MCP servers.

Changes to PhysiCell/PhysiBoSS engines, random-stream algorithms, publication,
scientific defaults and additional repositories are not authorized by this scope.
Necessary agentic-workflow integration changes should be identified in task plans
and discussed explicitly. Decisions about software capabilities do not waive
researcher approval for their use on a scientific model.

## Discussion agenda

| Area | Items to examine | Decision status |
|---|---|---|
| NeKo editing and provenance | B-NK-1: explicit interaction additions/sign changes. B-NK-2/3/5/7: truthful diagnostics and identifier handling. B-NK-4/6 and remaining C-NK provenance/documentation work: explain network growth and expose resource metadata. | Manual-edge policy and compact editing approach accepted (W2-D003–005). Resource/growth provenance and other remaining items still need discussion. |
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
  not a measurement of the tool schemas loaded by a particular client.

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

## NeKo and MCP implementation allocation

These requirements are recorded for later assignment; no implementation agents
have been dispatched as part of this discussion.

| Owner | Responsibility | Acceptance evidence |
|---|---|---|
| NeKo agent | Provide validated interaction editing; preserve explicit manual origin, supplied references and rationale, prior edge state and revision history. Check failed endpoint additions and keep internal representations consistent. Preserve existing database construction behavior. | An interaction absent from the resource can be added between existing nodes when explicitly requested; manual origin and supplied PMIDs survive supported persistence/export paths. Invalid endpoints fail without dangling edges or partial edits. Missing PMIDs remain empty, never fabricated. |
| MCP-server agent | Expose the approved editing operations compactly through the NeKo API; validate exact operation inputs; return the actual resulting change and revision. Correct the node-addition success report when the library returns `False`. Preserve provenance in returned records and appropriate handoff metadata/sidecars. | No false success after a refused node addition; precise edit responses and provenance; stale-revision/approval protections remain effective; representative tool-discovery, schema-size and result-size comparisons are recorded. |

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

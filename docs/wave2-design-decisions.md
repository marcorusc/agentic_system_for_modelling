# Wave 2 design discussion and decision record

Discussion opened: 2026-10-20 (researcher timezone: Asia/Tokyo).
Status: discussion only; implementation has not been authorized.

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

Authority: the researcher's message on 2026-10-20 stating the maintenance boundary
and requesting discussion and a decision record before distributing the work.

Changes to PhysiCell/PhysiBoSS engines, random-stream algorithms, publication,
scientific defaults and additional repositories are not authorized by this scope.
Necessary agentic-workflow integration changes should be identified in task plans
and discussed explicitly. Decisions about software capabilities do not waive
researcher approval for their use on a scientific model.

## Discussion agenda

| Area | Items to examine | Decision status |
|---|---|---|
| NeKo editing and provenance | B-NK-1: explicit interaction additions/sign changes. B-NK-2/3/5/7: truthful diagnostics and identifier handling. B-NK-4/6 and remaining C-NK provenance/documentation work: explain network growth and expose resource metadata. | Pending; start with B-NK-1. |
| MaBoSS reproducibility and readouts | B-MB-1: readout semantics and lineage. B-MB-2: investigate import failures. B-MB-3/4: persistent mutation runs and unique artifacts. B-MB-5/6: existing-engine rate configuration and analysis capabilities. Remaining metadata/documentation items. | Pending; MCP changes only, no MaBoSS/pyMaBoSS package changes. |
| PhysiCell configuration | Remaining MCP portions of B-PC-1/2/4/6, initial cells/user parameters, portable project export, substrate handling and mapping validation. Reconcile already completed library and lineage work before assigning tasks. | Pending. |
| Analysis ownership | Decide whether existing artifact-validation calculations remain orchestrator checks, are also exposed through MCP, or need a shared implementation. Define the approved scope before any ODE extension. | Pending. |
| Release boundary | Decide whether the selected Wave 2 fits the next coordinated release or follows a separate Wave 1 release. Resolve official NeKo metadata and dependency alignment before publication. | Pending. |

## First proposal: explicit NeKo interaction editing (B-NK-1)

Status: **proposed, not accepted**.

Problem: the benchmark required hand-edited SIF files to add specific interactions
and change a sign. The inspected MCP interface exposes removal but lacks matching
dedicated addition/sign-change tools. NeKo already has a low-level `add_edge`
method; whether it needs a stronger public mutation API is an implementation
question, not permission to bypass its internal consistency requirements.

Proposed contract:

1. Provide distinct operations for adding an interaction and changing the
   effect of an existing interaction. Whether they share one MCP tool remains
   under discussion; separate operations do not require separate tool names.
   Do not silently overwrite a conflicting edge.
2. Require explicit source/target identifiers resolving unambiguously to existing
   nodes. Missing endpoints require a separate explicit node-addition operation;
   editing an edge must not silently expand or reconnect the network.
3. Require rationale and explicit provenance/evidence information. Preserve the
   original evidence separately from the justification for the edit. The exact
   provenance fields and handling of evidence-free hypotheses remain to discuss;
   no new provenance category is approved here.
4. Preserve the before/after edge state and edit history, keep library node/edge
   representations consistent, and invalidate exports/approvals tied to an older
   model revision. Editing alone never exports or approves a new handoff.
5. Keep each operation within the researcher's explicitly authorized mutation
   scope. An API capability is not scientific permission to use it autonomously.

First decision requested: agree or revise the proposed separation of edge editing
from node addition/automatic network completion. After that, settle evidence,
conflict handling and revision requirements before marking B-NK-1 ready for work.

## Database restrictions and tool discoverability discussion (2026-10-20)

Researcher concerns: original NeKo behavior may reject nodes/interactions absent
from its database; adding many MCP tools may impair discovery and consume context.
These concerns reopen the first proposal. No curation policy or tool layout has
been accepted.

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

### Revised recommendations, still pending

Separate the scientific provenance policy from the MCP interface:

- Retain resource-backed construction behavior. Consider a separately explicit,
  researcher-authorized curation operation for literature-supported interactions
  absent from that resource. Such an edge must not acquire a database provenance
  label. Whether to admit these edits is the next researcher decision; custom
  nodes and evidence-free hypotheses remain separate unresolved choices.
- Consider one focused `edit_interactions` tool with a small, strictly typed set
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

## Implementation handoff format

Once each item is decided, record its accepted behavior, affected repository,
compatibility constraints, evidence/approval requirements, acceptance tests and
dependencies on other items. The researcher will use those bounded tasks to
distribute the implementation. Unresolved proposals must not be presented as
accepted requirements.

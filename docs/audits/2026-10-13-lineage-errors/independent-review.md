# Independent Boolean lineage v2 review

## Finding

**P2 — Initial typed-parent imports can accept missing or stale live parent artifacts.**

Location: `/tmp/agentic-wave1-20261013/mcp/mcp_biomodelling_servers/import_lineage.py:148` (typed-parent loading), with the digest-cache shortcut at lines 228–243 and source-before-ancestor reads at lines 261–265.

The typed-parent branch changed from artifact verification to `load_handoff_manifest(..., verify_artifacts=False)`. For a byte-identical import at a different path, snapshotting first caches the imported bytes. The ancestor and parent-artifact reads then find that digest in the cache and never inspect the parent's live BNET. Consequently an initial import succeeds even if that BNET was deleted or changed. The explicit live verification added for source sidecars at line 144 does not cover typed NeKo handoffs. This regresses initial-import integrity checking for both v1 and v2 parents; it is distinct from the intended portability of already-captured history. It does not by itself bypass current-stage approval.

**Reproduction:** Ran an in-memory virtual-filesystem fixture with the required interpreter, `PYTHONDONTWRITEBYTECODE=1 /home/marcorusc/miniforge3/envs/mcp_modelling/bin/python -`. It constructed a valid typed NeKo manifest, retained a byte-identical BNET at a new import path, removed the original BNET from the virtual filesystem, then called the real `capture_import(..., trusted_root='/virtual')`. Both versions incorrectly succeeded:

```
1.0 ACCEPTED missing live parent BNET: byte-identical opened: ['/virtual/import.bnet', '/virtual/parent.json']
2.0 ACCEPTED missing live parent BNET: byte-identical opened: ['/virtual/import.bnet', '/virtual/parent.json']
```

The fixture mocked only filesystem access, artifact-reference construction, and the initial parent-file hash; real manifest validation, import selection, evidence traversal, and portable validation executed. No fixture files or scientific models were created.

**Fix:** In the initial typed-parent branch, explicitly bound and verify current parent artifact paths against `trusted_root` before allowing digest-cache reuse, matching the source-sidecar treatment. Do not make portable snapshot validation reopen historical paths.

**Regression tests:** Parameterize v1/v2 typed NeKo parents and deleted/modified original BNETs; retain an unchanged import copy and require initial capture to reject. Keep the existing successful capture → delete originals → portable validation tests passing. Include an outside-root live parent BNET to ensure restoring verification does not introduce unbounded reads.

## Scope and validation limits

Reviewed pending changes versus HEAD in MCP and `/home/marcorusc/projects/github/agentic_system_for_modelling`, repository instructions, both requested design documents, source evidence traversal/ownership/bounds, typed export/import propagation, capture relocation/publication, gate approval binding, and configured-Python metadata fallback. No additional actionable findings identified in those inspected paths. This was a bounded review, not an exhaustive security or concurrency audit.

Read supplied integration logs; did not rerun their full suites:

- `/tmp/agentic-wave1-20261013/control/lineage-mcp-tests.log`: **1 failed, 625 passed, 12 warnings in 5.40s**. The failure expected `digest` but received `size changed`; current test source already expects `size changed`, so this log does not validate the latest corrected tree.
- `/tmp/agentic-wave1-20261013/control/lineage-agentic-tests.log`: **353 passed, 688 subtests passed in 13.53s**.
- Independent in-memory reproduction above: process exit **0**, confirming unexpected acceptance for both versions.

No repository, dependency, branch, or commit changes. Only this report was written. Suggested follow-up grouping: one MCP correctness fix plus its initial-import regression tests; retain the coordinator's separate MCP contract and agentic capture/gate integration groups.

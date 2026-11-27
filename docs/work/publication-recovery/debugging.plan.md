# Prepared Publication Quarantine

- Work type: debugging
- Delivery fidelity: Level 2 focused recovery repair
- Status: locally verified
- Baseline: `7c6a3a94`
- Governing contract: [Publication recovery](../../design/durable_execution_and_solver_runtime.md#closed-publication-and-control-authority)
- Related work: [First release conformance](../durable-memory-implementation/milestones/release-conformance.plan.md)
- Experiment budget: baseline reproduction, corrected guard routing, and one surrounding regression run

## Objective And Completion

Persist quarantine before the owner finishes recovery of an inconsistent
prepared publication. Prove that the corrupt cases fail against the baseline,
that ordinary managed access stays closed, that durable terminal quarantine
preserves the prior signed publication, and that healthy recovery cuts still
abort or finalize appropriately.

## Expected And Observed

The recovery owner must persist quarantine when a prepared publication's
partition is inconsistent with its old and new states. Ordinary transactions
must deny release while that intent is pending. The existing third-tuple test
raised `InstallationIntegrityError` at transaction entry and never reached the
quarantine decision. The same failure reproduced on the prior v7 baseline,
ruling out v8 initialization or payload encoding as the cause.

The guard compares the SQLite publication row before yielding the connection.
It correctly closes the transaction to callers, but previously used a generic
error even when the exact pending intent was under recovery. The recovery
owner now handles a typed mismatch for that case and records the observed
tuple digest, if present, along with durable quarantine. Selection and inode
errors retain their behavior. Exact-old recovery now verifies signed tuple
metadata and the materialized contents before aborting a prepared intent,
using the same checks as exact-new recovery. The lock order and persisted
format are unchanged.

## Evidence

All five corrupt recovery cases failed against an archived baseline using
the updated tests. The fixed path covers a third tuple, foreign generation,
missing publication row, and preserved-old-tuple corruption on the default
and named partition paths. The recovery tests prove that the finalized
authority is preserved and a fresh service refuses managed reads and writes.
Existing tests cover exact-old abort, exact-new finalization, interrupted
initialization, legacy migration and selected generation restore. All 138
focused tests passed with warnings promoted to errors. Ruff, behavioral
identity and whitespace checks passed.

Independent correctness, specification and test review identified the
adjacent rejected-row, named manifest and default old-materialization
conditions. The final repair and tests cover those conditions in the same
recovery path. The standard managed roots retain the existing publication
fence. Initial legacy adoption keeps its separate lock and can resume when
no initial tuple was written. A cold named exact-old recovery may verify the
manifest in the guard and again inside the recovery snapshot. The extra
verification is confined to prepared-intent recovery.

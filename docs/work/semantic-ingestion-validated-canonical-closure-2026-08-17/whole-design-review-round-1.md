# Whole-Design Review Round 1

Date: 2026-08-17

Frozen candidate:
`722a0a933ff9dd34591e310ad58b01b2f04c9b519725c0136b23f139615ee1db`

Reviewers:

- `spec_auditor`: `CHANGES_REQUIRED`
- `correctness_reviewer`: `CHANGES_REQUIRED`
- `test_reviewer`: `CHANGES_REQUIRED`

All reviewers confirmed that the 19 manifest-tracked hashes matched the frozen
candidate. No reviewer changed production code, tests, or candidate artifacts.

## Reconciled Findings

| ID | Product priority | Approval disposition | Finding type | Coordinator classification | Reconciled finding and required correction |
| --- | --- | --- | --- | --- | --- |
| `VCC-DREV-001` | Not applicable | blocks_approval | architecture / feasibility | confirmed | The separate reference encoder does not prove that current canonical codec owners can emit exact spans during their own canonical traversal. Freeze an owner-level byte-and-span encoder contract for `_normalized_typed_json` and semantic-contract encoding, then directly prove byte identity, all accepted CTV containers including set ordering, and decoder compatibility. |
| `VCC-DREV-002` | Not applicable | changes_required | architecture | confirmed | The candidate names typed handoffs but does not specify exact creation, parameter, return, validation, and consumer signatures, while the current arena is ambient. Specify the sole issuer and exact typed handoff at every covered boundary; the enabled path must not obtain authority from `current_canonical_evidence_arena()` or another `ContextVar`. |
| `VCC-DREV-003` | Not applicable | changes_required | verification | confirmed | The durable-writer ledger is incomplete. Enumerate every writer and bootstrap repository port, including authorization transition and prepared-source publication, and classify each as a typed closure consumer or explicit full-path exclusion with writer-local validation and durable outcome. |
| `VCC-DREV-004` | Not applicable | changes_required | operability | confirmed | `VCC-R11` lacks a production metrics owner and sink. Specify content-free counters and emission points for creation, hit, miss/fallback reason, invalidation, capacity refusal, retained charge, saved reconstruction/digest work, and scope close; prohibit bytes, paths, and values in labels. |
| `VCC-DREV-005` | Not applicable | changes_required | compatibility | confirmed | Disabled and rollback semantics are ambiguous because current `sync_event` creates the existing arena. Decide the feature-selection point and explicitly preserve or retire the current arena, including reservation refusal and cleanup equivalence. |
| `VCC-DREV-006` | Not applicable | changes_required | runtime behavior / concurrency / capacity | confirmed | Define one linearizable capacity state machine: reserve before exposure, build in staging, atomically seal or clear all capability/index/charge and permanently select full-path mode. Specify close-versus-reader behavior plus concurrent reservation and late-overflow proofs. |
| `VCC-DREV-007` | Not applicable | changes_required | security / authorization | confirmed | Scope omits authenticated partition and fresh writer binding. Require non-optional authenticated partition/scope plus operation-fence equality, and mint writer-local evidence bound to `SemanticWriterCommitBinding`; omission or mismatch must be a miss followed by full validation. |
| `VCC-DREV-008` | Not applicable | blocks_approval | governance | confirmed | The production binding artifact lacks complete requirement-to-binding rows, mapping queries, caller counts, and focused path proofs. Add a revision-bound, deterministically validated ledger for `VCC-R01` through `VCC-R12` that fails on zero/test-only callers, removed handoffs, omitted authority arguments, or bypass fallbacks. |
| `VCC-DREV-009` | Not applicable | changes_required | verification | confirmed with phase correction | Reference experiments validly prove design feasibility but cannot prove implemented production behavior. Preserve them as pre-implementation evidence and specify implementation acceptance gates through `ProviderMemoryService.sync_event` for enabled, disabled, capacity-refused, negative handoff, lifecycle/retry/replay, authorization, and capacity cases. These gates are required during implementation, not executable before the design exists in production. |
| `VCC-DREV-010` | Not applicable | changes_required | verification | confirmed | The primary VCC-EXP-001B result reports `passed: false`, and the operation-aware reconciliation lacks a tracked executable producer. Consolidate stable and operation-bound identity rules in one tracked program whose primary output passes, and add nonzero mutations for path, span, validation context, boundary role, and illicit operation-bound digest reuse. |

## Duplicate And Unsupported Observations

| Observation | Coordinator classification | Disposition |
| --- | --- | --- |
| Proposed symbols do not already exist in production | unsupported | A design may introduce new symbols; the required correction is exact ownership and signature binding, captured by `VCC-DREV-002`. |
| Current 1 MiB arena and proposed 16 MiB closure are inherently contradictory | unsupported | They are different current and target envelopes; disabled-path and migration ambiguity remains captured by `VCC-DREV-005` and capacity behavior by `VCC-DREV-006`. |
| Reference evidence should already prove the unimplemented production closure | unsupported as a pre-implementation requirement | Production proof is an implementation acceptance gate, captured by the phase-corrected `VCC-DREV-009`. |
| Spec writer-ledger and test Spark-ledger findings | duplicate in part | Reconciled separately as runtime writer completeness (`VCC-DREV-003`) and deterministic governance mapping (`VCC-DREV-008`). |

## Approval Decision

`CHANGES_REQUIRED`

The frozen candidate remains a valid review identity but is not approved for
implementation. Any remediation changes invalidate its candidate lock. The
next candidate must receive a fresh manifest and a fresh independent
whole-design review after all confirmed findings close.

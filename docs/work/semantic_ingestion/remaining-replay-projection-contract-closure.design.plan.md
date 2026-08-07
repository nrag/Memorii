# Remaining Replay And Projection Contract Closure

- Work ID: remaining_replay_projection_contract_closure
- Work type: design
- Status: complete
- Coordinator and sole canonical-design writer: Codex main thread
- Created: 2026-08-02
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related completed design: `docs/work/semantic_ingestion/conflict-attention-replay-design.plan.md`
- Governing sources: `docs/design/memorii_spec.md`; `docs/design/memorii_storage_details.md`; `docs/design/event_model.md`; `docs/design/semantic_ingestion_architecture.md`; `docs/design/conflict_attention.md`; `docs/IMPLEMENTATION_RULES.md`

## Objective And Baseline

Close the determinate semantic gaps found by the mandatory pre-coding test
review so the remaining conflict, replay, checkpoint, recovery, projection,
policy-migration, and lineage implementation requires no hidden conversation
choice. Rollout step 1 is implemented and locally verified. Stateful attention,
canonical replay, and historical projection are not yet implemented.

The implementation WorkPlan is paused only at the affected semantic boundaries.
No production, test, fixture, workflow, or generated-artifact writer may begin
those boundaries until this design operation completes.

## Requirements And Acceptance

| ID | Requirement | Acceptance |
| --- | --- | --- |
| D01 | Cursor continuation must preserve one retained authorized listing snapshot without ignored caller fields | The design says exactly how omitted/equal/changed scope and page-size fields behave and names typed failures |
| D02 | Clarification retries and receipts must have one durable idempotency algebra | The design fixes pre-append receipt failure, committed retry, divergent retry, nonce consumption, attempt counting, and eligibility |
| D03 | Integrity isolation must be proof carrying | The store-owned proof schema, validation, freeze boundary, unrelated-scope rule, and unfreeze preconditions are closed |
| D04 | Projection-policy migration must be replayable and bitemporal | Plan, base/catch-up membership, read set, ledger coordinates, certificate, cutover, late arrivals, history, rollback, and restart are typed and deterministic |
| D05 | The equal-version external-decision register must reflect the resolved authority | The semantic architecture no longer calls the frozen decision pending and its acceptance remains fail closed |
| D06 | The changed authority chain must remain executable | Bound hashes, decision artifact, validator, negative mutations, identity hygiene, test/gate owners, and implementation WorkPlan pins are current |

## Proposed Decisions

- A continuation cursor owns snapshot membership. Omitted `scope_ids` means the
  retained narrowed snapshot; supplied `scope_ids` must be the exact canonical
  set bound to that snapshot or the request rejects as `invalid_cursor_scope`.
  `page_size` may change within `1..100` because it affects only the next slice,
  never membership, order, totals, watermark, or last key. Every other cursor
  field is server-owned and caller mutation rejects.
- A fresh list request uses all authorized scopes when `scope_ids` is absent.
  Supplied scopes must already be a nonempty, unique, canonical subset; invalid
  order, duplicates, emptiness, or unauthorized members reject before a
  repository read. Cursor claims cryptographically bind tenant, principal,
  authorization snapshot, retained snapshot, scope membership, key epoch, and
  expiry. Continuation requires exact current authorization equality; key
  rotation accepts only retained non-revoked verification keys.
- Receipt verification is a precondition to the one atomic append. A failed
  verification creates no operation receipt, nonce consumption, proposal,
  work item, or transition. A corrected receipt may retry the same operation
  because no durable operation exists. After commit, the same operation ID and
  request digest returns the original outcome without re-verification; changed
  request bytes reject. Receipt proof and nonce consumption are retained in the
  committed generation.
- `attempt_count` means completed retryable processing failures. Work starts at
  zero. Failures one and two clear ownership and are immediately eligible under
  version 1; the third atomically records count three and transitions to a new
  open revision. No implicit backoff or reset exists.
- Every processor claim and result is append-only. A deterministic downstream
  operation ID and same-transaction semantic receipt let a reclaimer adopt an
  already committed result after a crash without invoking the semantic write
  twice. Lease expiry records attempt history but does not consume the
  retryable-failure budget.
- A store-owned `ConflictScopeIsolationProof` binds repository/partition
  identity, the exact frozen scope set, ledger range and event position,
  referenced conflicting byte digests, unaffected partition set, store
  topology fingerprint, proof revision, and digest. Only a proof validated in
  the same repository snapshot may authorize unrelated progress. Unfreeze
  requires an append-only repair generation plus clean replay through its final
  position under a successor proof.
- Release is a typed successor algebra: it binds the predecessor authority,
  exact repaired subset, repair generation, clean replay coordinate and state
  digest, and atomically publishes the prior frozen set minus only that subset.
- Projection migrations preserve immutable policy-relative system-time
  generations. They never rewrite a historical view. A migration freezes a
  base repository watermark and complete server-derived slot membership, emits
  one result per slot under a target policy bundle, consumes a contiguous
  catch-up ledger through a final watermark, and atomically publishes a
  certificate plus active-policy pointer. Arrivals at or below the final
  watermark are included in catch-up; later arrivals use the active policy.
  Failure exposes the prior complete generation. Rollback is a new forward
  migration to the earlier policy bytes, never pointer or revision rollback.
- Every later projection-changing write publishes a complete immutable
  successor generation, certificate, pointer-history entry, and active pointer
  in the graph/event transaction. Historical selection uses the greatest
  server publication coordinate not later than `system_as_of`; equal timestamps
  are ordered by monotonic publication sequence.

## Alternatives And Consequences

- Rejecting every cursor request that supplies `page_size` is simpler but makes
  pagination ergonomics brittle without improving snapshot integrity. Ignoring
  a changed scope is unsafe. The selected rule validates scope and permits only
  presentation-size changes.
- Persisting failed receipt checks would make invalid external evidence consume
  idempotency coordinates and permit denial of service. Silent receipt
  downgrade would forge attribution. Zero-write rejection is the conservative
  choice.
- Recomputing historical projections in place would erase which policy was
  authoritative at a system time. Immutable generations preserve bitemporal
  truth and make rollback auditable.
- A boolean isolation claim cannot prove blast-radius containment. The typed
  store proof is required even though it adds durable metadata.

## Authority, Rollout, And Compatibility

`docs/design/conflict_attention.md` owns D01-D03. The semantic architecture
owns D04-D05 and continues to defer event-envelope algebra to
`docs/design/event_model.md`. The replay-decision artifact binds all three and
must be regenerated after their bytes change. Existing provider legacy models
and methods remain unchanged. These decisions add only new protocol/state
records and do not reinterpret rollout-step-1 bytes.

The authority chain is:

`memorii_spec.md -> event_model.md / semantic_ingestion_architecture.md / conflict_attention.md -> equal_version_replay_decision-v1.json -> validator -> implementation contracts -> tests/timings/workflows`.

## Attack And Verification Matrix

- Cursor: omitted/equal/different scope, order/duplicates, variable page sizes,
  every byte mutation, expiry boundary, unavailable snapshot, cross-principal,
  cross-tenant, protocol and signer rotation, concurrent introduction and
  resolution between every page.
- Receipt/idempotency: invalid then valid receipt, valid then mutated retry,
  loss of acknowledgement, two-operation nonce race, stale revision, exact and
  divergent operation retry, and failure after every prospective append.
- Processor: claim/renew/fail/complete at every token/epoch boundary, crash and
  reopen after each transition, and exact third-failure semantics.
- Isolation/recovery: missing/partial/cross-repository/stale/topology-mismatched
  proofs, corruption in one and several partitions, unrelated writes with and
  without proof, repair replay failure, and unfreeze race.
- Migration: missing/extra/duplicate slot, stale read set, base/catch-up gap or
  reorder, late arrival on both sides of cutover, crash at every publication
  boundary, same-target retry, divergent plan reuse, fingerprint mixing,
  forward rollback, genesis replay, and checkpoint-tail replay.
- Identity hygiene: requirement/work coordinates may occur only in this plan
  and typed traceability fields; public, persisted, test, fixture, job, and
  artifact names are behavioral.

Executable ownership for the remediated decisions is fixed as follows. Every
new unit node is measured in `memorii/tests/ci/unit-test-durations.json` and is
collected by all four deterministic shard plans. The integration owners are
added explicitly to `.github/workflows/pr-gates.yml` job
`semantic-ingestion-generation`, whose timeout remains 15 minutes unless the
measured combined run proves that budget insufficient. The implementation
WorkPlan records the workflow's exact pre-change collection, then the observed
post-change count and duration; no estimated count is accepted.

| Requirement | Exact test owner | Required observable assertion | PR owner |
| --- | --- | --- | --- |
| D01 cursor scope/authentication/snapshot | `memorii/tests/unit/core/test_conflict_attention.py`; `memorii/tests/unit/core/test_conflict_attention_repository.py`; `memorii/tests/unit/core/test_conflict_attention_provider_service.py`; `memorii/tests/integration/test_conflict_attention_persistence.py` | malformed, expired, rotated/revoked-key, cross-tenant, cross-principal, authorization-changed, and unavailable-snapshot cursors return exactly `invalid_conflict_cursor`, read zero conflict payloads, and never create a fallback snapshot; complete authorization `(a,b,c)` plus listing subset `(a,b)` are retained as distinct fields and expose only subset members; omitted/equal continuation subset preserves the sequence while narrowed, widened, reordered, or duplicate subset returns `invalid_cursor_scope`; authorization expansion/reduction returns `invalid_conflict_cursor` even when the listing subset remains authorized; omitted fresh scope makes both sets equal and invalid fresh scopes return `invalid_conflict_scope` before repository read | unit shards; `semantic-ingestion-generation` |
| D02 receipt/idempotency/attempt history | `memorii/tests/unit/core/test_conflict_attention.py`; `memorii/tests/integration/test_conflict_attention_persistence.py` | failed verification writes no receipt, nonce, proposal, work, attempt, or transition and a corrected receipt succeeds; exact committed retry calls neither verifier nor nonce consumer; crash after semantic commit adopts one durable receipt; failures one/two remain claimable and failure three appends `processing_exhausted` plus a new open revision | unit shards; `semantic-ingestion-generation` |
| D03 isolation/repair/release | `memorii/tests/unit/core/semantic_ingestion/test_event_replay.py`; `memorii/tests/integration/test_semantic_ingestion_replay.py` | malformed, stale, cross-repository, topology-mismatched, overlapping, or rollback proof publishes whole-repository freeze; initial and additive isolation CAS exact union; failed/substituted/incomplete release leaves current control byte-identical; successful release removes exactly the repaired subset | unit shards; `semantic-ingestion-generation` |
| D04 migration and normal projection history | `memorii/tests/unit/core/semantic_ingestion/test_projection_history.py`; `memorii/tests/integration/test_semantic_ingestion_replay.py` | exact normal-write retry returns the same certificate/generation/pointer and divergent bytes reject; graph/event and pointer publication are atomic; equal-time history chooses greatest publication sequence; stale current materialization returns `stale_materialized_projection`; failed migration retains the old pointer; genesis and checkpoint-tail replay reconstruct the complete pointer chain byte-identically | unit shards; `semantic-ingestion-generation` |

## Evidence Maturity

- Specified: canonical amendments are present in the conflict-attention and
  semantic-ingestion designs.
- Derivable: cursor, receipt/attempt, isolation/unfreeze, and projection
  migration/certificate/generation/pointer algorithms are closed at the
  current design bytes.
- Implemented or later: explicitly unavailable until this design WorkPlan is
  complete and the implementation WorkPlan resumes.

Current frozen candidate SHA-256 values:

- semantic-ingestion architecture:
  `53b796de59dead7fb16902bc8c53c0225628b602e53c5ee4c9f91dd1fe1e2261`;
- event model:
  `9ce93e4a826f3e47b2e41fa06d2ec1e40bb0cad2475fa0527d9bb2c9ab3acdec`;
- conflict-attention design:
  `b2d58a05a77c4105d2ce41433024bcb88d41204b6f2de8a86e76b699d8eb66de`;
- replay-decision artifact:
  `f04b778e8e23632ff732199f6776ebbf740210d20778338bb7524b316f3ed241`;
- replay-decision validator:
  `41a50fa6847a5c96704536521842761b3400c79fb8e75096193c87b72d480262`.

Final deterministic evidence at the hashes above: the standalone decision
validator exited 0; all 30 decision mutation tests passed; the explicit
WorkPlan-pin comparison matched every canonical file; field-aware identity
hygiene and `git diff --check` exited 0.

## Review Findings And Dispositions

- Spec DREV-001: confirmed, `Not applicable`, `blocks_approval`, public
  contract/authorization. Resolved by strict new-request scope grammar and
  pre-read rejection.
- Spec DREV-002 and correctness DREV-002: confirmed, `P2`,
  `changes_required`, lifecycle/transactional recovery. Resolved by immutable
  attempt lineage plus deterministic downstream operation receipts.
- Spec DREV-003 and correctness DREV-003: confirmed, `P2`,
  `changes_required`, integrity recovery. Resolved by typed repair generation,
  release proof, and atomic freeze-control successor algebra.
- Spec DREV-004 and correctness DREV-004: confirmed, `P2`,
  `changes_required`, bitemporal migration. Resolved by monotonic pointer
  history, deterministic `system_as_of` selection, and normal-write successor
  publication.
- Correctness DREV-001: confirmed, `P2`, `changes_required`, security. Resolved
  by closed claims, principal/tenant/authorization/snapshot binding,
  domain-separated MAC grammar, and explicit key lifecycle.
- Final correctness DREV-005: confirmed, `P2`, `changes_required`, integrity
  recovery/concurrency. Resolved by making initial and additional isolation
  proofs atomically publish additive freeze-control successors under CAS,
  including the whole-repository fallback.
- Spec DREV-005: confirmed, `Not applicable`, `changes_required`, authority
  governance. The implementation WorkPlan current-baseline pins are updated as
  the final closure action before implementation resumes.
- Test DREV-001 and DREV-002: confirmed, `Not applicable`,
  `changes_required`, verification governance. Resolved by correcting all test
  and timing owners and removing stale current-state claims in the related
  design WorkPlan.
- Final test DREV-001 and DREV-002: confirmed, `Not applicable`,
  `changes_required`, verification governance. Resolved by labeling the prior
  plan hashes as historical and adding exact D01-D04 unit/integration files,
  failure assertions, PR job, timeout, timing manifest, and observed-collection
  rule.

Final spec, correctness/security, and test delta reviewers approved the
remediated bytes with `remaining_validated_p1_p2: []` and no residual
verification-governance finding.

## Review Budget And Stop Rules

One full three-role review, at most two bounded remediation passes, then one
fresh final design review if the canonical semantics change materially. Stop
only for a product choice not resolved by the governing precedence and
universal invariants.

## Next Action

None. This design operation is closed. The parent implementation WorkPlan is
resumed at the authenticated conflict reader/list slice.

# Recovery/Reconciliation Fresh-Owner Propagation

- Parent WorkPlan: `../implementation.plan.md`
- Status: active; resumed 2026-08-26 after linked debugging closure
- Linked debugging WorkPlan (complete):
  `../../semantic-ingestion-recovery-reconcile-baseline-debug-2026-08-18/debug.plan.md`
- Base revision: `5bd516bf4b576d927f1a32edb01531b6f18419e6` (closure commit of
  the linked debugging operation; supersedes `b9daf00a` plus dirty tree)
- Prior implementation candidate: `implementation-candidate-manifest-v1.json` is superseded; no current implementation candidate is claimed

## Objective

Map and prepare one real recovery/reconciliation family so every invocation
creates a fresh private canonical-evidence owner, revalidates retained source
bytes, binds/seals only at the authoritative durable boundary, and carries a
leased exact result to an approved durable or replay consumer without reusing a
sibling or persisted capability.

The exact production path under investigation is:

```text
ProviderMemoryService.reconcile_memory_evolution
  -> ProviderIngestionCoordinator.reconcile
  -> _run_semantic_ingestion
  -> durable/replay consumers
```

## Allocated Requirements

| Requirement | Allocation in this packet | Initial state |
| --- | --- | --- |
| `VCC-R01` | Measurement contribution only; no acceptance claim without the required production reduction evidence | partial / not started |
| `VCC-R02` | Revalidated retained-source canonical result for the recovery family | not started |
| `VCC-R03` | Fresh explicit sealed authority; no ambient or persisted capability | not started |
| `VCC-R05` | Existing semantic/provenance validation remains mandatory before staging | not started |
| `VCC-R06` | Current recovery-local writer admission remains mandatory | not started |
| `VCC-R07` | Exact tenant, operation, generation, fence, and writer checks at the consumer | not started |
| `VCC-R08` | Fresh reservation, tokenized lease drain, and capacity fallback behavior | not started |
| `VCC-R09` | Durable/replay bytes, outcome, and reload identity for this family | not started |
| `VCC-R10` | Non-test production caller reaches the fresh owner and consumer | not started |
| `VCC-R11` | One content-free terminal snapshot per recovery invocation | not started |
| `VCC-R12` | Disabled/refused recovery remains on the full validated path | not started |

## Explicit Non-Goals

- Do not change canonical codec/profile semantics, public schemas, persisted
  schemas, event semantics, writer policy, authorization, or transactions.
- Do not reuse the direct-ingress owner, its issuer, binding, lease, or any
  capability persisted from a previous invocation.
- Do not extend composite, memory-write, Hermes, or unrelated replay families
  in this packet.
- Do not claim whole-program replay, all-root closure, performance reduction,
  candidate freeze, CI, or final review completion.

## Known Starting Finding

The existing recovery/reconciliation route reaches `_run_semantic_ingestion`
with `canonical_evidence_arena=None`. It therefore has no fresh staged owner,
sealed binding, or lease at the durable/replay boundary. This is a readiness
finding, not evidence that substitution is currently permitted.

## Expected Production Entrypoint Binding Ledger

| Trigger family | Non-test composition/root | Required authority and consumer proof | Status |
| --- | --- | --- | --- |
| `reconcile_memory_evolution` | `ProviderMemoryService.reconcile_memory_evolution` | fresh private arena created per recovered operation and injected through the coordinator | implemented / focused proof blocked |
| `_run_semantic_ingestion` recovery handoff | `ProviderIngestionCoordinator.reconcile` | retained V3 marker is loaded by exact fence; scope derives from ingress, marker generation/fence, and current writer; bind-and-seal follows staging | implemented / focused proof blocked |
| selected durable/replay consumer | `SemanticIngestionAtomicStore.reload_bootstrap_recovery_replay_v3` | object-identity lease is decoded and checked against the loaded prepared source, marker, tenant, writer, and exact bytes before replay reconstruction | implemented / focused proof blocked |
| disabled/capacity-refused recovery | same real recovery root | no sealed substitution; ordinary validated path produces the same durable/public outcome | preflight required |

Only the first three rows have implementation changes. None has sufficient
focused production evidence while the recorded baseline failures remain.

## Planned Deterministic Validation Matrix

| Behavior | Planned focused proof | Failure signal |
| --- | --- | --- |
| Fresh owner per recovery/redelivery invocation | two exact recovery invocations through the public root | reused issuer, owner, binding, or lease identity |
| Stage then bind/seal ordering | observe canonical result after validation and before durable consumer | empty staging, pre-seal lookup, or post-seal admission |
| Five-coordinate integrity | independently mutate tenant, operation, generation, fence, and writer | conflict/no durable handoff |
| Recovery-local writer freshness | advance or substitute current writer binding where the real harness supports it | writer-unavailable/conflict rather than substitution |
| Durable/replay identity | compare prepared/durable/reload bytes and idempotent outcome across enabled and disabled/refused modes | byte, digest, record, reload, or public-outcome drift |
| Lease lifecycle | deterministic close/release, exception, miss, and consumer rejection paths | duplicate release, underflow, stranded reservation, or more than one terminal snapshot |
| Observability isolation | completed, validation-failed, exception, cancellation if supported, disabled, and refusal | content-bearing snapshot, duplicate emission, or sink outcome changing product state |

## Evidence Maturity

| Evidence | Maturity |
| --- | --- |
| Production path/caller map | mapped by read-only explorer |
| Authoritative-coordinate map | mapped in source; focused proof blocked |
| Durable/replay consumer selection | mapped; focused proof blocked |
| Focused deterministic tests | blocked by pre-existing public-root/replay failures |
| v11 source-shape update | regenerated; validator passed 32 mutations |
| Performance contribution | not started |
| Candidate freeze/review/CI | not started |

## Delegation Ledger

| Task | Role | Ownership | Status |
| --- | --- | --- | --- |
| Recovery caller, retained-state, coordinate, and durable-consumer map | `code-mapper` capacity fallback to read-only explorer | read-only preflight consultation | complete |
| Existing harness, deterministic schedule, and regression-test inventory | `test-reviewer` | consultation unavailable because of inappropriate freeze gating; existing acceptance matrix retained | unavailable |
| Recovery implementation | sole writer | provider coordinator, atomic replay seam, service factory, and governance packet | partial / verification blocked |

## Implementation Attempt And Blocking Evidence

- `ProviderMemoryService` now passes a private repository-owned fresh-arena
  factory to `ProviderIngestionCoordinator`; the factory gives every recovery
  loop item its own enabled-mode/dispatcher-owned arena.
- Recovery loads one existing `BootstrapWriterHandoffMarkerV3` through a new
  atomic-store public method keyed by exact `OperationFenceBinding`. It never
  reconstructs or persists a handoff marker.
- When the marker exists and its writer binding is current, recovery revalidates
  the retained `PreparedSource`, stages it, binds/seals exact tenant/operation/
  generation/fence/current-writer coordinates, and holds the lease through the
  existing `reload_bootstrap_recovery_replay_v3` call. The atomic consumer
  decodes leased bytes and rechecks loaded prepared data, marker, all five
  coordinates, member evidence, and current writer before replay reload.
- Lease release is in the coordinator `finally`; disabled arenas take the
  existing full path. No capability is persisted or reused.
- Focused validation is blocked before the new recovery branch in
  `test_public_jsonl_reconcile_resumes_preplanning_outage_without_redelivery`:
  `ProviderMemoryService._ensure_writer_admission_record` raises
  `SemanticWriterAdmissionError: writer admission is already bound differently`
  against the fixture's durable writer record.
- Existing `test_bootstrap_recovery_replay_v3.py` also fails without a lease:
  `reload_bootstrap_recovery_replay_v3` returns `None`; V3 reopen tests report
  existing control/claim outcomes (`preplanning` versus `terminal`, `foreign`
  versus `consumed`). These occur in the current dirty tree's replay path and
  prevent establishing recovery equivalence without changing adjacent behavior.

## Exact Blocker

The current public recovery harness cannot reach the new recovery branch
because its provider root attempts to write an evidence-only admission over an
already durable-bound writer record. In parallel, the existing no-lease V3
replay reload baseline is nonfunctional. Resolving either requires ownership
and a decision about the pre-existing writer-admission/replay changes outside
this bounded recovery slice.

## Pause Record

The implemented-but-unverified recovery wiring remains in the working tree.
This implementation milestone is paused rather than completed or globally
blocked while the linked debugging operation isolates the two baseline failure
families. No further recovery implementation or acceptance claim may proceed
until that operation records a causal result.

## Transferred Debug Findings (2026-08-19)

- Confirmed WA correction is complete in the linked debug operation: provider
  ingress now resolves before fallback writer-admission initialization, so
  absent/rejected ingress creates no durable writer record while valid and
  corrupt record behavior remains fail closed. This packet does not own that
  correction.
- Confirmed V3 atomic/reconcile findings remain unresolved here: fresh-owner
  reconciliation/replay authority propagation and the related durable consumer
  proof are not modified by the debug correction. They transfer unchanged to
  this paused implementation packet when it resumes.
- Round-3 debug work confirms writer-admission construction safety is resolved;
  only the transferred V3 authority/reconcile scope remains for this packet.

## Next Action (superseded 2026-08-26)

Await the linked debugging operation's causal signatures before resuming this
implementation milestone.

## Resumption Record (2026-08-26)

- The linked debugging operation completed with all three independent
  reviewers approving closure (`remaining_validated_p1_p2: []`); its closure
  record and candidate `debug-candidate-identity-v4.json` are at revision
  `5bd516bf4b576d927f1a32edb01531b6f18419e6`.
- Both former blockers are cleared: the writer-admission reopen conflict is
  corrected in the linked operation, and the no-lease V3 replay reload family
  is a corrected test contract (complete Atlas/Bob proposal for Found/consumed;
  abstained stays claimed/no-replay). The focused recovery/replay proofs this
  packet planned are now reachable.
- Transferred review follow-ups absorbed into this milestone's matrix:
  1. Resume-after-recovered-outage with exactly-once redelivery and
     `evolution_committed` has no remaining proof after the legacy outage test
     deletion; this packet's durable/replay identity row must add that class
     with a governing-doc citation for the V3 ordering contract.
  2. The deferred `_validate_semantic_runtime_after_ingress` behavior
     (validation at first resolved ingress instead of construction, and
     evidence-only bootstrap of runtime-writer compositions over planes with
     no writer record) must be ratified against governing documents and pinned
     by a focused test; the `_provider_ingestion._semantic_runtime` private
     bridge should be removed in favor of a stored constructor reference.
- Remaining transferred follow-ups owned by the later trigger-family
  milestone (not this packet): WA family-proof gaps across
  factory/Hermes/filesystem roots and JSONL variants, the no-runtime
  construction no-write assertion, the foreign-manifest defense-in-depth
  pin, and the vestigial `_owns_writer_admission_record` cleanup.

## Validation Matrix Results (2026-08-26)

Three focused production-root proofs were added to
`memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_coordinator_v3.py`
and pass at the current revision:

| Matrix row | Proof | Result |
| --- | --- | --- |
| Fresh owner per recovery invocation | `test_redelivery_recovery_uses_fresh_owner_and_leases_exact_prepared_bytes`: crash-after-handoff interruption, recovery by exact redelivery through the public root; one new arena per delivery; scope coordinates equal marker/ingress/writer; lease released; exactly one content-free `enabled/completed` terminal snapshot; zero plain-path PreparedSource encodes after the lease reaches the reload consumer; third delivery is an idempotent lost-ack replay | passed |
| Five-coordinate integrity | `test_redelivery_recovery_rejects_mutated_lease_coordinates`: foreign generation, fence, operation, writer, and tenant each fail closed at `reload_bootstrap_recovery_replay_v3` before reconstruction; the drained lease cannot re-authorize | passed |
| Durable/replay identity across modes | `test_redelivery_recovery_outcomes_are_identical_across_enabled_and_disabled_modes`: identical public outcomes, idempotent third deliveries, identical durable kind projections, and equal found-state recovery indexes across enabled and disabled modes on JSONL | passed |

## Structural Finding: Reconcile Leased Branch Is Unreachable (2026-08-26)

Running the matrix exposed that the milestone's assumed recovery door is
structurally unreachable:

- `ProviderIngestionCoordinator.reconcile` enters its fresh-owner/lease branch
  only when `recover_execution_plan(fence)` returns a persisted
  `execution_plan` generation member and a handoff marker exists.
- The only production writer of `execution_plan` members is
  `lease_session.checkpoint_execution_plan` at `ingestion.py` (ordinary path),
  which V3 bootstrap operations never reach: they return through the V3
  handoff fast path before ordinary checkpointing. V3 operations therefore
  persist markers without plans, and ordinary operations persist plans
  without markers. The conjunction never occurs, so the implemented
  per-recovery-item arena factory, `_stage_recovery_prepared_source`, and the
  reconcile lease plumbing have no production caller.
- The reachable V3 mid-ingestion recovery door is exact redelivery through
  the direct root (marker `already_started`), consistent with the governing
  SIA-R23 redelivery/replay contract and the marker's own idempotence design
  ("an idempotent marker still consumes a fresh lease").

Disposition: the redelivery door is now wired and proven (below). The
unreachable reconcile branch is retained unchanged pending an explicit
decision: repairing it requires persisting a V3 execution plan (a durable
record-content change that returns to `$build-design`), while removing it is
behavior-neutral dead-code cleanup. This packet does not decide that
unilaterally.

## Lease Propagation Correction (2026-08-26)

The redelivery door had its own gap: `_bootstrap_prepare_and_handoff`
released its sealed lease at the writer handoff, so `_run_semantic_ingestion`
reached `reload_bootstrap_recovery_replay_v3` with no lease and the reload
validation/substitution wiring was dead on the direct path too. Corrected:

- `_bootstrap_prepare_and_handoff` now returns the handoff result together
  with the still-open lease and releases it on every failure exit.
- The V3 fast path passes `canonical_evidence_lease` into
  `_run_semantic_ingestion` and releases it in a `finally`, mirroring the
  recovery loop's intended lease lifetime; the non-V3 fall-through releases
  it before the ordinary path.
- `reload_bootstrap_recovery_replay_v3` now receives an unreleased lease on
  first delivery and redelivery; its `_validate_recovery_prepared_lease`
  checks (decode-and-compare against retained prepared bytes, marker,
  ingress, writer, digest, and member evidence) execute in production.

## Updated Production Entrypoint Binding Ledger

| Trigger family | Non-test composition/root | Required authority and consumer proof | Status |
| --- | --- | --- | --- |
| `reconcile_memory_evolution` | `ProviderMemoryService.reconcile_memory_evolution` | per-item fresh arena, marker load by exact fence, stage/bind/seal, lease into reload | implemented but structurally unreachable; see the finding above; disposition pending |
| Exact redelivery recovery | `ProviderMemoryService.sync_event` (same operation id) over a retained marker + found index | fresh private arena and sealed lease through `_bootstrap_prepare_and_handoff` into `bootstrap_writer_handoff` and `reload_bootstrap_recovery_replay_v3`; five-coordinate and drained-lease rejection; enabled/disabled parity | proven by the three focused production-root proofs above |
| disabled/capacity-refused recovery | same real roots in disabled mode | no sealed substitution; ordinary validated path produces the same durable/public outcome | proven for the redelivery family (mode-parity proof); capacity-refused variant remains covered by arena unit evidence |

## Next Action

Decide the unreachable reconcile branch disposition (repair via a V3
execution-plan persistence design change, or remove the dead branch), then
close this milestone's remaining transferred follow-up (runtime-validation
ratification) before extending proofs to the remaining trigger families.

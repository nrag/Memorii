# Recovery/Reconciliation Fresh-Owner Propagation

- Parent WorkPlan: `../implementation.plan.md`
- Status: paused; linked debugging operation owns baseline causal isolation
- Linked debugging WorkPlan:
  `../../semantic-ingestion-recovery-reconcile-baseline-debug-2026-08-18/debug.plan.md`
- Base revision: `b9daf00a0e6956e51106756f1baaf23190c688bb` plus the active dirty-tree remediation state
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

## Next Action

Await the linked debugging operation's causal signatures before resuming this
implementation milestone.

# Recovery/Reconciliation Fresh-Owner Propagation

- Parent WorkPlan: `../implementation.plan.md`
- Status: complete for the redelivery recovery door (2026-08-26, commit
  `4560d29`); user decision recorded 2026-08-26: host-independent recovery is
  required because Memorii must function as a tool without agent-harness
  changes, so the unreachable reconcile branch is promoted to a required
  `$build-design` repair round (reachability, recovery-ingress authority,
  and an internal reconcile trigger owned by Memorii adapters or the
  service; no production invoker of `reconcile_memory_evolution` exists
  today). The redelivery proofs remain the redelivery-safety leg of the
  contract per SIA-R23.

## Design Direction For The Repair Round (user answers, 2026-08-26)

The user answered the two open design questions:

1. Trust model, do-not-overdesign: the Memorii/harness interface is not
   authenticated and Memorii likely runs as a separate process; the only
   enforceable guarantee is that write locations are locked down so only the
   Memorii process can write (reads allowed). Recovery provenance must
   therefore derive from retained durable records under process write
   exclusivity, not from reconstructed authenticated ingress or new
   capability machinery.
2. Trigger: the product requires automatic periodic curation and
   organization of memories across planes (see the product document's
   Learning & Consolidation Plane); the recovery sweep must be a phase of
   that periodic process rather than a new mechanism.

Shape agreed for the design round: marker-keyed reconcile admission from
retained state (no new persisted records, no V3 execution-plan
persistence), recovery scope derived from retained records, a bounded
maintenance tick owned by Memorii (piggybacked rate-limited sweep on public
calls plus an explicit maintenance entry point), attempts counted against
the existing lease-recovery budget, and a documented process-exclusive
write-permission deployment premise.
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

The production path this packet originally targeted was the reconcile loop;
the validation matrix established that the reachable recovery door for V3
mid-ingestion interruption is exact redelivery through the direct root (see
the Structural Finding section), and the proofs below close that door:

```text
ProviderMemoryService.sync_event (same operation id, retained marker + found index)
  -> _bootstrap_prepare_and_handoff (fresh arena, stage, bind/seal, lease)
  -> _run_semantic_ingestion (canonical_evidence_lease)
  -> reload_bootstrap_recovery_replay_v3 (lease validation and substitution)
```

## Allocated Requirements

| Requirement | Allocation in this packet | Final state (2026-08-26) |
| --- | --- | --- |
| `VCC-R01` | Measurement contribution only; no acceptance claim without the required production reduction evidence | not claimed (performance milestone owns it) |
| `VCC-R02` | Revalidated retained-source canonical result for the recovery family | proven: redelivery stages the retained prepared source and reuses leased bytes downstream |
| `VCC-R03` | Fresh explicit sealed authority; no ambient or persisted capability | proven: one fresh arena per recovery delivery; drained lease cannot re-authorize |
| `VCC-R05` | Existing semantic/provenance validation remains mandatory before staging | proven: staging follows preparation/publication validation; zero plain re-encodes after the lease reaches the consumer |
| `VCC-R06` | Current recovery-local writer admission remains mandatory | proven: lease and consumer recheck current admission digest and epoch |
| `VCC-R07` | Exact tenant, operation, generation, fence, and writer checks at the consumer | proven by the five-coordinate mutation proof |
| `VCC-R08` | Fresh reservation, tokenized lease drain, and capacity fallback behavior | lease drain proven at the consumer; capacity fallback remains arena-local evidence |
| `VCC-R09` | Durable/replay bytes, outcome, and reload identity for this family | proven: mode-parity outcomes, durable projections, found-state identity, idempotent third delivery |
| `VCC-R10` | Non-test production caller reaches the fresh owner and consumer | proven for the redelivery door; reconcile door structurally unreachable (finding) |
| `VCC-R11` | One content-free terminal snapshot per recovery invocation | proven: exactly one `enabled/completed` snapshot, content-free |
| `VCC-R12` | Disabled/refused recovery remains on the full validated path | proven for disabled mode via the parity proof; capacity-refused remains arena-local evidence |

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

Superseded 2026-08-26 by the Updated Production Entrypoint Binding Ledger
below: the first three rows' reconcile-door wiring is implemented but
structurally unreachable, and the proven recovery door is redelivery.

| Trigger family | Non-test composition/root | Required authority and consumer proof | Status at packet start |
| --- | --- | --- | --- |
| `reconcile_memory_evolution` | `ProviderMemoryService.reconcile_memory_evolution` | fresh private arena created per recovered operation and injected through the coordinator | implemented / focused proof blocked |
| `_run_semantic_ingestion` recovery handoff | `ProviderIngestionCoordinator.reconcile` | retained V3 marker is loaded by exact fence; scope derives from ingress, marker generation/fence, and current writer; bind-and-seal follows staging | implemented / focused proof blocked |
| selected durable/replay consumer | `SemanticIngestionAtomicStore.reload_bootstrap_recovery_replay_v3` | object-identity lease is decoded and checked against the loaded prepared source, marker, tenant, writer, and exact bytes before replay reconstruction | implemented / focused proof blocked |
| disabled/capacity-refused recovery | same real recovery root | no sealed substitution; ordinary validated path produces the same durable/public outcome | preflight required |

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

| Evidence | Maturity (updated 2026-08-26) |
| --- | --- |
| Production path/caller map | mapped; the redelivery door is the proven recovery path; the reconcile door is mapped and proven unreachable |
| Authoritative-coordinate map | proven by the five-coordinate mutation rejection at the reload consumer |
| Durable/replay consumer selection | proven: `reload_bootstrap_recovery_replay_v3` receives and validates the sealed lease |
| Focused deterministic tests | three production-root proofs passing at `4560d29` (fresh owner, mutations, mode parity) |
| v11 source-shape update | regenerated; validator passed 32 mutations |
| Performance contribution | not claimed (performance milestone owns it) |
| Candidate freeze/review/CI | not claimed |

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

## Reconcile-Branch Disposition Resolved (2026-08-29, by the legacy-path removal operation)

The pending disposition above is resolved by the linked removal operation
(`../semantic-ingestion-legacy-path-removal-2026-08-26/`), slice 2: the
ordinary/reconcile branch was REMOVED rather than repaired — the retained
state admission is marker-keyed with no execution-plan persistence and no
reconstructed ingress, and `_run_semantic_ingestion` is V3-only (foreign
result types rejected). The "repair via V3 execution-plan persistence"
option is therefore moot: there is no branch left to repair, and any future
reconcile-family trigger would be a new design, not a repair of this one.

The parent's "Final branch review" milestone inherits the removal
operation's broad-gate evidence (recorded in that operation's WorkPlan).
The remaining transferred follow-up (runtime-validation ratification) stays
open on the parent roadmap; it is unaffected by this disposition.

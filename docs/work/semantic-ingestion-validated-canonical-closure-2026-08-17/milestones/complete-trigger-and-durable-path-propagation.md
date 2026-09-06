# Complete Trigger And Durable-Path Propagation

- Parent WorkPlan: `../implementation.plan.md`.
- Status: complete (family-proof closure 2026-08-26, commit `02502eb`);
  follow-ups recorded in the Family-Proof Closure section.
- Requirements: direct prepared-source evidence for `VCC-R02` through `VCC-R10`;
  lifecycle/observability evidence for `VCC-R08` and `VCC-R11`.
- Started: `2026-08-18`; completed: `2026-08-26`.
- Scope: direct `sync_event` prepared-source propagation, the private owner
  lifecycle, and per-family sealed proofs for composite, memory-write, and
  Hermes hooks. Recovery/replay is owned by the recovery packet.

## Objective

Run the direct prepared-source production ownership and durable handoff through
the typed canonical-evidence control path without altering validation or
persistence semantics:

- pass typed arena authority through `ProviderMemoryService.sync_event`,
- propagate typed closure context to the prepared-source graph/atomic handoff,
- keep failure behavior identical for disabled, capacity-refused, and completed paths,
- preserve retry/replay and writer-admission identity and outcomes.

## Production Entrypoints Verified

| Trigger | Primary composed owner | Typed closure owner | Evidence and outcome
| --- | --- | --- | --- |
| `sync_event` prepared source | `ProviderMemoryService._ingest_event` | `CanonicalEvidenceArena` + `ProviderIngestionCoordinator.ingest` | staged, sealed, leased exact prepared bytes enter `SemanticIngestionAtomicStore.bootstrap_writer_handoff`; focused production-root proof |
| `_sync_composite_event` | `ProviderMemoryService._sync_composite_event` | arena construction + sealed lease | proven 2026-08-26: `test_every_trigger_family_stages_seals_and_leases_prepared_bytes[composite]` |
| `apply_memory_write` | `ProviderMemoryService.apply_memory_write` | arena construction + sealed lease | proven 2026-08-26: same family proof `[memory_write]` and `[hermes_write]` |
| Hermes hooks | `HermesMemoryProvider.sync_turn`/`on_memory_write` | arena construction + sealed lease per child | proven 2026-08-26: same family proof `[hermes_turn]` (both composite children) and `[hermes_write]` |
| Recovery/replay consumers | redelivery door (recovery packet) | fresh owner + sealed lease into the replay reload | proven in the recovery packet; the reconcile-door variant is structurally unreachable (finding there) |

## Current Remediation Record

- The direct prepared-source and lifecycle edits are present in:
  - `memorii/memorii/core/provider/service.py`
  - `memorii/memorii/core/provider/ingestion.py`
  - `memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py`
  - `memorii/memorii/core/semantic_ingestion/bootstrap_graph_host.py`
  - `memorii/memorii/core/semantic_ingestion/bootstrap_graph_coordinator.py`
  - `memorii/memorii/core/semantic_ingestion/source_normalization_repository.py`
  - `memorii/memorii/core/memory_evolution/atomic_store.py`
  - `memorii/memorii/core/memory_evolution/ingestion_contracts.py`
  - `memorii/memorii/core/memory_evolution/writer_admission.py`
  - `memorii/memorii/core/memory_plane/store.py`
- `CanonicalEvidenceArena` issues an independent unforgeable token for every
  sealed lookup. Closing stays in `closing` until every token drains; a final
  drain clears payload, releases the reservation, and emits exactly once.
- `ProviderMemoryService` owns one repository dispatcher and passes it to each
  private arena. The dispatcher retains only typed content-free terminal
  snapshots; unavailable or malformed sink outcomes cannot alter the product
  result.
- Focused tests added or extended:
  - `memorii/tests/unit/core/semantic_ingestion/test_canonical_evidence_arena.py`
  - `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_coordinator_v3.py`
  - `memorii/tests/unit/core/test_provider_service.py`

## Reviewer Remediation

### Consolidated Reviewer Findings

| Reviewer | Status | Finding | Resolution |
| --- | --- | --- | --- |
| independent candidate review | confirmed; P2 / changes required / runtime correctness | Multiple leases for one cache key aliased a raw key and could underflow or strand a close. | Each successful lookup now receives a private random token; deterministic two/N lease, duplicate/stale/foreign, close-vs-final-release, and reacquisition tests pass. |
| independent candidate review | confirmed; Not applicable / changes required / operability | Terminal observability used a success-shaped no-op instead of a service-composed repository sink. | `ProviderMemoryService` owns one retaining typed dispatcher; enabled and disabled roots, every supported terminal reason, privacy, exactly-once, and unavailable parity are focused-tested. |
| independent candidate review | confirmed; Not applicable / changes required / verification | The M3 packet overstated all-trigger/replay completion. | This packet is reopened and every unproven root is explicitly incomplete. The overlapping lifecycle/observability finding is recorded once here. |

## Reviewer-Closure Artifacts

- `remaining_validated_p1_p2: []` for this lease/dispatcher correction only.
- `remaining_blocks_approval: []` for this bounded correction only.
- `remaining_changes_required: [all-root/recovery/replay proof, performance reduction, candidate refreeze and independent review]`.

## Family-Proof Closure (2026-08-26)

Every trigger family now has a focused production-root sealed-capability proof:

| Trigger family | Proof | Result |
| --- | --- | --- |
| `direct_sync` | existing `test_verified_production_root_leases_prepared_bytes_into_writer_handoff` and redelivery proof | passing (pre-existing plus the recovery milestone's proofs) |
| `direct_composite_sync`, `direct_memory_write`, `hermes_sync`/`hermes_memory_write` | `test_every_trigger_family_stages_seals_and_leases_prepared_bytes` in `test_bootstrap_graph_coordinator_v3.py`: composite child, direct memory write, Hermes `sync_turn` (both composite children), and Hermes `on_memory_write` each construct a fresh arena per delivery, consume an unreleased sealed lease with member evidence at `bootstrap_writer_handoff` and `reload_bootstrap_recovery_replay_v3`, release it, and emit exactly one content-free `enabled/completed` terminal snapshot; controls reach terminal | `4 passed in 923.04s` |

Writer-admission family gaps from the debug closure review (TR-F1/F2 for
Hermes and composed roots) are covered by
`test_hermes_root_preserves_existing_durable_writer_and_skips_writes_without_ingress`
and `test_composed_roots_write_nothing_without_resolved_ingress`
(`3 passed in 15.46s`). Still remaining from that review (follow-up class):
existing-record preservation and JSONL variants for the factory/filesystem
roots are blocked on those builders not exposing an ingress-resolver
passthrough, the no-runtime construction no-write assertion (TR-F4), and the
foreign-manifest defense-in-depth pin (TR-F6).

The transferred runtime-validation follow-up is closed: the
`_provider_ingestion._semantic_runtime` private bridge is replaced by the
service's stored `_composed_semantic_runtime` composition reference, and
`test_semantic_runtime_validates_exactly_once_at_first_resolved_ingress`
pins deferral (no validation or writer record at absent ingress, exactly
one validation and record at first resolved ingress, no re-validation on
later ingresses). Ratification against the governing profile/runtime
contract is recorded as accepted: both directions fail closed and the
deferral is the same authority boundary the ingress-first correction
established.

## Next Action

Record the milestone outcome in the parent index and proceed to the
performance milestone (VCC-R01): instrument the production-bound digest
counter, implement codec-level child-slice reuse, and measure the capture
matrix against the 90 percent gate.

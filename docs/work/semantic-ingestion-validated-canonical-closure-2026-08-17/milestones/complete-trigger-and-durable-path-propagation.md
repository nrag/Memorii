# Complete Trigger And Durable-Path Propagation

- Parent WorkPlan: `../implementation.plan.md`.
- Status: active remediation; reopened 2026-08-18.
- Requirements: direct prepared-source evidence for `VCC-R02` through `VCC-R10`;
  lifecycle/observability evidence for `VCC-R08` and `VCC-R11`; all-root and
  replay requirements remain partial.
- Started: `2026-08-18`.
- Completed: not complete.
- Scope: direct `sync_event` prepared-source propagation plus the private owner
  lifecycle. Composite, memory-write, Hermes, recovery, replay, and other
  durable families are deliberately outside this bounded proof.

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
| `_sync_composite_event` | `ProviderMemoryService._sync_composite_event` | arena construction only | incomplete: no family-specific stage/seal/lease consumer proof |
| `apply_memory_write` | `ProviderMemoryService.apply_memory_write` | arena construction only | incomplete: no family-specific stage/seal/lease consumer proof |
| Hermes and recovery/replay | Hermes hooks and coordinator recovery seams | none proven | incomplete: no fresh owner/lease or persisted-safe handoff proof |
| Other graph/persistence consumers | normalization/graph/persistence owners | none proven | incomplete: no exact certified-byte consumer proof |

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

## Next Action

Map one recovery or replay root with a fresh private owner and an exact durable
consumer before extending the closure to the remaining trigger families.

# Changed Surface And Ownership Ledger

- Original frozen working revision: `b9daf00a0e6956e51106756f1baaf23190c688bb`
- Current branch revision (2026-08-26): `02502eb` — the original dirty
  working set was committed as `5bd516b`, then advanced by the debugging
  closure (`5f61c9c`), the recovery redelivery-door wiring and proofs
  (`4560d29`), and the trigger-family proofs and bridge cleanup (`02502eb`).
- Total working-set entries observed at the original freeze: 38 paths.

## Surfaces Added By The 2026-08-26 Milestones

- `memorii/memorii/core/provider/ingestion.py`: the sealed lease now
  propagates from `_bootstrap_prepare_and_handoff` through
  `_run_semantic_ingestion` into the replay reload, with release on every
  exit path (recovery milestone, `4560d29`).
- `memorii/memorii/core/provider/service.py`: `_composed_semantic_runtime`
  stored composition reference replaces the coordinator private-attribute
  bridge (trigger-family milestone, `02502eb`).
- `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_coordinator_v3.py`:
  three redelivery recovery proofs and the parametrized family proof.
- `memorii/tests/unit/core/test_provider_service.py`: runtime-validation
  deferral proof; `_build_production_scoped_provider_service` gained
  optional `memory_plane`/`now_provider` fixture parameters.
- `memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py`:
  Hermes-root preservation and composed-root no-write proofs.
- `docs/work/semantic-ingestion-recovery-reconcile-baseline-debug-2026-08-18/`:
  closure record and `debug-candidate-identity-v4.json`.

## Approved-Design Production Surface (tracked at the original freeze)

These files are modified relative to the frozen base and are within the approved
implementation surface identified by the active candidate manifest:

- `memorii/memorii/core/filesystem_storage/bundle.py`
- `memorii/memorii/core/memory_evolution/atomic_store.py`
- `memorii/memorii/core/memory_evolution/ingestion_contracts.py`
- `memorii/memorii/core/memory_evolution/writer_admission.py`
- `memorii/memorii/core/memory_plane/store.py`
- `memorii/memorii/core/provider/factory.py`
- `memorii/memorii/core/provider/ingestion.py`
- `memorii/memorii/core/provider/service.py`
- `memorii/memorii/core/semantic_ingestion/bootstrap_graph_coordinator.py`
- `memorii/memorii/core/semantic_ingestion/bootstrap_graph_host.py`
- `memorii/memorii/core/semantic_ingestion/contracts.py`
- `memorii/memorii/core/semantic_ingestion/source_normalization_repository.py`
- `memorii/memorii/integrations/hermes_provider.py`
- `memorii/tests/support/memory_evolution_provider_harness.py`

## Added Production/Test Surface (tracked as uncommitted output)

These files are newly added and map directly to implementation scope for
validated canonical closure and its readiness checks:

- `memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py`
- `memorii/memorii/core/semantic_ingestion/production_authority.py`
- `memorii/memorii/core/semantic_ingestion/production_capture.py`
- `memorii/tests/fixtures/semantic_ingestion/canonical_evidence_artifact_validator.py`
- `memorii/tests/fixtures/semantic_ingestion/canonical_evidence_lock_resolver.py`
- `memorii/tests/fixtures/semantic_ingestion/canonical_evidence_performance_runner.py`
- `memorii/tests/fixtures/semantic_ingestion/canonical_evidence_preimport_gate.sh`
- `memorii/tests/fixtures/semantic_ingestion/canonical_evidence_production_matrix.py`
- `memorii/tests/unit/core/semantic_ingestion/test_canonical_evidence_arena.py`

## Design, evidence, and operational collateral (untracked)

- `docs/design/semantic_ingestion_canonical_evidence/`
- `docs/design/semantic_ingestion_canonical_evidence_performance.md`
- `docs/design/semantic_ingestion_validated_canonical_closure.md`
- `docs/evidence/`
- `docs/reviews/semantic-ingestion-canonical-evidence-performance/`
- `docs/reviews/semantic-ingestion-validated-canonical-closure/`
- `docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-15/`
- `docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-16-debug-hang.plan.md`
- `docs/work/semantic-ingestion-canonical-evidence-performance-observability-2026-08-16/`
- `docs/work/semantic-ingestion-canonical-evidence-performance-observability-review-2026-08-16/`
- `docs/work/semantic-ingestion-canonical-evidence-performance-review-2026-08-15/`
- `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/`
- `docs/work/semantic-ingestion-codec-owned-attestation-2026-08-16/`
- `docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17/`

## Ownership conclusion

- No unknown in-scope production owners were introduced in this milestone.
- Related sibling workplan folders are intentionally separated and treated as evidence collateral rather than part of the canonical readiness surface.

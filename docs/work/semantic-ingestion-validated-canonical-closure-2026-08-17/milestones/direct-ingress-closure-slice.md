# Direct Ingress Closure Slice Milestone

- Parent WorkPlan: `docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/implementation.plan.md`
- Status: complete
- Requirements: `VCC-R02` through `VCC-R09`, `VCC-R11`, `VCC-R12`; partial on `VCC-R01`
- Last updated: `2026-08-18`

## Objective

Enable canonical-evidence closure on the production direct ingress paths in
`ProviderMemoryService` while preserving default-disabled behavior in non-production
service construction.

## Milestone Scope

- Production composition in `memorii/memorii/core/provider/service.py`:
  - direct `sync_event`
  - `_sync_composite_event`
  - `apply_memory_write`
- Unit coverage in `memorii/tests/unit/core/test_provider_service.py` that proves
the canonical arena mode passed to `_provider_ingestion.ingest` is:
  - `False` for default/source-admission composition
  - `True` for production-typed bootstrap composition

## Evidence

- Added internal gating flag for arena activation based on verified production
  composition and successful bootstrap profile verification.
- Added helper construction path in unit tests to reuse deterministic scenario
  bootstrap fixtures while forcing production trust domain and verifier input.
- Added default and production path assertions for both `sync_event` and
  `apply_memory_write` arena mode handoff.

## Completion Record

- Default/source-admission composition and production profile composition now
  route direct ingress through the same `_ingest_event` and `apply_memory_write`
  call sites with explicit `CanonicalEvidenceArena.enabled` toggles.
- Unit evidence now records the exact `canonical_evidence_arena.enabled` handoff:
  `False` for default composition and `True` for production-scoped bootstrap
  composition.
- No direct-ingress-only follow-up engineering changes remain; next work begins on
  durable propagation, typed closure handoff across normalization/graph/atomic
  paths, and full acceptance rows in milestone two.

## Known Limitations

- This milestone covers direct-ingress handoff mode selection only.
- Semantic closure semantics, writer admission behavior, and production-path
  durability/performance proof are tracked under later milestones.

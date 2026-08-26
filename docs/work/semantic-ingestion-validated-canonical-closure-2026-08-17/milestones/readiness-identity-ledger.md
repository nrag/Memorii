# Readiness Identity Ledger

- Purpose: inventory of allowed production and evidence identities for milestone 1.
- Evidence scope: non-authoring, non-mutable, candidate/binding validation and ownership files.

## Production and runtime ownership identities

- Candidate-tracked production paths: `CanonicalCodecResult`, `CanonicalMemberIndex`, `ValidatedCanonicalClosure`.
- Lifetime and reservation identities: arena scope owner, reservation coordinator, and closure owner identities in the semantic-ingestion production module graph.
- Observability identities: terminal-mode/status/reason counters and sink result enums.
- Added 2026-08-26 (behavioral, no persisted/public schema change):
  - `ProviderMemoryService._composed_semantic_runtime` — stored composition
    reference replacing a coordinator private-attribute read.
  - Test identities `test_redelivery_recovery_uses_fresh_owner_and_leases_exact_prepared_bytes`,
    `test_redelivery_recovery_rejects_mutated_lease_coordinates`,
    `test_redelivery_recovery_outcomes_are_identical_across_enabled_and_disabled_modes`,
    `test_every_trigger_family_stages_seals_and_leases_prepared_bytes`,
    `test_semantic_runtime_validates_exactly_once_at_first_resolved_ingress`,
    `test_hermes_root_preserves_existing_durable_writer_and_skips_writes_without_ingress`,
    and `test_composed_roots_write_nothing_without_resolved_ingress` are
    behavioral descriptions; none carries a planning, milestone, or
    requirement coordinate.

## Evidence and artifact identities

- Readiness artifacts in this packet:
  - `source-bound-production-entrypoint-map.md`
  - `reconstruction-digest-owner-census.md`
  - `changed-surface-ownership-ledger.md`
  - `test-and-workflow-inventory.md`
  - `readiness-validation-matrix-readout.md`

## Forbidden identities for this milestone

- No planning or issue coordinates are introduced in production symbols, tests, fixtures, workflow names, or file names.
- New production and test names must remain behavioral and traceable through typed contracts and existing allowlist logic.

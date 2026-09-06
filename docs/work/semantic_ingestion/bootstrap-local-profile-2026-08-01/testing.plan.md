# Bootstrap Profile Test Migration

- Work ID: semantic_ingestion_bootstrap_profile_testing_2026_08_01
- Work type: testing
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-01
- Last updated: 2026-08-01
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/bootstrap-local-profile-2026-08-01/design.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md` at `aae9faa1d7fce59c658308114286a33250245b764b2cef3dde51ad3a47f2f785`
- Expected outputs: current-contract M1 root and compatibility tests.

## Objective

Replace retired dynamic provider behavior expectations with truthful M1 source-only
outcomes while retaining immutable public schema and independent-reader proof.

## Completion Contract

Every failed case is retained, migrated, or removed with its reason; schema,
field order, enums, defaults, nullability, validators, delivery identity, and
legacy-reader decoding remain proven; real direct/factory/Hermes/filesystem and
reconcile roots have deterministic M1 containment coverage.

## Scope

Included: test/fixture migration only. Excluded: M2 behavior and product changes.

## Current State

Baseline relevant run: 69 collected, 45 passed, 24 failed in 16.59s. Retain
schema/reader and non-semantic tests. Migrate the two R22 service-byte tests and
provider candidate/commit/trace expectations to M1 source-only outcomes; do not
delete their negative coverage. Factory/filesystem ambient-construction cases
become containment tests.

The completed migrated selection passes 98/98 in 17.71 seconds. The two historical
R22 runtime-byte cases retain the independent legacy reader and schema bytes
but no longer treat obsolete dynamic outcomes as current behavior. Provider,
factory, Hermes, and filesystem cases retain their non-semantic invariants and
now assert source-only containment where they previously required candidate,
evolution, trace, or ambient dependency behavior.

## Progress Log

- 2026-08-01: Captured the 69-case baseline at 45 pass / 24 fail in 16.59s.
- 2026-08-01: Migrated all 24 cases according to the retention map without
  skips or deletion. The exact selection passes 69/69 in 15.35s. Scoped Ruff,
  scoped Pyright for changed production owners, and `git diff --check` pass.
- 2026-08-01: Expanded the suite after independent review to cover installed
  host-capability discovery through direct/factory/Hermes/filesystem roots,
  raw CTV artifact decoding, mandatory corpus inventory, altered installed
  components, authenticated-versus-public language authority, all source-only
  containment, explicit disablement, protected lookup ordering, JSONL reopen,
  replace failure, lost acknowledgement, exact metadata-poor bytes, and
  socket/DNS denial. The complete selection passes 80/80 in 16.37 seconds;
  repository Ruff, Pyright, and `git diff --check` pass.
- 2026-08-01: Closed the final M1 evidence gaps with the complete corpus/outcome
  matrix, exact protected case IDs and input digests, canonical-envelope and
  binding mutations, unreadable-component containment, atomic host-root
  ordering, expected ingress-denial normalization, exact lost-ack record-kind
  recovery, direct-root outcome assertions, and broader socket/listener traps.
  The expanded selection passed 96/96 at that checkpoint. Repository Ruff,
  Pyright, and `git diff --check` pass.
- 2026-08-01: Added barrier-controlled simultaneous exact-delivery tests for
  both the in-memory and JSONL stores. A losing optimistic writer re-reads and
  accepts only the exact immutable source/index pair; conflicting deliveries
  still reject. The final focused selection passes 98/98 in 17.71 seconds.
- 2026-08-01: Ran the full unit inventory to expose migration debt rather than
  hide it: 2,264 passed, 136 failed, and 18 errored in 453.70 seconds. The
  failures split between tests that intentionally exercise deferred M2/M3
  provider evolution and tests bound to stale pre-bootstrap traceability
  authority. Neither class is enabled or weakened to make M1 pass.
- 2026-08-01: Completed the mergeability migration. Deferred evolution tests
  use a provider harness located only under `tests/support`; the production
  package contains no M2 composition. The runtime benchmark accepts an
  explicit provider factory, fails immediately when M2 is unavailable, and
  benchmark verification passes the test-only harness directly.
  Traceability authority is regenerated while preserving the frozen v1
  release body and CTV profile, and the final full unit gate passes 2,421 tests
  with zero failures in 1,498.59 seconds. Two process-concurrency
  cases skip only because this sandbox denies semaphore discovery; their real
  multi-process assertions remain active on capable hosts. The final authority
  suites pass 277/277; Ruff, repository-scoped Pyright, and `git diff --check`
  pass.

## Evidence Log

- Command: `python -W error -m pytest` over bootstrap admission, provider
  compatibility, provider service, provider factory, and filesystem storage
  bundle tests with `-p no:cacheprovider -q` from `memorii/`.
- Result: 98 passed in 17.71s.
- Static result: scoped Ruff passed; scoped Pyright reported zero errors;
  `git diff --check` passed.

## Retention Map

| Family | Disposition | Failure signal |
| --- | --- | --- |
| Schema/field/order/enum/default/validator/legacy reader | retain | wire compatibility regression |
| Delivery/replay/cross-principal | retain | identity or protected-index regression |
| Dynamic candidate/evolution/trace bytes | migrate | M2 behavior starts in M1 |
| Factory/filesystem ambient construction | migrate | ambient dependency constructed before M1 boundary |
| Direct/Hermes/reconcile roots | migrate | source-only outcome or zero-effect containment missing |

## Case Retention Ledger

| Present owner / cases | Disposition | Distinct failure signal | Gate |
| --- | --- | --- | --- |
| `test_provider_compatibility.py` schema, field-order, enum, default, validator, and reader cases | retained | public bytes or legacy reader changes | focused M1 gate |
| `test_bootstrap_source_admission.py` delivery exactness, replay, cross-principal, scope, and protected lookup cases | retained and expanded | identity collision, disclosure, or unauthorized outcome read | focused M1 gate |
| Complete nine-row bootstrap corpus plus unlisted/foreign-language inputs | added | wrong kind, reason, case ID, or normalized digest | focused M1 gate |
| Disabled, unavailable, unsupported, abstained, and selected-pipeline-pending outcomes | migrated/added | missing five-record evidence or any semantic candidate/graph effect | focused M1 gate |
| Direct, factory, Hermes, filesystem, session-end, and pre-compress roots | migrated/added | missing installed discovery, lossy source bytes, or non-source-only result | focused M1 gate |
| Canonical envelope, binding, artifact digest, component inventory/content/readability, anchor, and corpus cases | added | substituted authority accepted or construction crash | focused M1 gate |
| JSONL reopen, replace failure, lost acknowledgement, and idempotent retry | retained and expanded | visibility other than zero or the exact five-record generation | focused M1 gate |
| Network construction/ingestion traps | added | DNS, connect, bind, or listen call | focused M1 gate |
| `tests/unit/core/benchmark/test_memory_evolution_*`, `test_memory_evolution_orchestration.py`, and related evolution-provider suites | retained behind an explicit non-production harness | M2 behavior becomes reachable from an M1 production root | full unit gate |
| `tests/unit/tools/test_generation_closure_exactness.py`, `test_semantic_ingestion_ctv_reference_compiler.py`, structural/fixture authority suites | retained and regenerated | current design/registry/authority or frozen v1 compatibility drifts | full unit and authority gates |

## Next Action

None. The testing WorkPlan completion contract is satisfied.

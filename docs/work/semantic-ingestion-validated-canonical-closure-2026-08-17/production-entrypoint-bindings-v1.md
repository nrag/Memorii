# Validated Canonical Closure Production Bindings

This file is a normative component of the frozen design candidate. It binds the
new design contracts to current production owners without claiming that the new
symbols already exist.

## Symbol status

| Design symbol | Status at design freeze | Existing owner it evolves or composes |
| --- | --- | --- |
| `CanonicalCodecResult[T]` | New typed result required by the design | `memorii/memorii/core/semantic_ingestion/contracts.py::encode_semantic_contract`, `decode_semantic_contract`; `memorii/memorii/core/memory_evolution/ingestion_contracts.py::_normalized_typed_json`, `encode_typed_value`, `decode_typed_value` |
| `ValidatedCanonicalClosure` | New operation-scoped closure and compact exact-path index required by the design | `memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py::ValidatedCanonicalEvidenceResult` and its arena ownership model |
| `ValidatedCanonicalBinding` | New immutable binding from root identity and traversal-issued member path to exact canonical span and digest | The canonical traversal sites in the two codec owner modules above |

`CanonicalCodecResult[T]` is not an alias for
`ValidatedCanonicalEvidenceResult[T]`. The former carries the complete typed
value, canonical root bytes, root digest, and traversal-issued exact-path
bindings needed by this design. The latter is the current bounded evidence
result and remains the disabled-path implementation until the new path is
enabled.

## Production entrypoint bindings

| Boundary | Existing production trigger and composition owner | Authority-bearing callsite | New handoff | Durable or observable outcome |
| --- | --- | --- | --- | --- |
| Provider ingress | `memorii/memorii/core/provider/service.py::ProviderMemoryService.sync_event` and `memorii/memorii/core/provider/ingestion.py::ProviderIngestion.ingest` | `ProviderIngestion._run_semantic_ingestion`, reached through `_admit_with_writer_retry` and `_bootstrap_prepare_and_handoff` | One operation-scoped `ValidatedCanonicalClosure` is created after admission and passed only through typed in-process arguments | Existing accepted, rejected, retried, and persisted outcomes remain unchanged |
| Semantic-contract codec | `memorii/memorii/core/semantic_ingestion/contracts.py` | `encode_semantic_contract(value)` and `decode_semantic_contract(...)` | Codec returns `CanonicalCodecResult[T]`; only its canonical traversal may issue member paths and spans | Persisted bytes and decoded typed values remain byte-for-byte and semantically unchanged |
| Typed memory-evolution codec | `memorii/memorii/core/memory_evolution/ingestion_contracts.py` | `_normalized_typed_json(...)`, `encode_typed_value(...)`, and `decode_typed_value(...)` | Codec returns or contributes the same typed closure data under its existing profile authority | Existing profile, envelope, and typed-value validation remain unchanged |
| Source-normalization construction | `memorii/memorii/core/semantic_ingestion/source_normalization_stage.py` and `source_normalization_execution.py::normalize_after_recovery_claim` | Existing generation-member construction and recovery-claim execution | Consumers request exact bindings by root identity plus traversal-issued member path; post-hoc byte search is forbidden | Existing recovery keys, joins, renewals, and normalization results remain unchanged |
| Bootstrap graph execution | `memorii/memorii/core/semantic_ingestion/bootstrap_graph_host.py::BootstrapGraphHostBundle.execute` and `bootstrap_graph_builtin.py::build_builtin_bootstrap_graph_execution_v3` | Existing `BootstrapGraphAuthorityRequestV3` execution path | Closure is a non-authoritative typed input; authority and security decisions remain with the host bundle and validators | Existing graph transaction authority and terminal intent remain unchanged |
| Atomic publication and replay | `memorii/memorii/core/memory_evolution/atomic_store.py` | `publish_prepared_source`, `publish_bootstrap_prepared_source_if_absent`, `bootstrap_writer_handoff`, `publish_or_reload_bootstrap_graph_transaction_authority_v3`, `publish_or_reload_bootstrap_canonical_identity_authority_v3`, and terminal persistence methods | A binding may replace only redundant canonical reconstruction and digest work after exact identity, profile, and provenance checks | Persisted schemas, replay bytes, conflict behavior, idempotency, and writer admission remain unchanged |
| Terminal persistence | `memorii/memorii/core/semantic_ingestion/persistence.py::SemanticTerminalPersistenceService.persist` | Existing precommit, authorization, and terminal persistence sequence | Closure-derived digests are accepted only where the existing owner would compute the same digest from the same canonical bytes | Durable terminal state and failure behavior remain unchanged |

## Enabled, disabled, and fallback precedence

1. The feature is disabled by default during implementation and rollout. The
   current codec, arena, reconstruction, digest, validation, and persistence
   path remains authoritative.
2. When enabled, codec traversal creates the closure. A consumer substitutes a
   binding only after exact root identity, canonical profile, contract kind,
   traversal path, provenance, and operation-scope checks succeed.
3. A miss, ambiguity, capacity refusal, provenance mismatch, profile mismatch,
   unknown kind, stale operation, or lifecycle mismatch fails closed to the
   current full reconstruction-and-digest path. It never returns a
   success-shaped cache result.
4. Semantic validators, authorization, writer admission, lifecycle policy,
   transaction boundaries, persistence, and replay always execute. The design
   skips only duplicate canonical reconstruction and digest computation.
5. Rollback disables closure creation and substitution together. No persisted
   migration or replay conversion is required.

## Operation capability and lifecycle ownership

`ProviderMemoryService` owns one private `CanonicalClosureScopeOwner`. Before
staging it atomically reserves the complete 16 MiB envelope through the
repository-owned `CanonicalClosureReservationCoordinator`. Staged entries are
not visible; refusal clears all entries, releases, and selects immutable full-
path mode before substitution.

Only semantic validation may seal and receive issuer identity. Explicit typed
arguments carry the sealed closure; ambient context is not authority. Lookup
matches issuer plus tenant, operation, generation, fence, and writer and returns
a bounded lease. Close rejects new leases and releases exactly once after the
last lease drains. Disabled mode creates no owner, capability, or reservation.

The complete transitions and unsupported forms are frozen in
`canonical-closure-operation-contract-v1.json`. Ordinary construction, stale or
foreign scope, admission after seal, lookup before seal, fallback after first
lookup, double release, and underflow fail closed.

## Capacity migration contract

The current `canonical_evidence_arena.py` constants
`MAX_ARENA_CHARGED_BYTES = 1_048_576` and
`MAX_PROCESS_RESERVED_BYTES = 67_108_864` describe the existing arena, not the
new compact closure index. Implementation must not silently reinterpret the
1 MiB arena as the new operation envelope.

The enabled design introduces the independently measured compact limits:

| Limit | Frozen value |
| --- | ---: |
| Canonical roots per operation | 512 |
| Canonical bytes per root | 2 MiB |
| Traversal-issued paths per operation | 32,768 |
| Total charged bytes per operation | 16 MiB |
| Process reservations | 64 MiB |

The 64 MiB process reservation is shared across concurrent closures. Admission
must reserve before allocation and release on every terminal path. Exceeding an
operation or process limit refuses closure insertion or creation and uses the
full validation path; it cannot weaken validation or expand persisted state.

The reservation unit is exactly 16 MiB and is acquired before closure
allocation, allowing at most four simultaneous enabled operations. Root, path,
and byte accounting occurs only while staging; any over-limit result rejects
the entire staged closure. Seal makes the index immutable.

## Content-free observability ownership

`ProviderMemoryService` injects the repository-owned
`CanonicalClosureObservabilityDispatcher`. One terminal snapshot is attempted
for disabled, rejected, completed, validation-failed, exception, and cancelled
operations. Exact fields and forbidden content are frozen in the operation
contract. The sink returns `recorded` or `unavailable`; unavailability cannot
change validation, retry, persistence, replay, or public outcomes.

## Preflight finding reconciliation

| Finding | Product priority | Approval disposition | Finding type | Coordinator classification | Resolution |
| --- | --- | --- | --- | --- | --- |
| Proposed symbols were not bound to existing owners | Not applicable | changes_required | architecture | confirmed | Closed by the symbol-status and production-binding tables in this file |
| Proposed symbols do not already exist in production | Not applicable | follow_up | governance | unsupported | A design necessarily names not-yet-implemented symbols; status is now explicit |
| Current 1 MiB arena and proposed 16 MiB operation envelope conflict | Not applicable | follow_up | architecture | unsupported | They are distinct current and target contracts; migration and rollback behavior are now explicit |
| V3, disabled, and fallback precedence was not fully explicit | Not applicable | changes_required | compatibility | confirmed | Closed by the precedence contract in this file |
| Exact fan-in counts were not enumerated for every internal method | Not applicable | follow_up | verification | accepted limitation | Implementation readiness requires the named authoritative surfaces; caller census remains an implementation verification obligation |

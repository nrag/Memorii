# Observer Contract Map (Production Boundary Only)

## Status
- `memory_evolution/graph_observation.py` does not exist.
- No production adapter calls `GraphObservationAuthorizer`, `GraphObservationRequest`, or `GraphObservationPage`.
- `CanonicalIngestionObservationRecord` is only a type alias: `CanonicalSourceTerminalOutcomeRecord` in `memorii/memorii/core/memory_evolution/graph_effect_contracts.py` (no separate source-introduction/operation-introduction family).
- Graph-observation paging/error surfaces remain design-only in `docs/design/semantic_ingestion_architecture.md`.

## production_entrypoint_bindings

| requirement/behavior | production trigger | composition root | authority-bearing callsite + exact arg | validation | durable outcome | production caller count | fallback/bypass | evidence path |
|---|---|---|---|---|---|---|---|---|
| Resolve accepted source + operation fence + typed terminal result | `lookup_semantic_ingestion_outcome(...)` | `memorii/memorii/core/provider/service.py` + `memorii/memorii/integrations/hermes_provider.py` | `ProviderMemoryService.lookup_semantic_ingestion_outcome(request, authenticated_host_ingress)` → `_resolve_ingress()` → `_semantic_ingestion_admission.lookup(request, authenticated_ingress=ingress)` | Non-disclosing admission-index gate (principal/scopes/tenant), canonical index decode, manifest terminal/lifecycle decode, terminal-hash match | `SemanticIngestionOutcomeLookupResponse(available=True, outcome=BootstrapProfileOutcome)` where committed outcome can be `ProfileCommittedTerminal(terminal_result_digest=...)` | 1 public adapter call site (`hermes_provider.py`) | missing checks return empty `SemanticIngestionOutcomeLookupResponse()` | `memorii/memorii/core/provider/service.py:803-815`; `memorii/memorii/integrations/hermes_provider.py:217-225`; `memorii/memorii/core/memory_evolution/admission.py:312-437` |
| Read identity lineage audit (not graph observation) | `read_identity_lineage(...)` | `memorii/memorii/core/provider/factory.py` + `memorii/memorii/core/provider/service.py` | `ProviderMemoryService.read_identity_lineage(request, authenticated_host_ingress)` → `GrantBackedIdentityLineageAuditAuthorizer.authorize_identity_lineage_audit(...)` (2-phase) → `AtomicStoreScopedIdentityLineageAuditReader.read_identity_lineage(...)` | Final scope contract checks: tenant, principal digest, scope-mode/ids, revalidated snapshot timing, `require_current` | `IdentityLineageAuditView` | 1 public adapter call site (`hermes_provider.py`) | denied scope raises `ValueError("identity_lineage_audit_denied")` | `memorii/memorii/core/provider/factory.py:84-129`; `memorii/memorii/core/provider/service.py:846-899`; `memorii/memorii/core/memory_evolution/identity_lineage.py:129-193`; `memorii/memorii/core/memory_evolution/identity_lineage.py:274-305` |
| Reload terminal closure by authenticated recovery (fence-aware) | `reload_terminal(...)` in bootstrap recovery | `memorii/memorii/core/semantic_ingestion/bootstrap_graph_host.py` | `BootstrapGraphHostBundle.reload_terminal(normalization_replay=..., required_outcome_scopes=..., operation_fence_binding=...)` → `SemanticIngestionAtomicStore.reload_bootstrap_graph_terminal_by_recovery_v3(...)` | Replay key/principal digest/required-scope digest/operation-fence binding equality, locator/member/control/member-manifest identity and digest closure checks | `BootstrapGraphTerminalReloadV3` with `canonical_source_result: CanonicalSourceTerminalOutcomeRecord` | host/internal recovery path only | recover miss => `None`; malformed closure => `PreplanningStoreError` | `memorii/memorii/core/semantic_ingestion/bootstrap_graph_host.py:95-113`; `memorii/memorii/core/memory_evolution/atomic_store.py:10652-11134` |
| Internal generation read (source-finalization/group reconstruction path only) | runtime/fixture reads, admission/lease verification paths | `memorii/memorii/core/memory_evolution/atomic_store.py` | `generation_members(operation_fence, generation)` → `_read_generation_members` | Fenced control lookup; manifest/member IDs, kinds, digests, and replay/ledger consistency checks | `tuple[AtomicGenerationMember, ...]` for one operation/fence generation only | internal/runtime callers; no production surface contract | not publicly authorized and can be called only with a retained operation fence object | `memorii/memorii/core/memory_evolution/atomic_store.py:2277-2296`; `memorii/memorii/core/memory_evolution/atomic_store.py:2320-2365` |

## Concrete type-to-persistence mapping (verified)
- `CanonicalSourceTerminalOutcomeRecord` in `graph_effect_contracts.py` fields already hold canonical terminal output keys: `source_id`, `source_digest`, `delivery_principal_binding_digest`, `delivery_key_digest`, `required_outcome_scopes`, `operation_fence_id`, `operation_ids`, `final_status`, `group_result_digests`, `source_result_digest`, `record_digest`.
- `BootstrapGraphCanonicalSourceResultV3` stores `canonical_source_result: CanonicalSourceTerminalOutcomeRecord` and validates `ordered_group_result_digests == canonical_source_result.group_result_digests`.
- `BootstrapGraphTerminalReloadV3` stores `canonical_source_result`, `required_scope_set_digest`, and terminal-control completion coordinates.
- Terminal-group persistence uses `SemanticObservationDelta` in `AtomicGenerationMember.kind == "observation_delta"`; `_validate_terminal_group_closure` enforces:
  - `group_result`, `artifact_closure`, `artifact_index`, `observation_delta` required.
  - Committed paths require `graph_delta` + `event_batch`.
  - Non-committing paths require `SemanticObservationDelta` terminal-derived without `graph_delta`/`event_batch`.
- `persist_terminal_group` and `finalize_source` constraints remain active; no schema mutation inferred:
  - `persist_terminal_group`: required member set for committed vs noncommitting group members.
  - `finalize_source`: required `{terminal_operation, source_summary, source_result, observation_delta, lifecycle}`.

## Native group-vs-source-record distinction
- `GraphEffectCodec` supports `GraphRevisionDelta | CanonicalSourceTerminalOutcomeRecord | IngestionObservationDelta` but production native path does **not** currently expose an explicit public `source_introduction`/`operation_introduction` reader.
- `SemanticIngestionAtomicStore` currently reads/returns terminal closure and generation members; it does not provide a production API that starts from `seed_source_ids`/`seed_operation_ids` and returns a `GraphObservationPage`.
- `BootstrapGraphObservationDeltaEffectV3` existence is a wrapped/typed CAS artifact family and does not prove public graph-observation paging behavior by itself.

## Exact missing bounded query interface (narrow, additive)
- Missing production methods: `seed_source_ids/seed_operation_ids` expansion, authoritative cohort expansion, and paged cursor return shape.
- Missing query methods to implement (exactly scoped):
  1. `resolve_graph_observation_cohort(...):` map source/operation seeds + authorized scope to canonical terminal outcomes + terminal-group deltas.
  2. `read_graph_observation_page(...):` apply strict cursor/version checks, scope digest/version checks, and return typed observation page envelope.
- Coordinator correction: these query additions are necessary but insufficient.
  The native source/operation introduction and operation-terminal record variants
  are absent from the implemented observation algebra, and the persisted
  `SemanticObservationDelta`/bootstrap CTV summaries are not native
  `IngestionObservationDelta` payloads. Implement the already specified native
  observation record/persistence path before claiming complete cohort reads.
  Preserve old summary identities and reject unavailable historical evidence;
  do not relabel summary bytes or fabricate missing native records.
  See `observer-readiness.md` for the coordinator-validated exact source trace.

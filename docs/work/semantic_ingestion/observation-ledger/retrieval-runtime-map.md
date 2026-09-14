# Authenticated Retrieval Runtime Map

Scope: implementation ownership map for the approved authenticated retrieval
slice. This does not approve the parent observation-ledger milestone.

## Public boundary and trusted authority

`ProviderMemoryService` is the production public boundary
(`memorii/core/provider/service.py:239-631`). It already owns the shared
`MemoryPlaneService` and composes `AuthorizedSemanticIngestionRuntime` and its
`SemanticIngestionAtomicStore` at lines 466-596. The factory route is
`build_provider_memory_service_from_env` (`memorii/core/provider/factory.py:34-112`).
Both direct and factory composition must receive the new retrieval owner through
this boundary; `MemoryEvolutionRetrievalRuntime`/provider prefetch is a separate
ordinary retrieval route and is not an observation read.

The request roots are the registered-profile-3 classes in
`memorii/core/memory_evolution/graph_observation_public_contracts.py`:

* `AuthenticatedGraphObservationContext` (55-60): principal, tenant,
  authorized-scope-set digest, session, and self digest.
* `GraphObservationAuthorizationDecision` (63-75): authorized scope identity,
  policy/page-policy revisions and digest, expiry, and self digest.
* `GraphObservationPagePolicySnapshot` (78-90): page bounds, cursor schema
  version, maximum snapshot age, and self digest.
* `GraphObservationRequest` / `IngestionTimeAttestationRequest` (93-124):
  client coordinates plus opaque `cursor` only.

The existing authority concepts are reusable only as concepts:
`GraphObservationContextResolver`, `GraphObservationCurrentPolicyProvider`, and
`GrantBackedGraphObservationAuthorizer` (`graph_observation_authority.py:25-109`)
resolve trusted ingress, authorize before storage/seed access, and produce the
needed decision. They construct historical v1 models, however. The retrieval
owner must construct the registered public roots through the protected typed-value
reader and profile-3 self-digest rules, rather than importing those v1 values or
digest constructors.

Current `ProviderMemoryService.__init__` accepts
`authenticated_ingress_resolver` and `VerifiedProductionHostAuthority`, but no
graph-observation context resolver, current-policy provider, protected page
policy, or retrieval runtime (`service.py:259-288`). The factory mirrors that
absence. Add these as trusted composition inputs (or a single host-owned
retrieval runtime bundle) at the provider/factory root. Do not accept context,
decision, policy, signing key, registry, or expected digest from a page caller.

## Snapshot and projection access

The required first-store read is `MemoryPlaneService.read_write_snapshot()`
(`memorii/core/memory_plane/service.py:170-173`), returning the full write
revision and detached records. It is protected by the same lock as conditional
writes: `conditionally_write_records(... expected_write_revision=...)`
(188-214); both in-memory and JSONL backends expose that revision
(`memory_plane/store.py:304-358`, `517-574`). Construct all typed indices,
including ledger head/entries, replay, graph, reference and projection records,
only from this one record tuple.

`SemanticIngestionAtomicStore.graph_state_snapshot()` (8324-8408) and
`reference_integrity_snapshot()` (8430-8458) are live multi-read accessors and
cannot assemble the required cohort after the detached read. Use their exact
decode/validation logic against a snapshot-backed record reader, with no live
fallback.

Projection authority remains `ProjectionHistoryRepository`: current selectors
are `current_temporal`/`current_trust` (`projection_history.py:3969-4018`),
history/replay binding validation is at 4173-4205, and `_load_kind` validates
the complete pointer/generation/certificate closure (4661-4735). Those methods
currently use their bound live reader and current replay revision. Retrieval
needs a detached-reader instance (or equivalent extracted read path) populated
from the full snapshot, preserving separate temporal and trust histories. The
native group writer's publication integration remains a prerequisite for any
projection coordinates advertised in a cohort.

## Cursor owner

Profile-3 cursor body is
`graph_observation_snapshot_contracts.GraphObservationCursorPayload`
(121-158): it binds position/predecessor, policy, context/decision, expiry,
cohort, unguessable snapshot token, snapshot write revision, both revisions,
view/time coordinates, and signature. The snapshot roots bind the same context,
decision, cursor-free request, cohort and immutable ordered stream
(`graph_observation_public_contracts.py:154-225`).

`graph_observation_cursor.py` is historical v1: it imports v1 contracts and
issues `v1.<base64 CTV>` under its own signing wire/domain (13-110). It is not a
registered-profile-3 cursor codec and must not be wired into retrieval. The
new signature/strict artifact decode owner belongs with the protected registered
typed-value reader configured by the semantic runtime; issue and decode raw
UTF-8 text of that complete existing artifact envelope, using fixed purpose
`graph_observation_cursor` and domain `memorii.graph-observation.cursor.v3`.
Authorize first; then decode, look up token, re-read a full write snapshot,
and compare the cursor/snapshot write revision before returning a contiguous
page.

## Concrete caller gaps at mapping baseline

There is no `ProviderMemoryService` graph-observation or ingestion-time
attestation method, no composed profile-3 authorization/policy runtime, no
snapshot-retention/token store, no detached projection-history reader, and no
registered cursor issue/decode callsite. These are determinate retrieval
implementation work. Existing schema classes, the legacy authorizer/cursor,
and `graph_state_snapshot()` do not constitute reachable production retrieval.

## 2026-09-08 bounded paging-owner construction

`memorii/core/memory_evolution/graph_observation_paging.py` now defines the
canonical Profile-3 paging owner, trusted context/policy/authorization and
detached-cohort protocols, and in-memory unguessable-token retention. It
authorizes before cursor decode, token lookup, or memory-plane read; snapshots
one detached full-write inventory only after authorization; reauthorizes every
continuation; and compares request, policy, context, expiry, cursor predecessor,
and full write revision before emitting a contiguous page. It uses the
registered artifact emitter for cohort, snapshot, and page roots and the
registered cursor issuer/decoder for cursor envelopes. There is intentionally no
default cohort provider or live-read fallback.

Root added the graph authority, policy, cohort, snapshot and page registered
roots to `observation_activation_runtime.py`. A real registered construction
test passes two-page continuity, reauthorization, scope substitution rejection
and intervening-write invalidation using a fixture cohort provider. The
provider/factory root still has no trusted construction or public caller, and
the concrete detached cohort/projection backend remains pending. This module
therefore has no production entrypoint binding yet.

There is a public-contract blocker for ingestion-time continuation: the cursor
requires graph-record `preceding_record_kind` plus `view`, `valid_at`, and
`system_as_of`, but `IngestionTimeAttestationRequestCoordinates` has none of
those coordinates and its two stream variants have no graph-record kind. A
bridge would invent public semantics. The paging owner therefore rejects that
bridge rather than minting a nonconforming continuation; the public cursor or
attestation request contract needs an explicit design correction.

The narrow proposed correction is a separately registered ingestion-time cursor
whose preceding discriminator is the existing attestation `kind` and whose
request coordinates match the ingestion-time API. It would retain the same
authorization, decision, policy, snapshot/write-revision and predecessor-digest
fences, use its own signature domain, and leave the graph cursor byte contract
unchanged. This is a proposal only: the new schema, domain and registry identity
must be fixed in a separate design operation before implementation.

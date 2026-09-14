# Registered Ingestion-Time Attestation Continuation

Status: proposed canonical amendment; no production implementation claimed.
Canonical targets: docs/design/semantic_ingestion_observation.md, Locator And
Cursor Closure and Replay Snapshot Contract, plus an explicit endpoint-dispatch
cross-reference at SIA's ingestion-time paging paragraph and "Every page request
reauthorizes" cursor paragraph (baseline lines31873 and31969). Higher-priority scope, event and
memory-domain requirements are unchanged. This amendment resolves only the
known unrepresentable ingestion-time continuation, not cohort completeness.

## Requirement And Decision

Existing IngestionTimeAttestationRequestCoordinates has scope_constraint,
cohort_selector, expected_graph_revision, expected_observation_revision and
total_page_size. Its stream consists of SourceRetentionTimeAttestation and
TransactionGroupCommitTimeAttestation. GraphObservationCursorPayload instead
requires graph-kind/view/valid_at/system_as_of coordinates. Inventing those
coordinates or treating attestation kinds as graph kinds is prohibited.

Select a separate registered IngestionTimeAttestationCursorPayload.v1 root.
Alternative: add a purpose-discriminated union to the graph cursor. Rejected:
that changes an existing signed shape and complicates historical byte handling
without improving either endpoint. The two cursors share envelope/verification
machinery and retention rules, not a permissive mixed payload.

## Complete New Root

All fields are required, including explicit nullable predecessors. Frozen strict
model, extra fields forbidden, bool rejected for every integer/literal integer.
Identifier and Digest use the existing observation aliases; UTC uses the existing
zero-offset aware timestamp contract. No coercive model-copy result bypasses
validation at issuance or decoding.

| Field | Exact type/constraint |
| --- | --- |
| schema_version | integer literal1 |
| stream_position | integer>=0 |
| preceding_attestation_kind | source_retention or transaction_group_commit, or null |
| preceding_attestation_id | Identifier or null |
| preceding_attestation_digest | Digest or null |
| request | complete existing IngestionTimeAttestationRequestCoordinates |
| page_policy_revision | Identifier |
| page_policy_digest | Digest |
| caller_context_digest | Digest |
| authorization_decision_digest | Digest |
| authorization_expires_at | aware UTC datetime |
| cohort_digest | Digest |
| snapshot_token | Identifier |
| snapshot_write_revision | integer>=0 |
| signature | exactly128 lowercase hexadecimal characters |

At position0 all three predecessor fields are null. At positive position all
are non-null. The cursor does not add view or graph-record fields. It signs the
complete cursor-free request rather than constructing a second request digest
or copying only some coordinates. The request's two expected revisions are the
cursor's graph/observation revision coordinates; no second duplicated field set
exists. Existing shared page-policy cursor_schema_version=1 applies to this
root's version1; endpoint purpose selects the root, never that integer alone.

The predecessor triple is exactly (kind, attestation_id, attestation_digest) of
stream[position-1]. The stream remains sorted uniquely by the existing
_attestation_order_key: source retention uses(kind,source_id,operation_fence_id,
empty-string,attestation_id); group commit uses(kind,source_id,operation_fence_id,
transaction_group_id,attestation_id). The triple binds the actual retained item
at an exact position; it does not replace the canonical ordering key. An unknown
kind, duplicate ordering key, out-of-order stream or wrong digest fails.

## Signing And Wire Authority

Root name: IngestionTimeAttestationCursorPayload.v1.
Schema ID: IngestionTimeAttestationCursorPayload. Schema version:1.
Decoder ID: memorii.semantic_ingestion.observation.IngestionTimeAttestationCursorPayload.v1.
Signature-only policy, field signature, purpose ingestion_time_attestation_cursor,
domain memorii.ingestion-time-attestation.cursor.v3.
The preimage is the existing registered_signature_only_message over the complete
typed body excluding only signature, including its complete selected registry
binding and fixed purpose. No bespoke JSON signing or digest algorithm is added.
The wire is the existing raw UTF-8 registered artifact envelope, not a prefixed
base64 wrapper. No self-digest or ordinary-policy route may issue this root.

Host-held selected publication/history, reader limits and verification key are
required. Endpoint decoding requires this exact selected binding, exact model,
and cryptographic_signature_checked. A graph cursor, legacy v1 cursor, cursor
under another selected publication, signature purpose/domain or key rejects.
The public caller cannot select a registry, key, policy or authorization context.
Key provisioning uses the existing trusted configuration boundary; this design
does not grant arbitrary key material authority or define acceptance witnesses.

## Public Flow And Failure Contract

ProviderMemoryService.observe_ingestion_time_attestations forwards trusted ingress
and the typed request to its host-composed AuthenticatedGraphObservationPagingRuntime.
The factory composes the same runtime/registry as direct initialization. The
runtime gains observe_ingestion_time_attestations, backed by the existing
DetachedGraphObservationCohortProvider.ingestion_time_input on one detached
read_write_snapshot result. It must be backed by the real validated ledger,
graph/reference/projection cohort owner in the implementation campaign; the
protocol or feasibility model alone is not a production binding.

For every call resolve context/current policy and authorize before decoding any
cursor, looking up tokens/seeds or reading memory. The authorization purpose is
ingestion_time_attestation. The production composition must explicitly supply
that purpose to its trusted authorizer (the present graph-only protocol omits
it and must be made purpose-aware for both endpoints). Invalid/missing ingress
or denied scope yields denied on first page and revoked_access on continuation,
without a storage read.
The requested page size must satisfy the current protected page policy.

First page: read one full snapshot; validate complete native authority and scope;
build and verify existing IngestionTimeObservationSnapshot; retain with a fresh
token and deadline=min(decision expiry,created_at+maximum age). Emit the first
contiguous slice. Empty/final page has next_cursor=null. A nonfinal page emits
the new cursor at the end position, binding its final item's predecessor triple.

Continuation: authorize, then verify the new registered cursor. Cryptographic,
shape, resource or binding failure yields invalid_cursor. Compare complete
request, context digest, exact current decision including expiry, page-policy
revision/digest and unexpired time. Under the retention lock load only the
ingestion-time token space; missing/expired/evicted state yields stale_cursor.
Require retained purpose, request, context/decision, cohort, write revision and
predecessor triple to match; require0<position<len(stream) for issued continuation.
Read a fresh full write revision and require equality with cursor and retained
snapshot. Any intervening batch makes it stale, even if graph revision is equal.
Return the next contiguous slice, never regenerate a stream under an old token.
Recheck protected time/authorization expiry immediately before response issuance;
an expiry during validation yields revoked_access for continuation (denied for
first-page issuance). No response contains a partial page on failure.

Existing failure enums and payload-free correlation behavior remain unchanged.
Authorized first-page stale requested revisions/cohort/reference failures keep
their existing canonical mappings; this amendment does not collapse them into
invalid_cursor. Unavailable trusted runtime is fail-closed, never a direct-store
or legacy read fallback. Restart/eviction invalidates retained tokens normally.

### Explicit Supersession And Failure Dispatch

For profile3 only, SIA's shared GraphObservationCursorPayload requirement and
the supplement's retained SIA cursor field inventory are replaced for the
ingestion-time endpoint by the new IngestionTimeAttestationCursorPayload above.
observe_graph continues to use the unchanged GraphObservationCursorPayload.
SIA's graph view/time constancy applies only to graph observation; ingestion-time
pages instead keep their complete IngestionTimeAttestationRequestCoordinates
constant. Both retain the same ordered-stream and authorization guarantees.
Historical profile2 and graph cursor signatures/bytes are unchanged.

This explicit table preserves SIA's canonical non-disclosing failure meanings:

| Condition in evaluation order | First page | Continuation |
| --- | --- | --- |
| Missing/invalid ingress, authorizer/policy outage, denied or revoked/expired current authorization | denied | revoked_access |
| Requested page size outside current protected policy | denied | denied |
| Invalid cursor envelope/signature/binding/schema/position/predecessor or complete request/context mismatch | not applicable | invalid_cursor |
| Changed graph/observation/write revision, page-policy revision/digest, expired/evicted/lost retained snapshot | denied for unresolvable requested cohort | stale_cursor |
| Different decision digest with unchanged policy and no denial/expiry | not applicable | invalid_cursor |
| Current authorization expires during validation/issuance | denied | revoked_access |
| Initial snapshot exceeds protected retention/stream capacity | denied | not applicable |

Authorization always runs before cursor parsing or lookup. After cryptographic
validation, changed page-policy/revision is classified stale before comparing
other retained coordinates; complete request mismatch is invalid_cursor when
current policy/revisions remain unchanged. An unknown token is stale, with no
existence disclosure beyond this standard opaque-token outcome. Expiry of
retention alone is stale; expiry of current authorization is revoked_access.
Implementation must correct the existing graph helper's conflated stale/denied
branches when wiring both endpoints; that changes failure conformance, not wire.

### Bounded Shared Retention Owner

Both endpoints use one host-protected retention budget with required positive
integer (never bool) fields: maximum_stream_records, maximum_snapshot_bytes,
maximum_retained_snapshots, maximum_retained_bytes, maximum_tenant_snapshots,
maximum_tenant_bytes. No default, request-selected value or runtime traffic
changes these limits. Tenant identity comes from authenticated context; changing
session/context cannot escape the tenant quota. Global ceilings bound tenants
collectively. Snapshot byte charge is its complete registered UTF-8 envelope
length; record/count caps also bound Python object overhead independently.

Before cohort construction reserve one token and maximum_snapshot_bytes against
both tenant and global capacity under the shared retention lock. Reject if any
ceiling would be exceeded; do not evict another tenant's or an existing same-
tenant live token. Enforce stream-record and serialized-byte ceilings during
construction using bounded builders/registered encoding, before retaining the
stream. Atomically replace the reservation charge with actual envelope bytes
when publishing the snapshot; the actual charge cannot exceed the reservation.
Release on failure, expired authorization, final/empty first page, and expiry or
explicit eviction of retained state. A restarted owner starts empty; old tokens
are stale. An in-flight reservation remains charged until its owner publishes
or releases it; ordinary expired-token cleanup cannot reclaim it early.
Concurrent issuance uses the same lock for reservation, publication and release.
Expired retained snapshots are reclaimed before evaluating capacity. No new
quota-driven eviction behavior is introduced, so exhausting a quota cannot
invalidate another live token. Existing authorized explicit eviction remains
stale_cursor. Retention is bounded even when no subsequent request arrives.

Implementation proof must cover per-tenant/global count and byte ceilings,
one-over stream/body ceilings, expiry reclamation, failed construction,
in-flight reservations and concurrent first-page reservation. This closes the
shared graph/ingestion retention family without modifying graph cursor bytes.

## Promotion, Compatibility And Gates

Production schema owner: graph_observation_snapshot_contracts.py. Move shared
request-coordinate ownership only if needed to prevent a circular import;
prefer placing the new cursor in graph_observation_public_contracts.py where
IngestionTimeAttestationRequestCoordinates is already available. Canonical final
owner is graph_observation_public_contracts.py; no relocation of existing roots.
Register the static decoder there, add the root to observation_activation_runtime
and its closed signature route, and add explicit issue/decode functions for this
cursor. The graph route remains exact-type checked and byte-identical under its
existing selected publication. New publication bytes naturally differ; do not
claim graph envelopes from different publications are byte-identical.

Author seven per-root roles (schema,enum,optional,numeric,digest-signature,upcast,
decoder), regenerate selected-source/publication/registry manifests, update the
root inventory, independently generated normalized vectors and all dependent
pins/cardinality gates. Existing77 explicit roots become78 and179 transitive
schemas become180; the existing raw-role count
1255 becomes1262 if no other amendment adds roots. Those counts describe this
amendment only, not a substitute for recomputing the full candidate inventory.
New cursor transitive references use existing typed request/scope/selector roots.
No historical schema is overwritten, upcast or given synthesized coordinates.
Old deployments lacking the new binding report ingestion-time continuation
unavailable; rollout publishes verified new registry before enabling this API.
Rollback invalidates ephemeral new tokens; historical graph reading is unchanged.

Required implementation evidence: both cursor round trips with separate public
key, wrong root/key/domain/publication, all request/predecessor/authority changes,
scope isolation, expiry during work, revocation-before-decode, zero and last
page, restart/eviction, concurrent write fence, both real attestation variants,
protected reader ceilings and no-fallback public provider routes. Run affected
registry/source/vector checks, graph cursor compatibility, paging/host tests,
identity gate, Ruff/Pyright and exact-candidate CI. Root owns long commands.

## Feasibility And Identity Ledger

cursor_feasibility.py/test_cursor_feasibility.py exercise the proposed strict
shape against real request and attestation types, exact retained comparisons,
order and predecessor behavior. They deliberately do not implement a private
signature/wire codec. Registered signing is existing verified machinery; the
new registered root and full production caller proof belong to implementation.
Tests are local design feasibility, not independent runtime certification.
All proposed root/function/domain names describe ingestion-time attestation
continuation; WorkPlan requirement labels remain only traceability metadata.

Known blockers: none beyond completing this amendment's evidence/review and
the separately tracked real cohort/backend implementation. No signing-key or
external policy choice is needed to specify this contract.

Exact downstream inventory owners under docs/work/semantic_ingestion/registry-publication:
source-role-inventory.json owns six authored roles per schema plus grammar
(1075->1081 for this amendment); decoder-source-selection.json adds the decoder
ID and retains the complete selected file closure. reproduce_publication.py
checks reviewed raw SHA256 values and regenerates decoder-source-manifest.json,
publication-manifest.json, registry.json and decoder roles under packaged
observation_registry_sources. It compares acceptance/observation_registry_compiler.py
normalized output. verify_registry_vectors.py retains independent vectors and
registry-vector-manifest/results.json; refresh hashes and cardinalities from
actual generated output. Source audit/root maps and package-source inclusion
records must identify the same new root. .github/workflows/pr-gates.yml owns
static-analysis, package-smoke, observation-ledger-activation and aggregate
pr-gate; its relevant commands and artifact pins must be inventoried again at
the integrated candidate, not inferred from this proposal's local feasibility.

The Spark map's unverified RegisteredGraphObservationCursor and
ActivatedGraphObservationContextResolver names, prompt-schema cursor assertions
and historical production witness inventory are rejected by coordinator direct
inspection. Actual owners and the no-witness boundary are specified above.

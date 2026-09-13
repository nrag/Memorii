# Observation Replay And Snapshot Contract

Status: design construction. Uses the owner-approved operational profile
direction in `profile-decision.md`; no production implementation is claimed.

## Snapshot Ownership And Activation Preconditions

The new `MemoryPlaneService.read_write_snapshot()` returns one detached
`(write_revision, records)` under the backend lock. The observer authorizes before
calling this method. Existing `read_snapshot()` remains unchanged: its data
revision does not advance for internal-control-only writes and is not a full
inventory fence.
All graph, source/result, observation-head/entry, reference-ledger, schema and
activation lookups for that observation resolve exclusively from these records.
Missing records do not fall back to live individual reads. The snapshot owner
checks duplicate canonical identities before constructing typed indexes.

The memory-plane write revision is a consistency token, not the graph or observation
revision. Those domain revisions are decoded from their respective heads in
the same snapshot. Activation and checkpoint publication require a separate
optional `expected_write_revision` on the service conditional batch and backend
`apply_batch`. Compare it under the same lock before publication. It is an exact
nonnegative integer, never a boolean. Preserve existing `expected_revision`
data-revision behavior for current unit-of-work callers. If both are supplied,
both must match. The JSONL backend already persists a full batch `revision`
separately from `data_revision`; use that existing full revision, without
rewriting old logs. The in-memory backend adds a separate write counter.
Every successful root canonical-record batch, including an empty batch consistently
with JSONL behavior, advances the full write revision; failed validation or CAS
advances neither counter. Stage/upsert/write/conditional routes share this rule.
Protected secret files do not mutate the canonical-record inventory and do not
participate in this token. A unit-of-work empty commit remains its existing
staged-view no-op and creates no root batch; nonempty UOW commit advances the
underlying full revision. Full-write snapshot/guard calls inside a UOW reject
rather than pairing a committed token with speculative records.

Activation scans the complete drained inventory from one snapshot and submits
that exact revision as well as the admission/head/immutable-record conditions.
This replaces the draft's unspecified "inventory partition revision": no such
separate partition token exists. Unrelated writes can conservatively cause a
retry; a retry must rescan rather than keep a stale inventory. A protected
finite retry limit bounds this work. Group/source append uses the narrower
head and source authority preconditions and does not require whole-store CAS.

## Replay State Grammar

`ObservationReplayState` is an immutable profile-3 schema with exactly:

- `schema_version`: integer literal 1;
- `repository_id`: nonempty string;
- `activation_digest`: lowercase SHA-256;
- `head`: the complete `ObservationLedgerHead`;
- `entries`: tuple of complete `ObservationLedgerEntry`, in sequence order;
- `records`: tuple of `CanonicalIngestionObservationRecord`, ordered by
  `(ingestion_record_kind, canonical record identity)` with no duplicates;
- `state_digest`: its registered digest, excluding only itself.

This first checkpoint format retains the full audit prefix. It is deliberately
not a pruning or compact-Merkle-proof protocol. Entries retain typed result
locators and graph-delta links through their canonical delta variants. The
checkpoint accelerates loading a verified materialization, not deletion of
source evidence. Resource exhaustion rejects rather than truncating a prefix.
Supporting a compact prefix later requires an explicit versioned design.

Genesis replay verifies activation, the complete entry chain, exact registered
delta variants, immutable result links and committed graph-delta/base-record
links. It applies every create mutation once and adds each source outcome once.
Repeated record identity, even with identical bytes, is rejected where the
canonical create contract forbids another introduction. Source-only empty
operation outcomes remain valid. Group operations require their complete
introduction/outcome bijection. Reconstructed records must equal the state's
exact ordered records; neither missing nor extra records are accepted.

The expected persisted head is read independently from the same snapshot. A
valid prefix is not a valid full replay unless its complete head equals that
expected head. There is no reliance on iterator exhaustion as completeness.

## Checkpoint And Signature Dependency Order

`ObservationCheckpointBundle` has exactly `schema_version=1`, `repository_id`,
`activation_digest`, `sequence`, `head`, `state: ObservationReplayState`,
`checkpoint: IngestionObservationReplayCheckpoint`, `lifecycle`,
`publication_receipt`, and `bundle_digest`. All duplicated repository/activation/sequence/head coordinates
must be equal. Sequence is positive: an empty genesis needs no checkpoint.

`ObservationCheckpointSigningPreimage` has exactly the registered purpose
literal `observation_checkpoint`, repository, activation, sequence, head,
the complete lifecycle snapshot including its authority digest, and all canonical checkpoint fields except checkpoint digest
and signature. Its materialized ledger digest equals `state.state_digest`.
Its last delta ID/digest and observation revision equal the head. Creation time
is protected-clock UTC and validated against the signing authority's interval.

Compute in this acyclic order: verified replay state and state digest; unsigned
checkpoint fields; complete registered signing preimage and checkpoint digest;
Ed25519 signature over the registered purpose/binding/preimage/digest; final
checkpoint; then publication receipt; then bundle digest. The signed preimage never includes bundle digest,
signature or its own checkpoint digest. Bundle digest includes the signed
checkpoint. A mutable signing callback does not choose different authority
coordinates after the preimage is frozen.

`ObservationCheckpointLifecycle` contains exactly repository_id,
authority_revision, registry_revision, registry_digest, registry_history_digest,
trust_policy_revision, trust_policy_digest, minimum_checkpoint_sequence,
predecessor_authority_digest (required nullable), and authority_digest. Revisions
and minimum sequence are positive exact integers. Genesis authority has revision
1 and null predecessor; successors increment authority revision by one, name the
exact predecessor digest, and never reduce registry/trust revisions or rollback
floor. Equal registry/trust revisions require equal corresponding digests.
Its registered digest excludes only authority_digest. The protected durable
authority owner retains the immutable predecessor chain and current head.

`ObservationCheckpointPublicationReceipt` contains exactly repository_id,
activation_digest, checkpoint_id, checkpoint_digest, lifecycle_authority_digest,
state_digest, head_digest, and receipt_digest. Its registered digest excludes
only receipt_digest. It is derived after signing, has no bundle digest or
mutable current-head dependency, and is retained both in the bundle and as an
immutable record in the same CAS. Reload requires byte equality. The lifecycle
snapshot in the bundle must equal the snapshot used by the signing preimage and
be reachable through the retained authority chain. Publication uses the current
authority without incrementing its revision merely to record a checkpoint.

Observation replay reconstructs observation records and revisions only, as
required by SIA23235-23240. It verifies linked graph deltas/results against
independently loaded canonical graph authority; it does not replace graph event
replay or claim to materialize graph state. The observation service composes
this verified ledger with the graph/reference snapshot from the same detached
memory-plane read. Graph replay retains its own checkpoint and authority owner.

Checkpoint creation reads the protected lifecycle and one consistent committed
snapshot, verifies the full replay, signs that exact preimage, then atomically
publishes bundle and lifecycle receipt under exact snapshot revision and current
lifecycle/admission preconditions. Failed CAS publishes neither; retry reacquires
all authority and re-signs only the newly frozen preimage. Signing alone is not
publication. The signer implementation and public-key verifier are configured;
actual release-key issuance remains deferred.

Checkpoint verification checks complete registry authority and original bytes,
current repository lifecycle and rollback floor, key identity and issue/current
use eligibility, signature and all equalities before accepting state. Retained
entries and immutable result/graph links remain available for integrity checks;
missing links reject. Tail replay begins immediately after the checkpoint head
and must reach the independently read expected current head. A later head does
not invalidate an old entry's immutable result locator. The old graph-event
checkpoint is not an observation checkpoint and is never accepted by structural
look-alike decoding.

## Authenticated Snapshot And Cohort Preimage

The existing normative request, cursor, page and observed-payload schemas in
SIA31360-31815 remain the public field inventories, except that the approved
profile-3 route replaces `ObservedClaimProjection` with its separate temporal
and trust models. The incomplete foundation classes do not supersede them. The
public cohort listing omits some coordinates explicitly required in the
normative prose at SIA31900. In profile 3, retain the existing
ResolvedGraphObservationCohort fields and add all the following coordinates.
This makes the public cohort independently verifiable even when a page contains
no projection records; no hidden metadata participates in its digest:

- `graph_revision` and `observation_revision` from the snapshot;
- `memory_plane_write_revision` from that same full detached snapshot;
- `temporal_projection_generation_digest` and
  `temporal_projection_pointer_digest`, resolved by the canonical temporal
  selector from those snapshot records, both required nullable digests;
- `trust_projection_generation_digest` and `trust_projection_pointer_digest`,
  resolved independently by the canonical trust selector from those same
  snapshot records, both required nullable digests;
- `observation_schema_fingerprint` (the reference schema fingerprint is already
  in the cohort fields);
- `changed_record_keys` and `boundary_record_keys`, each a sorted unique tuple
  of typed `(record_kind, primary_key)` records, disjoint from each other.

Each generation/pointer pair is either both present or both null. A null pair
means its verified history is absent at the requested coordinate; it cannot
stand in for an unread, invalid or unavailable history. A cohort requiring a
projection of that kind rejects if its pair is null. A terminal zero-effect or
zero-operation source remains observable before the first projection generation.
For lineage, each coordinate identifies the selected history tip; predecessor
links commit the reachable generations returned in the stream.

GraphObservationCohortPreimage has exactly the complete new public cohort fields
minus cohort_digest. The cohort uses the ordinary registered self_digest rule:
its complete ResolvedGraphObservationCohort binding and all its other fields,
without an external-preimage exception. The server retains the typed preimage
with the snapshot. An independently collected complete stream must have exactly
the declared disjoint changed/boundary keys and matching page/cohort coordinates;
matching a cohort digest alone does not prove complete paging.

The two projection coordinates are not a merged authority. The production
snapshot selector must apply the selection rules of
`ProjectionHistoryRepository.current_temporal`/`current_trust` for a current
view, and `historical_temporal`/`historical_trust` for a historical view with
the same requested system time; lineage follows each corresponding pointer
chain. It receives only indexes constructed from the one detached memory-plane
snapshot. It validates each complete native generation before retaining its
generation digest, complete `TemporalProjectionRecord` or
`TrustProjectionRecord`, complete corresponding active/history pointer, and
same-kind successor pointer where present. A temporal advance cannot substitute
or rewrite the trust coordinate, and conversely. Missing, swapped,
cross-repository, generation/pointer-mismatched, or unreachable values reject
observation rather than falling back to a live read.

`GraphObservationSnapshot` is a server-owned type alias for two model roots,
`GraphRecordObservationSnapshot` and `IngestionTimeObservationSnapshot`, each
with exactly schema version 1,
snapshot token, protected creation time, memory-plane revision, authenticated
context digest, purpose, authorization decision, complete request coordinates
excluding cursor, cohort preimage, resolved cohort, and immutable ordered stream.
The first root has purpose literal `graph_observation`, a cursor-free
GraphObservationRequest field, and a tuple of GraphObservationStreamRecord.
The second has purpose literal `ingestion_time_attestation`, a cursor-free
IngestionTimeAttestationRequest field, and a tuple of ProductionIngestionTimeAttestation.
The request field refers to an explicit model with the corresponding complete
request field set minus cursor, named GraphObservationRequestCoordinates or
IngestionTimeAttestationRequestCoordinates. The attestation tuple element uses
the canonical `kind`-discriminated model union. No mixed request/stream union
is inferred from fields outside its own model. The snapshot alias dispatches
only by the two fixed purpose literals and is not itself a registry entry.
All other fields are identical across the two roots. The token is an unguessable identifier,
not authorization. Its retention deadline is the earlier of authorization
expiry and creation time plus protected page-policy maximum age. Restart or
eviction that loses this state returns a stale cursor; it never reconstructs a
different stream under the old token. Durable snapshot caching is not required
for correctness and is not introduced by this ledger design.

Each page reauthorizes before looking up token or seed. It then validates the
cursor signature, exact request coordinates, stream position and preceding
triple, and the cursor's signed `snapshot_write_revision`. It obtains a fresh
full `read_write_snapshot()` token and requires it to equal both the cursor and
retained snapshot `memory_plane_write_revision` before using the stream. This
is intentionally conservative: any intervening canonical-record batch makes
continuation stale, including a temporal-only or trust-only projection-history
publication. It does not reload one projection kind or manufacture a merged
state. It then compares current graph/observation and page-policy revisions,
checks snapshot age, and emits only the next contiguous slice. The canonical failure
mapping in SIA31947-31962 remains unchanged. Snapshot state, cursor and page
all bind the same decision; equal principal text does not substitute for the
authenticated context digest. No error includes stored identity or cohort data.

`GraphObservationCursorPayload.v1` consequently adds the required nonnegative
integer `snapshot_write_revision`, copied from the retained snapshot. Its
signature-only policy signs that field together with every other cursor field;
the field is not caller supplied and cannot be omitted or null. The emitted
`GraphObservationPage` and `IngestionTimeAttestationPage` each carry the same
`memory_plane_write_revision`, so their
records, cohort, snapshot token and cursor are independently joinable. These
are profile-3 fields only; historical cursor bytes stay on their existing route.

The graph stream uses the explicit per-kind variant union specified in
`schema-publication.md`. The outer record kind is the discriminator, each
variant's payload model is fixed, and outer primary-key/digest equalities are
checked before stream ordering or cursor construction. `GraphObservationStreamRecord`
is a type alias only, never an independently decoded registry root.

## Production Binding And Proof

| Trigger | Owner and arguments | Required proof |
| --- | --- | --- |
| Activate ledger after drain | Writer admission -> memory-plane exact snapshot CAS | New control insertion or any intervening write prevents stale inventory activation |
| Group/source terminal write | Atomic store -> registered entry/head and native result in one conditional batch | Concurrent sources, lost acknowledgement, exact retry and no partial writes |
| Genesis replay | Observation persistence -> registered state from detached snapshot | Missing/extra/reordered entries and missing result/graph links reject |
| Checkpoint create/load | Observation replay authority -> protected lifecycle, profile registry, signer/verifier and snapshot | Wrong repository/key/lifecycle/floor or failed publication CAS rejects |
| First observation page | Public observation service -> authorizer -> one memory-plane snapshot -> cohort closure -> stream | No storage lookup on denial; mixed-revision assembly impossible |
| Next page | Same service -> current authorizer -> verified cursor -> retained snapshot | Expired/changed authority, duplicate/gap/overlap or lost snapshot never yields partial success |

Tests of these routes belong to the implementation packet. Existing ordering
and backend feasibility evidence proves only their previously recorded bounded
mechanics. No new complete replay, authentication or checkpoint claim follows
from this construction document.

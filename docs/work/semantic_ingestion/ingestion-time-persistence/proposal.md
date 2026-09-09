# Atomic Ingestion-Time Attestation Binding

## Canonical Owners And Trigger

`SemanticIngestionAtomicStore.admit_source` atomically publishes the retained
source record and preplanning generation before a terminal source result exists.
The source-retention attestation belongs to that admission CAS, not to a later
terminal CAS. Its `retained_at` must be supplied by the protected server clock and equal the
newly retained record timestamp; `source_record_digest` is that exact committed
record digest. The current provider instead uses the caller-owned event timestamp
for retention (see the reconciliation below), so that path must be corrected
before it can produce a truthful server-time attestation.
`commit_or_reload_bootstrap_graph_group_v3` samples
`transaction_started_at` once after request/reload discrimination and before
building effects; it samples `transaction_committed_at` once inside the winning
CAS construction immediately before records are submitted. The latter is never
earlier than the former. A CAS loser writes neither attestation; reload returns
the already persisted result and its original artifacts.

The protected composition root supplies `IngestionTimeClock` with `identity`
and `now_utc()`. The identity is a stable protected configuration identifier,
not a caller string. Both methods reject non-UTC timestamps. No fallback clock,
ambient `datetime.now`, caller time, or inferred event timestamp is permitted.

## Exact Durable Binding

Keep the existing closed `SourceRetentionTimeAttestation` and
`TransactionGroupCommitTimeAttestation` bodies and their registered self-digest
policies. Use the canonical registered artifact encoder and complete profile
binding. Their domains are respectively
`memorii.semantic_ingestion.observation.SourceRetentionTimeAttestation.v1` and
`memorii.semantic_ingestion.observation.TransactionGroupCommitTimeAttestation.v1`.
No bespoke digest preimage or trailing-NUL domain is introduced.

Add these exact versioned fields:

```text
CanonicalSourceTerminalOutcomeRecord:
  source_result_schema_version: Literal[1,2] = 1
  source_retention_attestation_digest: Digest|null = null
BootstrapGraphGroupCommitResultCoreV3:
  group_result_schema_version: Literal[1,2,3] = 1
  transaction_group_commit_attestation_digest: Digest|null = null
```

Source schema 1 omits its new fields from serialization and digest preimages,
preserving historical bytes. Source schema 2 requires a non-null source digest
and includes it in `record_digest`. Core schema 3 requires a non-null group
digest exactly when committed and null when noncommitting, including it in
`core_digest`. The source-finalization delta validates the schema-2 digest;
the group ledger/result locator validates the core-schema-3 digest. A later
terminal can reach but cannot manufacture the admission-CAS attestation.

The admission CAS writes the source member; the group CAS writes the group
member. Each is an execution record of source kind
`semantic_ingestion_source_retention_attestation` or
`semantic_ingestion_transaction_group_commit_attestation`. Its content is
exactly `{semantic_ingestion_kind, artifact}` where `artifact` is the registered
canonical bytes. The write preconditions already used by admission/group CAS
cover these members. Reload validates result digest -> member identity ->
registered artifact -> typed attestation -> all source/fence/group/operation,
graph revision, batch digest, and clock identity equality before returning.

## Membership And Recovery

Source retention binds source ID, operation fence, source-record digest, graph
revision and clock identity. Group commit binds source/fence/group IDs, sorted
operation IDs, start/commit instants, graph revisions, applied graph delta,
committed batch digest and clock identity. The detached ingestion-time reader
selects only registered artifacts whose result-bound digest is reachable from
the resolved source finalization/group entry and validates those exact joins.
Missing, duplicate, substituted, mixed-fence/source/group, invalid time order,
or absent result digest makes the cohort unavailable.

For legacy source schema 1 and group core schemas 1/2, readers preserve exact
serialization and return no synthetic attestations. Migration writes only source
schema 2 and group core schema 3; it never rewrites history or derives time
from a later record timestamp. An orphan admission member remains evidence but
is not cohort-reachable until schema-2 terminal binding. Partial member/result
publication fails closed; lost acknowledgement reloads the immutable winner.

## Required Implementation Proof

Cover source admission, committed and non-committing groups; duplicate/retry,
CAS race, crash between construction and write, lost acknowledgement, JSONL
reopen, clock identity/time/source/fence/group/operation/delta/batch mutations,
and legacy decoding. Prove source/group result digest substitution fails before
detached selection, and no attestation is emitted for a failed CAS or inferred
from an execution-record timestamp. This design does not choose clock service,
retention duration, polling policy, or any time value.

## Coordinator Readiness Findings

This is an unapproved draft, not an executable persistence contract. Before
freezing it, resolve the admission-time immutable anchor available before a
source terminal exists; specify its exact member/preimage/version and reload
validation. Specify `committed_batch_digest` without a circular dependency on
the result/attestation that itself contains that digest. Also enumerate
`publish_admitted_source` as well as `admit_source`, and identify the protected
clock at raw-source construction so its timestamp and clock identity have one
authority. Source-result field additions must account for the complete existing
core -> outcome ID -> source-result digest -> record digest chain, not only
`record_digest`. These are code-inspected readiness gaps; no producer or
compatibility guarantee has yet been implemented or verified.


## Canonical Admission Reconciliation (2026-09-08)

SIA lines 24391-24407 already require a retention attestation in the non-bootstrap
atomic admission request. Lines 24692 onward define its immutable request digest,
including the retention-attestation and pending-operation digests while excluding
current authorization evidence. The implementation's authorization index digest
is not that immutable request digest. Do not invent a second admission anchor.

SIA 24679 separately requires bootstrap admission without a writer binding or
pending operation until handoff. Current provider ingestion calls the writer-bound
`publish_admitted_source` before handoff; implementing a producer only there would
retain that discrepancy. The next revision must trace the canonical bootstrap
pre-writer path and preserve exact replay through handoff.

`source_admission_source_digest` deliberately excludes the retention timestamp;
it identifies the logical source for retry. Attestation `source_record_digest`
must instead use existing `record_digest(source)` for the complete persisted
record. These digests are not interchangeable. Clock identity is absent from the
retained record and cannot be inferred from its timestamp. The proposed terminal
schema additions above remain unapproved until the admission binding and acyclic
batch digest are fully specified. Read-only mapping independently confirmed these
paths; no production persistence schema has changed.


## Proposed Acyclic Group Batch Binding

Use the canonical event batch's original persisted digest for
`committed_batch_digest`, not the JSONL physical-write checksum or the logical
`atomic_write_digest`. In current production that is
`SemanticMemoryEventBatch.source_event_batch_digest` (equal to `event_batch_digest`
on fresh creation, preserving the original digest across reader upcasts).
The proposed dependency order is native graph delta -> canonical event batch ->
time attestation -> versioned result core -> receipt/result -> ledger entry.
The event batch excludes attestation/result bytes, so this chain has no cycle.
Only committed groups have this attestation; noncommitting groups have no batch
or attestation. The existing SIA names the attestation field but does not state
this exact equality, so this is a proposed clarification requiring design review,
not an already implemented guarantee. Physical store batch checksums include all
members and therefore cannot be used without a circular dependency or changing
their existing contract.


## Provider Clock Discovery

Direct coordinator inspection of `core/provider/ingestion.py` lines 397-409 found
that `retained_at = delivery_event.timestamp`, expressly documented there as a
caller-owned immutable delivery timestamp, and that this same value supplies both
`received_at` and `retained_at` to governance derivation. The preceding mapping's
phrase "existing server retention instant" was inaccurate. Keeping that value
and adding a protected clock identity would falsely authenticate caller time.

The producer change must route a single protected clock through both source
construction and governance derivation. Exact redelivery must load and reuse the
winning retained source/material/attestation after current authorization instead
of minting a new time. CAS losers must validate/reload the immutable winner or
return a typed retry-required outcome; they cannot relabel a newly sampled time
as the winner. This requires tracing initial authorization, authorized source
lookup, preparation, publication and retry together. Legacy records retain their
original bytes and never receive a synthetic server-time attestation. This is a
confirmed production-path gap against SIA 4.1.5, not missing release-signing data.

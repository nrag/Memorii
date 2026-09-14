# Shared Ledger Closed Contract Construction

Status: proposal supplement; not approved or registered. The source/result
hash dependency was reconciled in proposal.md after independent consultation. Runtime names describe audit
behavior; numeric versions below are persisted grammar versions, not delivery IDs.

## Store Record Schemas

All records are frozen/extra-forbidden. Counts are exact integers (not booleans),
identifiers nonempty strings, digests lowercase SHA-256 hex. Unknown variants or
versions fail. Repository identity is the configured store partition's canonical
semantic repository identity; callers cannot override it. Sequence orders the
whole partition, not a single source, tenant selector or wall-clock time.

ObservationLedgerHead has fields schema_version=1, repository_id,
activation_digest, sequence>=0, observation_revision, last_delta_id?,
last_delta_digest?, last_entry_digest?, head_digest. All three optional values
are null exactly at sequence0; revision is genesis exactly at sequence0.
head_digest binds every preceding field. The head record ID is the CTV-framed
repository identity under observation-ledger-head domain. No mutable payload is
excluded from head CAS comparison.

ObservationLedgerEntry has fields schema_version=1, repository_id,
activation_digest, sequence>=1, previous_entry_digest?, semantic_payload_digest,
delta:CanonicalIngestionObservationDelta, result_locator:ObservationResultLocator,
result_digest, entry_digest. previous_entry_digest is null exactly at sequence1.
The typed locator is group-primary or source-terminal with its immutable record
ID and corresponding stable source/group/fence coordinates. Unknown locators
reject. Entry ID derives from repository+delta ID, not sequence. Entry digest
binds every preceding field. Result digest names the immutable canonical result,
not a reload wrapper that itself contains the entry digest.

ObservationResultLocator is the closed union discriminated by `kind` of:

- ObservationGroupResultLocator: kind=`group_primary`, immutable_record_id,
  source_id, source_digest, source_operation_id, operation_fence_id,
  transaction_group_id, operation_ids, request_ctv_digest.
- ObservationSourceResultLocator: kind=`source_terminal`, immutable_record_id,
  source_id, source_digest, source_operation_id, operation_fence_id,
  namespace_id, artifact_generation>=1, member_id, publication_request_digest.

Each locator has schema_version=1. Identity strings are nonempty; source and
request digests are lowercase SHA-256; operation_ids is the exact sorted unique
nonempty tuple from the group request. Group record identity is recomputed by
the existing `_bootstrap_graph_v3_group_commit_primary_id` owner from the four
request coordinates, and source identity by `_bootstrap_graph_v3_member_id`
from namespace, generation and member ID. Locator IDs are not arbitrary lookup
authority. Replay requires those identities, source/fence coordinates and every
request digest to equal the retained request and manifest. Group result_digest
selects the retained BootstrapGraphGroupCommitResultV3.result_digest; source
result_digest selects BootstrapGraphCanonicalSourceResultV3.result_digest.
Neither selects the enclosing reload's digest. The source member must have kind
bootstrap_graph_canonical_source_result and occur exactly once in its verified
terminal manifest. Missing or ambiguous joins reject the complete replay.

ObservationLedgerSemanticPayload is a discriminated union of terminal_group and
source_finalization with EXACT fields of the corresponding canonical delta minus
observation_revision_before/after and delta_digest. It retains delta ID and all
source, scope, result, mutation and schema fields already declared by that delta.
It is a type alias, never a model registry root. Its alternatives are the model
roots ObservationGroupSemanticPayload and ObservationSourceSemanticPayload,
respectively, each at schema_version 1 in profile 3. The `kind` literal selects
exactly that root's protected binding; it cannot select an arbitrary schema ID.
Each payload digest includes that complete selected binding under the registered
observation semantic-payload domain. A full delta or the other variant fails
shape validation before hashing. No field is added merely to wrap this union.
No extra generic result digest is inserted into a terminal-group payload.
Successor is H(registered revision domain, repository, activation, predecessor,
semantic_payload_digest). Final delta digest then includes both revisions.
Full group/source record validation precedes these hashes. The ordering model's
minimal payload is illustrative; it is not this production schema.

## Terminal Intent And Receipt Grammar

SourceObservationIntent contains kind=source_finalization, source_outcome:
CanonicalSourceTerminalOutcomeRecord, observation_schema_fingerprint and
intent_digest. Its typed outcome already closes source/fence/delivery/governance,
operation set, groups and canonical source result. The store recomputes the
schema fingerprint from active registered schema and rejects a mismatch.

Terminal member schema3 introduces source_observation_intent as the final intent
kind. It is NOT persisted as the final source delta. The existing first nine
semantic intent kinds and multiplicities remain exact; the assembler validates
source_outcome equals canonical_source_result_input.completed_canonical_source_result.
Schema3 publication request contains source_observation_intent and forbids a
preassigned source_finalization_observation_delta. It seals all normal authority
and semantic inputs unchanged. Schema3 terminal reload requires exact assigned
source delta plus ledger entry ID/digest; it forbids absence of either.

At linearization, nine semantic intent kinds map to their existing receipt kinds;
source_observation_intent maps to exactly one native source-finalization delta
member. The store compares the reconstructed revision-free semantic source
payload against the intent, validates its assigned head transition, and binds
the actual complete manifest. It never compares final delta digest to the intent
digest. The manifest has exactly the existing members plus the one assigned delta;
entry/head are separate audit/control records in the same CAS, not fake semantic
members. Reload validates request intent, actual member, canonical source result,
entry result locator/digest and historical reachability under current head.

| Grammar | New write | Literal historical reload | Shared audit use |
| --- | --- | --- | --- |
| terminal1 / legacy group | Forbidden after activation | Existing exact bytes | None; missing audit fails cohort closure |
| terminal2 / local observation | Forbidden after activation | Existing exact bytes | None; never relabel local chain global |
| terminal3 / ledger group | Required after activation | Exact new bytes/joins | Entry must be reachable and complete |
| mixed/unknown | Reject | Reject | Reject |

## Activation And Writer Fencing

ObservationLedgerActivation contains schema_version=1, repository_id,
previous_writer_admission_digest, target_writer_epoch, writer_implementation_fingerprint,
observation_schema_fingerprint, ledger_codec_fingerprint,
legacy_terminal_inventory_digest, activation_digest. The inventory covers exact
legacy terminal/control IDs and digests at drain completion; it proves exclusion,
not imported audit. Activation digest excludes only itself. Target admission
retains this digest as an explicit typed field in its new admission/binding
grammar. Legacy admission serializer omits the field only for old grammar.

Store-owned activation first sets the existing draining fence under exact current
admission CAS. No new old-epoch operations may start. Existing operations finish
under old rules. Activation validates every old operation terminal/exhausted and
lease-free against the same complete control inventory used at final CAS; each
record and the inventory partition revision is a precondition. It then atomically
writes activation, genesis head and the incremented writer admission. Existing
nonterminal work prevents activation; it is never force-finalized. Repeating the
identical activated intent returns the same activation after exact inventory and
successor verification. Different content or stale admission rejects.

Every post-activation group/source writer requires current binding activation
digest and current ledger head. ALL legacy mutation recognizers are disabled in
that epoch; historical read/reload remains supported. Public ordinary writes,
unit-of-work batches and low-level atomic owner routes share governed policy.
Rollback can stop new ingestion while preserving read/replay, but cannot restore
an old writer epoch or erase the ledger. A later compatible writer needs a new
explicit migration; no implicit format downgrade is supported.

## Replay, Checkpoint And Resource Contract

Authoritative genesis replay requires an independently read persisted head;
an arbitrary valid prefix is not completeness. It verifies every entry in exact
sequence, repository/activation, unique delta identity, before/after chain,
semantic/final/entry commitments and canonical result/graph links. Retained
source outcomes and operation pairs reconstruct the audit record set without
providers or provenance-index inference. A replay byte parser uses registered
CTV/schema limits before allocation/recursive decoding; resource settings come
from protected deployment configuration and cannot be supplied with entries.

Checkpoint remains the canonical IngestionObservationReplayCheckpoint payload
(SIA23010), with an explicit outer ObservationCheckpointBundle containing
repository_id, activation_digest, sequence, head, canonical materialized ledger,
checkpoint, lifecycle_revision and bundle_digest. The materialized ledger digest
binds the complete typed audit records, delta identities/digests, result/graph
links and prefix head, so merely presenting a matching last delta cannot substitute
a partial prefix. The signed checkpoint's checkpoint_digest preimage MUST bind
the outer repository/activation/sequence/head/lifecycle coordinates as well as
its declared fields. This requires a registered observation-specific preimage;
reusing graph-checkpoint bytes or relying only on unsigned bundle_digest is forbidden.

Observation checkpoint lifecycle is a distinct repository-scoped monotonic owner
with authority_revision, registry revision/digest/history digest, trust policy
revision/digest, minimum_checkpoint_sequence and predecessor authority digest.
Verification compares current protected lifecycle, key issue/current-use state,
repository, activation and rollback floor before using the prefix. Configured
Ed25519 signer/public verifier use explicit raw-public-key fingerprints and
64-byte signatures; no production signature is required for implementation tests.
Checkpoint creation occurs only at a validated committed head and atomically
publishes the exact bundle and checkpoint lifecycle receipt. A concurrently
advanced head retries from new authority; a signature alone cannot activate a
checkpoint. Tail replay starts at exact saved successor and must reach current
expected head. Unsigned/untrusted/stale checkpoints fail closed; no silent
fallback to claiming checkpoint success. Genesis remains a separate explicit
recovery route.

Head retry budget and decoding/ledger snapshot resource ceilings are positive
protected configuration values. Exhaustion yields retryable/stale failure, never
partial ledger state. Tests inject small limits to verify boundaries; these are
operational limits, not statistical acceptance thresholds.

## Remaining Readiness Work

This construction still needs exact registered CTV bindings, the generated
schema/profile/writer ownership inventory and a real transaction feasibility
proof. The checkpoint outer-preimage proposal changes the currently declared
signing contract and must receive independent design review before canonical
promotion. The minimal ordering model does not establish these broader claims.

Production registration boundary: the new schema IDs will be behavior-owned
coordinates for the head, entry, revision-free payload, source intent, activation,
replay state, checkpoint bundle and signing preimage. They are registered through
CanonicalTypedValueProfileRegistryEntry at the canonical ingestion codec owner,
not by adding them to the nonoperational traceability inventory. Exact field,
policy and decoder fingerprints remain to be frozen. No existing body hash or
well-shaped caller binding substitutes for a trusted registry entry.

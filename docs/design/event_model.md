📄 Memorii Event Model

Canonical Event Payload and Replay Specification

⸻

1. Problem Statement

The current specification defines:

* event sourcing
* replay-based reconstruction

But does not define a canonical event payload shape, leading to ambiguity in:

* how entities are reconstructed
* how replay is deterministic
* how idempotency is enforced
* how different graph types are handled

This addendum defines a strict, canonical event model.

The event-model-owner decision selecting fail-closed equal-version handling is
frozen in `docs/design/equal_version_replay_decision-v1.json`. Its validator
binds this document, the semantic-ingestion design, and the conflict-attention
design by digest.

⸻

2. Design Principles

All event payloads must satisfy:

1. Deterministic replay
    * Same event log → same reconstructed state
2. Idempotency
    * Re-applying the same event must not duplicate state
3. Explicit typing
    * No implicit interpretation of payload
4. Graph independence
    * Execution graph and solver graph handled uniformly
5. Forward compatibility
    * Schema versioning supported

⸻

3. Canonical Event Structure

3.1 Base Event Schema

{
  "event_id": "string",
  "dedupe_key": "string",
  "logical_mutation_digest": "sha256 hex",
  "event_type": "string",
  "schema_version": "string",
  "repository_id": "string",
  "timestamp": "ISO8601",
  "task_id": "string | null",
  "execution_node_id": "string | null",
  "solver_run_id": "string | null",
  "payload": { ... },
  "provenance": {
    "source_type": "enum(user|agent|tool|system|derived)",
    "source_id": "string | null"
  },
  "event_digest": "sha256 hex"
}

`event_id` identifies one immutable envelope. `dedupe_key` identifies one
logical mutation across delivery retries, and `logical_mutation_digest` binds
the canonical mutation intent before an event ID or batch position is
allocated. Neither is the record identity. `event_type` is the registered
schema identifier; there is no second `schema_id` alias.

The event digest uses the closed semantic-ingestion canonical typed-value
profile over every field except `event_digest`, with domain separator
`memorii.event-envelope.v1`. Historical bytes verify under their declared
schema before a pure deterministic upcast. Unknown, future, retired-without-
upcaster, digest-invalid, or ambiguous schemas fail before exposure.

Repository order belongs to the batch, not to each event:

```text
EventBatch
  repository_id: string
  log_position:
    repository_id: string
    sequence: positive integer
    position_digest: sha256 hex
  events: nonempty tuple[BaseEvent, ...]
  event_batch_digest: sha256 hex
```

The zero-based tuple index is the event offset. The repository ID, positive
batch sequence, and derived offset form the authoritative log coordinate;
timestamps and event IDs never order replay. Batch and event repository IDs
must agree. The batch digest binds its log position and ordered event digests.

For semantic ingestion, `SemanticMemoryEvent` is the registered specialization
of `BaseEvent`, `event_digest` is the one event-envelope digest, and
`SemanticMemoryEventBatch` is the registered specialization of `EventBatch`.
Its `log_position.sequence` is the batch sequence and tuple order supplies the
event offsets. Semantic profile fields such as transaction group, operation
fence, and governance bindings extend the base event and batch; they do not
replace or alias base identities. The semantic event registry owns supported
versions and deterministic upcasters. A strict generic-to-semantic conformance
validator must reject any field, digest, repository, sequence, or offset
inconsistency before replay.

⸻

4. Canonical Payload Shape

4.1 Required fields

Every payload MUST include:

{
  "graph_type": "execution | solver | memory | system",
  "entity_type": "node | edge | overlay | memory_object | checkpoint | directory | routing",
  "operation": "create | update | delete | link | unlink | version",
  "entity_id": "string",
  "record_id": "string",
  "entity": { ... },
  "metadata": {
    "version": "int",
    "is_candidate": "bool",
    "is_committed": "bool"
  }
}

For semantic-ingestion memory events, `entity_id == record_id` and the record
identity is distinct from `event_id` and `dedupe_key`. Their mutation kind is
the closed `create | update` contract from the semantic compiler. Logical
retirement, invalidation, supersession, and archival are full-state updates,
never physical deletion. Other graph profiles must declare their legal
graph/entity/operation combinations in their own registered schema; the base
string examples do not authorize a combination.

⸻

5. Entity Definition Rules

5.1 Entity is full snapshot

entity MUST contain the full state required to reconstruct the object.

Do NOT use partial patches.

Example:

{
  "entity": {
    "node_id": "n123",
    "node_type": "hypothesis",
    "content": "...",
    "attributes": {...}
  }
}

⸻

5.2 No implicit reconstruction

Replay must NOT rely on:

* previous in-memory state
* implicit defaults
* missing fields

Everything needed must be in the payload.

⸻

6. Graph Type Semantics

6.1 Execution Graph

"graph_type": "execution"

* entity_type: node | edge
* reconstruct execution graph structure
* used for task/work state

⸻

6.2 Solver Graph

"graph_type": "solver"

* entity_type: node | edge | overlay
* reconstruct reasoning/search state

⸻

6.3 Memory

"graph_type": "memory"

* entity_type: memory_object
* reconstruct memory domain entries

⸻

6.4 System

"graph_type": "system"

* entity_type: checkpoint | directory | routing
* reconstruct global state

⸻

7. Operation Semantics

7.1 create

Creates entity with full state.

Idempotent only when the event ID, dedupe key, and record-version reservation
already bind the same canonical envelope and logical-mutation digest. Merely
finding the same entity ID and version is not idempotency.

⸻

7.2 update

Replaces entire entity.

Must include:

"metadata": {
  "version": <incremented version>
}

⸻

7.3 delete

Marks entity as deleted.

Do NOT physically remove during replay.

⸻

7.4 link / unlink

Used for edges if edges are stored separately.

⸻

7.5 version

Used for overlays:

* new version created
* previous versions preserved

⸻

8. Versioning Rules

8.1 Monotonic version

Each entity must maintain:

"metadata": {
  "version": int
}

Rules:

* version must strictly increase
* replay must ignore older versions

⸻

8.2 Conflict resolution

For events with the same entity identity:

* a strictly higher version may replace a lower version only after version
  continuity and operation semantics validate
* a byte-identical canonical envelope is an idempotent duplicate
* two non-identical envelopes that claim the same entity identity and version
  are a storage-integrity conflict

A storage-integrity conflict MUST fail closed before either event is selected
or materialized. Timestamp, arrival order, and event_id ordering MUST NOT choose
a winner. The same rule applies during live append, genesis replay, and replay
after a checkpoint.

⸻

9. Idempotency Rules

Replay must be safe under:

* exact redelivery of a previously committed event envelope
* logical append retry using the same dedupe key and mutation digest
* a complete genesis prefix ending on a repository-batch boundary
* a complete tail after a fully validated checkpoint

9.1 Idempotency key

Primary key:

(event_id)

Secondary:

(dedupe_key)

Record-version reservation:

(repository_id, graph_type, record_id, version)

The event-ID index binds one event ID to one envelope digest. The dedupe index
binds one logical mutation key and mutation digest to one committed envelope,
record/version, and batch position.
The record-version index binds one record/version to one envelope digest. All
three bindings publish atomically with the event batch and materialized state.

Before allocating another event ID or batch position, live append looks up the
dedupe key. Reusing it with the same logical-mutation digest returns the
previously committed envelope and position. Divergent reuse of an event ID,
dedupe key, or record-version reservation raises `memory_integrity_conflict`.
It never allocates a second envelope or selects one binding as the winner.

⸻

9.2 Replay behavior

If event already applied:

* skip only when the canonical envelope is byte-identical

If entity exists with same version:

* skip only when the event is the same canonical envelope already bound to
  that entity and version
* otherwise raise a storage-integrity conflict before changing state

If entity exists with lower version:

* apply

If entity exists with higher version:

* ignore event

⸻

10. Replay Algorithm (Canonical)

10.1 Input

* ordered event stream

10.2 Algorithm

for batch in complete_batches:
    require_next_contiguous_batch_position(batch)
    validate_batch_digest_and_complete_offsets(batch)
    candidate = copy(last_verified_state_and_all_binding_indexes)
    for event in batch.events:
        validate_schema_digest_and_references(event)
        if event.event_id in candidate.event_id_index:
            require_same_event_digest_and_binding(event)
            continue
        if event.dedupe_key in candidate.dedupe_index:
            require_same_logical_mutation_digest_and_committed_envelope(event)
            continue
        reservation = (
            event.repository_id,
            event.payload.graph_type,
            event.payload.record_id,
            event.payload.metadata.version,
        )
        if reservation in candidate.record_version_index:
            require_same_bound_canonical_envelope(reservation, event)
            continue
        apply_full_state_operation(candidate, event.payload)
        bind_event_dedupe_and_record_version_indexes(candidate, event)
    publish_batch_state_indexes_and_position_atomically(candidate, batch)

One complete repository batch is the atomic replay unit. The reducer validates
its repository identity, position continuity, digest, complete offset set,
every event, every binding index, and every reference in isolated candidate
state. Any failure discards the whole batch. No partial winner, binding,
processed-event marker, checkpoint position, or materialized view from the
failed batch becomes visible.

⸻

11. Overlay Handling

Overlay events MUST:

* use entity_type = overlay
* use operation = version
* always create new version
* never mutate previous versions

⸻

12. Candidate vs Committed in Events

12.1 Representation

"metadata": {
  "is_candidate": true/false,
  "is_committed": true/false
}

12.2 Rules

* candidate entities may be overwritten or invalidated
* committed entities require stronger validation before update
* replay must preserve distinction

⸻

13. Validation Requirements

Before applying an event:

13.1 Schema validation

* required fields present

13.2 Type validation

* graph_type valid
* entity_type valid
* operation valid

13.3 Referential validation

* edges reference existing node_ids (or are applied after nodes)

13.4 Version validation

* version monotonic

⸻

14. Event Ordering Guarantees

14.1 Preferred ordering

Events SHOULD be stored in:

* append-only order
* contiguous repository batch-position order

Timestamps remain event data and may support temporal projection, but they do
not determine replay order.

14.2 Replay safety

Replay MUST tolerate:

* duplicated events
* a complete prefix ending on a batch boundary
* replay starting after a fully validated checkpoint batch position

An arbitrary partial log or mid-batch start is corruption, not a supported
ordering variation.

⸻

15. Checkpoint Integration

Checkpoint must store:

* repository_id
* last complete batch sequence and digest
* last processed event_id and dedupe_key
* event-ID, dedupe, and record-version binding snapshot or a digest-bound
  independently loadable index generation
* snapshot of:
    * execution graph
    * solver graph
    * overlays

On resume:

* validate checkpoint signature, schema/policy bindings, snapshot digest, and
  complete event-batch position before exposing it
* load the validated checkpoint into isolated candidate state
* replay complete event batches after its position using the same conflict
  algebra as genesis replay
* if a tail event conflicts with checkpoint-bound entity/version state, reject
  the affected replay scope before exposing the checkpoint-plus-tail result

An invalid checkpoint is retained for diagnosis and is not silently repaired.
Genesis replay may be attempted only from independently verified event and
artifact history; it uses the same equal-version rule and therefore cannot turn
a checkpoint conflict into a winner.

Batch sequence is contiguous per repository and event offsets are contiguous
within a batch. Replay accepts only complete batches and reads them with
`read_batches_after(repository_id, last_complete_batch_sequence)`. A gap,
duplicate position, cross-repository position, batch-digest mismatch, or
position rollback fails before candidate-state exposure.

⸻

16. Testing Requirements

You MUST add tests for:

16.1 Determinism

Same event log → identical reconstructed state

16.2 Idempotency

Duplicate events → no duplication

16.3 Ordering and batch continuity

* contiguous complete repository batches apply deterministically
* gaps, duplicate positions, cross-repository positions, incomplete offsets,
  and batch-digest mismatches fail without visibility

16.4 Version correctness

Higher version overrides lower

16.5 Replay boundaries

* a complete genesis prefix ending on a batch boundary is consistent
* a complete tail after a validated checkpoint is consistent
* a truncated batch or arbitrary midpoint start fails closed

16.6 Equal-version integrity

* byte-identical duplicate envelopes are idempotent
* non-identical equal-version envelopes fail before visibility
* divergent create, update, event-ID, dedupe-key, and record-version bindings
  all return the same typed integrity failure
* every arrival, timestamp, and event-ID ordering has the same result
* genesis and checkpoint-tail replay have the same result
* supported historical schemas upcast before comparison; future,
  retired-without-upcaster, digest-invalid, and mixed-schema ambiguity fail

16.7 Atomic failure

An invalid event, missing artifact, continuity error, or integrity conflict
leaves the last verified materialized state and replay position unchanged.

16.8 Cross-graph correctness

Execution and solver graphs reconstructed independently

16.9 Profile conformance

* generic event and batch projections accept every valid semantic profile event
* a schema-ID alias, digest alias, repository mismatch, zero batch sequence,
  incoherent tuple-derived offset, or unsupported system entity variant rejects
  before reducer access

16.10 Logical append retry

The same dedupe key and logical-mutation digest, before and after repository
reopen, returns the original event envelope and batch position with one
committed event and byte-identical state and indexes. A changed mutation digest
is the paired integrity-conflict case.

⸻

17. Explicit Constraints

Do NOT:

* use partial patch updates
* infer missing fields
* rely on in-memory state during replay
* mix execution and solver graph reconstruction logic
* mutate overlay history
* choose a non-identical equal-version winner by timestamp, arrival order, or
  event_id

⸻

Summary

This addendum defines:

* canonical event payload
* strict replay contract
* versioning rules
* idempotency rules
* graph reconstruction rules

This resolves Codex’s ambiguity around:

payload.graph_type + payload.entity

by making it:

* explicit
* typed
* deterministic
* replay-safe

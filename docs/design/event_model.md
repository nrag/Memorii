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
  "event_type": "string",
  "schema_version": "string",
  "timestamp": "ISO8601",
  "task_id": "string | null",
  "execution_node_id": "string | null",
  "solver_run_id": "string | null",
  "payload": { ... },
  "provenance": {
    "source_type": "enum(user|agent|tool|system|derived)",
    "source_id": "string | null"
  }
}

⸻

4. Canonical Payload Shape

4.1 Required fields

Every payload MUST include:

{
  "graph_type": "execution | solver | memory | system",
  "entity_type": "node | edge | overlay | memory_object",
  "operation": "create | update | delete | link | unlink | version",
  "entity_id": "string",
  "entity": { ... },
  "metadata": {
    "version": "int",
    "is_candidate": "bool",
    "is_committed": "bool"
  }
}

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

Idempotent if entity_id already exists with same version.

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

If two events have same entity_id:

* higher version wins
* if same version → event_id ordering defines precedence

⸻

9. Idempotency Rules

Replay must be safe under:

* duplicate events
* partial replay
* out-of-order ingestion (within tolerance)

9.1 Idempotency key

Primary key:

(event_id)

Secondary:

(entity_id, version)

⸻

9.2 Replay behavior

If event already applied:

* skip

If entity exists with same version:

* skip

If entity exists with lower version:

* apply

If entity exists with higher version:

* ignore event

⸻

10. Replay Algorithm (Canonical)

10.1 Input

* ordered event stream

10.2 Algorithm

for event in events:
    if event_id already processed:
        continue
    payload = event.payload
    graph = resolve_graph(payload.graph_type)
    entity_id = payload.entity_id
    version = payload.metadata.version
    existing = graph.get(entity_id)
    if existing:
        if existing.version > version:
            continue
        if existing.version == version:
            continue
    apply_operation(graph, payload)
    mark event_id as processed

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
* timestamp order

14.2 Replay safety

Replay MUST tolerate:

* duplicated events
* partial logs
* replays starting mid-stream

⸻

15. Checkpoint Integration

Checkpoint must store:

* last processed event_id
* snapshot of:
    * execution graph
    * solver graph
    * overlays

On resume:

* load checkpoint
* replay events after last processed event_id

⸻

16. Testing Requirements

You MUST add tests for:

16.1 Determinism

Same event log → identical reconstructed state

16.2 Idempotency

Duplicate events → no duplication

16.3 Ordering tolerance

Out-of-order (within window) → correct state

16.4 Version correctness

Higher version overrides lower

16.5 Partial replay

Replay from midpoint → consistent state

16.6 Cross-graph correctness

Execution and solver graphs reconstructed independently

⸻

17. Explicit Constraints

Do NOT:

* use partial patch updates
* infer missing fields
* rely on in-memory state during replay
* mix execution and solver graph reconstruction logic
* mutate overlay history

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
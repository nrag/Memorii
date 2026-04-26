📄 Memorii Storage Details 

Enhancements Inspired by MemPalace

⸻

1. Verbatim Transcript Memory (Strengthened Requirement)

1.1 Principle

Raw transcript memory must be treated as a first-class, lossless source of truth.

The system MUST:

* store user messages, agent messages, and tool outputs verbatim where possible
* preserve full fidelity of raw interaction data
* never overwrite or mutate transcript memory with summarized or transformed content

1.2 Separation of concerns

Transcript memory:

* contains raw interaction data
* is append-only (except for explicit redaction operations)
* is never used to store derived knowledge

Derived memory (semantic, episodic, etc.):

* must reference transcript memory via source_refs
* must not replace transcript entries

1.3 Retrieval behavior

The retrieval planner MUST be able to:

* retrieve raw transcript segments directly
* prioritize verbatim evidence for grounding
* combine transcript retrieval with higher-level abstractions

⸻

2. Scoped Retrieval Model

2.1 Problem

Flat retrieval across all memory leads to:

* irrelevant context
* cross-task contamination
* degraded reasoning quality

2.2 Requirement

All retrieval must be explicitly scoped.

2.3 Retrieval scope dimensions

Every retrieval plan MUST include one or more of the following filters:

* memory_domain
* task_id
* execution_node_id
* solver_run_id
* agent_id
* user_id
* artifact_id
* time_range (optional)

2.4 Retrieval planner behavior

The retrieval planner MUST:

* choose memory domains explicitly
* choose scope constraints explicitly
* avoid global search unless explicitly required

2.5 Example

For debugging:

{
  "intent": "debug_or_investigate",
  "domains": ["solver", "episodic", "semantic"],
  "scope": {
    "task_id": "...",
    "execution_node_id": "..."
  }
}

⸻

3. Temporal Validity for Memory Objects

3.1 Motivation

Certain facts, assumptions, and environmental conditions may become stale over time.

3.2 Applicable domains

Temporal validity MAY apply to:

* semantic memory
* solver assumptions
* environment references
* user context (optional)

3.3 Schema addition

Add optional fields to relevant memory objects:

{
  "valid_from": "timestamp | null",
  "valid_to": "timestamp | null",
  "validity_status": "active | expired | invalidated | unknown"
}

3.4 Behavior

* expired or invalidated items MUST NOT be treated as valid evidence
* retrieval planner SHOULD filter or downgrade stale items
* solver may reopen branches if underlying assumptions become invalid

3.5 Resume behavior

On resume:

* validate temporal constraints
* mark stale assumptions
* trigger re-evaluation if necessary

⸻

4. Memory Hook Interface (Harness Integration)

4.1 Purpose

Allow integration with agent harnesses for:

* checkpointing
* context compaction
* lifecycle events

4.2 Required hooks

Memorii MUST support the following hook points:

Pre-compaction hook

Triggered before context compression in host system

Use:

* capture high-fidelity state
* preserve important transient context

Post-message hook

Triggered after each user/agent message

Use:

* route transcript entries
* extract candidate memory objects

Post-tool-result hook

Triggered after tool execution

Use:

* create observations
* update execution/solver memory

Periodic checkpoint hook

Triggered at defined intervals

Use:

* persist execution graph state
* persist solver state
* append event log entries

Task completion hook

Triggered when a task completes

Use:

* trigger consolidation
* generate writeback candidates

Resume hook

Triggered when task resumes

Use:

* reload execution graph
* reload solver graph
* validate temporal state
* reconstruct frontier

⸻

5. Agent-Scoped Memory Partitions

5.1 Motivation

Multiple agents may:

* work on different subproblems
* have specialized roles
* require isolated context

5.2 Requirement

Memorii MUST support agent-scoped memory partitioning.

5.3 Scope behavior

Memory objects MAY include:

{
  "agent_id": "string | null"
}

5.4 Behavior

* episodic memory may be agent-specific
* solver graphs may be agent-specific
* transcript entries may be tagged by agent
* retrieval may filter by agent scope

5.5 Cross-agent interaction

* agents may reference shared memory
* agent-specific memory must not leak unless explicitly allowed

⸻

6. Backend Plugin Architecture (Formalized)

6.1 Requirement

All memory stores MUST be pluggable via a backend interface.

6.2 Interface principles

Each store must expose:

* typed inputs and outputs
* explicit error handling
* health check capability

6.3 Registration

Backends MUST be discoverable via plugin registration (e.g., entry points).

6.4 Example interface

class BaseStore(Protocol):
    def put(self, obj): ...
    def get(self, id): ...
    def query(self, filters): ...
    def health(self): ...

6.5 Separation

Logical model MUST NOT depend on backend implementation.

⸻

7. Local-First Design Principle

7.1 Requirement

Memorii MUST operate in a local-first mode.

7.2 Behavior

* all core functionality must work without external services
* cloud backends are optional
* sensitive data must not be transmitted without explicit configuration

7.3 Implications

* local storage backends must be available
* default configuration must not require network access

⸻

8. Retrieval Benchmarking and Evaluation

8.1 Requirement

Memorii MUST include benchmarking capabilities for memory performance.

8.2 Metrics

At minimum:

* Recall@K (retrieval)
* Precision@K
* retrieval latency
* routing accuracy
* resume correctness
* solver recovery accuracy

8.3 Separation of concerns

Benchmark categories MUST be separated:

* transcript retrieval
* semantic retrieval
* episodic retrieval
* execution resume correctness
* solver resume correctness
* routing accuracy
* retrieval planning quality

8.4 Reproducibility

Benchmarks MUST:

* be deterministic where possible
* include dataset definitions
* separate retrieval from reranking

⸻

9. Structured Retrieval Namespaces

9.1 Requirement

Memory must be logically partitioned into namespaces.

9.2 Namespace model

Instead of “palace rooms,” use structured keys:

{
  "namespace": {
    "memory_domain": "...",
    "task_id": "...",
    "execution_node_id": "...",
    "solver_run_id": "...",
    "agent_id": "...",
    "artifact_id": "..."
  }
}

9.3 Behavior

* namespaces must be enforced at write time
* retrieval must respect namespace boundaries
* cross-namespace queries must be explicit

⸻

10. Checkpointing Enhancements

10.1 Requirement

Checkpointing must be explicit and reusable.

10.2 Checkpoint content

A checkpoint MUST capture:

* execution graph snapshot
* solver graph snapshot
* belief/status overlays
* active frontier
* unresolved questions
* unexplained observations

10.3 Behavior

* checkpoints must be replayable
* checkpoints must support resume without recomputation
* checkpoint frequency may be configured

⸻

11. Design Constraints Reinforced

The following constraints are explicitly reaffirmed:

* transcript memory remains verbatim
* retrieval is always scoped
* memory domains remain separate
* execution graph and solver graph remain distinct
* candidate vs committed lifecycle remains enforced
* no speculative writes to semantic or user memory
* no single unified “memory blob”

⸻

Summary

This addendum strengthens Memorii in the following ways:

Area	Improvement
Transcript memory	Explicit verbatim guarantee
Retrieval	Scoped, namespace-aware
Temporal reasoning	Validity windows
Integration	Hook-based lifecycle
Multi-agent	Agent-scoped memory
Extensibility	Plugin backend architecture
Reliability	Benchmark discipline
Resume	Stronger checkpoint semantics
Architecture	Reinforced separation of concerns

⸻

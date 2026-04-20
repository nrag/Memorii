Memorii — Updated Implementation Plan
Overview

Memorii is a memory plane for agent systems.

It separates:

execution memory
solver memory (state-space reasoning)
semantic / episodic / user memory
routing, retrieval, and consolidation

Unlike traditional memory systems that optimize for retrieval alone, Memorii focuses on:

correct memory usage
safe writeback
stateful reasoning
resumability
Phase Progression (Updated)
Phase 1–2: Core Modeling (COMPLETED)

Implemented:

memory domain models (semantic, episodic, user, transcript)
execution graph
solver graph
event schema
identity model (task_id, node_id, etc.)

Outcome:

clear separation of memory types
typed, structured memory foundation
Phase 3: Persistence + Event System (COMPLETED)

Implemented:

event log (append-only)
replay and idempotency
overlay model for solver state
persistent stores

Outcome:

deterministic reconstruction
durable memory state
replay-safe execution
Phase 4: Memory Plane (COMPLETED)

Implemented:

router (multi-domain routing)
retrieval planner (scoped retrieval)
memory directory
consolidation pipeline (candidate-only writeback)

Key behavior:

no direct writes to semantic/user memory
routing determines memory placement
retrieval is intent + scope driven

Outcome:

structured memory system instead of flat retrieval
Phase 5: Runtime + Solver (COMPLETED)

Implemented:

runtime step loop
solver update pipeline
abstention states:
SUPPORTED
REFUTED
INSUFFICIENT_EVIDENCE
NEEDS_TEST
MULTIPLE_PLAUSIBLE_OPTIONS
deterministic verifier

Outcome:

explicit reasoning state
controlled updates to solver graph
no blind commitment
Phase 7: Benchmarking Framework (COMPLETED)

Implemented:

benchmark harness
fixtures
metrics:
retrieval
routing
resume
solver validation
writeback correctness
baseline comparisons:
transcript-only
flat retrieval
no solver graph

Outcome:

measurable system behavior
baseline comparisons available
Phase 7.1: Advanced Benchmark Coverage (COMPLETED)

Added:

learning across episodes
long-horizon degradation
conflict resolution
implicit recall

Outcome:

benchmark coverage now spans:
memory correctness
reasoning correctness
temporal behavior
inference-driven retrieval

Phase 8: Benchmark Review (CURRENT PHASE)
Goal

Understand system behavior before locking APIs.

Focus
analyze benchmark outputs
compare against baselines
identify failure modes
classify root causes
Deliverables
Benchmark summary table:
category → Memorii vs baseline vs delta
Top failures list (5–10 cases)
Root cause classification:
retrieval planner
routing
verifier
runtime
data/fixture issues
Fix prioritization:
must fix before integration
should fix
can defer
Key principle

Do NOT change architecture here.
Only analyze.

Phase 9: Cleanup + API Stabilization
Goal

Prepare Memorii for external use.

Focus
fix drift:
solver_run_id canonicalization
remove solver_graph_id from public models
tighten schemas:
solver decision schema
verifier strictness
clean boundaries:
retrieval policy → planner
runtime → execution only
finalize internal contracts
Deliverables
stable internal interfaces
stable public API design
consistent event schema
Phase 10: Integration (Adapters + Harness)
Goal

Make Memorii usable in real systems.

Focus
runtime API:
start_task
step
resume_task
get_state
adapter layer:
generic adapter
one real harness integration
model integration layer
Deliverables
working end-to-end integration
harness-driven execution
example usage
Principle

Adapters are thin.
Memory system remains unchanged.

Phase 11: Hardening + Optimization
Goal

Make Memorii production-ready.

Focus
performance:
retrieval latency
planner efficiency
storage:
memory growth control
robustness:
replay correctness
failure recovery
observability:
logs
traces
Deliverables
stable system under load
predictable performance
debugging capability
Phase 12: Expansion (Optional)
Focus
additional adapters
additional storage backends
advanced evaluation
optional harness-level proposal engines

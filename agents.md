# AGENTS.md

## Purpose

This file is the operating guide for contributors and coding agents working on
Memorii. It records repository-wide invariants and workflow rules. Detailed
behavior belongs in the design documents and tests linked below; do not copy
large specifications into this file.

Memorii is a framework-neutral memory plane for agents. It is a typed,
multi-memory system with explicit routing, retrieval, persistence, execution
memory, solver/search memory, and conservative memory evolution. It is not a
generic chat-history wrapper, a single vector store, a single graph for every
kind of state, or a replacement for an agent harness.

## Sources Of Truth

Before changing a subsystem, read the documents that govern it. Use this
precedence when requirements conflict:

1. `docs/design/memorii_spec.md`
2. `docs/design/memorii_storage_details.md`
3. `docs/design/event_model.md`
4. `docs/IMPLEMENTATION_RULES.md`
5. The relevant current document under `docs/design/`
6. `docs/plans/engineering_hardening_closure_matrix.md` for the current
   hardening acceptance contract
7. `docs/plans/agent_integration_readiness.md` for integration scope and
   readiness claims
8. This file
9. `docs/plans/initial.md`, which is historical context rather than a statement
   of current implementation status

For benchmark, prompt, runtime-memory-evolution, or CI work, also read:

- `docs/design/memory_evolution_runtime.md`
- `docs/design/memory_evolution_runtime_benchmark.md`
- `docs/design/latent_graph_simulator.md`
- `docs/design/prompt_contracts.md`
- `docs/design/semantic_temporal_retrieval.md`
- `docs/development/benchmark_certification.md`
- `docs/development/static_tooling.md`

Do not claim that a planned behavior exists merely because it appears in a
plan. Confirm it in production code and tests. Conversely, update current-state
documentation when an implementation change makes it stale.

## Non-Negotiable Architecture

Preserve all of the following distinctions:

- raw transcript, semantic, episodic, user-context, execution-plan, and
  solver/search memory are separate logical domains
- candidate state is distinct from committed state
- structural graph state is distinct from versioned belief/status overlays
- the persistent execution graph is distinct from task-local solver graphs
- memory routing is distinct from retrieval planning
- raw observations are distinct from derived memory-evolution projections
- provider transport validation is distinct from domain-semantic validation
- production retrieval is isolated from benchmark oracle data
- framework-neutral contracts are isolated from host-specific integrations

Do not:

- store dynamic beliefs directly on structural graph nodes
- let model output mutate committed truth without explicit validation
- write speculative content directly into semantic or user memory
- let adapters or integrations bypass validators or store contracts
- replace typed public or persisted schemas with untyped dictionary blobs
- delete event history to represent revision or backtracking
- collapse execution and solver graphs into one generic graph
- import simulator oracle state into production extraction or retrieval
- couple core logic to Hermes, OpenClaw, LangGraph, AutoGen, OpenAI Agents, or
  another particular harness

Unknown, ambiguous, insufficient-evidence, and needs-test outcomes are valid.
The system must fail closed rather than require a model to guess.

## Package Ownership

Application code lives under `memorii/memorii/`. Follow the current repository
layout and existing ownership boundaries; do not enforce a historical exact
file tree.

- `memorii.domain`: canonical domain schemas, enums, stable IDs, and graph
  records; no persistence or framework-specific behavior
- `memorii.core.memory_plane`: canonical storage model, transactions, atomic
  filesystem persistence, visibility, and unit-of-work behavior
- `memorii.core.memory_evolution`: extraction, validation, entity resolution,
  claim lifecycle, temporal semantics, graph projection, retrieval, and durable
  evolution operations
- `memorii.core.provider`: production-facing composition for ingestion,
  retrieval, prefetch, tool dispatch, and work-state projection
- `memorii.core.benchmark`: benchmark contracts, fixtures, metrics, artifacts,
  calibration, reproducibility, simulator logic, and runtime evaluation
- `memorii.core.prompts`: prompt registry, ownership, schema parity, semantic
  validation, and runtime manifests
- `memorii.core.promotion`: distinct promotion assessment and execution
  contracts
- `memorii.core.execution`, `memorii.core.solver`, `memorii.core.retrieval`,
  `memorii.core.consolidation`, `memorii.core.belief`, and neighboring packages:
  their named orchestration responsibilities
- `memorii.stores`: persistence interfaces and implementations for the legacy
  domain stores
- `memorii.adapters`: framework-neutral adapter contracts and translations
- `memorii.integrations`: host-facing integrations built only on canonical
  Memorii contracts
- `memorii.api`: framework-neutral API models and service boundaries
- `memorii.tools`: thin command-line entry points and benchmark-suite
  composition; reusable business logic belongs in `memorii.core`
- `memorii.prompts`: package-owned, versioned prompt assets

Prefer cohesive modules with explicit owners. Before adding a helper, search for
an existing contract or implementation. Avoid relocation facades, circular
imports, monolithic services, magic registries, and framework-heavy base
classes.

## Types And Serialization

Use Python 3.11+ syntax, explicit type hints, Pydantic models for public and
persisted contracts, enums for closed vocabularies, and protocols for pluggable
components. Small immutable internal values may use dataclasses when that is
clearer.

Persisted and public objects must have:

- explicit schemas and deterministic reconstruction
- JSON serialization or an explicit serialization adapter
- stable IDs rather than reliance on Python object identity
- graph references by ID rather than object pointer
- fail-closed parsing for unknown enum and lifecycle values

Keep typed models intact until the serialization boundary. If storage and
domain representations differ, define both explicitly. Do not use casts or raw
nested dictionaries to avoid modeling a contract.

## Memory Evolution And Provider Contracts

`ProviderMemoryService` is the production-facing memory composition boundary.
`build_provider_memory_service_from_env(...)` is the environment-aware
composition root; direct construction must remain deterministic and must not
read process configuration implicitly.

All public provider mutations require a non-empty, caller-supplied stable
`operation_id`. Retries must reuse the same ID. Turn synchronization derives
stable child IDs from its parent delivery ID. Replay must remain idempotent
across process restarts and partial-turn recovery.

Evolution operations must preserve:

- durable operation state when a persistent memory-plane store is configured
- transactional source-event and projection commits
- process-safe, crash-atomic filesystem updates
- checksum and incomplete-batch validation that fails closed
- fenced leases with renewal during active work
- bounded stale recovery and an explicit terminal exhaustion state
- token fencing so an expired worker cannot commit after ownership is lost
- sanitized persisted failures while full exceptions remain in operational logs

Extraction outcomes must distinguish success, partial output, abstention,
provider failure, schema failure, and hybrid fallback. Failed extraction must
never commit memory. Deferred or ineligible modalities may remain audit
evidence but cannot become active truth.

Model-produced extraction or decisions pass through separate stages:

1. prompt output-schema validation
2. provider transport parsing
3. typed domain-semantic validation
4. provenance and evidence validation
5. lifecycle or candidate/commit policy
6. transactional persistence

Prompt schemas and provider transport models must accept the same JSON value
space. Cross-field semantics belong in the explicit post-transport validation
stage rather than being hidden in one transport model.

## Retrieval And Oracle Isolation

Retrieval must be typed, scoped, temporal, lifecycle-aware, and intentional.
Natural-language analyzers propose typed constraints; server-owned state
resolves them. Ambiguous entity, scope, temporal, or graph constraints must
abstain or fail closed rather than broaden silently.

Use half-open validity intervals, `[valid_from, valid_to)`, consistently. Keep
query-time temporal relevance separate from stored lifecycle state. Production
code may not import benchmark simulator/oracle modules or use expected IDs,
hidden graph items, or judge votes to affect extraction, retrieval, or output.
Runtime benchmark alignment may use oracle data only after the production
decision and graph projection have completed.

## Prompts And Model Output

Prompts that can affect memory or solver state must be evidence-bounded,
versioned, package-owned, registered to an explicit owner, structured, and
abstention-aware. Require evidence identifiers or spans where applicable and
represent missing evidence explicitly.

Never trust a model's self-report of compliance. Validate schema, structure,
provenance, evidence coverage, allowed identifiers, and domain semantics in
code. Do not make a single fluent model answer committed solver or memory truth.

Prompt conformance fixtures belong in tests, not in `memorii.core`. Changing a
prompt, output schema, generation setting, retry policy, or gate threshold
changes evaluation identity and requires the corresponding contract and
artifact updates.

## Benchmark Evidence

Keep these evidence classes distinct:

- deterministic unit and contract tests establish code-level invariants
- fake-oracle dry runs validate plumbing, artifacts, alignment, judges, and
  calibration without measuring provider quality
- live runtime evaluation measures the memory component for an exact clean
  revision under declared seeds, replicates, families, and statistical policy
- no current benchmark establishes agent policy quality, tool-use strategy,
  recovery behavior, or end-to-end task improvement

Never report fake-oracle execution as provider success. Runtime reports must
preserve execution source, provider health, source revision, source-tree
fingerprint, prompt hash, model identity, generation settings, attempt count,
and retry budget where the artifact schema requires them.

The engineering-hardening change is complete only when every row in
`docs/plans/engineering_hardening_closure_matrix.md` has implementation
coverage and the exact reviewed revision passes every declared deterministic
gate plus the revision-bound live statistical gate. A live result from another
commit, a dirty tree, mixed run identities, or post-run threshold/prompt tuning
is not certification.

Runtime memory evolution being default-on inside provider ingestion does not
mean Memorii is ready for agent-system integration. Agent integration remains
out of scope until a separate agent-level evaluation and operational rollback
design are approved, as specified in
`docs/plans/agent_integration_readiness.md`.

## Testing And Required Checks

Tests should be proportional to the changed contract and must cover failure
modes, not only successful examples. Preserve tests for idempotent replay,
atomic visibility, process contention, corruption, lease fencing, stale
recovery, scope isolation, prompt parity, oracle isolation, lifecycle behavior,
temporal retrieval, artifact validation, and deterministic reconstruction when
touching those areas.

From `memorii/`, install development dependencies with:

```bash
python -m pip install -e '.[dev]'
```

Run the normal local gates:

```bash
python -W error -m pytest tests/unit -p no:cacheprovider
python -m ruff check memorii tests
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Follow `docs/development/static_tooling.md` for wheel/package verification and
deterministic benchmark smoke commands. Follow
`docs/development/benchmark_certification.md` for exact-revision live
certification. Do not run live provider gates casually: they consume credentials
and are meaningful only with the declared source and run identity.

The normal PR checks are `Unit Tests` and `Benchmark Contracts`. The unit job
also runs Ruff, scoped Pyright, and wheel smoke verification. The live runtime
statistical gate is an explicit candidate-acceptance check for the exact PR head,
not a substitute for deterministic PR checks.

Do not weaken warnings, test selection, schema validation, family coverage,
sample-size requirements, retry accounting, or statistical thresholds merely
to make a gate pass. Fix the implementation or document and approve an actual
contract change.

## Change Workflow

Before editing:

1. Read the controlling documents and nearby tests.
2. Identify the production composition root and every affected public,
   persistence, prompt, artifact, and CLI boundary.
3. Search for existing types and helpers before adding new ones.
4. Inspect the working tree and preserve unrelated user changes.

While implementing:

1. Change canonical schemas and contracts first when the behavior requires it.
2. Update validators, orchestration, and persistence without bypass paths.
3. Keep adapters and CLI modules thin.
4. Add adversarial and failure-mode tests alongside happy-path tests.
5. Update current-state documentation in the same change.
6. Run the relevant deterministic gates and report anything that could not be
   verified.

Do not opportunistically redesign adjacent systems. If a choice would alter a
core semantic contract and the controlling documents do not resolve it, stop
and surface the ambiguity. Otherwise implement the narrowest complete behavior
consistent with the architecture.

## Completion Standard

A change is complete only when:

- implementation, types, tests, prompts, artifacts, and current-state docs
  agree
- invalid input and unsupported states fail explicitly and safely
- provenance, scope, replay, transaction, and lifecycle invariants remain intact
- deterministic reconstruction and serialization remain stable where required
- relevant local and CI-equivalent checks pass
- any required external or live certification is identified separately and is
  bound to the exact reviewed revision

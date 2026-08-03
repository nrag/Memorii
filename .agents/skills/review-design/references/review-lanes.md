# Review Lanes

## Contents

1. Problem, scope, and requirements
2. Internal consistency and architecture
3. Data, lifecycle, transactions, and recovery
4. Security, failure, and operations
5. Verification, evidence, and implementation readiness

## 1. Problem, Scope, And Requirements

Check:

- concrete problem, actors, current behavior, desired behavior, and success
- explicit scope, exclusions, and non-goals
- stable requirement IDs and traceable sources
- measurable acceptance criteria
- public, persisted, security, operational, negative, and unsupported behavior
- contradictions or hidden assumptions

## 2. Internal Consistency And Architecture

Check:

- consistent terminology, diagrams, prose, schemas, and examples
- complete state transitions and error behavior
- assumptions not presented as guarantees
- canonical ownership and extension points
- typed public and persisted contracts
- absence of bypasses, duplicate truth, circular dependencies, hidden global
  state, unowned abstractions, framework leakage, or dictionary contracts
- preservation of all universal Memorii invariants in `AGENTS.md`
- complete identity ledger, behavioral durable names, exact typed traceability
  and migration exceptions, and no planning/evidence coordinate used as an
  executable or durable identity

For declared languages and generated authority, check:

- normative source selection
- executable versus declarative boundary
- closed grammar or projection
- aliases, inheritance, nesting, metadata, ordering, duplicates, and versions
- complete source-to-artifact authority chain

## 3. Data, Lifecycle, Transactions, And Recovery

Check applicable:

- identifiers, ownership, creation, validation, visibility, revision,
  supersession, retention, provenance, reconstruction, serialization, replay,
  and temporal validity
- candidate versus committed state
- atomicity, idempotency, retries, duplicate delivery, partial failure, crash
  recovery, stale work, leases, fencing, ordering, concurrent mutation,
  consistency, restart, rollback, and terminal exhaustion

Require explicit behavior between every pair of material steps. “Retry” is not
sufficient without identity, ownership, visibility, and side effects.

## 4. Security, Failure, And Operations

Check applicable:

- authentication, authorization, caller identity, tenant isolation, provenance,
  evidence validation, model-output validation, privacy, sensitive data, audit,
  and privilege boundaries
- malformed, unsupported, ambiguous, insufficient-evidence, provider, schema,
  semantic, partial-output, timeout, exhaustion, dependency, corruption,
  incompatible-version, and interruption behavior
- deployment, flags, migration, backfill, rollback, mixed-version behavior,
  observability, metrics, logs, alerts, capacity, and recovery procedures

Unknown and insufficient-evidence outcomes must remain valid where applicable.
Fail closed where guessing would mutate truth, broaden scope, or cross trust.

## 5. Verification, Evidence, And Implementation Readiness

Check:

- verification method and clear failure signal for every material requirement
- appropriate unit, property, contract, integration, process, concurrency,
  migration, rollback, end-to-end, benchmark, live, or operational level
- mocks preserve the contract being tested
- deterministic, fake-oracle, live-runtime, agent-level, and operational
  evidence remain distinct
- exact revision and environment identity where required
- evidence maturity is not overstated
- affected components, owners, sequencing, compatibility, migration, rollout,
  rollback, verification, deferrals, and unresolved decisions are explicit
- field-aware identity enforcement is owned by a required gate and proves both
  rejection mutations and the fixed legitimate-name corpus

A design is not implementation-ready when an implementer must invent a material
semantic choice or reconstruct an unstated authority boundary.

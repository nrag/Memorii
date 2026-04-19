# Implementation Rules

## Hard constraints
1. The full spec in `docs/memorii_spec.md` is the source of truth.
2. If the spec and code conflict, update code to match spec unless explicitly instructed otherwise.
3. Do not simplify architecture to move faster.
4. Do not silently defer core invariants.
5. Do not invent new core memory domains without updating the spec.
6. Do not use one database abstraction as a substitute for the domain model.
7. Do not mix raw transcript with semantic memory.
8. Do not mix execution state with solver-search state.
9. Do not make the model the source of truth for committed state.
10. Do not commit unsupported beliefs or writebacks.

## Commit gating
A memory update must pass:
- schema validation
- provenance validation
- candidate/committed policy checks
- type-specific validation
- optional solver verification if model-derived

## Resume guarantees
Resuming a task must reconstruct:
- active frontier
- unresolved work items
- suspended and reopenable branches
- last committed overlay state
- unresolved questions
- unexplained observations

## Adapter guarantees
Adapters may translate.
Adapters may not bypass validation.
Adapters may not mutate storage directly.
Adapters may not alter core semantics.

## If unsure
Choose the more explicit, typed, and auditable design.
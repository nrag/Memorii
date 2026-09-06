# Validated Canonical Closure Implementation Acceptance Matrix

## Approved Design Baseline

- Candidate lock:
  `1e314415930bd43b176b50c28ba8f8b8250a7fa5d959758bc60acd47fc47b2ca`
- Design outcome: `Approved with follow-ups`.
- Follow-up sources: `DREV-003` and `DREV-004` as reconciled in
  `delta-v12-coordinator-addendum.md`.
- Evidence boundary: design/reference evidence is not production, CI, live, or
  operational proof.

## Lifecycle And Authority Acceptance

| Behavior | Required implementation proof | Failure signal |
| --- | --- | --- |
| Disabled selection | No evidence capability, index charge, or process reservation; existing full path and outcomes remain authoritative | Any closure lookup authority, charged index, reservation, or changed outcome |
| Initial process refusal | Fifth simultaneous 16 MiB request uses the full path before staging; release permits later reacquisition | Partial authority, retained charge, or failed reacquisition |
| Sealed-only authority | Lookup before seal and admission after seal fail closed; no fallback transition occurs after a successful substitution | Pre-seal hit, post-seal mutation, or mixed enabled/fallback operation |
| Five-coordinate scope | Tenant, operation, generation, fence, and writer are independently mutated and rejected | Any foreign or stale coordinate hits |
| Capacity boundaries | Exact and one-over tests for 512 roots, 2 MiB root bytes, 32,768 paths, 16 MiB operation charge, and 64 MiB process reservation | Wrong boundary acceptance, partial authority, eviction, or global retention |
| Close idempotence | Repeated close is a no-op in `sealed`, `closing`, and `closed`; it never revives authority or releases twice | Exception, second release, new lease, or changed terminal outcome |
| Linearizable leases | Deterministic lookup/close/release interleavings block new leases after close and release once after the final lease drains | Post-close lease, premature release, leak, or underflow |
| Terminal release | Completion, validation failure, capacity refusal, exception, cancellation, and retry release exactly once | Reservation leak, double release, or outcome mutation |
| Production ownership | `ProviderMemoryService` reaches `ProviderIngestionCoordinator.ingest` and `_run_semantic_ingestion` through typed handoffs at every mapped root and trigger | Invented owner, ambient authority, missing handoff, or test-only reachability |
| Writer admission | Two writers and writer retry each perform fresh local admission while preserving durable identity and replay | Sibling evidence reuse or changed durable/replay result |

## Observability Acceptance

| Behavior | Required implementation proof | Failure signal |
| --- | --- | --- |
| Closed modes | Only `disabled_full_path`, `capacity_rejected_full_path`, and `enabled` are accepted | Unknown or content-bearing mode |
| Closed terminal reasons | Only feature-disabled, capacity-refused, completed, validation-failed, exception, and cancelled values are accepted | Arbitrary string, identifier, or exception text |
| Typed counters | Counts and byte values are nonnegative bounded integers; `released` is boolean | Wrong type, negative value, overflow, or semantic payload |
| Reason latching | The first terminal cause is immutable through `closing`; final lease drain emits that cause | Cancellation/exception reported as completion |
| Reason precedence | Repeated close cannot replace the first cause; validation failure, exception, and cancellation precedence is deterministic | Cause changes with call order or retry |
| Exact terminal cardinality | Disabled, initial/staging rejection, completion, validation failure, exception, cancellation, retry, and duplicate close attempt exactly one terminal snapshot | Missing or duplicate snapshot |
| Content privacy | Sentinel bytes, values, paths, digests, bindings, profiles, schemas, types, domains, scope coordinates, capability data, and exception messages appear in neither keys nor values | Any sentinel appears in emitted data |
| Sink outcomes | Only `recorded` or `unavailable`; unavailable leaves validation, retry, persistence, replay, durable state, and public output byte-identical | Unknown sink result or changed product outcome |
| Sink isolation | No arbitrary host callback executes inside closure authority | Host callback gains authority or blocks durable correctness |

## Performance And Promise Acceptance

| Behavior | Required implementation proof | Failure signal |
| --- | --- | --- |
| Digest reduction | Production-bound exact matrix records at least 90 percent fewer repeated full digest computations | Reduction below 90 percent or unbound counter source |
| Canonical equivalence | Enabled, disabled, and rejected modes produce identical canonical bytes, digests, promise projection, replay, writer admissions, and durable outcomes | Any semantic or byte difference |
| Independent trust | Semantic validators and every writer admission still execute in all modes | Skipped validator or writer trust event |
| Capacity accounting | Reported charge matches the approved packed representation and frozen limits | Unbounded growth, hidden global cache, or mismatched accounting |

## Evidence Maturity Gates

- Deterministic implementation tests must prove the matrix against the exact
  implementation revision.
- Focused production-root integration tests must prove every mapped trigger and
  composition root uses real production owners; fixtures remain thin.
- Mutation cells must fail when a typed handoff, authority coordinate, owner,
  lifecycle transition, privacy rule, or terminal emission is removed.
- CI enforcement is claimed only after a required workflow runs the revision-
  bound matrix and rejects an intentional failure.
- Live or operational claims require separate revision-bound evidence and are
  not prerequisites for code-level implementation completion unless the future
  implementation WorkPlan explicitly promotes them.

## Escalation Boundary

Return to `$build-design` only if implementation requires changing public or
persisted schemas, canonical identity, trust ownership, capacity limits,
rollback semantics, or the approved production composition model. Do not reopen
design for ordinary type definitions, synchronization mechanics, test fixture
construction, metric enum implementation, or CI wiring that satisfies this
matrix.

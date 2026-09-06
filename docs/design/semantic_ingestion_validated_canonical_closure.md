# Semantic Ingestion Validated Canonical Closure

Status: Draft feasibility candidate

WorkPlan: `docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/design.plan.md`

## Problem And Target

The V3 graph path performs `42,955` full digest computations for `238` unique
canonical identities, including `42,717` repeated computations. Exact-root reuse
left `27,346` repeats because equal nested contracts occur beneath different
parents. This design must leave at most `4,272` repeated and `4,510` total full
computations while preserving canonical bytes, semantic validation, writer
admission, and fail-closed authority.

## Constraints And Non-Goals

Canonical identity retains its exact embedded codec/profile/schema binding and
exact bytes; no ambient caller hint is authoritative. Typed contracts remain the
owner handoff, only validated content reaches persistence, and each writer remains
an independent trust event. The design does not change digest algorithms,
serialization, persisted or public schemas, replay meaning, semantic validators,
or writer policy. It introduces no global cache or caller-supplied proof.

## Contracts

The canonical codec emits one immutable internal result:

```python
CanonicalCodecResult[T](
    value: T,
    binding: CanonicalBinding,
    canonical_bytes: bytes,
    root_digest: Digest,
    member_index: CanonicalMemberIndex,
)
```

The member index is produced during the same typed encode/decode traversal. Each
entry contains the traversal-issued field/container path, exact byte span,
binding, and schema/type/domain. A receiver may independently verify those spans,
but may not discover membership by searching for equal bytes: `VCC-EXP-001A`
found `135` ambiguous equal-byte member locations among `285` links. The index
never serializes the typed value a second time.

After semantic validation, the validator seals:

```python
ValidatedCanonicalClosure(
    scope: CanonicalValidationScope,
    codec_result: CanonicalCodecResult[object],
    validated_members: CanonicalMemberEvidenceIndex,
)
```

Each member evidence entry binds exact root and member bytes, span, path,
codec/profile/schema, type/domain, digest, operation, generation, fence, and
completed validation stages. Only the canonical codec/validator owner can create
it. It is private, ephemeral, non-serializable, and unavailable to models,
adapters, callers, or persisted records.

The normative lifecycle and observability projection is
`docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/canonical-closure-operation-contract-v1.json`.
`ProviderMemoryService` owns one private `CanonicalClosureScopeOwner` per
operation. Its repository-owned `CanonicalClosureReservationCoordinator`
atomically reserves the complete 16 MiB operation envelope before staging.
Only codec and semantic validation may stage and seal. Seal issues an object-
identity capability bound to tenant, operation, generation, fence, and writer;
its constructor and issuer are absent from public, persisted, adapter, provider,
prompt, and model-controlled surfaces. Arbitrary trusted-process code execution
is outside this capability threat model.

The closed states are `new`, `disabled`, `reserved`, `staging`, `sealed`,
`closing`, `rejected`, and `closed`. Disabled selection creates no reservation
or capability. Staged entries cannot be looked up. Any limit refusal discards
all staged state, releases exactly once, emits a rejected terminal snapshot, and
runs the full path. Only `staging -> sealed` exposes a capability; no later
admission or transition to fallback is allowed.

A sealed lookup verifies issuer identity and every scope coordinate, then
returns an immutable slice lease. Close blocks new leases, enters `closing`
while leases exist, and clears authority and releases exactly once when the
final lease drains. Pre-seal validation failure, exception, and cancellation
discard staging and release exactly once. Repeated close is idempotent; lease or
reservation underflow is a contract violation rather than silent fallback.

Stable values retain exact content identity across equivalent runs. Values that
bind an operation, generation, fence, writer, or fresh publication retain exact
identity only within that scope and must receive a fresh validated digest when
the scope changes. Cross-run evidence for those values compares the complete
structural/owner coordinate, never substitutes an old digest. A specialized
digest owner, currently `BootstrapGraphTerminalPublicationIntentV3`, supplies its
own validation provenance; a generic digest-body reconstruction may not replace
that owner rule.

## Cross-Root Reuse

A downstream owner consumes the exact certified child slice. Parent encoding
writes its envelope once and copies or streams that child while recording the
new span. This creates a new parent root without reconstructing or hashing an
unchanged child. Reuse requires every binding and required validation stage to
match; digest equality alone is insufficient.

Typed handoffs carry value and closure together through provider ingestion,
normalization, repository/atomic-store, V3 graph host, and graph-plan composition.
An owner that changes a value creates a new result and generation. Semantic,
lifecycle, provenance, cardinality, bounds, closure, and policy validators still
run; only proven reconstruction and digest work is skipped.

## Writer Boundary

Every persistence writer opens a fresh writer-local admission scope and validates
the exact bytes it commits. Upstream or sibling-writer evidence cannot waive that
admission. Byte construction may be reused only within the writer invocation.

## Coherence And Capacity

Results are immutable, and scope destruction invalidates all entries. Evidence
cannot cross operations, generations, fences, tenants, processes, or writer
invocations. Roots are retained once. Repeated type, domain, profile, and codec
identifiers are interned, and typed paths use a per-root segment trie; member
records contain fixed-width span, trie-node, type-ID, stage, and digest references
rather than repeated strings. Frozen limits are `512` roots, `2 MiB` per root,
`32,768` member paths, `16 MiB` total root-plus-index charge per operation, and
`64 MiB` process reservations. The packed representation uses a `4,096`-byte
operation header, `128`-byte root records, `64`-byte member records, `16`-byte
trie nodes, `4`-byte intern lengths, and `32`-byte binding records. Exhaustion
declines new evidence and follows the existing full path; it does not evict
authority or retain a global cache.

The 16 MiB envelope is a conservative process reservation, not a promised
allocation. Reservation precedes staging and lookup begins only after seal, so
capacity cannot switch an operation to the full path after substitution. Four
reservations may coexist under the 64 MiB process ceiling; a fifth is rejected
before allocation. Root, path, and charge refusal during staging rejects the
entire closure. Every terminal path releases a held reservation exactly once.

## Failure, Compatibility, And Rollback

Substituted bytes, wrong binding/type/domain/path, malformed spans, stale scope,
foreign operation or writer, and missing stages never hit. Invalid codec-index
relationships are rejected. Persisted bytes, digests, schemas, APIs, and replay
stay unchanged. A private switch restores the current full-validation path
without migration.

`ProviderMemoryService` owns a private
`CanonicalClosureObservabilityDispatcher`. Exactly once at each terminal
transition it submits a typed snapshot containing only mode, terminal reason,
roots, member paths, lookups, hits, misses, capacity refusals, peak charged
bytes, reserved bytes, and a released flag. It excludes canonical bytes,
values, paths, digests, bindings, profile/schema/type/domain names, scope
coordinates, capability material, and exception messages.

The repository-owned sink returns `recorded` or `unavailable`; unavailability
cannot change validation, persistence, replay, durable state, or public outcome.
No arbitrary host callback executes inside the closure authority boundary.

AMENDED 2026-08-27 by user decision: the substitution is enabled by default for every verified runtime; the construction-trust-domain condition is removed, an explicit `canonical_evidence_enabled=False` constructor request is the only disabled path, and rollback remains migration-free through that switch.

The switch is selected privately before operation scope creation and is immutable
for that operation. Disabled mode creates no evidence capability or allocation
and executes the existing full-validation path. Capacity rejection occurs before
partial authority and selects the same disabled behavior. Closing a scope clears
all entries, charge, and capability; a later operation cannot accept the prior
capability.

The executable reference `canonical_closure_lifecycle_reference.py` consumes
the normative operation contract and covers disabled allocation, exact and
over-limit capacity, concurrent reservation, sealed-only capability exposure,
forged and stale scopes, lookup/close lease ordering, exact-once release,
terminal metric cardinality, privacy allowlisting, and sink unavailability.
This is local reference evidence; production, CI, live, and operational
evidence remain implementation milestones.

## Verification And Candidate State

The candidate must prove byte-identical member reconstruction; unambiguous paths
for maps, sequences, tagged values, and repeated values; the frozen 90 percent
gate; exact promise equality; complete semantic-validator execution; independent
writer admissions; adversarial fail-closed behavior; bounded capacity; and
enabled/disabled byte and replay equivalence.

`VCC-EXP-002` establishes reference feasibility for the performance gate: full
digest computations fall from `42,955` to `176`, repeated computations fall from
`42,717` to `46` (`99.8923` percent), all independent boundary and writer work is
retained, and the promise projection is exactly equal. The specialized terminal
publication-intent digest owner remains entirely on its concrete full path.

`VCC-EXP-003` closes all security attack cells but disproves naive path metadata:
the measured corpus would charge `18,890,284` bytes against a `16 MiB` operation
ceiling. `VCC-EXP-003B` resolves that finding: deterministic compact metadata is
`1,834,984` bytes and total operation charge is `13,484,545`, leaving `3,292,671`
bytes headroom under the unchanged ceiling. All capacity limits above are frozen.

`VCC-EXP-004` closes rollback and external-promise equivalence. Enabled mode uses
`176` full computations plus `42,779` exact substitutions; disabled and capacity-
fallback modes use all `42,955` full computations. Their digest-return ledger,
promise projection, canonical bytes, replay-visible outcomes, writer admissions,
and production output identity are equal. Rollback requires no migration.

This remediated design requires a new freeze and independent review.
`VCC-EXP-001A` rejected post-hoc path discovery, and
`VCC-EXP-001B` proved traversal-issued paths and exact canonical bytes across the
full `238`-identity family under the operation-aware identity contract.
`VCC-EXP-002` passed the 90 percent counterfactual. Security, compact-index
capacity, and rollback/equivalence experiments pass. Candidate identity freeze
and independent reviews by `spec_auditor`,
`correctness_reviewer`, and `test_reviewer` remain required.

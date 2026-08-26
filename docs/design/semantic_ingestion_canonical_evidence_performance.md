# Canonical Evidence Performance Contract

## Scope and authority

This contract defines the evidence boundary for the canonical-evidence performance
comparison. It does not implement an arena in production. The only acceptance
command is `canonical_evidence_artifact_validator.py`; latency records are
evidence inputs, never acceptance by themselves.

The workload is the frozen standard fixture. A run has exactly eight ordered,
fresh process-isolated cells: `direct/memory`, `direct/jsonl`,
`factory/memory`, `factory/jsonl`, `filesystem/memory`, `filesystem/jsonl`,
and `hermes/memory`, `hermes/jsonl`. Each cell constructs through one of the
four public roots (`ProviderMemoryService`, `build_provider_memory_service_from_env`,
`build_filesystem_provider`, or `HermesMemoryProvider`), supplies explicit
memory or JSONL storage, deterministic authenticated ingress, and built-in
local graph authority, then calls public `sync_event` once. Private
`_from_scenario_test_host` construction and imports from unit-test modules are
forbidden.

The evidence fixture, rather than a new production seam, must execute the four
public roots with only `host_bootstrap_capability`,
`host_bootstrap_material_verifier`, `source_normalization_host_bundle_builder`,
and authenticated ingress. It must not inject a graph builder or invoke the
scenario-only constructor. The built-in local capability's default graph
authority must carry the call through `sync_event`, `_ingest_event`, `ingest`,
and `_run_semantic_ingestion`, with no evidence-only or fallback terminal.
The authorized remediation replaces that blocked fixture seam with one future
production-owned boundary in `memorii.core.semantic_ingestion.production_authority`:
`build_verified_production_host_authority` accepts a `HostBootstrapCapability`, a
`HostBootstrapMaterialVerifier`, and server time; it calls the existing
`load_bootstrap_material_presentation` and `HostBootstrapMaterialVerifier.verify`
with `required_trust_domain="production"`; and it returns only a frozen
`VerifiedProductionHostAuthority` or no value. The bundle carries the verified
capability, verifier, authenticated ingress resolver, and a factory-issued
`ProductionAuthorityCompositionReceipt`. It has no graph-builder field.

The future explicit `verified_production_host_authority` argument is threaded
unchanged through `ProviderMemoryService`, `build_provider_memory_service_from_env`,
`build_filesystem_provider`, and `HermesMemoryProvider`. Existing arguments and
default behavior remain unchanged when it is absent. If the explicit path is
selected, absence, malformed material, verifier failure, non-production trust,
or an incomplete typed bundle fails closed before semantic ingestion. The factory
is the sole production owner of verification; the fixture cannot create a bundle,
call a verifier, normalize source bytes, build a graph, or call a private bridge.

The receipt is ephemeral evidence, not a persisted public product value. Its
typed owner has fields `schema`, `receipt_digest`, `authority_digest`,
`verified_material_digest`, `verification_digest`, `trust_domain`, `factory_symbol`,
`verification_symbol`, `root_symbol`, `root`, `backend`, `operation_identity`,
`source_revision`, and `trace_identity`. The factory creates it only after
verification; the selected root binds root/backend/operation; diagnostic tracing
binds `trace_identity` to the ordered production frames. The fixture may only
serialize the returned receipt. It must reject a receipt that is absent, has a
different typed identity, or disagrees with its trace.

Diagnostic capture (not latency capture) installs a production-only scoped trace
receiver. For every cell it records module-qualified symbol and source path in
this exact order: `build_verified_production_host_authority`, the existing
`HostBootstrapMaterialVerifier.verify`, the selected root constructor, public
`ProviderMemoryService.sync_event`, private `ProviderMemoryService._ingest_event`,
`ProviderIngestionCoordinator.ingest`, and
`ProviderIngestionCoordinator._run_semantic_ingestion`. Every path must be a
locked `memorii/memorii` production source path. The validator requires exactly
that ordered trace, matching production-issued receipt, and equal diagnostic and
latency production/evidence identity for each of all eight cells. Missing,
reordered, wrong-path, omitted-symbol, private/test/scenario, or fabricated
receipt/trace input fails closed. The future production implementation—not the
fixture—emits frames and receipt.

The fixture's executable allowlist is intentionally thin: parse pinned inputs,
create temporary storage, select root/backend, call the production factory,
call public `sync_event` once, supervise the child, and record child measurements
and returned receipts. Its lock-bound AST validator rejects imports from test or
scenario ownership, private construction calls, graph-builder injection,
scenario material, duplicated production/verifier/receipt definitions, and
source-normalization, digest, graph, or persistence ownership. Current bounded
feasibility remains blocked until this future production boundary is implemented;
the runner therefore continues to fail closed. No baseline or candidate is
created and production code is unchanged.

## Future arena lifecycle (specified, not implemented)

`ProviderMemoryService.sync_event` is the future owner: it creates the arena
and nonce before its existing `_ingest_event` call. The future explicit
`canonical_evidence_arena` and `arena_nonce` parameters propagate through the
existing `ProviderMemoryService._ingest_event`,
`ProviderIngestionCoordinator.ingest`, and
`ProviderIngestionCoordinator._run_semantic_ingestion` callsites; they are not
optional and have no default or fallback. There is no existing canonical-
evidence retry branch. In particular,
`ProviderIngestionCoordinator._admit_with_writer_retry` is an existing
writer-admission retry, not an arena retry, and must neither receive nor
recreate arena state. The future same-invocation retry loop is owned exactly by
`ProviderMemoryService.sync_event` and reuses its nonce; a later `sync_event`
call creates a new nonce. Existing durable-recovery branches in
`_run_semantic_ingestion` reload durable state only and never synthesize an
arena. A future `sync_event` `finally` tears the arena down on success, error,
and cancellation. Concurrent invocations receive separate explicit arena
parameters and arena-local capacity counters; capacity fallback is passed to
the canonical codec owner and records no full digest. This is specified, not
implemented; DREV-004 closure is exact design binding, not runtime proof.

The original baseline-first implementation gate is replaced by a
requirements-first evidence gate following the measured production defect and
the external decision recorded on 2026-08-16. Arena implementation is
authorized only against the source-bound uncached diagnostic manifest recorded
by the linked debugging WorkPlan at
`docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/uncached-diagnostic-v1.json`,
whose required SHA-256 is
`8ad48951e303263807b9a5187a257aa0c6fd27e0c8844668e576a9faafda5191`.
That diagnostic evidence is not an M3.1 baseline and cannot by itself certify
performance. Post-implementation evidence must prove every semantic,
coherence, capacity, lifecycle, persistence, and performance requirement below
before M3.1 can close.

The arena has immutable capacity limits: at most 128 entries, at most 65,536
canonical bytes in one entry, and at most 1,048,576 charged bytes in one
operation. Entry charge is
`len(canonical_contract_bytes) + len(domain_bytes) + 512`; the fixed charge
covers key and provenance metadata and is part of deterministic admission,
not an estimate of Python RSS. A process-wide coordinator permits at most
67,108,864 reserved bytes across active arenas. Each active full arena reserves
its complete per-operation budget before accepting entries and returns it in
an idempotent `finally` teardown. If the process reservation, entry count,
single-entry limit, or operation charge is unavailable, the value executes the
complete legacy validation path. The arena never evicts, overwrites, negatively
caches, deep-copies a validated model, or shares values between operations.
The existing 134,217,728-byte candidate RSS-delta threshold remains the
independent bound on actual process memory.

## Measurement contract

A sample contains eight cells in the stated order. Diagnostic mode is
`diagnostic_profiled_non_latency`: the child profiles the canonical digest
code object while executing only its cell's `sync_event`; latency mode is
`latency_unprofiled` and contains no profiling. The child reports its own
`RUSAGE_SELF`; the parent performs only process timeout supervision. The parent
uses bounded `Queue.get(timeout=...)`, never `Queue.empty`, and refuses to
overwrite evidence.

Before runner capture or validator processing, the shared lock resolver verifies
the candidate lock hash and every consumed authority: design, verification
contract, binding map, performance schema, standard-fixture schema, fixture
manifest, production-source manifest, event schema, receipt schema, runner,
recipe, validator, and the resolver itself. No runner or validator reads a
mutable authority path directly after that resolution. The fixture manifest is
itself lock-pinned before traversal; every listed fixture must then exist and
match its manifest digest.

Each cell records its trigger receipt, operation identity, source revision,
and counters: `eligible`, `unique`, `repeated`, per-identity full-digest
counts, `direct_non_eligible`, and `global`. Candidate cells additionally
record the arena nonce. The validator requires `eligible = unique + repeated`,
`unique = len(per_identity)`, candidate full-digest count exactly one for every
eligible unique identity (never zero or greater than one), `global >= eligible
+ direct_non_eligible`, global at most 1000 per cell, and the required
`aggregate_global = sum(cell.global)` at most 8000.

`source_revision` and `implementation_identity` must both equal the verified
SHA-256 of the locked production-source manifest; arbitrary or mismatched
identity values are rejected. Baseline and candidate records must have distinct implementation identities,
the same frozen workload and locked executable identities, and separately
linked diagnostic and latency records. Candidate performance thresholds are
median reduction at least 0.75, p95/median at most 1.5, and child RSS delta at
most 134217728 bytes.

## Evidence maturity

This revision specifies and locally verifies fixture tooling only. It does not
claim a valid baseline, production arena implementation, CI enforcement, or
approval. The invalid historical baseline remains unchanged.

## Requirements-first post-implementation evidence

The source-bound uncached diagnostic is causal evidence only. Candidate
acceptance requires executable proof of all of the following:

- identical eligible content in one operation performs one full digest and
  later uses reuse only through a factory-private arena nonce and previously
  produced canonical bytes
- concrete type, profile revision, codec revision, validation domain, canonical
  bytes, or nonce differences miss; caller-claimed digests never authorize hits
- invalid, partial, failed, oversized, saturated, persisted-and-reloaded, or
  provenance-changing values execute complete validation and never populate a
  reusable success entry
- entry, item-byte, operation-charge, and process-reservation boundaries reject
  the first value above each frozen limit without eviction or semantic change
- concurrent operations cannot read each other's values and cannot exceed the
  aggregate reservation; success, error, cancellation, and retry exhaustion
  release all reservations in `finally`
- hit, miss, disabled, and saturated paths produce byte-identical persisted
  records, terminal outcomes, replay identities, durable effects, and receipts
- production counters satisfy one full digest per eligible unique identity,
  no zero-digest acceptance, and no skipped provenance, authorization,
  lifecycle, transaction, persistence, replay, receipt, or observability stage
- the identical source-bound diagnostic operation materially reduces redundant
  digest calls and elapsed time, then the bounded eight-cell production smoke
  proves all public roots and backends before any larger certification run

M3.1 remains open until its final approval unit explicitly reconciles the
requirements-first evidence with the original statistical contract. No
diagnostic, unit proof, smoke result, or candidate-only timing may silently be
reported as the historical baseline.

## DREV-001 proof contract remediation

The lock-pinned positive AST grammar enumerates every accepted fixture import,
alias, declaration, node, call, assignment/dataflow edge, and the one public
`service.sync_event` call. Unknown or private production paths, direct
coordinator/ingest terminals, test/scenario material, injected authority, and
extra business logic reject.

Diagnostic cells carry closed typed `production_receipt` and ordered
`production_trace` objects. Only the future production factory issues the
receipt; the fixture serializes it. The validator recomputes receipt/trace
identity, requires seven exact source-locked frames, and requires latency to
bind the diagnostic-cell hash plus root/backend/order/operation/receipt/trace/
source/evidence identities. Design vectors are never acceptance evidence.

Capture remains blocked until the pending `production_authority.py` source
exists and hashes in a `capture_ready` manifest. System `shasum` checks the
expected frozen lock and launcher before the launcher executes; it then checks
itself and lock-declared resolver, runner, static validator, and artifact
validator before Python imports. After source-frame/source-byte verification,
the launcher starts the lock-pinned static AST grammar validator in isolated
mode against that exact locked runner. A verifier-interpreter invocation is
only static validation, never runner-target execution. Grammar rejection exits
64 before either capture lock and before the runner target is invoked. Python
resolution is not a trust root. The external caller retains the frozen launcher
hash. Post-implementation proof
must mutate missing caller, omitted authority, failed verifier/no bundle,
reordered/substituted trace, fabricated receipt, source path, latency linkage,
and explicitly prove absent authority preserves legacy defaults.

## DREV-001/002 regression closure

The positive fixture is an exact four-statement cell template, not a count of
syntax nodes. It has one declared factory assignment, one root construction
that receives that exact authority only as `verified_production_host_authority`,
one reachable non-looped public `sync_event`, and one production result return.
Branches, loops, exception blocks, context blocks, comprehensions, lambdas,
dynamic attribute access, aliases, subscript/attribute writes, direct terminal
calls, and fabricated definitions are rejected. Production imports occur only
after the child preflight; the runner has no top-level production import.

A receipt digest is an integrity checksum, not proof of issuance. The future
production receipt is a typed object with private construction and a
non-serializable opaque operation token. Before serialization, the child checks
the exact receipt type and object identity of that token against the
production-issued trace. Serialized receipt and trace projections exclude the
token and do not claim cryptographic issuance or an `origin_validated` flag.
Acceptance additionally requires a two-stage external anchor: an execution
lock is frozen before capture, then the trusted externally hashed launcher
atomically creates an O_EXCL result-lock manifest containing exact diagnostic
and latency paths/hashes plus the execution-lock hash and immediately prints
the result-lock SHA-256. The evidence ledger records that expected hash.
Before Python imports records, the launcher verifies `--expected-result-lock-sha256`
against the result-lock bytes; Python then verifies schema, lock linkage, and
record contents. A regenerated receipt, trace, records, execution lock, and
result lock fails against the previously printed expected result-lock hash.

The positive AST grammar covers the entire runner module and every function
body. The runner is declarative outside the sole four-statement cell template;
it has no helper or main control flow. Any factory source replacement, branch,
loop, exception/context block, side effect, direct terminal, alias, or receipt/
trace fabrication anywhere rejects. Capture-ready source transition requires
every mapped production factory, verifier, and trace frame to have a real path
and SHA-256 both in the source map and source manifest; unresolved placeholders
fail before Python and are never capture-ready. The fixture manifest is first
validated against its standard schema, then traversed only under the repository
root. Receipt and event projections have closed schemas and reject wrong
discriminators or extra properties.

The sole fixture `FunctionDef` has an exact signature: no decorators,
parameter or return annotations, type parameters, defaults or keyword defaults,
variadic or keyword-only parameters, type comments, async form, generator, or
other signature metadata. The static proof mutates `@print`, annotations,
function and assignment type comments, module type-ignore directives, defaults,
async/generator form, and type parameters when the parser supports them; each
must reject. The isolated repinned capture harness separately proves the three
type-comment/type-ignore forms run the verifier interpreter, then exit 64 with
no runner-target sentinel and no execution or result lock.

The production-source manifest owns the canonical `source_frames` inventory.
At `capture_ready` it has exactly one `{symbol,path,sha256}` entry per required
frame symbol and exactly one prehashed source entry per required path. Its
frame map must equal the binding map byte-for-value; every frame digest must
equal its source entry and every source must be referenced. Duplicate,
omitted, extra, wrong-owner, sentinel, fake-digest, and all-symbols-to-one-
valid-source substitutions reject in both the external pre-import gate and the
shared Python resolver/validator before capture or record acceptance.

The source manifest maps each exact root-specific frame symbol to its production
path and SHA-256 once capture is ready; a wrong-but-locked path is rejected.
The pre-import launcher derives both repository root and virtualenv interpreter
from its own path, clears `PYTHONPATH`, invokes Python with `-I`, and hashes all
lock-declared executable/schema authorities before imports. Pending production
authority blocks capture before Python, while validator self-tests remain
available.

## Whole-design remediation: canonical arena and production capture

`CanonicalEvidenceArena` is the future private, invocation-local owner in
`memorii.core.semantic_ingestion.canonical_evidence_arena`.  It is created only
by the public `ProviderMemoryService.sync_event` invocation owner and is passed
as an explicit private context value through `_ingest_event`, `ingest`, and
`_run_semantic_ingestion`.  The Pydantic context key is a private object,
`_CANONICAL_EVIDENCE_ARENA_CONTEXT_KEY`, not a string; every codec/validator
owner must propagate the same `ValidationInfo.context` mapping to nested
validation. Missing, malformed, copied, stale, or wrong-type context fails
closed to the legacy path.

The arena key is the tuple `(canonical_contract_bytes, concrete_contract_type,
profile_revision, codec_revision, domain)`. `canonical_contract_bytes` are the
canonical encoded contract body before any digest is calculated: neither a
claimed digest nor an envelope participates, so the key cannot recursively
depend on its own digest. An entry stores immutable copies of those bytes and
a typed `ValidatedCanonicalEvidenceResult` containing the exact validated
contract/result plus validation provenance. The canonical encoder and typed
validator remain their existing canonical owners; the arena neither decodes
raw dictionaries nor owns a second codec.

Only a content-addressed typed contract reached recursively more than once
within one `sync_event` operation is eligible. On first encounter the existing
complete validation pipeline executes unchanged (canonical bytes, decode,
transport/domain, provenance, lifecycle, and persistence admission); only a
successful completed result is cached. A hit returns the semantically identical
typed value, but still runs every downstream provenance, lifecycle, transaction,
and persistence step. Invalid input, validator/codec error, non-eligible
content, context failure, or capacity fallback executes the legacy route with
identical bytes, error, persistence, and durable effects. Capacity is bounded
per arena; after saturation it never evicts or reuses an entry and records an
explicit diagnostic fallback. `sync_event` clears the arena in `finally` on
return, error, and cancellation. Same-invocation retry reuses its nonce and
arena; recovery reloads durable state and never recreates an arena; later and
concurrent invocations use distinct arenas/nonces.

The future production-owned `CanonicalEvidenceCaptureSupervisor` is the sole
non-test caller used by the executable matrix. It selects the eight ordered
cells, creates one isolated child process per cell, obtains the opaque
production-issued bundle from `build_verified_production_host_authority`,
constructs the selected public root, calls public `sync_event` once, and emits
only the production result, terminal durable-effect receipt, and diagnostic
trace. Its trace must include the terminal `_run_semantic_ingestion` return and
the durable terminal identity; source-only, fixture-only, fallback, or
evidence-only traces are invalid. This pending symbol is capture-ready only
when production source frames and all four root arguments exist; until then the
runner must fail closed.

The opaque `VerifiedProductionHostAuthority` may be supplied only by the
production factory. Each of the four roots rejects the bundle if it is supplied
with any legacy authority, resolver, graph-builder, scenario, or verifier
argument; bundle substitution, invalid/expired material, and verifier failure
reject before `sync_event`. Absence of the bundle preserves existing defaults.
Fixtures cannot issue, deserialize into, or compose the bundle.

## Frozen comparison authority and schedule

The lock-pinned concrete `comparison-schedule-authority-v1.json`, validated by
`comparison-authority-schema-v1.json`, is the sole PRE-CAPTURE authority. It
binds the shared fixture, runner/tool, workload, environment, algorithm,
seeded matrix and execution order, warmup/discard policy, fresh-child policy,
and exactly retained ordinals `0..19`. The external launcher consumes and hashes
it before either capture; each execution lock and record repeats only that
authority hash and exact ordinal list. Warmups and discarded samples are not
serializable performance samples.

The POST-CAPTURE `comparison-result-binding-schema-v1.json` binds the two
captures only after both result locks exist. The launcher O_EXCL-creates that
instance from distinct baseline and candidate authority, implementation,
source, execution-lock, result-lock, diagnostic-record, and latency-record
identities, prints its SHA-256, and the caller supplies that expected hash
before Python imports either record. The validator resolves each side against
its own immutable authority and the shared schedule exactly once; crossed,
swapped, stale, same-id, mixed-fixture/environment/schedule, or warmup/order
drift rejects. Every cell contains exactly 20 `wall_ns` values for retained
ordinals `0..19`; p95 is nearest-rank `sorted[ceil(.95*n)-1]`, so twenty values
select index 18. Equality and threshold tests use retained samples only.

Every cell and its result lock also contain a typed terminal durable-effect
receipt: operation, root, backend, source revision, transaction-or-memory
durable identity, effect digest, successful terminal status, replay identity,
and no-duplicate count one. It is bound to the production trace and operation.
Source-only, persistence-failed, replay-duplicate, absent, mismatched, or
non-terminal receipts reject for all eight cells.

Post-implementation gates cover every root: invalid/expired ingress, verifier
failure, opaque-bundle substitution, legacy co-injection, absence/default
preservation, same-invocation nonce reuse, later-invocation nonce separation,
error/cancellation `finally` teardown, concurrent isolation, capacity fallback,
JSONL restart/recovery without duplicate durable effects, and all eight
terminal production traces/durable receipts. These are implementation gates,
not current production claims.

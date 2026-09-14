# Authenticated Observation Retrieval

Work type: implementation milestone. Status: readiness; depends on ledger append/replay.
Parent: ../implementation.plan.md. Governing design: semantic_ingestion_observation.md
public registry, snapshot and cohort sections; architecture SIA31320-32030.
Matrix: ../../engineering-closure/observation-query-validation-matrix.md.

## Verified Gap And Owners

ProviderMemoryService has no authenticated graph-observation/page entrypoint.
Ordinary MemoryEvolutionRetrievalRuntime is a separate API, not this integration.
Historical graph_observation_authority/cursor helpers use unregistered v1 models
and signatures. Profile3 public_contracts and snapshot_contracts are distinct
closed native owners; cursor signature uses registered graph_observation_cursor
purpose and memorii.graph-observation.cursor.v3 domain. Do not reuse v1 wire.
Root directly verified these distinctions; Spark's generic retrieval route and
its claimed authorize(auth) signature are rejected as inaccurate mapping.

Trusted host resolves opaque ingress into authenticated context. Scope/seed/
purpose/current policy are authorized before any seed/index/snapshot access.
The registered context/decision/policy/cohort/cursor bind the protected inputs;
no caller key or requested digest grants authority. Both graph and ingestion-time
attestation purposes require full per-page authorization and exact failure taxonomy.

First page takes one read_write_snapshot; all graph/replay/reference/source/group/
projection/ledger lookup derives from those records. Existing atomic graph_state_
snapshot and reference_integrity_snapshot call live reads and cannot be directly
used to assemble a coherent new snapshot. ProjectionHistoryRepository's current/
historical temporal and trust selectors likewise read their bound plane; reuse
through an explicitly detached read owner or extract exact read logic without
falling back to live state. Never merge temporal and trust histories.

Cohort closure follows exact source-finalization and operation/group records until
membership stops expanding, then bound graph/reference edges for boundary records.
Unknown/nonterminal/missing/duplicate/mixed-scope seeds fail without disclosure.
No provenance index, oracle or text reconstruction can certify membership.

Retain an immutable typed server snapshot, unguessable token, sorted complete
stream, exact context/decision/cohort and creation/deadline. Continuations authorize
before token lookup, authenticate profile3 cursor, require fresh full-write revision
matches snapshot+cursor, validate request and predecessor/position, and emit only
next contiguous slice. Expiry, eviction/restart, revocation and any intervening
canonical batch follow exact invalid/stale/revoked mapping, with no partial page.

## Verification And Scope

Approved matrix includes all record kinds, operation/source closure, empty and
multi-page streams, independent temporal/trust histories, attestation purpose,
revocation/outage, tampering, restart, and prelookup zero-read denial. Exercise
real production store/codec and isolated configured signing keys. Final projection
and snapshot evidence must use the actual activated append path. Independent
structural comparator and checkpoint publication retain separate parent obligations;
do not call those complete from a page-helper result.

## Next Action

Finish readiness mapping of registered authorization and snapshot read ownership
while activation and native ledger persistence are implemented.

## Registered Authority Consultation

Independent spec consultation confirms no new policy decision: construct profile3
context/decision/page policy using exact registered public root self-digest rules;
legacy authorizer grant/time/scope checks are reusable concepts, not legacy digest
constructors. Context/request binding is retained in snapshot/cursor; decision
uses its declared final field set. The protected registered codec selects the
fixed schema/binding, never GraphObservationService or caller input.

The opaque cursor string carries the existing complete fixed artifact envelope's
strict UTF-8 text directly. No new prefix, base64 or second envelope. Continuation
strictly encodes UTF-8, applies protected bounds, existing envelope/history/body/
integrity verification and requires exactly the profile3 cursor root and fixed
signature purpose/domain. This preserves the approved wire contract and rejects
legacy v1 cursors. Authorize first, then decode/token/snapshot checks. No external
wire-format or production-key decision is needed.

# Persisted Ingestion-Time Attestation Producer — Owner-Decision Packet

Status: draft for owner decision (2026-09-11, HEAD 1558b0aa). No canonical,
registry, or production bytes changed by this document. Substrate: the
existing unapproved proposal in this directory (see proposal.md readiness
findings; design.plan.md records the packet as active, not
implementation-ready).

## Objective

Make ProviderMemoryService.observe_ingestion_time_attestations
(memorii/core/provider/service.py:669-681) return real pages. The public wire
is already built and registered: SourceRetentionTimeAttestation /
TransactionGroupCommitTimeAttestation (graph_ingestion_time_contracts.py:24-63),
the request/snapshot/page/cursor models (graph_observation_public_contracts.py),
and the paging protocol are byte-frozen. Only the persisted producer is
missing; today ingestion_time_input fails closed
(graph_observation_materialization.py:153-162).

## The Authority Question

What retained artifact can prove "these events happened before time T"? A
paging-time clock sample cannot: "an authorization-time clock sample cannot
establish the atomic store snapshot's system time" (continuation-runtime
review correction) and observation uses "no live-clock resampling". The timed
snapshot (MemoryPlaneTimedWriteSnapshot, commit a7c6a9ed) proves only snapshot
existence at T, not event time before T. SIA answers normatively: source
retention creates its attestation atomically with the immutable source record;
group commit creates its attestation atomically with the graph delta, event
batch, dedupe state, trace and outcome, binding the server-clock identity
(docs/design/semantic_ingestion_architecture.md:31071-31077), read back through
a revision-bound read (:31079-31080). The credible authority is a
store-committed attestation sealed in the same CAS as the write it times.

## Options (recommended first)

1. **Recommended — store-persisted seal minted at admission/group-commit CAS
   under the protected clock; deny rather than guess when absent.** admit_source
   publishes the retention attestation with retained_at from the protected
   server clock; group commit samples start/commit instants inside the winning
   CAS; a CAS loser writes no attestation; reload returns original artifacts.
   Readers select only registered attestation artifacts whose result-bound
   digest is reachable from the resolved source finalization/group entry;
   any join anomaly denies the cohort. Strongest and SIA-conformant; touches
   persisted schemas and the producer clock path; must discharge the prior
   packet's ITP-01..04 ledger and coordinator readiness findings (proposal.md
   sections on admission anchoring, acyclic batch digest, publish_admitted_source
   enumeration, protected clock at raw-source construction, digest-chain
   coverage).
2. **Observation-time snapshot-existence attestation under the timed-snapshot
   clock.** No persisted schema change, but it cannot truthfully populate
   retained_at/started/committed times — it would falsely authenticate event
   times. Honest use requires a new weaker artifact kind and cursor enum
   extension. Rejected unless the owner wants a deliberately weaker claim.
3. **External trusted-time authority (TSA/Roughtime).** Strongest external
   verifiability; adds a network trust dependency in/after the write CAS,
   breaks fail-closed/offline posture, contradicts SIA's server-clock binding
   and the approved production/acceptance witness split. Recommended: never
   in the production write path; acceptance-layer countersigning only.

## What Option 1 changes

Persisted schemas: CanonicalSourceTerminalOutcomeCore/Record schema-2 fields
(source_result_schema_version, source_retention_attestation_digest);
BootstrapGraphGroupCommitResultCoreV3 schema-3
(transaction_group_commit_attestation_digest, required when committed, explicit
null when noncommitting) threaded through the full digest chain. New immutable
execution-record members carrying registered canonical bytes. Registry
regeneration coordinated with the already-pending publication refresh that
adds ProjectionObservationIdentity.v1. Paging/public contracts: none. Producer
clock: core/provider/ingestion.py:397-409 currently uses the caller event
timestamp for retained_at — a single protected clock must be routed through
source construction, and exact redelivery must reuse the winner's material.

## Fail-closed rules

Authorization before any read or clock authority; cohort unavailability maps
to non-disclosing denied; CAS loser writes nothing; no synthetic attestations
for legacy stores; join/tamper anomalies deny; no live-clock resampling;
read-only snapshot stores deny timed authority outright.

## Compatibility

No retroactive attestations: legacy schema bytes and field exclusions remain
exact; existing stores simply have no attestations (semantics per open
decision 2). Orphan admission members remain evidence but are not
cohort-reachable until terminal binding.

## Open decisions for the owner

1. Granularity: per-source-retention + per-group-commit seals (SIA/prior
   packet) vs one coarser per-write-revision seal.
2. Absent-seal semantics for stores written before the producer exists:
   empty cohort (valid empty first page) vs typed denial everywhere.
3. Retention/compaction of immutable attestation execution records: keep
   forever or compact.
4. External trusted time: confirm Option 3 is excluded from the production
   write path permanently.
5. Sequencing: fix the provider clock gap as a prerequisite milestone or in
   the same campaign; whether the schema-2/3 migration rides the same
   publication refresh as ProjectionObservationIdentity.v1.

## Verification obligations

Discharge ITP-01..04 and the implementation proof matrix from the prior
packet (fake-clock/identity substitution, retry/CAS-race/crash-between-
construction-and-write/lost-ack, JSONL reopen, one-field substitution and
partial-publication failpoints, legacy decoding), extending the
activated-provider/JSONL reopen harness pattern. Feasibility precedes
implementation; independent review before promotion.

## Status note (2026-09-11)

Placed before the owner with recommendations (Option 1; typed denial for
legacy data; per-source + per-group granularity; production-write exclusion
of external time). Implementation remains blocked until the owner decides;
recommendations are not approvals.

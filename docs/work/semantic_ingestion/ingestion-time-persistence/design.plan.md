# Ingestion-Time Attestation Persistence

- Work ID: semantic_ingestion/ingestion-time-persistence
- Work type: design
- Status: active design — owner-approved direction (2026-09-11, owner-decision.md);
  proposal revised to an implementation-ready contract pending feasibility proof
- Coordinator: root
- Parent WorkPlan: ../engineering-closure/implementation.plan.md
- Related WorkPlans: ../acceptance-authority-successor/design.plan.md
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md` section 5.6; `graph_ingestion_time_contracts.py`; `atomic_store.py`; `contracts.py`
- Expected outputs: implementation-ready atomic attestation binding design.

## Objective

Persist one source-retention attestation and, for each committed group, one
transaction-group commit attestation in the same immutable closure as their
source/group result. Detached observation may then read registered raw artifacts
without fabricating a clock or accepting an unattached companion record.

## Owner Decision (2026-09-11)

The owner approved Option 1: store-persisted seals minted at admission and
group-commit CAS under the protected clock; typed denial for legacy/unsealed
cohorts; per-source-retention plus per-group-commit granularity; external
trusted-time authorities permanently excluded from the production write path
(acceptance-layer countersigning only). Administrative defaults adopted with
the approval: immutable attestation execution records retained without
compaction; the provider clock gap fix proceeds as a prerequisite milestone;
the schema-2/3 migration rides the same publication refresh as
ProjectionObservationIdentity.v1. Full text: owner-decision.md.

## Requirements Ledger

| ID | Requirement | Evidence required |
| --- | --- | --- |
| ITP-01 | A server-owned protected clock identity and instants bind every persisted attestation. | Fake-clock, identity substitution, UTC/type boundary tests. |
| ITP-02 | Retry, CAS loss, lost acknowledgement and reopen return the original bytes; no second time is minted. | In-memory/JSONL retry and reopen proof. |
| ITP-03 | Attestation digests are members of the durable source/group result preimages and same-CAS generation. | One-field substitution and partial-publication failpoints. |
| ITP-04 | Existing legacy result bytes remain readable unchanged; v3 attestation-bearing results are explicit. | Historical reader and migration refusal tests. |

## Scope And Non-Goals

Included: contracts, storage members, atomic write/reload joins, and future
detached selection. Excluded: clock policy values, production clock
provisioning, cohort projection, paging, and actual producer implementation.

## Progress And Next Action

2026-09-08: root confirmed no current producer for either attestation and no
durable start/clock binding. Proposal drafted; coordinator found unresolved
admission anchoring, batch-digest cycle and source-result preimage/version
coverage. The draft was not implementation-ready and changed no canonical or
production bytes.

2026-09-08 coordinator discovery: provider retention currently uses the caller's
event timestamp, not a protected server clock (core/provider/ingestion.py:396).

2026-09-11: owner approved Option 1 with the administrative defaults recorded
above (owner-decision.md).

2026-09-11 post-decision revision: all five coordinator readiness findings are
resolved in proposal.md with code-inspected contracts — admission anchor
(retained source record + seal member in one admission CAS; schema-2 terminal
binds back via `source_retention_attestation_digest`), acyclic
`committed_batch_digest` (verified against
`SemanticMemoryEventBatch.source_event_batch_digest`,
event_replay.py:410-462/1124-1192), complete seal-minting enumeration
(`publish_admitted_source`, `admit_source`, group CAS; reload and legacy paths
mint nothing), protected-clock routing and recovery-before-derivation
redelivery, and complete schema-2/3 digest-chain coverage preserving legacy
schema-1 and group schema-1/2 bytes. Two open questions remain for design
review (SIA admission-request-digest alignment; clock-identity provisioning
surface). The normative reader rule is typed denial for legacy/unsealed
cohorts. Implementation milestones are ordered M0 clock fix (prerequisite), M1
schemas, M2 minting, M3 reader.

- Next action: feasibility proof of the revised contract on the real backend
  (per owner-decision.md Next), then independent design review before
  implementation.

## M0 Clock Fix Record (2026-09-11)

M0 is complete: closed IngestionTimeClock owner
(memorii/core/memory_evolution/ingestion_time_clock.py) required at the
ProviderIngestionCoordinator constructor (omission raises); one protected
sample supplies the retained record timestamp and governance
received_at/retained_at on both provider paths (caller delivery timestamp is
delivery identity only); recovery-before-derivation redelivery reuses the
winner's bytes through the new authorized replay_retained_source accessor and
never resamples (guard-deletion validated). Coordinator-run gates: 66 clock/
provider/factory cases, Ruff, scoped Pyright clean; two recovery-suite
failures proven pre-existing at clean HEAD. Recorded deviations: class name
is ProviderIngestionCoordinator (no ProviderIngestionService exists);
service/factory keep an optional clock defaulting to the composed protected
clock (fail-closed enforced at the coordinator constructor; no wall-clock or
caller-timestamp default remains); store sharing realized via clock.now_utc
as the store now_provider; seal-member recovery reuse lands with M2. The
projection-record materialization regression also completed: 19 passed in
4560.79s at 5927e10a. Next: M1 persisted schemas.

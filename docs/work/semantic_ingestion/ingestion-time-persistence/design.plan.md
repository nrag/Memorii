# Ingestion-Time Attestation Persistence

- Work ID: semantic_ingestion/ingestion-time-persistence
- Work type: design
- Status: active
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
durable start/clock binding. Proposal drafted; coordinator found unresolved admission anchoring, batch-digest
cycle and source-result preimage/version coverage. Next: reconstruct these exact
atomic binding contracts before feasibility proof and frozen review. The draft
is not implementation-ready and has not changed canonical or production bytes.

2026-09-08 coordinator discovery: provider retention currently uses the caller's
event timestamp, not a protected server clock. Proposal corrects the earlier
assumption and records the required authorization/retry/clock path. Next action
remains reconstructing the complete admission binding before producer edits.

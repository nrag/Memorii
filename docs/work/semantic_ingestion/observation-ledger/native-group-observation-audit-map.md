# Native Group Observation Audit Map

`build_bootstrap_group_observation_audit()` is a pure, pre-CAS construction
leaf. Its authoritative inputs are the sealed
`BootstrapGraphGroupCommitRequestV3`, the exact live `GraphStateSnapshot`, the
fully materialized canonical graph after-records, and the prior/next typed
`ReferenceEdgeLedgerSnapshot` values from the same atomic attempt. It also
receives the exact `PlanningCommitValues` that materialized the records and
re-materializes each accepted record intent before accepting its after-record.

The helper constructs source introductions only from accepted fact-effect
`observation_mention_bindings`. Each binding must retain exactly one admission;
the selected candidate's logical entity, entity revision, and already-canonical
type-evidence IDs are copied verbatim. Operation introductions and terminal
outcomes use each retained reduction's `native_compilation.operation_input`
planning-construction authority; operation spans are limited to the evidence
and mention spans owned by that specific operation member. Terminal
execution-manifest identity is the request's
`pre_execution_manifest_identity.identity_digest`.

The graph delta uses the current snapshot's sealed `GraphReadSet` digest,
canonical `SnapshotGraphRecord` envelopes, and only the exact suffix from the
next reference ledger after the prior ledger. Its write-set digest commits the
sorted actual `GraphRecordMutation` values. Retained operation read authority
remains distinct: a later owned group may correctly construct against a current
snapshot advanced by an earlier group in the same attempt. A noncommitting group produces only
operation introduction/outcome records; it rejects graph records or a reference
ledger advance. The helper does not assign observation-head coordinates, write
storage, or establish a production caller. The atomic group-CAS owner must
persist and reload its returned values as one authenticated closure.

# Capability Monitor Binding Preflight

Baseline: 191826cd3afb38bf605a337a71d576063b3bae5e, authorized dirty tree.
Status: incomplete mapping, not implementation or freeze evidence.

The Spark consultation did not establish the requested status/CAS chain and
did not write its assigned artifact. Coordinator rejects its claims that
source normalization noncommit is an authoritative capability demotion, that
Hermes is the sole production root, or that planning line references are
literal schema names to search. Those claims must not guide implementation.

Coordinator-verified current facts:

- `graph_records.GraphReadSetExtension` admits the `capability_status`
  dependency kind with record keys and partition versions; an enum value alone
  does not supply a status owner or demotion transaction.
- `contracts.OperationCapabilityExecutionBinding` carries status revision and
  digest, but a scoped search finds no `capability_status` usage in the native
  group store or bootstrap graph modules.
- `source_normalization_authority.CapabilityRegistrySnapshot` is the existing
  V2 entries/revision/digest schema. Preserve its historical bytes; the richer
  certification and freshness authority needs explicit composition.
- `SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3`
  revalidates the complete request and every operation reduction, authorizes
  current control/lease/writer state, derives graph and observation successors,
  then publishes the group through its shared CAS. The monitor must join that
  transaction's status preconditions, not merely reject a future source run.

Queries: `rg -n capability_status memorii/memorii/core -g '*.py'`;
`rg -n 'GraphReadSetExtension|effective_read_set' memorii/memorii/core/memory_evolution/atomic_store.py`.
Inspected owners: graph_records.py:550, source_normalization_authority.py:134,
atomic_store.py:11408 and its nested write closure.

Next mapping obligation: prove the exact status-record read-set insertion and
shared conditional-write precondition path, then select a real server-owned
scheduled trigger. Neither path is currently established by this preflight.
The separate monitor-validation-matrix.md defines the required behavioral proof.

Further coordinator trace: native group CAS at atomic_store.py:11864 currently
checks operation-control and writer record digests, absent fanout records and
canonical event preconditions. It has no capability-status precondition.
The preceding read-set check at :11482 permits an owned prefix of earlier groups
from the same attempt; a future capability-status check must remain mandatory
even when that graph-only prefix optimization is valid. Status demotion cannot
be represented merely by changing a source's operation-control revision.

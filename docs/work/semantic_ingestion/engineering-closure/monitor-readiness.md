# Monitor And Status Authority Preflight

Baseline: 191826cd3afb38bf605a337a71d576063b3bae5e. Coordinator read-only
inspection; this is an ownership map, not implementation evidence.

The governing architecture section 5.6.1 requires a server-scheduled monitor,
immutable evidence windows, independently recomputed cluster statistics,
time-uniform bounds, freshness checks even without traffic, and atomic
active-to-evidence-only transitions. Recovery requires explicit activation;
fresh labels alone never reactivate a demoted capability.

Existing `core/semantic_ingestion/authorization.py` provides same-store
source-bound authority transitions and CAS checks. Its authority scope is
`source:<source_id>:<source_digest>`, and its states are active/revoked. It is
not the missing per-capability registry and must not be relabeled as one.
`SemanticAuthorizationReadSet` binds deployment authorization, active epoch,
policy and egress coordinates. `atomic_store.py` installs/replaces these
authority records through existing writer and CAS boundaries.

The production contract currently contains capability status revision/digest
fields in `contracts.py` and a `capability_status` graph read-set category.
Those fields alone do not implement the design's `CertifiedSemanticCapability`
or `CapabilityRegistrySnapshot`. The monitor must persist a shared capability
status record and ensure every group commit conflicts on that exact record;
iterating over source authority records is not an atomic substitute.

Current-code clarification: `source_normalization_authority.py` does own a
`CapabilityRegistrySnapshot` with revision, entries and digest. Each entry only
contains capability ID/fingerprint; it has no certified status/freshness or
status-record read set. The earlier statement concerns the full monitoring
authority, not absence of every snapshot type. SIA's later V2 snapshot inventory
also needs reconciliation with section 835's richer activation schema before
changing persisted snapshot fields. Preserve existing V2 bytes; do not silently
replace this owner or assume an identical name proves equivalent authority.

Before writing package 4, trace the graph read-set extension through planning,
commit and replay to select the existing canonical storage owner. Implement
policy/freshness and scheduled trigger integration together with that status
record. The linked numeric design governs computed bounds and alpha-spent
representation; substantive thresholds and time limits remain supplied policy
inputs. No default policy or automatic recovery is authorized by this map.

Required failure families: missing policy/gate/observation, duplicate clusters,
unknown metric, sequential implementation mismatch, insufficient samples,
stale labels with healthy canaries, pause/outage grace expiry, zero traffic,
clock boundaries, simultaneous commit/demotion, and attempted automatic
reactivation. The final proof must use the production scheduler/control path
and exact CAS authority, not only a standalone monitor function.

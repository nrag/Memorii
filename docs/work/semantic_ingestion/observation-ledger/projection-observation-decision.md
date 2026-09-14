# Claim Projection Observation Decision

Status: approved by the user on 2026-09-07. Separate temporal and trust
observations, each retaining its own history, are the accepted public direction.
Technical design review and implementation remain required; no runtime completion
is implied by this decision.

## Demonstrated Boundary

SIA ObservedClaimProjection declares one selected_assertion_ids tuple, one
contested_assertion_ids tuple, one system_interval and transition_reason, with
both temporal and trust policy fingerprints. ExpectedClaimProjection mirrors
that shape. Neither shape identifies which projection authority supplies its
selection or how independently advancing histories combine.

Production has two validated authorities: TemporalProjectionRecord and
TrustProjectionRecord, each with its own generation, certificate and pointer
history. projection_history.py:6150-6198 can alter temporal selection after
trust arbitration. current_temporal/current_trust and their historical variants
select their respective histories independently. Equal projection_id does not
establish equal winners, publication time or transition reason.

Choosing one authority silently drops the other; manufacturing a merged result
would make the observation adapter a new arbitration owner. This is not a
registry encoding choice or permission to sign artifacts.

## Recommended Public Contract

Expose separate temporal and trust projection records in the observation stream.
Replace claim_projection with temporal_claim_projection and
trust_claim_projection in the new observation schema. Preserve all historical
reader routes; do not relabel existing bytes as the new schema.

Each new payload has exactly:

- observation_id: the profile-bound content address of projection kind,
  repository, generation digest and native projection digest;
- projection: the complete owner-validated TemporalProjectionRecord or
  TrustProjectionRecord respectively, with its original native digest;
- generation_digest: the selected native generation digest;
- publication_pointer: the complete owner-validated active/history pointer
  of the corresponding kind;
- successor_publication_pointer: the immediately following pointer of the
  same kind, or null when no successor exists in the snapshot;
- boundary: the cohort-derived flag;
- record_digest: the new registered observed-body digest.

These are two concrete models, not an untyped payload. Their stream primary
key is observation_id. The native logical projection_id remains unchanged
inside projection. Publication coordinates retain both time and sequence, so
two same-time publications are distinguishable without inventing a nonempty
wall-clock interval. The pointer's publication_kind supplies its own transition
reason; the adapter does not invent a combined reason.

Current and historical views select each kind through its existing canonical
selector at the same detached store snapshot and requested system time.
Lineage returns the reachable generation history for each kind. A trust-only
advance must not rewrite the temporal record, or vice versa. Expected graph
contracts and the independent comparator receive corresponding separate typed
records and compare both. No new winner-selection algorithm is introduced.

The alternative is to retain one combined public projection and specify a new
canonical composition rule, including disagreement, policy migration, temporal
partition boundaries and equal-time publications. That requires a separately
persisted/verified composition authority; the observation adapter cannot infer it.

## Independent Work And Validation

Regardless of this choice, native group CAS must add the existing canonical
projection-history publication authority, and retrieval must use snapshot-only
validators. These are implementation gaps, not choices about user policy.

Required evidence for the recommended shape: differing temporal/trust winners,
trust-only and temporal-only advances, same-time different-sequence history,
current/historical/lineage selection, missing/swapped generation and pointer,
native commit plus restart, and complete independent comparison of both kinds.
An unchanged graph with a changed projection pointer must invalidate affected
observation continuation authority. The concrete snapshot/cursor revision
binding must include projection history before implementation can close paging.

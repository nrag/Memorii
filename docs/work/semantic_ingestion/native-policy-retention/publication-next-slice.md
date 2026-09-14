# Native Projection Publication: Next Slice Feasibility

Status: read-only construction map. This does not activate native projection,
aggregate, checkpoint, registry, observation-ledger, or retrieval behavior.

## Examined Native Path

The actual accepted V3 caller remains `ProviderMemoryService.sync_event` through
`AtomicStoreBootstrapGraphRepositoryV3.commit_or_reload` to
`SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3`
(`memorii/memorii/core/memory_evolution/atomic_store.py:11409`).  The group CAS
already derives these authoritative values before its one
`conditionally_write_records` call:

* `prior_replay_state` and `next_replay_state`, the canonical
  `SemanticGraphDelta`, and `canonical_event_batch` from the actual
  materialized graph records (`atomic_store.py:11617-11818`);
* `before_graph`, `after_graph`, `committed_at`, the group transaction ID, each
  accepted reduction's `effective_read_set_digest`, and writer epoch; and
* the retained construction authority at
  `item.reduction.native_compilation.operation_input.planning_construction_authority`.
  Its `arbitration_policy_bundle` is now the typed
  `SemanticArbitrationPolicyBundle`, not an ambient policy lookup
  (`semantic_ingestion/contracts.py:9124-9205`, `9226-9271`,
  `11240-11389`).

The last carrier is nested in every reduction which the group method already
revalidates. It is not a caller-supplied publication argument. For a new
accepted publication, the CAS must additionally require that every accepted
operation has a non-null construction authority and bundle, and that their
`bundle_digest` values are identical. The latter is the single bundle needed
by one temporal/trust projection generation; legacy omission remains valid
only for reload of an existing primary, which returns before preparation.

## Reuse Decision

The full `_semantic_event_authority_updates` method cannot be called by the V3
group path. Its contract is an `AtomicGenerationRequest` and, for an event,
`CommittedGroupAtomicWriteRequest`; it derives generic
`SemanticReplayAuthorityMemberBinding` values from `request.members` and can
reconstruct them through generic control generations
(`atomic_store.py:12735-13085`, `5200-5285`). V3 persists its own group
primary/fanout/effect grammar and has no corresponding generic members.
Constructing those members merely to enter this helper would invent native
replay-member semantics.

The committed projection portion is reusable without that translation. Extract
a private V3-neutral preparation helper owned by `atomic_store.py`, using the
same canonical owners it already invokes in the generic path:

1. `projection_records_from_replay_state(next_replay_state, ...)`
   (`projection_history.py:5583`) derives both projection kinds from the
   actual replay state.
2. `ProjectionHistoryRepository.prepare(ProjectionCommitRequest(...))`
   (`projection_history.py:2746`) returns the immutable generation, pointer,
   certificate, history, replay-binding, record, and CAS-precondition closure.
3. `PolicyMigrationRepository.prepare_write_catch_up(...)`
   (`policy_migration.py:1074`) returns the related migration records and
   preconditions.
4. `create_replay_checkpoint` and `advance_semantic_replay_authority` retain
   the prepared `ProjectionPublication.replay_bindings` in the aggregate and
   checkpoint (`atomic_store.py:13044-13085`).

This is reuse of canonical projection and replay authority construction, not
reuse of the generic request/member grammar. The existing native event batch
is a real `SemanticEventInputBatch`; no synthetic event or placeholder member
is needed.

## Exact Inputs And Dispatch

The extracted helper needs these typed inputs from
`commit_or_reload_bootstrap_graph_group_v3`:

| Input | Native source |
| --- | --- |
| `SemanticReplayState` before and after | `prior_replay_state`, `next_replay_state` |
| `SemanticGraphDelta` | `canonical_graph_delta` |
| `SemanticEventInputBatch` | `canonical_event_batch` |
| group operation ID | `request.transaction_group_id` |
| sealed read set | each accepted reduction's `effective_read_set_digest`; require one exact value for the group |
| writer epoch | `request.writer_commit_binding.expected_writer_epoch` |
| base snapshot token | `prior_replay_state.state_digest` |
| policy bundle | equal retained bundles from all accepted reductions |
| conflict authority | server-derived `ProjectionHistoryRepository.resolve_semantic_conflict_authority(...)`, as in the generic path |
| authorization/capability | the V3 CAS's already-authorized writer and `self._write_capability` |

It constructs `ProjectionCommitRequest` with the existing fields:
`repository_id`, `operation_id`, `graph_revision`, `event_batch_sequence`,
`event_batch_digest`, `complete_read_set_digest`, `writer_epoch`,
`base_snapshot_token`, both policy fingerprints, `arbitration_as_of`, temporal
and trust projections, and `semantic_conflict_authority`. The migration call
uses the prepared trust generation's
`canonical_decay_command_digests`, plus graph revision, graph-delta digest,
batch sequence/digest watermark, and the same complete read set.

The policy dispatch has an important existing distinction. With no projection
history bindings, `projection_records_from_replay_state` must receive no
active-policy overrides; it derives the inaugural fingerprints and arbitration
coordinate from the closed native claims. The retained bundle validates that
all accepted closures agree with that result. With active bindings, pass the
bundle's `temporal_policy` and `trust_policy` as the existing helper does;
`projection_records_from_replay_state` then validates them against the active
pointers and does not substitute live policy.

## Required CAS And Reload Work

`commit_or_reload_bootstrap_graph_group_v3` must append, in the same existing
CAS, the prepared projection and migration records, the replay aggregate,
checkpoint lifecycle, and registry-history records, with all returned
preconditions plus `_semantic_authority_record_preconditions`. Its current
native `canonical_event_records` only contain the event batch, replay state,
and reference-integrity ledger (`atomic_store.py:11790-11820`). The new CAS
must advance the aggregate with no fabricated generic member bindings, replace
its projection-history bindings with the prepared pair, and create the
checkpoint over the actual V3 batch.

The primary/reload owner also needs an exact publication-closure check. Today
`_bootstrap_graph_v3_group_commit_reload_from_record` decodes only the group
reload and does not load the projection certificates, pointers, aggregate, or
checkpoint (`atomic_store.py:13824-13859`). `ProjectionHistoryRepository.prepare`
can identify an existing publication by the group operation ID, but a reload
path does not presently prove that its pair of certificates and replay bindings
were committed with that primary. The bounded implementation should extend the
V3 committed-result/reload contract with an explicit typed projection
publication receipt composed of existing temporal/trust certificate and
generation digests, both replay bindings, aggregate digest, and checkpoint
digest; reload validates those records before returning. This is a new V3
grammar/version-dispatch task, while old primary bytes continue through the
existing no-publication route without synthesized authority.

## Recommended Bounded Implementation Slice

Implement one accepted-native-group publication slice in
`memorii/memorii/core/memory_evolution/atomic_store.py` and the V3 result/reload
contracts only:

1. Read and cross-check the one retained policy bundle from the accepted
   reductions; fail closed for absent, mixed, or substituted bundles before
   any new records are prepared.
2. Extract and call the projection/migration/aggregate/checkpoint preparation
   described above from the accepted group branch, then commit all records and
   preconditions in its existing CAS/retry loop.
3. Add the explicit V3 publication receipt and make exact-primary reload
   validate it. Preserve old encoded group requests/results with explicit
   grammar dispatch and do not synthesize a publication for them.
4. Prove one public `sync_event` accepted group publishes both typed projection
   generations and a bound aggregate/checkpoint; prove noncommitting, lost-ack
   reload, stale CAS retry, absent/mixed bundle, and publication-record
   substitution fail closed.

No new projection algorithm, policy lookup, member vocabulary, aggregate
format, checkpoint format, registry publication, or ledger coordinate is
required by this slice.

## Remaining Boundaries

The retained bundle resolves the prior policy-authority input gap. Two
implementation boundaries remain, rather than unresolved product policy:

* V3 needs the deterministic single-bundle admission check above before it can
  use a single pair of active-policy overrides for a group.
* Existing V3 primary/reload grammar has no typed publication receipt, so the
  exact atomic join cannot currently be authenticated on reload. The required
  fields are the existing prepared-publication and replay/checkpoint identities
  listed above; their addition needs the normal V3 compatibility dispatch.

The global observation-ledger revision remains outside this slice. The V3
control's `observation_revision` is source-local and must not be presented as
the ledger coordinate.

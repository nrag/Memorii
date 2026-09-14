# Native Projection Publication Binding

This is an implementation map for the accepted branch of the actual native V3
group CAS.  It is not evidence that projection publication is already wired.

## Proven Production Caller

The production route is
`ProviderMemoryService.sync_event` (exercised by the root-composition fixture)
through the native coordinator and
`AtomicStoreBootstrapGraphRepositoryV3.commit_or_reload`
(`memorii/memorii/core/semantic_ingestion/bootstrap_graph_repository.py:402-419`)
to `SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3`
(`memorii/memorii/core/memory_evolution/atomic_store.py:11409-11889`).
`memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_observation_retention.py:20-75`
captures this non-test call boundary through the public provider service.

The V3 method materializes accepted native record intents, creates a real
`SemanticGraphDelta`, builds and replays a real semantic event batch, then
writes the event/replay/reference records in its group CAS
(`atomic_store.py:11640-11870`).  It currently does **not** call
`_semantic_event_authority_updates`, `ProjectionHistoryRepository.prepare`, or
`PolicyMigrationRepository.prepare_write_catch_up`.  The clarification method
and the generic `persist_terminal_group` path are not caller proof for V3.

## Reuse Boundary

Extract a private projection-publication preparation helper from the committed
branch of `_semantic_event_authority_updates`
(`atomic_store.py:12899-13030`), parameterized with the already-built native:

* `prior_state`, `next_state`, `canonical_event_batch`, `canonical_graph_delta`,
  `writer_commit_binding`, and `committed_at` from the V3 method;
* the V3 control's exact `effective_read_set_digest` and the pre-write state
  digest as `base_snapshot_token`; and
* the immutable temporal/trust policy snapshots that validate the already
  retained native claim closures.

The helper must call, in order:

1. `self._projection_history.replay_bindings()` and, when nonempty,
   `active_temporal_authority()` and `active_trust_authority()`.
2. `projection_records_from_replay_state(next_state, ...)`
   (`projection_history.py:5583-5904`).
3. `resolve_semantic_conflict_authority(...)` and
   `ProjectionHistoryRepository.prepare(ProjectionCommitRequest(...))`.
4. `self._policy_migration.prepare_write_catch_up(...)` with the prepared
   trust generation's canonical decay commands.

This preserves the existing history/pointer/certificate/projection validation
instead of reproducing it in the V3 CAS.  `prepare` supplies immutable
projection records and current-pointer preconditions; the catch-up preparation
supplies its records and preconditions.  Append both to the V3 `records` and
`conditionally_write_records(... preconditions=...)` tuples, before the single
CAS at `atomic_store.py:11845-11870`.

The prepared publication's `replay_bindings` must replace the previous binding
set in the same persisted semantic replay authority aggregate and replay
checkpoint, using the existing
`create_replay_checkpoint`/`advance_semantic_replay_authority` flow at
`atomic_store.py:12997-13085`.  V3 currently writes only the event batch,
replay state, and reference-integrity snapshot; merely adding projection
records would leave no authenticated aggregate/checkpoint binding for the new
generations.

## Retained Policy Authority

The V3 materialized `ClaimAssertion` does retain its claim identity, source
authority evidence, predicate trust rule, and temporal decision closure.  The
native planner produces those fields in
`bootstrap_graph_planning.py:434-469`; `projection_records_from_replay_state`
rejects a partial claim authority closure at `projection_history.py:5983-6021`.

The retention prerequisite now carries the complete bundle at
`ordered_operation_inputs[i].reduction.native_compilation.operation_input`
`.planning_construction_authority.arbitration_policy_bundle`. The built-in
builder reloads persisted reduction inputs, embeds them in native compilation,
and the assembler retains each reduction in the group request. The primary
record persists that complete request. The public provider retention test
verifies this path. No duplicate field on GraphAuthorityRequest, compilation,
terminal or group request is needed.

For activated accepted publication, the projection helper must extract the
bundle from this exact nested input, require presence, reject differing bundles
and verify every accepted claim closure before passing the snapshots to the
canonical projection owner. Historical absent-bundle decoding remains supported;
it does not authorize activated publication. Do not substitute a live policy
lookup or infer a bundle from fingerprints. This supersedes the initial map's
incorrect inference that omission of a direct field implied lost authority.

## Branches And Recovery

| Case | Required behavior |
| --- | --- |
| Accepted group | Prepare temporal and trust publications plus policy catch-up; append all records/preconditions, bind the returned replay bindings into aggregate/checkpoint, then write once with the existing V3 control/writer/event/replay/reference preconditions. |
| Noncommitting group | Keep current no-event/no-projection behavior.  It must retain the current replay bindings unchanged; it cannot advance projection history. |
| Existing primary/lost acknowledgement | Return `_bootstrap_graph_v3_group_commit_reload_from_record` before preparing new publication (`atomic_store.py:11449-11451`).  No duplicate projection history entry or callback is permitted. |
| CAS conflict | Re-enter the complete V3 sealed-read-set validation as the existing `write(retried_after_cas_conflict=True)` does (`atomic_store.py:11871-11886`); recompute preparation from the fresh replay/pointer authority and preserve exact-existing-primary reload. |
| Historical reads | Leave `current_temporal`, `current_trust`, `historical_temporal`, and `historical_trust` as separate authorities (`projection_history.py:3969-4089`).  The approved observation design must expose them separately, rather than merging their winners or intervals. |

## Focused Proof Owners

Add the native accepted-projection assertions to
`memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_observation_retention.py`,
which already drives a public `ProviderMemoryService.sync_event` through the
actual V3 commit.  Cover: one accepted fact produces both persisted projection
generations and replay bindings; a noncommitting native result produces none;
a lost acknowledgement reload does not append history; and a second accepted
commit verifies the retained policy bundle rather than using live policy.

Retain concurrency/reopen coverage in
`memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_scenario_replay.py`
and `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_jsonl_race_reopen.py`,
whose subprocess fixture is
`memorii/tests/fixtures/semantic_ingestion/bootstrap_graph_v3_process_runner.py`.
These are test ownership pointers only; no tests were run for this map.

# Bootstrap-V3 Source Progress Bridge Implementation

- Work ID: bootstrap_v3_source_progress_bridge_implementation_2026_09_04
- Work type: implementation
- Status: under-review; target-planner prerequisite and native bridge are
  implemented, with shared-candidate review pending
- Coordinator: Codex main thread
- Created: 2026-09-04
- Last updated: 2026-09-06
- Parent completion WorkPlan: `docs/work/semantic_ingestion/m4-closure-2026-09-04/implementation.plan.md`
- Approved design WorkPlan: `docs/work/semantic_ingestion/bootstrap-v3-source-progress-bridge-2026-09-04/design.plan.md`
- Frozen architecture SHA-256: `f7937f2871e07ca36cf58710d8ae6288f4f49f7f238ba468be5a49c4487e04f0`
- Baseline revision: `821b0bc7fd47ca0c55a18ccebb4b1628fa13689b`

## Objective

Implement the approved native Bootstrap-V3 source-progress bridge without a
parallel generic persistence owner. Preserve the original admission, delivery,
operation fence, retained member bytes, and append-only V3 lineage while the
real V3 group-CAS conflict appends exactly one bounded related-conflict
successor.

## Completion Contract

Complete only when the native three-state progress grammar is validated before
visibility and after reload in the existing V3 atomic generations; found-first
memory and JSONL recovery returns exact committed bytes; the public group-CAS
path resumes the original fence once without normalization, admission, or
full-pipeline re-entry; all mutation, concurrency, recovery, compatibility,
rollback, retry-exhaustion, production-root, and transaction-boundary families
pass; and independent specification, correctness, and test reviews leave no
remaining approval finding. This operation does not close M3.1 or M4 by itself.

## Scope Guard

Included: only the contracts, codecs, V3 assembler, V3 repository/store,
Bootstrap V3 coordinator, existing provider handoff, focused tests, and the
existing transaction-boundary gate named by architecture Section 4.8.3.4.

Excluded: generic source-progress schema changes, a second repository,
conflict-attention composition, general replay/history closure, M3.1 closure,
M5, provider API redesign, delivery-derived fallback, and unrelated refactors.

## Milestones

1. Conformance reset and native contracts: revert only the superseded generic
   progress/store/replay delta; add strict native V3 member references, replay
   bundle, measured counters, three progress variants, codecs, and exact
   assembler closures with staged availability.
2. Atomic persistence and recovery: validate exact cardinality, ordering,
   reference joins, acyclic digests, predecessor/retained closure, and legal
   transitions in the existing V3 store; add exact found-first memory/JSONL
   recovery and compatibility behavior.
3. Original-fence resume: use the existing group-CAS conflict branch and its
   bounded coordinator successor, preserve exact retained bytes, and reject an
   unavailable or invalid closure with a typed noncommitting result.
4. Evidence and review: complete mutation/concurrency/restart/rollback/root
   families, transaction-boundary rows and receipts, timing inventory, scoped
   and required gates, then reconcile three independent reviewers.

Only one writer may modify overlapping production or test files at a time.
Each milestone must update this WorkPlan with commands, results, findings, and
the next exact action before the next writer begins.

## Evidence Ledger

- Design approval: frozen architecture SHA above; three-role targeted review
  approved with no remaining findings.
- Slice 1: generic checkpoint/store/replay delta reverted; native reference,
  replay-bundle, counter, progress contract, codec, and plan/attempt/lineage
  member construction implemented. `test_bootstrap_graph_source_progress_contracts.py`
  and `test_bootstrap_graph_artifact_assembler.py` pass (10 focused tests
  total). The planned-variant regression proves the null manifest reference is
  included in the content-addressed creation preimage; it previously caused
  `progress_digest mismatch` in authorized-lineage construction. Changed
  production modules compile and `git diff --check` passes. The full
  coordinator parametrized cases exceed the local 30-second command window
  and remain an unrecorded slice-4 gate, not passing evidence.
  Store-side equivalence/reload validation
  remains explicitly owned by slice 2.
- Slice 2: complete native store/repository validation verifies the one progress
  member's checkpoint discriminator, original-fence/lease/writer/epoch joins,
  exact current-member references and typed artifact digests, native counters,
  forward-artifact exclusion, and the initial plan -> attempt -> planned
  progression before write and on ordinary reload. The new original-fence port
  finds the newest sealed bridge progress member in the local V3 generation
  chain, validates its persisted member closure, and returns a second decode of
  the exact stored bytes; generations without bridge progress return the typed
  unavailable error. `PYTHONPATH=memorii .venv/bin/pytest -q
  memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_source_progress_contracts.py
  memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_artifact_assembler.py
  memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_atomic_member_native_codec.py`
  passes (14); changed modules compile and `git diff --check` passes. The
  coordinator family remains slice-4 evidence. The previously missing native
  `BootstrapGraphReplanClosureReferenceV3` is now implemented: it binds frozen
  predecessor planned-progress and lineage member references, canonical final
  result references, and canonical unfinished/replanned identifiers. Its
  digest is registered, the V3 assembler constructs it from sealed predecessor
  bytes, and store validation rejects future/substituted closure references.
  The focused contract/assembler suite passes 11 tests. The real-store recovery
  family passes 9 tests in 322.39 seconds and proves exact memory and independent
  JSONL reload bytes, lost-acknowledgement found-first behavior, concurrent
  identical convergence, stale same-predecessor rejection, reclaimed-lease
  reload, pre-bridge typed unavailability without writes, duplicate closure
  rejection, substituted/future reference rejection, and a canonically
  recomputed counter decrease. That proof exposed and corrected four real
  implementation omissions: canonical JSON decoding of stored tuple-bearing
  requests, legal initial publication after a non-bridge normalization
  generation, retained `attempt-inputs` in all progress generations, and the
  attempt checkpoint's persisted authorization set. Store validation now also
  enforces stage-derived measured counts and componentwise predecessor
  monotonicity. Slice 2 is complete; slice 3 owns runtime resume wiring.
  A prerequisite recovery correction adds the internal-only
  `BootstrapGraphResumeClosureV3` port beside the progress-only port. It finds
  the newest sealed `planned` member, then reloads only the exact named
  current/predecessor member records referenced by that progress: progress,
  plan, replay bundle, counters, attempt inputs, authority, attempt,
  authorizations, complete lineage, the exact predecessor-chain pre-execution
  evidence, and any canonical
  predecessor final group constructions. Each carrier retains the decoded
  artifact, original atomic member, and original bytes; member-record,
  generation, codec, payload, typed-artifact, reference, and closure-partition
  substitutions reject. No schema or persisted record kind was added. Focused
  memory and JSONL tests are extended for exact closure bytes and a missing
  member; the fixture-backed runtime command exceeds the local 30-second
  command window, so execution remains candidate-gate evidence. `ruff`,
  `py_compile`, collection (11 tests), and `git diff --check` pass.
- Slice 3: implementation complete, production proof blocked. The native coordinator reloads the internal exact-byte
  `BootstrapGraphResumeClosureV3` at the real V3 group-CAS conflict boundary,
  appends exactly one replan plan -> attempt -> lineage sequence, preserves the
  predecessor closure and final-result bytes, and advances measured counters
  componentwise when a competing accepted graph transaction advances graph
  authority. A clarification answer is ordinary admitted ingestion and must
  reach that same accepted transaction path. The superseded
  provider-level `SemanticConflictProjectionStaleWinnerError` catch/direct host
  resume wiring and its test-only production-owner seam are removed:
  `SemanticConflictProjectionStaleWinnerError` remains generic non-V3
  event-batch preflight behavior. Retry generations remain immutable while their
  singleton request/fence locators advance under digest compare-and-swap.
- Slice 4: in focused-validation. The selector owns all four source-progress
  scenarios (`source_progress_initial`, `source_progress_related_conflict`,
  `source_progress_lost_ack`, and `source_progress_reclaimed_lease`) for
  direct/factory/filesystem/Hermes and memory/independent-JSONL roots: 232
  rows, 384 required tuples, and 29 selectors per receipt shard. The related
  conflict row uses the existing real V3 group-CAS scenario: it asserts three
  sealed native sequences (the initial generation plus two CAS successors),
  retained plan/replay bytes, one admission/delivery, one final effect, and
  matching independent-process JSONL reopen evidence. The other rows assert
  their single sealed sequence and relevant lost-ack or lease recovery. The
  selector manifest, receipt contract, and ownership assertions pass (`11
  passed in 8.99s`); focused ruff and `git diff --check` pass. Collection proves
  all four related-conflict selectors for each memory and independent-JSONL
  root (`4/116` and `4/117` selected respectively). The corrected related-conflict
  memory selector previously passed all four fixture-composed roots (`4 passed
  in 201.63s`). The complete
  four-scenario matrix was also executed directly through the production
  process runner for direct/factory/filesystem/Hermes: 16 first runs and 16
  independent reopen runs all exited zero. Every first run returned
  `source_only` with one graph effect; lost-ack rows recorded the injected lost
  acknowledgement; initial/lost-ack/reclaimed-lease rows retained one exact
  three-member progress sequence; related-conflict rows retained three exact
  sequences, two conflict calls, and one final graph effect. This earlier run
  was later rejected because its related-conflict row was synthetic. The row
  now runs two ordinary admitted `sync_event` calls and constructs each actual
  direct/factory/filesystem/Hermes root with the non-scenario
  `BootstrapGraphHostBundle`; the only test hook schedules calls at the real
  atomic group-CAS method. This corrected proof fails before the intended
  conflict: direct-root execution produces two admissions, two group-CAS calls,
  two unresolved group primary records, and only six progress checkpoints.
  The built-in production compiler unconditionally emits
  `graph_target_missing`, so B cannot create entity/fact effects or advance the
  shared graph revision and A never becomes stale. The focused direct selector
  fails at the required `3` CAS assertion (`2` observed). Scoped Ruff passes.
  This is an existing M3.1 production target-planner implementation gap, not a
  defect in the typed progress bridge and not valid evidence for bridge closure.

## Decisions And Risks

- Existing Bootstrap V3 generations remain the sole persistence authority.
- Pre-bridge generations remain readable and non-replannable; rollback disables
  new progress publication and replan without rewriting old generations.
- `SemanticConflictProjectionStaleWinnerError` remains typed at the generic
  event-batch graph-revision preflight; Bootstrap V3 group-CAS conflicts do not
  translate or catch it.
- The superseded generic checkpoint code has passing focused tests but violates
  the approved ownership boundary and is deliberately removed in slice 1.
- M3.1 and M4 remain incomplete until the parent completion contract is met.

## Independent Review Round 1

- `correctness_reviewer`: not approved. Confirmed `P2 / changes_required /
  runtime behavior + transaction consistency`: the real atomic group owner can
  emit `SemanticConflictProjectionStaleWinnerError`, but the coordinator's
  text-matched `PreplanningStoreError` classifier downgrades that real stale
  revision to `storage_retry`. The fixture scenario raises a synthetic error
  before the atomic store and therefore does not prove the production race.
- `correctness_reviewer`: not approved. Confirmed `P2 / changes_required /
  recovery + invalid state transition`: `coordinate()` does not resume sealed
  `plan_published`, `attempt_published`, or `planned` checkpoints, and the store
  currently treats every closure-free `plan_published` generation as an
  initial bridge plan. Interruption can therefore append a second initial plan;
  partial-result closure is also incomplete across recovered replan.
- `spec_auditor` and `test_reviewer`: review ineligible because the parent
  candidate is not yet a clean frozen commit. Their preliminary inspection
  independently confirmed that the related-conflict fixture was synthetic.
- Coordinator classification: both P2 findings are confirmed by direct code
  inspection at the atomic group event-batch preflight, coordinator classifier,
  fixture wrapper, coordinate entry point, and store transition validator.
  The candidate-identity finding is a real governance dependency for final
  parent closure, not a reason to defer the determinate product corrections.
- Current review arrays:
  `remaining_validated_p1_p2: [real_v3_stale_revision_downgraded,
  native_checkpoint_resume_absent]`;
  `remaining_blocks_approval: [candidate_identity_not_frozen]`;
  `remaining_changes_required: [typed_group_conflict_and_authority_refresh,
  exact_checkpoint_resume_and_partial_result_closure]`.

## Remediation Result

The host is the canonical fresh-authority owner. The group-CAS boundary emits
only `BootstrapGraphRelatedConflictRefreshRequiredV3`; the host reacquires the
shared graph snapshot/compiler/epoch/authorizer once, and the fresh coordinator
enters `coordinate_related_conflict` with the typed old-request/fence handoff.
That entrypoint reloads exact predecessor bytes and invokes the existing
bounded successor machinery. The group CAS now derives `graph_revision_before`
from the sealed shared graph read set, not the source-local operation control,
which is allowed to lag after B commits. A second conflict terminates without a
third attempt.

## Final Review Candidate

- Base/HEAD: `821b0bc7fd47ca0c55a18ccebb4b1628fa13689b`.
- Tree state: dirty and intentionally unfrozen while the production-root proof
  is failing. The previously recorded tracked-delta hash is superseded and may
  not be used as review identity.
- Untracked in-scope proof hashes:
  `test_bootstrap_graph_source_progress_contracts.py` =
  `3524464d52962daa02a8f8612a81c376c7f8b6b9fcd19999521778d2e6ff0abc`;
  `test_bootstrap_graph_source_progress_store_recovery.py` =
  `b24522693f43aa73a4429429a09e6edbcaba7769f977e833451f2e7365d3210a`.
- Review scope: the native V3 progress contracts, exact checkpoint/recovery
  state machine, real group-CAS typed conflict and host refresh handoff,
  source-local versus shared graph revision ownership, focused fixtures/tests,
  transaction selector, architecture delta, and binding ledger.
- Exclusions: generic non-V3 conflict preflight semantics, M3.1/M4 parent
  closure, M5, provider API redesign, and unrelated existing branch changes.

## Exact Next Action

Freeze this completed bridge with the shared M3.1/M4 candidate and obtain the
required exact-SHA hosted checks and independent specification, correctness,
and test review. Do not add another bridge or expand into M5 activation.

## Independent Review Round 2

- `spec_auditor`: confirmed `Not applicable / changes_required /
  verification + integration`. The earlier four-root labels still composed the
  private scenario host and injected authority provider. The correction now
  constructs the actual public roots and asserts the exact production host
  type, with only a post-construction atomic-boundary scheduling hook.
- Coordinator remediation result: the corrected proof is truthful and exposes
  a deeper prerequisite instead of closing. The production built-in compiler
  documents and implements an unconditional unresolved
  `graph_target_missing` result, contrary to the design's still-unimplemented
  accepted target-materialization algorithm. Therefore an ordinary B
  ingestion cannot advance graph authority in the required scenario.
- `test_reviewer`: confirmed `Not applicable / blocks_approval / governance +
  evidence` because the candidate changed after its recorded dirty-tree hash.
  Candidate identity will remain unfrozen while the required acceptance proof
  fails.
- `correctness_reviewer`: confirmed `P2 / changes_required / runtime behavior
  + integration mismatch`. The production built-in compiler emits only
  unresolved reductions, while group CAS advances shared graph revision only
  for accepted reductions. Therefore the normal-path trigger for the typed
  refresh/successor branch is unreachable. The earlier typed conflict and
  checkpoint-resume P2 defects are otherwise corrected locally.
- Current review arrays:
  `remaining_validated_p1_p2: [production_target_planner_unreachable_replan]`;
  `remaining_blocks_approval: [production_target_planner_not_implemented,
  candidate_identity_not_frozen]`;
  `remaining_changes_required: [production_target_planner_accepted_fact_path,
  real_public_root_related_conflict_proof]`.

## Superseding Resolution 2026-09-06

The separately bounded target-materialization operation implemented the real
accepted fact path, and the native V3 bridge now executes through the public
root. The final correction additionally proves an accepted clarification
staling an already-planned source through public `memorii_resolve_conflict` in
memory and independently reopened JSONL, with one admission, no
renormalization, original-fence reuse, and exact typed successor progress. The
older blocked state and review arrays above are historical and superseded;
their removal remains gated only on the shared frozen-candidate review.

# Semantic Conflict Authority Proof Failures

- Work ID: semantic_conflict_authority_proof_failures
- Work type: debugging
- Status: under-review; final-candidate corrections and local affected families
  are green
- Coordinator: Codex main thread
- Created: 2026-08-04
- Last updated: 2026-09-06
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/semantic-conflict-introduction-authority-2026-08-04/design.plan.md`; `docs/work/semantic_ingestion/testing.plan.md`
- Canonical inputs: `docs/design/conflict_attention.md`; `docs/design/semantic_ingestion_architecture.md`; `docs/design/event_model.md`; seven-node verification map
- Expected outputs: isolated root causes for the deterministic proof failures, smallest invariant-level fixes, family-complete green proof, and independent closure review

## Objective

Make the seven canonical semantic-conflict core proof nodes exercise the real
same-store authority path and pass without relaxing atomicity, authorization,
replay, lifecycle, or compatibility contracts.

## Completion Contract

Complete only when the exact 12-case reproducer passes; every failure family
has a recorded causal chain and before/after discriminator; real JSONL reopen,
lost acknowledgement, invalid resolver output, replay/checkpoint, and
clarification race behavior remain fail closed; focused sibling suites pass;
and independent specification, correctness, and test review reports no
remaining validated P1/P2, `blocks_approval`, or `changes_required` finding.

## Scope

Included: the seven mapped core proof nodes; their shared test support; replay
fixture graph revision; terminal atomic failure/reopen observation; authority
rejection transaction ordering; and any production defect causally required by
those failures.

Excluded: provider/factory/Hermes composition, derived cache/composite listing,
CI timing reconciliation, and the two separately known file-event freeze
defects.

Deferred: broad M4 gates and whole-branch review to the parent implementation.

## Constraints And Invariants

- Tests use real prepare, conditional write, JSONL reopen, verified host grant,
  and canonical resolver authority. They may not seed `ConflictAttention`, use
  private authority enrollment, or replace the memory plane with a fake reader.
- Invalid authority input must reject before any semantic event, replay,
  projection, conflict, receipt, or pointer record changes.
- Lost acknowledgement exposes the complete committed closure before retry;
  pre-write failure exposes the exact prior state.
- One writer owns overlapping production and test remediation at a time.

## Identity And Coordinate Hygiene

All durable code/test identities remain behavioral. This WorkPlan ID and
hypothesis/experiment IDs are evidence coordinates and may appear only here.

## Change Impact And Verification Closure

| Surface | Authority chain | Required evidence | Status |
| --- | --- | --- | --- |
| `test_event_replay.py` real conflict proof helpers | terminal prepare -> CAS -> replay/checkpoint -> reopen | two mapped replay nodes | failing |
| `test_semantic_terminal_persistence.py` atomic/authority/race nodes | terminal transaction -> exact rejection/recovery | three mapped terminal nodes | partially failing |
| projection history and policy migration mapped nodes | generic/special publisher -> shared authority closure | two mapped projection nodes | passing |
| production authority/replay transaction path | resolver/provenance -> prepare -> one CAS | focused siblings and exact reproducer | under investigation |

## Historical Next Action (Superseded)

Add same-plane canonical clarification submission, claim, completion, and
supersession records to the semantic-conflict authority, then prove both
projection-versus-clarification winner orders with deterministic barriers.

## Expected And Observed Behavior

Expected: all 12 concrete cases pass through real persisted authority without
partial or unauthorized state. Observed on dirty HEAD
`2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`: 4 passed and 8 failed in 512.92
seconds. Two replay nodes fail before authority publication with
`event compilation state does not match repository graph revision`. The
atomicity node fails before its injected write boundary. Five invalid-authority
cases raise as expected but leave the semantic replay aggregate changed,
violating zero-effect rejection.

## Reproduction Contract

Run the exact seven node selectors recorded in the parent verification map with
`PYTHONPATH=memorii`. They collect as 12 cases and reproduce deterministically.
The recorded run completed `8 failed, 4 passed in 512.92s`.

## Hypothesis Ledger

| ID | Hypothesis | Supporting evidence | Contradicting evidence | Discriminator | Status |
| --- | --- | --- | --- | --- | --- |
| H1 | replay helper reuses a terminal/fence whose graph revision is stale after a prior persisted terminal | failure arises in `build_semantic_memory_event_batch` before conflict preparation | none after direct state trace | inspect helper state/fence graph revisions and run one isolated case | confirmed fixture root cause |
| H2 | replay production reconstruction rejects a valid reopened authority even with correct fixture revision | failure is on real JSONL path | traceback occurs before any replay binding construction and H1 exactly explains mismatch | correct only fixture sequencing | disproved for observed failure |
| H3 | atomic failure hook is installed too late or watches the wrong write shape | atomic node fails before injected CAS | full isolated traceback shows introduction model validation failure | inspect exact introduction digest preimage | disproved as primary cause |
| H4 | invalid resolver output is rejected only after event/replay checkpoint publication has already committed | replay aggregate changes despite expected exception | none after conditional-write trace | trace every conditional write and compare operation IDs | confirmed production root cause |
| H5 | the before/after assertion includes legitimate pre-terminal lease/checkpoint mutations outside the contested semantic CAS | changed record is replay aggregate | design requires invalid authority to have zero effects before lease/checkpoint mutation | snapshot before call and classify writes | disproved as acceptable behavior |
| H6 | introduction construction hashes a partial body while strict validation hashes materialized defaults | atomic node fails with introduction digest mismatch | none after model/preimage comparison | include defaults or use one canonical constructor | confirmed production root cause |
| H7 | final terminal CAS needs a second host resolver callback to remain fresh | a second callback after lease/checkpoint can itself be malformed or changed | pointer/resolver records can be bound by exact in-lock CAS preconditions | seal one preflight result, then validate it against current records during final prepare/CAS | confirmed incorrect assumption; removed |
| H8 | the mapped projection-versus-clarification race is only missing test coverage | the named node exists | it races integrity recovery against a synthetic clarification and clarification has no canonical conflict pointer precondition or `superseded` outcome | map production clarification records and run both pointer CAS orders | disproved; confirmed production contract gap |

## Experiment Log

- E0: exact seven-node run established three deterministic failure families and
  retained the full trace in the active Codex task output.
- E1: traced replay helper control revisions. First commit advanced the replay
  graph while later pre-admitted controls retained `genesis`; compilation
  correctly rejected the stale baseline before conflict replay code.
- E2: isolated atomic node failed in 110.85 seconds with
  `semantic conflict introduction digest mismatch`. Construction omitted
  predecessor/status defaults that model validation includes.
- E3: traced invalid resolver `missing` case. Lease/planned-checkpoint mutation
  updated the replay aggregate before later conflict resolver validation raised.
- E4: installed a store-owned read-only preflight that derives the candidate
  projection output, resolves host authority once, and runs prospective
  `ProjectionHistory.prepare` before the terminal service acquires a lease.
  The sealed input is carried into the terminal request; final prepare derives
  contest/scope anew and binds resolver/pointer records as CAS preconditions
  without another host callback.
- E5: mapped the claimed-clarification path. It has no
  `ActiveSemanticConflict` pointer precondition, no typed `superseded` attempt
  result, and remains attached to the independent file-ledger workflow. The
  existing named race test exercises integrity recovery, not semantic conflict
  serialization.
- E6: added a typed clarification CAS input binding the exact active semantic
  conflict pointer digest/revision, work and attempt record digests, ownership
  epoch/token digest, operation, and proposal. The semantic transaction now
  reads those exact records and includes all three `RecordDigestPrecondition`s
  in its one CAS; its transaction bytes bind the CAS input digest. Added the
  typed `superseded` attempt result, which requires the successor conflict
  revision and cannot bind a semantic receipt. This is only the completion
  fence: submission, claimed work, attempt, result, and successor-pointer
  records are still file-ledger-only and must move into the memory plane before
  the race can be considered fixed.
- E7: three artifact-only Spark mappings independently located the same missing
  boundary: the file repository owns submission/claim state, the semantic
  adapter never constructs the existing clarification CAS input, and the
  recorded race node never creates a real conflict pointer/work/attempt image.
- E8: added the typed immutable clarification-transition foundation and taught
  projection reconstruction to validate predecessor status, revision, digest,
  and contiguous coordinates. `superseded` is audit-only and cannot be an
  active-pointer target. Model, Ruff, compile, and the existing 15-case
  projection-history suite passed. A real JSONL fixture exposed the remaining
  intentional boundary: governed writes reject lifecycle records because no
  canonical memory-plane lifecycle repository exists yet.
- E9: added canonical same-plane submission and work generations. Submission
  atomically binds the proposal, operation receipt, initial unclaimed work,
  submitted transition, pointer history/current pointer, and ledger head.
  Claim and renewal append immutable predecessor-keyed successors under a
  single-successor CAS. Replay rejects forks, orphans, stale ownership,
  divergent retries, and malformed persisted enum/scalar payloads. Terminal
  completion still requires independently addressable persisted work and
  attempt artifacts so the existing clarification CAS can fence both.

## Root-Cause Statement

The trigger is the first real slot-bearing contest, an intentionally invalid
host resolver result, or a claimed clarification racing a natural projection
successor. Four independent defects propagate to the observed matrix and proof
gap. First, the replay test helper admitted successor operations before a
predecessor commit, so their frozen graph baselines became stale; production
correctly rejected them and the test never reached replay assertions. Second,
conflict introduction construction hashed a partial dictionary, while strict
model validation hashed the fully materialized predecessor/status defaults, so
every real introduction failed before CAS. Third, terminal persistence acquired
a lease and published a planned checkpoint before it derived and validated host
conflict authority; invalid resolver output therefore changed replay authority
before later rejection. Fourth, clarification never joined the canonical
semantic-conflict pointer CAS and had no typed superseded outcome, so the
specified race behavior could not occur. Earlier focused tests missed these
because they
used empty authority, direct prepared records, or pre-created controls rather
than a real nonempty terminal sequence; the named race test covered an unrelated
integrity-recovery lock.

## Fix Strategy

Use one canonical complete introduction preimage/constructor and keep strict
validation unchanged. Add a read-only authority preflight after reading current
control/projection state but before lease acquisition or planned-checkpoint
write; retain independent derivation, record/pointer/provenance preconditions,
and freshness validation inside the final CAS. Change only replay test setup so
each successor is handed off after the prior terminal commits; retain stale
baseline rejection and its existing zero-effect regression. Bind accepted
clarification to the exact active semantic-conflict pointer and record claimed
work in the same plane. If a natural successor wins, atomically retain a typed
`superseded` attempt result with no semantic event, effect, or receipt; if
clarification wins, the projection publisher must reload/replan rather than
commit a stale pointer.

## Regression Proof

The exact 12-case reproducer, focused projection/scheduler siblings,
checkpoint replay siblings, scoped Ruff/compile/diff checks, and independent
three-role closure review are required.

## Delegation And Cost Ledger

| Phase | Task | Role/tier | Access | Status |
| --- | --- | --- | --- | --- |
| causal trace | replay fixture and graph revision | error-detective / Spark-class | read-only | ready |
| causal trace | atomic injection boundary | error-detective / Spark-class | read-only | ready |
| causal trace | invalid-authority write ordering | debugger/correctness / Terra-class | read-only | ready |
| lifecycle map | submission/claim/completion ownership | code-mapper / Spark-class | read-only | complete |
| proof map | exact reproducer and slow collection path | error-detective / Spark-class | read-only | complete |
| requirements | conflict race and replay obligations | explorer / Spark-class | read-only | complete |
| test matrix | same-plane winner-order proof | test-reviewer / Terra-class | read-only | complete |
| foundation | typed clarification transition and replay validation | worker / Terra-class | sole writer | complete |
| fixture proof | real-authority reconstruction mutation matrix | worker / Terra-class | sole writer | blocked on missing canonical lifecycle write API; routed into next slice |
| lifecycle authority | plane repository, atomic closure, supersession hook, and race proof | worker / Terra-class | sole writer | in progress |
| retry lifecycle map | failure, expiry/reclaim, and exhaustion transitions | mapper / low-reasoning Terra | read-only | complete; Spark quota unavailable |
| completion map | semantic completion and projection race seams | mapper / low-reasoning Terra | read-only | complete; Spark quota unavailable |
| persisted decoder | strict JSON-wire generation/transition decode | worker / Terra-class | sole writer | complete |
| retry lifecycle | failure, expiry/reclaim, terminal failure, and exhaustion closures | worker / Terra-class | sole writer | complete |
| CAS artifacts | separate work/attempt/result members and canonical CAS builder | worker / Terra-class | sole writer | complete |
| atomic completion | accepted/rejected/insufficient closure and replay binding | worker / Terra-class | sole writer | positive matrix complete; negative matrix in progress |
| completion safety | stale fences, retained corruption, and admission negatives | worker / Terra-class | sole writer | complete |

## Progress Log

- 2026-08-04: Opened linked debugging operation after the first complete real
  seven-node run produced 8 deterministic failures and 4 passes.
- 2026-08-04: Confirmed the eight failures split into two production defects
  and one test-fixture sequencing defect; no governing requirement ambiguity or
  environment failure remains.
- 2026-08-04: Implemented the bounded remediation. The direct invalid-authority
  family passed 6 cases (five resolver mutations plus the atomic introduction
  boundary); the real JSONL replay derivation node is running.
- 2026-08-04: Verification review proved the named clarification race test was
  a false proof and exposed the missing canonical pointer-CAS production path.
- 2026-08-04: Resumed from the compact M4 packet. Cost-aware mapping used three
  non-overlapping Spark roles; a bounded Terra test consultation established
  the failure matrix before product edits.
- 2026-08-04: Completed the typed clarification-transition/replay foundation.
  Direct coordinator inspection found and remediated missing predecessor-edge
  validation and prohibited `superseded` from becoming the current pointer.
- 2026-08-04: The first real JSONL reconstruction control reached governed
  admission and failed because resolver administration correctly rejects
  lifecycle writes. This is discriminating evidence for the missing canonical
  plane repository, not permission to bypass the policy. The next sole writer
  owns that production API and will replace the direct fixture write.
- 2026-08-04: Canonical submission, claim, and renewal generations landed with
  exact-retry and replay validation. The strict JSON-wire boundary now accepts
  canonical enum strings while rejecting unknown enums and coercible scalars.
  Spark capacity is exhausted until 2026-08-09, so subsequent read-only maps
  used low-reasoning Terra while writer concurrency remained one.
- 2026-08-04: Retry mapping confirmed that failure, lease reclaim, and
  exhaustion must append in the same memory-plane successor chain. Completion
  mapping confirmed that work and attempt need separate persisted identities
  before production can construct the typed terminal CAS input.
- 2026-08-04: Completed the canonical retry lifecycle. Retryable failure
  increments the attempt budget and clears ownership; lease reclaim closes the
  expired attempt and starts a new epoch without consuming budget; the third
  retry atomically publishes `processing_exhausted`; terminal infrastructure
  failure becomes unclaimable without fabricating a semantic pointer edge.
  Replay now distinguishes the proposal/open revision from the active
  submitted-pointer revision.
- 2026-08-04: Bounded retry audit confirmed three P2 defects and the sole
  remediation writer closed all three: queue-only closures now reject semantic
  and audit terminal outcomes; successors must extend the currently submitted
  generation while retaining exact predecessor-keyed retry; and lost-ack
  retention requires a live lease so expired same-token calls reclaim at the
  next epoch.
- 2026-08-04: Added separately addressable immutable work, attempt, and result
  members atomically beside their generation manifests. Admission and replay
  require exact 1:1 generation/member closure. The canonical read-only CAS
  builder now binds the active submitted pointer revision separately from the
  proposal/open revision and rejects stale, expired, wrong-owner/epoch, missing,
  or corrupt members before semantic processing.
- 2026-08-04: Completed the positive atomic terminal matrix. Submission,
  accepted/rejected/insufficient completion, and processing exhaustion now
  advance the prospective semantic-conflict replay binding in the same CAS as
  their transition/pointer closure; claim and renewal remain replay-neutral.
  Accepted completion preserves same-conflict adjacency, orders newly derived
  conflicts afterward, and emits one final ledger head.
- 2026-08-04: Completed the direct completion safety matrix. All stale pointer,
  work, attempt, token, epoch, and expired-lease images reject before a write.
  Lost-ack retry and semantic replay now validate the retained transaction,
  receipt, terminal queue/member closure, pointer lifecycle, and replay
  authority; detached semantic pairs are not admission-valid.
- 2026-08-04: Canonical clarification submission now binds the operation index,
  retained verified-user-confirmation proof, and one-time nonce consumption in
  the same immutable generation. Exact retries validate that whole closure;
  missing or substituted operation/proof/nonce members fail replay closed.
- 2026-08-04: Began the final projection-race slice. Projection preparation now
  recognizes changed natural successors over submitted clarification work and
  prepares terminal unowned work plus a `SUPERSEDED` attempt result without a
  clarification receipt or semantic effect. Deterministic two-order proof is
  still the exact active acceptance boundary.
- 2026-08-04: Completed both deterministic projection-versus-clarification
  winner orders. Projection-first terminalizes work with one `SUPERSEDED`
  result and no clarification receipt/effect. Clarification-first commits its
  semantic closure, rejects the stale prepared projection and stale graph
  fence with zero writes, then succeeds from a fresh handoff/replan.
- 2026-08-04: The winner-order proof exposed and closed three adjoining
  authority defects: completion now distinguishes the proposal's OPEN revision
  from the work/attempt submitted revision; clarification semantic effects
  advance reference-integrity authority in the same CAS; and multi-conflict
  resolver pointer digests are canonicalized as a set.
- 2026-08-04: Frozen-review remediation now uses the canonical
  `superseded_by_conflict_revision` attempt-result wire field and rejects the
  legacy name. Exact stale claimed completion recovers the retained terminal
  result, including `SUPERSEDED`, without a write or pipeline adoption; the
  processor/adapter treats verified supersession as a no-op rather than a
  receipt mismatch.
- 2026-08-04: Added real JSONL clarification recovery proofs. Submission and
  accepted completion both survive apply-then-raise, reopen, and exact retry
  without duplicate records. A signed nonempty submitted-conflict checkpoint
  validates/resumes through the reopened real repository, while syntactically
  valid pointer and immutable-member substitutions fail before exposure.
- 2026-08-04: Added the missing canonical submission-versus-projection race in
  both deterministic orders through the normal terminal publisher. A
  projection-first lost submission CAS re-reads canonical authority and
  returns `STALE_REVISION` with no proposal/operation/proof/nonce/work append.
  Submission-first publishes one closure, exact retained retry returns
  `IDEMPOTENT`, and the changing projection terminalizes unclaimed work with no
  attempt result. Canonical facade retry resolves its operation index before
  attention/proof work, and transition hashing now encodes the strict model.
- 2026-08-04: The exact reproducer's durable-boundary node exposed a retained
  committed-group retry defect. After a lost acknowledgement, the source
  remained correctly `planned` with its group durable, but `persist()` ran a
  new conflict preflight against the already-advanced graph before recognizing
  that retained group. Recovery now skips that preflight when the control
  already has group-result authority and proceeds directly to finalization.
  The test now distinguishes pre-write completion from committed-group
  lost-ack recovery and compares stable authority record discriminators rather
  than non-uniform memory-ID path segments.

## Evidence Log

- Exact run: 12 cases, `8 failed, 4 passed in 512.92s`.
- Passing families include the generic projection choke and both cutover/decay
  parameter variants.
- Atomic isolated reproducer: one deterministic failure in 110.85 seconds with
  introduction digest mismatch before the injected CAS.
- Invalid-authority trace: replay aggregate changes before expected rejection.
- Completion-fence partial correction: the atomic semantic transaction now
  rejects a supplied stale pointer/work/attempt image before it can write a
  receipt or semantic effect. `py_compile` plus the focused existing concurrent
  clarification idempotency node passed. The existing mapped race remains a
  false proof and no new race evidence has been claimed.
- Direct authority rejection selector: `6 passed` after the preflight change.
- Real replay derivation selector: running at the time of this update; it uses
  repeated durable JSONL reopen paths and has produced no failure output.
- The selector was interrupted after 1055.32 seconds with `no tests ran`; the
  interruption landed during pytest cleanup. A direct atomic-store import
  completed in approximately 29.35 seconds, so the next discriminator is
  `test_event_replay.py` collection/setup rather than terminal publication.
- Foundation proof: `py_compile` and Ruff passed for the changed transition,
  projection-history, writer-admission, and focused test surfaces;
  `test_semantic_clarification_transition_has_closed_lifecycle_edges` passed;
  `test_projection_history.py` passed 15 cases.
- Real-authority fixture discriminator: the valid control reached
  `SemanticGovernedWritePolicy` after approximately 68 seconds and failed with
  `conflict authority administration closure is invalid`, proving that no
  authorized lifecycle write API yet owns the proposed record closure.
- Canonical generation proof: the clarification-attention and projection
  history contract suites passed 28 cases after submission landed; focused
  compile/Ruff and the strict persisted-wire regression passed after
  claim/renew support. The parameterized memory/JSONL canonical claim-and-renew
  selector then passed with the final shared policy. Its regression accepts one
  authorization-authority record beside a valid conflict closure and rejects
  two residual authorization records with no durable write. `py_compile`,
  Ruff, and `git diff --check` also passed.
- Retry lifecycle proof: memory + JSONL/reopen retry/reclaim/exhaustion passed
  2 cases; memory + JSONL terminal failure passed 2 cases; the dedicated JSONL
  malformed-attempt-result mutation passed 1 case by failing closed with zero
  writes. Scoped Ruff, `py_compile`, and `git diff --check` passed.
- Retry audit remediation proof: 4 focused memory/JSONL cases passed in
  295.54s, covering live exact retry, expired same-token reclaim, forbidden
  accepted/rejected/insufficient/superseded queue closures with zero writes,
  stale exhausted-chain rejection after a real resubmission, and the existing
  retry/exhaustion path. `py_compile`, targeted Ruff, and diff-check passed.
- CAS-artifact proof: the combined memory/JSONL clarification persistence
  selector passed 4 cases (179 deselected) in 283.36s, including missing or
  corrupt work/attempt/result member rejection with zero writes. Core
  projection-history plus conflict-attention tests passed 29 cases;
  `py_compile`, scoped Ruff, and diff-check passed.
- Replay-binding/positive-completion proof: accepted, rejected, and insufficient
  completion pass on memory and JSONL/reopen; the JSONL three-outcome selector
  passed 3 cases in 593.46s. Exhaustion passed on memory in 107.79s and
  JSONL/reopen in 170.33s. Compile, Ruff, and diff-check passed.
- Completion-safety proof: one loop per backend covered 9 stale/expired fences;
  memory passed in 120s and JSONL in 188.8s with zero conditional writes and
  unchanged snapshots. Retained-corruption mutations passed all 4 memory and
  all 4 JSONL/reopen cases (JSONL 454.58s). Direct admission passed 3 cases;
  compile, Ruff, and diff-check passed.
- Submission-proof authority: verified positive submission/retry passed on
  memory in 82.12s and JSONL/reopen in 150.23s. All six retained missing or
  substituted operation/proof/nonce mutations passed in 609.00s. Five negative
  source, digest, request, action, and principal proof-binding cases passed in
  502.68s. The independently live cross-conflict nonce discriminator exposed a
  strict JSON-wire decode regression in projection-transition reconstruction;
  the decoder correction is in place and `test_projection_history.py` passes
  15 cases, but that cross-conflict discriminator requires a post-edit rerun.
- Final race proof: projection-first passed in 110.60s on the final in-memory
  CAS seam; clarification-first passed in 193.87s, including stale prepared-CAS
  rejection, stale old-fence rejection, and successful fresh replan. Accepted
  completion with its reference-integrity advance passed in 205.45s. The
  independently live cross-conflict nonce/operation discriminator passed in
  207.21s. Scoped compile and Ruff passed before these terminal runs.
- Exact reproducer rerun reached `5 passed` before the durable-boundary node.
  Its first failure was a contradictory test expectation that required a
  pre-write retry both to finish publication and remain byte-identical; its
  next discriminator proved the retained committed-group recovery performed
  an invalid fresh preflight. Scoped Ruff passes for persistence and the test.
- Durable-boundary closure proof: the corrected JSONL pre-write and
  committed-group lost-ack selector passed in 227.10s. The retained committed
  group remains `planned`, retry preserves its graph/event/projection/conflict
  authority while adding only source finalization, and the next retry is
  byte-identical. The exact 12-case reproducer is running again from its first
  node. The focused persistence/test diff review identity is
  `14f08f49a61caf34d1b2d63333e32125f27fd52a2eb5b9c276c76dc26e7b9e0e`.
- The next exact rerun passed 11 cases in sequence and exposed that its final
  clean-recovery/clarification selector still invoked the now-forbidden
  detached completion helper. That selector now builds two real terminals, a
  canonical conflict submission, a claimed work item, and its exact CAS before
  racing accepted completion with clean recovery. Its focused run passed in
  405.33s and proves two batches before completion, three after completion,
  retained claim/CAS retry, and one receipt/recovery authority.
- Post-repair sibling proof: projection-history plus projection-scheduler
  suites passed 26 cases in 38.13s; JSONL group/finalization lost-ack and
  restart-boundary selectors passed 4 cases in 11.86s. Scoped Ruff,
  `py_compile`, and `git diff --check` pass. The final exact 12-case rerun is
  active.
- Frozen-review recovery remediation: submission lost-ack, accepted completion
  lost-ack, real checkpoint pointer mutation, and real checkpoint immutable
  member mutation all pass (4 focused cases; immutable mutation 122.05s).
  Superseded-result focused race, queue-only, processor, and strict-wire
  families pass; scoped Ruff, `py_compile`, and diff check pass.
- Submission/projection remediation: projection-first passed in 112.02s and
  submission-first passed in 139.60s. Scoped Ruff, `py_compile`, and diff check
  pass; the pre-existing broader submission-proof family was still running
  without failures at the last terminal yield.

## Decision Log

- 2026-08-04: Paused implementation at the deterministic failure boundary and
  routed diagnosis through `$debug-problem`.
- 2026-08-05: Rejected a conflict-specific stale-terminal reset. Governing
  architecture requires planned state to remain one-way and graph-dependent
  retries to append a typed source/group plan lineage. Current code instead
  persists one opaque plan, one terminal artifact, and one group result, so it
  cannot represent the required clarification-winner replan safely. M4 now
  carries the missing typed lineage foundation as an explicit prerequisite:
  exact contracts/codecs, atomic append/current-attempt authority, result and
  finalization binding, then provider reconciliation. Prior artifacts remain
  immutable; no planned-to-preplanning regression is allowed.

## Review Log

- 2026-08-04 frozen linked-debug three-role closure review used
  `HEAD 2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93` plus changed/untracked
  content-manifest digest
  `6636b1e017750a18ad073130655b3151b205fadc279132c5c1b1a22dfcf68a20`.
  Correctness reported no findings. Specification reported two confirmed P2 /
  `changes_required` findings: the supersession result uses the noncanonical
  `successor_conflict_revision` wire field, and a projection-winner stale
  worker raises instead of returning the retained terminal `SUPERSEDED`
  result. Test review reported four gaps. Coordinator classification:
  submission-versus-projection in both orders, production-owned
  clarification-winner replan, and clarification-specific lost-ack/real
  checkpoint recovery are confirmed current-scope gaps. Provider/tool exact
  retry through the verifier is also confirmed, but is the already recorded
  provider/Hermes slice immediately following core debug closure and remains
  an M4 blocker rather than evidence for this debug packet.
- 2026-08-04 focused retained-group lost-ack correctness review reported no
  findings against frozen two-file diff
  `14f08f49a61caf34d1b2d63333e32125f27fd52a2eb5b9c276c76dc26e7b9e0e`.
  The reviewer confirmed new groups still preflight twice against current
  authority, retained groups remain terminal-bound by exact result validation,
  and the test separates pre-write, committed-group lost acknowledgement,
  restart/finalization, and exact retry. This is bounded repair review, not the
  linked-debug three-role closure review.
- 2026-08-04 bounded retry-lifecycle audit confirmed three `P2` /
  `changes_required` findings: queue-only admission accepted semantic terminal
  outcomes without the required transaction closure; a stale historical work
  chain could append while a newer clarification was current; and an expired
  same-token claim was returned as a lost acknowledgement before reclaim.
  Bounded remediation is complete with focused memory/JSONL proof; all three
  findings are classified `already resolved`. This is not the candidate-freeze
  three-role closure review.

## Blockers And Limits

No external blocker. Canonical submission, claim, retry/failure, proof/nonce
authority, semantic completion, and natural-projection supersession are
implemented. Frozen review found the remaining superseded-result recovery,
submission-race, production-replan, and recovery-proof gaps above.
Provider factory, filesystem selection, derived cache, composite listing, and
Hermes composition remain excluded until this debug operation closes.

Production replan is blocked on the explicitly reopened M3 source/group plan-
lineage correction. That approved contract must exist before this operation can
prove clarification-winner replan without a reverse progress transition.

## 2026-09-04 Pre-Code Next Action (Completed)

The sole writer implements the smallest invariant-level correction: original-
fence append-only replan through the existing graph transition authority,
dedicated stale-winner signaling, and public `sync_event` regression proof for
the complete Operation 1 family. Composition and replay/history are excluded.

### 2026-09-04 closure-audit reopening

- Confirmed P2 / `changes_required` / runtime behavior and persistence lineage:
  `derive_conflict_replan_delivery_id` creates a second delivery/source
  admission. The governing architecture requires replanning on the original
  source and fence with append-only predecessor/replacement lineage and exact
  unaffected-group reuse.
- Confirmed P2 / `changes_required` / failure behavior and integrity: the
  coordinator catches every `SemanticEventReplayError` as if it were the stale
  clarification-winner race. Repository freeze, replay, schema, registry,
  checkpoint, and integrity failures must propagate fail closed; only a
  dedicated typed stale-winner signal may start replan.
- The earlier two-attempt passing proof is now a reproducer of the first defect,
  not closure evidence: it explicitly expects two governed admissions and a
  nonterminal original control.
- Root-cause correction and family-complete proof are specified in
  `docs/work/semantic_ingestion/m4-closure-2026-09-04/implementation.plan.md`;
  this debugging WorkPlan remains the sole detailed owner of hypotheses,
  experiments, before/after discriminators, and correction evidence.

### 2026-09-04 pre-code review and binding disposition

- `test_reviewer` required the production happy-path test to reject any derived
  delivery or second admission and required real public-root emitters for the
  stale-winner and non-stale replay/integrity families. Generic exception
  injection is supplemental only.
- `code-mapper` confirmed all production roots converge on the provider
  coordinator and terminal persistence owner, with no original-fence replan
  verb currently wired at that boundary. The correction must connect existing
  graph transition authority; it must not add another root or fallback.
- Review result: both verification findings are confirmed P2 /
  `changes_required`, remediation eligibility `eligible_p1_p2`; no design
  ambiguity and no scope expansion.

### Production replan end-to-end proof complete (2026-09-04)

- `tests/unit/core/semantic_ingestion/test_conflict_replan_production_owner.py`
  `2 passed in 57.55s` through a real configured provider root
  (`provider_service` composition with the scenario normalization host and
  graph bundle builder):
  - `test_stale_projection_publication_replans_once_and_completes`: with the
    proven losing-race signal injected at the exact persistence boundary the
    store raises it, the coordinator persisted exactly twice — the public
    delivery, then `derive_conflict_replan_delivery_id` of it — the replan
    operation reached `terminal`, the stale public operation did not, exactly
    two governed admission indexes were retained, and the public outcome kept
    the ordinary `source_only` shape.
  - `test_second_consecutive_staleness_propagates_fail_closed`: a second
    consecutive staleness propagates `SemanticEventReplayError` after exactly
    two attempts.
- The proof exposed and fixed one real composition defect: a canonical
  evidence arena binds exactly one validation scope, so the replan attempt now
  owns a fresh arena from the provider's canonical-evidence-arena factory
  (closed via `ExitStack` on every exit path of `_ingest_semantic_source`).
- Regression after the arena correction: provider compatibility plus
  conflict-attention provider families `47 passed in 23.70s`; configured-root
  scenario node `initial_attempt-direct` `1 passed in 64.16s`; scoped Ruff,
  compilation, and diff checks clean.

### Production replan owner implemented (2026-09-04)

- `ProviderIngestionCoordinator` now owns the clarification-winner replan at
  the projection-publication seam.  The semantic-source pipeline was extracted
  into `_ingest_semantic_source` with a bounded one-replan loop: when
  `SemanticEventReplayError` (stale compiled graph fence, the deterministic
  clarification-winner signal proven by the reproducer) escapes
  `_persist_semantic_terminal`, the orchestrator re-runs the complete governed
  chain — normalization, governance material, admission, handoff, ingestion,
  publication — under a fresh internal delivery coordinate derived by
  `derive_conflict_replan_delivery_id`
  (`memorii/memorii/core/memory_evolution/ingestion_contracts.py`), a
  domain-separated `conflict-replan:v1:` coordinate that public
  `ProviderEvent` validation rejects as reserved.  A second staleness
  propagates; all other failure classes keep their existing handling; no
  planned-to-preplanning regression and no detached write was added.
- Mapping evidence for the owner choice: the admission index binds one
  delivery identity to one operation fence
  (`admission.py:_recover_exact_admission`), and `persist_terminal_group`
  hard-requires the request graph revision to equal the control's frozen
  revision (`atomic_store.py:10538`), so the lawful replan is a fresh derived
  delivery through the full canonical chain — exactly the shape the
  reproducer's manual replan uses.
- Contract proof: `tests/unit/core/semantic_ingestion/test_conflict_replan_delivery_coordinate.py`
  `4 passed in 12.57s` (domain separation, determinism, parent
  non-embedment, composite distinctness, public reserved rejection, public
  event immutability).
- Regression: exact reproducer both winner orders `2 passed in 243.10s`;
  provider compatibility plus conflict-attention provider service `47 passed
  in 27.40s`; conflict clarification plus provider service `61 passed in
  387.64s`; scoped Ruff, bytecode compilation, and `git diff --check` pass.
- The original exact next action (wire clarification-winner replan) is
  implemented at the coordinator seam; the store-level race proof above
  remains the required closure evidence.
rerun affected families and the exact reproducer, and perform frozen review.

### 2026-09-04 Operation 1 authority-boundary audit (blocked before edit)

- Experiment: traced the public `ProviderMemoryService.sync_event ->
  ProviderIngestionCoordinator -> SemanticTerminalPersistenceService` path and
  the configured bootstrap-graph host/coordinator path. Result: the provider
  loop can only re-enter by deriving a second delivery; it has no original-fence
  replan verb. `BootstrapGraphDependentCoordinatorV3.coordinate(transition=...)`
  accepts only `initial`, `lease_renewed`, and `lease_reclaimed` control-epoch
  transitions. Its existing `_related_conflict_successor` is private and can
  run only after a graph-group CAS reports a related conflict; it has no input
  for the persistence precondition's stale winner or its stale subset.
- Experiment: inspected the original source-control owner. Result:
  `PreplanningOperationControl.state` permits only `preplanning`, `planned`,
  `terminal`, and `lease_recovery_exhausted`; `SourceCheckpointAtomicWriteRequest`
  permits only `preplanning` and `planned`, and the store rejects a
  `planned -> preplanning` transition. There is no persisted request/receipt
  that authorizes the architecture-required
  `planned -> plan_published -> attempt_published -> planned` replacement
  transition or binds its predecessor closure, stale subset, and recovery
  identity.
- Root-cause conclusion: narrowing the generic `SemanticEventReplayError` to a
  dedicated stale-winner subtype is implementable in isolation, but cannot
  satisfy the required public original-fence replan without inventing a new
  persisted replan request/state/receipt and recovery protocol. The currently
  available graph successor routine cannot be safely called from terminal
  persistence because it lacks the necessary predecessor and subset authority.
- Blocker: the governing architecture specifies the target transition, but the
  implementation contains no canonical public authority contract or storage
  transition for a persistence-precondition stale winner. An external owner
  must decide whether to (a) introduce that source-control replan contract and
  its durable recovery semantics, or (b) designate an existing authority
  artifact/owner that can carry the required predecessor, replacement subset,
  and append-only lineage. Implementing either choice changes persisted
  protocol surfaces beyond the assigned bounded correction.

### Coordinator disposition of the proposed blocker

The targeted `correctness_reviewer` challenge confirmed the implementation gap
but rejected the need for an external semantic decision. The approved
architecture already fixes the intermediate progress variants, original-fence
state sequence, predecessor/final-result closure, exact reuse rules, retry
limit, and found-first recovery behavior. Therefore this is a P2 /
`changes_required` implementation gap inside Operation 1, not scope expansion
or an external blocker. The smallest determinate slice is the design-named
replan closure and intermediate progress contracts, a typed replan-or-reload
repository operation, and a coordinator resume entrypoint that reuses the
existing successor compilation/authority/lineage machinery.

## Superseded Next Action

Execute slice 1 of the approved native bridge implementation at
`docs/work/semantic_ingestion/bootstrap-v3-source-progress-bridge-2026-09-04/implementation.plan.md`.
No provider wiring, delivery-derived fallback, composition, replay-history, or
M3 closure work may begin before the native contract and assembler slice passes.

### 2026-09-04 final causal resolution

- The apparent external-decision blocker was rejected: the approved design
  already assigned fresh acquisition to the graph host and exact predecessor
  recovery to the native V3 repository/coordinator.
- The production defect had two parts. The typed group conflict was returned to
  the host without a callable fresh-coordinator resume entrypoint, leaving the
  implemented successor routine unreachable. Separately, group CAS derived its
  before-revision from source-local operation control, so a fresh shared graph
  snapshot still retried against `genesis` after a competing ingestion.
- `coordinate_related_conflict` now carries the typed old-fence conflict into a
  freshly acquired coordinator, reloads exact original-fence bytes, and calls
  the bounded successor. Group CAS derives the expected revision from the sealed
  group read set; generic non-V3 stale-winner behavior remains unchanged.
- The earlier two-ingestion result used fixture graph authority and is not
  production proof. After switching to each genuine public root and the exact
  production `BootstrapGraphHostBundle`, both A and B are admitted but the
  built-in compiler emits unresolved `graph_target_missing`; B does not advance
  graph revision, so A performs no replan. The typed conflict/resume correction
  remains implemented, but its required ordinary-ingestion proof is blocked by
  the separate M3.1 target-planner gap recorded in the linked bridge WorkPlan.

### 2026-09-04 original-fence retry and typed signal progress

- Changed `SemanticTerminalPersistenceService` to translate only the exact
  conflict-vs-projection graph-revision precondition into
  `SemanticConflictProjectionStaleWinnerError`; all other
  `SemanticEventReplayError` instances preserve their identity and propagate.
- Changed `ProviderIngestionCoordinator` to catch only that signal and retry
  on the original `ProviderEvent`/delivery/fence. The retry creates a fresh
  single-scope evidence arena but does not derive a delivery identity, source,
  or admission.
- Replaced the former successor-delivery public-root assertions with original
  fence/one-admission assertions, and added a generic repository-freeze error
  discriminator. `test_second_consecutive_staleness_propagates_fail_closed`
  passed (`1 passed in 23.93s`). The configured-root happy-path and generic
  error runs exceeded the local command-return window after entering their slow
  fixture setup; full family evidence remains pending.
- Commands: scoped Ruff (fixed one import ordering issue), bytecode compile,
  and `git diff --check` passed.
- Remaining required work: introduce and wire the approved
  `GraphDependentReplanClosure`/intermediate progress and original-fence
  replan-or-reload persistence protocol, then prove graph successor reuse,
  restart, concurrency, and real-emitter failure families. This partial retry
  correction does not close Operation 1 or M3.1/M4.

### 2026-09-05 frozen-candidate review reopening

- Candidate `48c6dc5ab3438684b6476b0919a17774c8bdc92b` was rejected by
  final independent review without reopening product scope.
- Confirmed P2 runtime findings: provider graph recovery catches replay and
  integrity failures too broadly; a post-preflight group-CAS conflict becomes
  generic durable retry instead of target-aware rebase or typed related
  conflict.
- Confirmed P2 verification finding: the special related-conflict vector races
  two ordinary ingestions and does not prove that an accepted clarification
  committed through its normal lifecycle stales the already-planned original
  fence.
- Confirmed governance findings: special-row outcome metadata is not bound to
  observed execution, canonical eight-cell production receipts remain
  unvalidated, and linked closure packets retain obsolete blocked/active state.
- The obsolete exact-SHA PR-gate run was cancelled. Its successful CodeQL run
  remains historical evidence only and cannot certify the replacement.

### 2026-09-05 review correction

- Replay corruption now preserves the exact `SemanticEventReplayError` through
  atomic-store, graph-coordinator, and provider recovery boundaries instead of
  being downgraded to a success-shaped retry or generic store error.
- A post-preflight group-CAS conflict first reloads the exact primary. When no
  primary exists it reruns the complete target/read-set preflight from fresh
  replay state, returns the typed related-conflict signal for an overlapping
  winner, and retries an unrelated revision at most once.
- The public `memorii_resolve_conflict` race now commits an accepted
  clarification through the normal lifecycle while a real V3 source is paused
  at group CAS. Memory and independently reopened JSONL prove one admission,
  no second normalization, the original fence, and six typed progress images
  split between predecessor and successor (`2 passed in 232.77s`).
- Unsupported selector effect/call counters were removed rather than promoted
  as evidence. The exact selector/topology/non-disclosure contract remains and
  passes (`11 passed in 6.37s`). The canonical source/binding lock is repinned;
  positive external activation remains the separately scoped M5 obligation.

## Exact Next Action

Finish the replacement local gate run, freeze and push the shared M3.1/M4
candidate, and obtain exact-SHA hosted checks plus independent specification,
correctness, and test review before recording this debugging operation complete.

- Contracts checkpoint: added the closed persisted replan closure, final-result
  and successor-authority unions, policy/counter references, intermediate
  progress variants, and exact pre-planning/planned progress shapes, codec
  registrations, and behavioral mutation proof. Focused contract tests passed
  (`29 passed in 14.05s`); scoped Ruff, bytecode
  compilation, and diff checks passed. Runtime persistence/coordinator wiring
  remains intentionally unmodified, so this checkpoint is partial and does
  not close Operation 1 or M3.1/M4.

- Repository checkpoint: `SourceCheckpointAtomicWriteRequest` now recognizes
  `plan_published` and `attempt_published`; `SemanticIngestionAtomicStore`
  validates the original-fence sequence
  `planned -> plan_published -> attempt_published -> planned`, exact lease and
  predecessor closure preservation, and rejects a typed intermediate through
  the legacy checkpoint fallback. The new
  `AtomicStoreGraphDependentSourceProgressRepository` publishes or reloads the
  exact persisted progress image rather than rebuilding a lost acknowledgement.
  Replay authority decodes all four closed progress discriminators as sealed
  progress members. Focused memory and independently reopened JSONL proof
  passed (`31 passed in 26.36s` including the contract family); scoped Ruff,
  bytecode compilation, and `git diff --check` pass. Provider/coordinator
  invocation, successor compilation, and the broader invalid-transition
  matrix remain for the next checkpoint, so this is partial and does not close
  Operation 1 or M3.1/M4.

- Repository correction: replan predecessor lookup now scans backward through
  append-only terminal-group generations for the latest valid typed `planned`
  image, while rejecting an in-flight `plan_published` or `attempt_published`
  duplicate. The replan closure must partition that prior unfinished group set
  and name exactly the control's retained final-result digests before a new
  plan publication can proceed. Provider/coordinator invocation remains
  excluded; focused partial-commit generation proof is the immediate remaining
  repository test addition.

- Runtime-wiring preflight: the requested binding is not determinate from the
  current canonical owners. The provider's only stale-winner catch is after
  `_run_semantic_ingestion`; normal Bootstrap-V3 execution returns
  `bootstrap_graph_terminal_persisted` and bypasses that generic persistence
  seam. `BootstrapGraphDependentCoordinatorV3` persists exclusively through
  `BootstrapGraphPlanAtomicWriteRequestV3` using
  `BootstrapTransactionGroupPlanV3`, `BootstrapGraphDependentAttemptV3`, and
  `BootstrapSourcePlanLineageV3`. The new original-fence repository accepts
  only `SourceCheckpointAtomicWriteRequest` whose progress models require the
  non-V3 `TransactionSemanticGroupPlanReference`,
  `SourceTransactionPlanLineageReference`, and non-V3 successor/final-result
  unions. There is no converter, shared supertype, or V3 progress-publish
  request/receipt from which those required closed values can be recovered.
  Calling the private `_related_conflict_successor` is also insufficient: it
  accepts only a group-CAS conflict discovered during `_execute_attempt`, not
  the terminal-persistence stale-winner signal, and it recompiles before a
  typed original-fence closure is persisted. A fabricated adapter would violate
  the required byte-identical reuse and durable recovery semantics. This is a
  concrete implementation-boundary blocker, not a reason to add a fallback.

- Independent architecture disposition: the design requires both the generic
  four-state progress boundary and the Bootstrap-V3 exact-reuse grammar, but it
  defines neither a common request nor a normative member-kind mapping and
  reload-equivalence rule. Reverting the generic contracts would violate the
  accepted conformance direction; adding a V3 adapter/request/receipt would
  change persisted semantics. The debugging operation therefore stops pending
  authorization for a separate bounded design delta.

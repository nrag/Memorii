# M3.1 And M4 Completion Operation

- Work ID: semantic_ingestion_m3_1_m4_completion_2026_09_04
- Work type: implementation
- Status: active; Operations 1 through 4 are locally green, candidate freeze,
  hosted checks, and final independent review remain
- Coordinator: Codex main thread
- Created: 2026-09-04
- Last updated: 2026-09-05
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Active milestone packets: `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`; `docs/work/semantic_ingestion/milestones/m4-event-history.plan.md`
- Linked debugging WorkPlan: `docs/work/semantic_ingestion/conflict-authority-proof-failures-2026-08-04/debug.plan.md`
- Linked bridge design WorkPlan: `docs/work/semantic_ingestion/bootstrap-v3-source-progress-bridge-2026-09-04/design.plan.md`
- Linked bridge implementation WorkPlan: `docs/work/semantic_ingestion/bootstrap-v3-source-progress-bridge-2026-09-04/implementation.plan.md`
- Linked conflict-attention debug WorkPlan: `docs/work/semantic_ingestion/composite-cursor-clock/debug-001.plan.md`
- Linked acceptance testing WorkPlan: `docs/work/semantic_ingestion/acceptance-evidence-closure-2026-09-05/testing.plan.md`
- Approved linked design: `docs/work/semantic_ingestion/semantic-conflict-introduction-authority-2026-08-04/design.plan.md`
- Governing architecture: `docs/design/semantic_ingestion_architecture.md`

## Objective

Close M3.1 and M4 at one immutable revision. Correct clarification-winner
replanning so it preserves the original source and delivery fence, append-only
plan and attempt lineage, exact unaffected group bytes, and fail-closed error
semantics. Then finish byte-equivalent replay/history proof and revalidate the
shared M3.1 transaction path before recording either milestone as complete.

## Why Both Milestones Are Active

The 2026-09-04 closure audit found that the recorded M3.1 candidate identity is
not reproducible and that current M4 replanning changes the delivery identity
instead of extending the original operation's plan lineage. The implementation
already present for M3.1 remains useful, but its administrative closure is
reopened until a replacement identity and revision-bound evidence exist.

M4 remains active because the replan behavior and exception boundary contain
two confirmed P2 defects and because replay/history and final closure evidence
have not been completed. The linked debugging WorkPlan is the sole detailed
owner of those two product defects. This implementation WorkPlan owns their
dependency, the remaining replay/history work, and coordinated final closure.

## Completion Contract

Complete only when all of the following hold at the same immutable revision:

- the linked debugging WorkPlan proves clarification-winner replanning on the
  original source and delivery fence, with append-only predecessor/replacement
  lineage and no second source admission;
- only the dedicated typed stale-winner conflict signal starts a replan; all
  replay, freeze, schema, registry, checkpoint, and integrity failures remain
  terminal fail-closed errors;
- unaffected groups and their authorizations/results are reused byte-for-byte,
  while only the exact stale subset is recompiled and appended;
- M3.1 direct, factory, filesystem, and Hermes roots pass accepted-effect,
  restart, lease-reclaim, lost-acknowledgement, and JSONL reopen proof;
- M4 genesis and checkpoint replay reconstruct byte-equivalent active state for
  every active read schema and pass all required adversarial families;
- provider, factory, filesystem, derived-cache, composite, and Hermes pulls
  expose bounded conflict attention without a proactive core callback or an
  inferred winner;
- a replacement candidate identity is generated after code, tests, WorkPlans,
  and evidence are final, and reproduces the exact clean revision and artifacts;
- required local gates and hosted checks execute for that exact revision;
- fresh whole-candidate specification, correctness, and test reviews leave
  `remaining_validated_p1_p2: []`, `remaining_blocks_approval: []`, and
  `remaining_changes_required: []` in both milestone closure records.

Passing focused tests, preserving an earlier candidate identity, or closing one
milestone against a different revision does not satisfy this contract.

## Scope

Included:

- correction and proof of the two confirmed replan defects through the linked
  debugging WorkPlan;
- M4 replay/history, conflict-attention composition, and migration proof;
- M3.1 regression proof for the shared ingestion, plan-lineage, transaction,
  recovery, and production-root surfaces;
- replacement revision identity, deterministic gates, hosted checks, reviewer
  reconciliation, and current-state documentation.

Excluded:

- reopening the frozen equal-version replay decision;
- newest-timestamp winner selection;
- non-atomic after-commit conflict-file append;
- M5 external activation or agent-system quality claims;
- unrelated redesign of semantic ingestion, storage, or provider APIs.

## Constraints And Invariants

- Replan is a transition of the original operation, not a new delivery.
- The durable transition remains append-only:
  `planned -> plan_published -> attempt_published -> planned`, followed by the
  replacement attempt and terminal result.
- Existing source admission, delivery fence, committed group results, and
  unaffected authorization bytes remain authoritative.
- A dedicated typed stale-winner signal is distinct from generic semantic
  replay/integrity failure.
- Unknown lifecycle, schema, registry, checkpoint, or persisted enum values
  fail closed.
- The file ledger remains a recoverable listing/clarification projection; the
  contested projection's memory-plane CAS owns canonical introduction.
- One writer at a time owns overlapping production, test, fixture, and WorkPlan
  edits. Reviewers operate only on a frozen candidate.
- Milestone and requirement coordinates stay out of durable product, fixture,
  workflow, and test identities.

## Work Breakdown And Dependencies

| Order | Operation | Work type and owner | Exit evidence | Dependency | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | Replan failure-family correction | Existing linked debugging WorkPlan | Before/after discriminator; original delivery retained; one admission; exact subgroup reuse; dedicated stale signal; sibling failures remain closed | none | complete locally; retained-attempt, typed related-conflict, and fail-closed sibling proof pass; identical concurrent writes separately prove no false successor |
| 2 | Conflict-attention composition reconciliation | This implementation WorkPlan | Existing provider/factory/filesystem/cache/composite/Hermes paths pass after the replan correction; opt-in and cursor/rotation behavior stay closed | operation 1 | complete locally; included in the final 415-case M4 family |
| 3 | Replay and history closure | This implementation WorkPlan | Genesis/checkpoint byte equivalence for every active schema; permutations, duplicates, corruption, late arrival, trust decay, rekey/merge/split, and migration races pass in memory and real JSONL reopen | operation 2 | complete locally; final 415-case family passed under `-W error` in 2142.04s |
| 4 | Shared M3.1 regression closure | This implementation WorkPlan | Four production roots pass accepted effect, exact retry, restart, lease reclaim, lost acknowledgement, lineage, and independent reopen against the final tree | operation 3 | complete locally; 8 exact-selector receipts cover 232 cases across four roots and two backends, and the receipt union validates |
| 5 | Dual milestone candidate freeze and review | This implementation WorkPlan | Reproducible clean identity; complete local gates; exact-SHA hosted checks; three-role whole-candidate review; empty closure arrays | operation 4 | in_progress |

Do not begin operation 2 until the debugging WorkPlan is complete. Do not freeze
or review a candidate between operations 1 through 4; their shared surfaces
must be reviewed together.

## Operation 1 Acceptance Matrix

The linked debugging WorkPlan must prove this family, not only the currently
passing happy path:

| Case | Required result |
| --- | --- |
| Clarification winner makes one planned projection stale | Same delivery/source/fence; one admission; append one replan transition and replacement attempt |
| Multiple groups, one stale | Reuse unaffected group plan, authorization, result, and terminal bindings byte-for-byte; compile only the stale subset |
| Lost acknowledgement before/after replan publication | Recovery returns the exact persisted transition/result without duplicate effect or admission |
| Second genuine stale-winner race | Deterministic bounded retry policy, typed failure after exhaustion, no partial successor |
| Repository scope frozen | Original `SemanticEventReplayError` propagates; no replan is created |
| Replay/checkpoint/schema/registry/integrity failure | Original typed failure propagates; no replan is created |
| Restart and independent JSONL reopen | Original lineage reconstructs exactly, including predecessor and replacement bindings |
| Concurrent retry of the same delivery | One linearized transition/result; exact retry returns existing authority |

Before code changes, `test_reviewer` must challenge whether the matrix detects
the delivery-identity and overbroad-exception causes. Before closure,
`correctness_reviewer` must challenge the root-cause chain and the exact
subgroup-reuse proof.

## Operation 2 Acceptance Matrix

- Re-run the complete conflict-attention provider and composition families, not
  only delta tests.
- Prove bounded pagination and immutable scope/watermark across reopen.
- Prove cursor corruption, key rotation, cross-principal/tenant/scope reuse,
  disabled composition, and enabled-without-authority all fail closed.
- Confirm the ordinary provider path remains unchanged when composition is not
  explicitly enabled.
- Reconcile documented follow-ups. Anything affecting safe approval is
  reclassified and corrected; genuine P3 items remain explicit follow-up.

## Operation 3 Acceptance Matrix

Inventory every active persisted and read schema before selecting tests. At a
minimum, verify:

- genesis versus signed-checkpoint reconstruction produces byte-equivalent
  authoritative graph, operation, observation, artifact, temporal/trust,
  identity-lineage, conflict, and clarification state;
- order permutations and exact duplicates are deterministic;
- current-writer collisions, historical equal-version conflict, corrupt or
  truncated records, unknown versions, and late arrivals fail closed;
- trust decay, rekey, merge, split, and policy/schema migration preserve their
  documented authority and replay ordering;
- real JSONL close/reopen and checkpoint corruption exercise production
  decoders and repositories, not fixture-only adapters;
- memory and JSONL results agree byte-for-byte where the contract requires
  backend equivalence.

If the inventory changes suite ownership, CI selection, or test architecture,
pause this operation and create a linked testing WorkPlan under
`$design-tests`. Feature-local regression additions remain in this WorkPlan.

## Operation 4 M3.1 Revalidation Matrix

Revalidate the surfaces changed or transitively affected by M4 rather than
relying on the superseded M3.1 evidence:

- direct, factory, filesystem, and Hermes production roots;
- memory and independent JSONL backends;
- accepted effect visibility and exact redelivery;
- lease reclaim and terminal acknowledgement loss;
- append-only source/group plan, attempt, authorization, result, and terminal
  lineage, including multi-group partial replan;
- production-signature isolation from scenario-only authority injection;
- selector manifest, field-aware identity hygiene, static typing, lint, and
  workflow structure.

The historical v81/v82 records remain evidence history only. They cannot be
promoted or repinned as the final candidate.

## Verification And Candidate Freeze

Before candidate freeze:

1. Reconcile the live changed-surface, authority-chain, gate, known-failure,
   identity, and generated-artifact ledgers.
2. Run focused before/after discriminators and complete affected families.
3. Run repository lint, configured type checking, compilation, static-tooling,
   identity-hygiene, WorkPlan-split verification, and diff hygiene gates.
4. Run all workflow-selected unit/integration shards and record exact commands,
   durations, exit status, revision, and tree state.
5. Finalize code, tests, generated artifacts, WorkPlans, and evidence.
6. Freeze one clean commit and generate a new candidate identity that binds that
   exact commit and all coordination artifacts without self-reference drift.
7. Push that revision and require hosted checks to report the same executed SHA
   and intended event/ref. Local runs are not substitutes for hosted evidence.

After freeze, concurrently run `spec_auditor`, `correctness_reviewer`, and
`test_reviewer` over the complete base-to-candidate diff and both completion
contracts. Any confirmed correction invalidates the freeze and returns to the
smallest owning operation. Repeat only after a new identity is generated.

## Finding And Evidence Ledgers

Confirmed findings at plan creation:

| ID | Product priority | Approval disposition | Finding type | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| replan-delivery-identity | P2 | changes_required | runtime behavior / persistence lineage | linked debugging WorkPlan | corrected locally; final candidate review pending |
| overbroad-stale-replay-catch | P2 | changes_required | failure behavior / integrity | linked debugging WorkPlan | corrected locally; final candidate review pending |
| m3-candidate-identity-not-reproducible | Not applicable | changes_required | governance / evidence | dual closure operation | open |
| m4-closure-evidence-incomplete | Not applicable | changes_required | verification / governance | dual closure operation | open |

Affected important scenarios for the P2 findings are clarification-winner
recovery on an admitted provider delivery and fail-closed handling of persisted
replay/integrity failures. Both are required M4 paths, not diagnostics.

Evidence must distinguish deterministic code proof, fake-oracle/plumbing proof,
live provider evidence, hosted CI enforcement, and agent-system quality. This
operation requires deterministic proof and hosted CI where configured; it does
not claim live-provider or agent-system quality unless independently obtained.

## Review And Iteration Policy

- Reviewer findings are advisory until the coordinator verifies and classifies
  them under `AGENTS.md`.
- One writer performs each coherent remediation slice.
- Targeted delta review may validate a bounded remediation, but final closure
  always reviews the whole frozen candidate.
- If a second remediation round exposes the same replan causal boundary, reopen
  the root-cause model instead of adding another case-specific branch.
- Stop for an external decision if a correction would change public or
  persisted semantics not resolved by the governing documents.

## Delegation And Cost Ledger

| Task | Role / tier | Access | Direct consumer | Status |
| --- | --- | --- | --- | --- |
| Operation 1 matrix challenge | `test_reviewer` / Terra-class | read-only | sole writer task packet | complete; changes required to make proof discriminating |
| Replan production binding preflight | `code-mapper` / Spark-class | read-only | sole writer and later reviewers | complete; original-fence API is not wired at the provider boundary |
| Replan failure-family containment | `worker` / Terra-class | sole writer | Operation 1 completion | partial: typed signal and original identity retained; durable resume still missing |
| Replan persisted contracts | `worker` / Terra-class | sole writer | repository/state-machine checkpoint | complete; 29 focused tests pass |
| Replan repository/state machine | `worker` / Terra-class | sole writer | coordinator resume checkpoint | complete; 31 focused tests pass |
| Replan coordinator/provider wiring | `worker` / Terra-class | sole writer | Operation 1 review | blocked before edit by unowned persisted bridge |
| V3 replan boundary decision review | `architect-reviewer` / high | read-only | coordinator blocker disposition | complete; design delta required |

## Review Log

### 2026-09-04 Operation 1 test-matrix consultation

The `test_reviewer` confirmed that all eight cases are relevant but required
three corrections before coding: replace the happy-path test that asserts the
second-admission defect; use real stale-winner versus real persistence-bound
non-stale emitters through public `sync_event`; and assert preserved error
identity plus absence of any replan transition/admission for every non-stale
sibling. The repository-scope freeze remains a distinct concrete case. No
design decision or scope expansion is required.

Coordinator disposition: confirmed P2 / `changes_required` verification gaps
for both product defects; remediation eligibility `eligible_p1_p2`. The revised
matrix is the original eight rows plus these mandatory failure signals.

### 2026-09-04 production-entrypoint preflight

The read-only `code-mapper` traced one canonical provider ingestion owner from
public `sync_event` through `ProviderIngestionCoordinator` and
`SemanticTerminalPersistenceService.persist`. Direct, factory, filesystem, and
Hermes roots converge on that owner. The current provider boundary has no wired
original-fence replan verb; it only loops through
`derive_conflict_replan_delivery_id`. The writer must connect the existing
graph replan/transition authority to the original operation rather than add
another public root or compatibility fallback.

### 2026-09-04 implementation-blocker challenge

The first writer pass correctly stopped before inventing a missing persisted
protocol. A targeted `correctness_reviewer` then confirmed that the runtime gap
is real but the design is already determinate: it specifies the named replan
closure and intermediate progress variants, original-fence state sequence,
exact reuse and retry policy, and found-first recovery. Coordinator disposition:
reject `external_blocker`; retain confirmed P2 / `changes_required` as an
in-scope implementation gap and re-dispatch the same sole writer with that
bounded contract/repository/coordinator slice.

## Progress Log

- 2026-09-04: Earlier M3.1 closure and M4-A/M4-B completion claims were
  independently audited against the closure packets and current code.
- 2026-09-04: Audit confirmed two P2 replan defects, an irreproducible M3.1
  candidate identity, and incomplete M4 replay/history and final evidence.
- 2026-09-04: User requested a completion plan. This WorkPlan coordinates both
  milestones at one final revision without absorbing the debugging ledger.
- 2026-09-04: The refreshed split manifest passes structural verification with
  candidate checking disabled. The required normal and `--self-test` commands
  both stop at `candidate identity git HEAD mismatch`, confirming the recorded
  candidate-identity governance gap; replacement is intentionally deferred
  until the final clean candidate is frozen.
- 2026-09-04: Required pre-code test review and production-entrypoint preflight
  completed. Both converge on the two confirmed defects and add no new scope.
- 2026-09-04: First writer pass found the missing durable replan boundary and
  made no code changes. Independent correctness challenge established that the
  approved design fully determines the missing protocol, so implementation can
  resume without a design change or scope expansion.
- 2026-09-04: The persisted-contract checkpoint added the exact four-state
  progress family, replan closure, final-result and successor-authority unions,
  policy/counter bindings, strict codecs, and mutation proof. The focused
  contract suite passes 29 tests. Provider and repository wiring remain open.
- 2026-09-04: The repository checkpoint added original-fence four-state
  publication, exact found-first reload, strict predecessor/lease binding, and
  independent memory/JSONL reopen proof. The combined focused suites pass 31
  tests. Coordinator/provider invocation and the full failure matrix remain.
- 2026-09-04: Runtime wiring stopped before editing because the live
  Bootstrap-V3 coordinator persists a different plan/attempt/lineage grammar
  and the approved design defines no member mapping or equivalence receipt.
  Independent architecture review confirmed that inventing this bridge would
  be a persisted-contract design change, not implementation wiring.
- 2026-09-05: The final retained-attempt correction now binds replan final
  results to the actual group-result generations, reloads construction through
  `result_digest`, merges exact predecessor and successor results, preserves
  successor commits across a later conflict, and validates target-level CAS
  preconditions so unrelated graph revisions rebase without weakening
  overlapping-write conflicts.
- 2026-09-05: The exact M3.1 selector matrix passed 29 cases for each of direct,
  factory, filesystem, and Hermes roots on both memory and independent JSONL
  backends. All eight receipts bind manifest
  `04d2d65ecdce7a7b74acb2c2930863f388c58b68f2a99d391fb09b9f050638ab`;
  their 232-selector union validates. Focused progress/recovery passed 18 tests
  in 422.16s and the selector contract passed 11 tests in 8.69s.
- 2026-09-05: The complete semantic-ingestion acceptance file passed 200 tests
  under `-W error` in 1071.05s. Identity hygiene, scoped Ruff, compilation,
  diff hygiene, traceability authorities, lifecycle/structural validators, and
  the equal-version decision validator pass on the same working tree.
- 2026-09-05: Configured Pyright initially found 16 missing union/narrowing
  declarations on changed M3/M4 surfaces. Minimal type-only corrections now
  pass with 0 errors and 0 warnings. The final M4 family then passed 415 tests
  under `-W error` in 2142.04s.
- 2026-09-05: Target-level CAS invalidated an old race assumption: two
  byte-identical concurrent ingestions are idempotent and must not create a
  successor merely because the global graph revision changed. The corrected
  test passes in 50.83s with two CAS attempts and six ordinary progress checkpoints;
  the distinct typed related-conflict pair passes 2 tests in 127.84s and
  remains the successor/replan discriminator.
- 2026-09-05: The canonical-evidence binding map, changed-fixture manifest,
  comparison schedule authority, and candidate lock were repinned as one
  digest chain. The fail-closed lock resolver and canonical-evidence adversarial
  self-test pass; the resulting candidate-lock SHA-256 is
  `e84f4bd801d6f44d34f7c300adae4d83bedcb36df7154d2a19f02b4696347d95`.

## Decision Log

- Decision: Reopen M3.1 administrative closure while retaining its implemented
  behavior.
  Rationale: its recorded candidate identity cannot reproduce its declared
  base/artifact set, and M4 correction changes a shared ingestion/lineage path.
- Decision: Close M3.1 and M4 at the same immutable revision.
  Rationale: closure at different revisions would leave M3.1 proof stale after
  M4 changes.
- Decision: Keep the two P2 corrections in the existing debugging WorkPlan.
  Rationale: it is already the sole detailed owner of the causal boundary;
  copying its hypotheses and experiments here would mix work types.
- Decision: Do not delete or rewrite historical v81/v82 evidence.
  Rationale: preserve audit history and create a new reproducible identity only
  after the final candidate is frozen.

## Blockers And Limits

No current local implementation blocker. Hosted CI requires the eventual final
candidate to be committed and pushed after all local gates and reviews are
green. M5 activation and live agent-system certification remain out of scope.

## Latest Bridge Evidence

- The separately bounded built-in target-materialization operation corrected
  the race harness, not the production coordinator: B is scheduled separately
  and held at the same actual group-CAS hook before it is released to commit.
  That identical-write vector correctly rebases without a related-conflict
  successor: it passed on 2026-09-05 with 2 CAS attempts, 2 admissions, 2
  accepted graph effects, and 6 typed progress checkpoints.
- The typed related-conflict fixture now injects the real related-conflict
  signal at the group-CAS owner rather than a generic storage exception. Its
  adjacent focused direct pair passes 2 tests in 127.84s and proves the
  successor path separately from the identical-write rebase case.
- The complete cross-root/backend selector matrix remains Operation 4 evidence;
  no final M3.1/M4 completion claim is made from these focused results alone.

## Exact Next Action

Push the frozen immutable candidate revision and run the required exact-SHA
hosted checks and whole-candidate specification, correctness, and test reviews
before clearing either milestone's closure arrays.

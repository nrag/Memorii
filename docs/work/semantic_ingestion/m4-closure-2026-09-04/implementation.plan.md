# M3.1 And M4 Completion Operation

- Work ID: semantic_ingestion_m3_1_m4_completion_2026_09_04
- Work type: implementation
- Status: active; candidates through `53b5363` are superseded and the bounded
  CI duration-inventory correction is under final local verification
- Coordinator: Codex main thread
- Created: 2026-09-04
- Last updated: 2026-09-06
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
| 1 | Replan failure-family correction | Existing linked debugging WorkPlan | Before/after discriminator; original delivery retained; one admission; exact subgroup reuse; dedicated stale signal; sibling failures remain closed | none | complete locally; retained-attempt, typed related-conflict, fail-closed sibling, disjoint accepted-winner successor, and outside-read-set execution-write proofs pass |
| 2 | Conflict-attention composition reconciliation | This implementation WorkPlan | Existing provider/factory/filesystem/cache/composite/Hermes paths pass after the replan correction; opt-in and cursor/rotation behavior stay closed | operation 1 | complete locally; included in the final 415-case M4 family |
| 3 | Replay and history closure | This implementation WorkPlan | Genesis/checkpoint byte equivalence for every active schema; permutations, duplicates, corruption, late arrival, trust decay, rekey/merge/split, and migration races pass in memory and real JSONL reopen | operation 2 | complete locally; final 415-case family passed under `-W error` in 2142.04s |
| 4 | Shared M3.1 regression closure | This implementation WorkPlan | Four production roots pass accepted effect, exact retry, restart, lease reclaim, lost acknowledgement, lineage, and independent reopen against the final tree | operation 3 | prior full local matrix complete; replacement selector contract and affected roots are green, and exact hosted receipts must be regenerated for the replacement manifest |
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
| m4-cross-module-private-import | Not applicable | changes_required | architecture / gate hygiene | dual closure operation | corrected locally; exact 302-case gate passes |
| corrupt-checkpoint-treated-as-absence | P2 | changes_required | runtime behavior / persisted recovery | dual closure operation | corrected locally; direct/public memory and JSONL proof passes |

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
  successor commits across a later conflict, and validates the complete sealed
  graph read set before every physical group CAS.
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
- 2026-09-05: An intermediate target-level CAS experiment treated a
  byte-identical concurrent ingestion as reusable after the global graph
  revision changed. Whole-candidate review superseded that experiment: the
  complete graph and reference-ledger partitions are globally sealed, so any
  accepted semantic winner requires the typed successor path.
- 2026-09-05: The canonical-evidence binding map, changed-fixture manifest,
  comparison schedule authority, and candidate lock were repinned as one
  digest chain. The fail-closed lock resolver and canonical-evidence adversarial
  self-test pass; the resulting candidate-lock SHA-256 is
  `e84f4bd801d6f44d34f7c300adae4d83bedcb36df7154d2a19f02b4696347d95`.
- 2026-09-05: Whole-candidate review rejected candidate `48c6dc5` because
  replay-integrity errors were still converted at broad exception boundaries,
  the late group-CAS path did not rerun the complete target-aware preflight,
  the public clarification-versus-planned-source race lacked real memory and
  independent-JSONL proof, and the selector manifest claimed counters it did
  not measure. The candidate is superseded and its hosted cancellation is not
  closure evidence.
- 2026-09-05: The bounded corrections now preserve the exact
  `SemanticEventReplayError`, reload the exact primary, and retain the typed
  related-conflict outcome for every accepted semantic winner. The public
  `memorii_resolve_conflict` race passes for memory and independently reopened
  JSONL with one admission, no renormalization, the original fence, and the
  exact typed successor lineage (`2 passed in 232.77s`). Selector outcome
  fields that were not measured were removed; its exact 232-selector/384-tuple
  ownership contract passes (`11 passed in 6.37s`).
- 2026-09-05: The canonical evidence source/binding chain is repinned to the
  corrected production source. Candidate-lock SHA-256 is
  `95729d40afe69f0e58a1ebc97d53445e7c8ed3c95437c8109f34db4542e4c422`;
  the canonical artifact adversarial validator passes. The canonical
  production capture remains honestly `implemented_unvalidated`: positive
  external activation belongs to the expressly excluded M5 operation and is
  not promoted as M3.1/M4 evidence.
- 2026-09-06: The replacement-tree complete semantic-ingestion acceptance file
  passes all 200 tests under warnings-as-errors in 569.71s. Configured Pyright
  reports 0 errors/0 warnings, identity hygiene passes, scoped Ruff and
  compilation pass, diff hygiene is clean, and the canonical-evidence
  adversarial self-test passes.
- 2026-09-06: The replacement-tree projection/history and semantic-ingestion
  integration family passes all 97 tests under warnings-as-errors in 725.17s.
  This reruns the exact 87-case projection owner plus the 10 process/replay
  integration cases after the replay-error and late-CAS corrections.
- 2026-09-06: The affected public-root concurrency and failure-identity
  discriminator passed all 11 parameterized cases (`33 deselected`) under
  warnings-as-errors in 459.06s at the superseded target-level-CAS revision.
  Exact replay-error propagation remains valid; its accepted semantic-winner
  rebase cases are superseded by the complete sealed-read-set correction.
- 2026-09-06: Removing unsupported selector outcome metadata intentionally
  changed the selector manifest digest. The earlier eight local receipts remain
  truthful historical execution evidence but cannot validate the replacement
  manifest. The exact eight replacement receipts and their 232-selector union
  are therefore required from exact-SHA hosted CI before closure.
- 2026-09-06: The broad 185-case conflict-attention collection reached 140
  passes before being stopped after the new JSONL clarification race exceeded
  its 60-second pre-CAS test wait while the terminal suite was running in
  parallel. The same two-backend proof had passed in 232.77s, so the bound was
  below its observed per-backend setup cost under load rather than a product
  assertion. The race now uses one explicit 300-second harness bound and is
  green for both memory and JSONL under the concurrent local load (`2 passed in
  331.40s`); no production behavior or expected outcome changed.
- 2026-09-06: The exhaustive terminal run exposed two obsolete assertions in
  the memory/JSONL divergent-replay-aggregate cases: they expected a generic
  `PreplanningStoreError` from the direct replay-authority API, while the
  reviewed correction deliberately preserves `SemanticEventReplayError`.
  Both executions failed on the required exact typed error after 34 earlier
  passes. The test now distinguishes replay corruption from missing retained
  records and asserts the typed error and message; the complete eight-case
  corruption family passes under warnings-as-errors in 393.70s.
- 2026-09-06: The indexed WorkPlan bundle and its adversarial self-test pass
  structural verification. Its historical dirty-tree review identity remains
  preserved as migration evidence and is deliberately excluded from candidate
  validation; the replacement identity is the clean immutable Git commit that
  follows this final packet state, not a rewrite of the historical identity.
- 2026-09-06: Whole-candidate review rejected candidate `e13df701` because the
  group-CAS authority retained only a digest of the complete `GraphReadSet` and
  could therefore reuse a stale request after a disjoint accepted semantic
  winner changed a sealed partition. Test review also required the public
  clarification race to execute and reopen in separate interpreters with its
  complete typed progress bytes, and required the late-CAS discriminator to
  pause at the physical conditional write. The earlier request for an
  accepted "unrelated retry" was withdrawn: every accepted semantic winner
  changes the globally sealed graph/ledger partitions and is related.
- 2026-09-06: The bounded correction now retains the complete typed
  `GraphReadSet` in every authenticated group-plan member, binds it to the
  enclosing plan digest, and compares the exact record-key, partition-version,
  and manifest vectors immediately before every physical group write attempt.
  Any change raises the existing typed related-conflict signal; an
  outside-read-set execution record neither changes the read set nor conflicts
  with explicit graph CAS preconditions. Discriminating local reruns are in
  progress before the replacement full matrix.
- 2026-09-06: Review of candidate `04a7303` found that its newly retained full
  read set was not yet joined to the legacy token and ledger fields. The
  bounded correction now derives the token from the same sealed store snapshot,
  validates its replay/ledger partitions in the persisted member, and checks
  its graph revision at the pre-effect store boundary. The same review required
  the independent JSONL race to expose and assert its disjoint materialized
  record-intent sets; that assertion is now part of the runner output. The
  digest-recomputed cross-snapshot token rejection passes in the focused
  contract file (`4 passed` total), the physical-CAS discriminator passes in
  memory (`1 passed` in 86.74s), and the separate-process JSONL proof passes
  (`1 passed` in 171.45s).
- 2026-09-06: The fully repinned authority chain is green on the stable tree:
  CTV/workflow/replay-decision tamper coverage passes all 309 tests in 655.39s;
  all four normal production roots pass in 199.33s; the eight root/backend
  outside-read-set execution-write cases pass in 371.10s; and the canonical
  evidence adversarial self-test passes. The persisted-member rejection test
  exercises both memory and an independent JSONL reopen before asserting that
  no group effect exists.
- 2026-09-06: The corrected physical-CAS discriminator passes in memory and
  independent JSONL: the competing accepted source writes disjoint record
  intents, changes the sealed graph/ledger partitions, and forces exactly one
  typed successor while preserving one effect per delivery (`1 passed` in
  83.19s and `1 passed, 116 deselected` in 182.27s). The external execution-
  record family remains correctly nonconflicting (`8 passed` in 391.83s).
- 2026-09-06: The public clarification winner now executes in one child
  interpreter and reopens in a second. Its complete typed progress payloads
  and checkpoint authority (source, request, principal, scope, epoch, lease,
  writer, predecessor, and raw-payload digest) compare exactly; memory also
  passes. The complete progress/recovery family passes 18 tests in 451.76s.
- 2026-09-06: Replacement broad local evidence is green: public acceptance
  `200 passed` in 770.83s; projection/history plus process/replay integration
  `97 passed` in 929.12s; all four normal roots `4 passed` in 222.23s;
  artifact assembler `6 passed`; configured Pyright reports 0 errors/warnings;
  scoped Ruff, compilation, and canonical-evidence adversarial self-test pass.
  The repinned candidate-lock SHA-256 is
  `6952929ab47bdc219e88434faeaef66605c7814e1fc6c0c63f0eb2fe78b11b10`.
- 2026-09-06: Review of candidate `223e0cba` exposed one P2 multi-group
  successor defect and one verification gap. Consecutive replacement groups
  shared one sealed successor snapshot, so the first accepted group made the
  second appear externally stale. The store now admits only the exact durable
  revision chain of earlier groups in the same attempt, while the coordinator
  replans every unfinished group whenever replacement compilation observes a
  changed graph or ledger snapshot. An unchanged snapshot still preserves the
  existing dependency-independent `reused_unfinished` arm. The physical JSONL
  two-interpreter `reused_committed` canary passes (`1 passed` in 142.94s), and
  the unchanged-snapshot `reused_unfinished` discriminator succeeds with all
  three effects and retained arms.
- 2026-09-06: The digest-recomputed cross-snapshot member proof now corrupts a
  real retained lineage checkpoint, including its recomputed plan, progress,
  member, request, and idempotency closure, then invokes the production resume
  repository. Memory and a fresh JSONL reopen both reject with typed
  `PreplanningStoreError` before any group-commit primary exists (`2 passed` in
  106.49s).
- 2026-09-06: Final-tree bounded verification passes the complete 15-case
  source-progress persistence/recovery file in 507.24s and all eight
  `reused_committed`/`reused_unfinished` public-root scenarios in 923.28s. The
  exact 232-selector transaction manifest passes 11 tests, the repinned
  CTV/workflow/replay-decision authority family passes all 309 tests in
  631.57s, configured Pyright reports 0 errors and 0 warnings, and scoped Ruff,
  compilation, diff hygiene, and the canonical-evidence adversarial self-test
  pass on the same tree.
- 2026-09-06: Hosted Benchmark Contract Tests for candidate `21432be` exposed
  a cross-module private-symbol import in the M4 composite conflict listing.
  The shared conflict validators now have public names and the exact hosted
  302-case command passes locally. Final test review also exposed that the
  persisted cross-snapshot corruption proof stopped at the repository API.
  Extending it through public `ProviderMemoryService.sync_event` found a real
  fail-open branch: a corrupt retained checkpoint was treated as absence and
  allowed genesis replanning. The coordinator now treats only the typed
  progress-unavailable condition as absence and returns typed
  `authority_unavailable` for corrupt persisted state. Memory and fresh-JSONL
  public recovery prove the production checkpoint call, zero second admission,
  normalization, or lineage, and zero graph effects; the combined direct/public
  discriminator passes all four cases. The complete affected recovery file
  passes 17 tests under warnings-as-errors in 610.06s; the exact hosted
  Benchmark Contract Tests command passes all 302 tests in 133.92s; and
  configured Pyright reports 0 errors and 0 warnings.
- 2026-09-06: Candidate `53b5363` review found one `Not applicable /
  changes_required / verification-operability` issue: the now 17-case recovery
  module was absent from the duration inventory and therefore underweighted by
  the file-balanced unit-shard planner. A fresh timing-plugin run passed all 17
  cases in 609.56s and measured 601.629s across setup/call/teardown. Recording
  each node and setting the planner target to 720s produces six complete,
  once-only shards estimated at 601.629s and 583.932-583.933s; the slow module
  is isolated and the established 15-minute timeout remains unchanged. Static
  workflow and sharding contract tests pass 28/28.

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

No external or scope blocker. Hosted CI requires the eventual final
candidate to be committed and pushed after all local gates and reviews are
green. M5 activation and live agent-system certification remain out of scope.

## Latest Bridge Evidence

- The separately bounded built-in target-materialization operation corrected
  the race harness, not the production coordinator: B is scheduled separately
  and held at the same actual group-CAS hook before it is released to commit.
  The superseded target-level experiment rebased that winner. The approved
  complete-read-set rule instead treats every accepted semantic winner as
  related because it advances the globally sealed graph/ledger partitions.
- The typed related-conflict fixture now injects the real related-conflict
  signal at the group-CAS owner rather than a generic storage exception. Its
  adjacent focused direct pair passes 2 tests in 127.84s and proves the
  successor path separately from the outside-read-set execution-write case.
- The complete cross-root/backend selector matrix remains Operation 4 evidence;
  no final M3.1/M4 completion claim is made from these focused results alone.

## Exact Next Action

Refresh the split manifest, freeze and push one clean timing-corrected
replacement candidate, and require exact-SHA hosted checks plus
whole-candidate specification, correctness, and test reviews before clearing
either milestone's closure arrays.

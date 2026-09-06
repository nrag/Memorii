# Trust Decay Cutover Integrity Failure

- Work ID: trust_decay_cutover_integrity
- Work type: debugging
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-03
- Last updated: 2026-08-03
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/testing.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `docs/design/event_model.md`; current M4 trust migration and projection scheduler implementation
- Expected outputs: confirmed causal chain, smallest invariant-level fix, deterministic family-complete regression proof, focused gates, and independent closure review

## Objective

Make trust-policy cutover correctly validate and publish a migration result with
nonempty scheduled-decay command membership while preserving fail-closed
corruption detection, CAS serialization, retry, and replay.

## Completion Contract

Complete only when the reproducer fails before and passes after the fix, the
root cause explains command creation through cutover validation, malformed or
substituted membership still fails closed, due-decay/cutover contention has one
committed outcome, focused siblings pass, and independent spec, correctness,
and test review has no unresolved required finding.

## Scope

Included: trust migration command-membership derivation, scheduler persistence
and loading, cutover coordinate validation, due-decay serialization, recovery,
and focused tests.

Excluded: temporal semantics, CI topology, test placement/count/timing, identity
lineage, and unrelated scheduler behavior.

Deferred: broad workflow gates to the parent implementation/testing closure.

## Constraints And Invariants

- Scheduled decay commands remain typed, immutable, digest-bound, and fail
  closed on corruption or substitution.
- Trust migration binds the complete command set for each slot.
- Due decay and trust cutover serialize through the canonical transaction/CAS
  owner; neither may publish stale-policy state.
- Recovery and replay are deterministic and idempotent.
- One writer owns overlapping production and regression-test changes.

## Identity And Coordinate Hygiene

No new durable identity is expected. Any new symbol or test must use behavioral
naming and pass the repository identity gate.

## Change Impact And Verification Closure

| Path or pattern | Surface class | Intended scope owner | Authority chain | Required gates | Status |
| --------------- | ------------- | -------------------- | --------------- | -------------- | ------ |
| `memorii/memorii/core/memory_evolution/projection_scheduler.py` | product code | this debugging WorkPlan | persisted commands -> typed load -> membership validation | focused scheduler/migration tests | under investigation |
| `memorii/memorii/core/memory_evolution/policy_migration.py` | product code | this debugging WorkPlan | migration result -> cutover coordinates -> scheduler membership | focused migration tests | under investigation |
| `memorii/memorii/core/memory_evolution/atomic_store.py` | product code | this debugging WorkPlan | cutover transaction -> epoch CAS -> projection publication | focused atomic tests | under investigation |
| `memorii/memorii/core/memory_evolution/writer_admission.py` | product code | this debugging WorkPlan | governed record classification -> atomic admission | focused migration tests | implemented |
| `memorii/tests/unit/core/semantic_ingestion/test_policy_migration.py` | regression test | this debugging WorkPlan | reproducer -> failure family -> closure proof | exact node and siblings | failing reproducer present |

## Sources Of Truth

Use repository precedence from `AGENTS.md`. The design requires complete
scheduled-decay membership and serialized cutover; current production code and
the deterministic reproducer define the observed failure.

## Current State

The before-fix reproducer deterministically raised
`ProjectionSchedulerError("trust_decay_integrity_error")` before publication.
The implemented fix makes `ProjectionScheduler.prepare_command_records` the
sole encoder/precondition owner for scheduler command records and reuses it in
migration progress and cutover closure. Writer admission recognizes that exact
canonical record shape. Trust results and nested commands are canonically
revalidated before any record or precondition preparation.

Focused evidence now passes for the original reproducer; JSONL reopen; command
tamper; membership omission/addition; both due-decay/cutover winner orders and
literal loser retry; nonempty-command progress/cutover lost acknowledgements;
and pre-persistence nested-command substitution with zero effects. No integrity
predicate was relaxed.

## Assumptions And Open Questions

- Verified: the failure is deterministic in the focused test and occurs before
  cutover publication.
- Verified: migration progress and the scheduler assign incompatible integrity
  digests to the same decay-command record identity.
- Disproved: cutover uses the wrong repository/root or stale snapshot.
- Disproved: the reproducer constructs unsupported state; the public atomic
  cutover path itself persists the incompatible command record before loading it.
- External decisions: none currently.

## Incident Or Symptom

Expected: a valid nonempty scheduled-decay set is bound into trust migration and
accepted at cutover. Actual: cutover rejects it with the same integrity error
used for corrupt persisted scheduler state. Impact candidate: any trust policy
migration for a slot with scheduled decay cannot cut over.

## Reproduction Contract

Run the exact new test node with `PYTHONPATH=memorii`, warnings enabled by the
repository defaults, and cacheprovider disabled. Expected: cutover succeeds and
the command is serialized against due execution. Actual: deterministic
`trust_decay_integrity_error` before publication.

## Timeline

- 2026-08-03: coherent M4 test review identified missing scheduler/migration
  integration proof.
- 2026-08-03: the new focused test produced the integrity failure; writer
  stopped before modifying production.

## Hypothesis Ledger

| ID | Hypothesis | Supporting evidence | Contradicting evidence | Experiment | Result | Status |
| -- | ---------- | ------------------- | ---------------------- | ---------- | ------ | ------ |
| H1 | migration and scheduler encode the same command record with different integrity digests | `_progress_closure` uses command digest while `_load_commands` requires SHA-256 of canonical bytes | none after direct code and runtime trace | trace exact writer and loader predicates | incompatible values confirmed | confirmed root cause |
| H2 | cutover validates through the wrong root/snapshot | failure appears at cutover | exact trace uses the active scheduler/repository and fails a record predicate | compare root identities | roots match | disproved |
| H3 | reproducer constructs unsupported state | test setup is newly authored | public cutover persists caller result through canonical progress before failure | trace public method and persisted closure | supported public state | disproved |

## Experiment Log

The deterministic trace distinguished the hypotheses. Public cutover persists
`TrustMigrationCommittedResult.decay_commands` through
`PolicyMigrationRepository._progress_closure`. Its generic `_authority_record`
stores `authority_digest = command.command_digest`. The next cutover validation
loads the same source kind and memory ID through `ProjectionScheduler`, whose
canonical predicate requires `authority_digest = sha256(canonical_bytes)`. Root
and repository identities match, so the record is rejected solely because two
owners encoded one record contract differently.

## Root-Cause Statement

Trigger: a trust migration result contains at least one future decay command.
Defect: policy migration writes the scheduler-owned command record through its
generic migration-authority serializer, using the domain command digest where
the scheduler contract requires a canonical-byte digest. Propagation: cutover
persists progress, validates current slot membership, and the scheduler reloads
all command records and rejects the newly persisted record. Existing controls
missed the defect because migrations without decay commands never create this
record and scheduler tests use only the scheduler writer. Symptom: deterministic
`trust_decay_integrity_error` before cutover publication.

## Fix Strategy

Make `ProjectionScheduler` the sole encoder of decay-command records and their
absent/digest preconditions. Reuse that preparation from migration progress and
cutover authority closure; retain generic migration result records as the plan-
to-command membership binding. Do not relax scheduler validation or special-case
the reproducer.

## Regression Proof

Required: before/after exact reproducer, malformed/substituted command bytes,
membership omission/addition, due-decay/cutover contention, reopen/replay, and
focused positive scheduler and migration siblings.

## Delegation And Cost Ledger

| Phase | Bounded task | Role and model tier | Writer or read-only | Why this tier | Output or evidence | Status |
| ----- | ------------ | ------------------- | ------------------- | ------------- | ------------------ | ------ |
| reproduce | confirm exact failure and pre-publication state | error-detective, Spark-class | read-only | smallest deterministic evidence | traceback and state snapshot | ready |
| hypotheses | trace creation/load/root identities | code-mapper, Spark-class | read-only | bounded causal mapping | competing-hypothesis evidence | ready |
| challenge | challenge confirmed causal chain | correctness_reviewer, Terra-class | read-only | high-risk persistence judgment | root-cause review | pending |
| fix | implement invariant-level correction and regression family | worker, Terra-class | sole writer | production persistence mutation | focused green proof | pending root cause |

## Progress Log

- 2026-08-03: Opened separate debugging operation and preserved the failing test
  without production changes.
- 2026-08-03: Confirmed dual-writer record encoding as the root cause. Scheduler
  required SHA-256 of canonical bytes while migration used the domain command
  digest under the same record identity.
- 2026-08-03: Centralized command record/precondition preparation in the
  scheduler, reused it from migration, and updated strict writer admission for
  the canonical scheduler record.
- 2026-08-03: Closure review exposed caller-supplied copied results bypassing
  nested validation. Added canonical pre-persistence revalidation and zero-effect
  substitution proof.

## Evidence Log

- Reproducer: `test_trust_cutover_binds_scheduled_decay_membership_before_due_execution`.
- Observed exception: `ProjectionSchedulerError("trust_decay_integrity_error")`
  from `_load_commands()` during `cutover_trust_policy` coordinate validation.
- Before/after: original reproducer failed before the fix and passes after it.
- Focused closure family: six command/membership/race cases passed in 16.59
  seconds; both contention orders plus reproducer passed in 11.61 seconds; the
  original reproducer plus pre-persistence substitution and nonempty-command
  lost-ack recovery passed three tests in 7.80 seconds.
- Focused Ruff passed for projection scheduler, policy migration, writer
  admission, and policy-migration tests.
- Tree identity remains dirty HEAD
  `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`; evidence is local/diagnostic
  until parent closure binds a final revision.

## Decision Log

- 2026-08-03: Stop the implementation operation at the product-defect boundary;
  isolate cause under `$debug-problem` before any product edit.

## Review Log

Initial closure review confirmed the canonical-owner fix and required two
bounded actions: nonempty-command progress/cutover lost-ack proof and canonical
revalidation of copied trust results/nested commands before persistence. Both
were implemented. Targeted spec and correctness review found no remaining
required issue. Test review requested an explicit nonempty-command/same-batch
assertion; it passed and final targeted review found no remaining issue.

## Blockers And Limits

Budget: three discriminating experiments, one fix batch, and one bounded
remediation round. No external blocker.

## Next Action

No active next action. Resume the parent implementation WorkPlan at its temporal
slice closure and identity-lineage milestone.

## Outcome And Retrospective

The defect is fixed at the shared ownership boundary. Scheduler-owned command
records now have one canonical encoder and validator across ordinary scheduling
and policy migration. Invalid copied results fail before persistence; valid
nonempty migrations recover from progress/cutover lost acknowledgement; command
tamper, membership mutation, race losers, retry, and reopen remain fail closed
and deterministic.

Revision-bound closure record:

```yaml
base_revision: 2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93
reviewed_revision: dirty_worktree_at_base_revision
tested_revision: dirty_worktree_at_base_revision
tested_tree_digest: not_applicable (dirty-tree focused diagnostic evidence; parent implementation owns final digest)
tree_state: dirty; scoped debugging changes reconciled, broader M4 changes remain parent-owned
changed_surface_inventory_complete: true for debugging scope
scope_delta_resolved: true
authority_chains_complete: true for scheduler command persistence and migration consumption
required_local_jobs: [focused_debug_regression_family, focused_ruff]
passed_local_jobs: [focused_debug_regression_family, focused_ruff]
known_local_failures: []
failure_exclusions: []
workflow_identities: []
ci_event: not_applicable (linked parent implementation owns CI closure)
ci_executed_sha: not_applicable (no CI run for scoped debugging operation)
ci_executed_ref: not_applicable (no CI run for scoped debugging operation)
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: not_applicable (focused debugging proof only; parent owns full local parity)
acceptance_gate_inventory: []
github_run_urls: []
pr_head_sha: not_applicable (no PR bound to this scoped debugging operation)
pr_base_sha: not_applicable (no PR bound to this scoped debugging operation)
merge_base_sha: not_applicable (no PR bound to this scoped debugging operation)
required_checks_green: not_applicable (parent implementation owns branch checks)
```

---

name: implement-design
description: Implement an approved Memorii design through bounded milestones, deterministic verification, independent review, and remediation.
----------------------------------------------------------------------------------------------------------------------------------------------

# Implement A Memorii Design

Read:

* root `AGENTS.md`
* `.agent/PLANS.md`
* the active implementation WorkPlan
* the canonical design baseline referenced by the WorkPlan
* governing documents selected through the repository knowledge router
* nearby production code and tests

Create or resume a WorkPlan whose work type is `implementation`.

The main thread is the coordinator.

Use exactly one writer at a time for overlapping code, tests, documents, prompts,
schemas, or generated artifacts.

## Phase 1: Establish The Baseline

1. Record the canonical design path and revision.
2. Extract all in-scope requirement IDs.
3. Create or rebuild the requirement coverage ledger.
4. Identify approved deviations and unresolved design questions.
5. Inspect the working tree and preserve unrelated user changes.
6. Identify the production composition root.
7. Identify every affected:

   * public boundary
   * persisted boundary
   * transaction boundary
   * prompt boundary
   * artifact boundary
   * provider boundary
   * adapter boundary
   * integration boundary
   * command-line boundary
8. Identify required migration, rollout, rollback, compatibility, and
   observability work.

If a material semantic choice is not resolved by the design, do not silently
choose one. Record the ambiguity and stop for a decision.

## Phase 2: Plan Bounded Milestones

Divide the implementation into independently verifiable milestones.

Each milestone must identify:

* requirements addressed
* expected files and components
* expected tests
* verification commands
* migration or compatibility implications
* completion evidence

Prefer vertical milestones that produce observable behavior over broad
horizontal rewrites.

## Phase 3: Implement A Milestone

For each milestone, spawn exactly one worker to modify overlapping artifacts.

The worker must:

1. read the controlling documents and nearby tests
2. search for existing types and helpers before adding new ones
3. change canonical schemas and contracts first when behavior requires it
4. update validators, orchestration, and persistence without bypass paths
5. preserve typed public and persisted models
6. keep adapters, integrations, and CLI modules thin
7. add adversarial and failure-mode tests with happy-path tests
8. update current-state documentation in the same change
9. preserve unrelated working-tree changes
10. report:

    * requirements addressed
    * files changed
    * commands run
    * test results
    * known limitations

Do not opportunistically redesign adjacent systems.

Implement the narrowest complete behavior consistent with the design and
architecture.

## Phase 4: Verify The Milestone

Run relevant deterministic checks.

From `memorii/`, the normal local gates are:

```bash
python -W error -m pytest tests/unit -p no:cacheprovider
python -m ruff check memorii tests
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Follow `docs/development/static_tooling.md` for:

* wheel verification
* package verification
* deterministic benchmark smoke commands
* other scoped static checks

Follow `docs/development/benchmark_certification.md` for exact-revision live
certification.

Do not run live provider gates casually. They consume credentials and are
meaningful only with the declared source and run identity.

Record:

* exact command
* working directory
* exit status
* relevant output
* revision and tree state where required

If a required check cannot run, record the reason and the resulting limitation.

## Phase 5: Independent Review

After each coherent milestone, run concurrently:

* `spec_auditor`
* `correctness_reviewer`
* `test_reviewer`

Tell reviewers to inspect the complete current repository state and not trust
the worker summary.

Tell each reviewer to classify findings using the canonical contract in
`AGENTS.md`: product priority, approval disposition, and finding type. Reviewers
must not use `Blocking`, `High`, `Medium`, or `Low` as severity labels or infer
P1 from an approval blocker.

During implementation review:

* `spec_auditor` compares the complete implementation with every in-scope
  requirement
* `correctness_reviewer` checks bugs, regressions, concurrency, security,
  transactions, replay, recovery, compatibility, and integration
* `test_reviewer` checks whether tests prove behavior, including negative,
  boundary, failure, retry, migration, and compatibility cases

Wait for every reviewer.

The coordinator must validate every finding against repository evidence.

Classify findings using `.agent/PLANS.md`.

Send confirmed gaps to one worker for remediation.

After remediation:

1. rerun relevant checks
2. update the requirement coverage ledger
3. update the evidence and review logs
4. set exactly one next action

## Phase 6: Final Branch Review

When all milestones appear complete:

1. run every required deterministic verification command
2. rebuild the requirement coverage ledger from the canonical design
3. compare the rebuilt ledger with the maintained ledger
4. resolve every discrepancy
5. inspect the entire branch relative to its base
6. search for:

   * stubs
   * placeholders
   * skipped tests
   * ignored errors
   * incomplete feature flags
   * dead fallback paths
   * undocumented TODOs
   * stale current-state documentation
7. verify migration, rollout, rollback, compatibility, observability, and
   failure behavior where applicable
8. run fresh whole-branch reviews with all three reviewers

Do not mark a requirement complete based only on test success or agent summary.

Complete the WorkPlan only when the implementation completion contract in
`.agent/PLANS.md` is satisfied.

Report completion as:

"No unresolved validated gaps remain against the canonical design, the recorded
requirement ledger, and the executed verification suite."

Do not claim that no possible defects exist.

Stop as blocked when the WorkPlan stop conditions apply.

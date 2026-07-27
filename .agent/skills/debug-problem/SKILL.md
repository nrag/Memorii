---

name: debug-problem
description: Investigate and fix a complex Memorii failure through reproduction, competing hypotheses, discriminating experiments, causal isolation, regression proof, and independent review.
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Debug A Memorii Problem

Read:

* root `AGENTS.md`
* `.agent/PLANS.md`
* the active debugging WorkPlan, if one exists
* governing documents selected through the repository knowledge router
* the incident report, logs, traces, failing tests, or other initial evidence
* relevant production code and tests

Create or resume a WorkPlan whose work type is `debugging`.

The main thread is the coordinator.

The first objective is to reduce uncertainty. Do not begin by making a
speculative production fix.

Use one writer at a time for code, tests, fixtures, or documentation.

## Phase 1: Establish Expected And Observed Behavior

Record:

* expected behavior and its source
* observed behavior
* impact
* frequency
* affected environments and versions
* known working environments and versions
* first known occurrence
* available logs, traces, artifacts, and reports

Use `spec_auditor` when the expected behavior is ambiguous.

Classify the problem as one or more of:

* implementation defect
* missing or incorrect requirement
* stale documentation
* environment or configuration issue
* dependency issue
* data issue
* test defect
* benchmark or evaluation defect
* operational failure
* unknown

Do not classify an issue as an implementation bug merely because a test fails.

## Phase 2: Build A Reproducer

Create the smallest practical reproduction.

Define:

* required environment
* required data or fixtures
* exact steps
* expected signal
* actual signal
* reproducibility rate
* sources of nondeterminism

Prefer a deterministic failing test when possible.

If reproduction is impossible:

1. state why
2. preserve the strongest available evidence
3. identify what observation would distinguish likely causes
4. avoid pretending that the root cause has been confirmed

## Phase 3: Generate Competing Hypotheses

Spawn read-only agents when useful to inspect:

* relevant execution paths
* state transitions
* persistence and transaction boundaries
* concurrency and lease behavior
* logs and traces
* recent changes
* configuration
* dependency versions
* test fixtures and mocks
* similar historical failures

Create at least two plausible hypotheses when the evidence permits.

Record every hypothesis in the ledger.

For each hypothesis, include:

* causal mechanism
* supporting evidence
* contradicting evidence
* observation that would confirm or weaken it
* proposed experiment

Do not delete disproved hypotheses.

## Phase 4: Run Discriminating Experiments

Choose experiments that distinguish among hypotheses.

For each experiment:

1. identify the hypotheses being distinguished
2. state the expected result under each hypothesis
3. run the smallest safe experiment
4. record the actual result
5. update the hypothesis ledger
6. select exactly one next action

Avoid:

* broad speculative refactors
* adding logging without a stated question
* changing several causal variables at once
* treating correlation as proof
* repeatedly rerunning a flaky test without changing the evidence

Use parallel agents for independent analysis, not overlapping code changes.

## Phase 5: Confirm The Root Cause

A confirmed root cause must explain:

1. the triggering condition
2. the defective assumption, state, or behavior
3. the propagation path
4. why existing validation, isolation, recovery, or tests did not prevent it
5. the observed symptom

Use `correctness_reviewer` to challenge the causal chain and propose serious
alternatives.

Do not proceed to a production fix merely because one hypothesis feels likely.

When immediate mitigation is required, distinguish:

* containment
* mitigation
* root-cause correction

A mitigation does not complete the debugging WorkPlan unless the completion
contract explicitly permits it.

## Phase 6: Implement The Smallest Safe Fix

Create a bounded fix strategy.

Record:

* causal mechanism addressed
* alternatives considered
* expected side effects
* compatibility implications
* migration implications
* rollback plan
* operational monitoring

Spawn exactly one worker for overlapping changes.

The worker must preserve Memorii architecture invariants and must not bypass
validators, typed contracts, transactions, provenance, or lifecycle policy.

Do not hide the symptom by weakening:

* validation
* retries
* tests
* warnings
* benchmark gates
* consistency rules
* failure reporting

## Phase 7: Prove The Fix

Where feasible, demonstrate:

1. the reproducer or regression test fails before the fix
2. the same reproducer or test passes after the fix
3. surrounding deterministic checks pass
4. relevant failure paths remain safe
5. the fix does not violate public, persisted, replay, transaction, temporal,
   or lifecycle semantics

Use `test_reviewer` to confirm that the regression test detects the actual
defect rather than a proxy.

Run relevant normal local gates from `memorii/`:

```bash
python -W error -m pytest tests/unit -p no:cacheprovider
python -m ruff check memorii tests
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Also run narrower reproduction and affected-subsystem tests.

Follow the repository certification documents for benchmark or live-runtime
failures.

## Phase 8: Independent Closure Review

Run concurrently:

* `spec_auditor`
* `correctness_reviewer`
* `test_reviewer`

Tell each reviewer to classify findings using the canonical contract in
`AGENTS.md`: product priority, approval disposition, and finding type. Reviewers
must not use `Blocking`, `High`, `Medium`, or `Low` as severity labels or infer
P1 from an approval blocker.

During debugging closure:

* `spec_auditor` confirms the expected behavior and identifies missing or stale
  requirements
* `correctness_reviewer` challenges the root cause and checks that the fix
  addresses the causal mechanism
* `test_reviewer` checks the reproducer, before-and-after proof, and surrounding
  regression coverage

Wait for every reviewer.

The coordinator must validate every finding.

Update:

* hypothesis ledger
* experiment log
* root-cause statement
* evidence log
* review log
* next action

Complete the WorkPlan only when the debugging completion contract in
`.agent/PLANS.md` is satisfied.

Do not claim certainty beyond the available evidence.

Stop as blocked when:

* reproduction requires unavailable production data or access
* every defensible hypothesis within the experiment budget has been exhausted
* a required semantic decision belongs to an external owner
* the remaining experiment would exceed the agreed risk or scope
* the iteration budget is exhausted

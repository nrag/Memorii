---
name: debug-problem
description: Investigate and fix a complex Memorii failure through deterministic reproduction, competing hypotheses, discriminating experiments, causal isolation, family-complete regression proof, and independent closure review.
---

# Debug A Memorii Problem

Read:

- root `AGENTS.md`
- `.agent/PLANS.md`
- the active debugging WorkPlan, if one exists
- governing documents selected through the knowledge router
- incident reports, logs, traces, failures, code, and tests

Create or resume a WorkPlan whose work type is `debugging`.

The main thread is the coordinator. Use one writer at a time for overlapping
code, tests, fixtures, and documentation.

## Phase 1: Establish Expected And Observed Behavior

Record:

- expected behavior and authoritative source
- observed behavior, impact, frequency, and affected versions
- known working environments and first known occurrence
- available logs, traces, artifacts, and reports

Classify the problem as implementation, requirement, documentation,
environment, dependency, data, test, evaluation, operational, or unknown.
Do not infer an implementation defect merely because a test fails.

## Phase 2: Build A Reproducer

Create the smallest practical reproduction and define:

- environment and input
- exact steps
- expected and actual signals
- reproducibility rate and nondeterminism

Prefer a deterministic failing test. If reproduction is impossible, preserve
the strongest evidence and identify the observation that would distinguish
likely causes.

## Phase 3: Generate Competing Hypotheses

Use parallel read-only agents when useful. Record at least two plausible
hypotheses when evidence permits.

For each hypothesis, include:

- causal mechanism
- supporting and contradicting evidence
- confirming or weakening observation
- discriminating experiment

Do not delete disproved hypotheses.

## Phase 4: Run Discriminating Experiments

For each experiment:

1. name the hypotheses distinguished
2. predict the result under each
3. run the smallest safe experiment
4. record the result
5. update the hypothesis ledger
6. select exactly one next action

Avoid broad speculative changes, multiple causal variables, correlation-as-
proof, and repeated flaky reruns without new evidence.

If two experiments expose variants of the same failure boundary, stop adding
case-specific probes. Enumerate the whole equivalence class and test the shared
invariant.

## Phase 5: Confirm Root Cause

A root cause must explain:

1. trigger
2. defective assumption, state, or behavior
3. propagation path
4. why validation, isolation, recovery, or tests missed it
5. observed symptom

Use `correctness_reviewer` to challenge this chain. Distinguish containment,
mitigation, and root-cause correction.

## Phase 6: Implement The Smallest Safe Fix

Record the causal mechanism, alternatives, side effects, compatibility,
migration, rollback, and monitoring.

Spawn exactly one worker for overlapping changes. Preserve typed contracts,
validators, transactions, provenance, lifecycle policy, warnings, tests,
benchmarks, and failure reporting.

Prefer an invariant-level correction over one branch per reproduced example.

## Phase 7: Prove The Fix

Where feasible, prove:

1. reproducer fails before the fix
2. same reproducer passes after it
3. sibling cases in the equivalence class are covered
4. positive behavior remains valid
5. surrounding deterministic checks pass
6. public, persisted, replay, transaction, temporal, and lifecycle semantics
   remain correct

Use `test_reviewer` to confirm the regression test detects the causal defect.

Run applicable repository gates and record exact commands, environment, exit
status, revision, and tree state.

## Phase 8: Independent Closure Review

Run concurrently:

- `spec_auditor`
- `correctness_reviewer`
- `test_reviewer`

Require reviewers to classify findings under `AGENTS.md`, challenge the root
cause, and report whole failure families rather than isolated sibling examples.

Reconcile all findings before remediation. If a second closure round exposes
the same causal boundary, reopen the root-cause model instead of adding another
patch.

Update the hypothesis, experiment, evidence, and review logs and set exactly
one next action.

Complete only when the debugging contract in `.agent/PLANS.md` is satisfied.
Stop when evidence, authority, scope, risk, or iteration budgets require it.

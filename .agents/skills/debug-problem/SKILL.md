---
name: debug-problem
description: Investigate and fix a complex Memorii failure through deterministic reproduction, competing hypotheses, discriminating experiments, causal isolation, family-complete regression proof, and independent closure review.
---

# Debug A Memorii Problem

Read:

- root `AGENTS.md`
- `.agents/PLANS.md`
- the active debugging WorkPlan, plus the parent index/resume/active milestone
  packet when the failure was discovered inside an indexed operation
- governing documents selected through the knowledge router
- incident reports, logs, traces, failures, code, and tests

Create or resume a WorkPlan whose work type is `debugging`.

The main thread is the coordinator. Use one writer at a time for overlapping
code, tests, fixtures, and documentation.

Apply the delegation task packet, artifact-only context, writer completion,
long-command ownership, and candidate freeze contracts in `.agents/PLANS.md`.
Use Spark-class roles for bounded evidence collection and hypothesis
discrimination; reserve Terra-class judgment for semantic root causes, the sole
writer, and frozen closure review.

Record the debugging result in its own WorkPlan and link it from the affected
milestone packet. Do not absorb debugging hypotheses and experiments into the
parent implementation milestone.

## Phase 1: Establish Expected And Observed Behavior

Record:

- expected behavior and authoritative source
- observed behavior, impact, frequency, and affected versions
- known working environments and first known occurrence
- available logs, traces, artifacts, and reports

Classify the problem as implementation, requirement, documentation,
environment, dependency, data, test, evaluation, operational, or unknown.
Do not infer an implementation defect merely because a test fails.

Inventory affected identities under `.agents/PLANS.md` when the symptom, fix,
or regression proof touches names, schemas, persisted bytes, fixtures,
generated artifacts, commands, or workflows. Treat a leaked milestone or
requirement coordinate as a leaked planning/evidence coordinate and an identity-
governance cause or contributing control failure, not harmless historical
context.

## Phase 2: Build A Reproducer

Create the smallest practical reproduction and define:

- environment and input
- exact steps
- expected and actual signals
- reproducibility rate and nondeterminism

Prefer a deterministic failing test. If reproduction is impossible, preserve
the strongest evidence and identify the observation that would distinguish
likely causes.

Do not label a failure pre-existing or unrelated from memory, an earlier red
run, or a different failure in the same suite. Run the exact command on a clean
worktree at the recorded merge base and require the same causal signature. If
the current diff changes any node in the failure's authority chain, keep the
failure in scope until a discriminating experiment proves otherwise.

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
Name every new or renamed artifact after behavior. Do not carry the incident,
issue, hypothesis, experiment, milestone, or requirement coordinate into a
durable product or test identity.

## Phase 7: Prove The Fix

Where feasible, prove:

1. reproducer fails before the fix
2. same reproducer passes after it
3. sibling cases in the equivalence class are covered
4. positive behavior remains valid
5. surrounding deterministic checks pass
6. public, persisted, replay, transaction, temporal, and lifecycle semantics
   remain correct
7. the affected identity family and sibling spellings are clean, exact typed
   exceptions are ledgered, and the field-aware identity gate rejects a
   representative recurrence

Use `test_reviewer` to confirm the regression test detects the causal defect.

Run applicable repository gates and record exact commands, environment, exit
status, revision, and tree state.

Reconcile the live changed-surface, authority-chain, gate, and known-failure
ledgers from `.agents/PLANS.md`. A focused reproducer proves the correction but
does not replace affected shard, artifact, aggregate, or workflow commands.

For a GitHub Actions failure, read the failing workflow and run the exact failed
job command, its matrix or shard selection, and every aggregate dependency
whose outcome it controls. After the correction is pushed, verify the required
check on its actual event and executed SHA/ref. Local success under a different
runner is diagnostic or locally verified evidence, not CI enforcement.

Before completing any debugging milestone, append the revision-bound closure
record from `.agents/PLANS.md` and require
`remaining_validated_p1_p2: []`. For PR-associated changes, inventory and verify
all scope-required GitHub and external acceptance gates even when the original
defect was not a CI failure.

## Phase 8: Independent Closure Review

Satisfy the candidate freeze gate in `.agents/PLANS.md` before launching the
closure cohort.

Run concurrently:

- `spec_auditor`
- `correctness_reviewer`
- `test_reviewer`

Require reviewers to classify findings under `AGENTS.md`, challenge the root
cause, and report whole failure families rather than isolated sibling examples.

Reconcile all findings before remediation. If a second closure round exposes
the same causal boundary, reopen the root-cause model instead of adding another
patch.

Use `contract_conformance_action` for a determinate identity-governance fix
without manufacturing P1/P2 product impact.

Update the hypothesis, experiment, evidence, and review logs and set exactly
one next action.

Complete only when the debugging contract in `.agents/PLANS.md` is satisfied.
Stop when evidence, authority, scope, risk, or iteration budgets require it.

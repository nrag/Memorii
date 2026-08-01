---
name: design-tests
description: Design, implement, reorganize, or prune Memorii tests and CI verification without weakening coverage. Use when adding substantial test coverage, replacing stale suites, reducing test runtime, deciding unit versus integration or acceptance placement, designing BVT/PR gates, or reviewing test architecture and maintainability.
---

# Design And Implement Tests

Read:

- root `AGENTS.md`
- `.agents/PLANS.md`
- the active testing WorkPlan for long-running work
- governing product designs and implementation paths
- existing tests, fixtures, CI gates, timing evidence, and recent failures

Create or resume a WorkPlan whose work type is `testing` when the work is
long-running. Keep product-semantic changes in a separate design,
implementation, or debugging WorkPlan.

## 1. Establish The Test Contract

For every requirement or risk, record:

- supported behavior and canonical execution path
- defect family the test must detect
- strongest appropriate test level
- oracle and fixture authority
- observable failure signal
- expected runtime and intended gate

Separate evidence gaps from product defects. Missing tests do not establish P1
or P2 without demonstrated product impact.

## 2. Inventory Before Adding

Map existing positive, negative, boundary, retry, replay, concurrency,
migration, compatibility, and failure coverage. Identify:

- exact duplicates and overlapping equivalence classes
- tests bound to retired schemas, fixtures, APIs, or implementation details
- expensive tests mislabeled as unit tests
- fixture generators or trust material shipped in production packages
- tests whose assertions cannot fail when the target behavior regresses
- suites and symbols named after temporary milestones, review rounds, or task IDs

Do not add a new test until its distinct failure signal is stated. Prefer
extending the canonical current-contract suite over creating a parallel suite.

## 3. Design The Suite Topology

Use stable behavioral names. Name files, fixtures, helpers, symbols, and jobs
after the contract they validate, never after internal milestones such as M0,
M1, C2, review rounds, issue numbers, or temporary implementation phases.
Preserve version labels only when they are genuine public, wire, schema,
fixture-format, or migration identities.

Choose the narrowest level that proves the behavior:

- unit: fast, deterministic, isolated logic with no subprocess, packaging,
  network, large artifact generation, or repeated full-system construction
- contract: public/schema/adapter compatibility at one boundary
- integration: interactions between real owners, persistence, subprocesses,
  packaging, restarts, or concurrency
- acceptance: supported end-to-end behavior through public composition
- benchmark or live: performance or provider behavior, kept distinct from
  deterministic correctness

Property or parameterized tests should cover equivalence classes without
copying large case matrices. Keep independent loaders or compilers independent;
do not share the oracle implementation.

Fakes and mocks must model the real boundary's failures and side effects. Do
not mock the service under test, canonical validator, serializer, or transaction
owner. Changed composition roots need at least one proof through the real
adapters and validation path up to the external boundary.

Deterministic suites must not depend on wall-clock time, ambient randomness,
unordered iteration, real networks, or sleeps. Inject clocks, seeds, IDs, and
completion signals. Keep intentionally probabilistic or live evidence outside
deterministic PR proof.

## 4. Budget Runtime And Gates

Measure collection count and wall time before and after material changes. Set a
runtime budget for each suite and gate.

BVT and PR-fast verification must be a small representative sample that gives rapid
signal on mainstream paths and critical trust boundaries. It must not become a
synonym for the full test corpus. Select cases explicitly and record why each
represents a failure family.

Route exhaustive matrices, packaging, large generated artifacts, slow
subprocess tests, broad compatibility permutations, and long-running acceptance
checks to dedicated parallel gates. Preserve full coverage there; do not weaken
assertions, thresholds, warnings, or supported families merely to meet the fast
gate budget.

A dedicated slow-exhaustive gate may still be required on pull requests when it
proves a unique merge-blocking invariant, has a measured budget, and does not
rerun a broad suite merely to add one case. It is not BVT or PR-fast.

Treat unexplained runtime growth as a test-architecture regression. Prefer
shared immutable setup, session-scoped derivation, smaller authoritative
fixtures, and boundary-level proofs over repeated full reconstruction.

## 5. Implement And Prune Together

Use one writer for overlapping tests and fixtures. When replacing a suite:

1. create a case-by-case retention map
2. migrate still-valid behaviors to current-contract owners
3. run the migrated cases and prove their failure signals
4. delete obsolete tests, fixtures, helpers, and CI references in the same change
5. search for stale imports, paths, names, WorkPlan references, and packaged bytes

Do not retain historical tests merely because they once caught a bug. Preserve
the invariant in a current test; remove the obsolete mechanism. Do not delete a
negative suite based only on passing tests or age.

## 6. Verify The Test Architecture

Run focused tests first, then applicable gates. Record:

- selected and collected tests
- pass/fail result and wall time
- before/after count and duration
- gate placement and timeout headroom
- retained, migrated, deleted, and intentionally deferred cases
- source/wheel isolation when fixture authority is test-only

Use mutation, temporary implementation breakage, or an equivalent discriminating
experiment for high-risk tests to prove they fail for the intended reason.

Run independent `test_reviewer` and `correctness_reviewer` passes for a coherent
test-architecture change. Reconcile findings under `AGENTS.md` and the testing
completion contract in `.agents/PLANS.md`.

## Completion

Complete only when requirements map to current tests, every retained test has a
distinct failure signal, obsolete artifacts are removed, suite topology and CI
placement match runtime budgets, fast gates remain representative, exhaustive
coverage remains enforced elsewhere, stable naming is used, and deterministic
evidence passes at the exact revision.

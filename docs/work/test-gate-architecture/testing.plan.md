# Deterministic PR Gate Architecture

- Work ID: test-gate-architecture
- Work type: testing
- Status: active
- Coordinator: Codex main thread
- Created: 2026-08-01
- Last updated: 2026-08-01
- Parent WorkPlan: None
- Related WorkPlans: `docs/work/semantic_ingestion/implementation.plan.md`
- Canonical inputs: `.github/workflows/pr-gates.yml`; `docs/development/static_tooling.md`; `.agents/skills/design-tests/SKILL.md`
- Expected outputs: measured suite topology, deterministic shard manifest and selector, PR and merge-queue gates, validation tests, and CI documentation

## Objective

Keep every required deterministic PR check below 15 minutes as the corpus grows
to approximately 5,000 tests, without weakening proof coverage or making merge
safety depend on an incomplete change-impact guess.

## Completion Contract

- Every deterministic test has exactly one canonical suite owner and remains
  required at a named merge or promotion point.
- Always-run fast, contract, acceptance, exhaustive, and benchmark tiers have
  measured counts, wall times, budgets, and at least 30 percent timeout headroom.
- Full deterministic PR or merge-queue coverage is split into balanced jobs;
  no required job exceeds 10 minutes at the measured baseline or 15 minutes at
  its enforced timeout.
- Any change selector is conservative, explainable, versioned, tested against
  dependency/configuration changes, and falls back to all relevant suites.
- A selector cannot suppress BVT, public-contract, architecture, packaging,
  security/trust, or CI self-tests.
- Scheduled full-corpus runs compare selected versus actually affected tests
  and fail on selector drift.
- Ruff, Pyright, workflow validation, representative counterfactuals, and
  independent test/correctness reviews pass at the exact revision.

## Scope

Included: deterministic unit, contract, integration, acceptance, packaging,
traceability, and fake-oracle benchmark plumbing gates; timing collection;
suite ownership; sharding; conservative impact selection; merge-queue and
scheduled backstops.

Excluded: live-provider certification semantics, product behavior changes,
and reducing test assertions or supported failure families.

Deferred until measured topology is stable: enabling selective PR execution as
a required-check optimization.

## Constraints And Invariants

- GitHub required jobs have a hard 15-minute timeout; target 10 minutes to
  retain at least 30 percent headroom.
- Aggregate CPU minutes may grow, but wall-clock merge latency must remain
  bounded.
- Directory location alone is not a runtime estimate or dependency map.
- Historical coverage data is advisory; configuration, schema, fixture,
  packaging, serialization, and dynamic-dispatch changes require broad fallback.
- Selection must fail open to more testing, never fail closed to less testing.
- Test-only fixtures and trust material remain outside production packages.

## Sources Of Truth

1. Governing product and test contracts in root `AGENTS.md` and
   `.agents/skills/design-tests/SKILL.md`.
2. Current test nodes and execution timings from pytest on the target GitHub
   runner class.
3. Current required checks in `.github/workflows/pr-gates.yml`.
4. Package/import ownership and CI self-tests in production and test code.

## Current State

Verified facts:

- 2,424 unit tests collect in 3.64 seconds locally.
- The latest complete local unit run passed 2,421 tests with two
  capability-based skips in 1,498.59 seconds.
- Collection is uneven: 1,161 non-benchmark core tests, 627 core benchmark
  tests, 567 tooling tests, 50 semantic-ingestion core tests, and 19 others.
- The current 15-minute `Unit Tests` job serially performs dependency install,
  Ruff, Pyright, wheel build/smoke, and the broad unit suite.
- Separate semantic-ingestion acceptance and benchmark-contract jobs already
  prove that stable behavioral tiers are viable, but their overlap and timing
  ownership are not yet measured.

Interpretation: the immediate scaling failure is job topology, not test count
alone. Path-only splitting will be imbalanced, and change selection is unsafe
until ownership and fallback rules are explicit.

## Assumptions And Open Questions

Verified facts: GitHub-hosted runner timing may differ materially from the
local machine; authoritative budgets require CI timing artifacts.

Working assumptions: four to six duration-balanced deterministic shards plus
separate static and packaging jobs can keep a 5,000-test corpus below ten
minutes per job.

Unresolved questions: whether merge queue is mandatory for this repository;
acceptable aggregate GitHub Actions minutes; whether required-check names may
change without external branch-protection coordination.

Decisions requiring external input: approval to make merge-queue full coverage
the authoritative backstop if ordinary PRs later use selective execution.

## Test Portfolio

| Requirement or contract | Behavior and canonical path | Test owner and level | Failure signal | Status |
| --- | --- | --- | --- | --- |
| Mainstream construction and memory operations | Public production composition | BVT / PR-fast | ordinary supported path fails | inventory pending |
| Public schemas and adapters | Typed public boundaries | PR-contract | compatibility or validation drift | inventory pending |
| Package isolation | Built wheel and installed imports | packaging | missing or accidentally shipped artifact | currently bundled; split required |
| Deterministic family completeness | All non-live test nodes | duration-balanced exhaustive shards | any retained invariant fails | currently monolithic |
| Semantic-ingestion authority | Independent compiler, traceability, and acceptance roots | dedicated contract/acceptance | authority or reconstruction mismatch | existing, overlap audit pending |
| Benchmark plumbing | Fake-oracle contracts and artifacts | benchmark-contract | artifact/provenance/plumbing drift | existing, runtime audit pending |
| Change selector safety | Changed files map conservatively to suites | CI self-tests and scheduled audit | under-selection or unexplained mapping | not implemented |

## Equivalence And Failure Matrix

The inventory milestone will map positive, negative, malformed, retry, replay,
concurrency, interruption, migration, compatibility, authorization, and
resource-limit families to one canonical owner. Reorganization may move a test
between gates but may not retire a family without a retention-ledger entry and
replacement proof.

## Suite Topology And Runtime Budget

Proposed topology:

| Tier | Trigger | Purpose | Target budget | Enforcement |
| --- | --- | --- | --- | --- |
| Static | every PR and merge group | Ruff, Pyright, workflow/config checks | <= 5 min | required |
| Packaging | every PR and merge group | wheel build, installed smoke, fixture isolation | <= 7 min | required |
| BVT / PR-fast | every PR and merge group | representative mainstream and trust-boundary signal | <= 5 min | required |
| PR-contract | every PR and merge group | public/schema/adapter/architecture compatibility | <= 8 min | required |
| Deterministic shards | every PR initially; merge group always | complete non-live corpus, balanced by recorded duration | <= 10 min each | required matrix |
| Acceptance | affected PRs and merge group; always for authority changes | supported end-to-end compositions | <= 10 min per shard | required when selected; full merge backstop |
| Benchmark contracts | affected PRs and merge group | deterministic fake-oracle plumbing | <= 10 min per shard | required when selected; full merge backstop |
| Live | manual/scheduled candidate | provider behavior and statistics | separately governed | promotion gate |

The first implementation keeps all deterministic shards on every PR. Selective
execution is enabled only after timing and impact telemetry demonstrate that it
never under-selects during an observation period.

## Test Asset Inventory

Pending inventory of fixtures, generators, golden files, fakes, mocks, trust
material, and shared expensive setup. The inventory must identify package
isolation, consumers, and retirement conditions before suite movement.

## Retention And Retirement Ledger

No tests are approved for deletion. Initial work changes ownership and gate
placement only. Duplicate execution between broad unit, authority, and
benchmark jobs must be measured and reconciled case by case before removal.

## Gate Change Log

Implemented: static analysis and package smoke are independent jobs; four
duration-balanced unit shards preserve full PR coverage; the stable `Unit
Tests` umbrella requires all supporting jobs and the merged timing inventory;
semantic-ingestion generation, scenario, and public acceptance are independent
15-minute jobs. Historical provider recapture is an independent full-history
integration gate, while its lightweight compatibility contracts remain in the
unit shards. No behavioral coverage was deleted.

## Milestones Or Experiments

### T1: Authoritative timing and ownership inventory

- Purpose: measure per-node runtime, setup cost, overlap, and variance on the
  GitHub runner class.
- Artifacts: checked-in suite manifest; CI timing JSON artifact; ownership and
  retention ledgers.
- Verification: repeated full runs produce stable node identities and timing
  distributions.
- Status: complete locally; CI artifact collection installed for GitHub-runner
  calibration.

### T2: Stable tiers and balanced full-corpus shards

- Purpose: separate static/packaging/BVT/contracts and partition exhaustive
  tests by measured duration rather than path or count.
- Artifacts: deterministic shard planner, checked-in manifest, matrix workflow,
  and CI self-tests proving every node is assigned exactly once.
- Verification: union equals the full collected corpus, intersections are
  empty except documented layered gates, and every job stays below budget.
- Status: complete.

### T3: Conservative change-impact model in shadow mode

- Purpose: reduce aggregate PR work without risking merge coverage.
- Artifacts: declarative ownership map, changed-file classifier, fallback
  rules, human-readable selection report, and shadow comparison telemetry.
- Verification: selector runs without suppressing shards; scheduled/full runs
  report every missed dependency and unknown paths select the full corpus.
- Status: pending.

### T4: Selective PR execution with full backstop

- Purpose: enable selection only after demonstrated recall.
- Artifacts: required selector/BVT checks, merge-queue full-shard enforcement,
  nightly drift audit, and documented override for full execution.
- Verification: representative source, test, fixture, config, dependency,
  workflow, packaging, and unknown-path mutations select the required suites;
  merge queue always runs full deterministic coverage.
- Status: pending external decision and T3 evidence.

## Progress Log

- 2026-08-01: Created the testing architecture operation. Collected 2,424 unit
  nodes and recorded the current 1,498.59-second local full-suite baseline.
  Identified the monolithic job and uneven path distribution. Next action is
  T1 authoritative timing and ownership inventory.
- 2026-08-01: Added exact per-node timing capture, conservative timing-manifest
  merge, deterministic whole-module longest-processing-time assignment, and a
  complete/disjoint plan verifier. Split the monolithic unit job into static,
  package, and four exhaustive shards while preserving `Unit Tests` as the
  branch-protection umbrella. Split the 35-minute semantic-ingestion job into
  three 15-minute jobs. After the final workflow and planner tests were added,
  the stable exhaustive inventory contains 2,382 tests. All four exact-evidence
  shards passed in 290.00, 222.93, 218.69, and 223.12 seconds. The complete
  2,382-node manifest predicts 288.94, 217.42, 217.42, and 217.42 seconds.
  Independent correctness and test reviews found no remaining
  `changes_required` issue. T1 and T2 are complete; T3 remains pending.
- 2026-08-01: Diagnosed the first GitHub-hosted shard failure as a shallow
  checkout regression: historical provider recapture requires its pinned Git
  revision, but the new shard checkout omitted full history. Moved that
  subprocess/artifact proof from the unit file into a dedicated integration
  gate with `fetch-depth: 0`, retained lightweight compatibility and tamper
  proofs in unit shards, added failure output that includes child stdout and
  stderr, and replaced 33 requirement/milestone/traceability-coded test names
  with stable behavioral names. Added a workflow regression test preventing
  recurrence while retaining requirement coordinates in traceability data.

## Evidence Log

- `pytest tests/unit --collect-only -q -p no:cacheprovider`: 2,424 tests in
  3.64 seconds.
- Latest full local unit result: 2,421 passed, two skipped, 1,498.59 seconds.
- `.github/workflows/pr-gates.yml`: current `Unit Tests` job combines static,
  wheel, and broad pytest work under `timeout-minutes: 15` (superseded by T2).
- Final exhaustive shard results: 12 passed in 290.00s; 759 passed and one
  skipped in 222.93s; 756 passed and one skipped in 218.69s; 853 passed in
  223.12s.
- `test_shards merge`: exact evidence from all four shards merged 2,382 unique
  node timings only after checking shard identity, plan digest, successful exit
  status, disjointness, and equality with a fresh collection.
- `test_shards verify`: 2,382 collected and measured exactly once; predicted
  shard seconds `[288.942, 217.418, 217.418, 217.418]` against a 600-second
  target.
- Focused workflow and planner regression suite: 33 passed in 108.43 seconds.
- Canonical scoped Pyright: zero errors; focused Ruff: all checks passed;
  package smoke built and installed the wheel and validated the simulator
  artifact.
- Provider compatibility cleanup: 12 lightweight unit contracts plus one
  historical integration recapture passed; workflow contract tests passed;
  the shard planner retained 2,382 collected nodes with all 2,382 timing
  entries after moving the recapture proof out of the unit corpus.
- Semantic-ingestion public acceptance: 207 passed locally in 1,113.03
  seconds; the same PR gate passed on GitHub-hosted Linux in 10 minutes 10
  seconds, within its 15-minute boundary.

## Decision Log

- Decision: use full duration-balanced parallel shards as the primary scaling
  mechanism; do not make change selection the first fix.
- Alternatives: directory splits are simple but predictably imbalanced;
  count-based shards ignore runtime; pytest-xdist alone is bounded by a single
  runner and does not establish stable proof ownership; selection-only is fast
  but can silently miss dependency and configuration effects.
- Consequence: initial aggregate Actions minutes may not decrease, while wall
  time and merge safety improve. Selection remains a later optimization.
- Decision: historical Git recapture is an integration contract, not a unit
  test. Its dedicated gate owns full-history checkout and remains a dependency
  of the stable `Unit Tests` umbrella. Test symbols describe behavior;
  requirement coordinates remain in traceability inputs and registries.

## Review Log

- Test review identified incomplete timing-artifact reconciliation and loss of
  PR runtime-semantic coverage. Both were confirmed and resolved by exact
  shard metadata/union validation and an eight-row simulator/runtime artifact
  matrix. The final test review reported no remaining `changes_required`
  finding.
- Correctness review identified an invalid scheduled invocation of the M2-only
  production runtime path and a missing pytest installation in the timing merge
  job. Both were confirmed and resolved. The final correctness review reported
  no remaining P1, P2, or `changes_required` finding.
- Compatibility cleanup review required exact comparison of every generated
  recapture artifact and identified ten remaining traceability-coordinate test
  names. Both findings were confirmed and resolved. Final test and correctness
  reviews reported no remaining `changes_required`, P1, or P2 finding.

## Blockers And Limits

No implementation blocker. Branch-protection and merge-queue policy become an
external decision before T4. Timing claims remain provisional until measured
on GitHub-hosted runners.

## Next Action

Collect the first GitHub-hosted timing inventory from the M1 pull request and
compare its shard wall times with the local T1 baseline; do not start T3 until
it is separately requested.

## Outcome And Retrospective

T1 and T2 are complete. The repository now has fail-closed, duration-balanced
full-corpus PR shards, exact timing evidence, stable branch-protection umbrella
checks, and independently reviewed 15-minute job boundaries. T3 and T4 remain
outside this implementation increment.

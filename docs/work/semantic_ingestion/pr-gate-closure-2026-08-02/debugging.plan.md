# Semantic Ingestion PR Gate Closure

- Work ID: semantic-ingestion-pr-gate-closure-2026-08-02
- Work type: debugging
- Status: blocked pending publication authorization and current-SHA GitHub CI
- Coordinator: Codex main thread
- Created: 2026-08-02
- Last updated: 2026-08-02
- Parent WorkPlan: docs/work/semantic_ingestion/implementation.plan.md
- Related WorkPlans: docs/work/process/change-impact-verification-closure-2026-08-02/implementation.plan.md
- Canonical inputs: GitHub Actions run 30769171521; current PR 115 tree; current workflows
- Expected outputs: causal corrections for all direct failure families and exact local PR-gate evidence

## Objective

Correct every direct failure family in PR 115 and prove the affected required
jobs and aggregate dependencies against the current tree.

## Completion Contract

Complete when each causal family has a reproducer and correction, all affected
authority-chain artifacts and workflow pins agree, exact failed job commands
pass locally, aggregate dependencies are reconciled, independent closure review
has no confirmed unresolved finding, and current-revision CI state is recorded
without overstating local evidence.

## Scope

Included: traceability authority/cardinality and frozen artifacts, scenario
heading identity consistency, identity-checker architecture compatibility, and
provider diagnostic consistency. Excluded: unrelated feature work and future
semantic-ingestion capabilities.

## Constraints And Invariants

Preserve the approved semantic-ingestion design, deterministic independent
authority verification, behavioral identity policy, provider fail-closed
behavior, and unrelated user changes. Do not weaken a validator or assertion
merely to turn a gate green.

## Identity And Coordinate Hygiene

All fixes use behavioral or genuine protocol identities. The PR, run, and job
numbers remain evidence coordinates in this WorkPlan only.

| Surface | Proposed or existing identity | Class | Behavioral owner or protocol meaning | Retain, rename, migrate, or reject | Proof |
| ------- | ----------------------------- | ----- | ------------------------------------ | --------------------------------- | ----- |
| acceptance evidence group | `semantic-ingestion-normative-traceability-approval` and `semantic-ingestion-acceptance-release-trust` | behavioral identity | approval behavior and trust ownership | renamed from requirement-derived executable values | registry bindings plus acceptance suite |
| acceptance command | `pytest-normative-traceability-approval-v1` and `pytest-acceptance-release-trust-v1` | behavioral identity | exact public acceptance command behavior | renamed from requirement-derived command values | registry command bindings plus acceptance suite |
| active profile scope prose | `scenario-first closure` | behavioral identity | governed scenario closure using typed-value profile v2 | renamed from `C2` scope prose | CTV compiler semantic-scope regression test |
| operational tooling prose | source-only composition and explicitly test-composed runtime artifacts | behavioral identity | current benchmark/runtime composition state | renamed from `M1`, `M2`, and `C2` delivery coordinates | static-tooling tests and repository identity scan |
| structural checker and prototype | `check_cgs_structural_contract_v1.py` and `cgs_structural_manifest_prototype.py` | protocol verification identity | isolated structural authority validation and derivation | retain behavioral names; reject non-isolated execution and stale source identities | workflow exact-argv test and checker self-test |
| old `memorii.semantic-ingestion.m2.v1` bytes | legacy rejection vector | planning-derived retired input | proves unshipped milestone bytes remain unreadable | retain only as two exact allowlisted negative vectors | named decoder rejection tests and field-specific allowlist entries |
| `SIA-Rxx` values | typed traceability metadata | planning/evidence coordinate | requirement-to-evidence linkage | retain only in typed traceability fields and explicit malformed-input vectors | canonical registry and identity checker |

## Change Impact And Verification Closure

| Path or pattern | Surface class | Intended scope owner | Authority chain | Required gates | Status |
| --------------- | ------------- | -------------------- | --------------- | -------------- | ------ |
| semantic-ingestion design, registry, golden vectors, workflow pins | normative and derived authority | traceability worker and coordinator | design -> registry -> compiled/frozen authority -> lifecycle and structural pins -> validators -> shards/aggregates | traceability, generation, scenario, CTV, affected unit shards | corrected and locally verified |
| structural checker CLI, workflow step, documentation, and workflow-contract tests | verification authority | coordinator | frozen inputs -> isolated checker -> external checker identity -> workflow/docs exact argv -> tamper tests | exact checker self-test, CTV PR-gate suite, static analysis, affected shards | corrected and locally verified |
| identity-hygiene implementation and architecture tests | product tooling and tests | identity worker | checker -> architecture contract -> benchmark/static gates -> unit shard | focused tests, benchmark contract, affected shard | corrected and locally verified |
| provider service diagnostic and tests | product code and tests | provider worker | provider validation -> diagnostic contract -> unit shard | provider tests, affected shard | corrected and locally verified |

Known failures are presumed in scope; none is excluded as pre-existing.

The exact acceptance job subsequently exposed a fifth direct family: test
fixture group and command values retained lower-case reformattings of
requirement coordinates after the registry adopted behavioral identities. The
acceptance fixture now uses the registry's behavioral group and command IDs,
and the identity checker is being extended to reject this recurrence.

## Sources Of Truth

Governing semantic-ingestion design and registry, repository implementation
rules, current workflows, and the exact GitHub failure logs already analyzed.

## Current State

Four initial causal families explained the ten reported failed jobs: stale
traceability cardinality, stale derived authority and pins, a checker constant
colliding with the dynamic-import architecture rule, and diagnostic/name
expectation mismatches. Exact full-gate execution then found the same authority-
chain omission in acceptance fixture identities and the lifecycle and structural
checker pins. These were additional members of the same incomplete impact-
inventory family, not independent product defects. Aggregate failures are
downstream consequences.

## Assumptions And Open Questions

Verified: failures are deterministic and revision-bound. Working assumption:
the newly added normative design section is intentional and therefore its
derived authority chain should be regenerated, subject to worker validation.
No user decision is currently required.

## Incident Or Symptom

GitHub Actions run 30769171521 reports failures across traceability,
generation, scenario authority, benchmark contract, and deterministic unit
shards for PR 115.

## Reproduction Contract

Use the exact workflow commands, cwd, warning mode, shard selection, and frozen
inputs from `.github/workflows/pr-gates.yml`. Preserve the causal assertion and
artifact mismatch from each job.

## Timeline

- 2026-08-02: Analyzed ten job failures into four direct causal families and
  two aggregate consequences.
- 2026-08-02: Hardened process instructions before remediation, as directed.

## Hypothesis Ledger

| Hypothesis | Discriminating evidence | Status |
| ---------- | ----------------------- | ------ |
| Registry count and frozen authority were not refreshed after a normative design edit | current cardinalities and digests differ from validators and workflow pins | confirmed |
| Identity checker introduced dynamic-import capability | architecture scanner sees a literal capability name, but runtime checker does not import dynamically | partially confirmed; correction must preserve both invariants |
| Provider and scenario failures are stale textual contracts | production/design text differs from exact test expectation | confirmed |

## Experiment Log

Workers will reproduce each owned family before editing and report exact
commands, signatures, and post-fix results.

## Root-Cause Statement

The implementation changed normative and behavioral surfaces without
reconciling every downstream authority artifact and exact gate contract. The
local closure used a focused test subset and incorrectly dismissed an observed
authority failure instead of following its changed source chain.

## Fix Strategy

Assign non-overlapping failure families to three workers, integrate their
smallest invariant-preserving corrections, then run the complete affected gate
inventory from current workflow definitions.

## Regression Proof

Required evidence includes focused causal tests, all affected deterministic
shards and dedicated authority/benchmark jobs, aggregate dependency checks,
identity hygiene, lint/type checks where touched, and independent spec,
correctness, and test closure review.

| Required local job | Exact workflow-equivalent command family | Status |
| ------------------ | ---------------------------------------- | ------ |
| CTV compiler parity | `pytest -W error tests/unit/tools/test_semantic_ingestion_ctv_reference_compiler.py -p no:cacheprovider` | passed as part of 277-test combined authority family |
| CTV PR-gate tamper tests | `pytest -W error tests/unit/tools/test_ctv_binding_authority_pr_gate.py -p no:cacheprovider` | passed as part of 277-test combined authority family |
| CTV binding authority exact | workflow-pinned isolated checker with current digests | passed: 56 schemas, 249 enum rows, 2 replicas |
| Lifecycle signer and structural manifest authority | workflow/documentation-pinned isolated checkers with current digests | passed: signer 6 accepted/41 rejected/2 replicas; structural self-test passed |
| Generation closure | exactness suite, collection-count assertion, and semantic-ingestion integration/process suite | passed: 39 exactness and 266 integration/process tests; collection 266 |
| Scenario authority | `pytest -W error tests/unit/tools/test_scenario_fixture_authority.py -p no:cacheprovider` | passed: 9 tests |
| Semantic-ingestion acceptance | `pytest -W error tests/acceptance/semantic_ingestion/test_sia_requirements.py -p no:cacheprovider` | passed: 197 tests |
| Benchmark contract tests | complete file list in `benchmark-contract-tests` | passed: 301 tests |
| Deterministic unit shards | shard-plan verification and indices 0 through 3 | passed on final reassigned inventory: 2,733 tests, 3 intentional skips; timing merge contains all 2,736 collected tests |
| Static analysis | Ruff, behavioral identity checker, and Pyright | passed: Ruff and identity checker clean; Pyright 0 errors and 0 warnings |
| Provider compatibility recapture | exact historical provider integration test | passed: 1 test |
| Installable source fingerprint | exact benchmark source-fingerprint integration suite | passed: 9 tests |
| Package smoke | build/install wheel, import ownership and removed-module checks, dry-run artifact validation | passed from isolated installed wheel |
| Aggregates | all dependencies for Unit Tests and Benchmark Contracts | local dependencies reconciled; CI aggregate action remains unexecuted until publication |

## Milestones Or Experiments

1. Correct independent failure families. Status: complete.
2. Execute exact affected local gate inventory. Status: complete.
3. Reconcile independent closure review. Status: in progress.

## Progress Log

- 2026-08-02: Process hardening validated. Next action: dispatch the three
  non-overlapping failure-family workers.
- 2026-08-02: Dispatched traceability-authority, identity-architecture, and
  provider-diagnostic workers with non-overlapping ownership. Next action:
  inventory the exact affected workflow commands while workers reproduce and
  correct their families.
- 2026-08-02: The combined generation/scenario/acceptance run passed generation
  and scenario through the observed point, then exposed 18 acceptance failures
  sharing stale lower-case requirement-coordinate group IDs. Replaced those
  values with registry-owned behavioral group and command IDs; the two-case
  positive reproducer and Ruff now pass, and dispatched identity-checker
  mutation coverage for the missed spelling family. Next action: finish the
  identity control correction, then rerun the full acceptance job.
- 2026-08-02: Exact semantic-ingestion acceptance rerun passed all 197 tests in
  1182.98 seconds. The expanded checker then found one unshipped requirement-
  derived value in the design's old-to-new mapping table. Next action: remove
  that value and regenerate the CTV authority and workflow pins from the final
  design bytes.
- 2026-08-02: Removed the final unshipped requirement-derived mapping value,
  regenerated the CTV authority, and reconciled its design, registry,
  authority, validator, checker, workflow, documentation, and test pins. Exact
  CTV verification passed with 56 schemas, 249 enum rows, and two replicas.
  The combined compiler/tamper family passed all 277 tests.
- 2026-08-02: The first complete shard run exposed two downstream current-
  source authorities omitted from the original ledger: lifecycle signer
  provenance and the structural graph manifest. Updated their current design
  and registry pins, regenerated the structural vector, updated checker
  identities in workflow/documentation/tests, and passed both self-tests. Next
  action: complete corrected shard indices 1 and 2.
- 2026-08-02: All four workflow-equivalent shards passed: index 0 (12), index
  1 (937 passed/1 environment-guarded skip), index 2 (712 passed/1 environment-
  independent contract skip), and index 3 (1,070 passed/1 environment-guarded
  skip). The two process-semaphore tests are unavailable in this sandbox; the
  prompt-contract parametrization intentionally skips a prompt with no
  structured input. Focused `-rs` reruns confirmed all three reasons. The
  timing merge accepted all 2,734 collected tests. Static
  analysis, provider recapture, source fingerprint, and isolated installed-
  wheel smoke verification also passed. Next action: reconcile independent
  spec, correctness, and test closure reviews.
- 2026-08-02: Independent review found no P1/P2 product defect, but confirmed
  four `Not applicable / changes_required` verification-governance defects:
  residual active `C2` scope prose, a dated WorkPlan used as checker authority,
  an unpinned structural checker, and non-isolated structural execution. The
  coordinator removed the WorkPlan dependency, made `-I` mandatory, added an
  externally supplied checker identity and mutation self-tests, added the exact
  structural command to PR CI and workflow-contract tests, replaced the active
  scope prose with behavioral terminology, and regenerated all affected CTV,
  lifecycle, structural, workflow, documentation, and test pins.
- 2026-08-02: Material remediation invalidated the earlier gate evidence and
  changed the deterministic shard assignment. Re-executed the final exact
  inventory: CTV compiler parity 259 passed, CTV PR gate 20 passed, generation
  exactness 39 passed, semantic integration/process 266 passed, scenario 9
  passed, acceptance 197 passed, final shards 12/897/707+1 skip/1117+2 skips,
  and final timing merge 2,736. Next action: fresh post-remediation independent
  closure review.
- 2026-08-02: Post-remediation review then proved that the isolated checker
  still called a prototype which did not reject direct non-isolated startup.
  Added fail-closed isolation to the prototype and an explicit non-isolated
  prototype mutation to the checker self-test. The prototype source identity
  changed from `b655f474...` to `45a8403c...`; propagated it through the
  checker, workflow, tooling documentation, production execution evidence,
  scenario fixture authority, acceptance, and generation-admission assertions.
  The checker identity changed from the stale intermediate `940b9ec2...` to
  final `3f5ba86e...` and is externally pinned in workflow, documentation, and
  tests.
- 2026-08-02: Frozen tracked diff digest
  `107fb40048014d1c39570eb9b4f20f5766c0f927dd896b355aa64245727e38b5`.
  Final replacement evidence after the prototype edit: structural self-test
  passed; CTV PR-gate 20 passed; generation admission 25 passed; generation
  exactness 39 passed; scenario 9 passed; public acceptance 197 passed; shard 1
  897 passed, shard 2 707 passed/1 intentional skip, shard 3 1,117 passed/2
  sandbox capability skips; shard 0's unchanged 12-test inventory remains valid;
  final timing merge accepted all 2,736 tests. Ruff, identity hygiene, Pyright,
  and `git diff --check` passed on the same tracked diff. Next action: fresh
  independent review of this exact digest.

## Evidence Log

GitHub run: https://github.com/nrag/Memorii/actions/runs/30769171521

```yaml
base_revision: 2cf7fde9f969b2a2fda1f4719c307ae0c7df2c09
reviewed_revision: 107fb40048014d1c39570eb9b4f20f5766c0f927dd896b355aa64245727e38b5
tested_revision: 107fb40048014d1c39570eb9b4f20f5766c0f927dd896b355aa64245727e38b5
tested_tree_digest: 107fb40048014d1c39570eb9b4f20f5766c0f927dd896b355aa64245727e38b5
tree_state: dirty_worktree
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: true
required_local_jobs:
  - ctv-compiler-parity
  - ctv-pr-gate
  - ctv-authority-exact
  - lifecycle-signer-provenance
  - structural-manifest-contract
  - semantic-ingestion-generation
  - semantic-ingestion-scenario
  - semantic-ingestion-acceptance
  - benchmark-contract-tests
  - deterministic-unit-shards
  - static-analysis
  - provider-compatibility
  - package-smoke
passed_local_jobs:
  - ctv-compiler-parity
  - ctv-pr-gate
  - ctv-authority-exact
  - lifecycle-signer-provenance
  - structural-manifest-contract
  - semantic-ingestion-generation
  - semantic-ingestion-scenario
  - semantic-ingestion-acceptance
  - benchmark-contract-tests
  - deterministic-unit-shards
  - static-analysis
  - provider-compatibility
  - package-smoke
known_local_failures: []
failure_exclusions: []
ci_event: not_executed_unpublished_worktree
ci_executed_sha: null
required_checks_green: false
remaining_validated_p1_p2: []
```

## Decision Log

- 2026-08-02: Keep traceability artifacts and scenario heading consistency
  under one writer because they overlap the canonical design authority chain.

## Review Log

- Spec audit: approved frozen diff `107fb400...`; DREV-001 through DREV-004
  closed and no remaining local specification or implementation gap.
- Correctness review: approved frozen diff `107fb400...`; no remaining code,
  authority-chain, or workflow defect.
- Test review: approved local closure at frozen diff `107fb400...`; no weakened
  assertion or unowned local test surface remains.
- All reviewers separately classified unpublished current-SHA GitHub CI as an
  external publication condition, not a P1/P2 or local code defect.

## Blockers And Limits

Local implementation and review are complete. The remaining blocker is external:
the user has not authorized committing/pushing this dirty worktree, so GitHub CI
cannot execute against the reviewed tree. Local evidence is not mislabeled as
CI evidence.

## Next Action

Obtain user authorization to commit and push the frozen tracked diff, then run
and record required GitHub checks against that exact published SHA.

## Outcome And Retrospective

Pending.

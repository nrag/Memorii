# PR 114 CI failure debugging

## Objective

Restore the four failing PR 114 gates without weakening their contracts, and prove the correction with the exact failing GitHub Actions commands.

## Expected and observed behavior

- Expected: benchmark-contract and unit-shard jobs pass for the PR revision.
- Observed: `test_dynamic_import_capabilities_have_explicit_owners` rejects the new dynamic import in `bootstrap_profile.py`; the benchmark-contract and unit-test aggregate jobs then fail transitively.

## Hypotheses

1. The new, intentional bootstrap-profile dynamic import lacks an explicit entry in `DYNAMIC_IMPORT_OWNERS`. Supported by both Actions logs and a local reproduction.
2. The failure is specific to the Actions Python or runner environment. Disproved by the local reproduction.
3. The four supplied jobs contain independent failures. Disproved: the two aggregate failures are downstream of the same failing test in benchmark contracts and unit shard 3.

## Scope and constraints

- Preserve the dynamic import needed for validated optional bootstrap sources.
- Do not weaken or bypass the architecture test.
- Limit the correction to registering the capability's explicit owner unless verification reveals a distinct defect.
- Preserve all unrelated dirty-worktree changes.

## Verification contract

- Run the isolated failing architecture test.
- Run the exact benchmark-contract test command from `.github/workflows/pr-gates.yml`.
- Run unit shard 3 through the repository shard runner.
- Obtain independent correctness and test-coverage closure review.

## Progress

- 2026-08-02: inspected all four supplied job logs and reproduced the architecture failure locally.
- 2026-08-02: classified one root cause and received user approval for the narrow correction.
- 2026-08-02: registered the bootstrap module's dynamic capabilities without weakening the ownership boundary; strengthened the boundary to compare complete per-file capability categories and added adversarial category-expansion coverage.
- 2026-08-02: the exact benchmark-contract command passed with 301 tests.
- 2026-08-02: the exact shard-3 command exposed and then verified the correction of an independent behavioral-naming violation; the final shard passed with 840 tests.
- 2026-08-02: Ruff and `git diff --check` passed. Independent spec, correctness, and test reviews were reconciled; no validated P1/P2 implementation defect remains in this debugging scope.

## Outcome

Complete. The supplied aggregate failures were downstream of the benchmark architecture failure. The final exact job partitions pass locally. GitHub Actions remains the authority for Linux/Python 3.11 runner enforcement after the branch is pushed.

## Next action

None; the debugging objective is complete.

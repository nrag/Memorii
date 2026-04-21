# GitHub PR Gates Plan

This document defines a practical PR-gating strategy for Memorii so pull requests cannot be merged unless unit tests pass.

## Gate design

### Required merge gate

- **Gate**: `Unit Tests` GitHub Actions check from `.github/workflows/pr-gates.yml`.
- **Policy**: Mark this check as **Required** in branch protection for `main`.
- **Result**: A PR to `main` cannot be merged unless unit tests are green.

### Why this gate first

- Unit tests are already present and map directly to core invariants in the project architecture.
- This gives immediate quality protection while keeping CI fast.

## Workflow details

Workflow file: `.github/workflows/pr-gates.yml`

- Trigger on `pull_request` to `main`.
- Trigger on `merge_group` to support GitHub merge queue usage.
- Use Python 3.11.
- Install dev dependencies via `pip install -e '.[dev]'`.
- Run: `pytest tests/unit`.
- Test import path is pinned in `memorii/pyproject.toml` (`[tool.pytest.ini_options].pythonpath = ["."]`) so `pytest tests/unit` behaves consistently in local and CI environments.

## GitHub settings plan (what to change in UI)

Apply these in **GitHub → Settings → Branches → Branch protection rules** for `main`:

1. **Require a pull request before merging**.
2. **Require status checks to pass before merging**.
3. Add required check: **`Unit Tests`**.
4. **Require branches to be up to date before merging** (recommended).
5. Optional hardening:
   - Require approvals (e.g., 1).
   - Dismiss stale approvals when new commits are pushed.
   - Restrict who can push directly to `main`.

If you use merge queue, also enable it and keep `merge_group` trigger in the workflow.


## Do we need GitHub environment files?

Short answer: **no** for this unit-test gate.

- This workflow does not require secrets, deployment environments, or custom environment-level variables.
- You do **not** need to add `.env` files to the repository for GitHub Actions.
- You only need the workflow file plus branch-protection settings that require the `Unit Tests` check.

When you *would* use GitHub environments:

- If a job needs protected secrets (e.g., deploy tokens).
- If you want required reviewers/approvals before running deployment jobs.
- If you need environment-scoped vars/secrets with audit controls.

For PR unit tests specifically, environment configuration is optional and usually unnecessary.

## Rollout sequence

1. Merge this workflow to `main`.
2. Open a small test PR and verify the `Unit Tests` check appears.
3. Add the branch protection required-check setting for `Unit Tests`.
4. Re-run test PR to verify merge is blocked on failing tests and allowed on passing tests.

## Future gate expansion (optional)

After unit tests are stable, add additional required checks in a controlled sequence:

1. lint (`ruff check .`)
2. formatting (`black --check .`)
3. type checks (`mypy memorii`)
4. integration tests (`pytest tests/integration`)

Keep each gate as a separate named job so branch-protection checks stay explicit and debuggable.

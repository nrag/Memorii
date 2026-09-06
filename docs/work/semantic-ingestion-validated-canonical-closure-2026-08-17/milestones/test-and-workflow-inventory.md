# Test And Workflow Inventory

- Working revision: `b9daf00a0e6956e51106756f1baaf23190c688bb`
- Evidence status: read-only mapping and command inventory only.

## Candidate-and-Binding Readiness Commands

| Command | Runtime | Status |
| --- | --- | --- |
| `python3.12 validate_candidate_manifest_v12.py --expected-candidate-lock 1e314415930bd43b176b50c28ba8f8b8250a7fa5d959758bc60acd47fc47b2ca` | Python 3.12 in repository worktree | Passed |
| `python3.12 validate_production_entrypoint_bindings_v11.py` | Python 3.12 in repository worktree | Passed (`mutation_count: 32`, `expected_mutation_count: 32`) |

## CI workflow inventory (directly read)

- `.github/workflows/pr-gates.yml`
  - `static-analysis` (Ruff + identity hygiene + pyright)
  - `unit-test-shards` (4 shards, `tests/ci/unit-shards.json`)
  - `semantic-terminal-persistence` (7 shards)
  - `unit-tests` aggregator job
  - `provider-compatibility` and `ctv-binding` gates
- `.github/workflows/benchmark-scheduled.yml`
  - manual or scheduled live statistical gate keyed by candidate SHA and clean tree requirement
  - merges certification artifacts against exact commit in merge/group context

## Local deterministic commands from `docs/development/static_tooling.md`

- `python -W error -m pytest tests/unit -p no:cacheprovider`
- `python -m memorii.tools.test_shards verify --config tests/ci/unit-shards.json`
- `python -m memorii.tools.test_shards run --config tests/ci/unit-shards.json --index <0..3>`
- `python -m memorii.tools.test_shards verify --config tests/ci/semantic-terminal-persistence-shards.json`
- `python -m memorii.tools.test_shards run --config tests/ci/semantic-terminal-persistence-shards.json --index <0..6>`
- `python -m ruff check memorii tests`
- `python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json`
- `pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"`

## Test inventory grouped by scope

- Unit + sharded suite: `tests/unit` (mapped by `tests/ci/unit-shards.json`, command-owner: repository).
- Semantic terminal persistence: dedicated 7-shard suite (`tests/ci/semantic-terminal-persistence-shards.json`).
- Provider compatibility and recapture: `tests/unit/core/semantic_ingestion/test_provider_compatibility.py` and integration recapture harness.
- Deterministic oracle tests: design traceability commands in `docs/development/static_tooling.md` and `docs/development/benchmark_certification.md` (governance, not implementation-only).

# Scoped Context Testing Report

## Completed Slice

Focused tests now prove blank request identity and failure-envelope non-disclosure,
typed corrupted-snapshot handling, optional provenance omission, real Hermes
factory composition, and filesystem-root composition. The dedicated workflow
job is an explicit dependency of `unit-tests`; its owner ledger records a
60-second budget and 540-second timeout headroom. Unit timings were measured
on 2026-09-06 with Python 3.12.14 and recorded for all nine scoped unit nodes.

## Commands And Results

`../.venv/bin/python -W error -m pytest -q tests/unit/core/test_scoped_context_activation.py tests/integration/test_scoped_context_production_binding.py tests/unit/tools/test_static_tooling_config.py -p no:cacheprovider` passed: 29 tests in 26.37 seconds.

`../.venv/bin/python -m ruff check tests/unit/core/test_scoped_context_activation.py tests/integration/test_scoped_context_production_binding.py tests/unit/tools/test_static_tooling_config.py memorii/core/scoped_context/service.py memorii/core/scoped_context/contracts.py memorii/core/provider/service.py` passed.

`../.venv/bin/python -m memorii.tools.test_shards verify --config tests/ci/unit-shards.json` passed: 3,551 collected, 3,486 measured; maximum estimated shard time 601.629 seconds under the 720-second limit.

## Remaining Matrix

This bounded evidence is incomplete for the approved exhaustive matrix. The
18 structured purpose/kind pair guard, full both-root R01--R10 mutation matrix,
barrier-based revocation/reprovision, fresh JSONL authority recreation,
source-lifecycle closure, exact source transitive closure, and one-attempt
fault matrix still need their integration proofs. `production_entrypoint_bindings`
also remains partial because the approved design records zero non-test callers.

## Root Completion Evidence

The focused real-root suite now covers both Filesystem and Hermes composition
for all six mandatory domains under scorer outage, blank query, optional item
overflow, mandatory overflow short-circuiting, authorized semantic/episodic
selection, snapshot mutation isolation, typed dependency faults, unexpected
fault propagation, exact namespace matching, finite all-null grants, and
malformed candidate filtering. It also proves factory/filesystem/Hermes deny
without an injected authority and do not call `prefetch` as a fallback.

2026-09-06 local focused command:
`../.venv/bin/python -W error -m pytest -q tests/integration/test_scoped_context_production_binding.py -p no:cacheprovider --durations=20`
passed 109 tests in 17.61 seconds. The slowest individual cases are the two
fresh-process JSONL reopen checks (4.96 and 4.75 seconds); all newly added root
cases are at or below 0.08 seconds. The dedicated integration job remains
within its 60-second budget. Unit timing entries remain limited to unit nodes;
the integration file is owned by the dedicated scoped-context job.

The complete focused command, including the retained unit and workflow
structure proofs, also passed on 2026-09-06:
`../.venv/bin/python -W error -m pytest -q tests/unit/core/test_scoped_context_activation.py tests/integration/test_scoped_context_production_binding.py tests/unit/tools/test_static_tooling_config.py -p no:cacheprovider`
reported 135 passed in 39.54 seconds. The static-tooling duration entries remain
measured; no full-evolution scoped test remains in the unit duration manifest.

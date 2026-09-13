# Observation Snapshot Contract Worker Report

- Scope: profile-3 `GraphObservationRecordKey`,
  `GraphObservationCohortPreimage`, `ResolvedGraphObservationCohort`, and
  `GraphObservationCursorPayload` model bodies only.
- Status: complete for this bounded schema slice; registry-publication and the
  parent milestone remain partial.

## Changed Paths

- `memorii/memorii/core/memory_evolution/graph_observation_snapshot_contracts.py`
  defines the four strict, frozen, extra-forbidden profile-3 roots. It uses the
  closed 17-kind profile-3 record set, requires cohort projection digest pairs,
  enforces sorted/unique/disjoint changed and boundary keys, and adds the
  required nonnegative cursor write revision. The preimage contains no cohort
  digest; the resolved cohort adds that field without any legacy digest logic.
- `memorii/tests/unit/core/memory_evolution/test_graph_observation_snapshot_contracts.py`
  covers valid model bodies, preimage/resolved field separation, invalid pairs
  and overlapping keys, cursor coordinate failures, and coexistence with the
  untouched legacy cursor foundation import.

## Boundary And Verification

This schema owner does not sign or decode cursors, derive self-digests, issue
tokens, retain snapshots, page streams, access storage, or claim a production
caller. Profile-3 signing and digest verification remain protected-decoder
work; historical v1 cursor models and wire codecs remain untouched. No
`production_entrypoint_bindings` update applies.

- Passed: `.venv/bin/ruff check` for the module and feature-local test.
- Passed: `.venv/bin/pyright --pythonpath "$PWD/.venv/bin/python"` for both
  paths, with `0 errors, 0 warnings, 0 informations`.
- Passed: `compileall` and `git diff --check`.
- Not run by this worker: pytest, per coordinator ownership.

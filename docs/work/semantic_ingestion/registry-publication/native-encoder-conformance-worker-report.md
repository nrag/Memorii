# Native Encoder Conformance Report

- Scope: construction-only correction of profile-3 native CTV emission in
  `memorii/memorii/core/memory_evolution/typed_value_model_codec.py`, with
  focused emission proof in
  `memorii/tests/unit/core/memory_evolution/test_typed_value_model_emission.py`.
- Base revision: `191826cd3afb38bf605a337a71d576063b3bae5e`; the assigned
  paths were already untracked construction artifacts in the authorized dirty
  tree.

## Delivered Behavior

- Map and model field keys now use unsigned lexicographic ordering of the
  emitted JSON-string bytes, matching the body validator's `_canonical_bytes`
  ordering. The comparator streams escaped bytes, so ordering does not create
  a full encoded-key copy.
- Integer emission rejects every non-`int` native value before emitting a
  tagged placeholder. Integer and duration decimal output preflights the exact
  output length, then writes digits incrementally; duration values also reject
  outside signed i64.
- Byte emission preflights padded base64 length and streams bounded 3,072-byte
  source chunks only after the output budget admits the whole tagged value.
- Ordered collections iterate their native input without `list(value)`.
  Sets/frozensets reject cardinality beyond remaining node capacity before
  staging; their required encoded ordering stages only bytes bounded by the
  remaining output budget.
- Removed the file-wide `E701`/`E702` Ruff suppression and formatted the
  touched emitter branches without changing nested decoder dispatch,
  publication joins, source-modality mapping, or envelope/authentication scope.

## Evidence

- `cd memorii && ../.venv/bin/ruff check memorii/core/memory_evolution/typed_value_model_codec.py tests/unit/core/memory_evolution/test_typed_value_model_emission.py`
  passed.
- `cd memorii && ../.venv/bin/pyright --pythonpath "$(../.venv/bin/python -c 'import sys; print(sys.executable)')" memorii/core/memory_evolution/typed_value_model_codec.py tests/unit/core/memory_evolution/test_typed_value_model_emission.py`
  passed with `0 errors, 0 warnings, 0 informations`.
- A direct non-pytest smoke probe compiled both paths and exercised encoded-key
  ordering plus wrong-int, bytes, set-cardinality, and huge-integer failures.
  Root owns the combined pytest run.
- The one configured full Ruff pass was attempted once. It is blocked by three
  pre-existing unrelated findings in `typed_value_registry_history.py`,
  `test_native_observation_decoders.py`, and
  `test_typed_value_registry_history.py`; the assigned focused paths pass.

## Binding And Boundary

This slice has no non-test production caller: the registry-publication plan
records the new runtime registry as zero-caller construction work. Therefore no
`production_entrypoint_bindings` entry is applicable or changed, and this report
does not claim a runtime, persistence, transaction, authentication, or
publication completion. The parent registry-publication milestone remains
partial. The production batch is stable for Root's combined pytest before any
source-snapshot construction.

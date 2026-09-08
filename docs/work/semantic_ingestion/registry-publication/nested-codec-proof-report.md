# Nested Native Codec Proof

## Bounded result

`memorii/tests/unit/core/memory_evolution/test_typed_value_model_codec.py`
now constructs a finite two-model registry closure from the checked-in public
declaration sources for `SegmentGovernanceBinding` and
`SegmentGovernanceCarrierSet`. The closure is compiled through the public
`author_typed_value_registry_role` owner. It verifies materialization and
byte-exact reencoding of a real native `SegmentGovernanceCarrierSet` containing
a nested `SegmentGovernanceBinding` and `SourceModality.ASSERTION`.

The test also proves that a nested decoder source snapshot mismatch is rejected
when the nested model is reached, before its native constructor runs, and that
a declared `SourceModality` wire value differing from the native enum value is
rejected before native Pydantic validation. Both early-rejection cases patch the
native decoder and assert it was never called.
It separately corrupts the nested binding digest after typed-body validation to
prove the nested native model's own validation remains active.

The decoder source digests in this test are explicit synthetic local-conversion
fixtures. They establish the codec's declaration/publication join behavior only;
they do not author, verify, or certify a deployable publication package.

## Local evidence

- `PYTHONPATH=memorii .venv/bin/python -m ruff check --fix memorii/tests/unit/core/memory_evolution/test_typed_value_model_codec.py && PYTHONPATH=memorii .venv/bin/python -m ruff check memorii/tests/unit/core/memory_evolution/test_typed_value_model_codec.py` — passed.
- `cd memorii && ../.venv/bin/pyright --pythonpath "$(../.venv/bin/python -c 'import sys; print(sys.executable)')" tests/unit/core/memory_evolution/test_typed_value_model_codec.py` — 0 errors, 0 warnings.

Focused pytest was intentionally not run by this worker because the coordinator
owns it while the codec implementation is changing. The added tests are ready
for that focused execution after the encoder-conformance worker reports.

## Scope boundary

This is feature-local test evidence only. It does not update a
`production_entrypoint_bindings` entry, claim a production caller, or complete
the parent M5 milestone.

# Native Model Materialization

## Bounded Result

Added `memorii/memorii/core/memory_evolution/typed_value_model_codec.py` and
`memorii/tests/unit/core/memory_evolution/test_typed_value_model_codec.py`.
The codec accepts only an already `ValidatedTypedValueBody` and a
`VerifiedTypedValuePublication`. Before it calls the finite native decoder
table, it proves the selected registry entry is the publication entry and that
its decoder ID and implementation-source digest exactly match both verified and
published source snapshots.

The conversion is directed by the compiled `TypeExpr` declarations. It handles
nested native models by joining and invoking each nested entry's exact static
decoder before its parent, discriminated unions, chunked arbitrary-size integer
conversion, UTC datetimes, bytes, durations, tagged containers and maps,
SourceModality by its declared reachable enum ID/member/wire value, and the
existing typed numeric wrapper codec. Reencoding walks only source-declared
native fields through a bounded writer; it does not call `model_dump`, and
checks byte/node/depth budgets during emission before growing the output. It
rejects a byte mismatch. The result keeps the validated body and explicit
present-field set; this inventory has only `required` and `required_nullable`
fields. A future `omittable` declaration fails closed until its native owner
adds a presence-preserving contract.

`MaterializedTypedValueModel` is explicitly an internal conversion result. It
does not authenticate self-digests, signatures, or external native authority,
and does not authorize persistence. Those remain required protected-envelope
stages for the future caller.

## Local Evidence

- `PYTHONPATH=memorii .venv/bin/python -m ruff check --fix memorii/memorii/core/memory_evolution/typed_value_model_codec.py memorii/tests/unit/core/memory_evolution/test_typed_value_model_codec.py` — passed.
- `cd memorii && ../.venv/bin/pyright --pythonpath "$(../.venv/bin/python -c 'import sys; print(sys.executable)')" memorii/core/memory_evolution/typed_value_model_codec.py tests/unit/core/memory_evolution/test_typed_value_model_codec.py` — 0 errors, 0 warnings.
- A direct `.venv` probe constructed the real public `MemoryScope` through the
  static table, then schema-directed reencoded byte-identically — passed.
- A direct 4,301-digit integer parse/reencode probe passed without Python's
  decimal-string digit conversion limit.

Root owns the focused pytest execution and the full source package/final source
hash. No production entrypoint binding is claimed by this bounded conversion
slice, so no `production_entrypoint_bindings` entry changes here.

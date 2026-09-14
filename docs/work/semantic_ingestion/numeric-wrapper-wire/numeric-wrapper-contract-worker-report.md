# Numeric wrapper contract worker report

## Delivered source-package slice

`typed_value_declarations.py` now requires `encoding_spec_id` on every numeric
field row. Decimal rows require a nonempty ASCII ID and binary64 rows require
null. The identifier is carried in `NumericFieldDeclaration` and therefore in
the raw numeric policy bytes used by existing closure/binding/entry/registry
commitments.

`typed_value_registry_compilation.py` now rejects a repeated decimal ID across
distinct numeric rows in a complete source package. The check walks source rows
once, so revisiting the same declaration through a model closure cannot create
a false duplicate. The shared fixed-scale lexical helper remains conversion
free and is used by compiler bounds and numeric bodies.

`typed_numeric_values.py` adds the selected-field-only primitive bodies:

* binary64 accepts exactly the one-member canonical map with lowercase
  `ieee754_hex`, rejecting exponent-all-ones bit patterns and negative zero;
* decimal accepts exactly the ordered two-member map with matching
  `encoding_spec_id` and `fixed_scale_value`, validates fixed scale and signed
  lexical form, and compares bounds lexically without rounding or native
  float/Decimal conversion.

It uses the existing protected canonical raw-JSON intake with a local protected
numeric limit adapter, and requires the same protected byte limit before
encoding. The inputs and outputs are frozen typed values; no raw dictionary is
accepted as a body value.

## Focused proof

The updated declaration/compiler tests cover missing/null ID rejection,
cross-schema duplicate IDs, and an ID mutation that changes numeric policy,
binding, entry, and registry commitments. The new numeric test covers exact
bytes and round trips, zero/subnormal/negative finite binary64, nonfinite and
negative-zero rejection, decimal endpoint/range/lexical/no-rounding rejection,
selected-ID mismatch, map member/order mutations, exact-cap and one-less
byte/node/depth limits for encode and decode, re-encode byte identity, and
wrong public dataclass scalar types. Oversized decimal encoding is instrumented
to prove its byte cap rejects before numeric lexical/range validation.
Decode performs that byte-identical re-encode comparison before returning; an
instrumented encoder disagreement is rejected by the production guard.

Executed (pytest reserved for the coordinator):

```text
PYTHONPATH=memorii .venv/bin/ruff check memorii/memorii/core/memory_evolution/typed_value_declarations.py memorii/memorii/core/memory_evolution/typed_value_registry_compilation.py memorii/memorii/core/memory_evolution/typed_numeric_values.py memorii/tests/unit/core/memory_evolution/test_typed_value_declarations.py memorii/tests/unit/core/memory_evolution/test_typed_value_registry_compilation.py memorii/tests/unit/core/memory_evolution/test_typed_numeric_values.py
PYTHONPATH=memorii .venv/bin/pyright --pythonpath .venv/bin/python memorii/memorii/core/memory_evolution/typed_value_declarations.py memorii/memorii/core/memory_evolution/typed_value_registry_compilation.py memorii/memorii/core/memory_evolution/typed_numeric_values.py memorii/tests/unit/core/memory_evolution/test_typed_value_declarations.py memorii/tests/unit/core/memory_evolution/test_typed_value_registry_compilation.py memorii/tests/unit/core/memory_evolution/test_typed_numeric_values.py
```

Ruff and Pyright both passed. A direct typed decimal encode/decode construction
also returned the exact approved bytes.

## Deliberate boundary

This is the approved source-package numeric contract only. It does not compose
numeric fields into the full CTV decoder, select a registry at runtime, load
decoder sources, publish a source package, or bind a production entrypoint.
Those protected runtime/publication responsibilities remain with their owners.

# Source-Directed CTV Body Validator

## Scope

Added `typed_value_body_validation.py`, a protected raw CTV model-body
validator. It accepts only an already selected `CompiledRegistryEntry` from an
already compiled immutable registry. It does not perform envelope binding
selection, publication, decoder import, native-model construction, persistence,
or runtime composition.

## Behavior

The validator uses the existing strict canonical raw-JSON intake limits before
tree validation, returns immutable raw bytes/tree/entry, and validates every
closed TypeExpr form: scalar/tag lexemes, arbitrary-size integer bounds,
numeric wrappers through the numeric codec, enums, nested models, collections,
canonical map/set ordering, exact optional/null policy, and discriminated
unions. It has no default insertion or fallback decoder route.

## Local Evidence

From repository root with Python 3.12.14:

* `PYTHONPATH=memorii .venv/bin/python -m pytest memorii/tests/unit/core/memory_evolution/test_typed_value_body_validation.py -p no:cacheprovider` — 6 passed in 5.35 seconds before the body-test fixture migrated to the public registry-role authoring API. Root owns the selected current-revision pytest check for that migration.
* Current revision: `PYTHONPATH=memorii .venv/bin/python -m ruff check memorii/memorii/core/memory_evolution/typed_value_body_validation.py memorii/tests/unit/core/memory_evolution/test_typed_value_body_validation.py` — passed.
* Current revision: `PYTHONPATH=memorii .venv/bin/pyright memorii/memorii/core/memory_evolution/typed_value_body_validation.py` — 0 errors.

## Binding Status

No `production_entrypoint_bindings` entry changes. This bounded leaf has no
non-test production caller and makes no runtime or persistence closure claim;
the later protected envelope/composition owner must provide that caller and
record its authority chain.

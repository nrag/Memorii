# Observation Payload Contract Worker Report

- Scope: profile-3 structural observation payload models only.
- Status: complete for this bounded contract slice; parent registry-publication
  milestone remains partial.

## Changed Paths

- `memorii/memorii/core/memory_evolution/graph_observation_records.py`
  introduces the nineteen approved structural payload roots and the closed
  effective-time discriminator. Every root is strict, frozen, and forbids
  extra fields. Public digest fields have strict SHA-256 lexical validation and
  identifier fields reject empties. The temporal and trust projection roots
  retain complete native projection records and same-kind active/successor
  pointers from `semantic_state.py`, binding the selected generation and
  repository locally. Relation payloads require the declared entity/literal
  endpoint shape.
- `memorii/tests/unit/core/memory_evolution/test_graph_observation_records.py`
  provides focused contract proof for closed/strict/immutable values, unknown
  effective-time kind rejection, the complete root inventory, and direct native
  projection/pointer ownership, including a real native projection/pointer and
  rejected mismatched generation binding.

## Contract Boundary

The payload models validate shape and delegate embedded native values to their
canonical owners. They do not validate profile-3 observation IDs or record
digests, derive a combined temporal/trust projection, publish a registry, or
provide a page, stream, storage, or runtime path. The protected registry body
decoder must later supply resolved registered binding and profile-3 self-digest
verification. The legacy `ObservedClaimProjection` remains untouched.

No `production_entrypoint_bindings` update applies: this slice has no runtime,
persistence, transaction, or composition requirement and makes no production
caller claim.

## Verification

- Passed: `.venv/bin/ruff check memorii/memorii/core/memory_evolution/graph_observation_records.py memorii/tests/unit/core/memory_evolution/test_graph_observation_records.py`
- Passed: `.venv/bin/pyright --pythonpath "$PWD/.venv/bin/python" memorii/memorii/core/memory_evolution/graph_observation_records.py memorii/tests/unit/core/memory_evolution/test_graph_observation_records.py`
- Passed: `.venv/bin/python -m compileall -q memorii/memorii/core/memory_evolution/graph_observation_records.py`
- Passed: `git diff --check -- memorii/memorii/core/memory_evolution/graph_observation_records.py memorii/tests/unit/core/memory_evolution/test_graph_observation_records.py`
- Not run by this worker: pytest, per coordinator ownership of pytest and long
  checks.

Residual risk: the yet-unimplemented protected decoder must bind these models
to a resolved registered profile-3 digest authority before any publication or
production retrieval claim is valid.

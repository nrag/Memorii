# Ingestion And Stream Contract Worker Report

- Scope: profile-3 ingestion observation payloads and the closed structural
  stream-variant alias only.
- Status: complete for this bounded contract slice; registry-publication and its
  parent milestone remain partial.

## Changed Paths

- `memorii/memorii/core/memory_evolution/graph_ingestion_observation_records.py`
  defines the five approved strict, frozen, extra-forbidden ingestion payload
  roots. It checks SHA-256 lexical digest form, nonempty identifiers, native
  governance/source coordinate joins, operation-temporal binding locality, and
  terminal graph-delta and carrier-set relations.
- `memorii/memorii/core/memory_evolution/graph_observation_streams.py` defines
  all seventeen explicit profile-3 stream variants. Each has only record kind,
  primary key, record digest, and the exact typed payload; the closed
  discriminated `GraphObservationStreamRecord` alias binds the outer key and
  digest to that payload.
- Feature-local tests cover lexical closure, an explicit stream round trip,
  key/digest substitution rejection, unknown stream kind rejection, and the
  seventeen-variant inventory.

## Boundary And Verification

The models do not decode registered bodies, recompute profile-3 observation
digests, publish registry data, assemble pages or snapshots, access storage, or
claim a production caller. No `production_entrypoint_bindings` update applies.
The protected future decoder must supply registered-binding and self-digest
verification.

- Passed: `.venv/bin/ruff check` over the two new modules and their tests.
- Passed: `.venv/bin/pyright --pythonpath "$PWD/.venv/bin/python"` over the
  same four paths, with `0 errors, 0 warnings, 0 informations`.
- Passed: `compileall` and `git diff --check` for the new paths.
- Not run by this worker: pytest, per coordinator ownership.

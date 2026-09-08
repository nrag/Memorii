# Generated Decoder Source Exclusion

- Scope: DREV-001 bounded source-manifest capture and verification contract.
- Status: implementation and focused static validation complete; parent candidate regeneration, pytest, source pins, and milestone reconciliation remain owned by the coordinator.

## Delivered Behavior

`typed_value_decoder_sources.py` now treats every path in the reserved
`observation_registry_sources` namespace as generated and ineligible for a
decoder source row. The policy applies without caller configuration to capture
and verification. A source root nested inside that namespace is also rejected,
so selecting a deeper protected root cannot make its generated children appear
native. Caller-supplied forbidden paths remain supplemental restrictions only.

Both entry points validate supplemental forbidden-path configuration before
opening the protected source-root descriptor. The policy uses path components;
it does not infer generated status from file contents or extensions.

## Focused Proof Added

- Default-argument capture and verification reject a generated decoder
  declaration, `registry.json`, `decoder-source-manifest.json`, and
  `publication-manifest.json`.
- Default-argument authoring rejects each same generated selection through its
  capture boundary.
- A root located inside `observation_registry_sources` rejects a plain
  `registry.json` relative path, proving root-depth changes do not evade the
  reservation.
- A malformed supplemental exclusion rejects before any `os.open` call.
- A normal `decoder/native.py` file captures and verifies successfully.

## Static Evidence

From `memorii/` at the dirty candidate based on
`191826cd3afb38bf605a337a71d576063b3bae5e`:

```text
../.venv/bin/ruff check memorii/core/memory_evolution/typed_value_decoder_sources.py tests/unit/core/memory_evolution/test_typed_value_decoder_sources.py tests/unit/core/memory_evolution/test_typed_value_publication_authoring.py
All checks passed!

../.venv/bin/pyright --pythonpath ../.venv/bin/python memorii/core/memory_evolution/typed_value_decoder_sources.py tests/unit/core/memory_evolution/test_typed_value_decoder_sources.py tests/unit/core/memory_evolution/test_typed_value_publication_authoring.py
0 errors, 0 warnings, 0 informations
```

The first Pyright attempt used `$PWD/.venv/bin/python` from `memorii/`, which
does not exist and therefore reported unresolved `pytest` imports. The recorded
command uses the actual repository virtual environment and passes.

## Binding And Residual Risk

This construction helper has no production composition, persistence, or
runtime caller. No `production_entrypoint_bindings` entry is applicable; the
registry-publication plan continues to record zero production callers for this
pre-composition source verifier. This slice does not close the parent
registry-publication milestone.

The modified source file participates in the decoder source candidate. The
coordinator must regenerate the candidate and its source pins before claiming
publication evidence for the changed revision.

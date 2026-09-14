# Registry Compiler Proof Report

## Scope And Status

This report records the bounded cross-role compiler proof on candidate base
`191826cd3afb38bf605a337a71d576063b3bae5e`. It is construction evidence for
the protected profile registry only. The shared observation/public registry has
zero production callers in `../observation-ledger/entrypoint-preflight.md`, so
no `production_entrypoint_bindings` entry changed and this report makes no
runtime-publication, persistence, or authority-chain claim.

The parent registry-publication plan remains active and partial.

## Changed Owners

- `memorii/memorii/core/memory_evolution/typed_value_registry_compilation.py`
  validates each declared decimal wrapper bound as an SIA canonical decimal
  quantity before compilation. It checks optional-minus form, non-leading-zero
  integer form, required decimal point, ASCII digits, exact registered scale,
  and rejects negative zero. It compares `str(len(fraction))` to the declared
  scale, avoiding integer conversion limits. It deliberately accepts empty
  units and `reject_inexact=false`, and introduces no generic lower/upper
  ordering rule. It also requires every `self_digest` field to be
  `string/sha256` and every `signature` field to be `string/signature_hex128`
  for self-digest, signature-only, and external-preimage policies.
  It now also exposes `author_typed_value_registry_role`, an offline-only
  authoring operation that reparses a complete non-registry role family,
  applies the compiler's exact cross-role validation and LP entry derivation,
  and emits the canonical RFC-8785 registry-role bytes. The production compiler
  remains a separate verifier of a supplied registry role. Authoring rejects a
  supplied registry role before it can become a circular input.
- `memorii/tests/unit/core/memory_evolution/test_typed_value_registry_compilation.py`
  adds a frozen, static registry commitment for a valid
  `IngestionObservationReplayCheckpoint.v1` /
  `ObservationCheckpointSigningPreimage.v1` declaration pair. The test does
  not calculate that expected commitment with compiler-private helpers. The
  fixture is explicitly closure-only and does not claim to be the full
  production checkpoint schema.
  Its ordinary complete-source fixture now obtains the registry role through
  the public authoring operation rather than compiler-private profile, role
  indexing, or entry derivation helpers.

## Proof Matrix

| Behavior | Observable proof |
| --- | --- |
| Valid checkpoint external signing preimage | Reparsed static source bytes compile to two active entries whose static registry entry digests match. |
| Closed exception ownership | External policy on another schema, missing result field, and duplicate `self_digest` reject with `digest_signature_policy_closure_invalid`. |
| Integrity field lexical closure | Self-digest, signature-only, and external-preimage policies accept only `string/sha256` digest fields and `string/signature_hex128` signature fields; bytes, bool, and generic strings reject. |
| Preimage dependency safety | A non-ordinary preimage rejects with `external_preimage_policy_invalid`; a model edge from the preimage back to the checkpoint rejects with `schema_dependency_cycle`; an absent referenced preimage rejects with `schema_dependency_unresolved`. |
| Decimal numeric source grammar | Malformed, leading-zero, wrong-scale, plus/exponent, and negative-zero bounds reject with `numeric_decimal_bound_lexical_invalid`; empty unit and `reject_inexact=false` with exact bounds compile. |
| Offline registry-role authoring | Complete non-registry role bytes emit a parseable registry role that round-trips through the production compiler; permuting the input role order preserves exact emitted bytes; incomplete role families and any supplied registry role reject. |

## Commands And Results

From `memorii/`, on Python 3.12.14:

```text
../.venv/bin/python -m ruff check memorii/core/memory_evolution/typed_value_registry_compilation.py tests/unit/core/memory_evolution/test_typed_value_registry_compilation.py
All checks passed!

../.venv/bin/pyright --pythonpath ../.venv/bin/python memorii/core/memory_evolution/typed_value_registry_compilation.py tests/unit/core/memory_evolution/test_typed_value_registry_compilation.py
0 errors, 0 warnings, 0 informations
```

The earlier 20-test result predates this authoring change. Per the coordinator's
ownership instruction, this slice did not rerun pytest; the root agent owns the
post-change affected test and source-join execution.

## Residual Risk

This proof uses a small closed declaration fixture; it does not construct the
complete source-selected observation model package, independently compile a
frozen package, or wire a production publication caller. The authoring
operation is an offline package-construction aid and has no production caller,
persistence effect, or authority-chain role, so no
`production_entrypoint_bindings` update applies. Those remain parent-plan
obligations and require their own binding-ledger evidence.

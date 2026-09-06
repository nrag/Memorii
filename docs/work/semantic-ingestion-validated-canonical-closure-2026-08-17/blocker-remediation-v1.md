# Blocker Remediation V1

This design-only addendum closes the proposed corrections for
`VCC-DREV-001` and `VCC-DREV-008`. It invalidates reviewed candidate lock
`722a0a933ff9dd34591e310ad58b01b2f04c9b519725c0136b23f139615ee1db`.
It does not claim that the production implementation exists.

## VCC-DREV-001: Codec-Owner Span Issuance

The implementation must extend the existing byte-producing owner in
`memorii/memorii/core/memory_evolution/ingestion_contracts.py`; it must not
introduce a second canonical normalization traversal.

The frozen target ownership is:

| Symbol | Target signature and responsibility |
| --- | --- |
| `_json_with_spans` | `_json_with_spans(normalized: object, *, check: Callable[[], None] | None = None) -> CanonicalJsonEmission`; emits the exact canonical bytes and immutable traversal-path spans in one byte-writing traversal |
| `_json` | `_json(normalized: object, *, check: Callable[[], None] | None = None) -> bytes`; compatibility wrapper returning `_json_with_spans(...).canonical_bytes` |
| `encode_typed_value_with_spans` | `encode_typed_value_with_spans(value: object, *, check: Callable[[], None] | None = None) -> CanonicalCodecResult[object]`; executes existing `_normalized_typed_json` exactly once, then `_json_with_spans` exactly once |
| `encode_typed_value` | Existing public signature and bytes remain unchanged; it delegates to the new owner and returns only canonical bytes |
| `encode_semantic_contract_with_spans` | Internal typed semantic-contract counterpart that preserves `_CONTRACT_KINDS`, Pydantic validation context, closed-enum handling, and the existing envelope |
| `encode_semantic_contract` | Existing public signature and bytes remain unchanged; it delegates to the internal owner and returns only canonical bytes |

`CanonicalJsonEmission` contains only `canonical_bytes` and immutable
`ValidatedCanonicalBinding` records. Each binding carries the traversal-issued
path, `[start, end)` offsets, digest, canonical profile, and node kind. It
carries no validation, authorization, persistence, tenant, or writer authority.

The codec is the sole issuer. Consumers cannot manufacture bindings. Existing
`decode_typed_value` and `decode_semantic_contract` remain unchanged and must
accept the enabled bytes exactly as they accept disabled bytes.

The feasibility proof calls the real public codec entrypoints, preserves the
real `_normalized_typed_json` traversal, and installs the proposed byte writer
at the real `_json` owner seam. It is not a post-hoc byte search and does not
replace normalization with a reference encoder.

Evidence:

- Program SHA-256:
  `3395ae11e7072ae90513bfdfaf0eefe3db3581dd8ff5f329688ec2222ad5054e`
- Result SHA-256:
  `891cb549a88fc7c01519a842c0b52861433b11b422b47f523e5132df993ffc0a`
- Result: 11 accepted typed families and one registered semantic contract are
  byte-identical and decoder-compatible; every span is in bounds, the root span
  covers the complete bytes, and every span digest equals its exact byte slice.

## VCC-DREV-008: Revision-Bound Production Ledger

`production-entrypoint-bindings-v2.json` is the machine-readable design ledger
for all requirements `VCC-R01` through `VCC-R12`. Every row records:

- production trigger and caller-count source
- composition root
- exact authority arguments
- full owner chain
- deterministic mapping tokens
- fallback or bypass behavior
- focused implementation proof

The ledger also enumerates the closure-relevant durable writers. The validator
fails for a missing requirement, zero or test-only production caller, missing
owner or writer, removed bootstrap handoff, omitted production authority,
missing fallback, or missing behavioral proof.

Evidence:

- Ledger SHA-256:
  `720ea32def9fb048213662842aa98e85e3c5d3aea85c952f2d616428ee24bf11`
- Validator SHA-256:
  `96cbe2e9c03fd49f545923779f96d0416ef63f4a627ca6e5943b2581e803fa7f`
- Validation result SHA-256:
  `02e3174d1da59c141c42837f0e5e9767aeb0107a45ead021564501993790b3ea`
- Result: 12 requirements, 12 checked owner files, 10 durable writers, five
  non-test production callers, and all negative guard classes pass.

## Candidate State

This artifact does not define its own candidate identity. It is bound by the
external candidate manifest that tracks it, its executable evidence, and its
validators without creating a circular self-hash. The remaining eight
round-one findings still require design remediation. Independent targeted
delta review must close these two blockers before they can be marked resolved.

# Blocker Remediation V4

This normative delta closes the proposed corrections for `VCC-DREV-001D`,
`VCC-DREV-001E`, and `VCC-DREV-008B` without changing production code or
repository tests.

## Production Callback Execution Proof

The baseline callback schedule is observed through the production
`_normalized_typed_json` and `_json` functions. The observer records the actual
call-tree path, phase, node kind, and value fingerprint at each callback
invocation without changing callback count or bytes.

The proposed span writer runs after production normalization. Its callback
schedule must equal the production baseline exactly. Reorder, omission, and
extra attacks alter actual callback invocation timing while preserving emitted
bytes; reorder also preserves callback count. All three must be detected.

## Complete Decoded Wrapper Algebra

Canonical raw set and frozenset payloads force each decoder-only wrapper:
`_HashableCtvMap`, `_ImmutableCtvList`, `_ImmutableCtvTuple`,
`_ImmutableCtvSet`, `_TagAwareCtvSet`, and `_TagAwareCtvFrozenSet`. Each fixture
asserts its runtime type before byte, decoder/re-encoder, callback, span, and
single-writer checks run. Mixed set and frozenset fixtures contain all six
wrapper types together and are the callback-attack subjects.

## Owner-Qualified Production Graph

The v5 binding ledger replaces ordered string chains with an independently
frozen owner graph. Every current edge names exact source and target paths,
qualified symbols, edge kind, and observed call name. The validator resolves
both qualified owners and the directed caller AST. Constructor/context-manager
edges are distinct from ordinary calls.

All twelve requirement rows distinguish current implementation maturity from
planned implementation. Local codec and arena outcomes are not mislabeled as
durable writes. The production root matrix contains supervised capture, direct
factory, filesystem, and Hermes integration roots. Runtime branch traces remain
explicit implementation evidence and are not claimed as locally verified
design evidence.

`VCC-R08` uses state bindings rather than invented constructor parameters. Its
outcome is scoped to arena-owned cache state. Structural proof requires no
persistence or atomic-store import and no durable-sink call anywhere in the
arena owner class. Public semantic operations may still persist through the
separately modeled conditional terminal path.

The coordinated mutation matrix covers reversed and invented edges, wrong
qualified symbols, reversed constructor ownership, capture-only root
substitution, invented state authority, R08 durable-write substitution,
invented snapshot reachability, and omitted implementation proof families.


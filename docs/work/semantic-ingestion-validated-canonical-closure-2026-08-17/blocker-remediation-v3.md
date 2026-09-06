# Blocker Remediation V3

This normative delta closes the proposed corrections for `VCC-DREV-001C`,
`VCC-DREV-001D`, `VCC-DREV-001E`, and `VCC-DREV-008B`.

## Complete Codec Owner Proof

The owner proof instruments the prototype span writer itself, not its public
encoder caller. It requires one span-writer invocation per public encode and
fails when a second final write is injected for map or set input.

Baseline and enabled owner traversals record complete path-aware callback
schedules. Their event sequences must be identical. Reordered and extra
callback attacks must be detected even when ordinary output bytes remain
unchanged.

The fixture algebra includes scalars, bytes, datetime, timedelta, list, tuple,
map, set, frozenset, every decoded immutable wrapper category, nested ordered
combinations, and one registered semantic contract. Every family must preserve
canonical bytes, decoder/re-encoder output, callback trace, exact spans, and
one final span write.

## Independent Ledger Contract

The v4 candidate ledger and `production-entrypoint-expected-rows-v1.json` are
separate frozen artifacts. The validator compares every complete row projection
against the independent expected contract, so coordinated candidate-ledger
changes cannot validate without also changing a separately hashed authority.

Current production anchoring is symbol scoped: AST inspection proves exactly
one `sync_event` call inside `_capture_child`, rather than counting unrelated
repository calls. Validation, fallback, and durable boundaries must be
connected to each row's ordered path and resolve to existing production
symbols. Planned proof IDs must resolve through the independent proof catalog.
`VCC-R08` is constrained to `no_durable_write` and cannot point at persistence.

The validator must reject coordinated parameter/binding substitution,
coordinated chain/edge substitution, unrelated fallback tokens,
repository-wide rather than symbol-scoped counts, wrong durable semantics,
an R08 durable-write substitution, and a missing proof-catalog entry.

These are design-feasibility and implementation-readiness proofs. They do not
claim that planned closure handoffs already exist in production.

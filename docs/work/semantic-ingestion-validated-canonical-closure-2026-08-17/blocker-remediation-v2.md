# Blocker Remediation V2

This normative delta supersedes the `VCC-DREV-001` and `VCC-DREV-008`
portions of `blocker-remediation-v1.md`.

## Single Final Span Writer

`_normalized_typed_json` retains one normalization traversal. Its map, set, and
frozenset ordering calls use a non-span `_ordering_json` helper with the exact
current canonical byte and `check` behavior. They never issue bindings.

After normalization completes, `encode_typed_value_with_spans` invokes
`_json_with_spans` exactly once on the final normalized root. `_json_with_spans`
mirrors the existing `_json` token order, scalar encoding, map-key ordering,
and `check` callback schedule while recording offsets during the same byte
write. Existing `encode_typed_value` returns only its canonical bytes.

The semantic-contract owner preserves its current preliminary validation
encoding as non-span work and issues bindings only for the final validated
envelope encoding. Existing public typed and semantic codec signatures and
decoder behavior remain unchanged.

The executable proof requires, for every accepted fixture family:

- one final span-writer call per public encode
- exact canonical byte equality
- decoder and re-encoder equality
- identical `check` callback count
- identical stateful stop/completion result at first, midpoint, final, and
  one-past-final callback thresholds
- exact in-bounds span slices and digests

## Structured Production Binding Ledger

The v3 ledger separates current production anchoring from planned closure
handoffs. Every `VCC-R01` through `VCC-R12` row records:

- one current non-test production anchor edge and row-local captured count
- one exact planned target owner and parameter list
- one authority binding per target parameter with status and proof ID
- the complete ordered owner chain and one typed planned edge per transition
- an existing validation boundary
- an existing durable outcome, or the explicit `no_durable_write` outcome
- an existing fallback branch
- three implementation proof IDs and explicit `planned` status

The deterministic validator resolves current paths and symbols, recomputes the
row-local caller count, checks parameter-to-binding equality, checks every
ordered edge, validation boundary, durable outcome, fallback token, and proof
ID, and then runs five mutation self-tests:

1. wrong authority parameter
2. disconnected owner edge
3. wrong row-local caller count
4. missing durable writer
5. missing fallback and proof

All five mutations must make validation fail.

## Evidence Boundary

These artifacts establish implementation-ready design feasibility and
revision-bound governance. They do not claim that the planned production
symbols or handoffs are already implemented. Production-path acceptance proof
remains an implementation-phase obligation.

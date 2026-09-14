# Operational Observation Profile Decision

Status: direction approved by the user on 2026-09-06 ("ok. go ahead").
Exact grammar and registry remain subject to design review. No production schema, profile constant,
canonical design, generated authority or persisted artifact has changed.

## Approved Direction

Use a new operational `semantic_ingestion_typed_value` profile version 3
for the new observation ledger and its authenticated observation artifacts.
Version 3 is an encoding version, not a milestone number. Publish the complete
runtime grammar, schema policies, preimage domains and independent golden bytes
under Section 3.15.1 before assigning any digest or enabling writes.

The runtime grammar follows Section 3.15.1: canonical tagged values, encoded
JSON-string byte ordering for map entries, no terminal LF, registered enum
identities, explicit field optionality, and exact schema validation. It does not
adopt the fixture-v2 grammar or reuse its digest. The complete grammar and
registry still require the planned independent design review; approving this
direction does not approve an unfinished implementation.

Preserve every existing profile-2 artifact, digest and literal decoder. Existing
pre-activation ingestion remains under its current admission rules. After ledger
activation, new ledger artifacts require the new profile; old artifacts remain
readable through their historical routes and cannot be relabeled as globally
ordered audit. No bulk rewrite or fabricated migration is authorized.

Freeze a single outer-envelope grammar for operational registered artifacts:
the existing canonical tagged-map envelope with exactly `binding`,
`canonical_value_bytes`, `canonical_value_digest` and `artifact_digest`; its
binding map has the six fields specified in Section 3.15.1. The outer grammar
uses the restricted scalar/map/bytes/integer subset and exact no-LF encoding.
The embedded complete binding selects the body decoder only after protected
registry validation. Future body profiles may not silently change this outer
grammar; a future envelope grammar needs a separately reviewed versioned
dispatch contract. The current historical diagnostic JSON wrapper remains a
separate non-authorizing reader.

## Why This Requires A Decision

The current runtime and test fixture declare the same profile digest but have
different byte rules. The retained `profile-identity-discrimination.json` proves
both the shared digest and differing encodings of one map. Merely adding a
registry would give that discrepancy new persisted authority. Reusing the old
coordinate with changed rules would invalidate or ambiguously interpret stored
evidence. The governing document specifies the registry mechanism but does not
choose the operational profile or future envelope dispatch policy.

The alternative is to stop new ledger integration until an existing published
operational profile can be shown byte-identical with complete registry inputs.
No such authority has been located. Changing the fixed 56-root test fixture to
make it operational is prohibited by its stated scope and is not an alternative.

## Completion After The Decision

The coordinator will finish the exact published grammar, envelope and registry
preimages, complete the replay/page/cursor field closures, and run the frozen
design reviews. Implementation then adds registered decoding through the real
group/source transaction and replay entrypoints, with historical-byte,
unknown-binding, independent-vector and resource-boundary proof. Production
signatures and external statistical policy remain separate release obligations.

# Numeric Wire Amendment Verification

This frozen design amendment fills the two omissions recorded by the independent
source consultation. It does not certify a runtime codec or registry. The user
approved existing maps plus explicit decimal source IDs on 2026-09-07.

| Contract | Required proof before implementation closure | Current evidence |
| --- | --- | --- |
| Existing map algebra, exact binary64 one-member body | Literal bytes, decode/re-encode identity, finite positive/negative/zero/subnormal; every exponent-all-ones class and negative zero reject | Proposal-only literal and bit tests in feasibility.py |
| Exact decimal two-member body | Required ID/value, correct map order, fixed positive scale, signed finite lexical values; exponent/plus/leading-zero/negative-zero/wrong scale reject | Proposal-only scale-two lexical cases |
| Field-selected ID | Raw decimal rows require explicit ascii-id; binary64 requires null; missing/unknown members reject; body ID equals selected row | Normative amendment plus mismatch example; parser/compiler tests required |
| Source ID uniqueness | Distinct rows with one ID reject across model closures/schema versions; revisiting the same row is valid; changed ID changes numeric policy and affected binding/entry commitments | Required implementation matrix, not claimed executed |
| Bounds and no rounding | Inclusive/exclusive endpoints, below/above bounds, signed comparisons, arbitrary-length fixed-scale input under protected byte limits, reject_inexact false cannot enable rounding | Existing SIA rule retained; runtime proof required |
| Closed canonical byte intake | Extra/missing/duplicate/misordered keys, alternate tags, scalar substitution, JSON numbers, malformed Unicode/UTF-8, trailing LF and resource overflows reject | Selected feasibility cases; full registry byte decoder required |
| Nested and optional wrapper fields | Selected declaration controls value kind and row; optional omission/null follows existing policy; no caller-selected policy, unresolved role or invented default | Existing TypeExpr/optional closure rules retained; composed codec tests required |
| Historical compatibility | Existing profile-2 artifacts, native embedded hashes and issued bindings keep original bytes; profile-3 publication regenerated before deployment | No issued operational profile-3 package exists; historical gates required |
| Independent compilation | Independent author reads frozen raw roles, independently parses new key/constraints and derives every output; no reference parser/compiler/normalizer or derived fixtures as inputs | Existing registry independence contract applies; unavailable until full source package |

## Ownership And Source Chain

SIA is authoritative for the exact numeric bodies. The observation design's
closed numeric row gains encoding_spec_id and its exact null/non-null/uniqueness
rule. The raw declaration parser and registry compiler own source enforcement.
The protected typed-value body decoder under the canonical ingestion-contract
owner consumes only the field's verified numeric role; request/body IDs cannot
select registry authority. Publication verifies the complete source/snapshot
package before deployment exposes it. Existing production entrypoint plan and
attack matrix remain in ../observation-ledger/entrypoint-preflight.md and
registry-verification-matrix.md. Their absent runtime callers are implementation
gaps; this amendment claims only specification readiness.

Two separate authority branches apply:

1. The observation-only amendment changes the per-field profile-3 numeric-role
   grammar. Source authoring under the registry implementation produces raw
   role files from this approved specification, including the explicit ID.
   typed_value_declarations.py parses those exact bytes;
   typed_value_registry_compilation.py verifies package-wide ID uniqueness and
   derives numeric-policy closure, binding, entry and registry commitments.
   typed_value_publication.py joins the exact source-role file hashes, decoder
   source manifest/snapshots and registry into publication/deployment pins.
   The full raw source package/static decoder table and independent package
   producer remain implementation work, not products of the old CTV compiler.
   An ID mutation must change each affected policy/binding/entry/registry,
   source-role manifest and publication commitment; a reused traversal of one
   declaration remains valid. This amendment cannot publish a partial package.
2. SIA/CTV/structural sources stay byte-identical because this amendment's exact
   edit boundary is semantic_ingestion_observation.md only. Its wrapper map
   clarification follows the existing SIA model-map algebra. A source-chain
   regression must compare the architecture, CTV authority, structural fixture,
   relevant checkers and workflow hashes before/after promotion and prove they
   are unchanged. If a later operation deliberately edits SIA, that operation
   must own its separate source refresh; the native-policy retention map is
   historical guidance for that different operation, not amendment authority.

The existing map tag leaves the profile literal unchanged. Future operational
publication regenerates all affected commitments and protected deployment pins
only after the complete source package and independent compilation pass. No
existing compatible producer is claimed for that still-unimplemented package.

## Identity And Environment

Only domain names enter code and wire fields: ieee754_hex, fixed_scale_value,
encoding_spec_id and existing numeric type names. Requirements/review coordinates
stay in work metadata. No new exceptions to the field-aware identity gate.
Python 3.12.14 runs the feasibility experiment. No network, live-provider, real
release signing or runtime deployment is required for this design decision.
Concurrency, authorization, retries and transaction semantics are unchanged.

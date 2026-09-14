# Observation Ledger Hash Preimages

Status: proposed owner decision; not canonical or implemented.
Parent implementation: ../observation-ledger/implementation.plan.md.
Baseline: docs/design/semantic_ingestion_observation.md, SHA256
8f2fba74b947eebaf0f91308143bcc67d77c2b8571ea9e6ad7d86b59b006ad6a.

## Exact Missing Choice

The canonical design at lines183-193 requires a bound semantic-payload digest
and observation successor, but specifies neither domain bytes nor preimage
framing. Both payload registry roles are ordinary. The feasibility model's
minimal payload and hashes are explicitly illustrative. Independent spec
consultation confirmed this is a persisted-identity ambiguity.

## Recommended Amendment

Retain the approved canonical map body and decimal encoding policy. Reuse the
existing cryptographic length framing used by artifact_preimage and
registered_self_digest_preimage; do not introduce another body serialization.

Define LP(parts) as concatenation, in stated order, of each part's unsigned
8-byte big-endian byte length followed by its exact bytes. Reject a part longer
than 2^64-1 bytes. No terminator, separator, JSON whitespace or implicit NUL is
added. H is SHA-256 rendered as 64 lowercase hexadecimal ASCII characters.

The semantic payload domain is exactly the UTF-8 bytes of:
`memorii.observation-ledger.semantic-payload.v1`

The payload preimage is LP of these eight parts, in order:

1. the semantic payload domain;
2. selected binding.profile_id as UTF-8;
3. selected binding.profile_version as canonical positive decimal ASCII;
4. selected binding.profile_digest as lowercase hexadecimal ASCII;
5. selected binding.schema_id as UTF-8;
6. selected binding.schema_version as canonical positive decimal ASCII;
7. selected binding.binding_digest as lowercase hexadecimal ASCII;
8. the exact verified profile-3 canonical payload body bytes.

semantic_payload_digest = H(payload preimage). The source/group kind selects
exactly ObservationSourceSemanticPayload.v1/ObservationGroupSemanticPayload.v1
from the active target publication. Full native shape, source/governance joins,
body and binding verification precede hashing. The artifact envelope, its digest,
the final delta, and final assigned revisions are not part of the payload body.
No unicode normalization or reserialization after verification is permitted.

The observation revision domain is exactly the UTF-8 bytes of:
`memorii.observation-ledger.revision.v1`

The successor preimage is LP of these five parts, in order:

1. the observation revision domain;
2. protected repository_id as UTF-8;
3. activation_digest as lowercase hexadecimal ASCII;
4. current head.observation_revision as UTF-8, preserving the existing nonempty
   Unicode-scalar identifier grammar;
5. semantic_payload_digest as lowercase hexadecimal ASCII.

observation_revision_after = H(successor preimage). Complete replay separately
requires the predecessor to be the exact reached head: genesis initially and
the preceding derived revision afterward. A structurally valid arbitrary head
identifier alone never proves that reachability. No new lexical restriction is
added to the existing head model or registered schema. A caller cannot supply the
repository, activation, predecessor, domain or binding. The atomic owner obtains
them from verified target and current head. Assigned native delta digest keeps
its existing native grammar, as canonical design lines1039-1040 require.

The phrase 'registered domain' in the canonical algorithm will be replaced by
these fixed profile-3 ledger protocol domain constants. They are not policy or
caller-selectable values. No new declaration role or model root is introduced;
source/body/declaration cardinality remains unchanged. The emitting/verifying
runtime code and constants must be covered by the activation target's installed
writer payload fingerprint, release package proof and immutable source identity.
No activation target built before that source update can authorize its writer.

## Alternatives And Consequences

Using only canonical_value_digest omits the complete schema binding and domain;
using artifact_digest silently adopts another protocol purpose. Both violate
the canonical ledger requirement. Adding two newly registered preimage schemas
would work but expands declaration/decoder/vector inventories without changing
the required information. Fixed protocol constants with existing length framing
are the narrower recommendation.

There are no production ledger entries to migrate. Preserve existing activation,
legacy schema1/2 terminal bytes, ordinary native delta digests and profile3 body
serialization. Rebuild the activation writer target and installed package proof
for the eventual implementation. Older writers remain fenced after activation;
no backward-compatible guessing or alternate preimage fallback is allowed.

## Acceptance And Attack Matrix

Verify exact byte vectors independently from the production helper. Change each
binding field, payload body, kind, repo, activation, predecessor and domain and
require a different commitment or typed input rejection. Cover empty/invalid
identifiers, bool/version coercion, noncanonical digests, unicode scalar UTF-8,
length framing ambiguities, reordered fields and alternate numeric spellings.
Test semantic payload rejection of a full delta and wrong union variant.
Interleaved sources must assign distinct contiguous global predecessors; CAS
loss publishes nothing; lost ACK recovers its immutable entry under a later head.
Production replay must recompute both recipes from independently loaded head,
entries and exact selected historical bindings. A short valid prefix is not full
replay. The change grants no checkpoint, query, signature or statistical authority.

These are required implementation checks, not executed evidence. Local activation
verification remains valid only for its frozen candidate; append and authenticated
retrieval remain unimplemented.

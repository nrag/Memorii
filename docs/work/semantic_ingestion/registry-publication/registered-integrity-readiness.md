# Registered Artifact Integrity Readiness

Status: bounded normative consultation; implementation remains pending.
Sources: docs/design/semantic_ingestion_architecture.md Section 3.15.1 and
docs/design/semantic_ingestion_observation.md closed digest/signature policies.
The spec auditor decoder_snapshot_review found no unresolved semantic choice.
This does not approve runtime trust, registry publication or the parent milestone.

The fixed envelope selects the original publication by complete embedded binding
and verifies its two native digests before body interpretation. Source-body
validation, finite native materialization and exact reencoding produce an
unauthenticated value. Registered integrity and native authority are additional
boundaries before persistence or public read authority.

## Closed Policies

The current package has 140 ordinary, 37 self-digest, one signature-only cursor
and one external-signing-preimage checkpoint root. Apply only the selected root
policy. Nested digest/signature fields stay in the parent's preimage. Native
graph/effect digests are ordinary profile fields whose original validators
remain responsible for native validation.

For self-digest, remove only the declared root digest field and compute SHA-256
of LP(registered domain, profile ID, profile version, profile digest, schema ID,
schema version, binding digest, canonical remaining body). Every LP member has
an unsigned eight-byte big-endian byte length; versions use canonical decimal
text. Compare the supplied digest before granting integrity-check success.

For GraphObservationCursorPayload.v1, exclude only signature. The registered
purpose is graph_observation_cursor and domain memorii.graph-observation.cursor.v3.
Build the schema-specific preimage using that domain, complete binding and
unsigned canonical body. Ed25519 signs LP(purpose, complete binding members,
exact schema-specific preimage, resulting SHA-256 digest). The final digest
member is the 64 lowercase hexadecimal characters encoded as ASCII/UTF-8,
not the intermediate 32 hash bytes (SIA 3.15.1 and observation sha256 grammar).
Require the exact
64-byte signature and a separately supplied trusted verification key. Existing
graph_observation_cursor.py signs a different legacy v1 wire and is not this route.
Cryptographic validity alone does not prove key lifecycle or request authority.

For IngestionObservationReplayCheckpoint.v1, the only allowed constructor is
observation_checkpoint_v1. It receives registered purpose observation_checkpoint,
repository ID, activation digest, sequence, full ledger head, complete lifecycle
including authority_digest, and checkpoint fields excluding checkpoint_digest
and signature. It constructs the ordinary ObservationCheckpointSigningPreimage.v1
body and checks all repository/activation/sequence/head/state/last-delta/revision
joins. Compute the digest under the checkpoint binding and registered domain
memorii.semantic_ingestion.observation.IngestionObservationReplayCheckpoint.v1,
then sign the same purpose/binding/preimage/digest sequence. Do not include
bundle_digest, checkpoint_digest or signature in the signing preimage. Receipt
and bundle digests follow signing.

Required trusted checkpoint inputs remain full replay state and independently
loaded head from one protected snapshot, activation, lifecycle chain, rollback
floor, original registry history, eligible key and raw public-key fingerprint,
and protected UTC creation time. Model shapes exist; durable composition is
unfinished. Existing HMAC CheckpointSignatureAuthority belongs to a different
protocol and must not authenticate observation checkpoints.

## Implementation Acceptance Matrix

| Boundary | Required proof |
| --- | --- |
| Root policy selection | Exact historical declaration selects the policy; no caller exclusions, current binding, decoder hint or fallback |
| Ordinary body | Digest-looking native fields remain in canonical body and native validators still run |
| Self digest | Independent literal LP/hash oracle; each binding/domain/member mutation fails; nested integrity fields remain committed |
| Cursor signature | Real isolated Ed25519 key, exact message oracle, wrong key/purpose/binding/body/signature reject; legacy cursor wire rejected |
| Checkpoint external body | Full independently loaded head and lifecycle joins; omitted/substituted authority fields reject; unsigned values grant no persistence authority |
| Resource and staging | Existing envelope/body limits honored; invalid envelope makes zero body/integrity calls; invalid integrity never reaches persistence |

No production signature issuance is required for these engineering proofs.

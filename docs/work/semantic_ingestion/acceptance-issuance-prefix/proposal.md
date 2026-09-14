# Release-Bound Issuance Key-History Prefix

Status: proposed, not approved or promoted. This amends only the issuance-prefix
ambiguity in the preserved acceptance-authority-successor contract. Its closed
release lifecycle, protected checkpoint, receipt, bounded parsing, signatures,
and ownership requirements remain in force.

## Binding And Owner

Keep `CapabilityBaselineApprovalRelease.acceptance_authority_snapshot_digest`
as the single signed release reference. Do not add redundant release head fields.
The acceptance-owned verifier resolves it through a constructor-held immutable
repository, never a latest-snapshot lookup or a caller-supplied prefix. This
approval snapshot is distinct from `AcceptanceRegistryAuthoritySnapshot`, which
controls acceptance registry publication.

Proposed closed `AcceptanceApprovalIssuanceSnapshotV1` fields are:

```text
schema_version: Literal[1]
purpose: Literal["semantic_ingestion_approval_issuance_snapshot"]
trust_snapshot_digest: Digest
key_event_digests: tuple[Digest, ...]  # nonempty, ordered by contiguous sequence
key_history_head_digest: Digest
key_history_head_sequence: PositiveInt
snapshot_digest: Digest
signing_key_coordinate: SigningKeyCoordinate
signature: bytes
```

The exact event bodies remain immutable `KeyLifecycleEvent` artifacts from the
predecessor proposal. The repository returns their raw bytes by these digests;
all bytes are bounded before decode. The terminal event digest equals the head,
and the sequence is exactly the number of events, starting at one. Every event
predecessor equals the previous event digest. The snapshot's trust reference
selects the complete static key declarations. Event signature verification uses
the event's own issuance trust snapshot. That reference must be independently
rooted in the protected acceptance anchor, never in the approval being verified.

Use the predecessor's complete-profile CTV digest/signature construction with
snapshot domain `memorii.semantic_ingestion.acceptance.approval_issuance_snapshot.v1`
and the purpose literal above. Only `snapshot_digest` and `signature` are omitted
from its unsigned body. The signed ordered event digests bind every event and
terminal coordinate. The snapshot signer must equal the approval release issuer. Its exact key
coordinate must resolve in the referenced trust snapshot, declare both approval
and `semantic_ingestion_approval_issuance_snapshot` purposes, have static validity
containing `release.issued_at`, and reduce to active in the complete bound prefix
at that cutoff. This is an additional authorization check, not just successful
cryptographic verification. A different, retired, revoked, compromised or
wrong-purpose signer rejects the snapshot. Every event key, including nonselected
and future-effective keys, must join a declaration in its governing trust snapshot.
The protected acceptance issuer captures and signs one
complete current prefix before creating the approval release; missing snapshot
publication prevents issuance. No event may be appended to an existing snapshot.

## Separate Reductions

First validate the complete issuance prefix, including future-effective events:
closed shapes, digest and signature joins, contiguous global sequence, exact
predecessors, ordered `(effective_at, global_sequence)`, and the complete key
lifecycle. Then separately reduce only events with `effective_at <= issued_at`.
The selected issuer must be active at that cutoff, declared for approval purpose,
and within static validity. A later append at the same time cannot retroactively
enter this immutable prefix. Future-effective activation inside the prefix cannot
authorize earlier issuance. Full-history transition validation must not use the
cutoff state as its predecessor state.

Independently load the protected current checkpoint and complete current history
once per verification. Its prefix through the issuance head must exactly equal
the issuance event digests; replacement and truncation reject. The current trust
declarations must preserve all issuance-prefix static declarations (new keys may
be added); status
changes are lifecycle events. Reduce at evaluation time to require current key
eligibility. Post-issuance revocation prevents current use without changing the
historical signature. Currentness and lifecycle receipts remain mandatory.

Verification order is bounded release/baseline decode, immutable snapshot and
trust verification, release signature and digest, issuance prefix validation and
cutoff authorization, protected current checkpoint/prefix validation, current
key/release reduction, A->T->B receipt validation, baseline binding. Each history
and nested trust artifact has protected cumulative count/byte limits as well as
per-artifact ceilings; repository recursion must detect repeated trust references.

## Compatibility And Promotion

No historical release bytes are rewritten. An existing release can be used only
if its already signed snapshot digest resolves to the exact issuance-prefix
contract. A missing prefix cannot be reconstructed from timestamps/current state;
such a release requires reissuance through the new issuer. No production fallback
is introduced.

Promotion requires approved snapshot/trust/event closed schemas and digest domains,
independent CTV vectors, registry/decoder publication, protected immutable repository
and bounded trust traversal, the acceptance verifier and normal evaluator/CLI,
the verified-digest deployment bridge, and current gates. This proposal does not
supply policy values, production keys, or qualifying acceptance measurements.

## Executable Evidence And Limits

`issuance_prefix_feasibility.py` composes the preserved successor decoder, full
history reducer, static key checks, current checkpoint and receipt/lifecycle
verifier. The new public entry takes only release/baseline bytes and evaluation
time; snapshots and status are constructor-held. Its compact symbolic aliases
are deliberately not CTV or cryptography. The prior 56 tests run unchanged beside
44 new tests (100 passed locally). The original composed A->T->B test is preserved.
The new tests cover prefix absence/substitution, equal-time append, future events,
head/sequence mutation, post-issuance revocation, predecode byte budget and receipt
tampering. The model uses inlined event/static declarations instead of repository
traversal and therefore does not prove cumulative retrieval bounds, signature
verification, registry publication, or production entry-point integration.


## Consolidated Review Correction

DREV-001 and DREV-002 were confirmed and corrected: snapshot signer authorization
is now explicit at the release cutoff, and all prefix/current events require
static declarations. New tests cover different signer, missing purpose, all three
terminal key states, and nonselected undeclared keys before/after the cutoff in
both histories. Coordinator inspection also found repeated activation accepted
by the preserved helper; the new adapter rejects it without editing predecessor
history. This candidate still claims no cryptographic or production proof.


## Atomic Issuance Capture

The protected issuance repository publishes the prepared snapshot and signed
release together, conditional on the exact current key-history head and status
generation captured during preparation. Signing can happen outside that CAS;
a changed head/generation makes publication fail and requires fresh preparation
and signatures. Neither object becomes an issued authority on a failed CAS.
The immutable repository records their pair and exposes a snapshot for approval
verification only when it belongs to that committed release/snapshot pair. The
repository owns this publication precondition; the public verifier cannot select
or override a historical head. The snapshot digest binds the actual head, so no
redundant timestamp-derived head coordinate is added to the release.

Completeness means every event appended when this issuance CAS succeeds. It does
not mean every event whose effective timestamp is earlier than the issue instant:
an equal-time event can be appended later. Such a later event cannot authorize
past issuance but participates in current-status reduction. Rejecting every
suffix with an equal effective timestamp would reintroduce the very ambiguity
this correction removes. A new CAS model proves stale capture rejection for
an unrelated appended event with equal, earlier-than-use, or future effective
time, atomic absence on failure, fresh complete capture, and immutability when
an equal-time append happens after successful publication. This models publication
ordering only; production repository transactions/signing remain unimplemented.

Test-review findings ISS-PFX-T01 through T04 were confirmed and addressed as one
bounded evidence action: positive current extension, coherent truncation, changed
nonselected declaration, legacy missing reference, every missing/extra snapshot
field, and each direct oversized byte stream now have public-entry cases.

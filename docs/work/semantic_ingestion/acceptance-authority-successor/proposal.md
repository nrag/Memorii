# Temporal Authority And Closed Public Byte Entry

This is a successor amendment to the rejected acceptance-authority candidate.
It is an acceptance-owned design: it changes neither canonical SIA bytes nor a
production module.  It resolves the predecessor's three missing contract
families as one state machine and gives the future implementation a public
byte-entry proof.  The SIA contract at 1209-1268 remains authoritative for the
release and verified-result fields; the amendment makes its stated lifecycle
checks executable without selecting a key, threshold, policy, dataset, or
acceptance outcome.

## Requirements Ledger

| ID | Requirement and measurable result | Owner/evidence maturity |
| --- | --- | --- |
| AA-S01 | The public `CapabilityBaselineApprovalVerifier.verify(release_bytes, baseline_artifact_bytes, evaluation_time)` scans every caller and protected-provider byte stream before decoding, then validates exact modeled shapes and types. | Future `acceptance/capability_baseline_approval.py`; specified, locally verified only by the successor model. |
| AA-S02 | Authorization at issuance uses the complete append-only key-event prefix at `issued_at`, ordered by `(effective_at, global_sequence)`; equal times have one unique sequence. Events after issue cannot grant retroactive authority. | Same owner and protected acceptance lifecycle repository; specified/model proof. |
| AA-S03 | The verifier checks the selected release at `evaluation_time`, current protected checkpoint, current release/key heads, static key validity, issuance-time authorization, expiry, receipt ordering, and immutable release reduction. | Same owner plus protected status provider; specified/model proof. |
| AA-S04 | All signed artifact bodies and nested modeled coordinate/event/receipt shapes are closed: every named field is present, unknown fields, duplicate JSON keys, wrong native types, and invalid enums fail before signature acceptance. | Same owner; specified/model proof. |
| AA-S05 | Rotation, retirement, revocation and compromise preserve historical signature verification but never permit a retired/revoked/compromised key to issue or currently authorize a release. | Same owner; specified/model proof. |
| AA-S06 | A withdrawal acknowledgement is usable only after the production revocation receipt has an advanced production epoch and a completion time no later than the protected checkpoint/evaluation boundary. | Acceptance control plane and deployment authority bridge; specified/model proof. |
| AA-S07 | Normal acceptance evaluation reaches the canonical acceptance verifier with protected authority. Deployment issuance consumes only its verified digest; production never imports acceptance schemas, keys, or verifier. | Future composition and deployment issuer; design binding only, not implemented. |

## Closed Contract And Chronology

All new bodies are canonical CTV v3 maps. Let `U` be the body with exactly its
own `*_digest` and `signature` members omitted, `P` the complete registered
profile-binding bytes, and `LP(x)` the unsigned 64-bit big-endian length of x
followed by x. Its digest is exactly `SHA256(LP(ASCII(domain)) || LP(P) ||
LP(CTV(U)))`. Its Ed25519 message is exactly `CTV({purpose: literal purpose,
complete_binding: P, signer_coordinate: SigningKeyCoordinate,
recomputed_body_digest: digest, unsigned_canonical_content: CTV(U)})` under
the registered profile; no other member is omitted or inferred. This is not a
wire decision left to implementation. `SigningKeyCoordinate` is the exact
four-member coordinate in the predecessor proposal.
The signed release remains the SIA `CapabilityBaselineApprovalRelease`; its
previously specified fields are all required, including nullable lifecycle
members. A concrete implementation must register exact CTV schema bindings for
the release, trust snapshot, key event, checkpoint and receipt before it can
parse any body.

`KeyLifecycleEvent` has exactly:

```text
key_reference, state, effective_at, global_sequence,
predecessor_key_event_digest, issuance_trust_snapshot_digest,
event_digest, signing_key_coordinate, signature
```

`state` is `active|retired|revoked|compromised`. The initial event for a key is
only `active`; the only successor is `active -> retired|revoked|compromised`.
Events have a global contiguous sequence and exact predecessor digest. The
total reduction order is `(effective_at, global_sequence)`, with global
sequence unique and contiguous even when timestamps tie. The provider rejects
decreasing pairs, ties with duplicate sequence, gaps, alternate predecessors,
undeclared keys, later activation, and any event whose signer does not have the
separate status purpose. A key is eligible to sign a release only when its
latest event at `release.issued_at` is `active`, its snapshot declaration
permits approval purpose, and its static validity interval contains issue time.
It must also remain active at `evaluation_time` for a release to be current.
This deliberately distinguishes historical signature verification from current
authorization.

The preserved predecessor model remains the closed release-lifecycle owner:
the SIA immutable `active A -> superseded|revoked T ->
active B` chain. A terminal release is a new signed body, names the immediate
active predecessor and copies every target/capability/policy coordinate; B is a
new exact successor with epoch `T.epoch + 1`. The reduction re-derives the
unique pointer after every record. Same-target terminal records, repeated
terminal action, active-to-active, terminal-to-terminal, forks, skipped
sequences, replacement before durable revocation acknowledgement, and any
attempt to revive an old digest reject. A `revoked` T requires `revoked_at`;
`compromise_effective_at`, when present, is no later than it. A compromise key
event at or before a release issue invalidates issuance. A later compromise
does not rewrite history, but prevents current authorization at use time.

`CurrentStatusCheckpoint` exactly contains capability fingerprint, strictly
increasing status generation, snapshot digest, complete release-chain head
digest/sequence, complete key-event head digest/sequence, all-null or
all-present active-pointer digest/epoch/sequence, ordered production-revocation
receipt digests for the reduced terminal transitions, observed time, digest,
signer coordinate and signature. It is signed by the status anchor and loaded
only from a protected latest-status provider. The verifier replays complete
release and key histories to the signed heads and recomputes all three pointer
coordinates. An old valid prefix cannot become current by omitting a later
revocation. A provider outage, duplicate latest generation, rollback, mismatch
or missing history fails closed.

This successor is only the temporal and byte-entry extension of that preserved
reduction. It requires the authenticated predecessor current pointer and heads
as its inputs; it neither replaces nor weakens A->T->B. Before promotion, its
focused proof must execute both reductions with a terminal/replacement fixture.

`ProductionRevocationReceipt` exactly contains prior approval-release digest,
withdrawal-requested time, prior production epoch, advanced production epoch, completed time, digest,
signer coordinate and signature. It is a separately purpose-bound production
receipt. For every A->T, exactly one receipt names A, has advanced epoch greater
than prior epoch, and completes after the withdrawal was requested but no later
than T/checkpoint acknowledgement. B cannot be current before that receipt.
This represents SIA 3942-3970's required durable production revocation before
replacement activation; it does not let acceptance inspect production trust.

## Public Byte Entry And Limits

`CapabilityBaselineApprovalVerifier.verify` is the only public acceptance
entry. Callers provide only `release_bytes`, `baseline_artifact_bytes`, and
explicit `evaluation_time`; constructors receive protected anchors, bootstrap
ceilings and a protected current-status provider. They do not accept a public
key, snapshot, pointer, status history, limits, receipt, provider, or approval
override. The provider returns raw bytes for the unique current checkpoint,
complete referenced histories, and a closed predecessor-reduction result with
active release digest/epoch/sequence, key-head sequence, withdrawn receipt
digest, receipt own digest, and that receipt's prior and advanced production epochs. The verifier reconstructs the preserved A->T->B result first and
compares every protected coordinate to the request, checkpoint, and receipt;
a valid but different predecessor result rejects. Every returned byte stream
crosses the same bounded scanner before a general JSON/CTV decoder.

The protected evaluator samples `evaluation_time` with its latest status
generation; `checkpoint.observed_at` must equal that instant. An earlier
checkpoint is a stale prefix, while a later checkpoint was not available at the
evaluation instant. This is a coverage rule, not a freshness duration or policy
threshold. Static key intervals are `[valid_from, valid_until)`: the start is
eligible, a null end is unbounded, and the end instant is ineligible. An event
participates exactly when `(effective_at, global_sequence)` is at or before the
cutoff pair; sequences are contiguous, so equal event times remain total.

The receipt's own digest uses the same defined `LP(domain) || LP(P) ||
LP(CTV(U))` digest construction under the receipt domain. Its digest must match
the supplied authenticated receipt, checkpoint, and predecessor result, in
addition to matching the withdrawn release and the exact increasing production
epoch transition. A valid receipt for the same withdrawn release is therefore
not interchangeable when its own digest or epoch transition differs.

The protected bootstrap scanner checks, before general decode or signature
verification: total raw bytes, maximum depth, total scalar/container/key nodes,
decoded UTF-8 string bytes including escapes, integer digit count, valid UTF-8,
JSON syntax, no duplicate keys, and the CTV subset/profile framing. It rejects
float/exponent numbers, malformed escapes/surrogates and non-map roots. The
bootstrap values are protected deployment configuration. The signed snapshot
may only narrow each ceiling; a signed expansion rejects. A later CTV decoder
must reapply effective ceilings and exact closed schema validation, so signing
cannot authorize unbounded parsing or field smuggling.

The feasibility model uses compact JSON aliases only to prove the entry order
and failure categories. It is not a CTV or signature implementation, does not
claim production cryptographic verification, and does not substitute for the
registered schemas or independent CTV expected-byte vectors. The required
implementation proof uses separately written encoder and decoder expected-byte
vectors for map key ordering by encoded UTF-8 JSON-string bytes, including
ASCII/control/non-ASCII keys and nested maps.

## Authority, Promotion, And Runtime Binding

```text
caller release/baseline bytes
  -> acceptance CapabilityBaselineApprovalVerifier.verify
  -> protected CurrentAcceptanceStatusProvider.load_current_bytes
  -> bounded decode + CTV closed schemas + signature/time/replay reduction
  -> VerifiedCapabilityBaselineApproval(release_digest)
  -> DeploymentAuthorizationIssuanceRequest
  -> production DeploymentAuthorization issuer (digest only)
```

`production_entrypoint_bindings` amendment (design target; current status is
unimplemented):

| Requirement | Non-test production trigger | Canonical owner and authority arguments | Durable outcome / fail-closed absence | Proof required for implementation completion |
| --- | --- | --- | --- | --- |
| AA-S07 / SIA-R13 | Normal acceptance release evaluation before deployment authorization issuance | `acceptance.capability_baseline_approval.CapabilityBaselineApprovalVerifier.verify(release_bytes, baseline_bytes, evaluation_time)`; constructor-held `AcceptanceTrustAnchor`, protected `CurrentAcceptanceStatusProvider`, protected bootstrap ceilings | Emits only `VerifiedCapabilityBaselineApproval`; missing/outage/currentness failure emits no verified object and no issuance request | A non-test acceptance CLI/evaluator caller reaches `verify` with protected constructor authority; owner-stripping tests prove it cannot inject keys/history/limits. |
| AA-S07 / SIA 3942-3970 | Deployment authorization issuance for `capability_baseline` | `DeploymentAuthorizationIssuer.issue(request)` receives only the verified release digest and stable target digest | Signed production authorization or no artifact; missing verified digest fails issuance | A normal issuer path consumes the exact verified digest; static import proof shows production imports no acceptance schema/key/provider. |
| AA-S06 / SIA-R13 | Acceptance lifecycle withdrawal acknowledgement/replacement publication | protected acceptance lifecycle command -> production revocation command -> signed receipt -> protected status publication | Durable production revocation epoch advances before checkpoint/current pointer can acknowledge terminal/replacement state; any missing receipt fails closed | End-to-end non-test control-plane path proves receipt order and restart recovery. |

The first row is intentionally a design binding, not an implementation claim.
The successor cannot mark it complete until a Spark mapper records an actual
non-test caller, exact arguments and protected authority construction in the
canonical binding ledger. Promotion then changes, as one atomic review unit:
SIA release text, CTV profile-v3 schema registrations, independent canonical
encoder/decoder, acceptance verifier/provider/CLI, deployment bridge,
byte vectors, production-entrypoint binding ledger, and CI jobs. Existing v1/v2
artifacts remain replay-only; no compatibility reader accepts a successor
unknown field or an incomplete predecessor shape.

## Verification, Identity, And Gate Ledgers

| Family | Required evidence | Status here |
| --- | --- | --- |
| Chronology | Independently authored expected outcomes for same-time sequence, future rotation, historical rotation, retirement, revocation, compromise before/after issue, expiry, out-of-order/missing/duplicate events, receipt ordering and checkpoint rollback. | Model tests specify representative cases; independent evaluator vectors pending implementation. |
| Byte entry | Boundary and one-over tests for each raw/depth/node/string/integer ceiling at every caller/provider artifact; malformed UTF-8/escapes, duplicate key, non-map, float/exponent and nested excess. | Model calls scanner from its actual public `verify`; full scanner parity pending. |
| Closed schemas | One-field omission/type/unknown/duplicate/enum mutation for every signed body and nested member, then trusted re-signing mutation. | Model release shape/type/unknown omissions; exhaustive schema-generated suite pending. |
| CTV | Independently specified expected bytes for all selected profile-v3 forms and encoded JSON-string map-key sorting; compiler and independent checker agree without shared encoder. | Pending canonical promotion. |
| Production binding | Real acceptance evaluator/CLI and deployment issuer path with owner stripping, receipt restart, and import boundary. | Explicitly unimplemented; parent R14 remains partial. |

Identity ledger: `AA-S01` through `AA-S07` are traceability coordinates only;
they occur only in this packet. Behavioral identities are the
literal protocol types and purposes above, `CapabilityBaselineApprovalRelease`,
`VerifiedCapabilityBaselineApproval`, `CapabilityBaselineApprovalVerifier`,
`CurrentAcceptanceStatusProvider`, and `ProductionRevocationReceipt`. The
successor files are documentation and nonproduction feasibility artifacts only;
they introduce no persisted artifact, production symbol, CI identifier, or
externally visible schema. No requirement coordinate may enter canonical CTV,
digest preimage, receipt, release, checkpoint, or runtime error bytes.

Gate ledger: the root must freeze this proposal/model/tests by SHA-256, run the
focused proof with warnings-as-errors, Ruff and Pyright, and then obtain one
consumer root review followed by spec/correctness/test reviews of that frozen
candidate. The implementation phase may begin only after those reviews approve
the amendment. Passing this model is deterministic feasibility evidence only;
it is neither R14 certification, CI enforcement, a production binding proof,
nor operational acceptance.

## Review Reconciliation

Root classified the final sequence, receipt identity, checkpoint coverage,
integer grammar, and byte-boundary observations as Not applicable /
changes_required design-conformance or evidence actions. This amendment resolves
them without choosing an external key, threshold, dataset, or policy outcome.

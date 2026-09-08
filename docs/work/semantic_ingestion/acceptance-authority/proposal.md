# Capability Baseline Approval Authority Proposal

This proposed acceptance-only prerequisite preserves SIA 1209-1268 release and
verified-result fields. It does not yet promote canonical schemas or runtime.
The following contract supersedes the abbreviated construction note at the end.

## Ownership And Closed Contracts

The owner is root `acceptance/`, outside the production wheel, with no imports
from production semantic, policy, identity, persistence, observation, simulator
or compiler helpers. Cryptographic primitives may be shared. The future public
verifier accepts only release bytes, baseline bytes and explicit evaluation time.
Protected configuration owns anchors, loaders, bootstrap ceilings and the current
status provider. CLI callers cannot supply keys, snapshots, pointers, status,
limits, a provider or an approval flag.

Use Ed25519 PureEdDSA, empty context/no prehash, profile
`memorii.acceptance.ed25519.rfc8032.v1`. Public keys are 32 raw bytes; signatures
are canonical padded base64 encoding 64 bytes. Digests are lowercase SHA-256 hex;
times are canonical UTC; positive integers exclude bool. Text is nonempty Unicode
scalar text. Every listed field is required, including nullable fields; unknown
fields, enums, duplicate keys and omitted values reject.

`Binding` is the complete SIA 2695 `CanonicalTypedValueProfileBinding`, with its
recomputed digest. New inventory uses profile version 3 and preserves encoded
UTF-8 JSON-string-byte map-key order. Existing v1/v2 bytes/bindings remain frozen.
The closed proposed root fields are:

```text
SigningKeyCoordinate = {key_reference: Text, signature_profile_id: Text,
  purpose: Text, public_key_fingerprint: Digest}
SigningKey = {key_reference: Text, approver_subject_id: Text,
  signature_profile_id: Text, public_key_bytes: Bytes32,
  public_key_fingerprint: Digest, valid_from: Time, valid_until: Time|null,
  allowed_purposes: tuple[Text], key_static_digest: Digest}
VerifierLimits = {max_release_bytes: PositiveInt, max_baseline_bytes: PositiveInt,
  max_snapshot_bytes: PositiveInt, max_key_record_bytes: PositiveInt,
  max_checkpoint_bytes: PositiveInt, max_receipt_bytes: PositiveInt,
  max_chain_records: PositiveInt, max_key_records: PositiveInt,
  max_ctv_depth: PositiveInt, max_ctv_nodes: PositiveInt,
  max_string_bytes: PositiveInt, max_integer_digits: PositiveInt}
IssuanceTrustSnapshot = {authority_id: Text, keys: tuple[SigningKey],
  limits: VerifierLimits, snapshot_digest: Digest,
  signing_key_coordinate: SigningKeyCoordinate, signature: Text}
KeyStateRecord = {key_reference: Text,
  state: active|retired|revoked|compromised, global_sequence: PositiveInt,
  predecessor_record_digest: Digest|null, issuance_snapshot_digest: Digest,
  recorded_at: Time, record_digest: Digest,
  signing_key_coordinate: SigningKeyCoordinate, signature: Text}
ActiveApprovalPointer = {capability_fingerprint: Digest, release_digest: Digest,
  target_approved_capability_baseline_artifact_digest: Digest,
  acceptance_release_epoch: PositiveInt, acceptance_release_sequence: PositiveInt,
  chain_head_digest: Digest, chain_head_sequence: PositiveInt, pointer_digest: Digest}
CurrentStatusCheckpoint = {capability_fingerprint: Digest,
  status_generation: PositiveInt, issuance_snapshot_digest: Digest,
  chain_head_digest: Digest, chain_head_sequence: PositiveInt,
  key_head_digest: Digest, key_head_sequence: PositiveInt,
  active_pointer_digest: Digest|null, active_release_epoch: PositiveInt|null,
  active_release_sequence: PositiveInt|null, observed_at: Time,
  checkpoint_digest: Digest, signing_key_coordinate: SigningKeyCoordinate,
  signature: Text}
ProductionRevocationReceipt = {prior_approval_release_digest: Digest,
  prior_production_epoch: PositiveInt, advanced_production_epoch: PositiveInt,
  completed_at: Time, receipt_digest: Digest,
  signing_key_coordinate: SigningKeyCoordinate, signature: Text}
```

Release, baseline and six-field verified result retain their exact governing
SIA schemas. Keys sort uniquely by reference; purposes sort uniquely by text.
Key fingerprints hash the exact raw public-key bytes. One immutable snapshot
declares all keys available to a lineage, including staged rotation keys.
In-place static-key, snapshot and root-anchor replacement are outside this
bounded protocol; they cannot reinterpret historical bytes.

## Signatures And Dependencies

The acyclic construction is anchors -> snapshot -> signed release chain and
global key log -> replay pointer -> current checkpoint. A snapshot/release
never hashes a later checkpoint. Receipts refer backward to withdrawn approvals.

Digest preimages length-prefix domain, full binding bytes and unsigned canonical
content with unsigned 64-bit big-endian byte lengths. Omit only the body's own
digest and signature; an unsigned pointer omits only its digest. Signatures cover
a closed CTV map `{purpose, complete_binding, recomputed_body_digest,
unsigned_canonical_content: bytes, signing_key_coordinate}`.

Each root has a distinct literal purpose/domain pair. Purposes are
`semantic_ingestion_capability_baseline_` followed by `issuance_trust`,
`key_state`, `approval`, `current_status`, or `production_revocation`.
Domains are `memorii:sia-capability-baseline-` followed respectively by
`issuance-trust`, `key-state`, `approval-release`, `status-checkpoint`, or
`production-revocation-receipt`, then `:v1` and one NUL byte. Pointer domain uses
the same prefix followed by `active-pointer:v1` and one NUL byte. The compiler
registers each full pair and field set; artifacts cannot select bindings.

Protected anchors authorize snapshot/key-log signing, checkpoint signing and
receipt signing separately. Coordinates must match reference, profile, purpose
and fingerprint exactly, even when two roles use identical key bytes. Release
coordinates derive from the signed key reference, approver, literal approval
purpose and verified snapshot entry. Issuance requires that key's purpose,
approver and validity interval to match. No caller-supplied public key is used.

## Immutable Release And Key State Machines

A lineage is scoped by capability fingerprint, not baseline artifact digest.
Every new record is a new immutable SIA release. Sequence starts at one and is
contiguous; inputs must already have that order. Every non-genesis record names
the immediately preceding digest in `supersedes_release_digest`. Epoch starts
at one. Missing records, forks, duplicate coordinates and reorderings reject.

| Prior | New record | Required transition |
| --- | --- | --- |
| none | active A | sequence/epoch 1, predecessor null, terminal times null; pointer A |
| active A | superseded T | same epoch and copied authority coordinates; terminal times null; pointer null |
| active A | revoked T | same epoch and copied authority coordinates; revoked_at present, compromise time optional and no later than revoked_at; pointer null |
| terminal T | active B | next sequence and epoch exactly T.epoch+1; terminal times null; independently verified replacement baseline; pointer B |

T copies A's target, capability, capability contract, dependency bundle, coverage,
statistical gate, monitoring policy and unsupported-cell digests. T has its own
authorized issuer/key and issue/expiry times. B preserves capability identity but
may approve a different baseline. A's bytes never change. Active-to-active,
terminal-to-terminal and actions against older noncurrent records reject. Those
older-record actions belonged to the rejected proposal, not a SIA requirement.
Replaying old bytes cannot revive their digest as a new approval.

SIA 3947 requires durable revocation of every production authorization naming A
and advancement of production's epoch before T acknowledgement or B activation.
The protected receipt authority signs completion only after that operation.
Require exactly one matching authenticated receipt for every A->T pair, completed
no later than the checkpoint. Its advanced production epoch must exceed its
prior production epoch; acceptance epochs are independent and never compared.
Missing, stale, ambiguous or substituted receipts deny acknowledgement/activation.
A crash leaves the transition pending and retry uses the same A identity.

The global key ledger has contiguous sequence and global predecessor digest,
and reduces to a map by declared key reference. Its only legal transitions are
absent->active and active->retired/revoked/compromised. Undeclared references,
unknown states, duplicate activation and revival reject. Historical signatures
remain verifiable against immutable issuance keys after retirement, but the key
of the selected current active approval must be active at use time. A new staged
key can sign B while A's key retires; unrelated entries cannot hide key loss.

## Currentness, Baseline And Resource Boundaries

The protected status provider serializes strictly increasing generations and
supplies its unique latest checkpoint, never a caller-selected historical prefix.
The verifier authenticates its exact capability, snapshot, chain/key heads and
sequences, time, and recomputed pointer. Pointer digest/epoch/sequence are all
null or all equal the derived nonnull values. All-null never emits approval.
Provider failure, rollback or ambiguity denies. A signature alone does not prove
latestness; serving the current generation is a protected-provider obligation.

Verify all issuance signatures and authorization at issue time. The selected
active release also requires issued_at <= evaluation_time < expires_at, current
key eligibility and exact independently recomputed baseline/policy coordinates.
SIA 3921-3930 excludes only the deployment authorization attachment from stable
baseline content, so subsequent authorization attachment cannot create a cycle.

Protected ceilings cap raw artifact bytes and collection counts before load or
decode. A bounded scanner accounts for depth, every container/scalar/key node,
decoded string UTF-8 bytes including escapes, and integer digits before general
decoder allocation. Unknown/malformed forms, duplicates and unpaired surrogates
reject. Recursive scanners must enforce a fixed implementation-safe maximum
depth; iterative scanners may implement larger explicit ceilings. Signed limits
can only narrow protected ceilings and are re-applied after authentication.
Full canonical CTV validation remains a separate required stage.

## Feasibility Limits And Promotion

The Python model is deliberately nonproduction, with compact coordinate aliases
and a fixture binding. It is not the normative wire implementation and does not
prove complete registered schemas, generic CTV, all time/resource limits, signing
template interoperability or operational latestness. Only root-observed tests
establish the particular modeled invariants. No model success closes R14.

After independent approval, promote the exact roots/preimages plus approved
numeric roots into SIA, profile-v3 compiler and independent checker together.
Regenerate the registry, structural inventory, vectors, checksums and CI pins.
Keep old v1/v2 bindings for replay. The acceptance CLI takes release, baseline,
evaluation time and output only. Its verified digest feeds existing deployment
authorization issuance; production independently verifies serialized output.
Full context reconstruction, CLI, receipt administration and host composition
remain explicit implementation work.

## Superseded Construction Note

The abbreviated note below is retained history, not a separate contract or
current evidence claim.

Status: proposed, nonnormative, acceptance-only feasibility contract.

The immutable release grammar is exactly `active A -> terminal T
(superseded|revoked) -> fresh active B`. Every record receives a new digest and
contiguous global sequence. T supersedes exactly immediate A, retains A's
capability fingerprint, target baseline, dependency, and policy coordinates,
and does not decrease epoch. `revoked` requires `revoked_at`; `superseded` has
null terminal times. B supersedes T, increments epoch, has null terminal times,
and can select a replacement baseline. A's bytes never change.

Active-to-active, terminal-to-terminal, older noncurrent actions, forks,
skipped predecessors, and revival fail closed. Post-terminal actions against an
older release are explicitly unsupported because SIA does not require them.

The signed checkpoint binds complete release-chain head/sequence, global
key-ledger head/sequence, and an all-null/all-present replay pointer group.
The ledger permits unrelated entries and rotation but only
`absent -> active -> retired|revoked|compromised`. Snapshot trust declares keys,
purposes, and a distinct anchored status key/fingerprint. Every signature binds
purpose, complete binding, signer coordinate, unsigned content, and digest.

Terminal acknowledgement or B activation requires a trusted production
revocation receipt binding A and an advanced production epoch; missing,
substituted, and stale receipts reject. The in-memory status provider is
root-held only.

The model accepts only a bounded JSON subset (object, array, string, integer,
boolean, null; no floats/exponents). Its scanner caps raw bytes, depth, all
nodes including keys, decoded escape bytes, and integer digits before
`json.loads`. It demonstrates that subset only, not a generic CTV parser.

No runtime or canonical artifact changes are proposed. There is no
`production_entrypoint_bindings` entry because no production caller exists;
this slice makes no reachability, persistence, or operational-authority claim.

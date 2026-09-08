# Operational Semantic Ingestion Observation

This target contract supplements semantic_ingestion_architecture.md for the
profile-3 observation route. Implementation and runtime activation are distinct
from specification. The user approved a separate operational profile with exact
historical byte preservation on 2026-09-06, and separate temporal/trust projection
observations on 2026-09-07. No release signature or external statistical threshold
is selected here.

For this route, the versioned contracts below replace the corresponding proposed
single-projection observation, source-local revision, and registry-publication
shapes. Historical profile-2 artifacts retain their existing reader contracts.
The test-only fixture-56 compiler and its historical profile are not runtime
registry authority. Core memory-domain, candidate/commit, graph/overlay and
framework-neutral boundaries remain governed by the repository specifications.

The implementation path is ProviderMemoryService through the built-in semantic
capability, writer admission and SemanticIngestionAtomicStore. One verified
protected registry is shared by writers, replay and observation. Authorization
precedes a detached full-write store snapshot; all cohort, graph, reference and
projection-history reads use that snapshot. Native accepted group publication
must include canonical projection histories and their replay authority in its
atomic batch. Native policy retention is specified in SIA 4.8.2.26.

The sections retain their construction source filenames as stable cross-reference
labels. They are consolidated here as the governing target contract; work plans
record evidence, review findings and implementation status separately.

## Proposal

Source label: `proposal.md`.

### Hash And Ownership Boundary

The shared ledger belongs to the same atomic-store partition as canonical graph
state, with one conditional head and append-only entries. Sequence is a positive
integer; revision is an opaque content address. Neither is a timestamp. All
fields have closed typed contracts and unknown kinds/versions reject.

A terminal identity is stable across a head conflict: group identity binds the
sealed request/group, source identity binds the operation fence/canonical source
result. The semantic payload contains the exact canonical observation delta
fields except observation_revision_before, observation_revision_after and
delta_digest. Compute payload_commitment from that closed typed payload under
a distinct registered CTV binding. Then compute successor from the exact
repository identity, activation digest, predecessor revision and payload_commitment
(which already includes the stable delta identity). Finally form
the delta with predecessor/successor and compute delta_digest. The immutable
entry binds sequence, delta, commit result locator/digest and entry digest.
The head binds sequence, successor, last entry identity and entry digest.
No hash depends on itself: successor does not contain final delta_digest.

A new append atomically compares the whole current head digest (or absence at
genesis), current writer/lease/control and applicable graph/reference authority,
then writes head, entry, result and all existing effects. Exact duplicate identity
reloads its original entry only after comparing immutable semantic/result inputs.
Changed content under an existing identity rejects before any write. A failed
head CAS publishes nothing. Retry rereads authority and reconstructs assigned
coordinates; it never reruns provider analysis merely to obtain a new head.

### Source Terminal Sealing

The current V2 source request includes a fully prepared revision-bearing delta;
it cannot be rewritten after sealing. New terminal grammar therefore separates
semantic intent from store-assigned receipt data. Preparation seals the existing
canonical source result and all existing semantic terminal members plus one typed
source-outcome intent. That intent contains the exact outcome and observation
schema binding, but no assigned revision, delta digest or caller-selected head.
The stable publication locator derives from that semantic intent and authority.

Inside terminal linearization, the store authenticates and validates the sealed
intent, reads the head, constructs the source delta and its final native member,
and writes its complete actual member manifest, terminal control, identity,
locator/recovery indexes, delta entry and head together. Receipt/reload retain
actual delta and manifest, linked to the original intent. The request digest
identifies intended work; the actual manifest/entry digests identify committed
bytes. Reload must verify both relationships explicitly, never equate request
bytes with a delta that did not exist when the request was sealed.

A terminal retry first checks durable locator/request/recovery identity; an
already committed terminal reloads exact entry bytes even if the global head
advanced. Otherwise it retries through the existing lease/generation policy
with fresh head authority. A head-only conflict does not fabricate a graph
conflict or discard the canonical source result. Exhaustion is typed retryable
progress, never a durable failed source observation.

### Group Append And Replay

Group materialization constructs actual graph/reference mutations and canonical
introductions/outcomes before its atomic batch. Source mention authority comes
from retained planner bindings. A noncommitting delta has exact operation
introduction/outcome pairs and no source introduction or graph delta. A committed
group links its one exact same-transaction GraphRevisionDelta. Group result and
reload retain the assigned delta; all effect/member reads verify byte equality,
not only primary metadata. Local control revision becomes a last-published
checkpoint and may lag the global head; it is never append authority.

Genesis replay walks entries in sequence, verifies exact predecessor/successor,
all payload/entry/head hashes, duplicate identity rejection, terminal operation
pair/source-finalization membership and immutable result/graph links. Graph
record keys and historical before/after versions remain explicit. A checkpoint
must be verified under the existing graph replay trust/rollback principles before
using its prefix; the precise checkpoint authority binding remains to be mapped.
The feasibility model proves only ordering/idempotency/hash acyclicity, not
production checkpoint trust or complete observation schema validation.

### Compatibility, Activation And Snapshot Reads

Legacy terminal V1/V2 and legacy group contracts retain exact bytes and their
existing public result/recovery behavior. No legacy record is silently entered
into the new audit ledger. A legacy source lacking a complete global observation
closure cannot satisfy authenticated structural observation. New writer admission
must require the new grammar and shared-head batch after activation; old writers
cannot continue appending source-local-only audit during a new-ledger epoch.
The exact writer activation marker and checkpoint migration must be mapped before
review; merely creating a head on first write is insufficient mixed-version proof.

Authenticated cohort reads must pin graph/reference/observation authority from
one consistent store snapshot. Seed indexes are only locators, never completeness
authority. Graph snapshot tokens currently omit observation head and therefore
cannot themselves identify the required observation snapshot. A read either
verifies one consistent revision set or returns typed stale failure. Page caches
must retain immutable creation time for age checks without caller authority.


## Closed Contracts

Source label: `closed-contracts.md`.

### Store Record Schemas

All records are frozen/extra-forbidden. Counts are exact integers (not booleans),
identifiers nonempty strings, digests lowercase SHA-256 hex. Unknown variants or
versions fail. Repository identity is the configured store partition's canonical
semantic repository identity; callers cannot override it. Sequence orders the
whole partition, not a single source, tenant selector or wall-clock time.

ObservationLedgerHead has fields schema_version=1, repository_id,
activation_digest, sequence>=0, observation_revision, last_delta_id?,
last_delta_digest?, last_entry_digest?, head_digest. All three optional values
are null exactly at sequence0; revision is genesis exactly at sequence0.
head_digest binds every preceding field. The head record ID is the CTV-framed
repository identity under observation-ledger-head domain. No mutable payload is
excluded from head CAS comparison.

ObservationLedgerEntry has fields schema_version=1, repository_id,
activation_digest, sequence>=1, previous_entry_digest?, semantic_payload_digest,
delta:CanonicalIngestionObservationDelta, result_locator:ObservationResultLocator,
result_digest, entry_digest. previous_entry_digest is null exactly at sequence1.
The typed locator is group-primary or source-terminal with its immutable record
ID and corresponding stable source/group/fence coordinates. Unknown locators
reject. Entry ID derives from repository+delta ID, not sequence. Entry digest
binds every preceding field. Result digest names the immutable canonical result,
not a reload wrapper that itself contains the entry digest.

ObservationResultLocator is the closed union discriminated by `kind` of:

- ObservationGroupResultLocator: kind=`group_primary`, immutable_record_id,
  source_id, source_digest, source_operation_id, operation_fence_id,
  transaction_group_id, operation_ids, request_ctv_digest.
- ObservationSourceResultLocator: kind=`source_terminal`, immutable_record_id,
  source_id, source_digest, source_operation_id, operation_fence_id,
  namespace_id, artifact_generation>=1, member_id, publication_request_digest.

Each locator has schema_version=1. Identity strings are nonempty; source and
request digests are lowercase SHA-256; operation_ids is the exact sorted unique
nonempty tuple from the group request. Group record identity is recomputed by
the existing `_bootstrap_graph_v3_group_commit_primary_id` owner from the four
request coordinates, and source identity by `_bootstrap_graph_v3_member_id`
from namespace, generation and member ID. Locator IDs are not arbitrary lookup
authority. Replay requires those identities, source/fence coordinates and every
request digest to equal the retained request and manifest. Group result_digest
selects the retained BootstrapGraphGroupCommitResultV3.result_digest; source
result_digest selects BootstrapGraphCanonicalSourceResultV3.result_digest.
Neither selects the enclosing reload's digest. The source member must have kind
bootstrap_graph_canonical_source_result and occur exactly once in its verified
terminal manifest. Missing or ambiguous joins reject the complete replay.

ObservationLedgerSemanticPayload is a discriminated union of terminal_group and
source_finalization with EXACT fields of the corresponding canonical delta minus
observation_revision_before/after and delta_digest. It retains delta ID and all
source, scope, result, mutation and schema fields already declared by that delta.
It is a type alias, never a model registry root. Its alternatives are the model
roots ObservationGroupSemanticPayload and ObservationSourceSemanticPayload,
respectively, each at schema_version 1 in profile 3. The `kind` literal selects
exactly that root's protected binding; it cannot select an arbitrary schema ID.
Each payload digest includes that complete selected binding under the fixed
observation semantic-payload domain defined below. A full delta or the other variant fails
shape validation before hashing. No field is added merely to wrap this union.
No extra generic result digest is inserted into a terminal-group payload.
Successor is H(the fixed revision preimage defined below), binding repository,
activation, predecessor and semantic_payload_digest. Final delta digest then includes both revisions.
Full group/source record validation precedes these hashes. The ordering model's
minimal payload is illustrative; it is not this production schema.

### Exact Ledger Hash Preimages

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
its existing native domain and byte grammar.

These are fixed profile-3 ledger protocol domain constants. They are not policy or
caller-selectable values. No new declaration role or model root is introduced;
source/body/declaration cardinality remains unchanged. The emitting/verifying
runtime code and constants must be covered by the activation target's installed
writer payload fingerprint, release package proof and immutable source identity.
No activation target built before that source update can authorize its writer.


### Terminal Intent And Receipt Grammar

SourceObservationIntent contains kind=source_finalization, source_outcome:
CanonicalSourceTerminalOutcomeRecord, observation_schema_fingerprint and
intent_digest. Its typed outcome already closes source/fence/delivery/governance,
operation set, groups and canonical source result. The store recomputes the
schema fingerprint from active registered schema and rejects a mismatch.

Terminal member schema3 introduces source_observation_intent as the final intent
kind. It is NOT persisted as the final source delta. The existing first nine
semantic intent kinds and multiplicities remain exact; the assembler validates
source_outcome equals canonical_source_result_input.completed_canonical_source_result.
Schema3 publication request contains source_observation_intent and forbids a
preassigned source_finalization_observation_delta. It seals all normal authority
and semantic inputs unchanged. Schema3 terminal reload requires exact assigned
source delta plus ledger entry ID/digest; it forbids absence of either.

At linearization, nine semantic intent kinds map to their existing receipt kinds;
source_observation_intent maps to exactly one native source-finalization delta
member. The store compares the reconstructed revision-free semantic source
payload against the intent, validates its assigned head transition, and binds
the actual complete manifest. It never compares final delta digest to the intent
digest. The manifest has exactly the existing members plus the one assigned delta;
entry/head are separate audit/control records in the same CAS, not fake semantic
members. Reload validates request intent, actual member, canonical source result,
entry result locator/digest and historical reachability under current head.

| Grammar | New write | Literal historical reload | Shared audit use |
| --- | --- | --- | --- |
| terminal1 / legacy group | Forbidden after activation | Existing exact bytes | None; missing audit fails cohort closure |
| terminal2 / local observation | Forbidden after activation | Existing exact bytes | None; never relabel local chain global |
| terminal3 / ledger group | Required after activation | Exact new bytes/joins | Entry must be reachable and complete |
| mixed/unknown | Reject | Reject | Reject |

### Activation And Writer Fencing

The exact authority, source closure and fingerprint recipes for activation are
defined by [Observation Activation Target Identity](semantic_ingestion_activation_target.md).
That additive contract preserves the fixed activation fields below.

ObservationLedgerActivation contains schema_version=1, repository_id,
previous_writer_admission_digest, target_writer_epoch, writer_implementation_fingerprint,
observation_schema_fingerprint, ledger_codec_fingerprint,
legacy_terminal_inventory_digest, activation_digest. The inventory covers exact
legacy terminal/control IDs and digests at drain completion; it proves exclusion,
not imported audit. Activation digest excludes only itself. Target admission
retains this digest as an explicit typed field in its new admission/binding
grammar. Legacy admission serializer omits the field only for old grammar.

Store-owned activation first sets the existing draining fence under exact current
admission CAS. No new old-epoch operations may start. Existing operations finish
under old rules. Activation validates every old operation terminal/exhausted and
lease-free against the same complete control inventory used at final CAS; each
record and the inventory partition revision is a precondition. It then atomically
writes activation, genesis head and the incremented writer admission. Existing
nonterminal work prevents activation; it is never force-finalized. Repeating the
identical activated intent returns the same activation after exact inventory and
successor verification. Different content or stale admission rejects.

Every post-activation group/source writer requires current binding activation
digest and current ledger head. ALL legacy mutation recognizers are disabled in
that epoch; historical read/reload remains supported. Public ordinary writes,
unit-of-work batches and low-level atomic owner routes share governed policy.
Rollback can stop new ingestion while preserving read/replay, but cannot restore
an old writer epoch or erase the ledger. A later compatible writer needs a new
explicit migration; no implicit format downgrade is supported.

### Replay, Checkpoint And Resource Contract

Authoritative genesis replay requires an independently read persisted head;
an arbitrary valid prefix is not completeness. It verifies every entry in exact
sequence, repository/activation, unique delta identity, before/after chain,
semantic/final/entry commitments and canonical result/graph links. Retained
source outcomes and operation pairs reconstruct the audit record set without
providers or provenance-index inference. A replay byte parser uses registered
CTV/schema limits before allocation/recursive decoding; resource settings come
from protected deployment configuration and cannot be supplied with entries.

Checkpoint remains the canonical IngestionObservationReplayCheckpoint payload
(SIA23010), with an explicit outer ObservationCheckpointBundle containing
repository_id, activation_digest, sequence, head, canonical materialized ledger,
checkpoint, lifecycle_revision and bundle_digest. The materialized ledger digest
binds the complete typed audit records, delta identities/digests, result/graph
links and prefix head, so merely presenting a matching last delta cannot substitute
a partial prefix. The signed checkpoint's checkpoint_digest preimage MUST bind
the outer repository/activation/sequence/head/lifecycle coordinates as well as
its declared fields. This requires a registered observation-specific preimage;
reusing graph-checkpoint bytes or relying only on unsigned bundle_digest is forbidden.

Observation checkpoint lifecycle is a distinct repository-scoped monotonic owner
with authority_revision, registry revision/digest/history digest, trust policy
revision/digest, minimum_checkpoint_sequence and predecessor authority digest.
Verification compares current protected lifecycle, key issue/current-use state,
repository, activation and rollback floor before using the prefix. Configured
Ed25519 signer/public verifier use explicit raw-public-key fingerprints and
64-byte signatures; no production signature is required for implementation tests.
Checkpoint creation occurs only at a validated committed head and atomically
publishes the exact bundle and checkpoint lifecycle receipt. A concurrently
advanced head retries from new authority; a signature alone cannot activate a
checkpoint. Tail replay starts at exact saved successor and must reach current
expected head. Unsigned/untrusted/stale checkpoints fail closed; no silent
fallback to claiming checkpoint success. Genesis remains a separate explicit
recovery route.

Head retry budget and decoding/ledger snapshot resource ceilings are positive
protected configuration values. Exhaustion yields retryable/stale failure, never
partial ledger state. Tests inject small limits to verify boundaries; these are
operational limits, not statistical acceptance thresholds.


## Operational Profile

Source label: `operational-profile.md`.

### Scope And Owner

The new operational profile is
`semantic_ingestion_typed_value`, version `3`. It applies to the new observation
ledger and its authenticated observation artifacts after activation. The
canonical runtime owner is
`memorii/memorii/core/memory_evolution/ingestion_contracts.py`. That module must
own the profile declarations, fixed-envelope parser, registry value types,
registry verifier, and registered writer/reader. Observation modules supply
typed values to a protected registry selected at composition; they do not
construct bindings, choose decoders, or derive profiles.

Profile 2 and its literal persisted artifacts remain on their existing reader
routes. They retain their original bytes and digests. A successful historical
read is not a ledger entry and must not synthesize globally ordered audit
evidence. The `fixture-v2`/56-root source inventory, its compiler, and its
signing ancestry are neither profile-3 inputs nor runtime authority.

### Published Source Package

Profile-3 publication is a finite set of exact UTF-8 source byte files. They
are data files checked by `ingestion_contracts.py`; no file names, module names,
Python annotations, reflection results, import side effects, or decoder
callbacks are input to any digest. A publication source file is raw declaration
input, not a persisted `CanonicalEncodedArtifact` and not an alternative
artifact codec. This avoids making the profile's own grammar source depend on a
profile that has not yet been verified.

Each source file is RFC 8785 JSON with no terminal LF and with these additional
declaration restrictions: object keys are ASCII nonempty strings; objects have
unique keys and are ordered by their encoded JSON-string bytes; arrays retain
their stated order; values are only objects, arrays, strings, `true`, `false`,
or `null`; JSON numbers are forbidden; and every integer is an ASCII canonical
unsigned-decimal string under an explicitly named key. A declaration source
cannot contain a digest field for itself or its container. The publication
manifest names every file by a stable ASCII role and commits its SHA-256 digest.

The `grammar` role is one literal byte sequence. The following one-line JSON
is the complete grammar-role source bytes (the code fence and its trailing
newline are not bytes):

```json
{"envelope":{"binding_fields":["profile_id","profile_version","profile_digest","schema_id","schema_version","binding_digest"],"fields":["binding","canonical_value_bytes","canonical_value_digest","artifact_digest"],"permitted_value_kinds":["bytes","integer","map","scalar"]},"grammar_revision":"operational-3","json":{"canonical":"RFC8785","terminal_lf":false,"utf8":"strict"},"profile_id":"semantic_ingestion_typed_value","profile_version":"3","role":"grammar","tags":{"bytes":"rfc4648_standard_padded","datetime":"utc_six_fractional_digits","duration_microseconds":"signed_i64","enum":"registered_qualified_member","frozenset":"canonical_member_byte_order","integer":"canonical_decimal_string","list":"declared_order","map":"encoded_json_string_key_order","set":"canonical_member_byte_order","tuple":"declared_order"},"type_rules":{"bool_as_integer":false,"defaults_before_verification":false,"float_decimal":false,"map_keys":"string_only","model_fields":"registered_exact","optional":"registered_policy","union":"one_registered_discriminator"}}
```

The remaining roles use this closed declaration grammar. `object{...}` means
an exact object key set; `array<T>` is an ordered array of `T`; and a role
object has no keys other than those shown.

```text
ascii-id       = one or more ASCII [A-Za-z0-9._/-]
uint           = "0" | [1-9][0-9]*
positive-uint  = [1-9][0-9]*
integer-string = "0" | "-"? [1-9][0-9]*
sha256         = 64 lowercase ASCII hex characters
TypeExpr       = String | Bool | Null | Literal | Integer | Bytes | Datetime | Duration |
                 DecimalQuantity | FiniteBinary64 | EnumRef | ModelRef |
                 List | Set | FrozenSet | VariadicTuple | FixedTuple | Map | Union
String         = object{kind: "string", lexical_rule: "unicode_scalar" |
                        "nonempty_unicode_scalar" | "sha256" | "signature_hex128"}
Bool           = object{kind: "bool"}
Null           = object{kind: "null"}
Literal        = object{kind: "literal", values: array<string | bool |
                        object{integer_value: integer-string}>}
Integer        = object{kind: "integer", lexical_rule: "canonical_decimal",
                        minimum: integer-string | null, maximum: integer-string | null}
Bytes          = object{kind: "bytes", lexical_rule: "rfc4648_standard_padded"}
Datetime       = object{kind: "datetime", lexical_rule: "utc_six_fractional_digits"}
Duration       = object{kind: "duration_microseconds", lexical_rule: "signed_i64"}
DecimalQuantity= object{kind: "canonical_decimal_quantity", field_name: ascii-id}
FiniteBinary64 = object{kind: "canonical_finite_binary64", field_name: ascii-id}
EnumRef        = object{kind: "enum_ref", qualified_id: ascii-id}
ModelRef       = object{kind: "model_ref", schema_id: ascii-id,
                        schema_version: positive-uint}
List           = object{kind: "list", element: TypeExpr}
Set            = object{kind: "set", element: TypeExpr}
FrozenSet      = object{kind: "frozenset", element: TypeExpr}
VariadicTuple  = object{kind: "variadic_tuple", element: TypeExpr}
FixedTuple     = object{kind: "fixed_tuple", items: array<TypeExpr>}
Map            = object{kind: "map", key_kind: "string", value: TypeExpr}
Union          = object{kind: "union", discriminator: ascii-id,
                        alternatives: array<object{discriminator_value: string,
                                                   model: ModelRef}>}
field          = object{name: ascii-id, type: TypeExpr,
                        integrity_role: "ordinary" | "self_digest" | "signature"}
schema-role    = object{role: "schema", schema_id: ascii-id,
                        schema_version: positive-uint, root_kind: "model",
                        fields: array<field>}
enum-role      = object{role: "enum", schema_id: ascii-id,
                        schema_version: positive-uint,
                        enums: array<object{qualified_id: ascii-id,
                                            members: array<object{member_id: ascii-id,
                                                                  wire_value: string}>}>}
optional-role  = object{role: "optional", schema_id: ascii-id,
                        schema_version: positive-uint,
                        fields: array<object{field_name: ascii-id,
                                             policy: "required" | "omittable_nonnull" |
                                                     "required_nullable" | "omittable_nullable"}>}
numeric-role   = object{role: "numeric", schema_id: ascii-id,
                        schema_version: positive-uint,
                        fields: array<object{field_name: ascii-id,
                                             representation: "canonical_decimal_quantity" |
                                                             "canonical_finite_binary64",
                                             encoding_spec_id: ascii-id | null,
                                             unit: string | null, scale: positive-uint | null,
                                             lower: string | null, lower_inclusive: bool | null,
                                             upper: string | null, upper_inclusive: bool | null,
                                             reject_inexact: bool | null}>}
DigestSignaturePolicy = OrdinaryPolicy | SelfDigestPolicy | SignatureOnlyPolicy |
                        ExternalSigningPreimagePolicy
OrdinaryPolicy = object{kind: "ordinary"}
SelfDigestPolicy = object{kind: "self_digest", digest_field: ascii-id,
                          digest_domain: ascii-id}
SignatureOnlyPolicy = object{kind: "signature_only", signature_field: ascii-id,
                              signature_purpose: ascii-id, signature_domain: ascii-id}
ExternalSigningPreimagePolicy = object{kind: "external_signing_preimage",
                                       result_digest_field: ascii-id,
                                       result_signature_field: ascii-id,
                                       preimage_schema_id: "ObservationCheckpointSigningPreimage",
                                       preimage_schema_version: "1",
                                       binding_kind: "observation_checkpoint_v1",
                                       signature_purpose: "observation_checkpoint",
                                       signature_domain: ascii-id}
policy-role    = object{role: "digest-signature", schema_id: ascii-id,
                        schema_version: positive-uint,
                        policy: DigestSignaturePolicy}
decoder-role   = object{role: "decoder", schema_id: ascii-id,
                        schema_version: positive-uint, decoder_id: ascii-id,
                        typed_root_kind: "model", implementation_source_digest: sha256}
upcast-role    = object{role: "upcast", schema_id: ascii-id,
                        schema_version: positive-uint, target_binding: null,
                        upcaster_id: null, implementation_source_digest: null}
registry-role  = object{role: "registry", profile: object{profile_id: ascii-id,
                        profile_version: positive-uint, grammar_revision: string,
                        grammar_digest: sha256, profile_digest: sha256},
                        entries: array<sha256>}
```

Literal values are a nonempty unique set ordered by their canonical source
JSON bytes. `integer_value` declares an exact integer literal in the body, not
an object body or boolean coercion. Literals permit schema-version constants,
the required `true` boundary-selector flag and closed string dispositions
without changing them into tagged enum values. Nullability remains the explicit
field policy. `sha256` and `signature_hex128` mean exactly 64 and 128 lowercase
ASCII hexadecimal characters, respectively; no other implicit string format
is accepted. Domain validation may impose additional cross-field constraints,
but cannot widen these registered types or insert defaults.

Every schema role is a model identified by its own schema ID/version. Every
field name is unique. `FixedTuple.items` is nonempty, and every
other collection's `element`/`value` is one complete TypeExpr. `Union`
alternatives are nonempty, unique by discriminator value, and reference only
model schemas; a union discriminator must name a field declared by every
alternative with a singleton string `Literal` equal to its discriminator value.
`Integer.minimum` and `maximum` are either null
or canonical integer strings, with minimum no greater than maximum. The two
numeric wrappers name their owning root-model field and have exactly one
matching numeric-policy row. No other TypeExpr may name a numeric-policy row.

Every repeated declaration is sorted by its semantic coordinate before source
emission: schema fields, optional fields, and numeric fields by encoded JSON
field name; enums by qualified ID and their members by member ID; union
alternatives by discriminator value; and every name list by encoded JSON-string
bytes. The
schema field-name set and optional field-name set must equal exactly. The numeric
role field-name set must equal exactly the root schema fields represented by a
numeric wrapper. Decimal entries require non-null unit, scale, lower/upper,
inclusivity, and `reject_inexact`; binary64 entries require all those values
null. Each schema has exactly one discriminated digest/signature policy. The
policy is selected from this closed grammar; its kind determines every field
omission, so a declaration cannot provide an arbitrary member or exclusion
list.

`ordinary` requires that every field has `integrity_role="ordinary"`; it is the
only policy for a digest-free root. `self_digest` requires exactly one field
named by `digest_field` with `integrity_role="self_digest"`, no signature
field, and computes its body from every declared root field except that digest
field. `signature_only` requires exactly one field named by `signature_field`
with `integrity_role="signature"`, no self-digest field, and signs every
declared root field except that signature field. Its signature message adds the
registered purpose, complete binding, and exact schema-specific body under
`signature_domain`, plus the SHA-256 digest of that complete unsigned preimage,
as fixed by Section 3.15.1. The digest is a signing input, not an added cursor
field. A signature-only policy cannot
select a second body or omit a referenced digest.

`external_signing_preimage` is the one finite exception to root-body
subtraction. It is valid only for `IngestionObservationReplayCheckpoint.v1`;
`result_digest_field` and `result_signature_field` name its one `self_digest`
and one `signature` field, and the referenced preimage coordinate and literal
purpose must equal the values shown in the grammar. Its complete body is
assembled by the fixed
`observation_checkpoint_v1` constructor below, not by reflection, a callback,
or a configurable field subset. The referenced
`ObservationCheckpointSigningPreimage.v1` uses `ordinary`: it contains neither
a self digest nor a signature. A publication
rejects every other use of `external_signing_preimage`, a mismatched literal,
an undeclared integrity field, or more than one field of an integrity role.

The fixed `observation_checkpoint_v1` constructor receives only the typed,
already-verified values in this order: registered purpose literal; repository
ID; activation digest; sequence; head; complete lifecycle including authority
digest; and the canonical checkpoint fields excluding `checkpoint_digest` and
`signature`. It emits `ObservationCheckpointSigningPreimage.v1` and requires
equality with the containing bundle's repository, activation, sequence and head,
and the checkpoint's state digest, last delta ID/digest, observation revision,
and protected creation-time
constraints. It then computes `checkpoint_digest` from that complete preimage
and writes the signature returned for the same frozen preimage.
The constructor has no optional source, lookup, or caller-specified projection.
This is the replay-snapshot contract's explicit external authority binding, not
a generic external-field facility.

Every `ModelRef`, union model alternative and external-signing preimage schema
reference resolves to exactly one declared schema role. The external-signing
reference is an explicit dependency edge, included in the same schema and policy
closure as a ModelRef. The transitive dependency graph is acyclic; self-reference,
unresolved coordinates, and duplicate schema coordinates reject. Every
`EnumRef` resolves to exactly one enum declaration in the reachable schema
closure. The schema fingerprint includes the complete reachable schema-role
bytes, not only the root role:

```
schema_fingerprint = SHA256(LP(
  "semantic-ingestion-typed-value-schema-fingerprint",
  root_schema_id, root_schema_version, closure_count,
  schema_id[0], schema_version[0], schema_role_bytes[0],
  ...,
  schema_id[closure_count - 1], schema_version[closure_count - 1],
  schema_role_bytes[closure_count - 1]
))
```

The closure includes the root and every model schema reachable through any
TypeExpr, ordered by `(schema_id, schema_version)` UTF-8/unsigned-integer
tuple. Enum roles declare each qualified enum identity exactly once across the
closure and every EnumRef must resolve. All policy digests bind that complete
transitive closure as specified below, including optional/numeric/exclusion
rules on nested models. Changing a nested policy cannot retain a root binding.

The required roles are:

| Role | Exact content committed by the role |
| --- | --- |
| `grammar` | The literal `role`, `profile_id`, `profile_version`, `grammar_revision`, `json`, `envelope`, `tags`, and `type_rules` object above. Its rule names are closed parser instruction IDs, never prose interpreted at runtime. |
| `schema/<schema_id>/<schema_version>` | `role`, `schema_id`, `schema_version`, `root_kind`, and `fields`, with each field's recursive discriminated `TypeExpr` exactly as defined above. |
| `enum/<schema_id>/<schema_version>` | `role`, `schema_id`, `schema_version`, and `enums`; each enum has `qualified_id` and ordered `members`, each with `member_id` and `wire_value`. An empty enum table is `[]`, never an omitted role. |
| `optional/<schema_id>/<schema_version>` | `role`, `schema_id`, `schema_version`, and `fields`; each schema field occurs exactly once with its one policy: `required`, `omittable_nonnull`, `required_nullable`, or `omittable_nullable`. |
| `numeric/<schema_id>/<schema_version>` | `role`, `schema_id`, `schema_version`, and `fields`. Each numeric field declares `field_name`, `representation`, and its exact lexical/range policy. Decimal entries name unit, fixed positive scale, inclusive/exclusive lower and upper bounds, and `reject_inexact`; binary64 entries require the fixed 16-lowercase-hex grammar and forbid NaN, infinity, and negative zero. An empty table is `[]`. |
| `digest-signature/<schema_id>/<schema_version>` | `role`, `schema_id`, `schema_version`, and exactly one discriminated `policy`. `ordinary`, `self_digest`, `signature_only`, and the one checkpoint-only `external_signing_preimage` have the closed declarations above; no role carries a configurable member or exclusion list. |
| `decoder/<schema_id>/<schema_version>` | `role`, `schema_id`, `schema_version`, `decoder_id`, `typed_root_kind`, and `implementation_source_digest`. This is descriptive and committed; it is not executable input. |
| `upcast/<schema_id>/<schema_version>` | The exact null-only `upcast-role` grammar above. Every profile-3 entry has no upcast. |
| `registry` | `role`, `profile`, and `entries`, where `entries` is the ordered complete list of entry digests. |

### Exact Numeric Wrapper Encoding

The profile-3 numeric primitives use the existing CTV model-map algebra. A
CanonicalFiniteBinary64 value has exactly one string member, ieee754_hex:

```json
{"$type":"map","entries":[["ieee754_hex","3ff0000000000000"]]}
```

A CanonicalDecimalQuantity has exactly two string members, encoding_spec_id and
fixed_scale_value, in canonical map order:

```json
{"$type":"map","entries":[["encoding_spec_id","example.quantity.v1"],["fixed_scale_value","1.25"]]}
```

The examples represent finite binary64 one and a scale-two decimal respectively.
No new tag, JSON number, native float/Decimal, extra/missing member or alternate
scalar representation is accepted. The selected registered field TypeExpr fixes
which exact map applies. These primitives are not unregistered root schemas.

Each numeric-role.fields[] object carries the required encoding_spec_id member
alongside field_name and representation, never at the role's top level. It is a
non-null ascii-id for canonical_decimal_quantity and null for
canonical_finite_binary64; omission rejects for both. Decimal IDs are unique
across distinct (schema_id, schema_version, field_name) declarations in the
complete source package. Repeated traversal of one declaration through multiple
model closures is not a duplicate. The body ID must equal that exact selected
field's declared ID; it cannot select an ambient or current numeric policy.

SIA's numeric lexical and value rules apply unchanged: binary64 is exactly 16
lowercase hexadecimal digits in network bit order, rejects NaN/infinity/negative
zero, and preserves every other finite bit pattern including subnormals.
Decimal uses its selected field's unit, positive scale, bounds and inclusivity.
Exponent/plus/leading-zero/negative-zero/wrong-scale spellings and rounding
reject. reject_inexact=false is committed metadata and does not override the
higher-precedence prohibition on rounding. No new generic bound-ordering rule
is introduced. Both maps obey existing canonical JSON, key uniqueness/order,
protected resource limits and byte-identical decode/re-encode requirements.

The numeric closure commits the complete raw per-field declaration including
encoding_spec_id. Changing that ID changes the affected policy, binding, entry,
registry and publication commitments. It does not change the existing map tag
or profile grammar literal. Historical profile-2 bytes remain on their original
binding/decoder route. Operational publication requires the complete regenerated
source package and independent compilation; this contract alone publishes none.

The source-role manifest is an external, non-self-referential publication
artifact, not a source role. Its final exact shape is defined in Registry
History, Decoder Sources, And Native Publication Receipts below: it includes
the ordered source-role files, decoder-source-manifest digest, ordered decoder
source snapshots, and final registry digest. Every `files` item has exactly
`role` and `sha256`; its order is unsigned UTF-8 byte order by role. It contains
the complete role set and no extra role. Schema IDs and
role path components are ASCII nonempty identifiers; schema versions and profile
versions are positive mathematical integers, emitted as canonical unsigned
decimal strings. A source role cannot be repeated. Reader startup rejects a
missing, unknown, duplicate, differently ordered, noncanonical, or
digest-mismatched source file before a registry map is made available.

The schema declaration grammar is closed. A field declaration includes a stable
field name; exact value kind; recursively declared element/key/value kinds;
tuple arity and item types; ordered-list versus set/frozenset distinction; and
the one discriminator field/value for each union member. Model inheritance is
flattened before this file is authored. Map keys are string-only. Defaults,
default factories, `Any`, object subclasses, callable validators, runtime
classes, implicit unions, and unregistered extension fields are excluded from
the declaration language. They cannot enter a profile-3 body.

The policy files are separate because a structurally equal schema with a changed
enum, optionality, numeric rule, or digest exclusion is a different binding.
Every enum member is explicitly listed; enum aliases, ordinal/numeric encoding,
and values not present in that table reject. Optionality is not inferred from a
Python default or a nullable type. A numeric field has exactly one numeric entry
when numeric and none otherwise. The digest/signature policy records no implied
exclusions: a digest field is excluded only when it is named in that file, and
entry/registry self-digests are excluded only by their separately defined
container preimages below.

### Profile-3 Grammar And Fixed Envelope

The profile grammar is the SIA 3.15.1 tagged-value algebra: strict UTF-8 JSON,
RFC 8785 output, no terminal LF, exact Unicode scalars, null/bool/string,
tagged integer/bytes/datetime/duration/enum/list/tuple/set/frozenset/map, and
schema-bound maps. The publication fixes all listed rejection behavior,
including bool-as-integer rejection, canonical base64, set duplicate/order
checks, encoded-JSON-string map-key order, exact union discrimination, and
decode/re-encode byte equality. JSON numbers, raw float, raw Decimal,
unregistered enum, unknown tag, duplicate map key, and unpaired surrogate are
outside the grammar.

Operational registered artifacts use one fixed outer envelope, encoded by this
same restricted tagged-value grammar. It is exactly the model map with these
four fields and no others:

```
binding
canonical_value_bytes
canonical_value_digest
artifact_digest
```

`binding` is exactly the six-field map:

```
profile_id
profile_version
profile_digest
schema_id
schema_version
binding_digest
```

The outer parser permits only the scalar/map/bytes/integer subset needed to
represent those fields and the six-field binding. It validates the outer model
shape and scalar spellings first, but treats `canonical_value_bytes` as opaque
at that stage. It then resolves the complete embedded binding against the
protected immutable registry history. Only the unique embedded-binding entry
with the declared read-status permission can select the original body decoder.
It verifies the two artifact digests over the exact
body bytes, then invokes that selected decoder, enforces the entry's complete
closed schema and policies, and requires byte-identical re-encoding.

The parser has no endpoint hint, caller binding, file-name dispatch, current
profile fallback, or body-first generic decode. A profile-2 or diagnostic JSON
reader remains an explicitly selected historical route; it never enters this
operational parser. The fixed envelope syntax is preserved for future bodies.
Changing the envelope itself requires a separately reviewed versioned outer
dispatch contract; a new body binding alone cannot do it.

### Canonical Length-Prefix Construction

`LP(parts...)` below is the exact byte function already used by the canonical
artifact primitive: concatenate each part as an unsigned 64-bit big-endian
length followed by that many bytes. Every textual component is strict UTF-8.
Versions are ASCII canonical unsigned decimal. SHA-256 is applied to all stated
complete preimages. The ASCII domain is the first LP member, never a prefix
outside LP. No digest value below stands for a fabricated literal; all are
computed only from the published source package and actual registry values.

The profile record has the following preimage:

```
profile_digest = SHA256(LP(
  "semantic-ingestion-typed-value-profile",
  profile_id, profile_version, grammar_revision, grammar_bytes
))
```

`grammar_digest` is `SHA256(grammar_bytes)`. The profile record rejects unless
its `profile_digest` recomputes from the exact `grammar` role and its
`grammar_digest` equals those bytes. This is the SIA profile commitment with a
fixed LP domain.

For one schema coordinate, each of the four policy digests (enum, optional,
numeric and digest-signature) is SHA-256 of:

```
LP("semantic-ingestion-typed-value-policy-closure", role_kind,
   root_schema_id, root_schema_version, closure_count,
   schema_id[0], schema_version[0], policy_role_bytes[0], ...,
   schema_id[closure_count - 1], schema_version[closure_count - 1],
   policy_role_bytes[closure_count - 1])
```

The closure and order equal the schema closure, and every model has an explicit
role even when its local policy entries are empty. No transitive policy is
inferred from another deployment registry. `schema_fingerprint` is the complete transitive
schema-closure construction specified above.
`decoder_digest` is the independently reproducible
`SHA256(LP("semantic-ingestion-typed-value-decoder", decoder_id,
typed_root_kind, implementation_source_digest))`. The implementation source
digest is the SHA-256 of a separately published, exact whole-file decoder
source snapshot selected only by the protected decoder-source manifest,
excluding generated registry/profile declaration files. It is never obtained by
runtime reflection and the implementation cannot contain the decoder digest it
is being measured against. This prevents a hashed-constant self-cycle. Profile-3 entries
have null `upcast_target` and null `upcaster_digest`. These digests do not
replace the source files: the source package is retained for independent
reproduction.

The binding preimage is:

```
binding_digest = SHA256(LP(
  "semantic-ingestion-typed-value-binding",
  profile_id, profile_version, profile_digest,
  schema_id, schema_version, schema_fingerprint,
  enum_registry_digest, optional_field_policy_digest,
  numeric_encoding_spec_registry_digest,
  digest_signature_field_policy_digest
))
```

This is deliberately independent of the decoder, upcaster, read status, entry
digest, and registry digest, so it has no entry/registry cycle and matches the
SIA binding definition.

The proposed registry-entry preimage is:

```
entry_digest = SHA256(LP(
  "semantic-ingestion-typed-value-registry-entry",
  profile_id, profile_version, profile_digest,
  schema_id, schema_version, binding_digest,
  schema_fingerprint, enum_registry_digest, optional_field_policy_digest,
  numeric_encoding_spec_registry_digest, digest_signature_field_policy_digest,
  decoder_digest,
  "0", "", "", read_status
))
```

The final three fixed members are, in order, ASCII `"0"` for no-upcast,
zero-length bytes for `upcast_target`, and zero-length bytes for
`upcaster_digest`. They are fixed for every profile-3 entry. `read_status` is
exactly one of `active`, `replay_only`, or `retired`. A retired entry must still
have a decoder sufficient for historical verification if any retained artifact
names it; an active entry is the only writer-selectable status.

Entries sort by the UTF-8 byte tuple `(profile_id, profile_version,
schema_id, schema_version)`. Duplicate coordinates reject before sorting or map
construction. The registry preimage is:

```
registry_digest = SHA256(LP(
  "semantic-ingestion-typed-value-registry",
  profile_id, profile_version, grammar_revision, grammar_digest, profile_digest,
  entry_count,
  entry_digest[0], ..., entry_digest[entry_count - 1]
))
```

`entry_count` is an ASCII canonical unsigned decimal. The `registry` role lists
the entry digests in the same required order and its profile value must equal
the recomputed profile record. The external publication manifest commits every
source-role SHA-256 and the final `registry_digest`; the registry does not refer
to that manifest, so no digest cycle exists. The deployment manifest pins this
`registry_digest` and the independently published golden-vector manifest digest
before a composition root can publish the registry.

The existing canonical artifact preimage remains exactly:

```
SHA256(LP(
  "semantic-ingestion-canonical-artifact",
  profile_id, profile_version, profile_digest,
  schema_id, schema_version, binding_digest, canonical_value_bytes
))
```

`canonical_value_digest` is SHA-256 of exactly `canonical_value_bytes`.
Schema-specific digest and signature preimages are defined only by the entry's
published digest-signature policy: their own registered ASCII domain precedes
the complete binding and canonical bytes with precisely the listed fields
excluded. No profile-wide implicit exclusion exists.

### Deterministic Construction And Publication

The protected composition root supplies one already-read source package and a
closed table mapping each declared decoder identity to a concrete typed decoder
implemented in `ingestion_contracts.py`. It performs this sequence before
publishing any usable registry:

1. Parse every source file under the raw declaration grammar above and reject
   closure violations. Protected composition configuration supplies byte, node,
   and depth limits; those limits are enforced before parsing but are not
   profile-grammar, schema, or registry-digest inputs.
2. Verify the complete role manifest and every source-byte digest.
3. Recompute profile, policy, binding, entry, and registry commitments using
   the preimages above; compare every declared value exactly.
4. Check every decoder table row against its declared identity and digest,
   every declared status permission, unique immutable coordinate, schema/policy closure, and
   the profile-3 null-only upcast rule.
5. Build immutable coordinate and binding lookup tables from the sorted entries,
   then atomically publish the one verified registry object.

Any failure leaves the previously published registry unchanged. Requests,
cursor payloads, stores, checkpoints, artifacts, and tests cannot provide a
registry, replace an entry, or widen read status. Reload receives the same
protected registry as writes. The registered reader first resolves the embedded
binding and only then decodes the body; this is required even when a caller has
an expected schema coordinate.


### Registry History, Decoder Sources, And Native Publication Receipts

The protected registry is append-only by complete entry bytes. An entry's
coordinate is `(profile_id, profile_version, schema_id, schema_version)` and
its status is part of its committed entry preimage. A registry history may not
replace an entry at that coordinate, alter its status, decoder identity, source
snapshot, schema closure, or binding digest. A later candidate that has the
same coordinate but differs in any of those values rejects; it does not select
the current entry as a fallback. The historical reader resolves the embedded
complete binding against the protected registry history, requires exactly one
byte-identical entry, and selects only that entry's original decoder.

`read_status` has exactly these permissions:

| Status | New writer selection | Public registered read | Internal replay/retention verification |
| --- | --- | --- | --- |
| `active` | Allowed after the matching activation epoch | Allowed only through the embedded complete binding | Allowed |
| `replay_only` | Forbidden | Forbidden | Allowed only through the embedded complete binding |
| `retired` | Forbidden | Forbidden | Allowed only to verify retained bytes that name the exact entry |

Every retained artifact keeps its original decoder for the status committed in
its exact entry. Profile 3 has no status-transition grammar: an attempted
same-coordinate `active`/`replay_only`/`retired` replacement rejects. The
protected history is the append-only, ordered set of complete registry entries
and the verified publication manifest that contains them; it is not an ambient
or separately pinned lookup. None of these statuses permits body upcast,
default insertion, current-profile selection, caller-supplied decoder, or
mutation of historical bytes. A writer can select only `active`; an observation
API can decode a historical body only where its declared route permits it, and
never widens `replay_only`/`retired`. A future retirement lifecycle requires a
separately versioned registry contract.

The decoder source manifest is a second external publication artifact at the
fixed source-package location `decoder-source-manifest.json`. Its exact JSON
object is `{role:"decoder_source_manifest",profile_id,profile_version,files}`.
The document follows the strict RFC-8785 UTF-8, duplicate-name rejection and
no-terminal-LF rules of the raw source grammar. `role` is the literal shown,
`profile_id` is exactly `semantic_ingestion_typed_value`, `profile_version` is
the canonical decimal string `"3"`, `files` is an array of the closed objects
below, and every item field is a string. Each `sha256` is exactly 64 lowercase
hexadecimal characters. Define
`decoder_source_manifest_digest = SHA256(exact_manifest_raw_bytes)`.
Both publication construction and deployment verification must recompute this
digest from those canonical raw bytes before using it in the publication LP
preimage; a matching selected-file snapshot cannot substitute for that check.
`files` is a nonempty array ordered by `(decoder_id, source_file_id)` UTF-8
bytes; every item has exactly `decoder_id`, `source_file_id`, `relative_path`,
and `sha256`. `relative_path` is a nonempty ASCII path of slash-separated
segments matching `[A-Za-z0-9._-]+`, with no empty, `.` or `..` segment,
backslash, percent escape, Unicode escape, absolute root, or trailing slash.
The compiler resolves it beneath the configured canonical source-package root,
opens it with symlink traversal disabled, and rejects any resolved path outside
that root. `source_file_id` and `decoder_id` are nonempty ASCII IDs. Duplicate
`(decoder_id, source_file_id)` or `(decoder_id, relative_path)` pairs reject.
Different decoders may name the same shared source file; repeated relative paths
must have identical bytes and SHA-256 values. Conflicting source IDs for a shared
path or a digest that does not match the actual bytes reject.
Raw files are strict UTF-8 and their unmodified bytes, including or
excluding a terminal LF exactly as present, are the LP input. A decoder role names one `decoder_id`; its
implementation-source digest is the SHA-256 of the deterministic source
snapshot for all rows bearing that ID:

```
decoder_source_snapshot = SHA256(LP(
  "semantic-ingestion-profile3-decoder-source-snapshot",
  decoder_id, file_count_ascii_unsigned_decimal,
  source_file_id[0], relative_path[0], raw_utf8_file_bytes[0],
  ...
))
```

Rows name whole files only. Region selectors, import traversal, reflection,
runtime module names, callbacks, and generated constants are not source
selection. The finite rows for each decoder include the complete native
validator and canonical-encoder file closure used by that decoder. Generated
profile/registry constants must reside in separately named files and are not
eligible manifest rows, preventing a generated digest from selecting or
self-hashing its own decoder source. The compiler reads every named file as
strict UTF-8, verifies its SHA-256, then computes the LP snapshot; it does not
load the decoder before this verification.

The external `publication_manifest` has exactly `role:"publication_manifest"`,
`profile_id`, `profile_version`, ordered source-role `files`,
`decoder_source_manifest_digest`, ordered `decoder_source_snapshots`, and
`registry_digest`. Every `files` item is exactly `{role,sha256}`; every
`decoder_source_snapshots` item is exactly
`{decoder_id,source_snapshot_digest}` and items sort by decoder ID UTF-8 bytes.
Its digest is `SHA256(LP("semantic-ingestion-profile3-publication-manifest",
profile_id, profile_version, source_role_count, role[0], source_sha256[0], ...,
decoder_source_manifest_digest, decoder_count, decoder_id[0],
source_snapshot_digest[0], ..., registry_digest))`. It is external to
the registry preimage: registry digest still commits only the profile and
ordered entry digests, so no manifest/registry cycle exists. Protected
deployment configuration pins publication-manifest digest, registry digest,
all declared decoder-source snapshot digests, and the independent-vector
manifest digest; composition verifies all pins before exposing a registry.

For an activated accepted V3 group, define
`publication_identity_digest = SHA256(LP(
"memorii.bootstrap-graph.native-projection-publication-identity.v3",
source_operation_id, transaction_group_id, request_ctv_digest,
canonical_graph_delta.delta_digest,
canonical_event_batch.source_event_batch_digest))`. The same group CAS writes
these three create-only native members, using only the typed embedded values
named here:

| Model and deterministic record ID | Exact fields and preimage |
| --- | --- |
| `BootstrapGraphNativeProjectionPublicationReceiptV3`, `semantic_ingestion:bootstrap-graph-v3:native-projection-publication:<publication_identity_digest>:receipt` | `schema_version=1`, `source_operation_id`, `transaction_group_id`, `request_ctv_digest`, `graph_revision_before`, `graph_revision_after`, `canonical_graph_delta: SemanticGraphDelta`, `canonical_event_batch: SemanticMemoryEventBatch`, `temporal_publication: TemporalProjectionPublication`, `trust_publication: TrustProjectionPublication`, exact ordered pair `projection_history_replay_bindings: tuple[ProjectionHistoryReplayBinding, ProjectionHistoryReplayBinding]`, `replay_authority_evidence_id`, `replay_authority_evidence_digest`, `replay_checkpoint_evidence_id`, `replay_checkpoint_evidence_digest`, `publication_identity_digest`, and `receipt_digest`. `receipt_digest` is the profile-3 self digest under `memorii.bootstrap-graph.native-projection-publication-receipt.v3` over every preceding field except itself. |
| `BootstrapGraphNativeReplayAuthorityEvidenceV3`, `semantic_ingestion:bootstrap-graph-v3:native-projection-publication:<publication_identity_digest>:aggregate` | `schema_version=1`, `source_operation_id`, `transaction_group_id`, `request_ctv_digest`, `publication_identity_digest`, `receipt_id`, `aggregate: SemanticReplayAuthorityAggregate`, and `evidence_digest`. `evidence_digest` is the profile-3 self digest under `memorii.bootstrap-graph.native-projection-authority-evidence.v3` over every preceding field except itself. |
| `BootstrapGraphNativeReplayCheckpointEvidenceV3`, `semantic_ingestion:bootstrap-graph-v3:native-projection-publication:<publication_identity_digest>:checkpoint` | `schema_version=1`, `source_operation_id`, `transaction_group_id`, `request_ctv_digest`, `publication_identity_digest`, `receipt_id`, `checkpoint_bundle: SemanticReplayCheckpointBundle`, and `evidence_digest`. `evidence_digest` is the profile-3 self digest under `memorii.bootstrap-graph.native-projection-checkpoint-evidence.v3` over every preceding field except itself. |

`publication_identity_digest` excludes all three self/evidence digests, so the
IDs are available before receipt construction and no digest cycle exists. The
receipt stores the full canonical group delta because the current V3 group path
does not retain one immutable group-delta member; per-operation effect records
and the event batch do not substitute for it. The aggregate evidence must have
`aggregate.graph_state.graph_revision == graph_revision_after`, its projection
bindings exactly equal the receipt pair, and its latest checkpoint exactly equal
the checkpoint evidence bundle. The checkpoint evidence must bind the same
post-batch replay state, projection bindings, writer epoch, and event-batch
watermark as the aggregate. Receipt publications must equal the corresponding
immutable projection-history certificate, generation and history-entry records
written in that CAS. Each publication's embedded active pointer is the immutable
snapshot of the pointer written by that publication; validate its links to those
historical records using the native owner. Do not require a later current-pointer
record to equal this historical snapshot. These equalities use the existing typed owners, never an
ad hoc dictionary or synthetic generic member binding.

For each receipt publication, reload reconstructs the native history prefix
from all immutable entries of that kind through the embedded history entry's
`publication_sequence`, validating sequence continuity, predecessor links and
the native certificate/generation/pointer relation. Use the canonical native
prefix-digest construction on that bounded prefix. Derive the corresponding
`ProjectionHistoryReplayBinding` and require the receipt's pair, in exact
`(temporal, trust)` order, to equal the derived repository, prefix digest,
pointer digest and generation digest coordinates, including each binding's own
digest. Do not compare this historical pair with the current head's bindings.
Missing, reordered, substituted or cross-repository prefix members reject.

`BootstrapGraphGroupCommitResultCoreV3` gains
`native_projection_publication_receipt: BootstrapGraphNativeProjectionPublicationReceiptV3 | None`, and
`BootstrapGraphGroupCommitReloadV3` carries the same named field. Both use
`group_result_schema_version: Literal[1,2]`: an absent version field decodes as
version 1, which omits both the version field and the receipt field from
serialization and digest preimages and requires the receipt absent. Version 2
includes both fields, requires the receipt non-null for an activated accepted group, and requires it null
for a noncommitting group. Exact reload validates receipt/member IDs, encoded
bytes, evidence digests, canonical delta/event batch, publications, bindings,
and the immutable targets before returning. Thus a lost acknowledgement for A
after B advances mutable aggregate/checkpoint pointers validates A's immutable
evidence and never requires A's former current-pointer record. Legacy bytes
remain readable only by version-1 dispatch and cannot synthesize a receipt.
The reload's direct receipt and version fields must equal those in
`persisted_result.core`; independently valid but different copies reject.

## Schema Publication

Source label: `schema-publication.md`.

### Publication Rule

Every row below is one `semantic_ingestion_typed_value` profile-3 registry entry
with `schema_version=1`. The schema ID is the value in the table, without its
`.v1` suffix. A row is emitted only after its complete recursive TypeExpr
closure, enum table, optional policy, numeric policy, digest/signature policy,
and decoder source identity have been authored under the grammar in
`operational-profile.md`. An entry contains its own root schema plus the
transitive schemas referenced from that root; a nested root is not copied into a
second hand-maintained declaration.

Each durable or public body has `read_status=active` once its owning capability
is enabled. Profile-2 diagnostic/history readers remain separately registered
historical routes and receive no profile-3 upcast. A schema may be loaded for
replay only after its original profile/binding/entry verifies; no profile-3
schema relabels a legacy local-observation chain as global audit.

All `*_digest` fields below use the profile declaration's `sha256` string
lexical rule. `schema_version`, sequence, stream position, page size and record
version use the exact integer TypeExpr with the stated nonnegative/positive
bound; they are never booleans. Every tuple remains a tuple in the schema
declaration, not a set inferred from a Python collection. Nullable values use
the registered optional policy, so omitted and null stay distinct.

### Durable Ledger And Terminal Roots

| Schema ID | Source field authority | Digest/signature policy | Transitive closure owner |
| --- | --- | --- | --- |
| `ObservationLedgerHead.v1` | `closed-contracts.md`, Store Record Schemas: repository, activation, sequence, revision, predecessor coordinates and head digest. | `head_digest` excludes only itself; no signature. | Observation persistence owns the root; strings and integer rules are profile-owned. |
| `ObservationLedgerEntry.v1` | `closed-contracts.md`: exact predecessor, semantic payload, result locator/result digest and entry digest. | `entry_digest` excludes only itself; no signature. | Observation persistence owns the root; `CanonicalIngestionObservationDelta` and `ObservationResultLocator` are dependencies. |
| `ObservationGroupSemanticPayload.v1`, `ObservationSourceSemanticPayload.v1` | `closed-contracts.md`: separate model roots with `terminal_group`/`source_finalization` literals and delta fields minus `observation_revision_before`, `observation_revision_after`, and `delta_digest`. | The external semantic payload digest binds the selected complete binding and body; no self field exists. | Observation contracts own the two models; ObservationLedgerSemanticPayload is only their union alias. |
| `IngestionObservationDelta.v1` | SIA Section 3.15.1 observation contract (`IngestionObservationDelta`): group delta fields, exact operation membership, graph delta link and record mutations. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own `IngestionObservationRecordMutation`, canonical record union, governance and graph-delta link types. |
| `SourceFinalizationObservationDelta.v1` | SIA Section 3.15.1 observation contract (`SourceFinalizationObservationDelta`): source/delivery/governance carriers, operation IDs and full source outcome. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own the source-terminal record plus carrier sets. |
| `IngestionObservationRecordMutation.v1` | SIA Section 3.15.1 observation contract (`IngestionObservationRecordMutation`): create-only kind, record kind/ID/version/body/digest. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own the discriminated canonical record union. |
| `CanonicalSourceIntroductionRecord.v1` | SIA Section 3.15.1 observation contract, class of the same name. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own governance, admission, source span and canonical identity dependencies. |
| `CanonicalOperationIntroductionRecord.v1` | SIA Section 3.15.1 observation contract, class of the same name. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own ordered governance/admission/source-span dependencies. |
| `CanonicalOperationTerminalOutcomeRecord.v1` | SIA Section 3.15.1 observation contract, class of the same name. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own terminal status, temporal-decision and lineage dependencies. |
| `CanonicalSourceTerminalOutcomeRecord.v1` | SIA Section 3.15.1 observation contract, class of the same name. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own complete carrier sets, required scopes, operation/group result membership. |
| `GraphRevisionDelta.v1` | SIA22842-22855. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own record changes, reference-edge entries, governance/admission and graph records. |
| `BootstrapGraphNativeProjectionPublicationReceiptV3.v1` | Activated accepted native-group projection publication receipt. | `receipt_digest` excludes only itself and binds group/request/revision/delta/batch coordinates, both full publications, ordered replay bindings, and both immutable evidence targets. | Native group contracts own the root; projection-history and event-replay owners validate embedded native values. |
| `BootstrapGraphNativeReplayAuthorityEvidenceV3.v1` | Immutable historical aggregate evidence for one group receipt. | `evidence_digest` excludes only itself and commits the complete resulting `SemanticReplayAuthorityAggregate`. | Event-replay aggregate owner supplies/validates the embedded value; native group contracts own immutable member identity. |
| `BootstrapGraphNativeReplayCheckpointEvidenceV3.v1` | Immutable historical checkpoint evidence for one group receipt. | `evidence_digest` excludes only itself and commits the complete resulting `SemanticReplayCheckpointBundle`. | Event-replay checkpoint owner supplies/validates the embedded value; native group contracts own immutable member identity. |
| `SourceObservationIntent.v1` | `closed-contracts.md`, Terminal Intent And Receipt Grammar. | `intent_digest` excludes only itself. | Native terminal contracts own the root; canonical source outcome and active schema fingerprint are dependencies. |
| `ObservationLedgerActivation.v1` | `closed-contracts.md`, Activation And Writer Fencing. | `activation_digest` excludes only itself. | Writer admission owns drain inventory, target epoch and writer/schema/codec fingerprints. |

#### Native Value Compatibility

Native graph/effect values are exact owner-validated embedded values. Profile 3
commits all their bytes, including their native digest fields, as ordinary fields.
It never computes those native digests using a profile-3 binding. The finite
static decoder table invokes the exact existing canonical model owner, including
its complete native digest validation. The pinned decoder implementation source
closure includes these native validators and their canonical encoder; registry
data cannot select a callback or supply a digest algorithm. The table is finite
and checked against the publication inventory, not the fixture-56 compiler.

This rule also covers transitive existing graph records and carrier values.
New ledger head/entry/state/intent/activation and public observation outputs use
their declared profile-3 policies. Creating a post-activation ledger entry around
a newly committed native delta is supported; wrapping historical terminal1/2
results to fabricate global audit is forbidden. Verification must discriminate
valid native nesting, changed body with retained digest, substituted profile-3
hash, unknown owner/version and forbidden historical wrapping.

#### Exact Durable Dependencies

The following are roots already named by SIA and must be published as separate
entries when they occur as an artifact body: `ReferenceEdgeLedgerEntry.v1`,
`GraphRecordMutation.v1`, `SegmentGovernanceBinding.v1`,
`MessageAdmissionIdentity.v1`, `GovernanceCarrierArtifact.v1`,
`SegmentGovernanceCarrierSet.v1`, `MessageAdmissionCarrierSet.v1`,
`RequiredOutcomeScopeSet.v1`, `SourceSpanReference.v1`, and
`OperationTemporalDecisionBinding.v1`. Their field authority remains the
existing SIA definitions; the observation registry does not duplicate them or
loosen their fields. If a dependency is only nested, its declaration remains in
the consuming root's transitive schema closure and does not create an independent
write endpoint.

### Replay, Checkpoint And Activation-Read Roots

| Schema ID | Source field authority | Digest/signature policy | Transitive closure owner |
| --- | --- | --- | --- |
| `ObservationReplayState.v1` | `replay-snapshot-contract.md`, Replay State Grammar. | `state_digest` excludes only itself. | Observation replay owns head, ordered entries and ordered canonical audit records. |
| `IngestionObservationReplayCheckpoint.v1` | SIA23010-23022 and the replay-snapshot signing supplement. | `checkpoint_digest` commits the registered checkpoint signing preimage, excluding the checkpoint digest and signature; including the signature here would create a cycle. | Observation replay owns the checkpoint body and typed head/replay links. |
| `ObservationCheckpointLifecycle.v1` | `replay-snapshot-contract.md`, Checkpoint And Signature Dependency Order. | `authority_digest` excludes only itself. | Observation replay authority owns lifecycle history/current authority. |
| `ObservationCheckpointSigningPreimage.v1` | `replay-snapshot-contract.md`: exact purpose `observation_checkpoint`, repository/activation/sequence/head/lifecycle and checkpoint fields excluding checkpoint digest/signature. | It is the signed preimage; it has no self digest or signature field. | Observation replay authority owns purpose and lifecycle; replay owns the state/checkpoint closure. |
| `ObservationCheckpointPublicationReceipt.v1` | `replay-snapshot-contract.md`: exact repository/activation/checkpoint/lifecycle/state/head receipt fields. | `receipt_digest` excludes only itself. | Observation replay authority owns publication receipt. |
| `ObservationCheckpointBundle.v1` | `replay-snapshot-contract.md`: schema version, repository, activation, sequence, head, replay state, checkpoint, lifecycle, receipt and bundle digest. | `bundle_digest` excludes only itself; it includes the signed checkpoint and receipt. | Observation replay owns the root and all checkpoint dependencies. |

No checkpoint schema receives a generic signature exclusion. The checkpoint
policy explicitly selects ObservationCheckpointSigningPreimage as its preimage
owner, including the external lifecycle and head coordinates required by the
replay-snapshot supplement. The preimage has no self-digest or signature field.
Bundle and receipt policies include their referenced checkpoint digest and
signature wherever declared; they cannot inherit the checkpoint exclusion.

### Public Observation And Retrieval Roots

SIA31314-31815 is the field authority for every public request, cursor, page,
failure and observed payload below. The schema IDs deliberately match the
normative class names, which gives registry generation a stable, finite list.

| Family | Root schema IDs |
| --- | --- |
| Authorization and request | `AuthenticatedGraphObservationContext.v1`, `GraphObservationAuthorizationDecision.v1`, `GraphObservationPagePolicySnapshot.v1`, `GraphObservationCohortSelector.v1`, `ResolvedGraphObservationCohort.v1`, `GraphObservationRequest.v1`, `IngestionTimeAttestationRequest.v1`, `GraphObservationFailure.v1` |
| Cursor, cohort and retained snapshot | `GraphObservationCursorPayload.v1`, `GraphObservationCohortPreimage.v1`, `GraphRecordObservationSnapshot.v1`, `IngestionTimeObservationSnapshot.v1`, `GraphObservationRequestCoordinates.v1`, `IngestionTimeAttestationRequestCoordinates.v1`, `GraphObservationRecordKey.v1` |
| Stream and responses | `GraphObservationPage.v1`, `IngestionTimeAttestationPage.v1`, `SourceRetentionTimeAttestation.v1`, `TransactionGroupCommitTimeAttestation.v1`; `GraphObservationStreamRecord` is the closed stream-variant type alias below, never a registry root. |
| Structural payloads | `ObservedEntityReference.v1`, `ObservedAssertionEntityReference.v1`, `ObservedEntityRevision.v1`, `ObservedAliasRevision.v1`, `ObservedTypeEvidence.v1`, `ObservedClaimAssertion.v1`, `ObservedTemporalClaimProjection.v1`, `ObservedTrustClaimProjection.v1`, `ObservedRelation.v1`, `ObservedActionRoleBinding.v1`, `ObservedActionRevision.v1`, `ObservedCitationRecord.v1`, `ObservedProvenanceRecord.v1`, `ObservedTemporalTransition.v1`, `ObservedCertifiedTextEffectiveTime.v1`, `ObservedAuthenticatedReferenceEffectiveTime.v1`, `ObservedSystemRecordedEffectiveTime.v1`, `ObservedIdentityTransition.v1`, `ObservedReferenceDisposition.v1` |
| Ingestion payloads and assessment | `ObservedSourceIntroduction.v1`, `ObservedOperationIntroduction.v1`, `ObservedOperationTerminalOutcome.v1`, `ObservedSourceTerminalOutcome.v1`, `ObservedSourceOutcomeConsistencyAssessment.v1` |

Production time observation publishes only `SourceRetentionTimeAttestation.v1`
and `TransactionGroupCommitTimeAttestation.v1`. `SourceRetentionTimeWitness` and
`TransactionGroupCommitTimeWitness` are acceptance-only values owned by the
acceptance harness under SIA's time-witness boundary. Neither witness is a
production registry root, transitive schema dependency, static decoder target,
source model, stored observation or public response. The acceptance harness
reads and verifies production attestations through the authorized public
boundary, then constructs and verifies witnesses under its separate acceptance
authority. This publication contract does not define or relax that authority,
and production never accepts expected witness IDs or fixture coordinates.

`GraphObservationCohortPreimage.v1` has exactly the replay-snapshot supplement
fields: all resolved-cohort fields except `cohort_digest`, snapshot graph and
observation revisions, full memory-plane write revision, exact temporal and
trust generation digests, exact temporal and trust pointer digests, observation
schema fingerprint, and disjoint sorted unique
`changed_record_keys`/`boundary_record_keys`. Its `cohort_digest` policy is
external to the preimage model, which has no self-digest field. The public
ResolvedGraphObservationCohort now includes every one of these coordinates,
as declared in replay-snapshot-contract.md, and uses its own registered
self_digest binding over all fields except cohort_digest. The stream
retains each selected generation and complete pointer in its corresponding
projection record; the cohort commits their digest coordinates without
constructing a combined projection state.
The two snapshot model roots have exactly the server-owned
fields in that supplement: schema version, snapshot token, protected creation
time, `memory_plane_write_revision` as a nonnegative integer, authenticated context digest, purpose,
authorization decision, cursor-free request, cohort preimage/resolved cohort,
and one immutable discriminated stream. Its `purpose` is exactly
`graph_observation` or `ingestion_time_attestation`, matching the authorizer
purpose literal in SIA31391; the former permits only
`GraphObservationStreamRecord` items and the latter only
`ProductionIngestionTimeAttestation` items. Their exact request-coordinate and
stream types are declared in replay-snapshot-contract.md; the GraphObservationSnapshot
union alias is not a registry root. This is retained server state, not a
caller-supplied body. Its snapshot token is not a digest or authorization
substitute.

All public `record_digest`, `page_digest`, `assessment_digest`, `decision_digest`
and `policy_digest` fields exclude only their own named field. `GraphObservation-
CursorPayload.v1` is signed under the cursor purpose; its signature preimage is
the complete cursor payload excluding only `signature`. The request and page
schemas have no implicit defaults, and the page's stream-record payload union is
exactly discriminated by `GraphObservationRecordKind` with matching outer kind,
primary key and record digest as required by SIA31912-31917.

The user-approved profile-3 observation route replaces the legacy
`claim_projection` stream kind with `temporal_claim_projection` and
`trust_claim_projection`. `ObservedTemporalClaimProjection.v1` has exactly
`observation_id`, complete owner-validated `TemporalProjectionRecord`, its
native `generation_digest`, complete owner-validated
`ActiveTemporalProjectionPointer`, same-kind
`successor_publication_pointer` or null, `boundary`, and `record_digest`.
`ObservedTrustClaimProjection.v1` has the corresponding complete
`TrustProjectionRecord`, `generation_digest`,
`ActiveTrustProjectionPointer`, same-kind successor pointer or null, boundary,
and record digest. In both cases `observation_id` is the profile-bound content
address of projection kind, repository, native generation digest, and native
projection digest; it is the stream primary key. The native `projection_id`,
publication time/sequence, policy fingerprint, transition reason encoded by
the pointer's `publication_kind`, and all native digests stay in their native
values. The adapter neither combines selections nor creates a transition reason.
Profile-2 and the existing `ObservedClaimProjection` bytes keep their historical
read routes and are never relabelled as either profile-3 model.

The approved decision is the profile-3 public-field authority for this
replacement. `semantic_state.py` owns the native projection, generation, and
pointer shapes (`TemporalProjectionRecord`, `TrustProjectionRecord`, their
generation models, and their active/history pointers);
`projection_history.py` owns the canonical selection and pointer-history rules.
No profile declaration duplicates or weakens those native validators.

`GraphObservationStreamRecord` is the following type alias, not a model root:

```text
GraphObservationStreamRecord =
  EntityRevisionStreamRecord | AliasRevisionStreamRecord |
  TypeEvidenceStreamRecord | ClaimAssertionStreamRecord |
  TemporalClaimProjectionStreamRecord | TrustClaimProjectionStreamRecord |
  RelationStreamRecord | ActionRevisionStreamRecord | CitationStreamRecord |
  ProvenanceStreamRecord | TemporalTransitionStreamRecord |
  IdentityTransitionStreamRecord | ReferenceDispositionStreamRecord |
  SourceIntroductionStreamRecord | OperationIntroductionStreamRecord |
  OperationTerminalOutcomeStreamRecord | SourceTerminalOutcomeStreamRecord
```

Every listed variant is an explicit profile-3 model in the enclosing page and
snapshot closure with exactly `record_kind`, `primary_key`, `record_digest`, and
`payload`. Its `record_kind` is respectively the literal
`entity_revision`, `alias_revision`, `type_evidence`, `claim_assertion`,
`temporal_claim_projection`, `trust_claim_projection`, `relation`,
`action_revision`, `citation`, `provenance`, `temporal_transition`,
`identity_transition`, `reference_disposition`, `source_introduction`,
`operation_introduction`, `operation_terminal_outcome`, or
`source_terminal_outcome`; its payload is respectively the like-named
`Observed...` model in the same order. The projection variants use only the two
new projection models above. A union alternative is selected by its literal
`record_kind`, and validates that `primary_key` equals the payload canonical
primary key and `record_digest` equals the payload record digest. There is no
generic `payload` union, implicit kind/payload pairing, or independent stream
record root.

`GraphObservationRecordKind` in every profile-3 request, cursor, cohort,
snapshot, page, and stream declaration is exactly the seventeen literals above.
In particular, cursor `preceding_record_kind` uses that closed enum and cannot
carry `claim_projection`; an existing legacy cursor remains readable only by its
historical profile route.

### Source-to-Decoder Construction

The profile compiler takes a checked-in source package with one role per root
above: `schema/`, `enum/`, `optional/`, `numeric/`, `digest-signature/`,
`decoder/`, and null-only `upcast/`, plus the one profile grammar/registry role
defined in `operational-profile.md`. It rejects an inventory item missing any
role, a role not named here, duplicate coordinate, unresolved model/enum
reference, cycle, or a non-null profile-3 upcast.

For each root, `decoder/<schema>/<version>` names a stable decoder ID of the
form `memorii.semantic_ingestion.observation.<schema>.v1` and commits an
implementation-source digest. That digest is calculated by the publication
builder from the complete named files selected by the checked-in
decoder-source-manifest; generated profile/registry declaration constants live
in separate excluded files, so it cannot self-hash. At runtime `ingestion_contracts.py` contains the closed static
decoder-ID-to-decoder table and compares the source-published identity/digest
before publication. It does not import a module from registry data, inspect
annotations, or reflect a model. Nested decoder calls occur only after the root
binding is resolved and each nested TypeExpr reference is already in the verified
closure.

The deployment publication is deterministic:

1. Sort roots by `(schema_id, schema_version)` and emit every raw declaration
   source byte file under the profile's no-LF/RFC-8785 source rules.
2. Recompute closure fingerprints, policy digests, bindings and entry digests;
   sort entries by the same coordinate; then compute the profile-3 registry
   digest using the exact LP preimage in `operational-profile.md`.
3. Emit the exact external publication manifest: ordered source-role files,
   decoder-source-manifest digest, ordered whole-file decoder source snapshots,
   and registry digest. The registry role already commits ordered entry digests;
   they are not repeated as undeclared manifest fields.
4. Protected deployment configuration supplies publication-manifest digest,
   registry digest, every declared decoder-source snapshot digest, and
   independent-vector-manifest digest as lowercase SHA-256 strings. These pins
   are deployment inputs, outside the source-role manifest.
   The vector manifest commits vector inputs, complete expected output bytes,
   independent implementation source identity and allowed shared inputs. A
   process verifies publication and registry pins before exposing the registry;
   release/package verification separately proves the vector manifest and
   independent parity. Requests cannot override any pin.

The real construction root is `ProviderMemoryService` in
`memorii/core/provider/service.py`: ordinary initialization invokes
`BuiltInLocalHostSemanticIngestionCapability.build_semantic_ingestion_runtime`
when verified host material and the bootstrap profile are present. That method
in `memorii/core/semantic_ingestion/capability.py` constructs the paired
`SemanticWriterAdmissionStore` and `SemanticIngestionAtomicStore`. Ledger mode
must add one required verified-registry parameter to this existing construction
path, verify the pinned registry once, and pass the same immutable object to
writer admission, atomic store, observation replay, and the public observation
service. An absent/mismatched registry leaves ledger mode unavailable; it must
not select a profile from a request or fall back to profile 2. The future
`ProviderMemoryService.observe_graph` and
`observe_ingestion_time_attestations` entrypoints receive the same configured
registry and protected authorizer/page/cursor configuration before taking the
memory-plane snapshot.

### Locator And Cursor Closure

The closed-contracts supplement declares ObservationGroupResultLocator and
ObservationSourceResultLocator as the two alternatives of ObservationResultLocator,
including exact native record identity recomputation and result-digest selection.
Both alternatives have their own schema roles in the entry's transitive closure.

The profile-3 cursor signing purpose is `graph_observation_cursor` and its domain
is `memorii.graph-observation.cursor.v3`. The signing preimage is the complete
registered cursor payload minus only signature; it includes the full binding
and purpose under the profile signing rules. This new registered route does not
reuse the foundation's unregistered `v1` wire signature domain. Existing v1
codec tests remain foundation evidence only. Profile-3 issuance and verification
must agree on the new route; an active profile-3 endpoint rejects a v1 cursor.
Snapshot purpose remains graph_observation or ingestion_time_attestation.

Raw declaration sources, decoder snapshots and full independent vectors remain
unpublished. This inventory closes names and field ownership; it does not claim
that complete source bytes or runnable registry generation already exist.

## Replay Snapshot Contract

Source label: `replay-snapshot-contract.md`.

### Snapshot Ownership And Activation Preconditions

The new `MemoryPlaneService.read_write_snapshot()` returns one detached
`(write_revision, records)` under the backend lock. The observer authorizes before
calling this method. Existing `read_snapshot()` remains unchanged: its data
revision does not advance for internal-control-only writes and is not a full
inventory fence.
All graph, source/result, observation-head/entry, reference-ledger, schema and
activation lookups for that observation resolve exclusively from these records.
Missing records do not fall back to live individual reads. The snapshot owner
checks duplicate canonical identities before constructing typed indexes.

The memory-plane write revision is a consistency token, not the graph or observation
revision. Those domain revisions are decoded from their respective heads in
the same snapshot. Activation and checkpoint publication require a separate
optional `expected_write_revision` on the service conditional batch and backend
`apply_batch`. Compare it under the same lock before publication. It is an exact
nonnegative integer, never a boolean. Preserve existing `expected_revision`
data-revision behavior for current unit-of-work callers. If both are supplied,
both must match. The JSONL backend already persists a full batch `revision`
separately from `data_revision`; use that existing full revision, without
rewriting old logs. The in-memory backend adds a separate write counter.
Every successful root canonical-record batch, including an empty batch consistently
with JSONL behavior, advances the full write revision; failed validation or CAS
advances neither counter. Stage/upsert/write/conditional routes share this rule.
Protected secret files do not mutate the canonical-record inventory and do not
participate in this token. A unit-of-work empty commit remains its existing
staged-view no-op and creates no root batch; nonempty UOW commit advances the
underlying full revision. Full-write snapshot/guard calls inside a UOW reject
rather than pairing a committed token with speculative records.

Activation scans the complete drained inventory from one snapshot and submits
that exact revision as well as the admission/head/immutable-record conditions.
This replaces the draft's unspecified "inventory partition revision": no such
separate partition token exists. Unrelated writes can conservatively cause a
retry; a retry must rescan rather than keep a stale inventory. A protected
finite retry limit bounds this work. Group/source append uses the narrower
head and source authority preconditions and does not require whole-store CAS.

### Replay State Grammar

`ObservationReplayState` is an immutable profile-3 schema with exactly:

- `schema_version`: integer literal 1;
- `repository_id`: nonempty string;
- `activation_digest`: lowercase SHA-256;
- `head`: the complete `ObservationLedgerHead`;
- `entries`: tuple of complete `ObservationLedgerEntry`, in sequence order;
- `records`: tuple of `CanonicalIngestionObservationRecord`, ordered by
  `(ingestion_record_kind, canonical record identity)` with no duplicates;
- `state_digest`: its registered digest, excluding only itself.

This first checkpoint format retains the full audit prefix. It is deliberately
not a pruning or compact-Merkle-proof protocol. Entries retain typed result
locators and graph-delta links through their canonical delta variants. The
checkpoint accelerates loading a verified materialization, not deletion of
source evidence. Resource exhaustion rejects rather than truncating a prefix.
Supporting a compact prefix later requires an explicit versioned design.

Genesis replay verifies activation, the complete entry chain, exact registered
delta variants, immutable result links and committed graph-delta/base-record
links. It applies every create mutation once and adds each source outcome once.
Repeated record identity, even with identical bytes, is rejected where the
canonical create contract forbids another introduction. Source-only empty
operation outcomes remain valid. Group operations require their complete
introduction/outcome bijection. Reconstructed records must equal the state's
exact ordered records; neither missing nor extra records are accepted.

The expected persisted head is read independently from the same snapshot. A
valid prefix is not a valid full replay unless its complete head equals that
expected head. There is no reliance on iterator exhaustion as completeness.

### Checkpoint And Signature Dependency Order

`ObservationCheckpointBundle` has exactly `schema_version=1`, `repository_id`,
`activation_digest`, `sequence`, `head`, `state: ObservationReplayState`,
`checkpoint: IngestionObservationReplayCheckpoint`, `lifecycle`,
`publication_receipt`, and `bundle_digest`. All duplicated repository/activation/sequence/head coordinates
must be equal. Sequence is positive: an empty genesis needs no checkpoint.

`ObservationCheckpointSigningPreimage` has exactly the registered purpose
literal `observation_checkpoint`, repository, activation, sequence, head,
the complete lifecycle snapshot including its authority digest, and all canonical checkpoint fields except checkpoint digest
and signature. Its materialized ledger digest equals `state.state_digest`.
Its last delta ID/digest and observation revision equal the head. Creation time
is protected-clock UTC and validated against the signing authority's interval.

Compute in this acyclic order: verified replay state and state digest; unsigned
checkpoint fields; complete registered signing preimage and checkpoint digest;
Ed25519 signature over the registered purpose/binding/preimage/digest; final
checkpoint; then publication receipt; then bundle digest. The signed preimage never includes bundle digest,
signature or its own checkpoint digest. Bundle digest includes the signed
checkpoint. A mutable signing callback does not choose different authority
coordinates after the preimage is frozen.

`ObservationCheckpointLifecycle` contains exactly repository_id,
authority_revision, registry_revision, registry_digest, registry_history_digest,
trust_policy_revision, trust_policy_digest, minimum_checkpoint_sequence,
predecessor_authority_digest (required nullable), and authority_digest. Revisions
and minimum sequence are positive exact integers. Genesis authority has revision
1 and null predecessor; successors increment authority revision by one, name the
exact predecessor digest, and never reduce registry/trust revisions or rollback
floor. Equal registry/trust revisions require equal corresponding digests.
Its registered digest excludes only authority_digest. The protected durable
authority owner retains the immutable predecessor chain and current head.

`ObservationCheckpointPublicationReceipt` contains exactly repository_id,
activation_digest, checkpoint_id, checkpoint_digest, lifecycle_authority_digest,
state_digest, head_digest, and receipt_digest. Its registered digest excludes
only receipt_digest. It is derived after signing, has no bundle digest or
mutable current-head dependency, and is retained both in the bundle and as an
immutable record in the same CAS. Reload requires byte equality. The lifecycle
snapshot in the bundle must equal the snapshot used by the signing preimage and
be reachable through the retained authority chain. Publication uses the current
authority without incrementing its revision merely to record a checkpoint.

Observation replay reconstructs observation records and revisions only, as
required by SIA23235-23240. It verifies linked graph deltas/results against
independently loaded canonical graph authority; it does not replace graph event
replay or claim to materialize graph state. The observation service composes
this verified ledger with the graph/reference snapshot from the same detached
memory-plane read. Graph replay retains its own checkpoint and authority owner.

Checkpoint creation reads the protected lifecycle and one consistent committed
snapshot, verifies the full replay, signs that exact preimage, then atomically
publishes bundle and lifecycle receipt under exact snapshot revision and current
lifecycle/admission preconditions. Failed CAS publishes neither; retry reacquires
all authority and re-signs only the newly frozen preimage. Signing alone is not
publication. The signer implementation and public-key verifier are configured;
actual release-key issuance remains deferred.

Checkpoint verification checks complete registry authority and original bytes,
current repository lifecycle and rollback floor, key identity and issue/current
use eligibility, signature and all equalities before accepting state. Retained
entries and immutable result/graph links remain available for integrity checks;
missing links reject. Tail replay begins immediately after the checkpoint head
and must reach the independently read expected current head. A later head does
not invalidate an old entry's immutable result locator. The old graph-event
checkpoint is not an observation checkpoint and is never accepted by structural
look-alike decoding.

### Authenticated Snapshot And Cohort Preimage

The existing normative request, cursor, page and observed-payload schemas in
SIA31360-31815 remain the public field inventories, except that the approved
profile-3 route replaces `ObservedClaimProjection` with its separate temporal
and trust models. The incomplete foundation classes do not supersede them. The
public cohort listing omits some coordinates explicitly required in the
normative prose at SIA31900. In profile 3, retain the existing
ResolvedGraphObservationCohort fields and add all the following coordinates.
This makes the public cohort independently verifiable even when a page contains
no projection records; no hidden metadata participates in its digest:

- `graph_revision` and `observation_revision` from the snapshot;
- `memory_plane_write_revision` from that same full detached snapshot;
- `temporal_projection_generation_digest` and
  `temporal_projection_pointer_digest`, resolved by the canonical temporal
  selector from those snapshot records, both required nullable digests;
- `trust_projection_generation_digest` and `trust_projection_pointer_digest`,
  resolved independently by the canonical trust selector from those same
  snapshot records, both required nullable digests;
- `observation_schema_fingerprint` (the reference schema fingerprint is already
  in the cohort fields);
- `changed_record_keys` and `boundary_record_keys`, each a sorted unique tuple
  of typed `(record_kind, primary_key)` records, disjoint from each other.

Each generation/pointer pair is either both present or both null. A null pair
means its verified history is absent at the requested coordinate; it cannot
stand in for an unread, invalid or unavailable history. A cohort requiring a
projection of that kind rejects if its pair is null. A terminal zero-effect or
zero-operation source remains observable before the first projection generation.
For lineage, each coordinate identifies the selected history tip; predecessor
links commit the reachable generations returned in the stream.

GraphObservationCohortPreimage has exactly the complete new public cohort fields
minus cohort_digest. The cohort uses the ordinary registered self_digest rule:
its complete ResolvedGraphObservationCohort binding and all its other fields,
without an external-preimage exception. The server retains the typed preimage
with the snapshot. An independently collected complete stream must have exactly
the declared disjoint changed/boundary keys and matching page/cohort coordinates;
matching a cohort digest alone does not prove complete paging.

The two projection coordinates are not a merged authority. The production
snapshot selector must apply the selection rules of
`ProjectionHistoryRepository.current_temporal`/`current_trust` for a current
view, and `historical_temporal`/`historical_trust` for a historical view with
the same requested system time; lineage follows each corresponding pointer
chain. It receives only indexes constructed from the one detached memory-plane
snapshot. It validates each complete native generation before retaining its
generation digest, complete `TemporalProjectionRecord` or
`TrustProjectionRecord`, complete corresponding active/history pointer, and
same-kind successor pointer where present. A temporal advance cannot substitute
or rewrite the trust coordinate, and conversely. Missing, swapped,
cross-repository, generation/pointer-mismatched, or unreachable values reject
observation rather than falling back to a live read.

`GraphObservationSnapshot` is a server-owned type alias for two model roots,
`GraphRecordObservationSnapshot` and `IngestionTimeObservationSnapshot`, each
with exactly schema version 1,
snapshot token, protected creation time, memory-plane revision, authenticated
context digest, purpose, authorization decision, complete request coordinates
excluding cursor, cohort preimage, resolved cohort, and immutable ordered stream.
The first root has purpose literal `graph_observation`, a cursor-free
GraphObservationRequest field, and a tuple of GraphObservationStreamRecord.
The second has purpose literal `ingestion_time_attestation`, a cursor-free
IngestionTimeAttestationRequest field, and a tuple of ProductionIngestionTimeAttestation.
The request field refers to an explicit model with the corresponding complete
request field set minus cursor, named GraphObservationRequestCoordinates or
IngestionTimeAttestationRequestCoordinates. The attestation tuple element uses
the canonical `kind`-discriminated model union. No mixed request/stream union
is inferred from fields outside its own model. The snapshot alias dispatches
only by the two fixed purpose literals and is not itself a registry entry.
All other fields are identical across the two roots. The token is an unguessable identifier,
not authorization. Its retention deadline is the earlier of authorization
expiry and creation time plus protected page-policy maximum age. Restart or
eviction that loses this state returns a stale cursor; it never reconstructs a
different stream under the old token. Durable snapshot caching is not required
for correctness and is not introduced by this ledger design.

Each page reauthorizes before looking up token or seed. It then validates the
cursor signature, exact request coordinates, stream position and preceding
triple, and the cursor's signed `snapshot_write_revision`. It obtains a fresh
full `read_write_snapshot()` token and requires it to equal both the cursor and
retained snapshot `memory_plane_write_revision` before using the stream. This
is intentionally conservative: any intervening canonical-record batch makes
continuation stale, including a temporal-only or trust-only projection-history
publication. It does not reload one projection kind or manufacture a merged
state. It then compares current graph/observation and page-policy revisions,
checks snapshot age, and emits only the next contiguous slice. The canonical failure
mapping in SIA31947-31962 remains unchanged. Snapshot state, cursor and page
all bind the same decision; equal principal text does not substitute for the
authenticated context digest. No error includes stored identity or cohort data.

`GraphObservationCursorPayload.v1` consequently adds the required nonnegative
integer `snapshot_write_revision`, copied from the retained snapshot. Its
signature-only policy signs that field together with every other cursor field;
the field is not caller supplied and cannot be omitted or null. The emitted
`GraphObservationPage` and `IngestionTimeAttestationPage` each carry the same
`memory_plane_write_revision`, so their
records, cohort, snapshot token and cursor are independently joinable. These
are profile-3 fields only; historical cursor bytes stay on their existing route.

The graph stream uses the explicit per-kind variant union specified in
`schema-publication.md`. The outer record kind is the discriminator, each
variant's payload model is fixed, and outer primary-key/digest equalities are
checked before stream ordering or cursor construction. `GraphObservationStreamRecord`
is a type alias only, never an independently decoded registry root.


## Projection Observation Decision

Source label: `projection-observation-decision.md`.

### Demonstrated Boundary

SIA ObservedClaimProjection declares one selected_assertion_ids tuple, one
contested_assertion_ids tuple, one system_interval and transition_reason, with
both temporal and trust policy fingerprints. ExpectedClaimProjection mirrors
that shape. Neither shape identifies which projection authority supplies its
selection or how independently advancing histories combine.

Production has two validated authorities: TemporalProjectionRecord and
TrustProjectionRecord, each with its own generation, certificate and pointer
history. projection_history.py:6150-6198 can alter temporal selection after
trust arbitration. current_temporal/current_trust and their historical variants
select their respective histories independently. Equal projection_id does not
establish equal winners, publication time or transition reason.

Choosing one authority silently drops the other; manufacturing a merged result
would make the observation adapter a new arbitration owner. This is not a
registry encoding choice or permission to sign artifacts.

### Recommended Public Contract

Expose separate temporal and trust projection records in the observation stream.
Replace claim_projection with temporal_claim_projection and
trust_claim_projection in the new observation schema. Preserve all historical
reader routes; do not relabel existing bytes as the new schema.

Each new payload has exactly:

- observation_id: the profile-bound content address of projection kind,
  repository, generation digest and native projection digest;
- projection: the complete owner-validated TemporalProjectionRecord or
  TrustProjectionRecord respectively, with its original native digest;
- generation_digest: the selected native generation digest;
- publication_pointer: the complete owner-validated active/history pointer
  of the corresponding kind;
- successor_publication_pointer: the immediately following pointer of the
  same kind, or null when no successor exists in the snapshot;
- boundary: the cohort-derived flag;
- record_digest: the new registered observed-body digest.

These are two concrete models, not an untyped payload. Their stream primary
key is observation_id. The native logical projection_id remains unchanged
inside projection. Publication coordinates retain both time and sequence, so
two same-time publications are distinguishable without inventing a nonempty
wall-clock interval. The pointer's publication_kind supplies its own transition
reason; the adapter does not invent a combined reason.

Current and historical views select each kind through its existing canonical
selector at the same detached store snapshot and requested system time.
Lineage returns the reachable generation history for each kind. A trust-only
advance must not rewrite the temporal record, or vice versa. Expected graph
contracts and the independent comparator receive corresponding separate typed
records and compare both. No new winner-selection algorithm is introduced.

The alternative is to retain one combined public projection and specify a new
canonical composition rule, including disagreement, policy migration, temporal
partition boundaries and equal-time publications. That requires a separately
persisted/verified composition authority; the observation adapter cannot infer it.

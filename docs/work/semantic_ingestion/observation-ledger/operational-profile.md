# Operational Typed-Value Profile Construction

Status: design construction for the user-approved profile-3 direction. This
document is not a production change, registry publication, activation decision,
or approval of the proposed byte layouts. It gives the independent design review
one complete construction target for the runtime grammar and registry required
by SIA2676-2730 and SIA2825-2868.

## Scope And Owner

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

## Published Source Package

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

The source-role manifest is an external, non-self-referential publication
artifact, not a source role. It has exactly `role` equal to
`publication_manifest`, `profile_id`, `profile_version`, ordered `files`, and
`registry_digest`. Every `files` item has exactly `role` and `sha256`; its order
is unsigned UTF-8 byte order by role. It contains the complete role set and no
extra role. Schema IDs and
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

## Profile-3 Grammar And Fixed Envelope

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
protected immutable registry. Only a unique active/replay-allowed entry can
select the body decoder. It verifies the two artifact digests over the exact
body bytes, then invokes that selected decoder, enforces the entry's complete
closed schema and policies, and requires byte-identical re-encoding.

The parser has no endpoint hint, caller binding, file-name dispatch, current
profile fallback, or body-first generic decode. A profile-2 or diagnostic JSON
reader remains an explicitly selected historical route; it never enters this
operational parser. The fixed envelope syntax is preserved for future bodies.
Changing the envelope itself requires a separately reviewed versioned outer
dispatch contract; a new body binding alone cannot do it.

## Canonical Length-Prefix Construction

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
digest is the SHA-256 of a separately published, exact decoder implementation
source snapshot selected by the protected build, excluding the generated
registry/profile declaration section. It is never obtained by runtime
reflection and the implementation cannot contain the decoder digest it is being
measured against. This prevents a hashed-constant self-cycle. Profile-3 entries
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

## Deterministic Construction And Publication

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
   every active/replay status, unique coordinate, schema/policy closure, and
   the profile-3 null-only upcast rule.
5. Build immutable coordinate and binding lookup tables from the sorted entries,
   then atomically publish the one verified registry object.

Any failure leaves the previously published registry unchanged. Requests,
cursor payloads, stores, checkpoints, artifacts, and tests cannot provide a
registry, replace an entry, or widen read status. Reload receives the same
protected registry as writes. The registered reader first resolves the embedded
binding and only then decodes the body; this is required even when a caller has
an expected schema coordinate.

## Required Review Closure And Unresolved Details

This proposal fixes the profile-3 grammar-source bytes and all construction
preimages, but does not publish the schema inventory, decoder source identities,
deployment manifest coordinate, or independent golden-vector bytes. Protected
parser resource limits are composition configuration and must be supplied to
the parser independently of profile publication. The following must be frozen
by review before implementation assigns a digest or permits a writer:

- One complete closed declaration/policy source set for every ledger head,
  ledger entry, revision-free delta, source intent, activation, replay state,
  checkpoint/signing, request, page, and cursor schema named in
  `runtime-registry-contract.md`.
- The concrete stable decoder source identities and an independently
  reproducible relation between those identities and the implementation table.
- The deployment-manifest publication and protected composition-root mechanism
  that pins the completed registry and independent vector manifest.

No unresolved item authorizes a fallback to profile 2, runtime reflection, a
caller-supplied binding, or fixture-56 authority. This note proposes a runtime
construction only; it creates no production entrypoint binding and makes no
runtime, persistence, replay, or ledger-completion claim.

# Runtime Registry Construction Boundary

Status: construction proposal under Section 3.15.1; not approved, generated,
or installed. This document does not authorize a new profile coordinate.

## Authority And Ownership

`memory_evolution/ingestion_contracts.py` owns the five canonical profile,
binding, artifact, registry-entry and registry types specified by SIA2676-2730.
The existing binding and artifact types remain their canonical owners; no
observation-local copies are introduced. An observation store receives a
validated immutable registry through its protected composition root. A request,
cursor, persisted record, or checkpoint cannot replace that registry or provide
its expected digest. Deployment pins come from protected configuration.

Registry declarations are data. They cannot name an import to execute, evaluate
Python annotations, or supply a decoder callback. The composition root installs
an explicit table of supported schema bindings and their typed decoders. Each
table entry must match the registered decoder fingerprint before accepting
traffic. Unknown, duplicate, incomplete or substituted entries reject startup.
No lookup falls back to a current profile or infers a schema from a filename.

The operational registry is distinct from the closed 56-root test-only source
inventory at SIA9288. Neither its compiler nor its test signing ancestry becomes
a runtime dependency. Existing literal historical bindings and artifact bytes
are retained; they are not recomputed with a new formula under old coordinates.

## Decode And Encode Order

The proposed registered-artifact reader takes envelope bytes, the protected
registry/decoder table, a read mode (active or replay), and protected resource
limits. Endpoint-specific expectations are checked after embedded binding
resolution; they cannot choose the decoder.

1. Enforce envelope byte and structural resource limits and parse only the
   canonical outer envelope. Its body remains an uninterpreted byte string.
2. Validate the complete embedded binding and locate exactly one matching
   immutable entry. Verify the pinned registry, entry and binding commitments,
   supported read status, decoder fingerprint and profile grammar authority.
3. Verify body-byte and complete artifact digests against those exact bytes.
4. Decode the body with that registered grammar and enforce its closed schema:
   exact fields, optionality, enum membership, discriminated unions and numeric
   rules. Re-encode to byte-identical input before returning a typed value.
5. Validate the schema-specific digest/signature preimage under its registered
   exclusions and purpose. Domain provenance and store authorization remain
   separate subsequent checks; valid bytes alone grant no access or write.

The current `decode_artifact` performs inner generic decode before returning and
has no registry parameter. It cannot serve as step 1 without a refactor that
preserves existing callers and keeps unknown-binding rejection ahead of inner
decoding. Reuse its outer-envelope field checks and length-prefix primitive;
do not wrap its return value and call that pre-decode registry enforcement.

The registered writer accepts a typed value and an explicitly selected active
entry from the same protected registry. It validates the exact schema before
encoding and computes all registered commitments. A replay-only entry cannot
authorize a new write. Replay validates original bytes first and returns their
original identity. An upcast is a distinct derived artifact, never an in-place
rewrite. No ledger upcaster is proposed for legacy local observation chains:
those chains lack the global ordering evidence needed for a lossless conversion.

## Closed Registry Inputs

Every entry includes the fields mandated by SIA2709-2720. Its source package
must retain the exact bytes behind schema, enum, optional-field, numeric and
digest/signature policy fingerprints, plus the decoder artifact identity.
Fingerprints alone are insufficient construction inputs.

Schema declarations must explicitly enumerate flattened fields and their types,
the one discriminator for each union, required/omittable and nullable policy,
ordered versus set-valued collections, and every enum member. New ledger
declarations have no implicit defaults or omitted digest fields. The only
excluded fields are those listed in the schema's digest/signature policy;
entry or registry digests do not recursively enter their own preimages.

Profile and binding commitments follow SIA2850-2861 exactly. Registry source
loading must reject duplicate coordinate keys before a map can collapse them.
Entry order is canonical and independently reproducible. Decoder and upcaster
identities are included in the entry commitment and hence the pinned registry,
even though they are not part of the binding preimage. Upcast paths, if later
introduced, must be adjacent, acyclic, lossless and independently reproduced.

## New Observation Schema Inventory

These are behavior-owned proposed identities, each with its own exact versioned
entry; nested types are part of its transitive schema closure:

| Schema family | Canonical behavior owner | Required authority |
| --- | --- | --- |
| Ledger head and entry | Atomic store / observation persistence | Repository, activation, exact global predecessor and result link |
| Revision-free delta payload | Observation contracts | Exact canonical delta variant minus assigned revisions and self digest |
| Source observation intent | Native terminal contracts | Exact source outcome and schema fingerprint, before store assignment |
| Ledger activation | Writer admission | Drained predecessor admission, complete inventory and target epoch |
| Materialized replay state | Observation replay | Complete ordered prefix, typed audit records and verified result/graph links |
| Checkpoint bundle and signing preimage | Observation replay authority | Prefix head, repository, activation and protected lifecycle |
| Observation request, page and cursor | Authenticated observation service | Authenticated scope, snapshot and policy coordinates |

The head/entry/source-intent field lists are in `closed-contracts.md`. This table
does not declare the replay-state, page or cursor fields complete. Those exact
closures and their byte authority must be supplied before candidate freeze.

## Verification Matrix

| Boundary | Required discriminating proof |
| --- | --- |
| Selection before body parsing | Unknown complete binding with otherwise valid body; decoder spy remains uncalled |
| Registry trust | Changed schema, policy, decoder or entry under pinned registry fails before body decode |
| No coordinate substitution | Same schema name with different version/profile/binding fails exact resolution |
| Optional fields | Omitted versus null, required versus omittable, and no default insertion before verification |
| Closed grammar | Unknown fields/tags/enums, duplicate coordinates/map keys, ambiguous union and bool-as-int reject |
| Resource limits | Exactly-at-limit succeeds; one-over byte/node/depth rejects without partial publication |
| Historical identity | Literal old bytes verify using their exact historical decoder; no global audit fabricated |
| Read/write status | Active writes succeed; replay-only rejects writes while permitted exact historical read succeeds |
| Commitments | Independent preimage/golden bytes cover every registered field and exclusion |
| Integration | Real group/source public writers and replay use the registered reader/writer; helper-only tests cannot close this row |

## Remaining Construction Decision

The frozen fixture-v2 formulas (reference compiler lines 865-894) and its grammar
are not the general runtime registry formula in Section 3.15.1. Current runtime
codec constants name profile 2, while the implemented generic primitive subset
uses no terminal LF and encoded-JSON-key map order; the fixture grammar specifies
a terminal LF and scalar-key order. Runtime enum registration is also absent.
Therefore a well-shaped profile-2 constant cannot establish full grammar
authority for new entries. Before promotion, identify the exact published
runtime grammar bytes and their profile coordinate, or record and review an
explicit versioned compatibility decision. Do not silently reinterpret existing
profile-2 bytes or expand the test-only fixture to conceal this boundary.

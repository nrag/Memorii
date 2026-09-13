# Observation source-authoring draft worker report

Scope: added the offline-only `semantic_ingestion_observation_source_draft.py`
authoring aid and focused tests.  Its explicit static inventory covers the
implemented profile-3 observation roots, the permitted legacy digest-free
selector/failure values, native graph/effect/governance roots, projection
publication values, replay/checkpoint values, and time roots.

The generated review artifact is
`source-draft/observation-profile3-authoring-draft.json`.  It is expressly
untrusted and cannot be consumed by a compiler, decoder, registry, or runtime
service.  The tool uses reflection only after the static model map selects a
reviewed class.  It emits flattened Pydantic field shapes, optional and empty
numeric/enum role drafts, and reports unsupported annotations, enum identities,
and digest/signature domains instead of inventing an authority.

`SnapshotGraphRecord.payload` is the sole explicit override and emits the
canonical adapter's twelve `record_kind` alternatives.  It never emits an open
`BaseModel` payload.  Root source IDs are normative class names; helper schema
name collisions are reportable rather than module-qualified.

Current generated inventory: 78 static roots and 180 flattened root/helper
schema drafts.  The authoring pass unwraps reviewed `Annotated` values in
tuples and optionals, preserves SHA-256/signature lexical metadata and exact
integer bounds, and renders Pydantic field discriminators.  It also flattens
reviewed nested record aliases and recognizes an existing common singleton
`Literal` discriminator: the temporal/trust certificate unions use their
native `publication_kind` values `projection_commit` and `migration_cutover`.

The integrity-policy table is source-only and explicit.  It preserves ordinary
native graph/effect/transitive values and stream wrappers, exact domains for the
three native V3 publication members, cursor signing, and the checkpoint's
external-signing-preimage grammar.  New profile-3 self-digest roots use the
requested stable proposed domains and carry `proposal_requires_review: true`.
Time-attestation roots remain unresolved.  `SourceModality` now has the
explicit `memorii.domain.SourceModality` enum draft with all owner member names
and wire values.

The finite source-only ordinary table now also covers every reviewed native and
transitive model that remained after the first policy pass.  Source and
transaction-group time attestations use proposed self-digest domains with
`attestation_digest`; the checkpoint external-signing domain has the same
concrete proposed-domain marker.  After the approved witness-boundary amendment,
`SourceRetentionTimeWitness` and `TransactionGroupCommitTimeWitness` are absent
from the core model, aliases, source roots, recursive schema closure, and draft
source IDs.  The current draft has no
unmapped policy rows.  Exact sort/uniqueness and cross-field validators remain
native owner semantics; this raw type draft records only grammar-representable
field shape.

Unresolved work is intentional: decoder, upcast, registry roles; reviewed enum
qualified IDs; and profile-3 digest/signature policy domains all require the
future static decoder/package authoring step.  No source digest, decoder digest,
binding, registry entry, or publication claim is generated.

Static checks run by this worker:

```text
.venv/bin/ruff check memorii/memorii/tools/semantic_ingestion_observation_source_draft.py memorii/tests/unit/tools/test_semantic_ingestion_observation_source_draft.py
.venv/bin/pyright --pythonpath "$PWD/.venv/bin/python" memorii/memorii/tools/semantic_ingestion_observation_source_draft.py memorii/tests/unit/tools/test_semantic_ingestion_observation_source_draft.py
```

Pytest remains owned by the coordinator.

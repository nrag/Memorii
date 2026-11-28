# Create and use a learned entity subtype

- Order: 5. Status: queued. Baseline: `80fc5852`; design and candidate head pending.
- Requirements: partial OLE-01/02/03/04/05/06/08/11/13.
- Dependencies: generic grounded candidate and owner selection path. Freeze a real subtype witness and how its identity, protected use and exact type-registry version are proved.

## Execution boundary

Reuse `EntityTypeGapSignature`, the existing typed entity registry and
`LearnedRelationRuntime` selection owners. Add one closed subtype edit
with one registered parent, distinguishing evidence, bounded aliases and
registered identity policy. Preserve compatible parent capability lookup
and exact type-registry authority through validation, writer, fact history
and protected read. Freeze serialized operation/registry compatibility and
rolled-back selection behavior. Existing IDs and facts are not reclassified.
Unknown codecs, roots, identity algorithms, parents and scopes fail closed
under the existing unsupported-capability boundary.

## Acceptance and verification

- Evaluate and approve a subtype-only edit. Verify inherited compatible
  read/write use after reopen through an existing relation, with a fact
  that demonstrates the subtype's independent identity. No relation edit
  or change to the parent's semantics.
- Reject collisions after normalization, multiple or unknown parents,
  incompatible identity, wrong scope and unsupported capability. Exercise
  a parent-compatible case and a disallowed sibling. Denied requests have
  no state changes or evidence disclosure.
- Show version-pinned replay, owner rejection and rollback with unchanged
  eligibility of historical reads and zero peer-agent disclosure. Verify
  the packaged registry and previously learned relation remain readable.

```sh
python -W error -m pytest -q -p no:cacheprovider \
  tests/unit/core/semantic_ingestion/test_default_catalog_corpus.py \
  tests/unit/core/semantic_ingestion/test_default_catalog_runtime.py \
  tests/unit/core/semantic_ingestion/test_coverage_recurrence.py \
  tests/unit/core/semantic_ingestion/test_learned_relation.py \
  tests/integration/test_scoped_context_production_binding.py
```

Close with installed subtype evidence, current gate and compatibility
results, field-aware identity checks and focused review. Record which
broader requirements remain partial or deferred in the index.

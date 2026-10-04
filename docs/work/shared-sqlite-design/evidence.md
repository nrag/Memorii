Current frozen candidate: 22e29f90ab90fa9b67b489d8f293b4a9ecbe4e5bf1dad7c0d6d3f2a7697706ad

# Shared SQLite Evidence

Historical first-review candidate: dd852f746068a3fe3d960c9566df06fa163d00b13b80e5608bacdaf4a0d457d5
Baseline HEAD bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8. Dirty tree: pre-existing user Hermes design edit; prior assessment/runtime design artifacts; current design extension. Only canonical design + this directory changed by this operation.

## Current Code And Owners

MemoryPlaneStore protocol at core/memory_plane/store.py:181; JsonlMemoryPlaneStore:482; apply_batch:616; full-history atomic replacement:788. Preserve data/write revisions, three typed preconditions, governed-write policy, callback fence, detached records. MemoryPlaneUnitOfWork is a snapshot + optimistic batch, not a held write transaction. FilesystemStorageBundle currently hardcodes JSONL constructors; update composition and types for shared backend, no silent fallback.

SemanticIngestionAtomicStore in core/memory_evolution/atomic_store.py owns governed semantic groups; commit_or_reload_bootstrap_graph_group_v3 -> memory-plane conditional batch. LearnedRelationRuntime in core/semantic_ingestion/learned_relation.py owns proposal/version/attempt/pointer/replay records; _select has pointer CAS; recover validates selected attempts; Hermes factory composes real owner-bound callbacks. Catalog package authority stays separate. Mapper independently confirmed these paths/tests; its recommendation to prohibit physical co-location was rejected as unsupported by governing logical-domain invariants and contrary to the user's expressly authorized backend-design extension. No domain authority is merged.

## Local Checks

From memorii/: ../.venv/bin/python -W error -m pytest tests/unit/core/test_jsonl_memory_plane_store.py tests/unit/core/test_memory_plane_store_contract.py -p no:cacheprovider -q
Exit 0: 27 passed in 2.87s. Existing backend behavior only; no SQLite implementation claim.

PYTHONPATH=memorii .venv/bin/python docs/work/shared-sqlite-design/migration_probe.py
Exit 0, SQLite 3.53.4: original batch bytes preserved; latest-record parity; write/data revisions 3/2; induced coupled transaction rollback; committed receipt survives reopen; source unchanged; integrity_check ok. Toy SQL only: not production migration, semantic/catalog authority parity, crash/powerloss or performance evidence. Original runtime/reducer mechanism probes remain in the linked parent evidence.

Canonical local checks: 12 links verified, 18 unique requirements, whitespace clean; git diff --check passes. Full production-binding plan and identity manifest in canonical document; planned callers are zero until implemented. No code/schema/generated package/workflow or production data mutation.

## Scope And Evidence Limits

Changed authority surfaces: shared physical transaction coordinator with separate views; entire memory-plane log and ontology records; dual revision/CAS parity; query/index contracts; full partition publication vector/manifest; offline migration selector and rollback; retained package/key/legacy reader authority; expanded release gates. New source identities, SQL catalogs, manifests/queries/migration artifacts and tests are inventoried in canonical identity ledger. Governing digest-bound semantic sources and catalogs unchanged.

Additional existing ontology baseline: from memorii/, ../.venv/bin/python -W error -m pytest tests/unit/core/semantic_ingestion/test_learned_relation.py -p no:cacheprovider -q. Exit 0: 14 passed in 4.65s. Current activation/recovery contracts only; no migrated backend evidence.

Final candidate 22e29f90ab90fa9b67b489d8f293b4a9ecbe4e5bf1dad7c0d6d3f2a7697706ad: 18 requirements, relative links and whitespace checked; new LegacyStorageSelector/storage lifecycle, constructor/read ingress binding and acceptance inventories reconciled. No tests rerun for documentation-only remediation; baseline 27+14 and probe unchanged. Final canonical freeze applies while review runs.

Final checks: canonical hash unchanged at 22e29f90ab90fa9b67b489d8f293b4a9ecbe4e5bf1dad7c0d6d3f2a7697706ad; all current packet identity claims agree; 18 requirements and links verified; whitespace checks passed including git diff --check. Final full spec/correctness/test approvals recorded in reviews.md.

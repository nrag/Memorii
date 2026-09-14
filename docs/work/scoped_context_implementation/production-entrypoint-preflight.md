# Production Entrypoint Preflight

Spark impl_paths read-only preflight, reconciled by coordinator at base
b4f6c24b091a28bd3d1f65102c742478fc7276b3 before product edits.
Approved design: f43d2cca76a57776cc2223ec1e9d413cb0deb6e94a5981263b0b43deae04386e.
Search: retrieve_context, read_snapshot, build_provider_memory_service_from_env,
EvolutionStateRepository, MemoryEvolutionRetrievalRuntime, BM25Scorer in production.

| Requirements | Current canonical owner | Required implemented chain | Baseline |
| --- | --- | --- | --- |
| SMC-R01,R02,R06,R07,R10 | provider/service.py prefetch at 902, result at 915 | retrieve_context -> validated request -> separate read authority -> assembler -> release -> typed result | new symbols zero callers |
| SMC-R03,R09 | memory_plane/store.py read_snapshot at 340,541 | provider -> MemoryPlaneService snapshot delegate -> store clone exactly once | usable store primitive; no retrieval binding |
| SMC-R04 | provider/reranking.py uses BM25Scorer at 87 | request-local scoped index -> existing scorer | scorer reusable, current reranker scope weights not required |
| SMC-R05 | memory_evolution/state_repository.py live readers; retrieval_runtime.py retrieve at 78 | pure from_snapshot -> ClaimStateQueryService -> runtime with local guarded analyzer and all snapshot callbacks | no snapshot decoder factory |
| SMC-R08,R10 | provider/factory.py constructor at 108 | forward separate scoped_read_authority | preserve defaults |
| SMC-R08,R10 | filesystem_storage/bundle.py build_provider_memory_service at 88 | forward authority to factory; returned provider method is root trigger | new forwarding absent |
| SMC-R08,R10 | integrations/hermes_provider.py constructor and prefetch | constructor forwards authority; new method forwards request/opaque ingress to provider | new forwarding absent |

All paths are below memorii/memorii/core except integrations. Existing prefetch
is not an authorized scoped API and does not fulfill R02 through ingestion
plumbing. Existing execution/service.py runtime retrieval remains excluded.

## Coordinator Reconciliation

Spark proposed three ambiguities that the frozen design already resolves:
handles are reusable until expiry/revocation (single-use was unsupported);
missing/ineligible mandatory refs yield MANDATORY_UNRESOLVED after valid initial
authorization; only canonical memory-plane clone is included, never cross-store
work-state/graph checkpoints. No external semantic decision is pending here.
The map's current prefetch caller-count assertions are not acceptance evidence.
The implementation must recount exact new retrieve_context callsites and prove
both real roots, authority, readers and release behavior before review.

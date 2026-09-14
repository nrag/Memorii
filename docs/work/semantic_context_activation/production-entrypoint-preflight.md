# Production Entrypoint Preflight

Baseline: `b4f6c24b091a28bd3d1f65102c742478fc7276b3`, initially clean.
Spark `code-mapper` task `map_paths`, reconciled by coordinator before canonical
writer edit on 2026-09-06. Scope: additive read API; ingestion mutation is excluded.

## Verified map

All paths below are relative to `memorii/memorii/`.

| Trigger | Composition/callsite | Arguments and owner chain | Current outcome |
| --- | --- | --- | --- |
| Host prefetch | `integrations/hermes_provider.py:133` | query, session/task/user, language/reference time -> `ProviderMemoryService.prefetch` -> `prefetch_result` | text/context channels; no explicit mandatory-reference contract |
| Direct provider read | `core/provider/service.py:902,1125` | `prefetch` and `prefetch_with_attention` -> `prefetch_result` | two internal callers; old envelopes retained |
| Provider composition | `core/provider/factory.py:108` | memory plane, host authority, conflict owners, clock -> `ProviderMemoryService` | one factory constructor site |
| Filesystem composition | `core/filesystem_storage/bundle.py:105` | configured memory plane -> provider factory | one root |
| Hermes composition | `integrations/hermes_provider.py:78` | provider configuration -> same factory | one adapter root |
| Canonical optional context | `core/provider/service.py:931` | query/session/task/user/top_k -> `MemoryPlaneService.prefetch_provider_context` -> scoped records -> `ProviderReranker` | one service caller; excludes evolution records; BM25/recency ranking |
| Structured semantic read | `core/memory_evolution/service.py:474` | `MemoryQueryInput` -> `MemoryEvolutionRetrievalRuntime.retrieve` | typed decision, graph/temporal/lifecycle policy |
| Runtime retrieval | `core/execution/service.py:402` | `RetrievalPlan` -> `MemoryPlaneService.retrieve_runtime_context` | not new API composition; solver creation is outside this scope |
| Canonical snapshot | `core/memory_plane/store.py:340,541` | `read_snapshot()` under backend lock -> detached cloned records and runtime data revision | both memory and JSONL implementations; no public snapshot API on service yet |

Queries used: `rg -n 'prefetch_result\(|prefetch_provider_context\(|retrieve_runtime_context\(|RuntimeStepService\(|ProviderMemoryService\('` and
`rg -n 'prefetch\(|build_provider_memory_service_from_env\('` over `memorii/memorii`.
Counts above are exact callsites in the named production files, not a count of
external consumers. Benchmark callers are not production activation proof.
Future `retrieve_context` callers: zero at baseline; proposed bindings must be
specified in the design and proved during implementation, not invented here.

## Reusable policy owners

- `core/memory_evolution/retrieval_runtime.py:56`: callback-injected claim,
  entity-link, action readers; query analyzer, temporal anchors, clock and predicate
  registry. New API must bind all readers to one request snapshot.
- `core/memory_evolution/state_repository.py:18`: typed decoding of claim states,
  entity links, actions, contradictions and temporal anchors. Extract/reuse decoding,
  never mutate ingestion policy or call live readers from a frozen read context.
- `core/provider/bm25.py`: existing scorer/tokenization. ICU availability changes
  tokenization; any reproducibility identity must bind tokenizer behavior.
- `core/directory/directory.py` and `indexes.py`: in-memory relationship directory;
  not a durable cross-store snapshot or authorization registry.

## Corrected mapper limitations

The raw mapper summary conflated benchmark callers with production callers and
described broad semantic ingestion stores as non-atomic. Those statements are not
adopted. Completed ingestion's atomic publication contract is preserved. The
relevant unsupported composition is a joint snapshot across separately configured
execution graph, solver/overlay stores and the memory plane. This design must not
claim that joint transaction exists. No generated build tree is treated as source.

`_matches_scope` permits null fields and is a query helper, not read authority.
`prefetch_result` performs multiple reads and truncates work-state summaries to
three; it cannot establish mandatory completeness. Store revision tracks runtime
data and alone cannot bind internal governance state. Request-local snapshot
indexes avoid a cross-request cache invalidation claim.

## Feasibility evidence

`snapshot_probe.py` passed for memory and JSONL with the repository `.venv`:
caller mutation does not change stored content, retained snapshot stays stable
after a second record, data revision advances, independent JSONL reopen retains
both records. This is mechanism evidence, not new API proof or a performance test.

## Planned binding acceptance

The design must name the new public request, host read-authority owner, root
arguments, snapshot reader, index/semantic policy owners, rendering and all denial
outcomes. Direct/factory/filesystem/Hermes component tests must strip each required
owner and prove fail-closed behavior. No existing benchmark-only runtime root may
be substituted for those tests. Live integration and deployment remain separate.

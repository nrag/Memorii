# Implemented Production Binding Ledger

Base b4f6c24b091a28bd3d1f65102c742478fc7276b3 plus active working tree.
Freeze hashes and final verification still required. Paths below are relative
to memorii/memorii. Design's zero-caller wording records its pre-implementation
baseline, not the present production caller count.

| Requirements | Trigger/root | Exact arguments and owner chain | Production callers / proof | State |
| --- | --- | --- | --- | --- |
| SMC-R01-R10 | HermesMemoryProvider.retrieve_context | integrations/hermes_provider.py:98 forwards request and opaque_host_ingress by identity to ProviderMemoryService.retrieve_context | one non-test call to provider retrieve_context; real Hermes constructor matrix | implemented, final evidence pending |
| SMC-R01-R10 | FilesystemStorageBundle.build_provider_memory_service returns provider | bundle.py:126 -> factory -> provider, scoped_read_authority; returned provider method is public root trigger | bundle and build_filesystem_provider forward authority; real filesystem integration matrix | implemented, final evidence pending |
| SMC-R02,R08,R10 | build_provider_memory_service_from_env | factory.py:128 passes scoped_read_authority into ProviderMemoryService | factory production construction, Hermes/bundle callers | implemented, final evidence pending |
| SMC-R01-R07,R09 | ProviderMemoryService.retrieve_context | service.py:619 revalidates request -> authority.resolve -> memory_plane.read_snapshot -> ScopedContextAssembler.assemble(request,revision,records,grant) -> authority.authorize_release -> validated result | one adapter caller, both library roots exercised | implemented, final evidence pending |
| SMC-R03,R09 | MemoryPlaneService.read_snapshot | service.py:168 delegates to record-store read_snapshot exactly once | provider call at service.py:638 | implemented, snapshot/fault proofs pending |
| SMC-R05,R07 | assembler structured path | EvolutionStateRepository.from_snapshot -> ClaimStateQueryService; runtime receives claims.retrieve, list_entity_links, list_actions, local guarded analyzer, captured anchors, explicit clock/predicates | `ProviderMemoryService.retrieve_context` is reached by both non-test roots and invokes `ScopedContextAssembler._assemble_structured`; `test_real_roots_return_unique_sorted_transitive_structured_source_closure` proves its selected claim -> canonical source -> raw closure through filesystem and Hermes | locally verified; final candidate review and CI evidence pending |

`rg` query: def retrieve_context, .retrieve_context(, scoped_read_authority=,
ScopedContextAssembler(, .read_snapshot(, authorize_release( across named roots.
No legacy prefetch substitution, remote analyzer, graph-store or harness
invocation is added. Fail-closed absence is a required design behavior; it is
not an alternate implementation path. Host pilot remains excluded.


Final construction root evidence: root-proof-report.md records 109 real-root cases, including exact namespace mismatch, owner stripping, dependency faults, immutable snapshot, lifecycle release races and process reopen. The coordinator reruns the exact dedicated workflow command at the frozen candidate. Historical zero-caller statements describe the preimplementation baseline only; HermesMemoryProvider.retrieve_context is now the non-test caller.


## Corrected Candidate Exact Callsites

- ProviderMemoryService.retrieve_context: core/provider/service.py619; resolve before memory-plane snapshot, release after assembly.
- Factory explicit scoped_read_authority forwarding: core/provider/factory.py128.
- Filesystem bundle forwarding: core/filesystem_storage/bundle.py126 and174.
- Hermes constructor forwarding: integrations/hermes_provider.py80/89; actual non-test retrieve_context caller at98 (method92).
- Snapshot delegate: core/memory_plane/service.py165; immutable decoder factory: core/memory_evolution/state_repository.py30.
- Root proof:145integration cases;8unit cases; main imported candidate153+CTV assertion=154passed19.61seconds. Exact current/history/interval/anchor IDs, claim-as-evidence budget union, captured revision, errors, stripped owners, release races and restart are covered. Runtime graph/action mutation dispatch remains prohibited.

No caller made grant or fallback reader was introduced. Source hashes are in candidate-source.json; review-candidate.json freezes this ledger and Spark preflight.

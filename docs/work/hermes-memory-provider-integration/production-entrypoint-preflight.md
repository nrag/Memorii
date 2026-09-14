# Hermes Memory Provider Production Entrypoint Preflight

- Historical base revision: `93788d9208a992337ebedc67ff954a606132fdef`
- Mapped implementation revision: `a862b361`
- Prior evidence revision: `229a3b80`
- Delivery fidelity: Level 2 early real-world testing
- Mapper: `/root/hermes_plugin_preflight`
- Mapping date: 2026-09-13

## Search Scope

The mapping traced `hermes_agent.memory_providers`,
`memorii.hermes.provider_service`, `MemoriiHermesMemoryProvider`,
`build_started_hermes_memory_provider`, `ProviderMemoryService`,
`InstalledHostBootstrapCapabilityProvider`, activation tooling, and every
in-repository service-factory implementation or caller. The candidate query
found one external Hermes discovery root and zero in-repository production
implementations of the deployment service-factory entry point.

Mapping query: `rg -n "hermes_agent.memory_providers|memorii.hermes.provider_service|MemoriiHermesMemoryProvider|build_started_hermes_memory_provider|ProviderMemoryService" memorii README.md docs/work/hermes-memory-provider-integration`.

## Production Entrypoint Bindings

| Behavior | Production trigger and root | Authority and owner chain | Durable outcome | Production callers | Status |
| --- | --- | --- | --- | ---: | --- |
| Hermes provider discovery | Hermes selects `memory.provider: memorii`; `hermes_agent.memory_providers` loads `MemoriiHermesMemoryProvider` | installed wheel metadata -> current Hermes plugin loader -> concrete Hermes ABC subclass | provider instance is available for Hermes probing | 1 external Hermes loader | Implemented and checked against Hermes `ee445299` |
| Configured service initialization | Hermes calls `initialize`; bridge resolves exactly one `memorii.hermes.provider_service` factory | deployment factory -> `HermesProviderRuntimeBinding` -> verified `ProviderMemoryService` plus ingress issuer -> `build_started_hermes_memory_provider` | observation-ledger activation and startup reconciliation | 0 in-repository production factory implementations | Blocked on deployment-owned signed factory |
| Turn capture and recall | Hermes calls `on_turn_start`, `prefetch`, `sync_turn`, and lifecycle hooks | current participant/session evidence -> deployment ingress issuer -> canonical Hermes adapter -> provider validation -> JSONL memory plane | durable source capture and committed-memory retrieval | 1 external Hermes manager after successful initialization | Implemented bridge path; operational proof blocked with initialization |

## Branch Points

- No service-factory entry point: Hermes discovers the provider and reports it
  unavailable before initialization.
- Multiple, unloadable, non-callable, or wrongly typed factories: the bridge
  fails closed.
- Invalid production bootstrap authority or profile: canonical service startup
  rejects observation-ledger activation before turn processing.
- Invalid ingress issuance: the mutating hook raises before persistence.

## Conclusion

The wheel and bridge are sufficient for discovery and contract validation.
They are not sufficient for an interactive semantic-memory run. The smallest
remaining deployment input is one installed, deployment-owned service factory
that constructs the verified production authority and ingress issuer from the
signed release artifacts. Packaging a scenario-test authority or an unsigned
fallback in Memorii would bypass the governing activation contract.

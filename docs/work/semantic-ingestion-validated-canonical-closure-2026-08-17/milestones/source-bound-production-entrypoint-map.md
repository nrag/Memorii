# Source-Bound Production Entrypoint Map

- Read-only evidence source: `production-entrypoint-bindings-v11.json` and `production-owner-oracle-v8.json`.
- Evidence run for this map: `validate_production_entrypoint_bindings_v11.py`.
- Timestamped working revision: `b9daf00a0e6956e51106756f1baaf23190c688bb`.

## Composition Roots And Triggers

| Root id | Owner and location | Trigger families | Nonzero production callers |
| --- | --- | --- | --- |
| `filesystem_bundle` | `memorii/memorii/core/filesystem_storage/bundle.py::FilesystemStorageBundle.build_provider_memory_service` | `direct_sync`, `direct_composite_sync`, `direct_memory_write` | 3 |
| `filesystem_factory` | `memorii/memorii/core/filesystem_storage/bundle.py::build_filesystem_provider` | `direct_sync`, `direct_composite_sync`, `direct_memory_write` | 3 |
| `provider_factory` | `memorii/memorii/core/provider/factory.py::build_provider_memory_service_from_env` | `direct_sync`, `direct_composite_sync`, `direct_memory_write` | 3 |
| `hermes_constructor` | `memorii/memorii/integrations/hermes_provider.py::HermesMemoryProvider.__init__` | `hermes_sync`, `hermes_turn`, `hermes_session_end`, `hermes_pre_compress`, `hermes_delegation`, `hermes_memory_write` | 18 |

## Trigger-Entry Mapping

| Trigger family | Entrypoint | Trigger rows (accepted design requirements) |
| --- | --- | --- |
| `direct_sync` | `memorii/memorii/core/provider/service.py::ProviderMemoryService.sync_event` | `VCC-R01`, `VCC-R02`, `VCC-R03`, `VCC-R04`, `VCC-R05`, `VCC-R06`, `VCC-R07`, `VCC-R08`, `VCC-R09`, `VCC-R10`, `VCC-R11`, `VCC-R12` |
| `direct_composite_sync` | `memorii/memorii/core/provider/service.py::ProviderMemoryService._sync_composite_event` | `VCC-R01`, `VCC-R02`, `VCC-R03`, `VCC-R04`, `VCC-R05`, `VCC-R06`, `VCC-R07`, `VCC-R08`, `VCC-R09`, `VCC-R10`, `VCC-R11`, `VCC-R12` |
| `direct_memory_write` | `memorii/memorii/core/provider/service.py::ProviderMemoryService.apply_memory_write` | `VCC-R01`, `VCC-R02`, `VCC-R03`, `VCC-R04`, `VCC-R05`, `VCC-R06`, `VCC-R07`, `VCC-R08`, `VCC-R09`, `VCC-R10`, `VCC-R11`, `VCC-R12` |
| `hermes_sync` | `memorii/memorii/integrations/hermes_provider.py::HermesMemoryProvider.sync_event` | `VCC-R01`, `VCC-R02`, `VCC-R03`, `VCC-R04`, `VCC-R05`, `VCC-R06`, `VCC-R07`, `VCC-R08`, `VCC-R09`, `VCC-R10`, `VCC-R11`, `VCC-R12` |
| `hermes_turn` | `memorii/memorii/integrations/hermes_provider.py::HermesMemoryProvider.sync_turn` | `VCC-R01`, `VCC-R02`, `VCC-R03`, `VCC-R04`, `VCC-R05`, `VCC-R06`, `VCC-R07`, `VCC-R08`, `VCC-R09`, `VCC-R10`, `VCC-R11`, `VCC-R12` |
| `hermes_session_end` | `memorii/memorii/integrations/hermes_provider.py::HermesMemoryProvider.on_session_end` | `VCC-R01`, `VCC-R02`, `VCC-R03`, `VCC-R04`, `VCC-R05`, `VCC-R06`, `VCC-R07`, `VCC-R08`, `VCC-R09`, `VCC-R10`, `VCC-R11`, `VCC-R12` |
| `hermes_pre_compress` | `memorii/memorii/integrations/hermes_provider.py::HermesMemoryProvider.on_pre_compress` | `VCC-R01`, `VCC-R02`, `VCC-R03`, `VCC-R04`, `VCC-R05`, `VCC-R06`, `VCC-R07`, `VCC-R08`, `VCC-R09`, `VCC-R10`, `VCC-R11`, `VCC-R12` |
| `hermes_delegation` | `memorii/memorii/integrations/hermes_provider.py::HermesMemoryProvider.on_delegation` | `VCC-R01`, `VCC-R02`, `VCC-R03`, `VCC-R04`, `VCC-R05`, `VCC-R06`, `VCC-R07`, `VCC-R08`, `VCC-R09`, `VCC-R10`, `VCC-R11`, `VCC-R12` |
| `hermes_memory_write` | `memorii/memorii/integrations/hermes_provider.py::HermesMemoryProvider.on_memory_write` | `VCC-R01`, `VCC-R02`, `VCC-R03`, `VCC-R04`, `VCC-R05`, `VCC-R06`, `VCC-R07`, `VCC-R08`, `VCC-R09`, `VCC-R10`, `VCC-R11`, `VCC-R12` |

## Segment outcomes for each requirement row

- `VCC-R01`: `conditional_durable`
- `VCC-R02`: `pure_no_write`
- `VCC-R03`: `admission_branch`
- `VCC-R04`: `pure_no_write`
- `VCC-R05`: `conditional_normalization`
- `VCC-R06`: `conditional_handoff`
- `VCC-R07`: `conditional_durable`
- `VCC-R08`: `cache_state_only_no_durable_write`
- `VCC-R09`: `durable_terminal_write`
- `VCC-R10`: `construction_no_write`
- `VCC-R11`: `planned_observability`
- `VCC-R12`: `current_always_allocated`

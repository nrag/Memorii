# Reconstruction And Digest Ownership Census

- Read-only evidence source: `production-owner-oracle-v8.json`.
- Revision: `b9daf00a0e6956e51106756f1baaf23190c688bb`.

## Current Owners and Source Files

- Durable modules: `memorii.core.semantic_ingestion.persistence`, `memorii.core.memory_evolution.atomic_store`
- Source files under owner oracle and hash coverage: 12 total
  - `memorii/memorii/core/filesystem_storage/bundle.py`
  - `memorii/memorii/core/memory_evolution/atomic_store.py`
  - `memorii/memorii/core/memory_evolution/ingestion_contracts.py`
  - `memorii/memorii/core/provider/factory.py`
  - `memorii/memorii/core/provider/ingestion.py`
  - `memorii/memorii/core/provider/service.py`
  - `memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py`
  - `memorii/memorii/core/semantic_ingestion/contracts.py`
  - `memorii/memorii/core/semantic_ingestion/persistence.py`
  - `memorii/memorii/core/semantic_ingestion/production_capture.py`
  - `memorii/memorii/core/semantic_ingestion/source_normalization_execution.py`
  - `memorii/memorii/integrations/hermes_provider.py`

## Expected Mutation Coverage Ledger

- Required mutation names (32):
  - `R08_relabelled_durable`
  - `alias_attribute_service_write`
  - `alias_setattr_service_write`
  - `aliased_durable_sink`
  - `arena_receiver_proxy`
  - `constructor_none_authority`
  - `container_service_annotation`
  - `detached_filesystem_instance`
  - `detached_root_bridge`
  - `detached_trigger_row`
  - `dict_service_write`
  - `dict_update_service_write`
  - `direct_durable_sink`
  - `disconnected_row`
  - `dispatch_table_durable_sink`
  - `dynamic_durable_sink`
  - `forged_root_mapping`
  - `forged_trigger_mapping`
  - `hook_none_authority`
  - `injected_service_type_substitution`
  - `later_receiver_reassignment`
  - `missing_authority_keyword`
  - `object_setattr_service_write`
  - `receiver_value_substitution`
  - `removed_composite_trigger`
  - `removed_memory_trigger`
  - `root_anchor_swap`
  - `service_guard_bypass`
  - `setattr_service_write`
  - `vars_service_write`
  - `widened_service_annotation`
  - `wrong_target_same_name`

## Census mismatch currently blocking readiness

- `validate_candidate_manifest_v12.py` reports 4 candidate tracked artifacts changed from the frozen lock:
  - `memorii/memorii/core/provider/service.py`
  - `memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py`
  - `memorii/memorii/core/semantic_ingestion/contracts.py`
  - `docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/production-entrypoint-bindings-v11-validation.json`

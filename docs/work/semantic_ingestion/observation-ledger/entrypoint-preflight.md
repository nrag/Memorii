# Observation Ledger Entry-Point Preflight (Bounded)

Scope is the bounded, production-relevant native write path and authority-retention boundary only.

## Exact discovery scope

- Read files under:
  - `memorii/memorii/core/provider/{factory.py,service.py,ingestion.py}`
  - `memorii/memorii/core/semantic_ingestion/{production_capture.py,capability.py,source_normalization_stage.py,bootstrap_graph_host.py,source_normalization_host.py,bootstrap_graph_builtin.py,bootstrap_graph_coordinator.py,bootstrap_graph_artifact_assembler.py}`
  - `memorii/memorii/core/filesystem_storage/bundle.py`
  - `memorii/memorii/integrations/hermes_provider.py`
  - `docs/work/semantic_ingestion/{observation-ledger/readiness.md,projection-observation-decision.md,engineering-closure/resume.md}`
- Read tests for bounded runtime confirmation:
  - `memorii/tests/unit/core/semantic_ingestion/{test_native_policy_retention.py,test_bootstrap_graph_observation_retention.py}`

## Verified owning path (ordered)

1. **Production entry root**
   - `CanonicalEvidenceCaptureSupervisor.capture_cell` resolves verified authority and calls `_build_root` (`production_capture.py:107-115`) and then one `service.sync_event(...)` (`production_capture.py:116-131`).

2. **Service assembly root**
   - `_build_root` dispatches one of four roots (`direct`, `factory`, `filesystem`, `hermes`) to either:
     - `ProviderMemoryService(...)` (direct),
     - `build_provider_memory_service_from_env(...)` (`factory`),
     - `build_filesystem_provider(...)` (`filesystem`),
     - `HermesMemoryProvider(...)` (`hermes`).
   - `build_provider_memory_service_from_env` always returns `ProviderMemoryService(...)` (`factory.py:44-129`).
   - `build_filesystem_provider` also returns `ProviderMemoryService(...)` (`filesystem_storage/bundle.py:141-175`).

3. **Provider service composition**
   - `ProviderMemoryService.__init__` optionally composes runtime if bootstrap capability and verified material are present (`service.py:464-487`).
   - `BuiltInLocalHostSemanticIngestionCapability.build_semantic_ingestion_runtime` creates `SemanticWriterAdmissionStore`, `SemanticIngestionAtomicStore`, source-normalization host bundle, and bootstrap graph host bundle (`capability.py:268-367`) and returns `build_authorized_local_semantic_runtime(...)` (`capability.py:368-421`).

4. **Ingress and semantic policy gate**
   - `ProviderMemoryService.ingest` routes through `_ingest_event` → `_preflight_ingress` → `_run_semantic_ingestion` (`service.py:760-770`, `service.py:786-793`, `ingestion.py:1073-1109`).
   - `_run_semantic_ingestion` refuses on missing semantic runtime/policy and returns evidence-only outcomes without entering graph execution (`ingestion.py:1090-1109`).

5. **Runtime source graph execution branch**
   - `_run_semantic_ingestion` requires retained normalized result + runtime bundles (`source_normalization_host_bundle` and `bootstrap_graph_host_bundle`), otherwise returns source-only evidence outcomes (`ingestion.py:1170-1181`, `ingestion.py:1192-1197`, `ingestion.py:1266-1283`, `ingestion.py:1460-1475`).
   - Graph execution call is `graph_bundle.execute(request=BootstrapGraphAuthorityRequestV3(...))` in both normal and recovery paths (`ingestion.py:1358-1369`, `ingestion.py:1501-1513`).

6. **Native policy-retention boundary (corrected) + native group request path**
   - `source_normalization_stage._planning_construction_authority_for_operation(... policy_bundle=...)` receives the full `policy_bundle` and passes it as `arbitration_policy_bundle` into `BootstrapNativePlanningConstructionAuthorityV3.create(...)` (`source_normalization_stage.py:89-97`, `source_normalization_stage.py:163-172`).
   - `planning_construction_authority` is then attached to `BootstrapNativeOperationReductionInputV3` (`source_normalization_stage.py:291-323`).
   - Built-in execution consumes `operation_inputs = reduction_reload.authority_member.operation_inputs` (`bootstrap_graph_builtin.py:374-380`, `517`).
   - Compiler targets emit `BootstrapGraphOperationReductionV3` with `native_compilation` and `native_compilation.operation_input` carried through `BootstrapNativeSemanticReducerV3.reduce(...)` (`bootstrap_graph_builtin.py:220-233`, `bootstrap_native_reducer.py:24-37`, `:79-87`, `:127-138`, `:219-230`).
   - `BootstrapGraphArtifactAssemblerV3.group_commit_request` wraps each reduction into `BootstrapGraphOperationStoreMaterializationInputV3(... reduction=reduction, ...)` and appends to `ordered_operation_inputs` (`bootstrap_graph_artifact_assembler.py:1457-1467`, `:1468-1485`).
   - Runtime commit persists `BootstrapGraphGroupCommitRequestV3` with those reductions in `commit_or_reload_bootstrap_graph_group_v3` (`atomic_store.py:11409-11417`, `11568-11580`, `11572-11580`).
   - Test-level confirmation: `test_native_policy_retention.py` checks `group_request.ordered_operation_inputs[0].reduction.native_compilation.operation_input == request.operation_input` and `planning_construction_authority == authority` (`test_native_policy_retention.py:36-43`).
   - Result: retained planning authority is preserved through native reduction + group request; it is not dropped at this stage, and there is no claim of direct retention loss inside this runtime path.

## production_entrypoint_bindings (frozen boundary)

| requirement/behavior | production trigger | composition root | authority-bearing callsite + exact arguments | validation | durable outcome | production caller count | fallback/bypass | evidence path |
| --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| Canonical capture ingress sync | `capture_cell` -> direct service path | `CanonicalEvidenceCaptureSupervisor._build_root` | `build_provider_memory_service_from_env(verified_production_host_authority=authority)` | `build_verified_production_host_authority(...)` must succeed | Canonical service sync attempt + ingestion terminal + policy gates | 3 (callsites in `_build_root` factory branch + hermes direct branch + filesystem branch) | authority verification failure or unsupported root throws before service | `production_capture.py:107-180`, `factory.py:44-129`, `bundle.py:141-175`, `hermes_provider.py:83-90` |
| Hermes adapter ingress alias | `HermesMemoryProvider.sync_event(...)` | `HermesMemoryProvider.__init__` and delegate target | internal `_service = build_provider_memory_service_from_env(...)` or `build_filesystem_provider(...)` | same production authority/ingress validation paths as capture root | Hermes `sync_event` persistence + semantic outcome | 2 direct constructor branches in `HermesMemoryProvider` + 4+ sync call forwards in adapter methods | direct adapter storage choice changes path (`service` vs composed service) | `hermes_provider.py:73-90`, `production_capture.py:116-131`, `hermes_provider.py:293-369` |
| Provider service runtime composition (writer/atomic-store memory plane) | service init with bootstrap capability and verified profile/material | `ProviderMemoryService.__init__` | `host_bootstrap_capability.build_semantic_ingestion_runtime(...)` with `memory_plane`, `bootstrap_profile`, `verified_material` | `build_semantic_ingestion_runtime` raises on auth/profile mismatch; `PreparedSourceRepository` depends on `atomic_store` | canonical runtime fields (`writer_admission`, `_semantic_atomic_store`) and admission/terminal persistence roots | 2 production direct constructor callsites (`factory.py` and `production_capture.py`; additional non-production in benchmark) | fallback to `semantic_runtime=None` if compose fails | `factory.py:110`, `production_capture.py:156`, `capability.py:474-369`, `service.py:474-534`, `ingestion.py:1117-1130` |
| Source-native planning authority construction | normalizer build request from retained source | `_native_reduction_inputs` inside `BootstrapV3SourceNormalizationStage.build_request` | `_planning_construction_authority_for_operation(... policy_bundle=inputs.policy_bundle, ...)` then `planning_construction_authority=...` field on operation input | strict identity checks inside `_planning_construction_authority_for_operation` and `_native_reduction_inputs` | native reduction inputs include planning authority for fact members | 1 | production-authority substitution or unsupported fact member raises | `source_normalization_stage.py:291-323`, `source_normalization_stage.py:163-176`, `source_normalization_stage.py:504-511` |
| Bootstrap graph request execution + commit | normalized source execution + recovery | `_run_semantic_ingestion` | `graph_bundle.execute(request=BootstrapGraphAuthorityRequestV3(...))` where request carries `normalization_replay`, `prepared_source`, `required_outcome_scopes`, `operation_fence_binding`, `operation_lease_binding`, `writer_commit_binding` | recovery/non-recovery branch, authority missing branch, reload/retry branch | terminal outcome (`accepted`/`source_only`) + durable graph terminal/retry persistence | 2 callsites (`_run_semantic_ingestion` normal and reconcile paths) | graph authority unavailable; authority-only branch returns `evidence_only` | `ingestion.py:1270-1325`, `ingestion.py:1446-1515`, `bootstrap_graph_host.py:29-37`, `bootstrap_graph_host.py:57-73` |
| Native group write root (memory-plane transition) | per-group compilation attempt | `BootstrapGraphDependentCoordinatorV3.coordinate()` | `BootstrapGraphArtifactAssemblerV3.group_commit_request(... request=request, attempt=attempt, member=..., authorization=..., operation_reductions=...)` then `self._group_commits.commit_or_reload(request=...)` | attempt/lineage/authority/authority-generation checks in compiler and coordinator | durable group commit record set (`ordered_operation_inputs` with full reductions) and graph/observation generation | 1 caller (`BootstrapGraphDependentCoordinatorV3` loop) | storage conflict or policy substitute returns refresh/retry terminal path | `bootstrap_graph_coordinator.py:552-567`, `bootstrap_graph_artifact_assembler.py:1437-1486`, `bootstrap_graph_coordinator.py:564-580`, `atomic_store.py:11409-11417` |
| Shared observation/public registry API | none in current runtime | not implemented | no production callsite exists | none | none | 0 direct production caller(s) | all paths absent by design state | `readiness.md` + `projection-observation-decision.md` + `engineering-closure/resume.md` |

## Highest-risk branch points

1. **Two `_run_semantic_ingestion` callers with different state assumptions**
   - one from ingest admission and one from recovery reconcile (`ingestion.py:545`, `ingestion.py:744`).
2. **Graph host branch split on retention mode**
   - normal/recovery branch with replay, and authority-replay branch returning persisted terminal/retry (`ingestion.py:1270-1315`, `ingestion.py:1501-1513`).
3. **Graph host request shape boundary**
   - `BootstrapGraphAuthorityRequestV3` excludes planner authority fields by design and only carries replay/prepared source + bindings (`bootstrap_graph_host.py:29-37`, `ingestion.py:1359-1368`, `ingestion.py:1503-1512`).
   - This is a boundary-surface characteristic, not a drop of already-sealed planning authority already present in reduction inputs.

## Unknowns + confidence drops

- **Call graph outside inspected files**: this preflight intentionally excludes non-production fixtures/scenario harnesses outside production modules listed above.
- **Observer surfaces**: this pass only proves absence of runtime public `observe_*` registry callsites in current production modules and references current design/state-gap artifacts.

## Evidence provenance (SHA-256, captured mapping baseline)

Document hashes below are historical mapping inputs. The external candidate
manifest pins this artifact; it does not carry a self hash. Production retention
was subsequently verified by six tests in native-policy-retention/tests-final-compatibility.log.

- `17867bf9916faf3dcc502917ae09811fcc5319e32adad69cac19d653dddde58a` — `docs/work/semantic_ingestion/observation-ledger/readiness.md`
- `8ea79ee94f772bc64e214a9518d47819186417c2168c4a45383fa2fe02639594` — `docs/work/semantic_ingestion/observation-ledger/projection-observation-decision.md`
- `2c9a065bdeee3933465079c05582d6d38e05503c2dc79650634ff2b00a75689a` — `docs/work/semantic_ingestion/engineering-closure/resume.md`
- `0ca159b05501ab6a23a697a2c0ea9075096f347b3fe12d23cc91fb049552002d` — `memorii/memorii/core/semantic_ingestion/source_normalization_stage.py`
- `ca47caa280b5931f85fd62391140ee90de52edbf1dfd9214378abd7b083aef4f` — `memorii/memorii/core/semantic_ingestion/bootstrap_graph_host.py`
- `f0d8abe952d6ef2d1ae9eb74b240529a25509534c39caa24051a950003cf128e` — `memorii/memorii/core/provider/ingestion.py`
- `3d702c0a0d9dbd45fd98db6614f012ef9f54263e774757ae6b8236d6f7d51886` — `memorii/memorii/core/semantic_ingestion/bootstrap_graph_builtin.py`
- `e07dcc7039d47a25d14b1d79e25e09bc33599777b1b939df42fc324c40171a93` — `memorii/memorii/core/semantic_ingestion/bootstrap_graph_artifact_assembler.py`
- `a1a1f2dcdcf616e8701126269f6479c5f5d728225ffde5572a8fdcbeffcfd1f5` — `memorii/memorii/core/semantic_ingestion/bootstrap_graph_coordinator.py`
- `39b334b91db468cfb94a854189b38ae55e22f56aa0a7883b3c2b33ad59432167` — `memorii/tests/unit/core/semantic_ingestion/test_native_policy_retention.py`
- `afc8be0cff4a9845db0de373d3f96cf1bf289758e7753c3aab1cd01504894261` — `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_observation_retention.py`

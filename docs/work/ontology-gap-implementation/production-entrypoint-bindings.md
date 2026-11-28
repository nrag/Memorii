# Ontology production entrypoint bindings

Read-only preflight at `80fc585228cf0b7d3e59067012f3d6998f34bbf8`.
The fast code mapper traced the two package factory surfaces and the service
and store seams. The coordinator owns the plan. This map grants no
implementation or design approval. Paths in the table are relative to
`memorii/memorii/`; line references are at the pinned baseline.

| Requirements and trigger | Current callsite and authority | Canonical owner and outcome | Caller count and planned proof |
| --- | --- | --- | --- |
| OCI-01–04, OLE-08/09/10/14, discover and recall | Packaged bridge `integrations/hermes_memory_provider.py:169,179,224,229` and generic `integrations/authenticated_source.py:141,146`; factory `integrations/hermes_factory.py:428,974` and `integrations/catalog_read_binding.py:80,95` supply the verified installation, opt-in and live session. | `core/provider/service.py:1710,1722` → `catalog_read_workflow.py:170,219,232` binds the selected snapshot and release. Existing exact name and subject/digest inputs are reached. Hermes completed-turn listing can pin a turn. | Two exact read surfaces and zero new discovery tool callers. Prove both bindings list and invoke the discover/recall workflow without turn pinning or a write grant. |
| OLE-02/04/05/06/07/10/13, owner decision and learned read | `integrations/hermes_factory.py:831,903,905,914,919` wires runtime recovery and owner callbacks. Current callbacks capture identities, then activation/rollback refresh authority after selection. | `core/semantic_ingestion/learned_relation.py:691,711,722,761,787,818` owns proposal, pointer, status and recovery. Exact read fails closed on the learned version in `core/provider/catalog_read_workflow.py:219`; the old version lacks the exact parent field. | Two approve/activate/status surfaces and one select-prior surface. Zero installed reject or evidence-detail ports, and zero learned exact-read paths. Prove current grants before mutations, status after refresh failure and both installed reads after reopen. |
| OLE-01/02/07/08/11/12/14, authenticate and observe | Hermes sync `integrations/hermes_memory_provider.py:343` → `core/semantic_ingestion/hermes_completed_turn_runtime.py:1765`; generic `integrations/authenticated_source.py:59,114` → shared provider with retained source and grants. `integrations/hermes_factory.py:153,605` supplies the no-key mentors observer. | `core/provider/ingestion.py:947,990,1095,2493` and `core/provider/service.py:806,842` retain and resume. `coverage_observer.py:159,293` validates spans and capability result. `coverage_recurrence.py:322,399` owns scope/signature grouping and CAS counts. | Two admitted adapter paths, one installed narrow observer binding, zero broader binding. Prove persistence, 3/2 eligibility, duplicate exclusion, and authorized pending/status. |
| OLE-01–06, OLE-08/11–14, candidate, evaluator and replay | `integrations/hermes_factory.py:844,864,892` composes recurrence and evaluation using retained evidence and owner scope. `:810` wires the ordinary replay writer. | `core/semantic_ingestion/learned_relation.py:129,223,530,857,1126,1188` binds the literal declaration, frozen paired evaluation and replay. `:1191–1204` returns existing proposals before dispatch. | One shared installed recurrence-to-candidate path for mentors. Zero generic relation and manual authoring callers. Prove both paths reach the same validator and exact-parent evaluator, and selection and writer remain separate. |
| OLE-01–06, OLE-08/11/13, create and use subtype | `core/semantic_ingestion/coverage_recurrence.py:98` supplies the typed gap. `default_catalog_corpus.py:75` and `default_catalog_runtime.py:29` describe packaged type authority. | `learned_relation.py:223` admits only relation addition today. The planned subtype path needs approved binding of the type registry through validation, selection, replay, history and protected read. | Zero learned subtype production lifecycle callers. Prove actual owner and normal writer/reader calls with a subtype-only witness. |

Search anchors for refreshing this preflight at the next runtime base:

```sh
git grep -n -E 'inspect_catalog_relation|diagnose_structured_recall|get_tool_schemas|handle_tool_call' HEAD -- memorii/memorii
git grep -n -E 'record_evaluation|approve_candidate|activate_candidate|select_prior_version|admit_recurrence' HEAD -- memorii/memorii
git grep -n -E 'OntologyObserverCapability|CoverageObserverRunner|EntityTypeGapSignature|add_entity_type' HEAD -- memorii/memorii
```

Counts describe distinct bound surfaces or installed capability paths,
including externally invoked factory entrypoints. Refresh exact callsites,
arguments, and caller counts for every changed trigger, and attach runtime
path proof to its milestone rather than counting test construction as a
production caller.

## Learned-read checkpoint at `e49b6445`

| Trigger | Verified owner chain | Baseline gap and discriminator |
| --- | --- | --- |
| Hermes browse, exact inspect, and diagnose | `hermes_memory_provider.py` dispatches registered public tool names to the first-party factory's `CatalogReadBinding`. The binding derives authenticated local installation, principal, agent, session, fact scope and current catalog visibility references. | Stock opt-in supplies base visibility. The learned witness uses explicit trusted host configuration with the exact child reference. |
| Authenticated-source browse, exact inspect, and diagnose | `build_local_level2_authenticated_source_runtime` forwards the same read binding to `AuthenticatedSourceRuntime.handle_read_tool_call`. The source envelope carries no read or catalog-owner grant. | Same verified protected workflow and exact grant check through the independent adapter after reopen. |
| Selected closure and fact release | `ProviderMemoryService` delegates to `CatalogReadWorkflow`. Metadata uses the selected pointer, immutable version and attempt from the linearized metadata lookup. Diagnosis adds the authorized semantic snapshot and release check. | Both callers reached a deliberate learned-catalog denial. Existing typed legacy recall does not establish the exact read workflow. Positive proof requires an exact immutable packaged parent and a vetted projection of the closed `mentors` declaration. Negative proof preserves denial without that parent or a valid grant. |
| Installed selection and durable parent proof | The first-party factory binds owner activation to `LearnedRelationRuntime.activate_candidate`. Retained observation evidence already carries the selected version identity from provider ingestion or completed-turn observation. | First activation had no persisted exact parent version. The new installed write must verify that parent and condition selection on its current authority. Legacy rows must retain their recorded meaning. |

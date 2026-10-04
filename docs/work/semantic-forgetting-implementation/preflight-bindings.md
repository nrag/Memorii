# Preflight Bindings — Semantic Forgetting Implementation

- Frozen mapping artifact (read-only Spark code-mapper output), produced
  2026-10-03 at base 4780db61, before the first writer edit.
- Consumed by milestone reviewers; refresh only when a remediation changes
  a mapped trigger, owner, authority, or persistence boundary.

## Binding ledger (summary; full detail in the mapper report preserved below)

| Requirement | Canonical trigger and composition root | Exact callsite and authority | Owner chain | Caller count (production) | Status |
| --- | --- | --- | --- | --- | --- |
| FGT-R7 enforcement publication | administration-side governance entry mirroring the native group commit (`commit_or_reload_bootstrap_graph_group_v3`) | `SemanticGraphDelta` via model_construct+model_validate (atomic_store.py:16571-16590); `build_semantic_event_batch` (event_replay.py:946-1018, 4 prod callsites); CAS RecordDigestPrecondition on `_semantic_replay_state_id()` (atomic_store.py:16681-16699) | governance entry → prepare (freeze guard :12354, writers.require_current :12356, OperationFenceBinding + SemanticWriterCommitBinding) → fold → CAS → memory-plane publication (`publish_memory_plane_batch`, 2 prod callers in persistence/factory.py:115,132) | builder 4; entry 0 (new) | planned |
| FGT-R2 view injection | factory `build_provider_memory_service_from_env` + `open_managed_partition` (persistence/factory.py:312-321) + sidecar/binding composition roots | constructor seams: retrieval_runtime (retrieval_runtime.py:60-76; scoped_context internal :335), ScopedContextAssembler (provider/service.py:1088), structured facts (:1689-1693), observation host (graph_observation_host.py:58-97 → factory :162), entity matching (:1892-1898), lineage reader (factory :124-141), memory-plane service (service.py:153-167) | view owner = storage administration service; refreshed on journal write/boot/restore | varies; see gaps 2-3, 9 | planned |
| FGT-R4 marking | HarnessStateService.read_state (harness_state/service.py:78-230); resume via build_resume_envelope (runtime_checkpoint.py:235-302) | sidecar.py:141 + binding.py:52 compose read_state; resume envelope is test-only today (gap 8) | repository reads → envelope | read_state 2 roots | planned |
| FGT-R5/R6 plan/apply | GovernanceOperator (operator_governance.py:100-198) | CLI dispatch tools/runtime_operator.py (plan-only; apply has zero dispatch — must be added, gap 4) | capability → barrier → journal → control | plan 1 CLI; apply 0 | planned |
| FGT-R9 epoch | service.py publish paths + `_finalize_publication` (:790-798, no control write today) + `resolve_pending_publication` (:629-679) + `_resume_or_conflict` boot hook (:236-270, via initialize) | control.py write_control_state (:265-283, 6 callers) / write_publication_state (:286-298, 1 caller) | control DB single-transaction precedent initialize_installation (control.py:232-255) | mapped | planned |
| FGT-R3 reader ledger | lifecycle enum readers enumerated (§6 of report) | retrieval_runtime.py:85 denylist, :113 conversion; record_projection.py:216-223 exhaustive map; retrieval.py:285,296-300,320; structured_fact_read.py:588,602,610,637; entity_resolution.py:51 | enum owners models.py:104-110,164-184 | enumerated | planned |
| FGT-R12 authority chain | memorii/scripts/generate_observation_registry_publication.py (argless generate(); reads prior decoder-source-manifest selections; writes grammar/registry/roles + both manifests) | manual candidate repin last (gap 7) | author_typed_value_publication_package | script 0 callers (manual) | planned |

## Mapping gaps (frozen caveats)

1. `query_records` is a zero-caller endpoint (composed-but-unused); §6.8
   extends it via the view at the store/service seam.
2. Graph observation runtime has no production composer (factory param
   default None → non-disclosing denial); observation rows enforced at the
   injected runtime.
3. `MemoryEvolutionService` has no production constructor caller and
   `_memory_evolution_service` is pinned None by factory tests
   (test_provider_factory.py:15, test_filesystem_storage_bundle.py:105) —
   the evolution channel is inert in factory builds; view injection lands
   at reachable roots (scoped-context internal runtime, structured facts,
   prefetch assembly) and the factory composes the real view everywhere it
   builds serving surfaces. Empty-view default is semantically "nothing
   revoked" (design §6.7); the factory must never omit the real view.
4. `apply_forget`/`apply_erasure`/`apply_retention` have zero production
   dispatch — CLI apply surface is part of M4.
5. No in-package production caller of `StorageAdministrationService.initialize()`;
   boot hook reachability to be verified via the operator/bootstrap path
   during M4.
6. Generation script invocation is argless `generate()` (module `__main__`);
   no recorded prior command line in docs/work.
7. Candidate repin is manual (recompute changed-file sha256 pins; update
   candidate.json + candidate.sha256 sidecar; repin LAST).
8. `build_resume_envelope` is test-only; M5 points marking at the actual
   serving surfaces (read_state + checkpoint) and keeps the resume marking
   for the resume path when wired.
9. `.get_record`/`.list_records` counts (372/76) span serving AND internal
   integrity readers — per-root discrimination required; internal readers
   stay unfiltered (design §6.7).
10. Exclude the stale `memorii/build/lib` tree from symbol greps.

## Preserved mapper report

The full mapper report (behaviors 1-8 with file:line for every claim,
caller counts, and test inventory) was delivered by the mapper agent on
2026-10-03 and is summarized above; its behavioral content is fully
captured by the ledger and gaps. Test inventory highlights: event replay
all-12-kinds test (test_event_replay.py:2043) extends to the new kind;
codec totality (test_identity_lineage_prerequisites.py:177); operator
forget cycle (test_storage_administration_operator.py:355) updates
deliberately with the M4 plan-contract change; retrieval lifecycle gates
(test_memory_evolution_retrieval.py:556, 995); checkpoint revalidation
(test_runtime_resume_checkpoint.py:240); query parity
(test_memory_plane_query_parity.py).

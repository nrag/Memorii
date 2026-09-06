# Semantic Ingestion M3.1 And M4 Resume Packet

- Active parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Active completion WorkPlan: `docs/work/semantic_ingestion/m4-closure-2026-09-04/implementation.plan.md`
- Active milestone packets: `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`; `docs/work/semantic_ingestion/milestones/m4-event-history.plan.md`
- Active linked debugging WorkPlan: `docs/work/semantic_ingestion/conflict-authority-proof-failures-2026-08-04/debug.plan.md` (sole detailed owner of the two replan defects)
- Approved bridge design WorkPlan: `docs/work/semantic_ingestion/bootstrap-v3-source-progress-bridge-2026-09-04/design.plan.md`
- Active bridge implementation WorkPlan: `docs/work/semantic_ingestion/bootstrap-v3-source-progress-bridge-2026-09-04/implementation.plan.md`
- Status: M3.1 local execution and acceptance evidence and the corrected M4
  415-case family are green; only immutable candidate, hosted, and independent-
  review closure remains
- Coordinator: Codex main thread
- Last updated: 2026-09-05
- Current reviewed HEAD: `821b0bc7fd47ca0c55a18ccebb4b1628fa13689b`
- Tree state at plan creation: clean

## Objective

Complete M3.1 and M4 at one immutable revision after correcting replan lineage
and error classification, finishing replay/history proof, revalidating the
shared M3.1 transaction path, and obtaining revision-bound local, hosted, and
independent review evidence.

## Current State

- M3.1 implementation remains present, but its v82 identity is not
  reproducible from its declared base and cannot support final closure.
- M4 conflict-attention composition and replay/history passed 414 of 415 tests
  on the first final-tree run. The only failure was a stale architecture hash
  in the equal-version decision artifact; after correction, the complete
  415-case family passes under `-W error` in 2142.04s.
- Native V3 progress publication, exact reload, and bounded group-CAS
  related-conflict successor are implemented. The direct two-ingestion race
  retains the original fence and creates the successor only for the dedicated
  typed related-conflict signal. The related-conflict pair passes in 127.84s;
  an identical two-ingestion race separately proves two CAS attempts and no
  false successor after an unrelated/global revision change.
- M3.1 now has eight validated exact-selector receipts: 29 cases for each of
  direct, factory, filesystem, and Hermes roots on memory and independent JSONL
  backends (232 selected cases total). Progress/recovery is 18/18, the selector
  contract is 11/11, and the complete acceptance file is 200/200 under
  warnings-as-errors.
- Clean candidate freeze, exact-SHA hosted execution, and final independent
  closure review remain pending after the active M4 rerun.

## Governing Decisions

- Preserve the original delivery identity and append plan/attempt lineage.
- Commit V3 related-conflict resolution at the existing group-CAS boundary.
- Reuse unaffected groups byte-for-byte and recompile only the stale subset.
- Preserve historical candidate records as superseded audit evidence.
- Freeze one final candidate and close both milestones against it.

## Operation Order

1. Close the two replan defects through the linked debugging WorkPlan.
2. Reconcile conflict-attention composition against the corrected behavior.
3. Complete byte-equivalent replay/history and adversarial proof.
4. Re-run the M3.1 four-root transaction/recovery/lineage matrix.
5. Freeze one clean identity, obtain exact-SHA hosted checks and three-role
   review, then record both closure decisions.

Full acceptance matrices, gates, and stop rules are in the active completion
WorkPlan. Historical evidence remains under the milestone packets and archive.

## Exact Next Action

Push the frozen exact candidate and run hosted checks plus the required
whole-candidate specification, correctness, and test reviews; do not add
product scope.

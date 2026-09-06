# Semantic Ingestion M3.1 And M4 Resume Packet

- Active parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Active completion WorkPlan: `docs/work/semantic_ingestion/m4-closure-2026-09-04/implementation.plan.md`
- Active milestone packets: `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`; `docs/work/semantic_ingestion/milestones/m4-event-history.plan.md`
- Active linked debugging WorkPlan: `docs/work/semantic_ingestion/conflict-authority-proof-failures-2026-08-04/debug.plan.md` (sole detailed owner of the two replan defects)
- Approved bridge design WorkPlan: `docs/work/semantic_ingestion/bootstrap-v3-source-progress-bridge-2026-09-04/design.plan.md`
- Active bridge implementation WorkPlan: `docs/work/semantic_ingestion/bootstrap-v3-source-progress-bridge-2026-09-04/implementation.plan.md`
- Status: active bounded correction after candidate `04a7303` review found a
  missing persisted read-set/token join and one JSONL proof assertion
- Coordinator: Codex main thread
- Last updated: 2026-09-06
- Superseded candidate: `48c6dc5ab3438684b6476b0919a17774c8bdc92b`
- Superseded candidate: `e13df701bf508955115637280125e25be2ca6916`
- Superseded candidate: `04a7303c354527280a6490e2ebac0cac2b7a551e`
- Current tree state: bounded correction pending replacement freeze

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
  typed related-conflict signal. Every accepted semantic winner advances a
  globally sealed partition and therefore takes that successor path; an
  execution-domain write outside the read set takes one CAS without retry.
- M3.1 now has eight validated exact-selector receipts: 29 cases for each of
  direct, factory, filesystem, and Hermes roots on memory and independent JSONL
  backends (232 selected cases total). Progress/recovery is 18/18, the selector
  contract is 11/11, and the complete acceptance file is 200/200 under
  warnings-as-errors.
- Replacement candidate freeze, exact-SHA hosted execution, and final
  independent closure review remain pending after the active bounded rerun.
- Review of `48c6dc5` found four bounded closure defects. The replacement tree
  now preserves exact replay-error identity, performs fresh target-aware
  preflight before one unrelated late-CAS retry, proves the real public
  clarification race in memory and independently reopened JSONL, and removes
  selector outcome counters that were never measured.
- The corrected public race passes both backends (`2 passed in 232.77s`) and
  the selector ownership contract passes (`11 passed in 6.37s`). Canonical
  source/binding evidence is repinned under candidate-lock SHA-256
  `95729d40afe69f0e58a1ebc97d53445e7c8ed3c95437c8109f34db4542e4c422`.
- Positive external production activation remains `implemented_unvalidated`
  and is not a closure blocker here because M5 activation and agent-system
  quality are expressly excluded from this M3.1/M4 operation.
- The selector metadata correction changed the manifest digest, so the prior
  eight local receipts are historical. Exact-SHA hosted CI must regenerate and
  aggregate all eight replacement root/backend receipts before closure.
- Candidate `04a7303` review correction is locally green: the physical-CAS
  disjoint accepted winner takes one typed successor in memory and independent
  JSONL, with both backends asserting disjoint materialized record intents;
  the persisted member now joins the full read set to its token and ledger
  fields and rejects a digest-recomputed cross-snapshot token. The public
  clarification race executes/reopens across two
  interpreters with byte-identical complete authority; acceptance is 200/200,
  projection/history plus integration is 97/97, progress/recovery is 18/18,
  four normal roots are 4/4, and configured Pyright/Ruff/compile/canonical-
  evidence checks pass. Candidate-lock SHA-256 is
  `6952929ab47bdc219e88434faeaef66605c7814e1fc6c0c63f0eb2fe78b11b10`.
- The stable post-review authority rerun passes all 309 CTV/workflow/replay
  tamper tests, all four normal roots, all eight outside-read-set root/backend
  cases, the memory/JSONL persisted-member rejection, and the canonical
  evidence adversarial self-test.

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

Reconcile and pin the active packets, freeze and push the shared M3.1/M4 candidate,
then obtain exact-SHA hosted execution and clean
independent specification, correctness, and test review.

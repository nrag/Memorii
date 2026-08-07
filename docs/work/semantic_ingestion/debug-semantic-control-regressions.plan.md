# Semantic Control Admission Regressions

- Work ID: semantic_control_admission_regressions
- Work type: debugging
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-03
- Last updated: 2026-08-03
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/testing.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `docs/design/event_model.md`; `docs/IMPLEMENTATION_RULES.md`; current M4 semantic writer admission and clarification implementation
- Expected outputs: classified test-vs-product causes, invariant-level fixes or test migration, family-complete focused proof, and independent closure review

## Objective

Restore the three deterministic semantic-provider nodes exposed by the M4
timing run without weakening governed-write admission: direct corruption
injection must use the canonical privileged test authority, and rejected or
insufficient clarification outcomes must commit exactly the required atomic
control closure.

## Completion Contract

Complete only when each exact reproducer is classified, before/after causal
evidence is recorded, the full clarification terminal family and corruption-
recovery sibling family pass, governed-write validation remains fail closed,
and targeted specification, correctness, and test review has no remaining
required finding.

## Scope

Included: the three failing provider-composition nodes, semantic control-record
derivation/admission, clarification rejected/insufficient transaction closure,
and privileged corruption-recovery test injection.

Excluded: CI selectors/timings/topology, unrelated semantic outcomes, weakened
writer admission, and broad product redesign. Testing WorkPlan timing remains
paused until this debugging operation closes.

## Incident Or Symptom

The live 566-node M4 timing run passed 169 nodes before three deterministic
failures in `test_semantic_provider_composition.py`:

- direct filesystem/Hermes corruption recovery is rejected as an unauthorized
  governed semantic write;
- rejected clarification fails with `SemanticWriterAdmissionError` because the
  atomic group lacks a control record;
- insufficient clarification fails with the same control-record error.

## Hypothesis Ledger

| ID | Hypothesis | Discriminating experiment | Status |
| -- | ---------- | ------------------------- | ------ |
| H1 | corruption test uses a stale direct injection that correctly fails new admission | rerun exact node and compare with canonical privileged corruption helper | confirmed; test migrated to backend rewrite |
| H2 | rejected/insufficient clarification terminal groups omit the control carrier during persistence derivation | inspect accepted vs rejected/insufficient group members and exact admission classifier | disproved; two-record closure is intentional |
| H3 | writer admission lacks an exact classifier for the valid no-projection transaction/receipt closure | compare accepted and nonaccepting member sets; mutate every binding family | confirmed and corrected |
| H4 | accepted clarification assumes projection history already exists | run accepted closure from genesis and compare committed-group publication path | confirmed; genesis guard mirrored |
| H5 | clean recovery can validate retained clarification authority without reading corrupted live primary batches | isolate ordinary-plus-clarification recovery on fresh storage | disproved; separate recovery-verification defect found |

## Reproduction Contract

Run each exact failing node independently from `memorii/` with `PYTHONPATH=.`
and `-p no:cacheprovider`; record traceback, group members, and zero/partial
effects. Do not rerun the full timing suite until the causal family is green.

## Delegation And Cost Ledger

| Phase | Bounded task | Role and model tier | Writer or read-only | Output | Status |
| ----- | ------------ | ------------------- | ------------------- | ------ | ------ |
| reproduce/map | isolate three traces and member/classifier differences | error-detective/code-mapper, Spark-class | read-only | causal signatures | complete |
| fix | apply one invariant-level product correction and/or canonical test migration | worker, Terra-class | sole writer | focused green family | complete |
| review | challenge cause and proof | spec/correctness/test reviewers, Terra-class | read-only | classified closure | complete through linked recovery review |

## Evidence Log

- Interrupted timing run: 169 passed before the known failures; partial timing
  output is invalid and will not be merged.
- Before correction, the exact provider composition nodes rejected the direct
  corruption injection and the rejected/insufficient two-record closure.
- After correction, the exact three reproducers pass: 3 passed in 62.18 seconds.
- Exact classifier proof: valid rejected and insufficient pairs plus six
  missing/duplicate/foreign-kind/operation/prefix/binding mutations, 8 passed.
- Accepted/rejected/insufficient and zero-effect family: 5 passed in 75.39
  seconds after the projection-history genesis guard.
- Fresh recovery isolation: ordinary-plus-clarification filesystem recovery
  fails because clarification-pair verification re-enters the deliberately
  corrupted live primary event batch; 1 failed in 31.92 seconds. This is a
  separate recovery-verification boundary, not temp-path contamination.
- Ruff passes all four touched Python files. Pyright with the repository venv
  passes with zero errors and zero warnings.

## Root Cause

The writer policy recognized context-only clarification and the accepted
projection/event closure, but not the deliberate rejected/insufficient pair of
one transaction and one processing receipt. The pair therefore reached the
generic preplanning-control requirement and failed. The exact classifier now
validates kinds, canonical IDs and prefixes, recomputed transaction digest,
operation, transaction, conflict, proposal, policy, result, outcome, and
available source binding. It admits no generic two-record family.

The corruption reproducer attempted to replace governed bytes through the
public API without authorization. Admission correctly blocked it. The test now
uses the canonical test-only JSONL snapshot rewrite pattern and does not mint
product authorization for corrupt bytes.

Accepted clarification also omitted the genesis condition already present in
normal committed-group publication. It attempted to read active projection
authority before the first publication. The clarification path now consults
active views and policies only when replay bindings exist; it synthesizes no
authority.

## Next Action

Resume the linked testing WorkPlan's invalidated 566-node timing capture on the
closed implementation and recovery revision.

## Blockers And Limits

Budget: three discriminating experiments, one coherent fix batch, and one
targeted remediation round. No external blocker.

## Outcome And Retrospective

Complete. The exact three reproducers, classifier mutation family, and complete
accepted/rejected/insufficient clarification family pass. The corruption test
now uses the canonical test-only persisted-byte rewrite rather than weakening
product admission. Rejected/insufficient clarification uses an exact bound
transaction/receipt atomic family, and accepted clarification handles genesis
without synthetic projection authority. The separately exposed recovery defect
is closed in the linked debugging WorkPlan. Independent review reports no
remaining required finding.

- `remaining_validated_p1_p2: []`
- `remaining_blocks_approval: []`
- `remaining_changes_required: []`

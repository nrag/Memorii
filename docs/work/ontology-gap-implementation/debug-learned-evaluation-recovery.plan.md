# Recover interrupted learned catalog evaluation

- Work ID: learned-evaluation-recovery
- Work type: debugging
- Delivery fidelity: Level 2 for installed agent-local ontology owners
- Status: active
- Coordinator: Codex
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: [learned catalog review and recall](milestones/learned-catalog-review-and-recall.plan.md)
- Related WorkPlans: [original capability audit](../learned-ontology/ontology-capability-audit.md)
- Canonical inputs: [ontology lifecycle](../../design/learned_ontology.md) sections 6–8, `LearnedRelationRuntime`, `LearnedRelationCandidateService`
- Expected outputs: trustworthy persisted proposal lifecycle and bounded evaluation recovery, with durable restart and concurrency evidence

## Reproduction and causal boundaries

The linked audit interrupted `record_evaluation` after publishing
`evaluating`. The next proposal load returned unavailable because the
runtime persisted a state missing from the closed decoder. The governing
lifecycle explicitly admits `evaluating`. Separately, `_replace_proposal`
fetches the latest persisted bytes for CAS and uses their digest without
checking that those bytes still encode the caller's old transition input.
If a concurrent operation wins before that read, the second operation may
overwrite the winning transition.

The first slice makes the already specified state readable and derives CAS
from the actual matched predecessor. This does not grant approval or
activate a catalog. Next, close retry and restart: establish exact attempt
identity before running evaluation, resume only the same parent and pinned
binding/corpus/budget, and finalize a persisted passing evaluation without
running the evaluator again. A legacy interrupted attempt without enough
identity remains inert and visible until the same binding can be proved.
The governing retry decision forbids substituting a new binding.

## Verification

- Publish `evaluating` through the real transition, interrupt publication,
  reopen a durable test store and decode the proposal as that inert state.
- Use two stale-transition interleavings: a predecessor change already
  visible when the CAS prepares, and a change after reading but before
  CAS. Observe rejection and the exact winning state retained.
- Keep the existing owner, paired-evaluation, selection, rollback and
  replay unit cases. No source, fact, evaluation policy, or provider
  changes belong in the predecessor/decoder correction.
- The separate retry slice requires an unavailable provider/binding,
  valid retry, binding mismatch, evaluated-before-decision restart, and
  terminal/approved proposal evidence. Then run the applicable hosted gates.

## Decoder and predecessor correction

Against clean `52948673`, the interruption test failed with
`proposal is unavailable` and the early-winning transition was
overwritten. The late-winning transition already failed the digest CAS.
The patched archive passed all 35 learned relation, catalog read, coverage
observer, and recurrence tests, plus scoped Ruff. A focused independent
review reproduced the baseline failures and passed the corrected slice.

The parallel learned version-key refactor in the same file is compatible.
Only the two recovery hunks and their tests are included in this checkpoint.
The version-key refactor remains with parallel work. The checkpoint makes
an interrupted proposal readable and inert and closes both tested stale
writer windows. Retry and version-aware owner controls remain open.

## Interrupted result publication

The production candidate service already runs the evaluator before calling
`record_evaluation`. Close the crash window between that call's durable
transitions without assuming an unrecorded result exists. Persist the
complete typed evaluation result in the same CAS that publishes
`evaluating`. The existing evaluation digest covers the binding, corpus,
budget and outcomes. This is the existing v1 evaluation field and does not
alter proposal identity or introduce a new wire field.

The scope-authorized startup recovery owner can finalize only that
persisted result through the existing state graph. A passing result passes
through `evaluated` to `awaiting_decision`. A completed failing result
ends rejected and an unavailable result remains inert. Recovery neither
reruns evaluation nor approves, activates or replays a proposal. Same-result
retry can finish a partially published transition. An altered result cannot
replace one already durable.

Legacy `evaluating` rows without a stored result remain readable and inert.
An interrupted executor before result publication has no durable result and
is not part of this step. Evaluator retry and its pre-execution binding,
source and exact-parent proof remain a separate slice.

The initial result-publication fix reproduced an additional startup race.
Two runtimes completing the same result could leave one startup returning a
proposal lifecycle conflict before selection recovery. The final patch
catches only the typed proposal-CAS conflict and rereads the durable
winner. It accepts only full proposal/result equality apart from lifecycle,
at the expected state or a legal later state. An altered result, evidence,
or incompatible state remains a conflict. The independent reviewer
reproduced both finalization windows, then passed the remediation and nine
focused interference tests.

The clean published base failed ten selected new publication regressions.
On the clean patched archive, 55 learned-relation, catalog-read, observer,
and recurrence tests passed with warnings as errors. Scoped Ruff and full
Pyright passed. The JSONL tests exercise restart before and after durable
publication, repeated recurrence, both concurrent finalization CAS
boundaries, identical first-publish retries, changed evidence or results,
and inert unavailable/veto/legacy outcomes. These are local tests.

The parallel version-key and metadata-read work remains outside these
commits. The durable-result publication slice is locally verified.

On clean pushed `74e70d06`, Python 3.12.16 ran the two targeted installed
Hermes bridge witnesses with warnings as errors. The no-key isolated
paired evaluator and learned `mentors` submission paths both passed
in 141.96 seconds. These results exercise installed factories. They do
not show that an unrecorded evaluator execution can resume.

## Next action

Review the exact-parent and evaluator-binding admission for retries of
unpublished work alongside the pending owner and learned-read design.

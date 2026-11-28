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

## Next action

Freeze a binding-pinned evaluation retry and installed recovery design.

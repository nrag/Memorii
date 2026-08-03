---
name: implement-design
description: Implement an approved Memorii design through readiness checks, bounded vertical milestones, evidence-maturity tracking, deterministic verification, family-complete independent review, and convergent remediation.
---

# Implement A Memorii Design

Read:

- root `AGENTS.md`
- `.agents/PLANS.md`
- the active implementation WorkPlan
- the frozen approved design baseline
- governing documents selected through the knowledge router
- nearby production code, tests, tooling, and CI

Create or resume a WorkPlan whose work type is `implementation`.

The main thread is the coordinator. Use exactly one writer at a time for
overlapping code, tests, documents, prompts, schemas, configuration, migrations,
and generated artifacts.

## Phase 1: Readiness And Baseline

Record:

- repository, base branch, design, schema, registry, and generated-artifact
  baselines
- in-scope requirements, exclusions, deviations, and unresolved questions
- dirty-tree ownership and unrelated user changes
- production composition root and canonical owners
- public, persisted, transaction, lifecycle, prompt, provider, artifact,
  adapter, integration, configuration, and CLI boundaries
- migration, rollout, rollback, compatibility, and observability obligations
- the complete identity ledger from `.agents/PLANS.md`, including existing
  planning-derived sibling names and generated or persisted occurrences
- the changed-surface, authority-chain, gate, and known-failure ledgers from
  `.agents/PLANS.md`, initialized from the live diff and current workflows

Reconstruct requirements independently from the design. Do not rely only on an
existing requirements table.

Track evidence maturity separately:

| State | Meaning |
| --- | --- |
| specified | Design behavior is explicit |
| derivable | Inputs and algorithms are complete |
| implemented | Production or reference path exists |
| locally verified | Exact deterministic checks pass |
| independently reproduced | A separate implementation agrees |
| CI enforced | Required automation executes the check |
| operationally verified | Revision-bound external evidence exists |

Never claim a later state using earlier evidence. A documented command is not
CI enforcement. Two isolated executions of one compiler are not independent
compilation.

Before coding, challenge implementation readiness:

- Is every material semantic choice resolved?
- Are normative and illustrative inputs distinguishable?
- Are parser, schema, projection, alias, inheritance, metadata, duplicate, and
  version boundaries explicit where applicable?
- Are independent implementations defined by prohibited shared inputs and code?
- Can required checks run under the same language and dependency versions as CI?

Stop for a design decision when a material semantic choice remains unresolved.

## Phase 2: Plan Vertical Milestones

Each milestone must identify:

- requirements and observable behavior
- canonical owners and expected files
- contract, schema, persistence, and transaction changes
- compatibility, migration, rollout, and rollback implications
- exact validation commands and toolchain
- evidence maturity delivered
- explicit non-goals and completion criteria
- base/head revision identity for closure evidence

Milestones organize work only. Their number, phase, requirement set, WorkPlan
ID, or review coordinate must not name any output. Resolve filenames, symbols,
schemas, discriminators, tests, fixtures, artifacts, commands, and CI labels
from behavior before assigning the milestone.

Prefer complete behavior through canonical execution paths. Test risky
assumptions early.

## Phase 3: Prepare The Validation Matrix

Before implementation, map each requirement to the strongest practical proof:

- static or schema validation
- unit, property, contract, integration, or end-to-end tests
- process restart, contention, migration, mixed-version, or rollback tests
- benchmark, live evaluation, or operational verification

For every test, state:

- behavior proved
- defect detected
- why the level is appropriate
- observable failure signal

Include the field-aware identity gate and representative planning/evidence-coordinate
mutations for every changed language or structured surface. Use exact typed
exceptions for traceability metadata and shipped migration identities; never a
whole-file or directory exemption.

For parsers, validators, registries, and generated authority, create an
equivalence-class matrix covering direct, aliased, quoted, nested, inherited,
ordered, duplicate, fast-path, and normal-path forms where applicable.

Run `test_reviewer` on the matrix before coding high-risk behavior.

For substantial test additions, suite reorganization, stale-test retirement,
or CI gate changes, use `$design-tests` with a linked testing WorkPlan. Small
feature-local tests remain in this implementation WorkPlan.

Before adding tests, inventory the current owners and measured runtime. Follow
the complete identity contract in `.agents/PLANS.md`; requirement and evidence
IDs are prohibited executable names just like milestones, phases, review
rounds, and task IDs. Keep unit tests isolated and fast. Place packaging,
subprocess, large-artifact, restart, migration, and exhaustive matrix coverage
in explicit slower tiers.

BVT and PR-fast gates must remain small representative samples. Preserve
family-complete coverage in dedicated parallel gates rather than deleting or
weakening tests to satisfy the fast-gate budget.

## Phase 4: Implement One Milestone

Spawn exactly one worker for overlapping changes. Require the worker to:

1. inspect existing contracts and helpers before adding new ones
2. change canonical types and contracts first when required
3. implement through canonical execution paths
4. preserve validation, provenance, lifecycle, transaction, and security stages
5. keep adapters, integrations, and CLI modules thin
6. add happy, adversarial, boundary, and failure validation with the behavior
7. update current-state documentation
8. preserve unrelated changes
9. run focused checks using the declared toolchain
10. report requirements, files, decisions, commands, results, and limitations
11. update the identity ledger and reject planning-derived names before they
    enter code, serialized bytes, tests, fixtures, generators, or workflows
12. after each material edit, reconcile the live diff and refresh every
    affected downstream artifact, checksum, workflow pin, validator, and gate

Do not hard-code fixtures, add test-only production branches, bypass canonical
owners, introduce parallel truth, hide invalid state with casts or defaults, or
silently ignore errors.

For independently authored implementations:

- use a different writer when feasible
- prohibit reuse or copying of the reference parser, normalizer, or compiler
- permit only the frozen normative inputs explicitly allowed by the design
- compare complete output bytes and key fail-closed behavior
- record shared libraries and justify why they do not defeat independence

## Phase 5: Verify The Milestone

Run focused checks, then applicable repository gates from the documented
working directory and environment.

Normal local gates from `memorii/` are:

```bash
python -W error -m pytest tests/unit -p no:cacheprovider
python -m ruff check memorii tests
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Follow `docs/development/static_tooling.md` and
`docs/development/benchmark_certification.md` for additional gates.

Record exact command, working directory, interpreter/tool versions, exit status,
relevant output, revision, and tree state. Compilation is not evidence that a
test executed. Local success under a different runtime is not CI parity.

Before calling a milestone complete, read the current GitHub workflow files
directly and inventory every applicable required job, matrix entry, shard,
aggregate dependency, environment variable, working directory, interpreter,
warning mode, and generated or timing artifact. Run the repository
deterministic commands selected by those workflows. Record workflow identities
with the results; a hand-maintained substitute is not equivalence evidence.

Record runner, runtime, dependency-resolution, dirty-tree, skipped-job, and
incomplete-matrix differences as evidence gaps. GitHub-only actions and runner
behavior require actual workflow evidence. Record the CI event, executed
SHA/ref, and run URL; PR head, synthetic merge, and merge-group SHAs are
distinct. Only successful scope-required GitHub and external acceptance gates
establish their corresponding evidence maturity.

Focused success cannot close a milestone after a normative design, registry,
schema, generator, golden, checksum, workflow, or dependency change. Follow
the complete affected authority chain and execute every required local job,
matrix entry, shard, generated-artifact check, and aggregate dependency named
by the gate ledger.

## Phase 6: Coordinator Integrity Check

Inspect the repository directly. Do not trust the worker summary.

Check separately:

- behavioral fidelity
- scope integrity for every changed file
- validation integrity and failure signals
- generality and canonical ownership
- evidence maturity and revision identity
- identity-ledger completeness, exact exception contexts, generated/persisted
  bytes, and the field-aware gate's mutation proof

Ask whether tests can pass while required behavior is absent, whether a special
case hides a missing abstraction, and whether behavior is narrower or broader
than the approved design.

## Phase 7: Independent Review And Remediation

After a coherent milestone, run concurrently:

- `spec_auditor`
- `correctness_reviewer`
- `test_reviewer`

Require reviewers to inspect the complete current state and classify findings
under `AGENTS.md`.

The milestone closure record must explicitly contain
`remaining_validated_p1_p2: []`. A confirmed P1/P2 finding prevents completion.
An unresolved `blocks_approval` or `changes_required` evidence or governance
finding required by the milestone contract also prevents completion, even when
its product priority is `Not applicable`.

Each finding must:

- cite the violated requirement and observable behavior
- identify the affected scenario or repository-contract surface
- for P1/P2 only, identify supported broken product behavior and justify its
  prevalence or importance
- identify the root invariant, not only one example
- enumerate the complete known equivalence class and sibling bypasses
- inspect positive cases that must remain valid
- distinguish missing implementation, weak evidence, missing CI enforcement,
  and unavailable operational evidence
- recommend the smallest architecture-consistent correction and proof

Apply the product-impact remediation gate in `.agents/PLANS.md` before editing.
Only validated `P1` or `P2` implementation defects enter a product-remediation
round. Do not treat approval disposition, a critical-sounding invariant, or a
missing test as proof of product priority.

Classify other findings as:

- a bounded `evidence_action` already required by the validation matrix
- a bounded `contract_conformance_action` for determinate identity or
  repository-contract violations
- `record_only` follow-up
- `external_blocker` requiring a decision rather than another edit

A malformed or hypothetical registry, parser, or validator input is not P1/P2
unless it is supported input or crosses a reachable trust boundary and causes
wrong authorization, persistence, availability, or rejection of valid
supported behavior.

Reconcile all reviewers before editing. Cluster eligible P1/P2 and contract-
conformance findings by root cause and send one coherent batch to the sole
writer.

Use this cadence:

1. full review once per coherent milestone
2. targeted or delta review for bounded remediation
3. another full review only after material contract changes
4. fresh full review for final whole-branch approval

Do not run a fresh whole-scope review after every micro-edit.

When a review finds no new validated P1/P2 defect, do not start another product-
remediation round. Complete required evidence and contract-conformance actions,
then complete the milestone if its predefined evidence passes, record P3 and
nonblocking observations as follow-ups, or stop once with the exact external
blocker. Reviewer silence is not the goal; verified required behavior is.

If two successive findings affect the same parser, validator, lifecycle, or
ownership boundary, stop patching examples. Reconstruct the boundary and
replace special cases with a closed grammar, typed contract, state machine, or
owner rule. If that changes approved semantics, reopen design instead.

## Phase 8: Final Branch Review

When all milestones appear complete:

1. run every deterministic gate
2. rebuild requirement and scope coverage independently
3. inspect the entire branch relative to its base
4. verify every evidence-maturity claim
5. search for stubs, placeholders, skipped tests, ignored errors, silent
   fallbacks, bypasses, duplicated state, hard-coded identifiers, stale docs,
   and planning/evidence coordinates leaked into durable identities
6. verify migration, rollback, compatibility, observability, and failure behavior
7. rerun the field-aware identity gate and independently audit all exceptions
8. run fresh whole-branch reviews with all three reviewers
9. compare the actual base-to-head and working-tree diff with the changed-
   surface ledger and prove every authority-chain node is current
10. record the structured closure evidence required by `.agents/PLANS.md`

Any production, test, fixture, generated-artifact, dependency, or workflow
change after final review invalidates closure. Repeat affected gates and a
fresh whole-branch review at the new revision.

When the branch is a pull request, use `$review-pr` after implementation closure
to evaluate the complete approval unit, GitHub checks, review threads, and
head-SHA identity.

Complete the WorkPlan only when `.agents/PLANS.md` is satisfied. Do not claim
completion from test success or an agent summary alone. Stop as blocked when the
WorkPlan stop conditions apply.

# Behavioral Identity Governance

- Work ID: behavioral-identity-governance-2026-08-02
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-02
- Last updated: 2026-08-02
- Parent WorkPlan: None
- Related WorkPlans: docs/work/semantic_ingestion/behavioral-contract-identities-2026-08-02/design.plan.md
- Canonical inputs: .agents/PLANS.md; .agents/skills/*/SKILL.md; semantic-ingestion naming-debt evidence
- Expected outputs: repository-wide identity-hygiene contract and workflow enforcement in every Memorii skill

## Objective

Make planning and evidence coordinates impossible to mistake for durable product, protocol,
test, fixture, generated-artifact, or CI identities, and make violations a
required pre-closure correction in every long-running workflow.

## Completion Contract

Complete when `.agents/PLANS.md` defines a closed identity taxonomy, every
repository skill applies it at the earliest relevant phase and at closure,
reviewers can require a bounded conformance correction without inventing P1/P2
product impact, and the resulting instructions are internally consistent and
pass repository skill validation.

## Scope

Included: `.agents/PLANS.md` and all six repository `SKILL.md` files. Included
conceptually: mandatory field-aware static enforcement and explicit exception
ledgers. Excluded: completing the separate semantic-ingestion code cleanup and
changing user-level product semantics.

## Constraints And Invariants

Requirement IDs remain stable traceability metadata. Milestones, phases,
WorkPlan IDs, issue IDs, review rounds, and requirement coordinates remain
legal in planning and typed traceability contexts only. Genuine shipped
protocol and migration versions remain legal. Behavioral naming must not erase
provenance or weaken traceability.

## Identity And Coordinate Hygiene

| Surface | Proposed or existing identity | Class | Behavioral owner or protocol meaning | Retain, rename, migrate, or reject | Proof |
| ------- | ----------------------------- | ----- | ------------------------------------ | --------------------------------- | ----- |
| Common WorkPlan section | `Identity And Coordinate Hygiene` | behavioral identity | Repository-wide durable identity policy | retain | `.agents/PLANS.md` |
| Remediation vocabulary | `contract_conformance_action` | behavioral identity | Determinate non-product contract correction | retain | `.agents/PLANS.md` finding contract |
| Static checker | `memorii.tools.identity_hygiene` | behavioral identity | Repository identity-policy enforcement | retain | checker CLI and PR gate |
| Exception authority | `.agents/identity_hygiene_allowlist.json` | behavioral identity | Exact machine-verified compatibility and traceability exceptions | retain | allowlist validation tests |

The WorkPlan IDs and review-round labels in this document are planning/evidence
coordinates and remain confined to the WorkPlan.

## Sources Of Truth

The user decision in this task governs the desired policy. Root `AGENTS.md`,
`.agents/PLANS.md`, the repository skills, and the observed semantic-ingestion
debt define the current process and failure evidence.

## Current State

The common WorkPlan contract separates planning/evidence coordinates from
behavioral, protocol, and migration identities. All six repository skills
apply the distinction at creation and closure, and review governance supports a
determinate non-product conformance action. The linked testing WorkPlan owns the
field-aware checker, exact content-bound exceptions, required CI command, and
family-complete mutation evidence. Specification, correctness, and test closure
reviews are clean.

## Assumptions And Open Questions

Verified: all current Memorii skills read `.agents/PLANS.md`. Working
assumption: the central contract belongs in `.agents/PLANS.md` with concise
skill-specific enforcement, avoiding duplicated policy prose. No external
decision is required.

## Milestones Or Experiments

1. Define the closed identity taxonomy, exception model, and remediation path.
   Status: complete. Verification: common WorkPlan contract inspection.
2. Apply phase-specific prevention and closure checks to every repository
   skill. Status: complete. Verification: six-file coverage inventory.
3. Validate skill structure and run independent process review. Status:
   complete. Verification: six valid skills, focused gates, and three clean
   final reviewer approvals.

## Progress Log

- 2026-08-02: Isolated three process causes: traceability/durable-identity
  conflation, incomplete workflow coverage, and no required non-P1/P2
  conformance remediation. Next action: amend the common WorkPlan contract.
- 2026-08-02: Added the common taxonomy, durability test, identity ledger,
  field-aware mutation gate, exact exception model, and bounded conformance
  action; applied phase-specific checks to all six repository skills. Next
  action: run independent process review against the coherent revision.
- 2026-08-02: Reconciled three independent reviews. Corrected the domain-term
  collision by renaming the policy class to planning/evidence coordinate;
  removed the P1/P2-only conformance deadlock; required positive and negative
  corpora; and assigned a canonical checker, exception authority, and CI
  command. Next action: obtain delta review of the remediated process contract.
- 2026-08-02: Reconciled delta review. Expanded generic `*_id`, import,
  f-string, diagnostic, path, design-generator, JSON/YAML, and workflow-key
  enforcement; replaced label-only exceptions with machine-checked proof; and
  completed the full coordinate-by-surface mutation matrix. Next action: obtain
  final independent closure review.
- 2026-08-02: Reconciled final review findings for diagnostic keywords and bare
  IDs, constant aliases and enum discriminators, numeric phase/review fields,
  exception proof binding, and stale WorkPlan state. Next action: run focused
  evidence and obtain a clean delta closure review.
- 2026-08-02: Reconciled delta findings that a similarly named local function
  and a same-line canonical call could imitate exception proof. Proof now
  resolves exact imported canonical owners and binds the exact value line and
  column; lexical-lookalike and same-line collision regressions pass. Next
  action: obtain explicit clean closure from all three reviewers.
- 2026-08-02: Closed the remaining Python binding families: direct and nested
  imports, wildcard imports, assignments, parameters, local definitions,
  pattern captures, module-object monkeypatching, and direct or qualified
  dynamic namespace mutation now fail closed. All three independent reviewers
  approved the final delta. Next action: none; completion contract satisfied.

## Evidence Log

- `.agents/PLANS.md` currently requires stable requirement IDs but has no
  common identity classification or identity inventory.
- `.agents/skills/design-tests/SKILL.md` contains the only explicit milestone
  naming prohibition and omits requirement-coordinate executable names.

## Decision Log

- Use one normative policy in `.agents/PLANS.md`; make every skill invoke it at
  planning and closure.
- Treat identity leakage as `Not applicable` plus `changes_required` unless
  demonstrated product impact warrants P1/P2.

## Review Log

- Round 1 `spec_auditor`: confirmed a design-remediation deadlock. Disposition:
  confirmed, `Not applicable`, `changes_required`, `identity-governance`,
  `contract_conformance_action`; remediated across design and implementation
  workflows plus the shared finding contract.
- Round 1 `correctness_reviewer`: confirmed missing executable enforcement and
  collision with Memorii's legitimate `DeliveryCoordinate` domain term.
  Disposition: confirmed; canonical checker/CI ownership added and policy class
  renamed to planning/evidence coordinate.
- Round 1 `test_reviewer`: confirmed missing checker/CI ownership and missing
  positive corpus. Disposition: confirmed; linked testing WorkPlan implements
  the checker, required CI step, negative mutations, and positive corpus.
- Delta `spec_auditor`: confirmed generic identity fields and traceability
  exceptions were too broad. Disposition: confirmed; generic `*_id` fields now
  fail and traceability is allowed only at exact registry locations or through
  a proof-backed exact exception.
- Delta `correctness_reviewer`: confirmed disguised forms, design generators,
  and label-only allowlist classifications could evade enforcement.
  Disposition: confirmed; all named surfaces are scanned and every exception
  class now validates its repository context.
- Delta `test_reviewer`: confirmed the mutation and positive corpora were not
  family-complete. Disposition: confirmed; all six fixed coordinates now run
  across eighteen surfaces, and the retained provider compatibility fixture is
  the real positive compatibility proof.
- Final `spec_auditor`: confirmed diagnostic-keyword and bare-ID bypasses plus
  stale WorkPlan current-state sections. Disposition: confirmed and remediated
  in the checker, mutation matrix, common WorkPlan closure rule, and both active
  WorkPlans.
- Final `correctness_reviewer`: confirmed alias-fed identity values, enum
  discriminators, custom raises, numeric phase/review fields, and label-only
  proof content remained bypasses. Disposition: confirmed; local constant
  propagation, explicit AST contexts, closed planning fields, and content-bound
  proof validation added.
- Final `test_reviewer`: confirmed traceability, compatibility, and legacy
  proof tests did not prove the waived value reached its claimed context.
  Disposition: confirmed; empty, wrong-field, wrong-value, substituted-test,
  unrelated-raises, and stale exceptions now fail.
- Delta `spec_auditor`: confirmed typed traceability proof trusted a callee-name
  heuristic. Disposition: confirmed; proof resolves only exact imported
  canonical constructors, and `fake_mapping` is a rejection regression.
- Delta `correctness_reviewer`: confirmed lexical lookalikes could imitate the
  retained compatibility reader. Disposition: confirmed; proof resolves only
  exact imported frozen readers, and a local `read` function is rejected.
- Delta `test_reviewer`: confirmed the transient gate `NameError` and a
  same-line source-occurrence collision. Disposition: confirmed; positional
  coordinates are checked without the removed helper, source proof matches
  line and column, and the exact collision is a rejection regression.
- Closure `spec_auditor`, `correctness_reviewer`, and `test_reviewer`: clean
  approval after adversarial proof-binding review. No remaining actionable
  identity-governance findings.

## Blockers And Limits

No blocker.

## Next Action

None. Completion contract satisfied.

## Outcome And Retrospective

The process failed because bookkeeping coordinates had no repository-wide
identity class, naming checks were confined to one testing workflow, reviewers
lacked a determinate non-product remediation path, and no executable gate
proved the rule. The completed contract centralizes the distinction, makes
every skill inventory and close durable identities, gives reviewers a bounded
conformance action, and backs the policy with field-aware CI enforcement and
content-bound exceptions.

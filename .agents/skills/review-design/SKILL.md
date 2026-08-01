---
name: review-design
description: Independently review a Memorii technical design for requirements, contract boundaries, architecture, feasibility, failure behavior, security, operability, evidence maturity, and implementation readiness. Use for full approval reviews, delta remediation reviews, or targeted design concerns without editing the canonical design.
---

# Review A Memorii Design

Perform a read-only, evidence-backed review. Do not edit the canonical design,
governing specifications, production code, or tests.

Read:

- root `AGENTS.md`
- `.agent/PLANS.md`
- target design and frozen baseline
- active review WorkPlan, if one exists
- governing documents selected through the knowledge router
- relevant code, tests, gates, prototypes, incidents, and prior decisions

Do not trust design status, implementation behavior, tests, or prior findings
without direct evidence.

## Progressive References

- Read [references/finding-contract.md](references/finding-contract.md) before
  issuing findings.
- Read [references/review-lanes.md](references/review-lanes.md) for a full
  review; for targeted review, load only the applicable lane sections.
- Read [references/convergence.md](references/convergence.md) for delta review,
  remediation review, evidence-maturity claims, or any operation with prior
  review rounds.
- Use [assets/design-review-template.md](assets/design-review-template.md) when
  writing a durable review report.

## Review Modes

Choose one:

- `full`: inspect all material requirements and review lanes; required before
  approval or a major architecture commitment
- `delta`: inspect changes between two frozen revisions, the complete affected
  semantic boundary, and regression impact
- `targeted`: inspect one named concern; never make whole-design approval claims

For a full or long-running review, create or resume a `design-review` WorkPlan
at `docs/work/<work-id>/design-review.plan.md`. Record target path, baseline,
mode, scope, governing sources, exclusions, report location, budget, and exactly
one next action.

Write immutable reports under `docs/reviews/<design-id>/<review-id>.md`.

## Phase 1: Freeze The Review Baseline

Record:

- design path, title, and content-addressed revision
- review mode, included scope, and exclusions
- governing sources and precedence
- relevant implementation revision
- external decisions and prior reports
- review date and budget

Do not review a moving target. If the design changes, finish or abandon the
current report explicitly and restart against the new baseline.

## Phase 2: Reconstruct Requirements Independently

Rebuild expected requirements from governing specifications, related designs,
implementation rules, public and persisted contracts, current behavior, tests,
operations, certification rules, and explicit stakeholder decisions.

Use:

| ID | Reconstructed requirement | Source | Design coverage | Acceptance criteria | Finding |
| --- | --- | --- | --- | --- | --- |

Classify coverage as complete, partial, missing, contradictory, intentionally
excluded, or unclear.

Do not treat every test or existing implementation behavior as intentional.
Apply source precedence from `AGENTS.md` when sources conflict.

## Phase 3: Reconstruct Contract And Evidence Boundaries

Identify applicable:

- normative versus illustrative sources
- executable versus declarative inputs
- accepted grammar, schema, projection, or state-machine forms
- source selection, aliases, inheritance, nesting, metadata, ordering,
  duplicates, and version behavior
- canonical owners and trust boundaries
- authority chain from source bytes to artifacts, implementation, and gates

For every requirement, classify evidence maturity:

| State | Meaning |
| --- | --- |
| specified | Normative behavior is explicit |
| derivable | Inputs and algorithms are complete |
| implemented | Production or reference path exists |
| locally verified | Exact deterministic checks passed |
| independently reproduced | A separate implementation agrees |
| CI enforced | Automation executes the evidence |
| operationally verified | Revision-bound external evidence exists |

Reject evidence inflation. A documented command is not CI enforcement. Multiple
runs of one implementation are not independent reproduction.

## Phase 4: Inspect Repository Reality

Inspect enough production code, schemas, persisted models, events, transactions,
providers, prompts, adapters, integrations, configuration, tests, and deployment
behavior to determine feasibility and ownership.

Check whether the design:

- changes the canonical owner
- duplicates or bypasses a contract
- assumes a missing capability
- conflicts with production reality
- requires unstated migration or mixed-version behavior
- violates a universal Memorii invariant

Do not reject a design merely because implementation is substantial.

## Phase 5: Review Applicable Lanes

Use [references/review-lanes.md](references/review-lanes.md).

For parser, compiler, registry, validator, schema, or generated-authority work,
require an equivalence-class attack matrix. Inspect direct, aliased, quoted,
nested, inherited, ordered, duplicate, fast-path, and normal-path forms where
applicable.

Do not report one syntax form and leave readily inspectable siblings for later
rounds.

## Phase 6: Run Independent Reviewers

Run concurrently:

- `spec_auditor`
- `correctness_reviewer`
- `test_reviewer`

Give each reviewer the frozen baseline, mode, scope, governing sources, code and
test paths, WorkPlan, contract boundaries, attack matrix, and canonical finding
classification contract.

Do not show one reviewer another reviewer’s findings before independent passes
finish.

Mandates:

- `spec_auditor`: reconstructed requirements, contradictions, undefined terms,
  hidden assumptions, scope, and acceptance criteria
- `correctness_reviewer`: architecture, feasibility, lifecycle, transactions,
  concurrency, recovery, security, migration, compatibility, and integration
- `test_reviewer`: behavioral proof, negative and boundary cases, failure,
  retry, concurrency, migration, rollback, benchmark, and evidence maturity

Require the finding contract in
[references/finding-contract.md](references/finding-contract.md).

## Phase 7: Reconcile Findings

Validate every proposed finding against direct evidence. Classify it as
confirmed, duplicate, unsupported, already addressed, accepted limitation,
design ambiguity, outside scope, or blocked by missing evidence.

For each confirmed finding:

1. validate the violated governing requirement
2. validate product priority independently from approval disposition
3. identify a supported broken scenario and its prevalence or importance
4. identify the root invariant or contract boundary
5. require the complete known equivalence class and adjacent bypass inventory
6. reject recommendations that expand scope or introduce a larger defect
7. define invariant-level correction and behavioral proof
8. assign remediation eligibility under `.agent/PLANS.md`

Only validated `P1` or `P2` design defects are eligible for design remediation.
Missing tests, weak proof, evidence-maturity gaps, governance concerns, and
hypothetical unsupported inputs must not be relabeled P1/P2 without direct
product-impact evidence.

Cluster eligible findings by root cause before handing them to a writer.

If two successive findings affect the same boundary, stop accepting
case-by-case patches. Require a closed grammar, typed contract, state machine,
ownership rule, or explicit design decision.

## Phase 8: Review Cadence And Outcome

Follow [references/convergence.md](references/convergence.md).

Use:

1. one full review for a coherent candidate
2. targeted or delta review for bounded remediation
3. full review after a material contract change
4. one fresh full review for final approval

Do not restart unrelated exploratory review after every micro-edit.

When the candidate has no newly validated P1/P2 defect, do not request another
design revision. Record P3 and nonblocking observations as follow-ups. Route a
predefined missing proof to one bounded evidence action. If an external
authority or semantic decision is missing, report `Blocked` once with the exact
decision required instead of starting another revision round.

Outcomes:

- `Approved`
- `Approved with follow-ups`
- `Changes required`
- `Blocked`

Approve when no validated P1/P2 design defect remains, every requirement is
traceable, predefined acceptance evidence is sufficient, material choices are
explicit, and implementation needs no hidden semantic decision. Approval
disposition alone does not establish product priority or justify another
revision.

## Phase 9: Write And Validate The Report

Use [assets/design-review-template.md](assets/design-review-template.md).

Run:

```bash
python .agent/skills/review-design/scripts/validate_review_report.py \
  docs/reviews/<design-id>/<review-id>.md
```

The validator checks required report sections and finding fields. It does not
establish that the findings are correct.

## Phase 10: Close Or Hand Off

Complete the review only when the frozen baseline, reconstructed requirements,
applicable lanes, all three independent passes, reconciled findings, coverage,
risks, outcome, and limitations are durable and understandable without chat
history.

Do not edit the design in this workflow. For `Changes required`, hand confirmed
findings to a linked `$build-design` WorkPlan and require a new review baseline.
Do not rewrite an earlier report after the design changes.

State only that no unresolved validated findings remain under the recorded
scope, sources, and review method.

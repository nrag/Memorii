# Review Convergence

## Evidence Maturity

Keep these states distinct:

| State | Required evidence |
| --- | --- |
| specified | Normative design text |
| derivable | Frozen inputs and complete algorithm |
| implemented | Production or reference path |
| locally verified | Exact local command and result |
| independently reproduced | Separately authored implementation and agreement |
| CI enforced | Checked workflow invocation and failure behavior |
| operationally verified | Revision-bound external execution |

Do not promote evidence implicitly.

## Review Cadence

Use a full review for:

- first coherent candidate
- material contract or architecture change
- final approval

Use delta or targeted review for:

- bounded remediation
- proof-strengthening without semantic change
- documentation and WorkPlan conformance
- one previously identified boundary

A delta reviewer must inspect the full affected semantic boundary and regression
surface, not only changed lines. It should not restart unrelated exploration.

## Root-Cause Escalation

Cluster findings by violated invariant.

If two successive findings affect the same parser, validator, lifecycle,
evidence, or ownership boundary:

1. stop case-by-case remediation
2. enumerate the entire accepted and rejected family
3. define a grammar, typed contract, state machine, property, or owner rule
4. add positive and negative family-level proof
5. resume review against the reconstructed boundary

Do not spend more rounds discovering syntax siblings that one inventory could
have found.

## Materiality

A remediation is material when it changes:

- public or persisted semantics
- authority inputs or derivation
- grammar, schema, state machine, or trust boundary
- migration, compatibility, rollback, or security behavior
- production composition or canonical ownership

Material remediation requires a new full review baseline. Nonmaterial,
bounded remediation normally receives delta review.

## Saturation And Stop Rule

Before another round, state:

- new information learned
- root cause advanced
- family closed
- exact remaining uncertainty
- newly validated P1/P2 product defect, if any

If a round adds only another sibling example without advancing the invariant,
reject the round as non-discriminating. Reconstruct the boundary or stop as
non-convergent under the WorkPlan budget.

Do not open a product-remediation round unless the coordinator has admitted at
least one finding through the product-impact remediation gate in
`.agent/PLANS.md`. A round that finds only P3, unsupported, evidence-maturity,
documentation, or governance observations closes without product edits.

Required evidence work is bounded by the validation matrix frozen before
implementation or review. Do not recursively enlarge that matrix merely
because a reviewer can propose another negative case.

The convergence target is satisfied required behavior with proportionate
evidence, not reviewer silence or exhaustive hypothetical-input coverage.

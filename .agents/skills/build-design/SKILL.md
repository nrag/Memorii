---
name: build-design
description: Build or substantially revise a Memorii technical design through repository research, explicit contract boundaries, feasibility experiments, adversarial readiness checks, independent review, and convergent remediation. Use for new designs or material semantic design changes.
---

# Build A Memorii Design

Read:

- root `AGENTS.md`
- `.agents/PLANS.md`
- the active design WorkPlan, if one exists
- governing documents selected through the repository knowledge router
- relevant production code and tests

Create or resume a WorkPlan whose work type is `design`.

The main thread is the coordinator. Use exactly one writer for the canonical
design and overlapping generated artifacts.

## Phase 1: Establish The Problem And Baseline

Record:

- problem, actors, current behavior, desired outcome, and impact
- source of every requirement
- included scope, excluded scope, non-goals, and approved deviations
- canonical design path and reproducible baseline
- stable requirement IDs and measurable acceptance criteria
- the identity ledger required by `.agents/PLANS.md`, classifying every
  proposed file, symbol, persisted value, test, fixture, artifact, command, and
  CI name independently from its requirement or milestone coordinate
- assumptions, external decisions, and unresolved questions

Do not invent externally visible or persisted behavior to close an ambiguity.

## Phase 2: Freeze Contract And Authority Boundaries

Before drafting algorithms or schemas, define every applicable boundary:

- normative sources versus illustrative examples
- executable inputs versus declarative inputs
- accepted grammar, schema, projection, or state-machine language
- source-selection and declaration-resolution rules
- canonical owners and extension points
- public, persisted, transaction, trust, provider, prompt, artifact, adapter,
  integration, and command-line boundaries
- authority chain from source bytes to derived artifacts and gates
- unsupported inputs and fail-closed behavior

Treat requirement and milestone coordinates as planning metadata, never as a
source of product names. Specify behavioral public, persisted, code, test,
fixture, artifact, and workflow identities explicitly. Apply the durability
test in `.agents/PLANS.md`; if a name only makes sense with the delivery plan
visible, replace it before design review.

For parsers, compilers, registries, or generated authority, inventory every
accepted declaration form before claiming the language is closed. Define alias,
inheritance, nesting, metadata, ordering, duplicate-name, and version semantics.

Record evidence maturity separately:

| State | Meaning |
| --- | --- |
| specified | Normative behavior is explicit |
| derivable | Complete inputs and algorithms are frozen |
| implemented | A production or reference implementation exists |
| locally verified | Exact deterministic verification passed |
| independently reproduced | A genuinely separate implementation agrees |
| CI enforced | Required automation executes the evidence |
| operationally verified | Revision-bound external evidence exists |

Never use evidence from one state to claim a later state. Two executions of the
same implementation prove reproducibility, not independent implementation.

## Phase 3: Analyze Reality And Feasibility

Use parallel read-only explorers when useful to inspect:

- architecture and canonical owners
- production execution paths
- public and persisted contracts
- provider and integration boundaries
- tests, fixtures, gates, and deployment behavior
- related designs, changes, and WorkPlans

Reconcile findings against direct repository evidence.

For every material choice:

1. evaluate at least one serious alternative
2. identify affected invariants and compatibility boundaries
3. record migration, rollout, rollback, and operational consequences
4. use a bounded experiment when feasibility is uncertain

An experiment must have a discriminating outcome.

If the design requires independent implementations, define independence
precisely. Identify prohibited shared code, parser, normalizer, fixtures, and
derived inputs. Run a feasibility spike before design approval.

## Phase 4: Build The Verification And Attack Model

Before the first full review, create:

- requirement-to-evidence matrix
- positive, negative, boundary, failure, retry, replay, concurrency, migration,
  compatibility, rollback, security, and observability cases where applicable
- equivalence-class attack matrix for parsers, validators, schemas, and state
  transitions
- environment and toolchain matrix
- deterministic versus live or operational evidence boundary
- a field-aware identity-hygiene check, exact typed exceptions, and mutations
  proving planning/evidence coordinates are rejected on every affected durable
  surface while legitimate behavioral numerals and protocol versions pass

For each attack family, name the invariant and enumerate sibling forms. Prefer
one grammar, typed contract, state machine, or property check over a list of
special-case patches.

The design is not review-ready when:

- a claimed closed language has no accepted-form inventory
- a derived artifact lacks an explicit authority chain
- independent evidence is required but independence is undefined
- a requirement depends on CI or operational evidence without an owner
- implementation would need hidden conversation context

## Phase 5: Draft The Design

Cover applicable:

- requirements and acceptance criteria
- architecture and ownership
- typed public and persisted contracts
- data, event, lifecycle, and visibility flow
- candidate versus committed state
- transaction, idempotency, replay, concurrency, fencing, and recovery
- provenance, validation, authorization, privacy, and trust
- migration, compatibility, rollout, rollback, and observability
- resource and performance limits
- verification strategy, evidence maturity, non-goals, and limitations

Preserve the universal Memorii invariants in `AGENTS.md`.

## Phase 6: Independent Review And Convergence

After the readiness checks pass and a coherent draft exists, run concurrently:

- `spec_auditor`
- `correctness_reviewer`
- `test_reviewer`

Tell reviewers to inspect the frozen design, governing sources, relevant code,
tests, WorkPlan, contract boundaries, and attack matrix directly.

Require every finding to:

- cite a governing requirement and observable contradiction
- identify the affected scenario or repository-contract surface
- for P1/P2 only, identify supported broken product behavior and justify its
  prevalence or importance
- identify the violated invariant or root cause
- enumerate the complete known equivalence class and adjacent bypasses
- distinguish product behavior, design completeness, implementation evidence,
  CI enforcement, and operational evidence
- propose an invariant-level correction and behavioral proof
- use the classification contract in `AGENTS.md`

Do not accept one syntax variant as a complete finding when adjacent variants
can be inspected in the same pass.

Apply the product-impact remediation gate in `.agents/PLANS.md` before editing.
Only validated `P1` or `P2` design defects enter a product-remediation round.
Missing tests, evidence-maturity gaps, hypothetical unsupported inputs, and
governance observations do not become product defects without demonstrated
product impact.

Classify non-P1/P2 findings as a bounded evidence action, a bounded
`contract_conformance_action`, record-only follow-up, or external blocker.
Determinate identity-governance violations enter conformance remediation and
block approval until corrected; do not relabel them P1/P2. An external blocker
stops the design operation and names the required decision; it does not justify
speculative revision.

Reconcile all reviewers before editing. Cluster eligible P1/P2 and contract-
conformance findings by root cause and send one coherent remediation batch to
the sole writer.

Use this cadence:

1. one full review of the coherent draft
2. targeted or delta review for bounded remediation
3. fresh full review only after a material contract change or at final approval

If two successive confirmed findings affect the same semantic boundary, stop
case-by-case remediation. Reconstruct that boundary and replace patches with a
closed grammar, typed contract, state machine, ownership rule, or explicit
scope decision.

If a review produces no new validated P1/P2 defect, do not start another
product-remediation round. Complete predefined evidence and contract-
conformance actions, record nonblocking follow-ups, approve when the completion
contract is met, or stop once with the exact external blocker.

## Phase 7: Final Design Review

When the design appears complete:

1. rebuild the requirements ledger independently
2. compare it with the maintained ledger
3. verify contract and evidence-maturity boundaries
4. verify every confirmed finding family is closed
5. confirm implementation needs no hidden semantic decision
6. independently reconstruct the identity ledger and confirm requirement IDs
   occur only as typed traceability values
7. run one fresh whole-design review with all three reviewers

Complete the WorkPlan only when the design completion contract in
`.agents/PLANS.md` is satisfied.

State only that no unresolved validated design gaps remain under the recorded
scope, sources, and review method. Stop as blocked when the WorkPlan stop
conditions apply.

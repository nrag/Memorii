# Statistical Acceptance Boundary Repair

- Work type: design
- Status: complete (bounded component design; see closure.md)
- Coordinator: main thread
- Parent: ../acceptance-numeric-boundary/design.plan.md
- Related implementation: ../engineering-closure/implementation.plan.md
- Authorization: user approved repairing the recorded failures on 2026-09-06.
- Baseline: 191826cd3afb38bf605a337a71d576063b3bae5e plus retained authorized work.

## Objective And Scope

Establish the complete policy-bound statistical computation and serialized
verification boundary before canonical promotion. Prior rejected prototypes
remain untouched as evidence. Preserve exact policy decimals, independent
clusters, binomial/Clopper-Pearson, weighted Hoeffding, complete-family Holm and
fail-closed decisions. No production policy values or signing keys are chosen.
The observer implementation remains an independent package.

## Reconstruction Strategy

Separate three owners: bounded rational arithmetic and inference; strict
policy/evidence/certificate transport; independent verification experiments.
The candidate certificate supplies no null probability, margin or policy input
that can override verifier-held manifests. Verification reconstructs the whole
expected certificate from separately parsed policy and evidence and compares
every field. Claimed results cannot select computation inputs.

The numeric kernel derives raw p-values and inverted confidence bounds from
manifest threshold/direction/alpha and independently validated cluster values,
ranges and normalized weights. Holm includes every gate, a deterministic
canonical locator tie break, frozen family alpha and nominal alpha. Unresolved
interval ordering or arithmetic exhaustion cannot accept a capability.

Every arithmetic operation has a conservative preflight bit bound and one
shared monotonic operation meter. Transport caps and duplicate-field rejection
apply to each independently supplied document before typed decoding. Decimal
lexemes are checked before integer conversion. Certificate encoding counts
bytes before allocation and uses the actual canonical typed-value bytes.

## Acceptance And Attack Matrix

- Unchanged authority rejects altered null/margin, threshold, alpha, weights,
  counts, membership, direction, policy/evidence digests and paired results.
- Full binomial tails and CP endpoints cover both directions, zero/all and
  interior observations; independent exact evaluations bracket each endpoint.
- Hoeffding derives the observed mean and range sum, including zero margin
  and deterministic ranges; inversion brackets the same concentration test.
- Holm proves complete-family presence, ties, first/middle/last ranks, prefix
  rejection and conservative unresolved ordering across methods.
- Duplicate/unknown/missing/wrongly typed fields and noncanonical rationals
  reject through the public serialized verifier, including policy/evidence.
- Instrumented arithmetic, parse and serializer sites reject over-limit work
  before the corresponding allocation; exact-limit positives remain covered.
- Locator bytes compare directly against the repository CTV encoder; digests
  exclude themselves and bind exact source bytes/authority coordinates.

## Ownership And Evidence

Coordinator owns this plan, normative proposal, kernel and transport/binding
proof. Workers own only their separate test files. A different agent independently
recomputes mathematical examples without sharing the kernel. Standard independent
design reviewers inspect a frozen candidate
after coordinator readiness. Nonproduction artifacts do not prove runtime
deployment or CI enforcement. Canonical promotion must enumerate and refresh
the complete schema/registry/structural evidence authority chain.

## Budget And Resume

The user has reopened the failed operation. This pass permits one coherent
reconstruction, one full review and up to two bounded conformance/evidence
corrections. Do not increment the budget for small test edits or confuse a
worker handoff with a review round. Record any remaining real design decision
explicitly. Do not pause unrelated implementation solely for this operation.

## Next Action

No remaining design action. Production promotion is handed to the parent
independent-statistical-evaluator implementation packet.

## Requirements And Evidence Ledger

These are component obligations derived from the governing numeric grammar and
Section 5.6, not replacement closure claims for parent R14.

| ID | Measurable acceptance | Owner/evidence | Maturity |
| --- | --- | --- | --- |
| NUM-AUTH | Independently supplied coverage/frame context matches every numeric policy projection; changed authority/gate/cluster rejects before calculation | wire_contract.py, test_wire_contract.py | implemented in nonproduction proof; tests being refreshed |
| NUM-INFERENCE | Both binomial tails, CP bounds, weighted Hoeffding and its inversion derive from complete validated event aggregates | bounded_math.py, independent_math_check.py, run_boundary_evidence.py | independently reproduced on 31 vectors; latest coefficient implementation pending rerun |
| NUM-FAMILY | Full-family Holm uses canonical ties, prefix stopping, effective alpha and conservative ambiguous ordering | bounded_math.py, both test files | locally verified before context change |
| NUM-WIRE | Exact independently held inputs and full CTV recomputation reject forged candidate fields/bytes | wire_contract.py, test_wire_contract.py | locally verified before context change |
| NUM-RESOURCE | Lexemes, arithmetic intermediates and output encoding reject before over-limit allocation | kernel/wire hooks and focused boundary tests | local evidence being refreshed |
| NUM-PROMOTION | Enumerate canonical schema and generated-authority consequences without rewriting current signed identities | proposal.md, promotion-map.md | specified; production promotion excluded from this proof |

## Review Scope And Exclusions

Actors are the independent acceptance owner and certificate verifier. This
operation approves a numerical subcomponent specification with a nonproduction
feasibility implementation, not the complete R14 acceptance pipeline. Parent
implementation still owns baseline verification, independent label provenance,
coverage/frame reconstruction, capability promotion and deployment composition.
No production entrypoint or persisted record is introduced by this proof, so
production caller evidence is not applicable to this review. Its future binding
is acceptance owner -> verified baseline/coverage/frame context -> evaluator ->
certificate -> same-context verifier; missing context fails closed. Production
readiness must prove that binding before any parent requirement is verified.

Independent checker may use stdlib exact arithmetic and mathematical definitions;
it must not import the kernel, transport decoder, normalizer or expected outputs.
Runner supplies raw vector parameters plus claimed outputs; checker independently
reconstructs their values/inequalities. Synthetic values prove mechanics only.

No persistent writes, retries, concurrency or rollback occur inside this pure
component. Repeated evaluation is deterministic for identical inputs and budgets.
Malformed input/resource exhaustion raises WireRejected without a certificate.
No runtime/provider/live certification or CI enforcement is claimed here.
Existing signed versions remain replayable; future promotion follows the full
authority chain in promotion-map.md and requires a linked implementation packet.

## Identity And Changed-Surface Ledger

All changes for this operation are under this work directory. Python filenames
describe numerical, transport or verification behavior; Markdown filenames are
planning evidence. Dataclasses in wire_contract.py define the exhaustive field
inventory; there is no dynamic registry, inheritance or alias expansion.
`statistical_acceptance_certificate.v1` is a genuine proposed wire version.
Requirement IDs occur only in this planning ledger. Fixtures use synthetic
behavioral labels and explicit numeric values. No production source, dependency,
workflow pin, existing CTV inventory or signed release changes in this operation.

## Confirmed Consultation Actions

NUM-AUTH consultation findings DREV001/002 are confirmed as determinate contract
conformance actions: a self-contained policy cannot establish coverage or IID.
Added a mandatory typed preverified context, separate expected authority,
exact projection equality, context-derived family/event set and context IID proof.
The acceptance owner's upstream reconstruction remains a parent integration
obligation. This construction consultation is not the frozen full review.

## Frozen Candidate Verification

Coordinator independently ran the combined math/wire suite: 52 passed in 4.78s
using Python 3.12, warnings as errors and no pytest cache. Scoped Pyright reports
zero errors/warnings; Ruff and tracked diff whitespace checks pass. The separately
authored checker passes 31 vectors and rejects six altered results under both
normal Python and optimization mode. These are local component proofs only.
All component writers have stopped. candidate.json pins every scoped source,
test, design/field inventory and governing source used by the review. The dirty
repository's pre-existing authorized signing/evidence work is outside this
component review and remains subject to parent closure review.

The first full review required the conformance/evidence actions in review.md.
The coherent correction now passes 76 focused tests (5.20s), including public
fixed-step CP/Hoeffding checks. All three public precision cases demonstrably
fail when inverse bounds are replaced with the full range. Independent checks
now pass 33 vectors and reject eight altered results, including widened bounds
and false endpoint claims. Resource preflight now traverses the dataclass before
map allocation. No substantive threshold or policy value changed.

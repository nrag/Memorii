# Acceptance Numeric Contract Correction

- Work ID: acceptance-numeric-contract
- Work type: design
- Status: paused (boundary reconstruction required)
- Coordinator: Codex main thread
- Created: 2026-09-06
- Last updated: 2026-09-06
- Parent WorkPlan: ../engineering-closure/implementation.plan.md
- Related WorkPlans: ../../semantic_ingestion_completion_readiness/investigation.plan.md
- Canonical inputs: docs/design/semantic_ingestion_architecture.md at commit 191826cd3afb38bf605a337a71d576063b3bae5e, sections on canonical numeric values and 5.6
- Expected outputs: reviewed computed-result numeric contract, feasibility proof, authority-chain reconciliation

## Objective And Problem Definition

Make independently computed statistical results representable and verifiable
without rounding exact policy values or strengthening an acceptance claim.
The current architecture requires fixed-scale decimal values with reject-inexact
rounding for probabilities and bounds, but Clopper-Pearson roots and Hoeffding
exponentials generally have no finite exact decimal representation. There are
also no registered field-specific decimal encoding specifications in the current
design or implementation. Do not silently choose a decimal scale or treat a
floating-point approximation as an exact signed value.

## Scope And Non-Goals

Included: result enclosure grammar, comparison and termination rules, exact
input encoding boundary, deterministic family ordering, independent validation,
and the complete downstream authority chain affected by a normative correction.
Excluded: choosing substantive thresholds, alpha, coverage, sample minima,
sampling weights or real production signers; changing ingestion semantics;
weakening the existing exact policy-input encoding contract.

## Sources And Existing-System Analysis

Apply root AGENTS.md precedence. Architecture lines 2798-2814 prohibit raw
float/Decimal and require per-field encoding specs. Section 5.6 lines
32548-32631 specifies the statistical tests and independent recomputation.
The existing calibration/statistics.py implements different bootstrap and
floating-point calculations and is not the acceptance authority. A repository
search for encoding_spec_id, reject_inexact and fixed_scale_value finds only
the architecture declarations, not an existing field registry to reuse.

## Requirements Ledger

| ID | Requirement | Source | Acceptance | State |
| --- | --- | --- | --- | --- |
| ANC-01 | Exact policy inputs retain reject-inexact behavior | canonical numeric profile | malformed/inexact input rejects | specified |
| ANC-02 | Computed probability/bound enclosure contains mathematical value | Section 5.6 | independent rational certificate and boundary checks | proposed |
| ANC-03 | Approximation cannot turn a failing or undecidable gate into acceptance | Section 5.6; fail closed | conservative comparisons; inconclusive rejects | proposed |
| ANC-04 | Identical inputs and budget produce deterministic evidence | canonical profile | canonical grammar, ordering, exact re-encoding | proposed |
| ANC-05 | Registered authority and derived pins agree with corrected design | PLANS authority chain | all affected validators/gates pass | not started |

## Alternatives And Current Recommendation

Recommended: separate certified rational enclosures for computed results; keep
CanonicalDecimalQuantity for exact policy inputs. Exact binomial p-values can
have equal endpoints; nonterminating roots and exponentials have outward
endpoints and a verifier-recomputable certificate. The upper p-value endpoint
must satisfy the declared alpha; confidence-bound comparisons use the unsafe
direction's outer endpoint. Exhausted precision/work budgets yield inconclusive,
never acceptance. No display decimal has authority.

Alternative: result-only directed-rounding decimal schemas. This is feasible
but adds fixed scale choices to persisted semantics and makes near-boundary
results needlessly inconclusive. It must never reuse the policy input type.

This recommendation is not yet an approved normative contract. Endpoint grammar,
algorithm/certificate, budget ownership, input encoding registration, and exact
boundary comparisons must be frozen and independently reviewed before use.

## Constraints, Identity And Change Map

Preserve exact policy inputs, independence from production semantic helpers,
closed typed schemas, and fail-closed activation. Proposed behavioral owner:
acceptance numeric verification; no milestone or requirement IDs in executable
symbols or wire identities. No product/schema changes made in this operation yet.
Planning-only paths are traceability metadata. Normative architecture changes
will require the full registry/CTV/structural/golden/workflow pin chain; inventory
that chain before changing the canonical document. No persisted migration yet;
new unsupported result schemas must fail closed on older readers.

## Feasibility And Verification Strategy

Before review, execute exact finite binomial examples and rational brackets for
nonterminating roots, and a rational exponential enclosure experiment. Use a
separately authored recomputation rather than two calls to one function.
Attack matrix: malformed/noncanonical rationals, reversed endpoints, false
certificates, tail direction, equality, zero/all failures, zero-weight and
degenerate ranges, duplicate/missing claims, tie order, exhausted budget,
precision substitution and unsupported algorithm identity. Show both accepted
and rejected boundary neighbors. Integration must consume the evidence through
the acceptance owner; a standalone helper test cannot close parent R14.

## Failure And Operational Analysis

Invalid inputs or certificates reject before authorization. Interrupted
computation yields no acceptance artifact. Computation limits are explicit and
cannot relax a threshold; exhaustion is inconclusive. No mutable production
state, network service, private key or real activation is required for feasibility.
Retries over identical inputs remain deterministic. Operational policy values
remain external inputs and are not supplied by this correction.

## Progress, Decisions And Review

- 2026-09-06: Coordinator and independent correctness consultation confirmed
  the numeric representation conflict. Deterministic Holm ordering and typed
  raw evidence are ordinary concretization; computed-result encoding needs this
  linked design correction. User production-signature deferral remains intact.
- No canonical design edit, product implementation, or design approval claimed.
- 2026-09-06: Added `proposal.md`, a nonnormative closed rational-interval
  grammar and certificate proposal. It keeps policy inputs in their existing
  field-specific `CanonicalDecimalQuantity` boundary and assigns no alpha,
  threshold, scale, budget, schema ID, or activation authority.
- 2026-09-06: Extended the nonproduction proof to exact general-binomial
  bisection for both tails with nonzero/non-all counts, Taylor-enclosed
  weighted-Hoeffding tails, and a deterministic exact-rational Holm tie. A
  separate verifier parses the generated certificate and independently
  recalculates the binomial inequalities, exponent identities, Taylor
  enclosures, and tie ordering. This is locally verified feasibility only,
  not independent production evidence or design approval.
- 2026-09-06: Revised the proposal to a freeze-ready draft after coordinator
  review. It distinguishes signed general rationals from `[0,1]`
  probabilities; names exact binomial and Clopper-Pearson tail equations and
  endpoints; uses `min(nominal_alpha, family_wise_alpha/(m-i))` without
  choosing either input; defines a bracketed/clipped Hoeffding inversion; and
  supports the exact `S = 0` fixed-value branch. It names future acceptance
  owners, schema roles, finite failure codes, architecture coordinates, and
  the registry-to-activation authority-chain inventory without modifying any
  normative or production artifact.
- 2026-09-06: Added the R15 sibling-field crosswalk for
  `MonitoringMetricDecision` (`estimate`, bounds, and `alpha_spent`). This is
  limited to shared computed numeric representation; sequential-estimator and
  monitoring-policy semantics remain outside this correction.
- 2026-09-06: Corrected the draft's invalid assumption that field-specific
  decimal registrations already exist. It now proposes a closed immutable
  `CapabilityStatisticalNumericEncodingRegistry` with exact per-field
  `encoding_spec_id`, unit, scale, bounds, inclusivity, and reject-inexact
  binding. The registry is operator-provided and digest-bound before labels;
  no scale, range, or default entry was chosen here.
- 2026-09-06: Reconciled review-round findings in one proposal/prototype batch:
  exact cell/metric locator and paired-proof coupling, independently supplied
  contribution evidence with derived statistics, strict domain/minimum checks,
  bounded resource accounting, acyclic registry digest, monitoring alpha
  enclosure, zero-based Holm evidence, existing acceptance-owner binding, and
  a closed explicit-exception prototype verifier. Candidate is ready for the
  authorized targeted re-review; no canonical promotion is claimed.
- 2026-09-06: Consolidated the proposal after coordinator inspection. The
  original contract sections now contain the final locator, compound proof,
  contribution, registry, budget, monitoring-alpha, and owner definitions;
  superseded appendix language was removed. The candidate contains no
  contradictory earlier schema or budget definition.
- 2026-09-06: Reconciled the second delta-review batch in
  `review-round-2.md`: cyclic proof coupling, manifest budget ownership and
  preallocation, primitive/derivation closure, locator tie ordering, and
  executable resource/mutation fixtures. The candidate is frozen for review;
  this remains nonproduction feasibility and does not complete the parent work.
- 2026-09-06: Archived the preceding candidate identity and wrote a new
  `review-candidate.json` containing actual SHA-256 values for this plan,
  proposal, both original proof files, the new boundary proof, generated
  evidence, both reconciliation records, and the governing architecture input.
  Hashes were rechecked after all proof commands; do not edit listed files
  until the next review outcome is reconciled.

## Completion Contract And Limits

Freeze complete contracts and feasibility evidence, reconcile derived authority,
and obtain specification/correctness/test review with no required finding.
Budget: one coherent review and at most two bounded remediation rounds; stop for
an external semantic decision if required. Other engineering packages need not
wait for this numeric correction.

## Next Action

Resume only after the linked `../acceptance-numeric-boundary/design.plan.md`
establishes complete typed contracts, pre-allocation proof and a real serialized
compound validator. The round-two candidate is not approved; its exact files
are preserved in the content-addressed history archive referenced there.

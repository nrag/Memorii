# Proposed Computed-Numeric Contract

Status: freeze-ready design proposal only. It makes no canonical architecture,
registry, CTV, production, approval, or policy-value change.

## Scope, Owners, And Exact Inputs

This correction covers Section 5.6 computed p-values, confidence bounds,
Holm decisions, and the shared computed fields of `MonitoringMetricDecision`.
It does not design the sequential monitoring estimator or choose alpha,
threshold, scale, range, weight, minimum, or work limit.

The architecture has `CanonicalDecimalQuantity` but no field-specific encoding
registry. Before labels, an operator supplies an immutable
`CapabilityStatisticalNumericEncodingRegistry`. It binds each exact policy
field path to one encoding spec (unit, fixed scale, finite lower/upper bound,
inclusivity, and `reject_inexact`); it has no default or inheritance. Required
paths are every numeric policy field currently named in `CertificationMetricGate`,
`CapabilityStatisticalGateManifest`, `CapabilityMonitoringPolicy`,
`MonitoringMetricGate`, and `SequentialTestManifest`. A new numeric policy
field is unusable until its entry is added in the same registry revision.

`acceptance/statistical_certification.py` is the planned canonical owner of
immutable contribution validation, numeric evaluation, independent certificate
verification, and signed certification output. `acceptance/capability_baseline_approval.py`
approves only pre-evaluation baseline/manifest/registry inputs. Production
`memory_evolution/deployment_authorization.py` verifies serialized signed
deployment bytes only. `CertifiedSemanticCapability.certification_evidence_digest`
is a post-evaluation consumer and cannot enter a baseline-approval preimage.

## Closed Numeric Grammar

`UnsignedDecimal` is `0` or a nonzero digit followed by digits. `SignedDecimal`
is `UnsignedDecimal` or `-` followed by a nonzero digit and digits. No JSON
number, whitespace, plus, exponent, leading zero, or negative zero is valid.
`PositiveInteger` is a nonzero `UnsignedDecimal`; `PositiveDecimal` is the same
lexeme when used as a denominator. `Digest` is exactly 64 lowercase hexadecimal
ASCII digits. `Identifier` is lowercase ASCII `[a-z][a-z0-9_]*`. A nullable
field is explicitly `null`; omission is never a value.

```text
SignedRational := { "numerator": SignedDecimal, "denominator": PositiveDecimal }
Probability := SignedRational where 0 <= value <= 1
RationalInterval := { "lower": SignedRational, "upper": SignedRational }
  where lower <= upper
ProbabilityInterval := RationalInterval where 0 <= lower <= upper <= 1
GateLocator := { "capability_fingerprint": Digest,
                 "coverage_cell_id": Identifier, "metric_id": Identifier }
WorkBudget := {
  "maximum_input_bytes": PositiveInteger,
  "maximum_contribution_count": PositiveInteger,
  "maximum_integer_digits": PositiveInteger,
  "maximum_rational_bits": PositiveInteger,
  "maximum_exact_operations": PositiveInteger,
  "maximum_certificate_bytes": PositiveInteger,
  "root_bisection_steps": PositiveInteger,
  "exponential_taylor_terms": PositiveInteger,
  "log_bisection_steps": PositiveInteger,
  "sqrt_bisection_steps": PositiveInteger
}
PositiveRationalInterval := RationalInterval where 0 <= lower <= upper
HoeffdingRawDerivation := { "exponent": SignedRational,
  "partial_sum": SignedRational, "first_omitted_term": SignedRational,
  "geometric_tail_upper": SignedRational, "taylor_terms": PositiveInteger }
HoeffdingClipInputs := { "weighted_mean": SignedRational,
  "range_lower": SignedRational, "range_upper": SignedRational,
  "unclipped_lower": SignedRational, "unclipped_upper": SignedRational }
```

Every rational is reduced and re-encodes exactly with positive denominator;
`2/4`, `+1/2`, `01/2`, and `-0/1` reject. General ranges, means, thresholds,
and bounds use `SignedRational`; only probabilities and alpha use `Probability`.
Equal endpoints are allowed only for an exact result. `MonitoringMetricDecision`
changes only its computed fields: `estimate`, `lower_bound`, `upper_bound`, and
`alpha_spent` become nullable `RationalInterval`, `RationalInterval`,
`RationalInterval`, and `ProbabilityInterval`, respectively. Its sequential
method and lifecycle semantics are unchanged.

## Registry And Gate Binding

The registry's closed body is `{registry_revision, entries}`. An entry is
`{schema_field_path, encoding_spec_id, unit, fixed_scale,
lower_bound_fixed_scale_value, lower_inclusive, upper_bound_fixed_scale_value,
upper_inclusive, reject_inexact}`. Entries sort by the existing canonical
encoder's unsigned UTF-8 JSON-string order of `schema_field_path`; duplicate
paths or encoding IDs reject. Bound text has precisely `fixed_scale` digits
after its decimal point and the existing fixed-scale lexical rules. Bounds are
ordered; equal bounds require both endpoints inclusive.

`registry_digest` is not in that body. It is SHA-256 of the existing canonical
artifact length-prefix encoding of: ASCII domain
`memorii:capability-statistical-numeric-encoding-registry:v1`, UTF-8 registry
revision, and the canonical typed-value bytes of the body, with each component
prefixed by its unsigned 64-bit big-endian length. The registry schema's normal
profile/binding bytes remain part of its enclosing canonical artifact. This
prevents a digest cycle and makes revision, order, or body substitution fail.

`CapabilityStatisticalGateManifest` gains required
`numeric_encoding_registry_digest`, `work_budget:WorkBudget`, and
`work_budget_digest:Digest`; every claim must equal that frozen budget and
digest. Each `CertificationMetricGate` gains positive
`minimum_independent_cluster_count`. Initial transport decodes only a separately
provisioned bounded envelope before it parses manifest or budget; oversize input
rejects and that bootstrap limit is not a policy default. The same digest is required in
`ApprovedCapabilityBaselineArtifact` and `CapabilityBaselineApprovalRelease`.
All three must equal the registry artifact used to decode policy inputs.

## Evidence, Budgets, And Claim Schema

`ImmutableClusterMetricContribution` is independently supplied acceptance
evidence with exactly `gate_locator`, `cluster_id`, `value`, `range_lower`,
`range_upper`, `weight`, `missing_disposition`, and `source_evidence_digest`.
It is canonicalized by `(gate_locator, cluster_id)`. The verifier matches every
entry against the frozen sampling-frame cluster membership and frozen weighting
policy: complete cluster set, exact range, exact nonnegative weight, no
duplicates, positive normalized total exactly one, and no post-label change.
The only allowed missing disposition is the predeclared `cluster_failure`.

The evaluator derives, rather than accepts, all trial/failure/independent
cluster/positive-weight counts, missingness effects, weighted mean, and S from
this table. The table must be nonempty and its derived independent count must
meet the gate's positive minimum; binomial also requires positive trial count.
All raw, nominal, family, and effective alpha values require `0 < alpha < 1`.

Every `CapabilityStatisticalNumericClaim` is the closed map
`{gate_locator, manifest_digest, numeric_encoding_registry_digest,
contribution_evidence_digest, work_budget, method, bound_direction, threshold,
nominal_alpha, family_wise_alpha, effective_alpha, raw_p_value,
confidence_bound, proof_bundle, outcome}`. `proof_bundle` is one closed
discriminated bundle whose `binding` contains gate locator, manifest/registry/
contribution/budget digests, method, direction, derived counts, threshold,
nominal/family/effective alpha, and reported raw-p/bound digests.
`binding_digest` is the canonical digest of that binding. Each proof carries
that digest, typed inputs, derivation, and result; the bundle carries
independently recomputed raw-p and confidence-proof digests. Verifier
recomputation must reproduce both digests and claim-reported results.

The evaluator preflights input byte length, contribution cardinality, integer
lexeme length, and every projected certificate field before allocation. It
maintains one monotonic exact-operation counter: parse/reduce/compare,
coefficient construction, rational multiplication/addition, Taylor term,
bisection comparison, interval refinement, and Holm comparison each consume a
declared unit. It checks rational numerator/denominator bit length after every
operation. Every branch, including degenerate, root, log, square-root, and tie
refinement, is bounded by this same budget. Exhaustion yields `resource_limit`
and `inconclusive` before a result/certificate is emitted.

## Compound Proof Variants

Only `ExactBinomialBundle` (exact-binomial p plus Clopper-Pearson bound) and
`HoeffdingBundle` (Hoeffding p plus Hoeffding bound) are permitted; cross-pairs
reject. Their contained variants are:

```text
ExactBinomialRawP := { kind:"exact_binomial", binding_digest:Digest,
  trial_count:PositiveInteger, observed_success_count:UnsignedDecimal,
  tail:"greater_or_equal"|"less_or_equal", null_probability:Probability,
  exact_p_value:Probability }
ClopperPearsonBound := { kind:"clopper_pearson", binding_digest:Digest,
  endpoint:"lower"|"upper", trial_count:PositiveInteger,
  observed_success_count:UnsignedDecimal, alpha:Probability,
  root_interval:ProbabilityInterval, root_bisection_steps:PositiveInteger }
WeightedHoeffdingRawP := { kind:"weighted_hoeffding", binding_digest:Digest,
  branch:"exponential"|"degenerate_fixed_value", weighted_mean:SignedRational,
  threshold:SignedRational, squared_range_weight_sum:SignedRational,
  p_value:ProbabilityInterval, derivation:HoeffdingRawDerivation }
HoeffdingBound := { kind:"weighted_hoeffding_bound", binding_digest:Digest,
  endpoint:"lower"|"upper", alpha:Probability,
  log_interval:PositiveRationalInterval, sqrt_interval:PositiveRationalInterval,
  clip_inputs:HoeffdingClipInputs, confidence_bound:RationalInterval }
```

All fields are the grammar above and each map rejects unknown/missing fields.
Exact binomial computes the stated finite tail. The lower CP endpoint solves
`P_p(X >= k)=alpha` and is exactly zero for `k=0`; the upper endpoint solves
`P_p(X <= k)=alpha` and is exactly one for `k=n`. Nondegenerate lower proof
requires `tail(lower)<=alpha<=tail(upper)`; upper proof requires
`tail(lower)>=alpha>=tail(upper)`.

Weighted Hoeffding derives `S=sum(w_i^2*(upper_i-lower_i)^2)`. For `S>0` it
certifies `exp(-q)` by positive Taylor partial sum plus rational geometric tail.
For zero directional margin p is `[1,1]`. For `S=0`, every positive-weight
range must be fixed; the exact branch is `[0,0]` only for strict favorable
direction and `[1,1]` otherwise. Inversion brackets `log(1/alpha)` and its
square root rationally, then clips the resulting outer endpoints to the exact
range. An upper claim uses the outer upper endpoint and a lower claim the outer
lower endpoint.

## Decisions And Holm

For zero-based position `i` in complete family length `m`, where
`0 <= i < m`, effective alpha is exactly
`min(nominal_alpha, family_wise_alpha/(m-i))`. A probability passes only when
its upper endpoint is at most effective alpha; it fails only when its lower
endpoint is greater; otherwise it is inconclusive. Exact p-values order by
value then canonical UTF-8 bytes of `GateLocator`; Hoeffding p-values order by
reverse exact exponent then those same locator bytes.
Cross-method overlap refines within budget or is inconclusive. A failed or
inconclusive prefix blocks later acceptance. Required evidence covers first,
middle, last, equality, just-above, exact tie, unresolved overlap, and prefix
cases.

Finite failure codes are `malformed_rational`, `out_of_domain`,
`unsupported_algorithm`, `evidence_mismatch`, `invalid_weight_or_range`,
`invalid_degenerate_branch`, `resource_limit`, `unresolved_order`, and
`certificate_mismatch`; each produces inconclusive and unknown codes reject.

## Canonical Promotion Inventory And Feasibility

The future architecture change touches lines 2798-2814, 1209-1232, 32471-32627,
32676-32684, 3755-3762, and 34283-34287. Its chain is architecture -> registry
schema/profile binding -> CTV registry -> structural manifest/derivation ledger
-> coverage/execution roots -> signed release/active pointer -> gate/baseline
-> acceptance certification -> serialized deployment evidence -> production
read-only verifier. Each changed schema requires CTV, structural inventory,
golden vector/validator, derived pins, mutation coverage, and entrypoint proof.

The nonproduction proof writes six nonzero/non-all CP roots, five Hoeffding
cases including `S=0`, and an exact Holm tie. Its independent verifier rejects
unknown fields/tails/branches, malformed rationals, boundary alpha, empty
evidence, and invalid Holm families using explicit exceptions; normal and
`python -O` execution agree. This is feasibility only, not design approval.

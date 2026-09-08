# Numeric Component Field Inventory

Generated from the frozen dataclasses in the nonproduction proof. No aliases,
inheritance, implicit fields or production schema registration is introduced.

| Owner | Type | Explicit fields |
| --- | --- | --- |
| bounded_math.py | ArithmeticBudget | maximum_rational_bits: int; maximum_exact_operations: int |
| bounded_math.py | ArithmeticMeter | budget: ArithmeticBudget; allocation_hook: Callable[[str], None] &#124; None; operations: int |
| bounded_math.py | RationalInterval | lower: Fraction; upper: Fraction |
| bounded_math.py | WeightedObservation | value: Fraction; weight: Fraction; lower: Fraction; upper: Fraction |
| bounded_math.py | HoeffdingResult | probability: RationalInterval; weighted_mean: Fraction; squared_range_weight_sum: Fraction; margin: Fraction; deterministic: bool; exponent: Fraction &#124; None |
| bounded_math.py | HolmClaim | locator_bytes: bytes; nominal_alpha: Fraction; probability: RationalInterval; exact_order: Fraction &#124; None |
| bounded_math.py | HolmDecision | locator_bytes: bytes; effective_alpha: Fraction; outcome: Literal['pass', 'fail', 'inconclusive']; rank: int &#124; None |
| wire_contract.py | TransportLimits | max_candidate_bytes: int; max_policy_bytes: int; max_evidence_bytes: int; max_arithmetic_bits: int; max_operations: int; max_precision: int; max_output_bytes: int; max_integer_digits: int; max_depth: int; max_members: int; max_string_bytes: int |
| wire_contract.py | EncodingSpec | encoding_spec_id: str; unit: str; scale: int; lower: str; upper: str; lower_inclusive: bool; upper_inclusive: bool; reject_inexact: Literal[True] |
| wire_contract.py | CanonicalDecimalQuantity | encoding_spec_id: str; fixed_scale_value: str |
| wire_contract.py | GateLocator | capability_fingerprint: str; cell_id: str; metric_id: str |
| wire_contract.py | Gate | locator: GateLocator; method: Literal['exact_binomial', 'weighted_hoeffding']; direction: Literal['upper', 'lower']; estimand: Literal['cluster_any_failure', 'cluster_macro_mean']; threshold: CanonicalDecimalQuantity; nominal_alpha: CanonicalDecimalQuantity; minimum_clusters: int; threshold_spec_id: str; nominal_alpha_spec_id: str; lower_spec_id: str; upper_spec_id: str; weight_spec_id: str; event_value_spec_id: str; iid_declared: bool |
| wire_contract.py | Membership | cluster_id: str; locator: GateLocator; provenance_ids: tuple[str, ...]; expected_event_ids: tuple[str, ...]; weight: CanonicalDecimalQuantity; lower: CanonicalDecimalQuantity; upper: CanonicalDecimalQuantity |
| wire_contract.py | Policy | arithmetic_bits: int; arithmetic_operations: int; precision: int; output_cap: int; family_alpha: CanonicalDecimalQuantity; family_alpha_spec_id: str; specs: tuple[EncodingSpec, ...]; gates: tuple[Gate, ...]; memberships: tuple[Membership, ...] |
| wire_contract.py | EvidenceEvent | event_id: str; provenance_id: str; locator: GateLocator; value: CanonicalDecimalQuantity &#124; None |
| wire_contract.py | Evidence | events: tuple[EvidenceEvent, ...] |
| wire_contract.py | NumericAuthority | approved_baseline_artifact_digest: str; verified_baseline_approval_release_digest: str; capability_fingerprint: str; capability_contract_digest: str; coverage_manifest_digest: str; coverage_release_id: str; statistical_gate_manifest_digest: str; sampling_frame_digest: str; independent_cluster_definition_digest: str; strata_definition_digest: str; cluster_weighting_digest: str; numeric_encoding_registry_digest: str |
| wire_contract.py | PreverifiedNumericGate | gate: Gate; iid_bernoulli_clusters_proven: bool |
| wire_contract.py | PreverifiedNumericCertificationContext | authority: NumericAuthority; numeric_encoding_specs: tuple[EncodingSpec, ...]; family_alpha: CanonicalDecimalQuantity; family_alpha_spec_id: str; expected_gates: tuple[PreverifiedNumericGate, ...]; expected_clusters: tuple[Membership, ...] |
| wire_contract.py | HeldBinding | policy_sha256: str; evidence_sha256: str; expected_authority: NumericAuthority; context: PreverifiedNumericCertificationContext |
| wire_contract.py | RationalNumber | numerator: int; denominator: int |
| wire_contract.py | ExactValue | kind: Literal['exact']; value: RationalNumber |
| wire_contract.py | EnclosedValue | kind: Literal['enclosure']; lower: RationalNumber; upper: RationalNumber |
| wire_contract.py | GateResult | locator: GateLocator; method: Literal['exact_binomial', 'weighted_hoeffding']; direction: Literal['upper', 'lower']; independent_clusters: int; positive_weight_clusters: int; observed_successes: int &#124; None; weighted_mean: RationalNumber; squared_range_weight_sum: RationalNumber &#124; None; threshold: RationalNumber; nominal_alpha: RationalNumber; effective_alpha: RationalNumber; raw_probability: ComputedValue; confidence_bound: ComputedValue; holm_rank: int &#124; None; holm_outcome: Outcome; bound_outcome: Outcome; outcome: Outcome |
| wire_contract.py | Certificate | schema: Literal['statistical_acceptance_certificate.v1']; policy_sha256: str; evidence_sha256: str; authority: NumericAuthority; family_alpha: RationalNumber; accepted: bool; results: tuple[GateResult, ...] |
| wire_contract.py | _Derived | gate: Gate; observations: tuple[WeightedObservation, ...]; threshold: Fraction; alpha: Fraction; probability: RationalInterval; successes: int; weighted_mean: Fraction; squared_sum: Fraction &#124; None; exponent: Fraction &#124; None |

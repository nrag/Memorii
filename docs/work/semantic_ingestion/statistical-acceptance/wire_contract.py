"""Nonproduction strict policy/evidence binding and canonical certificate recomputation.

Policy and evidence use ASCII JSON; their exact bytes have independently held
SHA-256 bindings. Certificates use canonical typed-value bytes. A candidate is
never decoded or trusted to choose calculation inputs: only exact equality to
freshly computed canonical bytes permits a typed result to be returned.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, fields, is_dataclass
from fractions import Fraction
from hashlib import sha256
from typing import Any, BinaryIO, Callable, Literal

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from bounded_math import (
    ArithmeticBudget, ArithmeticMeter, HolmClaim, RationalInterval,
    WeightedObservation, clopper_pearson_bound, exact_binomial_tail,
    holm_complete, invert_weighted_hoeffding, parse_rational, weighted_hoeffding,
)

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_DEC = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]+\Z")
ENCODER_HOOK: Callable[[], None] | None = None
MATERIALIZER_HOOK: Callable[[], None] | None = None
_ZERO, _ONE = Fraction(0), Fraction(1)
Outcome = Literal['pass', 'fail', 'inconclusive']


class WireRejected(ValueError):
    """No certificate or acceptance result is returned after rejection."""


@dataclass(frozen=True)
class TransportLimits:
    max_candidate_bytes: int
    max_policy_bytes: int
    max_evidence_bytes: int
    max_arithmetic_bits: int
    max_operations: int
    max_precision: int
    max_output_bytes: int
    max_integer_digits: int
    max_depth: int
    max_members: int
    max_string_bytes: int

    def __post_init__(self) -> None:
        if any(type(getattr(self, f.name)) is not int or getattr(self, f.name) < 1 for f in fields(self)):
            raise WireRejected('transport_configuration')


@dataclass(frozen=True)
class EncodingSpec:
    encoding_spec_id: str
    unit: str
    scale: int
    lower: str
    upper: str
    lower_inclusive: bool
    upper_inclusive: bool
    reject_inexact: Literal[True]


@dataclass(frozen=True)
class CanonicalDecimalQuantity:
    encoding_spec_id: str
    fixed_scale_value: str


@dataclass(frozen=True)
class GateLocator:
    capability_fingerprint: str
    cell_id: str
    metric_id: str


@dataclass(frozen=True)
class Gate:
    locator: GateLocator
    method: Literal['exact_binomial', 'weighted_hoeffding']
    direction: Literal['upper', 'lower']
    estimand: Literal['cluster_any_failure', 'cluster_macro_mean']
    threshold: CanonicalDecimalQuantity
    nominal_alpha: CanonicalDecimalQuantity
    minimum_clusters: int
    threshold_spec_id: str
    nominal_alpha_spec_id: str
    lower_spec_id: str
    upper_spec_id: str
    weight_spec_id: str
    event_value_spec_id: str
    iid_declared: bool


@dataclass(frozen=True)
class Membership:
    cluster_id: str
    locator: GateLocator
    provenance_ids: tuple[str, ...]
    expected_event_ids: tuple[str, ...]
    weight: CanonicalDecimalQuantity
    lower: CanonicalDecimalQuantity
    upper: CanonicalDecimalQuantity


@dataclass(frozen=True)
class Policy:
    arithmetic_bits: int
    arithmetic_operations: int
    precision: int
    output_cap: int
    family_alpha: CanonicalDecimalQuantity
    family_alpha_spec_id: str
    specs: tuple[EncodingSpec, ...]
    gates: tuple[Gate, ...]
    memberships: tuple[Membership, ...]


@dataclass(frozen=True)
class EvidenceEvent:
    event_id: str
    provenance_id: str
    locator: GateLocator
    value: CanonicalDecimalQuantity | None


@dataclass(frozen=True)
class Evidence:
    events: tuple[EvidenceEvent, ...]


@dataclass(frozen=True)
class NumericAuthority:
    approved_baseline_artifact_digest: str
    verified_baseline_approval_release_digest: str
    capability_fingerprint: str
    capability_contract_digest: str
    coverage_manifest_digest: str
    coverage_release_id: str
    statistical_gate_manifest_digest: str
    sampling_frame_digest: str
    independent_cluster_definition_digest: str
    strata_definition_digest: str
    cluster_weighting_digest: str
    numeric_encoding_registry_digest: str

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            _id(value) if field.name == 'coverage_release_id' else _digest(value)


@dataclass(frozen=True)
class PreverifiedNumericGate:
    gate: Gate
    iid_bernoulli_clusters_proven: bool


@dataclass(frozen=True)
class PreverifiedNumericCertificationContext:
    """Acceptance-owner output, never decoded from candidate or policy input."""

    authority: NumericAuthority
    numeric_encoding_specs: tuple[EncodingSpec, ...]
    family_alpha: CanonicalDecimalQuantity
    family_alpha_spec_id: str
    expected_gates: tuple[PreverifiedNumericGate, ...]
    expected_clusters: tuple[Membership, ...]


@dataclass(frozen=True)
class HeldBinding:
    policy_sha256: str
    evidence_sha256: str
    expected_authority: NumericAuthority
    context: PreverifiedNumericCertificationContext

    def __post_init__(self) -> None:
        _digest(self.policy_sha256)
        _digest(self.evidence_sha256)
        if (type(self.expected_authority) is not NumericAuthority
                or type(self.context) is not PreverifiedNumericCertificationContext
                or self.context.authority != self.expected_authority):
            raise WireRejected('numeric_context_authority')


@dataclass(frozen=True)
class RationalNumber:
    numerator: int
    denominator: int


@dataclass(frozen=True)
class ExactValue:
    kind: Literal['exact']
    value: RationalNumber


@dataclass(frozen=True)
class EnclosedValue:
    kind: Literal['enclosure']
    lower: RationalNumber
    upper: RationalNumber


ComputedValue = ExactValue | EnclosedValue


@dataclass(frozen=True)
class GateResult:
    locator: GateLocator
    method: Literal['exact_binomial', 'weighted_hoeffding']
    direction: Literal['upper', 'lower']
    independent_clusters: int
    positive_weight_clusters: int
    observed_successes: int | None
    weighted_mean: RationalNumber
    squared_range_weight_sum: RationalNumber | None
    threshold: RationalNumber
    nominal_alpha: RationalNumber
    effective_alpha: RationalNumber
    raw_probability: ComputedValue
    confidence_bound: ComputedValue
    holm_rank: int | None
    holm_outcome: Outcome
    bound_outcome: Outcome
    outcome: Outcome


@dataclass(frozen=True)
class Certificate:
    schema: Literal['statistical_acceptance_certificate.v1']
    policy_sha256: str
    evidence_sha256: str
    authority: NumericAuthority
    family_alpha: RationalNumber
    accepted: bool
    results: tuple[GateResult, ...]


@dataclass(frozen=True)
class _Derived:
    gate: Gate
    observations: tuple[WeightedObservation, ...]
    threshold: Fraction
    alpha: Fraction
    probability: RationalInterval
    successes: int
    weighted_mean: Fraction
    squared_sum: Fraction | None
    exponent: Fraction | None


def _keys(value: Any, required: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != required:
        raise WireRejected(name + '_shape')
    return value


def _id(value: Any) -> str:
    if not isinstance(value, str) or not value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise WireRejected('identifier')
    return value


def _digest(value: Any) -> str:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise WireRejected('digest')
    return value


def _read(stream: BinaryIO, limit: int) -> bytes:
    if type(limit) is not int or limit < 1:
        raise WireRejected('transport_configuration')
    # A binary stream may legally return short reads; do not mistake one for EOF.
    chunks: list[bytes] = []
    count = 0
    while count <= limit:
        chunk = stream.read(limit + 1 - count)
        if type(chunk) is not bytes:
            raise WireRejected('binary_stream_required')
        if not chunk:
            return b''.join(chunks)
        count += len(chunk)
        if count > limit:
            raise WireRejected('transport_limit')
        chunks.append(chunk)
    raise WireRejected('transport_limit')


def _json(raw: bytes, limits: TransportLimits) -> Any:
    depth = members = string_size = 0
    quoted = escaped = False
    for byte in raw:
        if byte > 127:
            raise WireRejected('ascii_transport_required')
        if quoted:
            string_size += 1
            if string_size > limits.max_string_bytes:
                raise WireRejected('string_limit')
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted, string_size = True, 0
        elif byte in (91, 123):
            depth += 1
            if depth > limits.max_depth:
                raise WireRejected('nesting_limit')
        elif byte in (93, 125):
            depth -= 1
        elif byte in (44, 58):
            members += 1
            if members > limits.max_members:
                raise WireRejected('member_limit')

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise WireRejected('duplicate_json_key')
            result[key] = value
        return result

    def integer(token: str) -> int:
        if len(token) > limits.max_integer_digits or not re.fullmatch(r'0|[1-9][0-9]*', token):
            raise WireRejected('metadata_integer_limit')
        runtime_limit = sys.get_int_max_str_digits()
        if runtime_limit and len(token) > runtime_limit:
            raise WireRejected('metadata_integer_limit')
        return int(token)

    def no_number(_: str) -> None:
        raise WireRejected('floating_number_forbidden')

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_int=integer,
                          parse_float=no_number, parse_constant=no_number)
    except (json.JSONDecodeError, RecursionError) as error:
        raise WireRejected('json_invalid') from error


def _locator(value: Any) -> GateLocator:
    row = _keys(value, {'capability_fingerprint', 'cell_id', 'metric_id'}, 'locator')
    return GateLocator(_digest(row['capability_fingerprint']), _id(row['cell_id']), _id(row['metric_id']))


def locator_bytes(locator: GateLocator) -> bytes:
    return encode_typed_value(asdict(locator))


def _quantity(value: Any) -> CanonicalDecimalQuantity:
    row = _keys(value, {'encoding_spec_id', 'fixed_scale_value'}, 'decimal')
    if not isinstance(row['fixed_scale_value'], str):
        raise WireRejected('decimal_value')
    return CanonicalDecimalQuantity(_id(row['encoding_spec_id']), row['fixed_scale_value'])


def _spec(value: Any, limits: TransportLimits) -> EncodingSpec:
    row = _keys(value, {f.name for f in fields(EncodingSpec)}, 'spec')
    if (type(row['scale']) is not int or not 1 <= row['scale'] <= limits.max_precision
            or type(row['lower_inclusive']) is not bool or type(row['upper_inclusive']) is not bool
            or row['reject_inexact'] is not True or not isinstance(row['lower'], str) or not isinstance(row['upper'], str)):
        raise WireRejected('spec_value')
    return EncodingSpec(_id(row['encoding_spec_id']), _id(row['unit']), row['scale'],
                        row['lower'], row['upper'], row['lower_inclusive'], row['upper_inclusive'], True)


def _gate(value: Any) -> Gate:
    row = _keys(value, {f.name for f in fields(Gate)}, 'gate')
    if (type(row['method']) is not str or row['method'] not in {'exact_binomial', 'weighted_hoeffding'}
            or type(row['direction']) is not str or row['direction'] not in {'upper', 'lower'}
            or type(row['estimand']) is not str or row['estimand'] not in {'cluster_any_failure', 'cluster_macro_mean'}
            or type(row['minimum_clusters']) is not int or row['minimum_clusters'] < 1
            or type(row['iid_declared']) is not bool):
        raise WireRejected('gate_value')
    method: Literal['exact_binomial', 'weighted_hoeffding'] = 'exact_binomial' if row['method'] == 'exact_binomial' else 'weighted_hoeffding'
    direction: Literal['upper', 'lower'] = 'upper' if row['direction'] == 'upper' else 'lower'
    estimand: Literal['cluster_any_failure', 'cluster_macro_mean'] = 'cluster_any_failure' if row['estimand'] == 'cluster_any_failure' else 'cluster_macro_mean'
    return Gate(_locator(row['locator']), method, direction, estimand,
                _quantity(row['threshold']), _quantity(row['nominal_alpha']), row['minimum_clusters'],
                _id(row['threshold_spec_id']), _id(row['nominal_alpha_spec_id']),
                _id(row['lower_spec_id']), _id(row['upper_spec_id']),
                _id(row['weight_spec_id']), _id(row['event_value_spec_id']),
                row['iid_declared'])


def _membership(value: Any) -> Membership:
    row = _keys(value, {f.name for f in fields(Membership)}, 'membership')
    arrays = []
    for name in ('provenance_ids', 'expected_event_ids'):
        if type(row[name]) is not list or not row[name]:
            raise WireRejected('membership_value')
        items = tuple(_id(v) for v in row[name])
        if len(items) != len(set(items)):
            raise WireRejected('membership_duplicate')
        arrays.append(items)
    return Membership(_id(row['cluster_id']), _locator(row['locator']), arrays[0], arrays[1],
                      _quantity(row['weight']), _quantity(row['lower']), _quantity(row['upper']))


def _policy(raw: bytes, limits: TransportLimits) -> Policy:
    row = _keys(_json(raw, limits), {f.name for f in fields(Policy)}, 'policy')
    for name, ceiling in (('arithmetic_bits', limits.max_arithmetic_bits),
                          ('arithmetic_operations', limits.max_operations),
                          ('precision', limits.max_precision), ('output_cap', limits.max_output_bytes)):
        if type(row[name]) is not int or not 1 <= row[name] <= ceiling:
            raise WireRejected('policy_transport_ceiling')
    if not all(type(row[n]) is list and row[n] for n in ('specs', 'gates', 'memberships')):
        raise WireRejected('policy_collections')
    result = Policy(row['arithmetic_bits'], row['arithmetic_operations'], row['precision'], row['output_cap'],
                    _quantity(row['family_alpha']), _id(row['family_alpha_spec_id']),
                    tuple(_spec(v, limits) for v in row['specs']), tuple(_gate(v) for v in row['gates']),
                    tuple(_membership(v) for v in row['memberships']))
    if (len({s.encoding_spec_id for s in result.specs}) != len(result.specs)
            or len({g.locator for g in result.gates}) != len(result.gates)
            or len({(m.locator, m.cluster_id) for m in result.memberships}) != len(result.memberships)
            or {m.locator for m in result.memberships} != {g.locator for g in result.gates}
            or len({g.locator.capability_fingerprint for g in result.gates}) != 1):
        raise WireRejected('policy_duplicate_or_bijection')
    expected = [(m.locator, event) for m in result.memberships for event in m.expected_event_ids]
    if len(expected) != len(set(expected)):
        raise WireRejected('expected_event_duplicate')
    provenance_clusters: dict[str, str] = {}
    for member in result.memberships:
        for provenance in member.provenance_ids:
            if provenance in provenance_clusters and provenance_clusters[provenance] != member.cluster_id:
                raise WireRejected('dependent_clusters')
            provenance_clusters[provenance] = member.cluster_id
    return result


def _evidence(raw: bytes, limits: TransportLimits) -> Evidence:
    row = _keys(_json(raw, limits), {'events'}, 'evidence')
    if type(row['events']) is not list:
        raise WireRejected('events')
    events = []
    provenance: dict[str, str] = {}
    for value in row['events']:
        item = _keys(value, {f.name for f in fields(EvidenceEvent)}, 'event')
        event = EvidenceEvent(_id(item['event_id']), _id(item['provenance_id']), _locator(item['locator']),
                              None if item['value'] is None else _quantity(item['value']))
        if event.event_id in provenance and provenance[event.event_id] != event.provenance_id:
            raise WireRejected('event_provenance_mismatch')
        provenance[event.event_id] = event.provenance_id
        events.append(event)
    if len({(e.locator, e.event_id) for e in events}) != len(events):
        raise WireRejected('event_duplicate')
    return Evidence(tuple(events))


def _decimal(text: str, scale: int, meter: ArithmeticMeter) -> Fraction:
    if not isinstance(text, str) or not _DEC.fullmatch(text):
        raise WireRejected('decimal_invalid')
    whole, fractional = text.split('.')
    if len(fractional) != scale:
        raise WireRejected('decimal_scale')
    digits = (whole.lstrip('-') + fractional).lstrip('0')
    if not digits and whole.startswith('-'):
        raise WireRejected('decimal_negative_zero')
    coefficient = ('-' if whole.startswith('-') else '') + (digits or '0')
    value = parse_rational(coefficient, '1', meter)
    denominator = meter.pow(parse_rational('10', '1', meter), scale)
    return meter.div(value, denominator)


class _Quantities:
    def __init__(self, policy: Policy, meter: ArithmeticMeter):
        self.meter = meter
        self.specs = {s.encoding_spec_id: s for s in policy.specs}
        self.bounds = {}
        for spec in policy.specs:
            lower, upper = _decimal(spec.lower, spec.scale, meter), _decimal(spec.upper, spec.scale, meter)
            if meter.compare(lower, upper) >= 0:
                raise WireRejected('spec_range')
            self.bounds[spec.encoding_spec_id] = (lower, upper)

    def read(self, quantity: CanonicalDecimalQuantity, expected_spec: str) -> Fraction:
        if quantity.encoding_spec_id != expected_spec or expected_spec not in self.specs:
            raise WireRejected('encoding_spec_binding')
        spec = self.specs[expected_spec]
        result = _decimal(quantity.fixed_scale_value, spec.scale, self.meter)
        lower, upper = self.bounds[expected_spec]
        low, high = self.meter.compare(result, lower), self.meter.compare(result, upper)
        if low < 0 or high > 0 or (low == 0 and not spec.lower_inclusive) or (high == 0 and not spec.upper_inclusive):
            raise WireRejected('decimal_range')
        return result

    def unit(self, spec_id: str) -> str:
        if spec_id not in self.specs:
            raise WireRejected('encoding_spec_binding')
        return self.specs[spec_id].unit


def _number(value: Fraction) -> RationalNumber:
    return RationalNumber(value.numerator, value.denominator)


def _computed(value: RationalInterval) -> ComputedValue:
    if value.lower == value.upper:
        return ExactValue('exact', _number(value.lower))
    return EnclosedValue('enclosure', _number(value.lower), _number(value.upper))


def _validate_context(policy: Policy, binding: HeldBinding) -> None:
    context = binding.context
    if (context.authority != binding.expected_authority
            or policy.specs != context.numeric_encoding_specs
            or policy.family_alpha != context.family_alpha
            or policy.family_alpha_spec_id != context.family_alpha_spec_id
            or policy.gates != tuple(g.gate for g in context.expected_gates)
            or policy.memberships != context.expected_clusters):
        raise WireRejected('numeric_context_policy')
    for expected in context.expected_gates:
        if (type(expected.iid_bernoulli_clusters_proven) is not bool
                or expected.gate.locator.capability_fingerprint != context.authority.capability_fingerprint
                or expected.gate.iid_declared != expected.iid_bernoulli_clusters_proven
                or (expected.gate.method == 'exact_binomial' and not expected.iid_bernoulli_clusters_proven)):
            raise WireRejected('numeric_context_gate')


def _derive(policy: Policy, evidence: Evidence, context: PreverifiedNumericCertificationContext,
            meter: ArithmeticMeter, q: _Quantities) -> tuple[_Derived, ...]:
    by_event = {(e.locator, e.event_id): e for e in evidence.events}
    expected = {(m.locator, e) for m in context.expected_clusters for e in m.expected_event_ids}
    if set(by_event) != expected:
        raise WireRejected('evidence_event_bijection')
    derived = []
    for preverified in sorted(context.expected_gates, key=lambda g: locator_bytes(g.gate.locator)):
        gate = preverified.gate
        if gate.estimand == 'cluster_any_failure' and gate.direction != 'upper':
            raise WireRejected('safety_gate_direction')
        if q.unit(gate.nominal_alpha_spec_id) != 'probability' or q.unit(gate.weight_spec_id) != 'weight':
            raise WireRejected('gate_units')
        if len({q.unit(s) for s in (gate.threshold_spec_id, gate.lower_spec_id, gate.upper_spec_id, gate.event_value_spec_id)}) != 1:
            raise WireRejected('metric_unit')
        threshold = q.read(gate.threshold, gate.threshold_spec_id)
        alpha = q.read(gate.nominal_alpha, gate.nominal_alpha_spec_id)
        if meter.compare(alpha, _ZERO) <= 0 or meter.compare(alpha, _ONE) > 0:
            raise WireRejected('alpha')
        members = sorted((m for m in policy.memberships if m.locator == gate.locator), key=lambda m: m.cluster_id)
        if len(members) < gate.minimum_clusters:
            raise WireRejected('minimum_clusters')
        observations = []
        successes = 0
        total_weight = mean = _ZERO
        for member in members:
            lower = q.read(member.lower, gate.lower_spec_id)
            upper = q.read(member.upper, gate.upper_spec_id)
            weight = q.read(member.weight, gate.weight_spec_id)
            if meter.compare(lower, upper) >= 0 or meter.compare(weight, _ZERO) < 0:
                raise WireRejected('member_range_or_weight')
            if meter.compare(threshold, lower) < 0 or meter.compare(threshold, upper) > 0:
                raise WireRejected('threshold_range')
            values = []
            for event_id in member.expected_event_ids:
                event = by_event[(gate.locator, event_id)]
                if event.provenance_id not in member.provenance_ids:
                    raise WireRejected('evidence_membership')
                if event.value is None:
                    value = _ONE if gate.estimand == 'cluster_any_failure' else (upper if gate.direction == 'upper' else lower)
                else:
                    value = q.read(event.value, gate.event_value_spec_id)
                if meter.compare(value, lower) < 0 or meter.compare(value, upper) > 0:
                    raise WireRejected('event_range')
                if gate.estimand == 'cluster_any_failure' and value != _ZERO and value != _ONE:
                    raise WireRejected('binary_outcome')
                values.append(value)
            if gate.estimand == 'cluster_any_failure':
                value = _ONE if any(v.numerator != 0 for v in values) else _ZERO
            else:
                value = _ZERO
                for item in values:
                    value = meter.add(value, item)
                value = meter.div(value, parse_rational(str(len(values)), '1', meter))
            observations.append(WeightedObservation(value, weight, lower, upper))
            successes += value == _ONE
            total_weight = meter.add(total_weight, weight)
            mean = meter.add(mean, meter.mul(weight, value))
        if meter.compare(total_weight, _ONE) != 0:
            raise WireRejected('weights_not_normalized')
        if gate.method == 'exact_binomial':
            equal_weight = meter.div(_ONE, parse_rational(str(len(observations)), '1', meter))
            if (not preverified.iid_bernoulli_clusters_proven or gate.estimand != 'cluster_any_failure'
                    or any(meter.compare(o.weight, equal_weight) != 0 or o.lower != _ZERO or o.upper != _ONE for o in observations)):
                raise WireRejected('binomial_compatibility')
            # Upper claims reject a high null mean using the left tail; lower use right.
            tail = 'less_or_equal' if gate.direction == 'upper' else 'greater_or_equal'
            probability = exact_binomial_tail(len(observations), successes, threshold, tail, meter)
            interval, squared, exponent = RationalInterval(probability, probability), None, None
        else:
            result = weighted_hoeffding(tuple(observations), threshold, gate.direction, policy.precision, meter)
            interval, squared, exponent = result.probability, result.squared_range_weight_sum, result.exponent
        derived.append(_Derived(gate, tuple(observations), threshold, alpha, interval, successes, mean, squared, exponent))
    return tuple(derived)


def _build(policy: Policy, evidence: Evidence, binding: HeldBinding, meter: ArithmeticMeter) -> Certificate:
    quantities = _Quantities(policy, meter)
    if quantities.unit(policy.family_alpha_spec_id) != 'probability':
        raise WireRejected('family_alpha_unit')
    family = quantities.read(policy.family_alpha, policy.family_alpha_spec_id)
    derived = _derive(policy, evidence, binding.context, meter, quantities)
    claims = tuple(HolmClaim(locator_bytes(d.gate.locator), d.alpha, d.probability, d.exponent) for d in derived)
    decisions = holm_complete(claims, tuple(locator_bytes(g.gate.locator) for g in binding.context.expected_gates), family, meter)
    by_locator = {d.locator_bytes: d for d in decisions}
    results = []
    for item in derived:
        decision = by_locator[locator_bytes(item.gate.locator)]
        if item.gate.method == 'exact_binomial':
            bound = clopper_pearson_bound(len(item.observations), item.successes, decision.effective_alpha,
                                         item.gate.direction, policy.precision, meter)
        else:
            bound = invert_weighted_hoeffding(item.observations, item.threshold, item.gate.direction,
                                             decision.effective_alpha, policy.precision, policy.precision, meter)
        if item.gate.direction == 'upper':
            bound_outcome: Outcome = 'pass' if meter.compare(bound.upper, item.threshold) <= 0 else ('fail' if meter.compare(bound.lower, item.threshold) > 0 else 'inconclusive')
        else:
            bound_outcome = 'pass' if meter.compare(bound.lower, item.threshold) >= 0 else ('fail' if meter.compare(bound.upper, item.threshold) < 0 else 'inconclusive')
        combined: Outcome = 'pass' if decision.outcome == bound_outcome == 'pass' else ('fail' if 'fail' in (decision.outcome, bound_outcome) else 'inconclusive')
        results.append(GateResult(
            item.gate.locator, item.gate.method, item.gate.direction, len(item.observations),
            sum(o.weight.numerator > 0 for o in item.observations),
            item.successes if item.gate.method == 'exact_binomial' else None,
            _number(item.weighted_mean), None if item.squared_sum is None else _number(item.squared_sum),
            _number(item.threshold), _number(item.alpha), _number(decision.effective_alpha),
            _computed(item.probability), _computed(bound), decision.rank,
            decision.outcome, bound_outcome, combined,
        ))
    return Certificate('statistical_acceptance_certificate.v1', binding.policy_sha256, binding.evidence_sha256,
                       binding.expected_authority, _number(family), all(r.outcome == 'pass' for r in results), tuple(results))


def _count_string(value: str) -> int:
    size = 2
    for char in value:
        if char in ('"', '\\', '\b', '\t', '\n', '\f', '\r'):
            size += 2
        elif ord(char) < 32:
            size += 6
        elif ord(char) < 128:
            size += 1
        elif ord(char) < 0x800:
            size += 2
        elif 0xD800 <= ord(char) <= 0xDFFF:
            raise WireRejected('certificate_string')
        elif ord(char) < 0x10000:
            size += 3
        else:
            size += 4
    return size


def _integer_digits(value: int, meter: ArithmeticMeter) -> int:
    meter.reserve(max(1, value.bit_length()))
    meter.allocating('integer_digit_count')
    magnitude = abs(value)
    digits = 1 + (value < 0)
    while magnitude >= 10:
        meter.reserve(max(1, magnitude.bit_length()))
        meter.allocating('integer_digit_count')
        magnitude //= 10
        digits += 1
    runtime_limit = sys.get_int_max_str_digits()
    if runtime_limit and digits - (value < 0) > runtime_limit:
        raise WireRejected('resource_limit')
    return digits


def _count_ctv(value: Any, meter: ArithmeticMeter) -> int:
    if value is None:
        return 4
    if type(value) is bool:
        return 4 if value else 5
    if type(value) is str:
        return _count_string(value)
    if type(value) is int:
        return len('{"$type":"integer","value":""}') + _integer_digits(value, meter)
    if type(value) in (tuple, list):
        tag = 'tuple' if type(value) is tuple else 'list'
        return len('{"$type":"' + tag + '","items":[') + sum(_count_ctv(v, meter) for v in value) + max(0, len(value) - 1) + 2
    if type(value) is dict:
        return len('{"$type":"map","entries":[') + sum(_count_string(k) + _count_ctv(v, meter) + 3 for k, v in value.items()) + max(0, len(value) - 1) + 2
    if is_dataclass(value) and not isinstance(value, type):
        declared = fields(value)
        return len('{"$type":"map","entries":[') + sum(
            _count_string(field.name) + _count_ctv(getattr(value, field.name), meter) + 3
            for field in declared
        ) + max(0, len(declared) - 1) + 2
    raise WireRejected('certificate_value')


def _evaluate(policy_stream: BinaryIO, evidence_stream: BinaryIO, binding: HeldBinding, limits: TransportLimits) -> tuple[Certificate, bytes]:
    if type(binding) is not HeldBinding or type(limits) is not TransportLimits:
        raise WireRejected('authority_configuration')
    policy_bytes = _read(policy_stream, limits.max_policy_bytes)
    evidence_bytes = _read(evidence_stream, limits.max_evidence_bytes)
    # Independently held input identity is checked before any JSON/numeric parse.
    if sha256(policy_bytes).hexdigest() != binding.policy_sha256 or sha256(evidence_bytes).hexdigest() != binding.evidence_sha256:
        raise WireRejected('held_authority_digest')
    policy, evidence = _policy(policy_bytes, limits), _evidence(evidence_bytes, limits)
    _validate_context(policy, binding)
    meter = ArithmeticMeter(ArithmeticBudget(policy.arithmetic_bits, policy.arithmetic_operations))
    try:
        certificate = _build(policy, evidence, binding, meter)
        count = _count_ctv(certificate, meter)
    except ValueError as error:
        if isinstance(error, WireRejected):
            raise
        raise WireRejected(str(error)) from error
    if count > policy.output_cap:
        raise WireRejected('output_cap')
    if MATERIALIZER_HOOK is not None:
        MATERIALIZER_HOOK()
    wire = asdict(certificate)
    if ENCODER_HOOK is not None:
        ENCODER_HOOK()
    output = encode_typed_value(wire)
    if len(output) != count:
        raise WireRejected('ctv_count_mismatch')
    return certificate, output


def evaluate_certificate(policy_stream: BinaryIO, evidence_stream: BinaryIO, binding: HeldBinding, limits: TransportLimits) -> bytes:
    return _evaluate(policy_stream, evidence_stream, binding, limits)[1]


def verify_certificate(candidate_stream: BinaryIO, policy_stream: BinaryIO, evidence_stream: BinaryIO,
                       binding: HeldBinding, transport_limits: TransportLimits) -> Certificate:
    candidate = _read(candidate_stream, transport_limits.max_candidate_bytes)
    certificate, expected = _evaluate(policy_stream, evidence_stream, binding, transport_limits)
    if candidate != expected:
        raise WireRejected('certificate_mismatch')
    return certificate

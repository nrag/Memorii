"""Executable, nonproduction boundary for numeric acceptance certificates.

This module deliberately has no production imports.  It demonstrates the
closed wire and verification contract required before a future canonical
promotion can select real policy values or register a production CTV schema.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from fractions import Fraction
from hashlib import sha256
from io import BytesIO
import json
from math import comb
import re
from typing import Any, BinaryIO, Literal, Union, get_args, get_origin, get_type_hints


_RATIONAL = re.compile(r"(?:0|-[1-9][0-9]*|[1-9][0-9]*)/(?:[1-9][0-9]*)\Z")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class BoundaryRejected(ValueError):
    """A closed-boundary rejection; callers must treat it as inconclusive."""


class LimitExceeded(BoundaryRejected):
    pass


@dataclass(frozen=True)
class TransportLimit:
    max_document_bytes: int


@dataclass(frozen=True)
class WorkBudget:
    max_document_bytes: int
    max_contributions: int
    max_numeric_digits: int
    max_numeric_bits: int
    max_operations: int
    max_certificate_bytes: int


@dataclass(frozen=True)
class GateLocator:
    capability_id: str
    coverage_cell_id: str
    metric_id: str


@dataclass(frozen=True)
class RationalPoint:
    value: str


@dataclass(frozen=True)
class RationalEnclosure:
    lower: str
    upper: str


@dataclass(frozen=True)
class Contribution:
    contribution_id: str
    cluster_id: str
    value: RationalPoint
    weight: RationalPoint
    lower: RationalPoint
    upper: RationalPoint


@dataclass(frozen=True)
class ContributionAuthority:
    authority_id: str
    contributions: tuple[Contribution, ...]


@dataclass(frozen=True)
class GateBinding:
    locator: GateLocator
    proof_kind: Literal["exact_binomial", "weighted_hoeffding"]
    comparison: Literal["upper_at_most", "lower_at_least"]
    threshold: RationalPoint
    contribution_authority_digest: str


@dataclass(frozen=True)
class NumericManifest:
    manifest_id: str
    ctv_profile_id: str
    ctv_profile_version: int
    budget: WorkBudget
    gates: tuple[GateBinding, ...]


@dataclass(frozen=True)
class ExactBinomialProof:
    kind: Literal["exact_binomial"]
    contribution_ids: tuple[str, ...]
    trial_count: int
    success_count: int
    null_probability: RationalPoint
    tail: Literal["ge", "le"]
    result: RationalPoint


@dataclass(frozen=True)
class WeightedHoeffdingProof:
    kind: Literal["weighted_hoeffding"]
    contribution_ids: tuple[str, ...]
    margin: RationalPoint
    squared_range_weight_sum: RationalPoint
    terms: int
    result: RationalEnclosure


Proof = Union[ExactBinomialProof, WeightedHoeffdingProof]


@dataclass(frozen=True)
class ProofBundle:
    locator: GateLocator
    binding_digest: str
    contribution_authority_digest: str
    proof: Proof
    reported_probability: RationalEnclosure


@dataclass(frozen=True)
class CandidateCertificate:
    schema: Literal["numeric_acceptance_certificate.v1"]
    manifest_digest: str
    contribution_authority_digest: str
    bundles: tuple[ProofBundle, ...]


class Tripwires:
    """Observable pre-allocation markers used only by this feasibility proof."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def before_document_parse(self) -> None:
        self.events.append("before_document_parse")

    def before_integer(self, token: str) -> None:
        self.events.append("before_integer")
        self.events.append(f"before_integer:{token}")

    def before_fraction(self, token: str) -> None:
        self.events.append("before_fraction")
        self.events.append(f"before_fraction:{token}")

    def before_arithmetic(self) -> None:
        self.events.append("before_arithmetic")

    def before_certificate_serialization(self) -> None:
        self.events.append("before_certificate_serialization")


class Meter:
    def __init__(self, budget: WorkBudget, tripwires: Tripwires) -> None:
        self.budget = budget
        self.tripwires = tripwires
        self.operations = 0

    def charge(self, amount: int = 1) -> None:
        self.operations += amount
        if self.operations > self.budget.max_operations:
            raise LimitExceeded("resource_limit")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"


def _digest(domain: str, value: Any) -> str:
    return sha256(domain.encode("ascii") + b"\0" + _canonical_json(value)).hexdigest()


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise BoundaryRejected(f"invalid_{field_name}")
    return value


def _digest_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise BoundaryRejected(f"invalid_{field_name}")
    return value


def _strict_keys(value: Any, required: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != required:
        raise BoundaryRejected(f"invalid_{name}_fields")
    return value


def _bounded_read(stream: BinaryIO, limit: int) -> bytes:
    if limit < 0:
        raise BoundaryRejected("invalid_transport_limit")
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise LimitExceeded("transport_limit")
    return data


def _project_rational(text: Any, budget: WorkBudget, wires: Tripwires) -> None:
    if not isinstance(text, str) or not _RATIONAL.fullmatch(text):
        raise BoundaryRejected("malformed_rational")
    if len(text.replace("/", "")) > budget.max_numeric_digits:
        raise LimitExceeded("numeric_digit_limit")
    numerator, denominator = text.split("/", 1)
    # Bit length can be bounded from decimal digits without creating an integer.
    max_digits = (budget.max_numeric_bits * 30103) // 100000 + 1
    if len(numerator.lstrip("-")) > max_digits or len(denominator) > max_digits:
        raise LimitExceeded("numeric_bit_limit")
    wires.before_integer(text)


def _fraction(text: str, budget: WorkBudget, meter: Meter) -> Fraction:
    _project_rational(text, budget, meter.tripwires)
    numerator, denominator = text.split("/", 1)
    # int and Fraction happen only after the lexical/digit/bit projection.
    meter.tripwires.before_fraction(text)
    value = Fraction(int(numerator), int(denominator))
    if value.denominator <= 0 or f"{value.numerator}/{value.denominator}" != text:
        raise BoundaryRejected("noncanonical_rational")
    if value.numerator.bit_length() > budget.max_numeric_bits or value.denominator.bit_length() > budget.max_numeric_bits:
        raise LimitExceeded("numeric_bit_limit")
    meter.charge()
    return value


def _point(value: Any, budget: WorkBudget, meter: Meter) -> RationalPoint:
    item = _strict_keys(value, {"value"}, "rational_point")
    _fraction(item["value"], budget, meter)
    return RationalPoint(item["value"])


def _enclosure(value: Any, budget: WorkBudget, meter: Meter) -> RationalEnclosure:
    item = _strict_keys(value, {"lower", "upper"}, "rational_enclosure")
    lower, upper = _fraction(item["lower"], budget, meter), _fraction(item["upper"], budget, meter)
    if lower > upper:
        raise BoundaryRejected("reversed_enclosure")
    return RationalEnclosure(item["lower"], item["upper"])


def _locator(value: Any) -> GateLocator:
    item = _strict_keys(value, {"capability_id", "coverage_cell_id", "metric_id"}, "gate_locator")
    return GateLocator(*(_identifier(item[name], name) for name in ("capability_id", "coverage_cell_id", "metric_id")))


def _locator_ctv_bytes(locator: GateLocator) -> bytes:
    """Exact CTV-v2 map body used for locator sorting and locator digests."""
    return _canonical_json({"$type": "map", "entries": [
        ["capability_id", locator.capability_id],
        ["coverage_cell_id", locator.coverage_cell_id],
        ["metric_id", locator.metric_id],
    ]})


def locator_digest(locator: GateLocator) -> str:
    return sha256(b"memorii:numeric-gate-locator:v1\0" + _locator_ctv_bytes(locator)).hexdigest()


def _budget(value: Any) -> WorkBudget:
    names = {"max_document_bytes", "max_contributions", "max_numeric_digits", "max_numeric_bits", "max_operations", "max_certificate_bytes"}
    item = _strict_keys(value, names, "work_budget")
    parsed: list[int] = []
    for name in sorted(names):
        number = item[name]
        if type(number) is not int or number <= 0:
            raise BoundaryRejected("invalid_budget")
        parsed.append(number)
    return WorkBudget(**{name: item[name] for name in names})


def _contribution(value: Any, budget: WorkBudget, meter: Meter) -> Contribution:
    item = _strict_keys(value, {"contribution_id", "cluster_id", "value", "weight", "lower", "upper"}, "contribution")
    result = Contribution(
        _identifier(item["contribution_id"], "contribution_id"), _identifier(item["cluster_id"], "cluster_id"),
        _point(item["value"], budget, meter), _point(item["weight"], budget, meter),
        _point(item["lower"], budget, meter), _point(item["upper"], budget, meter),
    )
    weight, lower, upper, observed = (_fraction(x.value, budget, meter) for x in (result.weight, result.lower, result.upper, result.value))
    meter.tripwires.before_arithmetic()
    if weight < 0 or lower > upper or not lower <= observed <= upper:
        raise BoundaryRejected("invalid_contribution")
    return result


def _contribution_authority(value: Any, budget: WorkBudget, meter: Meter) -> ContributionAuthority:
    item = _strict_keys(value, {"authority_id", "contributions"}, "contribution_authority")
    if not isinstance(item["contributions"], list) or not item["contributions"] or len(item["contributions"]) > budget.max_contributions:
        raise LimitExceeded("contribution_limit")
    contributions = tuple(_contribution(row, budget, meter) for row in item["contributions"])
    if len({row.contribution_id for row in contributions}) != len(contributions):
        raise BoundaryRejected("duplicate_contribution")
    return ContributionAuthority(_identifier(item["authority_id"], "authority_id"), contributions)


def _binding(value: Any, budget: WorkBudget, meter: Meter) -> GateBinding:
    item = _strict_keys(value, {"locator", "proof_kind", "comparison", "threshold", "contribution_authority_digest"}, "gate_binding")
    if item["proof_kind"] not in {"exact_binomial", "weighted_hoeffding"} or item["comparison"] not in {"upper_at_most", "lower_at_least"}:
        raise BoundaryRejected("unsupported_gate")
    return GateBinding(_locator(item["locator"]), item["proof_kind"], item["comparison"], _point(item["threshold"], budget, meter), _digest_text(item["contribution_authority_digest"], "contribution_authority_digest"))


def _manifest(value: Any, budget: WorkBudget, meter: Meter) -> NumericManifest:
    item = _strict_keys(value, {"manifest_id", "ctv_profile_id", "ctv_profile_version", "budget", "gates"}, "numeric_manifest")
    if item["ctv_profile_id"] != "semantic_ingestion_typed_value" or item["ctv_profile_version"] != 2:
        raise BoundaryRejected("unsupported_ctv_profile")
    embedded_budget = _budget(item["budget"])
    if embedded_budget != budget:
        raise BoundaryRejected("manifest_budget_mismatch")
    if not isinstance(item["gates"], list) or not item["gates"]:
        raise BoundaryRejected("empty_gates")
    gates = tuple(_binding(row, budget, meter) for row in item["gates"])
    if tuple(sorted(gates, key=lambda gate: _locator_ctv_bytes(gate.locator))) != gates:
        raise BoundaryRejected("noncanonical_locator_order")
    if len({locator_digest(gate.locator) for gate in gates}) != len(gates):
        raise BoundaryRejected("duplicate_gate_locator")
    return NumericManifest(_identifier(item["manifest_id"], "manifest_id"), item["ctv_profile_id"], item["ctv_profile_version"], embedded_budget, gates)


def _binomial_tail(count: int, successes: int, probability: Fraction, tail: str, meter: Meter) -> Fraction:
    if count <= 0 or not 0 <= successes <= count or probability < 0 or probability > 1 or tail not in {"ge", "le"}:
        raise BoundaryRejected("invalid_binomial_proof")
    indices = range(successes, count + 1) if tail == "ge" else range(successes + 1)
    total = Fraction()
    for index in indices:
        meter.tripwires.before_arithmetic()
        meter.charge(4)
        total += Fraction(comb(count, index)) * probability ** index * (1 - probability) ** (count - index)
    return total


def _exp_enclosure(exponent: Fraction, terms: int, meter: Meter) -> tuple[Fraction, Fraction]:
    if exponent < 0 or type(terms) is not int or terms < 1 or Fraction(terms + 2) <= exponent:
        raise BoundaryRejected("invalid_hoeffding_proof")
    term = partial = Fraction(1)
    for index in range(1, terms + 1):
        meter.tripwires.before_arithmetic()
        meter.charge(3)
        term = term * exponent / index
        partial += term
    omitted_first = term * exponent / (terms + 1)
    upper_exp = partial + omitted_first / (1 - exponent / (terms + 2))
    return Fraction(1, 1) / upper_exp, Fraction(1, 1) / partial


def _proof(value: Any, budget: WorkBudget, meter: Meter) -> Proof:
    if not isinstance(value, dict) or value.get("kind") not in {"exact_binomial", "weighted_hoeffding"}:
        raise BoundaryRejected("unsupported_proof")
    if value["kind"] == "exact_binomial":
        item = _strict_keys(value, {"kind", "contribution_ids", "trial_count", "success_count", "null_probability", "tail", "result"}, "exact_binomial_proof")
        if type(item["trial_count"]) is not int or type(item["success_count"]) is not int or item["tail"] not in {"ge", "le"}:
            raise BoundaryRejected("invalid_binomial_proof")
        if not isinstance(item["contribution_ids"], list):
            raise BoundaryRejected("invalid_contribution_pairing")
        return ExactBinomialProof(item["kind"], tuple(_identifier(x, "contribution_id") for x in item["contribution_ids"]), item["trial_count"], item["success_count"], _point(item["null_probability"], budget, meter), item["tail"], _point(item["result"], budget, meter))
    item = _strict_keys(value, {"kind", "contribution_ids", "margin", "squared_range_weight_sum", "terms", "result"}, "weighted_hoeffding_proof")
    if type(item["terms"]) is not int:
        raise BoundaryRejected("invalid_hoeffding_proof")
    if not isinstance(item["contribution_ids"], list):
        raise BoundaryRejected("invalid_contribution_pairing")
    return WeightedHoeffdingProof(item["kind"], tuple(_identifier(x, "contribution_id") for x in item["contribution_ids"]), _point(item["margin"], budget, meter), _point(item["squared_range_weight_sum"], budget, meter), item["terms"], _enclosure(item["result"], budget, meter))


def _bundle(value: Any, budget: WorkBudget, meter: Meter) -> ProofBundle:
    item = _strict_keys(value, {"locator", "binding_digest", "contribution_authority_digest", "proof", "reported_probability"}, "proof_bundle")
    return ProofBundle(_locator(item["locator"]), _digest_text(item["binding_digest"], "binding_digest"), _digest_text(item["contribution_authority_digest"], "contribution_authority_digest"), _proof(item["proof"], budget, meter), _enclosure(item["reported_probability"], budget, meter))


def _candidate(value: Any, budget: WorkBudget, meter: Meter) -> CandidateCertificate:
    item = _strict_keys(value, {"schema", "manifest_digest", "contribution_authority_digest", "bundles"}, "candidate_certificate")
    if item["schema"] != "numeric_acceptance_certificate.v1" or not isinstance(item["bundles"], list) or not item["bundles"]:
        raise BoundaryRejected("invalid_candidate")
    bundles = tuple(_bundle(row, budget, meter) for row in item["bundles"])
    return CandidateCertificate(item["schema"], _digest_text(item["manifest_digest"], "manifest_digest"), _digest_text(item["contribution_authority_digest"], "contribution_authority_digest"), bundles)


def _wire(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_wire(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {name: _wire(item) for name, item in asdict(value).items()}
    return value


def contribution_authority_digest(authority: ContributionAuthority) -> str:
    return _digest("memorii:numeric-contribution-authority:v1", _wire(authority))


def binding_digest(binding: GateBinding) -> str:
    return _digest("memorii:numeric-gate-binding:v1", _wire(binding))


def manifest_digest(manifest: NumericManifest) -> str:
    return _digest("memorii:numeric-manifest:v1", _wire(manifest))


def _verify_bundle(bundle: ProofBundle, binding: GateBinding, authority: ContributionAuthority, budget: WorkBudget, meter: Meter) -> None:
    if bundle.locator != binding.locator or bundle.binding_digest != binding_digest(binding) or bundle.contribution_authority_digest != contribution_authority_digest(authority):
        raise BoundaryRejected("binding_or_contribution_mismatch")
    if (binding.proof_kind == "exact_binomial") != isinstance(bundle.proof, ExactBinomialProof):
        raise BoundaryRejected("proof_kind_mismatch")
    by_id = {contribution.contribution_id: contribution for contribution in authority.contributions}
    ids = bundle.proof.contribution_ids
    if not ids or len(ids) != len(set(ids)) or set(ids) != set(by_id):
        raise BoundaryRejected("invalid_contribution_pairing")
    reported_lower, reported_upper = (_fraction(item, budget, meter) for item in (bundle.reported_probability.lower, bundle.reported_probability.upper))
    if isinstance(bundle.proof, ExactBinomialProof):
        observed = [_fraction(by_id[item].value.value, budget, meter) for item in ids]
        if bundle.proof.trial_count != len(observed) or any(value not in {Fraction(), Fraction(1)} for value in observed) or bundle.proof.success_count != sum(value == 1 for value in observed):
            raise BoundaryRejected("binomial_evidence_mismatch")
        probability = _fraction(bundle.proof.null_probability.value, budget, meter)
        actual = _binomial_tail(bundle.proof.trial_count, bundle.proof.success_count, probability, bundle.proof.tail, meter)
        result = _fraction(bundle.proof.result.value, budget, meter)
        if actual != result or reported_lower != actual or reported_upper != actual:
            raise BoundaryRejected("binomial_result_mismatch")
    else:
        margin, squared_sum = (_fraction(item.value, budget, meter) for item in (bundle.proof.margin, bundle.proof.squared_range_weight_sum))
        derived_squared_sum = sum((_fraction(by_id[item].weight.value, budget, meter) ** 2 * (_fraction(by_id[item].upper.value, budget, meter) - _fraction(by_id[item].lower.value, budget, meter)) ** 2 for item in ids), Fraction())
        if squared_sum <= 0 or squared_sum != derived_squared_sum:
            raise BoundaryRejected("invalid_hoeffding_proof")
        exponent = 2 * max(Fraction(), margin) * max(Fraction(), margin) / squared_sum
        lower, upper = _exp_enclosure(exponent, bundle.proof.terms, meter)
        proof_lower, proof_upper = (_fraction(item, budget, meter) for item in (bundle.proof.result.lower, bundle.proof.result.upper))
        if (lower, upper) != (proof_lower, proof_upper) or (reported_lower, reported_upper) != (lower, upper):
            raise BoundaryRejected("hoeffding_result_mismatch")
    threshold = _fraction(binding.threshold.value, budget, meter)
    if binding.comparison == "upper_at_most" and reported_upper > threshold:
        raise BoundaryRejected("gate_does_not_pass")
    if binding.comparison == "lower_at_least" and reported_lower < threshold:
        raise BoundaryRejected("gate_does_not_pass")


def verify_serialized_certificate(
    serialized: bytes,
    transport: TransportLimit,
    independent_manifest: NumericManifest,
    independent_contributions: ContributionAuthority,
    tripwires: Tripwires | None = None,
) -> CandidateCertificate:
    """The only public feasibility verifier; every mutation calls this entrypoint."""
    wires = tripwires or Tripwires()
    budget = independent_manifest.budget
    if transport.max_document_bytes != budget.max_document_bytes:
        raise BoundaryRejected("transport_manifest_limit_mismatch")
    if not independent_contributions.contributions or len(independent_contributions.contributions) > budget.max_contributions:
        raise LimitExceeded("contribution_limit")
    payload = _bounded_read(BytesIO(serialized), transport.max_document_bytes)
    wires.before_document_parse()
    try:
        decoded = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BoundaryRejected("malformed_certificate") from error
    meter = Meter(budget, wires)
    candidate = _candidate(decoded, budget, meter)
    if candidate.manifest_digest != manifest_digest(independent_manifest) or candidate.contribution_authority_digest != contribution_authority_digest(independent_contributions):
        raise BoundaryRejected("authority_digest_mismatch")
    by_locator = {bundle.locator: bundle for bundle in candidate.bundles}
    if len(by_locator) != len(candidate.bundles) or set(by_locator) != {binding.locator for binding in independent_manifest.gates}:
        raise BoundaryRejected("gate_bijection_mismatch")
    for binding in independent_manifest.gates:
        _verify_bundle(by_locator[binding.locator], binding, independent_contributions, budget, meter)
    return candidate


def serialize_candidate(candidate: CandidateCertificate, budget: WorkBudget, wires: Tripwires) -> bytes:
    """Preflight the exact ASCII projection before allocating certificate bytes."""
    raw = _wire(candidate)
    # All schema strings are ASCII-safe; this projected count is the exact JSON count.
    projected = len(_canonical_json(raw))
    if projected > budget.max_certificate_bytes:
        raise LimitExceeded("certificate_limit")
    wires.before_certificate_serialization()
    return _canonical_json(raw)


def generated_field_table() -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for model in (TransportLimit, WorkBudget, GateLocator, RationalPoint, RationalEnclosure, Contribution, ContributionAuthority, GateBinding, NumericManifest, ExactBinomialProof, WeightedHoeffdingProof, ProofBundle, CandidateCertificate):
        hints = get_type_hints(model)
        result[model.__name__] = [{"field": member.name, "type": str(hints[member.name]).replace("typing.", "")} for member in fields(model)]
    return result

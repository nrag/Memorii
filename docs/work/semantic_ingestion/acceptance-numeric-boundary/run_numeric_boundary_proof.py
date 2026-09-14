"""Generate and verify the numeric-boundary candidate and its attack matrix."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

from numeric_boundary_contract import (
    BoundaryRejected,
    CandidateCertificate,
    Contribution,
    ContributionAuthority,
    ExactBinomialProof,
    GateBinding,
    GateLocator,
    LimitExceeded,
    NumericManifest,
    ProofBundle,
    RationalEnclosure,
    RationalPoint,
    TransportLimit,
    Tripwires,
    WeightedHoeffdingProof,
    WorkBudget,
    _exp_enclosure,
    _wire,
    binding_digest,
    contribution_authority_digest,
    generated_field_table,
    manifest_digest,
    serialize_candidate,
    verify_serialized_certificate,
)

ROOT = Path(__file__).parent


def rational(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def make_authority() -> ContributionAuthority:
    # These values are only synthetic boundary vectors, not acceptance policy.
    point = RationalPoint
    return ContributionAuthority(
        "synthetic_authority",
        (Contribution("synthetic_contribution_a", "synthetic_cluster_a", point("1/1"), point("1/2"), point("0/1"), point("1/1")), Contribution("synthetic_contribution_b", "synthetic_cluster_b", point("1/1"), point("1/2"), point("0/1"), point("1/1"))),
    )


def make_manifest(authority: ContributionAuthority, budget: WorkBudget) -> NumericManifest:
    authority_digest = contribution_authority_digest(authority)
    bindings = (
        GateBinding(GateLocator("synthetic_capability", "synthetic_cell", "binomial_metric"), "exact_binomial", "upper_at_most", RationalPoint("1/2"), authority_digest),
        GateBinding(GateLocator("synthetic_capability", "synthetic_cell", "hoeffding_metric"), "weighted_hoeffding", "upper_at_most", RationalPoint("1/1"), authority_digest),
    )
    return NumericManifest("synthetic_manifest", "semantic_ingestion_typed_value", 2, budget, bindings)


def make_candidate(manifest: NumericManifest, authority: ContributionAuthority) -> CandidateCertificate:
    binomial_binding, hoeffding_binding = manifest.gates
    ids = tuple(item.contribution_id for item in authority.contributions)
    binomial = ExactBinomialProof("exact_binomial", ids, 2, 2, RationalPoint("1/2"), "ge", RationalPoint("1/4"))
    wires = Tripwires()
    lower, upper = _exp_enclosure(Fraction(1, 4), 1, __import__("numeric_boundary_contract").Meter(manifest.budget, wires))
    hoeffding = WeightedHoeffdingProof("weighted_hoeffding", ids, RationalPoint("1/4"), RationalPoint("1/2"), 1, RationalEnclosure(rational(lower), rational(upper)))
    authority_digest = contribution_authority_digest(authority)
    return CandidateCertificate(
        "numeric_acceptance_certificate.v1", manifest_digest(manifest), authority_digest,
        (
            ProofBundle(binomial_binding.locator, binding_digest(binomial_binding), authority_digest, binomial, RationalEnclosure("1/4", "1/4")),
            ProofBundle(hoeffding_binding.locator, binding_digest(hoeffding_binding), authority_digest, hoeffding, RationalEnclosure(rational(lower), rational(upper))),
        ),
    )


def require_rejected(serialized: bytes, manifest: NumericManifest, authority: ContributionAuthority, label: str, expected_event: str | None = None, forbidden_event: str | None = None) -> None:
    wires = Tripwires()
    try:
        verify_serialized_certificate(serialized, TransportLimit(manifest.budget.max_document_bytes), manifest, authority, wires)
    except BoundaryRejected:
        if expected_event is not None and expected_event not in wires.events:
            raise AssertionError(f"{label} did not reach required preallocation tripwire: {wires.events}")
        if forbidden_event is not None and forbidden_event in wires.events:
            raise AssertionError(f"{label} allocated beyond its limit: {wires.events}")
        return
    raise AssertionError(f"{label} unexpectedly verified")


def mutate(serialized: bytes, path: list[object], replacement: object) -> bytes:
    document = json.loads(serialized)
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"


def main() -> None:
    # Synthetic limits have no policy or activation meaning.
    budget = WorkBudget(16384, 2, 64, 256, 1000, 16384)
    authority = make_authority()
    manifest = make_manifest(authority, budget)
    candidate = make_candidate(manifest, authority)
    wires = Tripwires()
    serialized = serialize_candidate(candidate, budget, wires)
    verified = verify_serialized_certificate(serialized, TransportLimit(budget.max_document_bytes), manifest, authority, wires)
    assert verified == candidate
    required_events = {"before_document_parse", "before_integer", "before_fraction", "before_arithmetic", "before_certificate_serialization"}
    assert required_events <= set(wires.events), wires.events

    # Every adversarial case enters the same public verifier, never an inequality-only predicate.
    mutations = {
        "wrong_binomial_result": (mutate(serialized, ["bundles", 0, "proof", "result", "value"], "1/3"), None),
        "wrong_reported_pair": (mutate(serialized, ["bundles", 0, "reported_probability", "upper"], "1/3"), None),
        "proof_swap": (mutate(serialized, ["bundles", 0, "proof", "kind"], "weighted_hoeffding"), None),
        "changed_evidence_digest": (mutate(serialized, ["contribution_authority_digest"], "0" * 64), None),
        "changed_binding_digest": (mutate(serialized, ["bundles", 0, "binding_digest"], "0" * 64), None),
        "wrong_locator_pair": (mutate(serialized, ["bundles", 0, "locator", "metric_id"], "hoeffding_metric"), None),
        "noncanonical_rational": (mutate(serialized, ["bundles", 0, "proof", "result", "value"], "2/8"), "before_integer"),
        "malformed_field": (mutate(serialized, ["bundles", 0, "unexpected"], True), None),
        "digit_limit_before_integer": (mutate(serialized, ["bundles", 0, "proof", "result", "value"], "1" * 65 + "/1"), "before_document_parse"),
    }
    for label, (bad, event) in mutations.items():
        require_rejected(bad, manifest, authority, label, event)

    # Exact limit succeeds; each independently supplied cap rejects one over before numeric allocation.
    exact_budget = replace(budget, max_document_bytes=9999)
    exact_manifest = make_manifest(authority, exact_budget)
    exact_candidate = make_candidate(exact_manifest, authority)
    exact_serialized = serialize_candidate(exact_candidate, exact_budget, Tripwires())
    exact_budget = replace(exact_budget, max_document_bytes=len(exact_serialized))
    exact_manifest = make_manifest(authority, exact_budget)
    exact_candidate = make_candidate(exact_manifest, authority)
    exact_serialized = serialize_candidate(exact_candidate, exact_budget, Tripwires())
    assert len(exact_serialized) == exact_budget.max_document_bytes
    exact = verify_serialized_certificate(exact_serialized, TransportLimit(len(exact_serialized)), exact_manifest, authority)
    assert exact.schema == candidate.schema
    require_rejected(exact_serialized, replace(exact_manifest, budget=replace(exact_budget, max_document_bytes=len(exact_serialized) - 1)), authority, "transport_one_over")
    # The digit/bit cap fires after document parsing but before the integer tripwire.
    require_rejected(serialized, replace(manifest, budget=replace(budget, max_numeric_digits=1)), authority, "digit_one_over", "before_document_parse", "before_integer")
    bit_over = mutate(serialized, ["bundles", 0, "proof", "result", "value"], "10/1")
    require_rejected(bit_over, replace(manifest, budget=replace(budget, max_numeric_bits=3)), authority, "bit_one_over", "before_document_parse", "before_integer:10/1")
    require_rejected(serialized, replace(manifest, budget=replace(budget, max_operations=1)), authority, "operation_one_over", "before_fraction")
    try:
        serialize_candidate(candidate, replace(budget, max_certificate_bytes=len(serialized) - 1), Tripwires())
    except LimitExceeded:
        pass
    else:
        raise AssertionError("certificate one-over unexpectedly serialized")
    expanded_authority = replace(authority, contributions=authority.contributions + authority.contributions)
    require_rejected(serialized, manifest, expanded_authority, "contribution_one_over")

    (ROOT / "field-table.json").write_bytes(json.dumps(generated_field_table(), indent=2, sort_keys=True).encode("ascii") + b"\n")
    (ROOT / "candidate.json").write_bytes(serialized)
    hashes = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in ("numeric_boundary_contract.py", "run_numeric_boundary_proof.py", "field-table.json", "candidate.json")}
    (ROOT / "candidate-hash-manifest.json").write_bytes(json.dumps({"scope": "nonproduction numeric boundary reconstruction", "files": hashes}, indent=2, sort_keys=True).encode("ascii") + b"\n")
    print(json.dumps({"status": "passed", "mutations": sorted(mutations), "tripwires": sorted(required_events), "candidate_bytes": len(serialized)}, sort_keys=True))


if __name__ == "__main__":
    main()

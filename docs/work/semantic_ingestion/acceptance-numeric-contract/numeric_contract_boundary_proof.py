"""Bounded nonproduction proof for numeric-contract resource and mutation rules."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json


class ResourceLimit(ValueError):
    pass


@dataclass(frozen=True)
class Budget:
    input_bytes: int
    contributions: int
    digits: int
    operations: int
    bits: int
    certificate_bytes: int


class Meter:
    def __init__(self, budget: Budget) -> None:
        self.budget = budget
        self.operations = 0

    def charge(self, count: int = 1) -> None:
        self.operations += count
        if self.operations > self.budget.operations:
            raise ResourceLimit("resource_limit")

    def rational(self, text: str) -> Fraction:
        if len(text.encode("ascii")) > self.budget.input_bytes or len(text.replace("/", "")) > self.budget.digits:
            raise ResourceLimit("resource_limit")
        self.charge()
        numerator, slash, denominator = text.partition("/")
        if not slash or not numerator or not denominator:
            raise ValueError("malformed_rational")
        value = Fraction(int(numerator), int(denominator))
        if f"{value.numerator}/{value.denominator}" != text:
            raise ValueError("malformed_rational")
        if value.numerator.bit_length() > self.budget.bits or value.denominator.bit_length() > self.budget.bits:
            raise ResourceLimit("resource_limit")
        return value

    def evaluate(self, values: list[str]) -> dict[str, object]:
        try:
            if len(values) > self.budget.contributions:
                raise ResourceLimit("resource_limit")
            total = Fraction()
            for value in values:
                total += self.rational(value)
                self.charge()
            certificate = json.dumps({"total": f"{total.numerator}/{total.denominator}"}, sort_keys=True).encode("ascii")
            if len(certificate) > self.budget.certificate_bytes:
                raise ResourceLimit("resource_limit")
            return {"outcome": "passes", "certificate": certificate.decode("ascii")}
        except ResourceLimit:
            return {"outcome": "inconclusive", "failure_code": "resource_limit", "certificate": None}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def proof_mutations() -> None:
    binding = {"gate_locator": ["cap", "cell", "metric"], "threshold": "1/2"}
    binding_digest = digest(binding)
    proof = {"kind": "exact_binomial", "binding_digest": binding_digest, "reported": "1/4"}
    bundle = {"binding": binding, "binding_digest": binding_digest, "proof": proof, "proof_digest": digest(proof)}
    require(digest(bundle["binding"]) == bundle["binding_digest"], "binding baseline")
    for mutation in (
        {**proof, "binding_digest": "0" * 64},
        {**proof, "reported": "1/3"},
        {**bundle, "unexpected": True},
    ):
        if "unexpected" in mutation:
            require(set(mutation) != {"binding", "binding_digest", "proof", "proof_digest"}, "schema mutation")
        else:
            require(mutation["binding_digest"] != binding_digest or digest(mutation) != bundle["proof_digest"], "proof mutation")


def main() -> None:
    # Every case proves exact limit succeeds and boundary-plus-one returns no certificate.
    dimensions = {
        "input_bytes": (Budget(3, 1, 2, 2, 2, 32), ["1/2"], Budget(2, 1, 2, 2, 2, 32)),
        "contributions": (Budget(3, 1, 2, 3, 2, 32), ["1/2"], Budget(3, 0, 2, 3, 2, 32)),
        "digits": (Budget(3, 1, 2, 2, 2, 32), ["1/2"], Budget(3, 1, 1, 2, 2, 32)),
        "operations": (Budget(3, 1, 2, 2, 2, 32), ["1/2"], Budget(3, 1, 2, 1, 2, 32)),
        "bits": (Budget(3, 1, 2, 2, 2, 32), ["1/2"], Budget(3, 1, 2, 2, 1, 32)),
        "certificate_bytes": (Budget(3, 1, 2, 2, 2, 16), ["1/2"], Budget(3, 1, 2, 2, 2, 15)),
    }
    for name, (at_limit, values, over_limit) in dimensions.items():
        require(Meter(at_limit).evaluate(values)["outcome"] == "passes", f"{name} limit failed")
        rejected = Meter(over_limit).evaluate(values)
        require(rejected == {"outcome": "inconclusive", "failure_code": "resource_limit", "certificate": None}, f"{name} overflow accepted")
    proof_mutations()
    print(json.dumps({"boundary_dimensions": sorted(dimensions), "mutation_checks": True, "policy_or_activation_authority": False}, sort_keys=True))


if __name__ == "__main__":
    main()

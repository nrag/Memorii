"""Generate synthetic numerical vectors and check them independently, without writes."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction

from bounded_math import (
    ArithmeticBudget, ArithmeticMeter, HolmClaim, RationalInterval,
    WeightedObservation, clopper_pearson_bound, exact_binomial_tail,
    holm_complete, invert_weighted_hoeffding, weighted_hoeffding,
)
from independent_math_check import check_document


def rational(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def interval(value: RationalInterval) -> list[str]:
    return [rational(value.lower), rational(value.upper)]


def meter() -> ArithmeticMeter:
    # Synthetic resource settings exercise mechanics, not deployment policy.
    return ArithmeticMeter(ArithmeticBudget(8192, 1000000))


def vectors() -> dict:
    document: dict = {"binomial": [], "hoeffding": [], "holm": []}
    for successes in range(6):
        for direction in ("lower", "upper"):
            work = meter()
            tail = "greater_or_equal" if direction == "lower" else "less_or_equal"
            null, alpha = Fraction(1, 3), Fraction(1, 20)
            document["binomial"].append({
                "n": 5, "k": successes, "p": rational(null),
                "tail": "ge" if direction == "lower" else "le",
                "result": rational(exact_binomial_tail(5, successes, null, tail, work)),
                "alpha": rational(alpha), "direction": direction,
                "bound": interval(clopper_pearson_bound(5, successes, alpha, direction, 12, work)),
            })
    for direction in ("lower", "upper"):
        work = meter()
        tail = "greater_or_equal" if direction == "lower" else "less_or_equal"
        document["binomial"].append({
            "n": 5, "k": 2, "p": "1/3", "tail": "ge" if direction == "lower" else "le",
            "result": rational(exact_binomial_tail(5, 2, Fraction(1, 3), tail, work)),
            "alpha": "1/1", "direction": direction,
            "bound": interval(clopper_pearson_bound(5, 2, Fraction(1), direction, 12, work)),
        })
    for direction in ("lower", "upper"):
        successes = 0 if direction == "lower" else 5
        work = meter()
        tail = "greater_or_equal" if direction == "lower" else "less_or_equal"
        document["binomial"].append({
            "n": 5, "k": successes, "p": "1/3", "tail": "ge" if direction == "lower" else "le",
            "result": rational(exact_binomial_tail(5, successes, Fraction(1, 3), tail, work)),
            "alpha": "1/1", "direction": direction,
            "bound": interval(clopper_pearson_bound(5, successes, Fraction(1), direction, 12, work)),
        })
    for fixed in (False, True):
        observations = tuple(
            WeightedObservation(value, Fraction(1, 2), value if fixed else Fraction(0), value if fixed else Fraction(1))
            for value in (Fraction(4, 5), Fraction(9, 10))
        )
        for direction in ("lower", "upper"):
            for threshold in (Fraction(1, 2), Fraction(19, 20)):
                work = meter()
                alpha = Fraction(1, 5)
                result = weighted_hoeffding(observations, threshold, direction, 12, work)
                bound = invert_weighted_hoeffding(observations, threshold, direction, alpha, 12, 12, work)
                document["hoeffding"].append({
                    "values": [{name: rational(getattr(row, name)) for name in ("value", "weight", "lower", "upper")} for row in observations],
                    "threshold": rational(threshold), "alpha": rational(alpha),
                    "direction": direction, "p": interval(result.probability), "bound": interval(bound),
                })
    scenarios = (
        ("alpha_one", tuple(WeightedObservation(value, Fraction(1, 2), Fraction(0), Fraction(1)) for value in (Fraction(4, 5), Fraction(9, 10))), Fraction(1)),
        ("heterogeneous_ranges", (WeightedObservation(Fraction(1, 4), Fraction(1, 3), Fraction(0), Fraction(1, 2)), WeightedObservation(Fraction(3, 4), Fraction(2, 3), Fraction(1, 2), Fraction(1))), Fraction(1, 5)),
        ("zero_weight_wide_range", (WeightedObservation(Fraction(4, 5), Fraction(1), Fraction(4, 5), Fraction(4, 5)), WeightedObservation(Fraction(0), Fraction(0), Fraction(0), Fraction(1))), Fraction(1, 5)),
    )
    for _, observations, alpha in scenarios:
        for direction in ("lower", "upper"):
            work = meter()
            threshold = Fraction(1, 2)
            result = weighted_hoeffding(observations, threshold, direction, 12, work)
            bound = invert_weighted_hoeffding(observations, threshold, direction, alpha, 12, 12, work)
            document["hoeffding"].append({
                "values": [{name: rational(getattr(row, name)) for name in ("value", "weight", "lower", "upper")} for row in observations],
                "threshold": rational(threshold), "alpha": rational(alpha), "direction": direction,
                "p": interval(result.probability), "bound": interval(bound),
            })
    for probabilities in ((Fraction(1, 1000), Fraction(1, 500), Fraction(1, 50)),
                          (Fraction(1, 100), Fraction(1, 100), Fraction(1, 50)),
                          (Fraction(1, 1000), Fraction(1, 10), Fraction(1, 5))):
        claims = tuple(HolmClaim(name.encode(), Fraction(1, 20), RationalInterval(p, p))
                       for name, p in zip(("a", "b", "c"), probabilities, strict=True))
        decisions = holm_complete(claims, (b"a", b"b", b"c"), Fraction(1, 20), meter())
        document["holm"].append({
            "claims": [{"locator": c.locator_bytes.decode(), "p": rational(c.probability.lower), "nominal_alpha": rational(c.nominal_alpha)} for c in claims],
            "family_alpha": "1/20", "ordered_locators": [d.locator_bytes.decode() for d in decisions],
            "accepted": all(d.outcome == "pass" for d in decisions),
        })
    return document


def main() -> None:
    document = vectors()
    check_document(document)
    mutations = []
    bad = deepcopy(document)
    bad["binomial"][2]["result"] = "1/7"
    mutations.append(bad)
    bad = deepcopy(document)
    bad["binomial"][2]["bound"] = ["1/1", "1/1"]
    mutations.append(bad)
    bad = deepcopy(document)
    bad["hoeffding"][0]["p"] = ["0/1", "0/1"]
    mutations.append(bad)
    bad = deepcopy(document)
    bad["hoeffding"][0]["bound"] = ["0/1", "1/1"]
    mutations.append(bad)
    bad = deepcopy(document)
    bad["hoeffding"][0]["bound"] = ["0/1", "0/1"]
    mutations.append(bad)
    bad = deepcopy(document)
    bad["binomial"][0]["bound"] = ["0/1", "1/1"]
    mutations.append(bad)
    bad = deepcopy(document)
    bad["holm"][0]["ordered_locators"].reverse()
    mutations.append(bad)
    bad = deepcopy(document)
    bad["holm"][2]["accepted"] = True
    mutations.append(bad)
    for index, bad in enumerate(mutations):
        try:
            check_document(bad)
        except ValueError:
            continue
        raise RuntimeError(f"independent checker accepted altered numerical evidence:{index}")
    print(f"Independent numerical verification passed: {sum(map(len, document.values()))} vectors, {len(mutations)} rejected mutations")


if __name__ == "__main__":
    main()

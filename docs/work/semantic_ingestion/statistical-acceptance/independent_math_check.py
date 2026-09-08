"""Independent exact checker for externally generated statistical vectors.

This is deliberately a vector checker, not a production parser or transport.
It uses only the standard library and does not import the candidate kernel.
"""

from __future__ import annotations

import json
import sys
from fractions import Fraction
from math import comb
from pathlib import Path
from typing import Any


def _fraction(value: object) -> Fraction:
    if not isinstance(value, str) or value.count("/") != 1:
        raise ValueError("rational_invalid")
    numerator, denominator = value.split("/")
    if not numerator or not denominator:
        raise ValueError("rational_invalid")
    result = Fraction(int(numerator), int(denominator))
    if f"{result.numerator}/{result.denominator}" != value:
        raise ValueError("rational_noncanonical")
    return result


def _pair(value: object) -> tuple[Fraction, Fraction]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("interval_invalid")
    lower, upper = (_fraction(item) for item in value)
    if lower > upper:
        raise ValueError("interval_invalid")
    return lower, upper


def _tail(n: int, k: int, probability: Fraction, tail: str) -> Fraction:
    if type(n) is not int or type(k) is not int or not 0 <= k <= n or not 0 <= probability <= 1:
        raise ValueError("binomial_domain_invalid")
    if tail == "ge":
        indices = range(k, n + 1)
    elif tail == "le":
        indices = range(k + 1)
    else:
        raise ValueError("binomial_tail_invalid")
    return sum((Fraction(comb(n, index)) * probability**index * (1 - probability) ** (n - index) for index in indices), Fraction())


def _cp_bisection(n: int, k: int, alpha: Fraction, direction: str, steps: int = 12) -> tuple[Fraction, Fraction]:
    """Independent fixed-step rational inversion of the direction-selected tail."""
    tail = "ge" if direction == "lower" else "le"
    low, high = Fraction(), Fraction(1)
    for _ in range(steps):
        middle = (low + high) / 2
        value = _tail(n, k, middle, tail)
        if value == alpha:
            return middle, middle
        if (direction == "lower" and value < alpha) or (direction == "upper" and value > alpha):
            low = middle
        else:
            high = middle
    return low, high


def _check_binomial(row: object) -> None:
    if not isinstance(row, dict) or set(row) != {"n", "k", "p", "tail", "result", "alpha", "direction", "bound"}:
        raise ValueError("binomial_row_invalid")
    n, k, tail, direction = row["n"], row["k"], row["tail"], row["direction"]
    if type(n) is not int or type(k) is not int or tail not in {"ge", "le"} or direction not in {"lower", "upper"}:
        raise ValueError("binomial_row_invalid")
    probability, claimed, alpha = _fraction(row["p"]), _fraction(row["result"]), _fraction(row["alpha"])
    expected_tail = "ge" if direction == "lower" else "le"
    if tail != expected_tail or not 0 < alpha <= 1 or _tail(n, k, probability, tail) != claimed:
        raise ValueError("binomial_claim_invalid")
    lower, upper = _pair(row["bound"])
    if not 0 <= lower <= upper <= 1:
        raise ValueError("binomial_bound_invalid")
    if direction == "lower" and k == 0:
        if (lower, upper) != (Fraction(), Fraction()):
            raise ValueError("cp_endpoint_invalid")
        return
    if direction == "upper" and k == n:
        if (lower, upper) != (Fraction(1), Fraction(1)):
            raise ValueError("cp_endpoint_invalid")
        return
    if alpha == 1:
        if (lower, upper) != (Fraction(), Fraction(1)):
            raise ValueError("cp_alpha_one_bound_invalid")
        return
    low_tail, high_tail = _tail(n, k, lower, tail), _tail(n, k, upper, tail)
    if tail == "ge":
        bracketed = low_tail <= alpha <= high_tail
    else:
        bracketed = high_tail <= alpha <= low_tail
    if not bracketed:
        raise ValueError("cp_root_not_bracketed")
    if (lower, upper) != _cp_bisection(n, k, alpha, direction):
        raise ValueError("cp_fixed_step_bound_invalid")


def _exp_negative_interval(exponent: Fraction, terms: int = 48) -> tuple[Fraction, Fraction]:
    """Rational Taylor enclosure: reciprocal bounds for exp(exponent)."""
    if exponent < 0 or terms < 1 or exponent >= terms + 2:
        raise ValueError("exp_domain_invalid")
    term = total = Fraction(1)
    for index in range(1, terms + 1):
        term *= exponent
        term /= index
        total += term
    next_term = term * exponent / (terms + 1)
    upper_exp = total + next_term / (1 - exponent / (terms + 2))
    return Fraction(1, 1) / upper_exp, Fraction(1, 1) / total


def _hoeffding_probability(values: object, threshold: Fraction, direction: str, terms: int = 48) -> tuple[tuple[Fraction, Fraction], Fraction, Fraction]:
    if not isinstance(values, list) or not values or direction not in {"lower", "upper"}:
        raise ValueError("hoeffding_values_invalid")
    mean = squared = Fraction()
    weights = Fraction()
    for row in values:
        if not isinstance(row, dict) or set(row) != {"value", "weight", "lower", "upper"}:
            raise ValueError("hoeffding_value_invalid")
        value, weight, lower, upper = (_fraction(row[name]) for name in ("value", "weight", "lower", "upper"))
        if weight < 0 or lower > upper or not lower <= value <= upper:
            raise ValueError("hoeffding_value_invalid")
        weights += weight
        mean += weight * value
        squared += weight * weight * (upper - lower) * (upper - lower)
    if weights != 1:
        raise ValueError("hoeffding_weight_invalid")
    margin = max(Fraction(), mean - threshold) if direction == "lower" else max(Fraction(), threshold - mean)
    if squared == 0:
        return ((Fraction(), Fraction()) if margin > 0 else (Fraction(1), Fraction(1))), mean, squared
    return _exp_negative_interval(2 * margin * margin / squared, terms), mean, squared


def _hoeffding_bisection(values: object, alpha: Fraction, direction: str, lower: Fraction, upper: Fraction, steps: int = 12) -> tuple[Fraction, Fraction]:
    """Independent fixed-step inverse using the conservative upper p enclosure."""
    low, high = lower, upper
    for _ in range(steps):
        middle = (low + high) / 2
        probability = _hoeffding_probability(values, middle, direction, 12)[0]
        if direction == "lower":
            if probability[1] <= alpha:
                low = middle
            elif probability[0] >= alpha:
                high = middle
        else:
            if probability[1] <= alpha:
                high = middle
            elif probability[0] >= alpha:
                low = middle
        if probability[0] < alpha < probability[1]:
            return low, high
    return low, high


def _check_hoeffding(row: object) -> None:
    required = {"values", "threshold", "alpha", "direction", "p", "bound"}
    if not isinstance(row, dict) or set(row) != required:
        raise ValueError("hoeffding_row_invalid")
    alpha, threshold = _fraction(row["alpha"]), _fraction(row["threshold"])
    if not 0 < alpha <= 1:
        raise ValueError("hoeffding_alpha_invalid")
    expected, mean, squared = _hoeffding_probability(row["values"], threshold, row["direction"])
    claimed = _pair(row["p"])
    if claimed[0] > expected[0] or claimed[1] < expected[1]:
        raise ValueError("hoeffding_probability_not_conservative")
    lower, upper = _pair(row["bound"])
    values = row["values"]
    assert isinstance(values, list)
    range_lower = sum((_fraction(item["weight"]) * _fraction(item["lower"]) for item in values if isinstance(item, dict)), Fraction())
    range_upper = sum((_fraction(item["weight"]) * _fraction(item["upper"]) for item in values if isinstance(item, dict)), Fraction())
    if not range_lower <= lower <= upper <= range_upper:
        raise ValueError("hoeffding_bound_invalid")
    if squared == 0:
        fixed = all(
            isinstance(item, dict)
            and (
                _fraction(item["weight"]) == 0
                or _fraction(item["lower"]) == _fraction(item["upper"]) == _fraction(item["value"])
            )
            for item in values
        )
        if not fixed or (lower, upper) != (mean, mean):
            raise ValueError("hoeffding_deterministic_bound_invalid")
        return
    if alpha == 1:
        if (lower, upper) != (range_lower, range_upper):
            raise ValueError("hoeffding_alpha_one_bound_invalid")
        return
    at_lower = _hoeffding_probability(row["values"], lower, row["direction"])[0]
    at_upper = _hoeffding_probability(row["values"], upper, row["direction"])[0]
    if row["direction"] == "lower" and (lower, upper) == (range_lower, range_lower):
        if at_lower[0] < alpha:
            raise ValueError("hoeffding_lower_clip_invalid")
        return
    if row["direction"] == "upper" and (lower, upper) == (range_upper, range_upper):
        if at_upper[0] < alpha:
            raise ValueError("hoeffding_upper_clip_invalid")
        return
    if (lower, upper) != _hoeffding_bisection(values, alpha, row["direction"], range_lower, range_upper):
        raise ValueError(f"hoeffding_fixed_step_bound_invalid:{row['direction']}:{lower}:{upper}:{range_lower}:{range_upper}")
    # The claimed inversion must bracket a threshold where the same tail crosses alpha.
    if row["direction"] == "lower":
        bracketed = (lower == range_lower or at_lower[1] <= alpha) and (upper == range_upper or at_upper[0] >= alpha)
    else:
        bracketed = (lower == range_lower or at_lower[0] >= alpha) and (upper == range_upper or at_upper[1] <= alpha)
    if not bracketed:
        raise ValueError(
            f"hoeffding_inverse_not_conservative:{row['direction']}:{lower}:{upper}:{at_lower}:{at_upper}:{alpha}"
        )


def _check_holm(row: object) -> None:
    required = {"claims", "family_alpha", "ordered_locators", "accepted"}
    if not isinstance(row, dict) or set(row) != required or not isinstance(row["claims"], list):
        raise ValueError("holm_row_invalid")
    family_alpha = _fraction(row["family_alpha"])
    claims: list[tuple[str, Fraction, Fraction]] = []
    for claim in row["claims"]:
        if not isinstance(claim, dict) or set(claim) != {"locator", "p", "nominal_alpha"} or not isinstance(claim["locator"], str):
            raise ValueError("holm_claim_invalid")
        claims.append((claim["locator"], _fraction(claim["p"]), _fraction(claim["nominal_alpha"])))
    if not claims or len({item[0] for item in claims}) != len(claims) or not 0 < family_alpha < 1:
        raise ValueError("holm_claim_invalid")
    ordered = sorted(claims, key=lambda item: (item[1], item[0]))
    if row["ordered_locators"] != [item[0] for item in ordered]:
        raise ValueError("holm_order_invalid")
    passes = True
    for index, (_, probability, nominal) in enumerate(ordered):
        cutoff = min(nominal, family_alpha / (len(ordered) - index))
        if probability > cutoff:
            passes = False
    if row["accepted"] is not passes:
        raise ValueError("holm_acceptance_invalid")


def check_document(document: dict[str, Any]) -> None:
    """Reject any vector whose claimed exact, bounded, or family result is wrong."""
    if not isinstance(document, dict) or set(document) != {"binomial", "hoeffding", "holm"}:
        raise ValueError("vector_document_invalid")
    for row in document["binomial"]:
        _check_binomial(row)
    for row in document["hoeffding"]:
        _check_hoeffding(row)
    for row in document["holm"]:
        _check_holm(row)


def main(path: str) -> None:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    check_document(value)


if __name__ == "__main__":
    main(sys.argv[1])

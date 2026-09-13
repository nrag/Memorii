"""Nonproduction rational-enclosure feasibility proof; no policy authority."""

from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction
import json
from math import comb
from pathlib import Path


def rational_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def exponential_enclosure(value: Fraction, terms: int) -> tuple[Fraction, Fraction]:
    """Bracket exp(-value) from a positive Taylor sum and rational tail bound."""
    if value < 0 or terms < 1 or Fraction(terms + 2) <= value:
        raise ValueError("nonnegative argument and convergent tail required")
    term = total = Fraction(1)
    for index in range(1, terms + 1):
        term *= value / index
        total += term
    next_term = term * value / (terms + 1)
    remainder = next_term / (1 - value / (terms + 2))
    return 1 / (total + remainder), 1 / total


def binomial_tail(count: int, successes: int, probability: Fraction, tail: str) -> Fraction:
    if tail not in {"ge", "le"}:
        raise ValueError("unknown tail")
    indices = range(successes, count + 1) if tail == "ge" else range(successes + 1)
    return sum((Fraction(comb(count, index)) * probability**index * (1 - probability) ** (count - index) for index in indices), Fraction())


def binomial_root_enclosure(count: int, successes: int, alpha: Fraction, tail: str, steps: int) -> tuple[Fraction, Fraction]:
    """Bracket either monotone exact-binomial tail root using rational arithmetic."""
    if not 0 <= successes <= count or not 0 < alpha < 1 or steps < 1:
        raise ValueError("invalid binomial root input")
    if (tail == "ge" and successes == 0) or (tail == "le" and successes == count):
        raise ValueError("degenerate binomial root")
    increasing = tail == "ge"
    lower, upper = Fraction(), Fraction(1)
    for _ in range(steps):
        middle = (lower + upper) / 2
        value = binomial_tail(count, successes, middle, tail)
        if (increasing and value < alpha) or (not increasing and value > alpha):
            lower = middle
        else:
            upper = middle
    lower_value = binomial_tail(count, successes, lower, tail)
    upper_value = binomial_tail(count, successes, upper, tail)
    assert (lower_value <= alpha <= upper_value) if increasing else (lower_value >= alpha >= upper_value)
    return lower, upper


def weighted_hoeffding_enclosure(margin: Fraction, squared_range_weight_sum: Fraction, terms: int) -> tuple[str, Fraction, Fraction, Fraction]:
    """Return exponent and an enclosure for the named Section 5.6 tail."""
    if squared_range_weight_sum < 0:
        raise ValueError("nonnegative weighted squared-range sum required")
    if squared_range_weight_sum == 0:
        # All positive-weight cluster ranges are fixed, so this is an exact branch.
        return "degenerate_fixed_value", Fraction(), *( (Fraction(), Fraction()) if margin > 0 else (Fraction(1), Fraction(1)) )
    if margin <= 0:
        return "exponential", Fraction(), Fraction(1), Fraction(1)
    exponent = 2 * margin * margin / squared_range_weight_sum
    lower, upper = exponential_enclosure(exponent, terms)
    return "exponential", exponent, lower, upper


def as_decimal(value: Fraction) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


def main() -> None:
    # All literals below are examples, never approved policy values.
    with localcontext() as context:
        context.prec = 100
        exponent_cases = []
        for value in (Fraction(), Fraction(1, 10), Fraction(2), Fraction(20)):
            lower, upper = exponential_enclosure(value, 100)
            assert as_decimal(lower) <= (-as_decimal(value)).exp() <= as_decimal(upper)
            exponent_cases.append({"exponent": rational_text(value), "terms": 100, "lower": rational_text(lower), "upper": rational_text(upper)})
        roots = []
        for count, successes, tail in ((10, 1, "ge"), (10, 4, "ge"), (10, 4, "le"), (10, 9, "le"), (20, 3, "ge"), (20, 17, "le")):
            alpha = Fraction(1, 20)
            lower, upper = binomial_root_enclosure(count, successes, alpha, tail, 40)
            roots.append({"count": count, "successes": successes, "tail": tail, "alpha": rational_text(alpha), "lower": rational_text(lower), "upper": rational_text(upper)})
        hoeffding = []
        for margin, squared_sum in ((Fraction(1, 10), Fraction(1, 4)), (Fraction(3, 20), Fraction(7, 25)), (Fraction(), Fraction(1, 3)), (Fraction(1, 10), Fraction()), (Fraction(), Fraction())):
            branch, exponent, lower, upper = weighted_hoeffding_enclosure(margin, squared_sum, 100)
            if branch == "exponential":
                assert as_decimal(lower) <= (-as_decimal(exponent)).exp() <= as_decimal(upper)
            hoeffding.append({"branch": branch, "margin": rational_text(margin), "squared_range_weight_sum": rational_text(squared_sum), "exponent": rational_text(exponent), "terms": 100, "lower": rational_text(lower), "upper": rational_text(upper)})
    raw_p_values = {"claim-a": Fraction(1, 8), "claim-b": Fraction(1, 8), "claim-c": Fraction(1, 16)}
    holm_order = sorted(raw_p_values, key=lambda claim: (raw_p_values[claim], claim))
    assert holm_order == ["claim-c", "claim-a", "claim-b"]
    result = {"algorithm": "nonproduction-rational-enclosure-feasibility-v2", "binomial_root_certificates": roots, "exponential_certificates": exponent_cases, "weighted_hoeffding_certificates": hoeffding, "holm_exact_tie_certificate": {"raw_p_values": {claim: rational_text(value) for claim, value in raw_p_values.items()}, "canonical_order": holm_order}, "independent_decimal_reference": "100 decimal digits; diagnostic cross-check only", "policy_or_activation_authority": False}
    Path(__file__).with_name("feasibility-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps({"binomial_root_cases": len(roots), "hoeffding_cases": len(hoeffding), "holm_exact_ties": True, "policy_or_activation_authority": False}, sort_keys=True))


if __name__ == "__main__":
    main()

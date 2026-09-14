"""Nonproduction bounded rational inference; no policy values or transport defaults."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction
from functools import cmp_to_key
from typing import Literal

Tail = Literal["greater_or_equal", "less_or_equal"]
Direction = Literal["lower", "upper"]
_ZERO, _ONE = Fraction(0), Fraction(1)


@dataclass(frozen=True)
class ArithmeticBudget:
    maximum_rational_bits: int
    maximum_exact_operations: int

    def __post_init__(self) -> None:
        if any(type(v) is not int or v < 1 for v in (self.maximum_rational_bits, self.maximum_exact_operations)):
            raise ValueError("invalid_arithmetic_budget")


@dataclass
class ArithmeticMeter:
    budget: ArithmeticBudget
    allocation_hook: Callable[[str], None] | None = None
    operations: int = field(default=0, init=False)

    def reserve(self, numerator_bits: int, denominator_bits: int = 1) -> None:
        if (
            type(numerator_bits) is not int
            or type(denominator_bits) is not int
            or min(numerator_bits, denominator_bits) < 1
            or max(numerator_bits, denominator_bits) > self.budget.maximum_rational_bits
            or self.operations >= self.budget.maximum_exact_operations
        ):
            raise ValueError("resource_limit")
        self.operations += 1

    def allocating(self, kind: str) -> None:
        if self.allocation_hook is not None:
            self.allocation_hook(kind)

    def check(self, value: Fraction) -> None:
        if type(value) is not Fraction:
            raise ValueError("malformed_rational")
        self.reserve(_bits(value.numerator), _bits(value.denominator))

    def add(self, left: Fraction, right: Fraction) -> Fraction:
        self.check(left)
        self.check(right)
        # Cross products and the carry must fit, even if reduction later cancels them.
        self.reserve(
            max(_bits(left.numerator) + _bits(right.denominator), _bits(right.numerator) + _bits(left.denominator)) + 1,
            _bits(left.denominator) + _bits(right.denominator),
        )
        self.allocating("add")
        return left + right

    def sub(self, left: Fraction, right: Fraction) -> Fraction:
        self.check(right)
        self.allocating("negate")
        return self.add(left, -right)

    def mul(self, left: Fraction, right: Fraction) -> Fraction:
        self.check(left)
        self.check(right)
        self.reserve(_bits(left.numerator) + _bits(right.numerator), _bits(left.denominator) + _bits(right.denominator))
        self.allocating("multiply")
        return left * right

    def div(self, left: Fraction, right: Fraction) -> Fraction:
        self.check(left)
        self.check(right)
        if right.numerator == 0:
            raise ValueError("out_of_domain")
        self.reserve(_bits(left.numerator) + _bits(right.denominator), _bits(left.denominator) + _bits(right.numerator))
        self.allocating("divide")
        return left / right

    def compare(self, left: Fraction, right: Fraction) -> int:
        self.check(left)
        self.check(right)
        self.reserve(_bits(left.numerator) + _bits(right.denominator), _bits(left.denominator) + _bits(right.numerator))
        self.allocating("compare")
        return (left > right) - (left < right)

    def pow(self, value: Fraction, exponent: int) -> Fraction:
        self.check(value)
        if type(exponent) is not int or exponent < 0:
            raise ValueError("out_of_domain")
        result = _ONE
        for _ in range(exponent):
            result = self.mul(result, value)
        return result


def _bits(value: int) -> int:
    return max(1, value.bit_length())


def _integer(value: int, meter: ArithmeticMeter) -> Fraction:
    if type(value) is not int:
        raise ValueError("out_of_domain")
    meter.reserve(_bits(value))
    meter.allocating("fraction")
    return Fraction(value)


def parse_rational(numerator: str, denominator: str, meter: ArithmeticMeter) -> Fraction:
    if not isinstance(numerator, str) or not isinstance(denominator, str):
        raise ValueError("malformed_rational")
    magnitude = numerator[1:] if numerator.startswith("-") else numerator
    if (
        not magnitude
        or not magnitude.isascii()
        or not magnitude.isdigit()
        or (len(magnitude) > 1 and magnitude[0] == "0")
        or numerator == "-0"
        or not denominator
        or not denominator.isascii()
        or not denominator.isdigit()
        or denominator[0] == "0"
    ):
        raise ValueError("malformed_rational")
    # Most short lexemes fit by a conservative decimal-to-binary bound. Only
    # boundary lexemes need the exact maximum, avoiding a huge limit string
    # merely because the configured budget is larger than a small input.
    bits = meter.budget.maximum_rational_bits
    digits = max(len(magnitude), len(denominator))
    runtime_limit = sys.get_int_max_str_digits()
    if runtime_limit and digits > runtime_limit:
        raise ValueError("resource_limit")
    projected = (digits * 332193) // 100000 + 1
    if projected > bits:
        meter.reserve(bits)
        meter.allocating("integer_limit")
        maximum = ((1 << (bits - 1)) - 1) * 2 + 1
        limit = str(maximum)
        if any(len(s) > len(limit) or (len(s) == len(limit) and s > limit) for s in (magnitude, denominator)):
            raise ValueError("resource_limit")
    meter.reserve(min(bits, projected), min(bits, projected))
    meter.allocating("integer_parse")
    n, d = int(numerator), int(denominator)
    meter.reserve(_bits(n), _bits(d))
    meter.allocating("fraction")
    result = Fraction(n, d)
    if result.numerator != n or result.denominator != d:
        raise ValueError("malformed_rational")
    return result


@dataclass(frozen=True)
class RationalInterval:
    lower: Fraction
    upper: Fraction


@dataclass(frozen=True)
class WeightedObservation:
    value: Fraction
    weight: Fraction
    lower: Fraction
    upper: Fraction


@dataclass(frozen=True)
class HoeffdingResult:
    probability: RationalInterval
    weighted_mean: Fraction
    squared_range_weight_sum: Fraction
    margin: Fraction
    deterministic: bool
    exponent: Fraction | None


@dataclass(frozen=True)
class HolmClaim:
    locator_bytes: bytes
    nominal_alpha: Fraction
    probability: RationalInterval
    # This is an exponent q for exp(-q), never a probability-valued sort key.
    exact_order: Fraction | None = None


@dataclass(frozen=True)
class HolmDecision:
    locator_bytes: bytes
    effective_alpha: Fraction
    outcome: Literal["pass", "fail", "inconclusive"]
    rank: int | None


def _interval(value: RationalInterval, meter: ArithmeticMeter, *, probability: bool = False) -> None:
    if type(value) is not RationalInterval or meter.compare(value.lower, value.upper) > 0:
        raise ValueError("invalid_interval")
    if probability and (meter.compare(value.lower, _ZERO) < 0 or meter.compare(value.upper, _ONE) > 0):
        raise ValueError("out_of_domain")


def _alpha(value: Fraction, meter: ArithmeticMeter) -> None:
    if meter.compare(value, _ZERO) <= 0 or meter.compare(value, _ONE) > 0:
        raise ValueError("out_of_domain")


def _binomial_coefficient(trials: int, index: int, meter: ArithmeticMeter) -> Fraction:
    # Explicit recurrence makes intermediate products visible to the budget;
    # a library comb implementation need not bound its internal allocations.
    coefficient = 1
    for divisor in range(1, min(index, trials - index) + 1):
        factor = trials - divisor + 1
        meter.reserve(_bits(coefficient) + _bits(factor))
        meter.allocating("binomial_coefficient")
        product = coefficient * factor
        meter.reserve(_bits(product), _bits(divisor))
        meter.allocating("binomial_divide")
        coefficient = product // divisor
    return _integer(coefficient, meter)


def exact_binomial_tail(
    trials: int, successes: int, null_probability: Fraction, tail: Tail, meter: ArithmeticMeter
) -> Fraction:
    if (
        type(trials) is not int
        or type(successes) is not int
        or trials < 1
        or not 0 <= successes <= trials
        or tail not in {"greater_or_equal", "less_or_equal"}
        or meter.compare(null_probability, _ZERO) < 0
        or meter.compare(null_probability, _ONE) > 0
    ):
        raise ValueError("out_of_domain")
    complement = meter.sub(_ONE, null_probability)
    indices = range(successes, trials + 1) if tail == "greater_or_equal" else range(successes + 1)
    total = _ZERO
    for index in indices:
        coefficient = _binomial_coefficient(trials, index, meter)
        term = meter.mul(coefficient, meter.pow(null_probability, index))
        term = meter.mul(term, meter.pow(complement, trials - index))
        total = meter.add(total, term)
    return total


def clopper_pearson_bound(
    trials: int, successes: int, alpha: Fraction, direction: Direction, steps: int, meter: ArithmeticMeter
) -> RationalInterval:
    _alpha(alpha, meter)
    if (
        type(steps) is not int
        or steps < 1
        or type(trials) is not int
        or trials < 1
        or type(successes) is not int
        or not 0 <= successes <= trials
        or direction not in {"lower", "upper"}
    ):
        raise ValueError("out_of_domain")
    if direction == "lower" and successes == 0:
        return RationalInterval(_ZERO, _ZERO)
    if direction == "upper" and successes == trials:
        return RationalInterval(_ONE, _ONE)
    if alpha == _ONE:
        return RationalInterval(_ZERO, _ONE)
    low, high = _ZERO, _ONE
    tail: Tail = "greater_or_equal" if direction == "lower" else "less_or_equal"
    for _ in range(steps):
        middle = meter.div(meter.add(low, high), _integer(2, meter))
        value = exact_binomial_tail(trials, successes, middle, tail, meter)
        cmp = meter.compare(value, alpha)
        if cmp == 0:
            return RationalInterval(middle, middle)
        if (direction == "lower" and cmp < 0) or (direction == "upper" and cmp > 0):
            low = middle
        else:
            high = middle
    return RationalInterval(low, high)


def _exp_negative_enclosure(exponent: Fraction, terms: int, meter: ArithmeticMeter) -> RationalInterval:
    if type(terms) is not int or terms < 1 or meter.compare(exponent, _ZERO) < 0:
        raise ValueError("out_of_domain")
    if exponent.numerator == 0:
        return RationalInterval(_ONE, _ONE)
    if meter.compare(exponent, _integer(terms + 2, meter)) >= 0:
        raise ValueError("resource_limit")
    term = total = _ONE
    for index in range(1, terms + 1):
        term = meter.div(meter.mul(term, exponent), _integer(index, meter))
        total = meter.add(total, term)
    omitted = meter.div(meter.mul(term, exponent), _integer(terms + 1, meter))
    ratio = meter.div(exponent, _integer(terms + 2, meter))
    remainder = meter.div(omitted, meter.sub(_ONE, ratio))
    return RationalInterval(meter.div(_ONE, meter.add(total, remainder)), meter.div(_ONE, total))


def _weighted(
    observations: tuple[WeightedObservation, ...], meter: ArithmeticMeter
) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    if not observations or type(observations) is not tuple:
        raise ValueError("invalid_weight_or_range")
    mean = squared = weights = lower = upper = _ZERO
    for item in observations:
        if (
            type(item) is not WeightedObservation
            or meter.compare(item.weight, _ZERO) < 0
            or meter.compare(item.lower, item.upper) > 0
            or meter.compare(item.value, item.lower) < 0
            or meter.compare(item.value, item.upper) > 0
        ):
            raise ValueError("invalid_weight_or_range")
        weights = meter.add(weights, item.weight)
        mean = meter.add(mean, meter.mul(item.weight, item.value))
        lower = meter.add(lower, meter.mul(item.weight, item.lower))
        upper = meter.add(upper, meter.mul(item.weight, item.upper))
        width = meter.sub(item.upper, item.lower)
        squared = meter.add(squared, meter.mul(meter.mul(item.weight, item.weight), meter.mul(width, width)))
    if meter.compare(weights, _ONE) != 0:
        raise ValueError("invalid_weight_or_range")
    return mean, squared, lower, upper


def _probability(
    mean: Fraction, squared: Fraction, threshold: Fraction, direction: Direction, terms: int, meter: ArithmeticMeter
) -> HoeffdingResult:
    if direction not in {"lower", "upper"}:
        raise ValueError("out_of_domain")
    margin = meter.sub(mean, threshold) if direction == "lower" else meter.sub(threshold, mean)
    if squared.numerator == 0:
        p = _ZERO if margin.numerator > 0 else _ONE
        return HoeffdingResult(RationalInterval(p, p), mean, squared, margin, True, None)
    if margin.numerator <= 0:
        return HoeffdingResult(RationalInterval(_ONE, _ONE), mean, squared, margin, False, _ZERO)
    exponent = meter.div(meter.mul(_integer(2, meter), meter.mul(margin, margin)), squared)
    return HoeffdingResult(_exp_negative_enclosure(exponent, terms, meter), mean, squared, margin, False, exponent)


def weighted_hoeffding(
    observations: tuple[WeightedObservation, ...],
    threshold: Fraction,
    direction: Direction,
    terms: int,
    meter: ArithmeticMeter,
) -> HoeffdingResult:
    mean, squared, _, _ = _weighted(observations, meter)
    return _probability(mean, squared, threshold, direction, terms, meter)


def invert_weighted_hoeffding(
    observations: tuple[WeightedObservation, ...],
    threshold: Fraction,
    direction: Direction,
    alpha: Fraction,
    steps: int,
    terms: int,
    meter: ArithmeticMeter,
) -> RationalInterval:
    _alpha(alpha, meter)
    meter.check(threshold)
    if type(steps) is not int or steps < 1 or direction not in {"lower", "upper"}:
        raise ValueError("out_of_domain")
    mean, squared, low, high = _weighted(observations, meter)
    if squared.numerator == 0:
        return RationalInterval(mean, mean)
    if alpha == _ONE:
        return RationalInterval(low, high)
    # Bounds are clipped to the frozen weighted range, not the min/max of samples.
    # For lower claims p(t) increases; for upper claims it decreases.
    low_p = _probability(mean, squared, low, direction, terms, meter).probability
    high_p = _probability(mean, squared, high, direction, terms, meter).probability
    if direction == "lower" and meter.compare(low_p.lower, alpha) >= 0:
        return RationalInterval(low, low)
    if direction == "upper" and meter.compare(high_p.lower, alpha) >= 0:
        return RationalInterval(high, high)
    for _ in range(steps):
        middle = meter.div(meter.add(low, high), _integer(2, meter))
        probability = _probability(mean, squared, middle, direction, terms, meter).probability
        if meter.compare(probability.upper, alpha) <= 0:
            if direction == "lower":
                low = middle
            else:
                high = middle
        elif meter.compare(probability.lower, alpha) >= 0:
            if direction == "lower":
                high = middle
            else:
                low = middle
        else:
            # Neither side can be discarded; retain the established outer bracket.
            break
    return RationalInterval(low, high)


class _UnresolvedOrder(Exception):
    pass


def holm_complete(
    claims: tuple[HolmClaim, ...], expected_locators: tuple[bytes, ...], family_alpha: Fraction, meter: ArithmeticMeter
) -> tuple[HolmDecision, ...]:
    _alpha(family_alpha, meter)
    if (
        not claims
        or any(type(c) is not HolmClaim or type(c.locator_bytes) is not bytes or not c.locator_bytes for c in claims)
        or len(set(expected_locators)) != len(expected_locators)
        or {c.locator_bytes for c in claims} != set(expected_locators)
        or len({c.locator_bytes for c in claims}) != len(claims)
    ):
        raise ValueError("out_of_domain")
    for claim in claims:
        _alpha(claim.nominal_alpha, meter)
        _interval(claim.probability, meter, probability=True)
        if claim.exact_order is not None and meter.compare(claim.exact_order, _ZERO) < 0:
            raise ValueError("out_of_domain")

    def compare(left: HolmClaim, right: HolmClaim) -> int:
        if left.exact_order is not None and right.exact_order is not None:
            order = -meter.compare(left.exact_order, right.exact_order)
        elif meter.compare(left.probability.upper, right.probability.lower) < 0:
            return -1
        elif meter.compare(right.probability.upper, left.probability.lower) < 0:
            return 1
        elif (
            left.probability.lower == left.probability.upper
            and right.probability.lower == right.probability.upper
            and left.probability.lower == right.probability.lower
        ):
            order = 0
        else:
            raise _UnresolvedOrder
        return order or ((left.locator_bytes > right.locator_bytes) - (left.locator_bytes < right.locator_bytes))

    try:
        ordered = sorted(claims, key=cmp_to_key(compare))
        # Establish all pairwise order relations; an incidental sort path is insufficient.
        for i, left in enumerate(ordered):
            for right in ordered[i + 1 :]:
                if compare(left, right) > 0:
                    raise _UnresolvedOrder
    except _UnresolvedOrder:
        conservative = meter.div(family_alpha, _integer(len(claims), meter))
        return tuple(
            HolmDecision(
                c.locator_bytes,
                c.nominal_alpha if meter.compare(c.nominal_alpha, conservative) < 0 else conservative,
                "inconclusive",
                None,
            )
            for c in sorted(claims, key=lambda c: c.locator_bytes)
        )
    blocked = False
    output: list[HolmDecision] = []
    for index, claim in enumerate(ordered):
        allocated = meter.div(family_alpha, _integer(len(ordered) - index, meter))
        effective = claim.nominal_alpha if meter.compare(claim.nominal_alpha, allocated) < 0 else allocated
        outcome: Literal["pass", "fail", "inconclusive"]
        if blocked:
            outcome = "inconclusive"
        elif meter.compare(claim.probability.upper, effective) <= 0:
            outcome = "pass"
        elif meter.compare(claim.probability.lower, effective) > 0:
            outcome = "fail"
        else:
            outcome = "inconclusive"
        blocked = blocked or outcome != "pass"
        output.append(HolmDecision(claim.locator_bytes, effective, outcome, index))
    return tuple(output)

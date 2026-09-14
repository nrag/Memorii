from fractions import Fraction

import pytest
from acceptance.arithmetic import (
    ArithmeticBudget,
    ArithmeticMeter,
    HolmClaim,
    RationalInterval,
    WeightedObservation,
    _binomial_coefficient,
    clopper_pearson_bound,
    exact_binomial_tail,
    holm_complete,
    invert_weighted_hoeffding,
    parse_rational,
    weighted_hoeffding,
)


def meter() -> ArithmeticMeter:
    return ArithmeticMeter(ArithmeticBudget(4096, 100_000))


def test_exact_small_binomial_tails_and_endpoint_bounds() -> None:
    work = meter()
    assert exact_binomial_tail(2, 1, Fraction(1, 2), "greater_or_equal", work) == Fraction(3, 4)
    assert exact_binomial_tail(2, 1, Fraction(1, 2), "less_or_equal", work) == Fraction(3, 4)
    assert clopper_pearson_bound(3, 0, Fraction(1, 20), "lower", 8, work) == RationalInterval(Fraction(), Fraction())
    assert clopper_pearson_bound(3, 3, Fraction(1, 20), "upper", 8, work) == RationalInterval(Fraction(1), Fraction(1))
    assert clopper_pearson_bound(3, 1, Fraction(1), "lower", 8, work) == RationalInterval(Fraction(), Fraction(1))


def test_hoeffding_derives_margin_and_deterministic_branch() -> None:
    work = meter()
    fixed = (WeightedObservation(Fraction(1), Fraction(1), Fraction(1), Fraction(1)),)
    result = weighted_hoeffding(fixed, Fraction(1, 2), "lower", 12, work)
    assert result.probability == RationalInterval(Fraction(), Fraction())
    assert result.margin == Fraction(1, 2) and result.deterministic


def test_holm_complete_ties_and_prefix_stop() -> None:
    work = meter()
    claims = (
        HolmClaim(b"b", Fraction(1, 20), RationalInterval(Fraction(7, 100), Fraction(7, 100))),
        HolmClaim(b"a", Fraction(1, 20), RationalInterval(Fraction(1, 10), Fraction(1, 10))),
        HolmClaim(b"c", Fraction(1, 20), RationalInterval(Fraction(1, 100), Fraction(1, 100))),
    )
    result = holm_complete(claims, (b"a", b"b", b"c"), Fraction(1, 10), work)
    assert [item.locator_bytes for item in result] == [b"c", b"b", b"a"]
    assert [item.outcome for item in result] == ["pass", "fail", "inconclusive"]


def test_canonical_rational_and_budget_fail_closed() -> None:
    assert parse_rational("1", "2", meter()) == Fraction(1, 2)
    with pytest.raises(ValueError, match="malformed_rational"):
        parse_rational("2", "4", meter())
    with pytest.raises(ValueError, match="malformed_rational"):
        parse_rational("02", "4", meter())
    with pytest.raises(ValueError, match="resource_limit"):
        exact_binomial_tail(2, 1, Fraction(1, 2), "greater_or_equal", ArithmeticMeter(ArithmeticBudget(2, 1)))


def test_addition_preflights_cross_products_before_allocation() -> None:
    seen: list[str] = []
    work = ArithmeticMeter(ArithmeticBudget(7, 100), seen.append)
    with pytest.raises(ValueError, match="resource_limit"):
        work.add(Fraction(1, 8), Fraction(1, 8))
    assert "add" not in seen
    assert parse_rational("3", "4", ArithmeticMeter(ArithmeticBudget(3, 100))) == Fraction(3, 4)


def test_interior_cp_bounds_bracket_the_independent_tail_equation() -> None:
    alpha = Fraction(1, 4)
    lower = clopper_pearson_bound(3, 1, alpha, "lower", 8, meter())
    assert (
        exact_binomial_tail(3, 1, lower.lower, "greater_or_equal", meter())
        <= alpha
        <= exact_binomial_tail(3, 1, lower.upper, "greater_or_equal", meter())
    )
    upper = clopper_pearson_bound(3, 1, alpha, "upper", 8, meter())
    assert (
        exact_binomial_tail(3, 1, upper.lower, "less_or_equal", meter())
        >= alpha
        >= exact_binomial_tail(3, 1, upper.upper, "less_or_equal", meter())
    )


def test_nondegenerate_hoeffding_and_inverse_keep_an_uncertain_root_bracket() -> None:
    observations = (
        WeightedObservation(Fraction(1), Fraction(1, 2), Fraction(), Fraction(1)),
        WeightedObservation(Fraction(), Fraction(1, 2), Fraction(), Fraction(1)),
    )
    result = weighted_hoeffding(observations, Fraction(1, 4), "lower", 16, meter())
    assert not result.deterministic and result.exponent is not None
    assert Fraction() < result.probability.lower <= result.probability.upper < Fraction(1)
    bracket = invert_weighted_hoeffding(observations, Fraction(1, 4), "lower", Fraction(1, 2), 8, 1, meter())
    assert Fraction() <= bracket.lower < bracket.upper <= Fraction(1)


def test_holm_overlap_mixed_order_ties_and_alpha_one_are_conservative() -> None:
    overlapping = (
        HolmClaim(b"a", Fraction(1), RationalInterval(Fraction(1, 10), Fraction(1, 5))),
        HolmClaim(b"b", Fraction(1), RationalInterval(Fraction(1, 10), Fraction(1, 5)), Fraction(2)),
    )
    unresolved = holm_complete(overlapping, (b"a", b"b"), Fraction(1), meter())
    assert all(item.outcome == "inconclusive" and item.rank is None for item in unresolved)
    ties = (
        HolmClaim(b"b", Fraction(1), RationalInterval(Fraction(1, 25), Fraction(3, 50)), Fraction(3)),
        HolmClaim(b"a", Fraction(1), RationalInterval(Fraction(1, 25), Fraction(3, 50)), Fraction(3)),
    )
    ordered = holm_complete(ties, (b"a", b"b"), Fraction(1), meter())
    assert [item.locator_bytes for item in ordered] == [b"a", b"b"]


def test_metered_binomial_recurrence_is_exact_and_preflights_each_product() -> None:
    assert _binomial_coefficient(6, 3, meter()) == Fraction(20)
    boundaries: list[str] = []
    restrictive = ArithmeticMeter(ArithmeticBudget(4, 100), boundaries.append)
    with pytest.raises(ValueError, match="resource_limit"):
        _binomial_coefficient(6, 3, restrictive)
    assert boundaries.count("binomial_coefficient") == 1


def test_operation_budget_is_monotonic_across_binomial_recurrence() -> None:
    work = ArithmeticMeter(ArithmeticBudget(64, 1))
    with pytest.raises(ValueError, match="resource_limit"):
        _binomial_coefficient(6, 3, work)
    assert work.operations == 1

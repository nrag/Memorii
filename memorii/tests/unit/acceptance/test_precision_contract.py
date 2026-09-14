"""Public fixed-step cases; dyadic brackets are independently specified literals."""

import json
from fractions import Fraction
from io import BytesIO

import pytest
from acceptance.arithmetic import ArithmeticBudget, ArithmeticMeter, clopper_pearson_bound
from acceptance.statistical_certification import EnclosedValue, evaluate_certificate, verify_certificate
from test_statistical_certification import inputs, raw, synthetic_binding


@pytest.mark.parametrize(
    "method,direction,labels,coarse,fine",
    (
        ("exact_binomial", "upper", ("0.00", "1.00"), (45, 46), (181, 182)),
        ("weighted_hoeffding", "lower", ("0.80", "0.80"), (24, 25), (98, 99)),
        ("weighted_hoeffding", "upper", ("0.20", "0.20"), (39, 40), (157, 158)),
    ),
)
def test_public_bounds_honor_precision(method, direction, labels, coarse, fine):
    p, e, _, limits = inputs()
    policy, evidence = json.loads(p), json.loads(e)
    gate = policy["gates"][0]
    gate["method"], gate["direction"] = method, direction
    gate["estimand"] = "cluster_any_failure" if method == "exact_binomial" else "cluster_macro_mean"
    gate["iid_declared"] = method == "exact_binomial"
    member = policy["memberships"][0]
    event = evidence["events"][0]
    policy["memberships"] = [
        {
            **member,
            "cluster_id": f"cluster_{i}",
            "provenance_ids": [f"source_{i}"],
            "expected_event_ids": [f"event_{i}"],
            "weight": {"encoding_spec_id": "weight", "fixed_scale_value": "0.50"},
        }
        for i in range(2)
    ]
    evidence["events"] = [
        {
            **event,
            "event_id": f"event_{i}",
            "provenance_id": f"source_{i}",
            "value": {"encoding_spec_id": "metric", "fixed_scale_value": label},
        }
        for i, label in enumerate(labels)
    ]
    brackets = []
    for precision, expected in ((6, coarse), (8, fine)):
        policy["precision"] = precision
        policy_bytes, evidence_bytes = raw(policy), raw(evidence)
        binding = synthetic_binding(policy_bytes, evidence_bytes, limits)
        candidate = evaluate_certificate(BytesIO(policy_bytes), BytesIO(evidence_bytes), binding, limits)
        result = verify_certificate(BytesIO(candidate), BytesIO(policy_bytes), BytesIO(evidence_bytes), binding, limits)
        bound = result.results[0].confidence_bound
        assert isinstance(bound, EnclosedValue)
        actual = (
            Fraction(bound.lower.numerator, bound.lower.denominator),
            Fraction(bound.upper.numerator, bound.upper.denominator),
        )
        assert actual == tuple(Fraction(v, 2**precision) for v in expected)
        assert actual[1] - actual[0] == Fraction(1, 2**precision)
        brackets.append(actual)
    assert brackets[0][0] <= brackets[1][0] < brackets[1][1] <= brackets[0][1]
    assert brackets[0] != brackets[1]


@pytest.mark.parametrize("successes,direction,point", ((0, "lower", 0), (3, "upper", 1)))
def test_alpha_one_retains_exact_cp_endpoint(successes, direction, point):
    result = clopper_pearson_bound(
        3, successes, Fraction(1), direction, 8, ArithmeticMeter(ArithmeticBudget(1024, 40000))
    )
    assert result.lower == result.upper == point

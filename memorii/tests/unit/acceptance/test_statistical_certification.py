from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from io import BytesIO

import acceptance.statistical_certification as statistical_certification
import pytest
from acceptance.ctv import NumericCtvError, encode_typed_value
from acceptance.statistical_certification import (
    GateLocator,
    HeldBinding,
    NumericAuthority,
    PreverifiedNumericCertificationContext,
    PreverifiedNumericGate,
    TransportLimits,
    WireRejected,
    evaluate_certificate,
    locator_bytes,
    verify_certificate,
)


def raw(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("ascii")


def test_numeric_ctv_v1_closed_algebra_literal() -> None:
    assert encode_typed_value({"z": (1, True, None), "a": ["métric"]}) == (
        b'{"$type":"map","entries":[["a",{"$type":"list","items":["m\xc3\xa9tric"]}],'
        b'["z",{"$type":"tuple","items":[{"$type":"integer","value":"1"},true,null]}]]}'
    )


@pytest.mark.parametrize("value", [{1: "x"}, object(), "\ud800"])
def test_numeric_ctv_rejects_values_outside_closed_algebra(value: object) -> None:
    with pytest.raises(NumericCtvError):
        encode_typed_value(value)


def test_public_evaluator_rejects_escaped_surrogate_before_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    p, e, binding, limits = inputs()
    policy = json.loads(p)
    policy["gates"][0]["locator"]["metric_id"] = "\ud800"
    changed_policy = raw(policy)
    rebound = replace(binding, policy_sha256=sha256(changed_policy).hexdigest())
    encoded: list[bool] = []
    monkeypatch.setattr(statistical_certification, "ENCODER_HOOK", lambda: encoded.append(True))
    with pytest.raises(WireRejected, match="identifier"):
        candidate(changed_policy, e, rebound, limits)
    assert encoded == []


def synthetic_authority() -> NumericAuthority:
    """Fixture-only stand-in for an acceptance owner's independently held authority."""
    return NumericAuthority(
        "b" * 64,
        "c" * 64,
        "a" * 64,
        "d" * 64,
        "e" * 64,
        "synthetic-release",
        "f" * 64,
        "5" * 64,
        "0" * 64,
        "1" * 64,
        "2" * 64,
        "3" * 64,
        "4" * 64,
        "6" * 64,
    )


def synthetic_binding(
    policy: bytes,
    evidence: bytes,
    limits: TransportLimits,
    authority: NumericAuthority | None = None,
) -> HeldBinding:
    """Construct test-only acceptance output; production receives it independently."""
    parsed = statistical_certification._policy(policy, limits)
    expected_authority = authority or synthetic_authority()
    context = PreverifiedNumericCertificationContext(
        expected_authority,
        parsed.specs,
        parsed.family_alpha,
        parsed.family_alpha_spec_id,
        tuple(PreverifiedNumericGate(gate, gate.iid_declared) for gate in parsed.gates),
        parsed.memberships,
    )
    return HeldBinding(
        sha256(policy).hexdigest(),
        sha256(evidence).hexdigest(),
        expected_authority,
        context,
    )


def inputs(
    event: str | None = "0.00",
) -> tuple[bytes, bytes, HeldBinding, TransportLimits]:
    def q(spec: str, value: str) -> dict[str, str]:
        return {"encoding_spec_id": spec, "fixed_scale_value": value}

    locator = {
        "capability_fingerprint": "a" * 64,
        "cell_id": "cell",
        "metric_id": "metric",
    }
    specs = [
        {
            "encoding_spec_id": "probability",
            "unit": "probability",
            "scale": 2,
            "lower": "0.00",
            "upper": "1.00",
            "lower_inclusive": False,
            "upper_inclusive": True,
            "reject_inexact": True,
        },
        {
            "encoding_spec_id": "weight",
            "unit": "weight",
            "scale": 2,
            "lower": "0.00",
            "upper": "1.00",
            "lower_inclusive": True,
            "upper_inclusive": True,
            "reject_inexact": True,
        },
        {
            "encoding_spec_id": "metric",
            "unit": "metric",
            "scale": 2,
            "lower": "0.00",
            "upper": "1.00",
            "lower_inclusive": True,
            "upper_inclusive": True,
            "reject_inexact": True,
        },
    ]
    gate = {
        "locator": locator,
        "method": "exact_binomial",
        "direction": "upper",
        "estimand": "cluster_any_failure",
        "threshold": q("metric", "0.50"),
        "nominal_alpha": q("probability", "0.50"),
        "minimum_clusters": 1,
        "threshold_spec_id": "metric",
        "nominal_alpha_spec_id": "probability",
        "lower_spec_id": "metric",
        "upper_spec_id": "metric",
        "weight_spec_id": "weight",
        "event_value_spec_id": "metric",
        "iid_declared": True,
    }
    member = {
        "cluster_id": "cluster",
        "locator": locator,
        "provenance_ids": ["source"],
        "expected_event_ids": ["event"],
        "weight": q("weight", "1.00"),
        "lower": q("metric", "0.00"),
        "upper": q("metric", "1.00"),
    }
    policy = {
        "schema": "statistical_acceptance_policy.v2",
        "arithmetic_bits": 1024,
        "arithmetic_operations": 40000,
        "precision": 8,
        "output_cap": 40000,
        "family_alpha": q("probability", "0.50"),
        "family_alpha_spec_id": "probability",
        "specs": specs,
        "gates": [gate],
        "memberships": [member],
    }
    evidence = {
        "schema": "statistical_acceptance_evidence.v2",
        "events": [
            {
                "event_id": "event",
                "provenance_id": "source",
                "locator": locator,
                "value": None if event is None else q("metric", event),
            }
        ]
    }
    p, e = raw(policy), raw(evidence)
    limits = TransportLimits(40000, 40000, 40000, 2048, 50000, 12, 40000, 8, 32, 8000, 2000)
    return p, e, synthetic_binding(p, e, limits), limits


def candidate(
    p: bytes | BytesIO,
    e: bytes | BytesIO,
    binding: HeldBinding,
    limits: TransportLimits,
) -> bytes:
    return evaluate_certificate(
        BytesIO(p) if isinstance(p, bytes) else p,
        BytesIO(e) if isinstance(e, bytes) else e,
        binding,
        limits,
    )


def mutated(candidate_bytes: bytes, change) -> bytes:
    body = _decode_numeric_ctv(json.loads(candidate_bytes))
    assert isinstance(body, dict)
    change(body)
    return encode_typed_value(body)


def _decode_numeric_ctv(value: object) -> object:
    """Test-only inverse for the closed numeric CTV values used in candidates."""
    if value is None or type(value) in {bool, str}:
        return value
    if type(value) is not dict:
        raise TypeError("numeric CTV node invalid")
    tag = value.get("$type")
    if tag == "integer" and set(value) == {"$type", "value"} and type(value["value"]) is str:
        return int(value["value"])
    if tag in {"list", "tuple"} and set(value) == {"$type", "items"} and type(value["items"]) is list:
        members = [_decode_numeric_ctv(item) for item in value["items"]]
        return members if tag == "list" else tuple(members)
    if tag == "map" and set(value) == {"$type", "entries"} and type(value["entries"]) is list:
        return {key: _decode_numeric_ctv(item) for key, item in value["entries"] if type(key) is str}
    raise TypeError("numeric CTV node invalid")


class TrackingBytes(BytesIO):
    def __init__(self, content: bytes) -> None:
        super().__init__(content)
        self.requests: list[int] = []
        self.consumed = 0

    def read(self, size: int = -1) -> bytes:
        self.requests.append(size)
        chunk = super().read(size)
        self.consumed += len(chunk)
        return chunk


def test_known_upper_tail_and_cp_endpoint_values() -> None:
    p, e, b, limits = inputs("0.00")
    result = verify_certificate(BytesIO(candidate(p, e, b, limits)), BytesIO(p), BytesIO(e), b, limits).results[0]
    assert result.raw_probability.kind == "exact"
    assert result.confidence_bound.kind == "exact"
    assert (
        result.raw_probability.value.numerator,
        result.raw_probability.value.denominator,
    ) == (1, 2)
    assert (
        result.confidence_bound.value.numerator,
        result.confidence_bound.value.denominator,
    ) == (1, 2)
    assert result.outcome == "pass"
    p1, e1, b1, limits1 = inputs("1.00")
    assert (
        verify_certificate(
            BytesIO(candidate(p1, e1, b1, limits1)),
            BytesIO(p1),
            BytesIO(e1),
            b1,
            limits1,
        )
        .results[0]
        .outcome
        == "fail"
    )


@pytest.mark.parametrize(
    "field",
    (
        "threshold",
        "nominal_alpha",
        "observed_successes",
        "raw_probability",
        "confidence_bound",
        "policy_sha256",
    ),
)
def test_reencoded_candidate_fields_cannot_override_recomputation(field: str) -> None:
    p, e, b, limits = inputs()

    def change(body: dict[str, object]) -> None:
        if field == "policy_sha256":
            body[field] = "0" * 64
            return
        source_rows = body["results"]
        assert isinstance(source_rows, (list, tuple))
        rows = list(source_rows)
        assert rows and isinstance(rows[0], dict)
        body["results"] = rows
        rows[0][field] = 9 if field == "observed_successes" else {"numerator": 9, "denominator": 10}

    with pytest.raises(WireRejected, match="certificate_mismatch"):
        verify_certificate(
            BytesIO(mutated(candidate(p, e, b, limits), change)),
            BytesIO(p),
            BytesIO(e),
            b,
            limits,
        )


def test_candidate_shape_and_held_document_mutations_reject() -> None:
    p, e, b, limits = inputs()
    c = candidate(p, e, b, limits)
    for change in (
        lambda body: body.__setitem__("extra", True),
        lambda body: body.pop("accepted"),
    ):
        with pytest.raises(WireRejected, match="certificate_mismatch"):
            verify_certificate(BytesIO(mutated(c, change)), BytesIO(p), BytesIO(e), b, limits)
    with pytest.raises(WireRejected, match="held_authority_digest"):
        verify_certificate(BytesIO(c), BytesIO(p.replace(b"0.50", b"0.49", 1)), BytesIO(e), b, limits)
    with pytest.raises(WireRejected, match="held_authority_digest"):
        verify_certificate(BytesIO(c), BytesIO(p), BytesIO(e.replace(b"0.00", b"1.00", 1)), b, limits)


def test_public_transport_exact_limits_and_limit_minus_one_reject() -> None:
    p, e, binding, limits = inputs()
    certificate = candidate(p, e, binding, limits)
    exact = replace(
        limits,
        max_candidate_bytes=len(certificate),
        max_policy_bytes=len(p),
        max_evidence_bytes=len(e),
    )
    assert verify_certificate(BytesIO(certificate), BytesIO(p), BytesIO(e), binding, exact).accepted

    for field, _stream in (
        ("max_candidate_bytes", "candidate"),
        ("max_policy_bytes", "policy"),
        ("max_evidence_bytes", "evidence"),
    ):
        reduced = replace(exact, **{field: getattr(exact, field) - 1})
        with pytest.raises(WireRejected, match="transport_limit"):
            verify_certificate(BytesIO(certificate), BytesIO(p), BytesIO(e), binding, reduced)


def test_public_transport_reads_at_most_limit_plus_one_bytes() -> None:
    p, e, binding, limits = inputs()
    certificate = candidate(p, e, binding, limits)
    streams = (
        ("max_candidate_bytes", certificate + b"x", p, e),
        ("max_policy_bytes", certificate, p + b"x", e),
        ("max_evidence_bytes", certificate, p, e + b"x"),
    )
    for field, candidate_bytes, policy_bytes, evidence_bytes in streams:
        cap = (
            len(
                {
                    "max_candidate_bytes": candidate_bytes,
                    "max_policy_bytes": policy_bytes,
                    "max_evidence_bytes": evidence_bytes,
                }[field]
            )
            - 1
        )
        bounded = replace(limits, **{field: cap})
        tracked = TrackingBytes(
            {
                "max_candidate_bytes": candidate_bytes,
                "max_policy_bytes": policy_bytes,
                "max_evidence_bytes": evidence_bytes,
            }[field]
        )
        arguments = (
            (tracked, BytesIO(policy_bytes), BytesIO(evidence_bytes))
            if field == "max_candidate_bytes"
            else (
                BytesIO(candidate_bytes),
                tracked if field == "max_policy_bytes" else BytesIO(policy_bytes),
                tracked if field == "max_evidence_bytes" else BytesIO(evidence_bytes),
            )
        )
        with pytest.raises(WireRejected, match="transport_limit"):
            verify_certificate(*arguments, binding, bounded)
        assert tracked.requests == [cap + 1]
        assert tracked.consumed == cap + 1


@pytest.mark.parametrize(
    "target,changed",
    (
        ("policy", lambda p, e: (p[:-1] + b',"precision":8}', e)),
        (
            "policy",
            lambda p, e: (
                p.replace(b'"threshold":', b'"threshold":{},"threshold":', 1),
                e,
            ),
        ),
        ("evidence", lambda p, e: (p, b'{"events":[],"events":[]}')),
        (
            "evidence",
            lambda p, e: (
                p,
                e.replace(b'"event_id":"event"', b'"event_id":"event","event_id":"other"', 1),
            ),
        ),
    ),
)
def test_duplicate_json_keys_reject_before_context(target: str, changed) -> None:
    p, e, binding, limits = inputs()
    changed_policy, changed_evidence = changed(p, e)
    admitted = replace(
        binding,
        policy_sha256=sha256(changed_policy).hexdigest(),
        evidence_sha256=sha256(changed_evidence).hexdigest(),
    )
    with pytest.raises(WireRejected, match="duplicate_json_key"):
        evaluate_certificate(BytesIO(changed_policy), BytesIO(changed_evidence), admitted, limits)


@pytest.mark.parametrize(
    "change,reason",
    (
        (lambda evidence: evidence.pop("events"), "evidence_shape"),
        (lambda evidence: evidence.__setitem__("extra", []), "evidence_shape"),
        (lambda evidence: evidence.__setitem__("events", {}), "events"),
        (lambda evidence: evidence["events"][0].pop("value"), "event_shape"),
        (
            lambda evidence: evidence["events"][0].__setitem__("extra", True),
            "event_shape",
        ),
    ),
)
def test_evidence_missing_extra_and_wrong_types_reject(change, reason: str) -> None:
    p, e, binding, limits = inputs()
    evidence = json.loads(e)
    change(evidence)
    changed = raw(evidence)
    admitted = replace(binding, evidence_sha256=sha256(changed).hexdigest())
    with pytest.raises(WireRejected, match=reason):
        evaluate_certificate(BytesIO(p), BytesIO(changed), admitted, limits)


@pytest.mark.parametrize(
    "target,schema,reason",
    (
        ("policy", None, "policy_shape"),
        ("policy", "statistical_acceptance_policy.v1", "policy_schema"),
        ("evidence", None, "evidence_shape"),
        ("evidence", "statistical_acceptance_evidence.v1", "evidence_schema"),
    ),
)
def test_policy_and_evidence_require_explicit_v2_schema(
    target: str, schema: str | None, reason: str
) -> None:
    p, e, binding, limits = inputs()
    value = json.loads(p if target == "policy" else e)
    if schema is None:
        value.pop("schema")
    else:
        value["schema"] = schema
    changed = raw(value)
    admitted = replace(
        binding,
        policy_sha256=sha256(changed).hexdigest() if target == "policy" else binding.policy_sha256,
        evidence_sha256=sha256(changed).hexdigest() if target == "evidence" else binding.evidence_sha256,
    )
    with pytest.raises(WireRejected, match=reason):
        evaluate_certificate(
            BytesIO(changed if target == "policy" else p),
            BytesIO(changed if target == "evidence" else e),
            admitted,
            limits,
        )


@pytest.mark.parametrize(
    "value,reason",
    (
        ("1e-1", "decimal_invalid"),
        ("+0.50", "decimal_invalid"),
        ("-0.00", "decimal_negative_zero"),
        ("0.5", "decimal_scale"),
        ("0.500", "decimal_scale"),
        ("0.00", "decimal_range"),
    ),
)
def test_decimal_grammar_precision_and_zero_alpha_reject(value: str, reason: str) -> None:
    p, e, _, limits = inputs()
    policy = json.loads(p)
    policy["family_alpha"] = {
        "encoding_spec_id": "probability",
        "fixed_scale_value": value,
    }
    changed = raw(policy)
    with pytest.raises(WireRejected, match=reason):
        evaluate_certificate(BytesIO(changed), BytesIO(e), synthetic_binding(changed, e, limits), limits)


def test_literal_locator_ctv_bytes_cover_ascii_escapes_and_utf8() -> None:
    fingerprint = "a" * 64
    assert locator_bytes(GateLocator(fingerprint, "cell", "metric")) == (
        b'{"$type":"map","entries":[["capability_fingerprint","'
        + b"a" * 64
        + b'"],["cell_id","cell"],["metric_id","metric"]]}'
    )
    assert locator_bytes(GateLocator(fingerprint, 'cell\n"', "metric\\")) == (
        b'{"$type":"map","entries":[["capability_fingerprint","'
        + b"a" * 64
        + b'"],["cell_id","cell\\n\\""],["metric_id","metric\\\\"]]}'
    )
    assert locator_bytes(GateLocator(fingerprint, "métric", "x")) == (
        b'{"$type":"map","entries":[["capability_fingerprint","'
        + b"a" * 64
        + b'"],["cell_id","m\xc3\xa9tric"],["metric_id","x"]]}'
    )


def test_null_and_duplicate_provenance_are_not_dropped() -> None:
    p, e, b, limits = inputs(None)
    assert (
        verify_certificate(BytesIO(candidate(p, e, b, limits)), BytesIO(p), BytesIO(e), b, limits).results[0].outcome
        == "fail"
    )
    body = json.loads(p)
    body["memberships"].append(
        {
            **body["memberships"][0],
            "cluster_id": "cluster_two",
            "expected_event_ids": ["event_two"],
        }
    )
    p2 = raw(body)
    with pytest.raises(WireRejected, match="dependent_clusters"):
        evaluate_certificate(
            BytesIO(p2),
            BytesIO(e),
            synthetic_binding(p2, e, limits),
            limits,
        )


def test_short_reads_integer_limit_and_output_preflight() -> None:
    class Short(BytesIO):
        def read(self, size: int = -1) -> bytes:
            return super().read(3 if size < 0 else min(size, 3))

    p, e, b, limits = inputs()
    assert candidate(Short(p), Short(e), b, limits)
    oversized = p.replace(b'"precision":8', b'"precision":123456789')
    with pytest.raises(WireRejected, match="metadata_integer_limit"):
        evaluate_certificate(
            BytesIO(oversized),
            BytesIO(e),
            replace(b, policy_sha256=sha256(oversized).hexdigest()),
            limits,
        )
    capped = p.replace(b'"output_cap":40000', b'"output_cap":1')
    calls: list[bool] = []
    statistical_certification.ENCODER_HOOK = lambda: calls.append(True)
    try:
        with pytest.raises(WireRejected, match="output_cap"):
            evaluate_certificate(
                BytesIO(capped),
                BytesIO(e),
                synthetic_binding(capped, e, limits),
                limits,
            )
    finally:
        statistical_certification.ENCODER_HOOK = None
    assert not calls


@pytest.mark.parametrize(
    "needle,replacement,reason",
    (
        (
            b'"fixed_scale_value":"0.50"',
            b'"fixed_scale_value":"0.5"',
            "numeric_context_policy",
        ),
        (b'"method":"exact_binomial"', b'"method":true', "gate_value"),
    ),
)
def test_noncanonical_or_wrongly_typed_policy_never_becomes_a_candidate(
    needle: bytes, replacement: bytes, reason: str
) -> None:
    p, e, b, limits = inputs()
    changed = p.replace(needle, replacement, 1)
    changed_binding = replace(b, policy_sha256=sha256(changed).hexdigest())
    with pytest.raises(WireRejected, match=reason):
        evaluate_certificate(BytesIO(changed), BytesIO(e), changed_binding, limits)


def test_holm_rank_and_alpha_follow_locator_not_policy_input_order() -> None:
    p, e, _, limits = inputs()
    policy, evidence = json.loads(p), json.loads(e)
    first_gate = policy["gates"][0]
    first_member = policy["memberships"][0]
    second_locator = {**first_gate["locator"], "metric_id": "metric_two"}
    second_gate = {**first_gate, "locator": second_locator, "minimum_clusters": 2}
    second_members = [
        {
            **first_member,
            "cluster_id": "cluster_two_a",
            "locator": second_locator,
            "provenance_ids": ["source_two_a"],
            "expected_event_ids": ["event_two_a"],
            "weight": {"encoding_spec_id": "weight", "fixed_scale_value": "0.50"},
        },
        {
            **first_member,
            "cluster_id": "cluster_two_b",
            "locator": second_locator,
            "provenance_ids": ["source_two_b"],
            "expected_event_ids": ["event_two_b"],
            "weight": {"encoding_spec_id": "weight", "fixed_scale_value": "0.50"},
        },
    ]
    policy["memberships"][0]["weight"] = {
        "encoding_spec_id": "weight",
        "fixed_scale_value": "1.00",
    }
    policy["gates"] = [second_gate, first_gate]
    policy["memberships"] = [*second_members, first_member]
    evidence["events"].extend(
        [
            {
                "event_id": "event_two_a",
                "provenance_id": "source_two_a",
                "locator": second_locator,
                "value": {"encoding_spec_id": "metric", "fixed_scale_value": "0.00"},
            },
            {
                "event_id": "event_two_b",
                "provenance_id": "source_two_b",
                "locator": second_locator,
                "value": {"encoding_spec_id": "metric", "fixed_scale_value": "0.00"},
            },
        ]
    )
    p2, e2 = raw(policy), raw(evidence)
    binding = synthetic_binding(p2, e2, limits)
    certificate = verify_certificate(
        BytesIO(candidate(p2, e2, binding, limits)),
        BytesIO(p2),
        BytesIO(e2),
        binding,
        limits,
    )
    by_metric = {result.locator.metric_id: result for result in certificate.results}
    assert (
        by_metric["metric_two"].holm_rank,
        by_metric["metric_two"].effective_alpha.numerator,
        by_metric["metric_two"].effective_alpha.denominator,
    ) == (0, 1, 4)
    assert (
        by_metric["metric"].holm_rank,
        by_metric["metric"].effective_alpha.numerator,
        by_metric["metric"].effective_alpha.denominator,
    ) == (1, 1, 2)


def test_public_holm_ties_follow_canonical_locator_order() -> None:
    p, e, _, limits = inputs()
    policy, evidence = json.loads(p), json.loads(e)
    original_gate, original_member = policy["gates"][0], policy["memberships"][0]
    earlier_locator = {**original_gate["locator"], "metric_id": "aaa"}
    earlier_gate = {**original_gate, "locator": earlier_locator}
    earlier_member = {
        **original_member,
        "cluster_id": "earlier-cluster",
        "locator": earlier_locator,
        "provenance_ids": ["earlier-source"],
        "expected_event_ids": ["earlier-event"],
    }
    earlier_event = {
        "event_id": "earlier-event",
        "provenance_id": "earlier-source",
        "locator": earlier_locator,
        "value": {"encoding_spec_id": "metric", "fixed_scale_value": "0.00"},
    }
    policy["gates"] = [original_gate, earlier_gate]
    policy["memberships"] = [original_member, earlier_member]
    evidence["events"].append(earlier_event)
    p2, e2 = raw(policy), raw(evidence)
    binding = synthetic_binding(p2, e2, limits)
    certificate = verify_certificate(
        BytesIO(candidate(p2, e2, binding, limits)),
        BytesIO(p2),
        BytesIO(e2),
        binding,
        limits,
    )
    by_metric = {result.locator.metric_id: result for result in certificate.results}
    assert (
        by_metric["aaa"].holm_rank,
        by_metric["aaa"].effective_alpha.numerator,
        by_metric["aaa"].effective_alpha.denominator,
    ) == (0, 1, 4)
    assert (
        by_metric["metric"].holm_rank,
        by_metric["metric"].effective_alpha.numerator,
        by_metric["metric"].effective_alpha.denominator,
    ) == (1, 1, 2)


def test_macro_mean_derives_labels_and_missing_uses_upper_endpoint() -> None:
    p, e, _, limits = inputs()
    policy, evidence = json.loads(p), json.loads(e)
    gate, member = policy["gates"][0], policy["memberships"][0]
    gate.update(
        {
            "method": "weighted_hoeffding",
            "estimand": "cluster_macro_mean",
            "iid_declared": False,
            "minimum_clusters": 2,
        }
    )
    first = {
        **member,
        "cluster_id": "macro_a",
        "provenance_ids": ["macro_source_a"],
        "expected_event_ids": ["macro_a"],
        "weight": {"encoding_spec_id": "weight", "fixed_scale_value": "0.50"},
    }
    second = {
        **member,
        "cluster_id": "macro_b",
        "provenance_ids": ["macro_source_b"],
        "expected_event_ids": ["macro_b"],
        "weight": {"encoding_spec_id": "weight", "fixed_scale_value": "0.50"},
    }
    policy["memberships"] = [first, second]
    evidence["events"] = [
        {
            "event_id": "macro_a",
            "provenance_id": "macro_source_a",
            "locator": gate["locator"],
            "value": {"encoding_spec_id": "metric", "fixed_scale_value": "0.20"},
        },
        {
            "event_id": "macro_b",
            "provenance_id": "macro_source_b",
            "locator": gate["locator"],
            "value": None,
        },
    ]
    p2, e2 = raw(policy), raw(evidence)
    binding = synthetic_binding(p2, e2, limits)
    result = verify_certificate(
        BytesIO(candidate(p2, e2, binding, limits)),
        BytesIO(p2),
        BytesIO(e2),
        binding,
        limits,
    ).results[0]
    assert (result.weighted_mean.numerator, result.weighted_mean.denominator) == (3, 5)


def test_unicode_locator_and_exact_output_cap() -> None:
    p, e, _, limits = inputs()
    policy, evidence = json.loads(p), json.loads(e)
    locator = policy["gates"][0]["locator"]
    locator["cell_id"] = 'cell\n"'
    locator["metric_id"] = "métric"
    policy["memberships"][0]["locator"] = locator
    evidence["events"][0]["locator"] = locator
    p2, e2 = raw(policy), raw(evidence)
    binding = synthetic_binding(p2, e2, limits)
    initial = candidate(p2, e2, binding, limits)
    policy["output_cap"] = len(initial)
    exact_policy = raw(policy)
    exact_binding = synthetic_binding(exact_policy, e2, limits)
    materialized: list[bool] = []
    encoded: list[bool] = []
    statistical_certification.MATERIALIZER_HOOK = lambda: materialized.append(True)
    statistical_certification.ENCODER_HOOK = lambda: encoded.append(True)
    try:
        exact = candidate(exact_policy, e2, exact_binding, limits)
    finally:
        statistical_certification.MATERIALIZER_HOOK = None
        statistical_certification.ENCODER_HOOK = None
    assert len(exact) == len(initial)
    assert materialized == [True]
    assert encoded == [True]
    policy["output_cap"] -= 1
    too_small = raw(policy)
    materialized = []
    encoded = []
    statistical_certification.MATERIALIZER_HOOK = lambda: materialized.append(True)
    statistical_certification.ENCODER_HOOK = lambda: encoded.append(True)
    try:
        with pytest.raises(WireRejected, match="output_cap"):
            candidate(
                too_small,
                e2,
                synthetic_binding(too_small, e2, limits),
                limits,
            )
    finally:
        statistical_certification.MATERIALIZER_HOOK = None
        statistical_certification.ENCODER_HOOK = None
    assert materialized == []
    assert encoded == []


@pytest.mark.parametrize(
    "change",
    (
        lambda policy: policy.__setitem__(
            "family_alpha",
            {"encoding_spec_id": "probability", "fixed_scale_value": "0.49"},
        ),
        lambda policy: policy["gates"][0].__setitem__("direction", "lower"),
        lambda policy: policy["gates"][0].__setitem__("method", "weighted_hoeffding"),
        lambda policy: policy["memberships"][0].__setitem__(
            "lower", {"encoding_spec_id": "metric", "fixed_scale_value": "0.01"}
        ),
        lambda policy: policy["memberships"][0].__setitem__(
            "weight", {"encoding_spec_id": "weight", "fixed_scale_value": "0.50"}
        ),
        lambda policy: policy["gates"][0].__setitem__("minimum_clusters", 2),
        lambda policy: policy["memberships"][0].__setitem__("cluster_id", "other-cluster"),
        lambda policy: policy["memberships"][0].__setitem__("provenance_ids", ["other-source"]),
        lambda policy: policy["memberships"][0].__setitem__("expected_event_ids", ["other-event"]),
        lambda policy: policy["gates"][0].__setitem__("iid_declared", False),
    ),
)
def test_refreshed_policy_digest_cannot_override_fixed_preverified_context(
    change,
) -> None:
    p, e, binding, limits = inputs()
    policy = json.loads(p)
    change(policy)
    changed = raw(policy)
    refreshed_digest = replace(binding, policy_sha256=sha256(changed).hexdigest())
    with pytest.raises(WireRejected, match="numeric_context_policy"):
        evaluate_certificate(BytesIO(changed), BytesIO(e), refreshed_digest, limits)


def test_fixed_context_rejects_omitted_or_extra_internally_coherent_gates() -> None:
    p, e, binding, limits = inputs()
    policy, evidence = json.loads(p), json.loads(e)
    locator = {**policy["gates"][0]["locator"], "metric_id": "metric-two"}
    second_gate = {**policy["gates"][0], "locator": locator}
    second_member = {
        **policy["memberships"][0],
        "cluster_id": "cluster-two",
        "locator": locator,
        "provenance_ids": ["source-two"],
        "expected_event_ids": ["event-two"],
    }
    second_event = {
        "event_id": "event-two",
        "provenance_id": "source-two",
        "locator": locator,
        "value": {"encoding_spec_id": "metric", "fixed_scale_value": "0.00"},
    }
    policy["gates"].append(second_gate)
    policy["memberships"].append(second_member)
    evidence["events"].append(second_event)
    expanded_policy, expanded_evidence = raw(policy), raw(evidence)

    with pytest.raises(WireRejected, match="numeric_context_policy"):
        evaluate_certificate(
            BytesIO(expanded_policy),
            BytesIO(expanded_evidence),
            replace(
                binding,
                policy_sha256=sha256(expanded_policy).hexdigest(),
                evidence_sha256=sha256(expanded_evidence).hexdigest(),
            ),
            limits,
        )

    expanded_context = synthetic_binding(expanded_policy, expanded_evidence, limits)
    policy["gates"] = policy["gates"][:1]
    policy["memberships"] = policy["memberships"][:1]
    evidence["events"] = evidence["events"][:1]
    reduced_policy, reduced_evidence = raw(policy), raw(evidence)
    with pytest.raises(WireRejected, match="numeric_context_policy"):
        evaluate_certificate(
            BytesIO(reduced_policy),
            BytesIO(reduced_evidence),
            replace(
                expanded_context,
                policy_sha256=sha256(reduced_policy).hexdigest(),
                evidence_sha256=sha256(reduced_evidence).hexdigest(),
            ),
            limits,
        )


def test_fixed_context_rejects_internally_coherent_cross_cell_policy() -> None:
    p, e, binding, limits = inputs()
    policy, evidence = json.loads(p), json.loads(e)
    cross_cell = {**policy["gates"][0]["locator"], "cell_id": "other-cell"}
    policy["gates"][0]["locator"] = cross_cell
    policy["memberships"][0]["locator"] = cross_cell
    evidence["events"][0]["locator"] = cross_cell
    changed_policy, changed_evidence = raw(policy), raw(evidence)
    with pytest.raises(WireRejected, match="numeric_context_policy"):
        evaluate_certificate(
            BytesIO(changed_policy),
            BytesIO(changed_evidence),
            replace(
                binding,
                policy_sha256=sha256(changed_policy).hexdigest(),
                evidence_sha256=sha256(changed_evidence).hexdigest(),
            ),
            limits,
        )


def test_synthetic_context_rejects_lower_any_failure_safety_gate() -> None:
    p, e, _, limits = inputs()
    policy = json.loads(p)
    policy["gates"][0]["direction"] = "lower"
    changed = raw(policy)
    with pytest.raises(WireRejected, match="safety_gate_direction"):
        evaluate_certificate(BytesIO(changed), BytesIO(e), synthetic_binding(changed, e, limits), limits)


def test_exact_binomial_requires_preverified_iid_context() -> None:
    p, e, binding, limits = inputs()
    gate = binding.context.expected_gates[0]
    context = replace(
        binding.context,
        expected_gates=(PreverifiedNumericGate(gate.gate, False),),
    )
    inadmissible = replace(binding, context=context)
    with pytest.raises(WireRejected, match="numeric_context_gate"):
        evaluate_certificate(BytesIO(p), BytesIO(e), inadmissible, limits)


@pytest.mark.parametrize(
    "field",
    tuple(field.name for field in statistical_certification.fields(NumericAuthority)),
)
def test_context_authority_must_equal_every_independently_held_authority_field(
    field: str,
) -> None:
    _, _, binding, _ = inputs()
    replacement = "other-release" if field == "coverage_release_id" else "9" * 64
    other_authority = replace(binding.expected_authority, **{field: replacement})
    with pytest.raises(WireRejected, match="numeric_context_authority"):
        HeldBinding(
            binding.policy_sha256,
            binding.evidence_sha256,
            other_authority,
            binding.context,
        )


def test_candidate_authority_cannot_supply_or_replace_held_context() -> None:
    p, e, binding, limits = inputs()

    def change(body: dict[str, object]) -> None:
        authority = body["authority"]
        assert isinstance(authority, dict)
        authority["coverage_release_id"] = "candidate-release"

    with pytest.raises(WireRejected, match="certificate_mismatch"):
        verify_certificate(
            BytesIO(mutated(candidate(p, e, binding, limits), change)),
            BytesIO(p),
            BytesIO(e),
            binding,
            limits,
        )

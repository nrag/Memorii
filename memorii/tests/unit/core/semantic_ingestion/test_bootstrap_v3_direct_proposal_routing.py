"""Route ownership proof for retained structured V3 lifecycle proposals."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from memorii.core.semantic_ingestion import bootstrap_v3_proposal as proposal_module
from memorii.core.semantic_ingestion.bootstrap_v3_proposal import (
    DirectBootstrapV3ProposalProducer,
)


def _request(start: int, end: int) -> object:
    return SimpleNamespace(
        segment=SimpleNamespace(
            context_text=SimpleNamespace(projection_digest="projection"),
            bootstrap_projection=SimpleNamespace(
                bootstrap_route=SimpleNamespace(
                    unicode_scalar_start=start, unicode_scalar_end=end,
                )
            ),
        )
    )


def _producer(*operations: tuple[str, str]) -> DirectBootstrapV3ProposalProducer:
    corrections = tuple(
        SimpleNamespace(assertion_quote=assertion, correction_anchor_quote=anchor)
        for assertion, anchor in operations
    )
    proposal = SimpleNamespace(
        facts=(), corrections=corrections, retractions=(), action_states=(),
        identity_operations=(),
    )

    def resolve(quote: str, _context: object, owned: bool) -> object:
        assert owned is (quote == "Correction")
        starts = {"Correction: first": 10, "Correction: second": 30}
        start = _context.projection_span.start if owned else starts[quote]
        return SimpleNamespace(
            projection_span=SimpleNamespace(start=start, end=start + len(quote)),
            segment_local_span=SimpleNamespace(start=start, end=start + len(quote)),
        )

    return DirectBootstrapV3ProposalProducer(
        proposal=proposal, raw_proposal_artifact=b"proposal", resolve_quote=resolve,
        projection_quote_verifier=SimpleNamespace(verify_quote=lambda **_kwargs: None),
    )


def test_direct_producer_assigns_two_route_correction_once_and_abstains_sibling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    producer = _producer(("Correction: first", "Correction"))
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        proposal_module,
        "seal_bootstrap_proposal_run",
        lambda **kwargs: captured.update(kwargs) or "sealed",
    )
    authority = SimpleNamespace(
        proposal_requests=(_request(0, 30), _request(30, 50)),
        payload_limit_authority=object(),
    )

    assert producer.produce(authority=authority, renew=lambda: True) == "sealed"
    responses = captured["responses"]
    assert responses[0] is producer._proposal
    assert responses[1].abstained is True


@pytest.mark.parametrize(
    ("requests", "operations"),
    [
        ((_request(20, 30),), (("Correction: first", "Correction"),)),
        ((_request(0, 30), _request(0, 30)), (("Correction: first", "Correction"),)),
        (
            (_request(0, 30), _request(30, 50)),
            (("Correction: first", "Correction"), ("Correction: second", "Correction")),
        ),
    ],
    ids=("zero-owner", "ambiguous-owner", "split-operation-owners"),
)
def test_direct_producer_rejects_nonunique_lifecycle_route_ownership(
    requests: tuple[object, ...], operations: tuple[tuple[str, str], ...],
) -> None:
    producer = _producer(*operations)
    with pytest.raises(ValueError):
        producer._owning_request(requests)  # type: ignore[arg-type]

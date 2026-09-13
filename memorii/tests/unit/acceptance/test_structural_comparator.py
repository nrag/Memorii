"""Focused proof for the public structural-comparison acceptance slice."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from acceptance.structural_comparator import (
    ExpectedOperation,
    StructuralComparisonError,
    align_operations,
    canonical_expected_span,
    collect_graph_observation,
)
from memorii.core.memory_evolution.graph_ingestion_observation_records import (
    ObservedOperationIntroduction,
)
from memorii.core.memory_evolution.graph_observation_contracts import (
    GraphObservationFailure,
)
from memorii.core.memory_evolution.graph_observation_public_contracts import (
    GraphObservationPage,
    GraphObservationRequest,
)
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
    GraphObservationRecordKey,
    ResolvedGraphObservationCohort,
)
from memorii.core.memory_evolution.graph_observation_streams import (
    GraphObservationStreamRecord,
    OperationIntroductionStreamRecord,
)
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.semantic_ingestion.contracts import SourceSpanReference


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _span(value: str) -> SourceSpanReference:
    # The comparator only consumes the already validated public representation.
    return SourceSpanReference.model_construct(source_id="source", source_reference=value)


def _introduction(
    *, operation_id: str, fence_id: str, source_id: str = "source", kind: str = "claim", span: str = "a"
) -> OperationIntroductionStreamRecord:
    payload = ObservedOperationIntroduction.model_construct(
        operation_id=operation_id,
        operation_fence_id=fence_id,
        source_id=source_id,
        source_digest=_digest(source_id),
        operation_kind=kind,
        predicate_id="predicate",
        owned_source_spans=(_span(span),),
    )
    return OperationIntroductionStreamRecord.model_construct(
        record_kind="operation_introduction",
        primary_key=f"intro-{operation_id}",
        record_digest=_digest(f"intro-{operation_id}"),
        payload=payload,
    )


def _expected(*, key: str, fence: str, source_id: str = "source", kind: str = "claim", span: str = "a") -> ExpectedOperation:
    return ExpectedOperation(
        operation_key=key,
        operation_fence_key=fence,
        source_id=source_id,
        source_digest=_digest(source_id),
        operation_kind=kind,
        predicate_id="predicate",
        owned_source_spans=(canonical_expected_span(_span(span)),),
    )


def _page(
    records: Sequence[GraphObservationStreamRecord], *, start: int, next_cursor: str | None,
    cohort_keys: Sequence[tuple[str, str]], snapshot: str = "snapshot",
) -> GraphObservationPage:
    keys = tuple(
        GraphObservationRecordKey.model_construct(record_kind=kind, primary_key=primary)
        for kind, primary in cohort_keys
    )
    cohort = ResolvedGraphObservationCohort.model_construct(
        changed_record_keys=keys,
        boundary_record_keys=(),
    )
    return GraphObservationPage.model_construct(
        kind="page",
        graph_revision="graph",
        observation_revision="observation",
        snapshot_token=snapshot,
        memory_plane_write_revision=3,
        cohort=cohort,
        page_policy_revision="policy",
        page_policy_digest=_digest("policy"),
        view="current",
        valid_at=None,
        system_as_of=datetime(2026, 9, 13, tzinfo=UTC),
        total_page_size=1,
        stream_start_position=start,
        stream_end_position=start + len(records),
        records=tuple(records),
        observation_schema_fingerprint=_digest("schema"),
        next_cursor=next_cursor,
        page_digest=_digest(f"page-{start}"),
    )


def _request() -> GraphObservationRequest:
    return GraphObservationRequest.model_construct(
        cursor=None,
        scope_constraint=MemoryScope(user_id="user"),
    )


class _Observer:
    def __init__(self, responses: Sequence[GraphObservationPage | GraphObservationFailure]) -> None:
        self._responses = iter(responses)
        self.requests: list[GraphObservationRequest] = []

    def observe_graph(self, *, host_ingress: object, request: GraphObservationRequest) -> GraphObservationPage | GraphObservationFailure:
        self.requests.append(request)
        return next(self._responses)


def test_collects_multipage_public_chain_and_requires_closed_cohort() -> None:
    first = _introduction(operation_id="op-a", fence_id="fence", span="a")
    second = _introduction(operation_id="op-b", fence_id="fence", span="b")
    all_keys = tuple(sorted(((first.record_kind, first.primary_key), (second.record_kind, second.primary_key))))
    observer = _Observer((
        _page((first,), start=0, next_cursor="next", cohort_keys=all_keys),
        _page((second,), start=1, next_cursor=None, cohort_keys=all_keys),
    ))

    collected = collect_graph_observation(
        observer=observer, host_ingress=object(), request=_request(), maximum_pages=2,
    )

    assert collected.records == (first, second)
    assert collected.page_digests == (_digest("page-0"), _digest("page-1"))
    assert observer.requests[0].cursor is None
    assert observer.requests[1].cursor == "next"


@pytest.mark.parametrize("second_start, cohort_keys, message", [
    (2, (("operation_introduction", "intro-op-a"), ("operation_introduction", "intro-op-b")), "not contiguous"),
    (1, (("operation_introduction", "intro-op-a"),), "differs from closed cohort"),
])
def test_collector_rejects_page_chain_and_closed_cohort_failures(
    second_start: int, cohort_keys: Sequence[tuple[str, str]], message: str,
) -> None:
    first = _introduction(operation_id="op-a", fence_id="fence", span="a")
    second = _introduction(operation_id="op-b", fence_id="fence", span="b")
    observer = _Observer((
        _page((first,), start=0, next_cursor="next", cohort_keys=cohort_keys),
        _page((second,), start=second_start, next_cursor=None, cohort_keys=cohort_keys),
    ))

    with pytest.raises(StructuralComparisonError, match=message):
        collect_graph_observation(observer=observer, host_ingress=object(), request=_request(), maximum_pages=2)


def test_collector_propagates_public_failure_between_pages() -> None:
    first = _introduction(operation_id="op-a", fence_id="fence")
    observer = _Observer((
        _page((first,), start=0, next_cursor="next", cohort_keys=((first.record_kind, first.primary_key),)),
        GraphObservationFailure.model_construct(kind="failure", reason="revoked_access", request_correlation_token="token"),
    ))

    with pytest.raises(StructuralComparisonError, match="observation failed:revoked_access"):
        collect_graph_observation(observer=observer, host_ingress=object(), request=_request(), maximum_pages=2)


def test_alignment_is_unique_and_stable_across_observed_order() -> None:
    expected = (_expected(key="logical-a", fence="logical-fence", span="a"), _expected(key="logical-b", fence="logical-fence", span="b"))
    a = _introduction(operation_id="prod-a", fence_id="prod-fence", span="a")
    b = _introduction(operation_id="prod-b", fence_id="prod-fence", span="b")

    forward = align_operations(expected=expected, records=(a, b))
    reverse = align_operations(expected=expected, records=(b, a))

    assert forward == reverse
    assert forward.operation_ids == {"logical-a": "prod-a", "logical-b": "prod-b"}
    assert forward.operation_fence_ids == {"logical-fence": "prod-fence"}


def test_alignment_rejects_no_solution_ambiguous_operations_and_ambiguous_fences() -> None:
    expected = (_expected(key="logical", fence="fence", span="a"),)
    with pytest.raises(StructuralComparisonError, match="no solution"):
        align_operations(expected=expected, records=(_introduction(operation_id="prod", fence_id="fence", span="other"),))

    ambiguous_operations = (
        _expected(key="logical-a", fence="fence", span="a"),
        _expected(key="logical-b", fence="fence", span="a"),
    )
    with pytest.raises(StructuralComparisonError, match="ambiguous"):
        align_operations(
            expected=ambiguous_operations,
            records=(_introduction(operation_id="prod-a", fence_id="prod", span="a"), _introduction(operation_id="prod-b", fence_id="prod", span="a")),
        )

    ambiguous_fences = (
        _expected(key="logical-a", fence="fence-a", span="a"),
        _expected(key="logical-b", fence="fence-b", span="a"),
    )
    with pytest.raises(StructuralComparisonError, match="ambiguous"):
        align_operations(
            expected=ambiguous_fences,
            records=(_introduction(operation_id="prod-a", fence_id="prod-a", span="a"), _introduction(operation_id="prod-b", fence_id="prod-b", span="a")),
        )

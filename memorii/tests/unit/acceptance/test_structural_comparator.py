"""Focused proof for the public structural-comparison acceptance slice."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

import pytest
from acceptance.structural_comparator import (
    ExpectedObservationMembership,
    ExpectedOperation,
    ExpectedOperationTerminalOutcome,
    ExpectedSourceIntroduction,
    ExpectedSourceTerminalOutcome,
    StructuralComparisonError,
    align_operations,
    align_source_introductions,
    align_terminal_outcomes,
    canonical_expected_span,
    collect_graph_observation,
    validate_observation_membership,
)
from memorii.core.memory_evolution.graph_ingestion_observation_records import (
    ObservedOperationIntroduction,
    ObservedOperationTerminalOutcome,
    ObservedSourceIntroduction,
    ObservedSourceTerminalOutcome,
)
from memorii.core.memory_evolution.graph_observation_contracts import (
    GraphObservationFailure,
)
from memorii.core.memory_evolution.graph_observation_public_contracts import (
    GraphObservationPage,
    GraphObservationRequest,
)
from memorii.core.memory_evolution.graph_observation_records import ObservedEntityReference
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
    GraphObservationRecordKey,
    ResolvedGraphObservationCohort,
)
from memorii.core.memory_evolution.graph_observation_streams import (
    GraphObservationStreamRecord,
    OperationIntroductionStreamRecord,
    OperationTerminalOutcomeStreamRecord,
    SourceIntroductionStreamRecord,
    SourceTerminalOutcomeStreamRecord,
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


def _source_introduction(
    *,
    introduction_id: str,
    operation_id: str,
    source_id: str = "source",
    span: str = "a",
    entity_revision_id: str = "entity-revision",
    logical_entity_id: str = "entity",
    type_evidence_ids: tuple[str, ...] = (),
) -> SourceIntroductionStreamRecord:
    payload = ObservedSourceIntroduction.model_construct(
        introduction_id=introduction_id,
        source_id=source_id,
        source_digest=_digest(source_id),
        mention_span=_span(span),
        entity=ObservedEntityReference.model_construct(
            entity_revision_id=entity_revision_id,
            logical_entity_id=logical_entity_id,
            reference_path="source_introduction.entity",
        ),
        independently_asserted_type_evidence_ids=type_evidence_ids,
        operation_id=operation_id,
    )
    return SourceIntroductionStreamRecord.model_construct(
        record_kind="source_introduction",
        primary_key=introduction_id,
        record_digest=_digest(introduction_id),
        payload=payload,
    )


def _expected_source(
    *,
    record_key: str,
    operation_key: str,
    source_id: str = "source",
    span: str = "a",
    entity_key: str = "entity",
    type_evidence_keys: tuple[str, ...] = (),
) -> ExpectedSourceIntroduction:
    return ExpectedSourceIntroduction(
        record_key=record_key,
        source_id=source_id,
        source_digest=_digest(source_id),
        mention_span=canonical_expected_span(_span(span)),
        entity_key=entity_key,
        operation_key=operation_key,
        independently_asserted_type_evidence_keys=type_evidence_keys,
    )


def _operation_terminal(
    *,
    outcome_id: str,
    operation_id: str,
    source_id: str = "source",
    status: Literal["committed", "evidence_only", "rejected", "unresolved", "failed"] = "committed",
    delta: str | None = "delta",
    reason_codes: tuple[str, ...] = ("accepted",),
) -> OperationTerminalOutcomeStreamRecord:
    payload = ObservedOperationTerminalOutcome.model_construct(
        outcome_id=outcome_id,
        operation_id=operation_id,
        source_id=source_id,
        source_digest=_digest(source_id),
        final_status=status,
        graph_revision_delta_digest=delta,
        reason_codes=reason_codes,
    )
    return OperationTerminalOutcomeStreamRecord.model_construct(
        record_kind="operation_terminal_outcome",
        primary_key=outcome_id,
        record_digest=_digest(outcome_id),
        payload=payload,
    )


def _source_terminal(
    *,
    outcome_id: str,
    operation_ids: tuple[str, ...],
    source_id: str = "source",
    status: Literal[
        "fully_committed", "partially_committed", "evidence_only", "rejected", "unresolved", "failed"
    ] = "fully_committed",
) -> SourceTerminalOutcomeStreamRecord:
    payload = ObservedSourceTerminalOutcome.model_construct(
        outcome_id=outcome_id,
        source_id=source_id,
        source_digest=_digest(source_id),
        operation_ids=operation_ids,
        final_status=status,
    )
    return SourceTerminalOutcomeStreamRecord.model_construct(
        record_kind="source_terminal_outcome",
        primary_key=outcome_id,
        record_digest=_digest(outcome_id),
        payload=payload,
    )


def _expected_operation_terminal(
    *,
    record_key: str,
    operation_key: str,
    status: Literal["committed", "evidence_only", "rejected", "unresolved", "failed"] = "committed",
    delta: bool = True,
) -> ExpectedOperationTerminalOutcome:
    return ExpectedOperationTerminalOutcome(
        record_key=record_key,
        operation_key=operation_key,
        source_id="source",
        source_digest=_digest("source"),
        final_status=status,
        graph_effect="exact_committed_delta" if delta else "no_graph_mutation",
        reason_codes=("accepted",),
    )


def _expected_source_terminal(
    *,
    record_key: str,
    operation_keys: tuple[str, ...],
    status: Literal[
        "fully_committed", "partially_committed", "evidence_only", "rejected", "unresolved", "failed"
    ] = "fully_committed",
) -> ExpectedSourceTerminalOutcome:
    return ExpectedSourceTerminalOutcome(
        record_key=record_key,
        source_id="source",
        source_digest=_digest("source"),
        operation_keys=operation_keys,
        final_status=status,
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


def test_source_introduction_aligns_only_through_existing_operation_mapping() -> None:
    operations = align_operations(
        expected=(_expected(key="operation", fence="fence", span="a"),),
        records=(_introduction(operation_id="production-operation", fence_id="production-fence", span="a"),),
    )
    source = _source_introduction(
        introduction_id="source-introduction",
        operation_id="production-operation",
        entity_revision_id="production-revision",
        logical_entity_id="production-entity",
    )

    aligned = align_source_introductions(
        expected=(_expected_source(record_key="source-key", operation_key="operation"),),
        operation_alignment=operations,
        records=(source,),
    )

    assert aligned.source_introduction_ids == {"source-key": "source-introduction"}
    assert aligned.entity_revision_ids == {"entity": "production-revision"}
    assert aligned.logical_entity_ids == {"entity": "production-entity"}


def test_source_introductions_can_repeat_one_entity_with_consistent_production_pair() -> None:
    operations = align_operations(
        expected=(
            _expected(key="operation-a", fence="fence", span="a"),
            _expected(key="operation-b", fence="fence", span="b"),
        ),
        records=(
            _introduction(operation_id="production-a", fence_id="production-fence", span="a"),
            _introduction(operation_id="production-b", fence_id="production-fence", span="b"),
        ),
    )
    aligned = align_source_introductions(
        expected=(
            _expected_source(record_key="source-a", operation_key="operation-a", span="a", entity_key="entity"),
            _expected_source(record_key="source-b", operation_key="operation-b", span="b", entity_key="entity"),
        ),
        operation_alignment=operations,
        records=(
            _source_introduction(
                introduction_id="source-a",
                operation_id="production-a",
                span="a",
                entity_revision_id="production-revision",
                logical_entity_id="production-entity",
            ),
            _source_introduction(
                introduction_id="source-b",
                operation_id="production-b",
                span="b",
                entity_revision_id="production-revision",
                logical_entity_id="production-entity",
            ),
        ),
    )
    assert aligned.entity_revision_ids == {"entity": "production-revision"}
    assert aligned.logical_entity_ids == {"entity": "production-entity"}


def test_source_introductions_reject_inconsistent_production_pair_for_one_entity() -> None:
    operations = align_operations(
        expected=(
            _expected(key="operation-a", fence="fence", span="a"),
            _expected(key="operation-b", fence="fence", span="b"),
        ),
        records=(
            _introduction(operation_id="production-a", fence_id="production-fence", span="a"),
            _introduction(operation_id="production-b", fence_id="production-fence", span="b"),
        ),
    )
    with pytest.raises(StructuralComparisonError, match="entity introduction alignment is inconsistent"):
        align_source_introductions(
            expected=(
                _expected_source(record_key="source-a", operation_key="operation-a", span="a", entity_key="entity"),
                _expected_source(record_key="source-b", operation_key="operation-b", span="b", entity_key="entity"),
            ),
            operation_alignment=operations,
            records=(
                _source_introduction(
                    introduction_id="source-a",
                    operation_id="production-a",
                    span="a",
                    entity_revision_id="revision-a",
                    logical_entity_id="entity-a",
                ),
                _source_introduction(
                    introduction_id="source-b",
                    operation_id="production-b",
                    span="b",
                    entity_revision_id="revision-b",
                    logical_entity_id="entity-b",
                ),
            ),
        )


def test_expected_set_coordinates_require_canonical_order() -> None:
    with pytest.raises(ValueError, match="sorted and unique"):
        _expected_source(record_key="source", operation_key="operation", type_evidence_keys=("b", "a"))
    with pytest.raises(ValueError, match="sorted and unique"):
        ExpectedOperationTerminalOutcome(
            record_key="outcome",
            operation_key="operation",
            source_id="source",
            source_digest=_digest("source"),
            final_status="committed",
            graph_effect="exact_committed_delta",
            reason_codes=("b", "a"),
        )
    with pytest.raises(ValueError, match="sorted and unique"):
        _expected_source_terminal(record_key="source-outcome", operation_keys=("b", "a"))


@pytest.mark.parametrize(
    ("expected_operation", "observed_operation", "message"),
    [
        ("missing", "production-operation", "unmapped operation"),
        ("operation", "other-production-operation", "no solution"),
    ],
)
def test_source_introduction_rejects_absent_and_substituted_operation_mapping(
    expected_operation: str, observed_operation: str, message: str
) -> None:
    operations = align_operations(
        expected=(_expected(key="operation", fence="fence", span="a"),),
        records=(_introduction(operation_id="production-operation", fence_id="production-fence", span="a"),),
    )
    with pytest.raises(StructuralComparisonError, match=message):
        align_source_introductions(
            expected=(_expected_source(record_key="source-key", operation_key=expected_operation),),
            operation_alignment=operations,
            records=(_source_introduction(introduction_id="source", operation_id=observed_operation),),
        )


def test_source_introduction_rejects_ambiguous_matching_and_many_to_one_entity() -> None:
    operations = align_operations(
        expected=(
            _expected(key="operation-a", fence="fence", span="a"),
            _expected(key="operation-b", fence="fence", span="b"),
        ),
        records=(
            _introduction(operation_id="production-a", fence_id="production-fence", span="a"),
            _introduction(operation_id="production-b", fence_id="production-fence", span="b"),
        ),
    )
    expected = (
        _expected_source(record_key="source-a", operation_key="operation-a", span="a", entity_key="entity-a"),
        _expected_source(record_key="source-b", operation_key="operation-b", span="b", entity_key="entity-b"),
    )
    observed = (
        _source_introduction(
            introduction_id="source-a",
            operation_id="production-a",
            span="a",
            entity_revision_id="production-revision",
            logical_entity_id="production-entity",
        ),
        _source_introduction(
            introduction_id="source-b",
            operation_id="production-b",
            span="b",
            entity_revision_id="production-revision",
            logical_entity_id="production-entity",
        ),
    )
    with pytest.raises(StructuralComparisonError, match="many-to-one"):
        align_source_introductions(expected=expected, operation_alignment=operations, records=observed)

    ambiguous_expected = (
        _expected_source(record_key="source-a", operation_key="operation-a", span="a", entity_key="entity-a"),
        _expected_source(record_key="source-b", operation_key="operation-a", span="a", entity_key="entity-b"),
    )
    ambiguous_observed = (
        _source_introduction(introduction_id="source-a", operation_id="production-a", span="a", entity_revision_id="revision-a", logical_entity_id="entity-a"),
        _source_introduction(introduction_id="source-b", operation_id="production-a", span="a", entity_revision_id="revision-b", logical_entity_id="entity-b"),
    )
    with pytest.raises(StructuralComparisonError, match="source introduction alignment is ambiguous"):
        align_source_introductions(
            expected=ambiguous_expected,
            operation_alignment=operations,
            records=ambiguous_observed,
        )


def test_source_introduction_rejects_unverifiable_type_proof() -> None:
    operations = align_operations(
        expected=(_expected(key="operation", fence="fence", span="a"),),
        records=(_introduction(operation_id="production-a", fence_id="production-fence", span="a"),),
    )
    with pytest.raises(StructuralComparisonError, match="unverifiable-type-proof"):
        align_source_introductions(
            expected=(_expected_source(record_key="source", operation_key="operation", type_evidence_keys=("proof",)),),
            operation_alignment=operations,
            records=(_source_introduction(introduction_id="source", operation_id="production-a", type_evidence_ids=("production-proof",)),),
        )


def test_terminal_outcomes_require_exact_operation_and_source_completion() -> None:
    operations = align_operations(
        expected=(_expected(key="operation", fence="fence", span="a"),),
        records=(_introduction(operation_id="production-operation", fence_id="production-fence", span="a"),),
    )
    aligned = align_terminal_outcomes(
        expected_operations=(_expected_operation_terminal(record_key="operation-outcome", operation_key="operation"),),
        expected_sources=(_expected_source_terminal(record_key="source-outcome", operation_keys=("operation",)),),
        operation_alignment=operations,
        records=(
            _operation_terminal(outcome_id="production-operation-outcome", operation_id="production-operation"),
            _source_terminal(outcome_id="production-source-outcome", operation_ids=("production-operation",)),
        ),
    )
    assert aligned.operation_terminal_outcome_ids == {"operation-outcome": "production-operation-outcome"}
    assert aligned.source_terminal_outcome_ids == {"source-outcome": "production-source-outcome"}

    with pytest.raises(StructuralComparisonError, match="operation terminal outcome alignment has no solution"):
        align_terminal_outcomes(
            expected_operations=(
                _expected_operation_terminal(record_key="operation-outcome", operation_key="operation"),
            ),
            expected_sources=(
                _expected_source_terminal(record_key="source-outcome", operation_keys=("operation",)),
            ),
            operation_alignment=operations,
            records=(
                _operation_terminal(
                    outcome_id="production-operation-outcome",
                    operation_id="production-operation",
                    reason_codes=("different-reason",),
                ),
                _source_terminal(
                    outcome_id="production-source-outcome", operation_ids=("production-operation",)),
            ),
        )


@pytest.mark.parametrize(
    "records, message",
    [
        ((), "operation terminal outcome count differs"),
        (
            (_operation_terminal(outcome_id="extra", operation_id="production-operation"),) * 2,
            "operation terminal outcome count differs",
        ),
        (
            (_operation_terminal(outcome_id="outcome", operation_id="production-operation"),),
            "source terminal outcome count differs",
        ),
        (
            (
                _operation_terminal(outcome_id="outcome", operation_id="production-operation"),
                _source_terminal(outcome_id="source-a", operation_ids=("production-operation",)),
                _source_terminal(outcome_id="source-b", operation_ids=("production-operation",)),
            ),
            "source terminal outcome count differs",
        ),
    ],
)
def test_terminal_outcomes_reject_missing_and_extra_records(
    records: Sequence[GraphObservationStreamRecord], message: str
) -> None:
    operations = align_operations(
        expected=(_expected(key="operation", fence="fence", span="a"),),
        records=(_introduction(operation_id="production-operation", fence_id="production-fence", span="a"),),
    )
    with pytest.raises(StructuralComparisonError, match=message):
        align_terminal_outcomes(
            expected_operations=(_expected_operation_terminal(record_key="operation-outcome", operation_key="operation"),),
            expected_sources=(_expected_source_terminal(record_key="source-outcome", operation_keys=("operation",)),),
            operation_alignment=operations,
            records=records,
        )


def test_closed_world_membership_requires_exact_logical_keys_and_counts() -> None:
    introduction = _introduction(operation_id="production-operation", fence_id="production-fence")
    outcome = _operation_terminal(outcome_id="production-outcome", operation_id="production-operation")
    expected = ExpectedObservationMembership(
        expected_record_keys=("operation", "outcome"),
        exact_record_counts_by_kind=(("operation_introduction", 1), ("operation_terminal_outcome", 1)),
    )
    validate_observation_membership(
        expected=expected,
        resolved_record_keys={
            "operation": (introduction.record_kind, introduction.primary_key),
            "outcome": (outcome.record_kind, outcome.primary_key),
        },
        records=(introduction, outcome),
    )

    with pytest.raises(StructuralComparisonError, match="membership differs"):
        validate_observation_membership(
            expected=expected,
            resolved_record_keys={"operation": (introduction.record_kind, introduction.primary_key)},
            records=(introduction, outcome),
        )
    with pytest.raises(StructuralComparisonError, match="per-kind counts differ"):
        validate_observation_membership(
            expected=ExpectedObservationMembership(
                expected_record_keys=("operation", "outcome"),
                exact_record_counts_by_kind=(("operation_introduction", 2),),
            ),
            resolved_record_keys={
                "operation": (introduction.record_kind, introduction.primary_key),
                "outcome": (outcome.record_kind, outcome.primary_key),
            },
            records=(introduction, outcome),
        )

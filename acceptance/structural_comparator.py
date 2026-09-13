"""Independent public-page collection and operation/fence alignment.

This acceptance module consumes only the published observation contracts.  It
does not import production projection, cohort, storage, normalization, or
reconciliation helpers.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.graph_observation_public_contracts import (
    GraphObservationPage,
    GraphObservationRequest,
    GraphObservationResponse,
)
from memorii.core.memory_evolution.graph_observation_streams import (
    GraphObservationStreamRecord,
    OperationIntroductionStreamRecord,
)


class StructuralComparisonError(ValueError):
    """The public page chain or independently expected structure diverged."""


class PublicGraphObservationPort(Protocol):
    def observe_graph(
        self, *, host_ingress: object, request: GraphObservationRequest
    ) -> GraphObservationResponse: ...


class _ClosedExpectedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ExpectedOperation(_ClosedExpectedModel):
    """Pre-ingest operation coordinates that do not contain production IDs."""

    operation_key: str = Field(min_length=1, max_length=1024)
    operation_fence_key: str = Field(min_length=1, max_length=1024)
    source_id: str = Field(min_length=1, max_length=16384)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_kind: str = Field(min_length=1, max_length=16384)
    predicate_id: str | None = Field(default=None, max_length=16384)
    owned_source_spans: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_spans(self) -> ExpectedOperation:
        if not self.owned_source_spans or len(set(self.owned_source_spans)) != len(
            self.owned_source_spans
        ):
            raise ValueError("expected operation spans must be nonempty and unique")
        for span in self.owned_source_spans:
            try:
                value = json.loads(span)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError("expected operation span is not canonical JSON") from exc
            if _canonical_json(value) != span:
                raise ValueError("expected operation span is not canonical JSON")
        return self


@dataclass(frozen=True)
class CollectedGraphObservation:
    first_page: GraphObservationPage
    records: tuple[GraphObservationStreamRecord, ...]
    page_digests: tuple[str, ...]


@dataclass(frozen=True)
class OperationAlignment:
    operation_ids: Mapping[str, str]
    operation_fence_ids: Mapping[str, str]


def canonical_expected_span(value: BaseModel | Mapping[str, object]) -> str:
    """Encode one pre-ingest public span without production helper imports."""
    body = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    return _canonical_json(body)


def collect_graph_observation(
    *,
    observer: PublicGraphObservationPort,
    host_ingress: object,
    request: GraphObservationRequest,
    maximum_pages: int,
    before_continuation: Callable[[int, str], None] | None = None,
) -> CollectedGraphObservation:
    """Collect one exact public snapshot while independently checking continuity."""
    if request.cursor is not None or type(maximum_pages) is not int or maximum_pages < 1:
        raise StructuralComparisonError("invalid initial observation collection request")
    response = observer.observe_graph(host_ingress=host_ingress, request=request)
    if not isinstance(response, GraphObservationPage):
        raise StructuralComparisonError(f"observation failed:{response.reason}")
    first = response
    records: list[GraphObservationStreamRecord] = []
    page_digests: list[str] = []
    expected_start = 0
    page_number = 0
    cursor: str | None = None
    page = first
    invariant = _page_invariant(first)
    while True:
        page_number += 1
        if page_number > maximum_pages:
            raise StructuralComparisonError("observation page limit exceeded")
        if _page_invariant(page) != invariant:
            raise StructuralComparisonError("observation page invariant changed")
        if page.stream_start_position != expected_start:
            raise StructuralComparisonError("observation page chain is not contiguous")
        if page.stream_end_position != expected_start + len(page.records):
            raise StructuralComparisonError("observation page range is invalid")
        records.extend(page.records)
        page_digests.append(page.page_digest)
        expected_start = page.stream_end_position
        cursor = page.next_cursor
        if cursor is None:
            break
        if before_continuation is not None:
            before_continuation(page_number, cursor)
        response = observer.observe_graph(
            host_ingress=host_ingress,
            request=request.model_copy(update={"cursor": cursor}),
        )
        if not isinstance(response, GraphObservationPage):
            raise StructuralComparisonError(f"observation failed:{response.reason}")
        page = response
    keys = tuple((record.record_kind, record.primary_key) for record in records)
    if keys != tuple(sorted(set(keys))):
        raise StructuralComparisonError("observation stream is not globally unique and ordered")
    cohort_keys = {
        (record.record_kind, record.primary_key)
        for record in (*first.cohort.changed_record_keys, *first.cohort.boundary_record_keys)
    }
    if set(keys) != cohort_keys:
        raise StructuralComparisonError("observation stream differs from closed cohort")
    return CollectedGraphObservation(first, tuple(records), tuple(page_digests))


def align_operations(
    *, expected: Sequence[ExpectedOperation], records: Sequence[GraphObservationStreamRecord]
) -> OperationAlignment:
    """Require one unique global fence partition and operation bijection."""
    expected_values = tuple(expected)
    if not expected_values:
        raise StructuralComparisonError("expected operation inventory is empty")
    expected_keys = tuple(item.operation_key for item in expected_values)
    if len(set(expected_keys)) != len(expected_keys):
        raise StructuralComparisonError("expected operation keys are duplicated")
    introductions = tuple(
        item for item in records if isinstance(item, OperationIntroductionStreamRecord)
    )
    if len(introductions) != len(expected_values):
        raise StructuralComparisonError("operation introduction count differs")

    expected_partitions: dict[str, list[ExpectedOperation]] = defaultdict(list)
    observed_partitions: dict[str, list[OperationIntroductionStreamRecord]] = defaultdict(list)
    for item in expected_values:
        expected_partitions[item.operation_fence_key].append(item)
    for item in introductions:
        observed_partitions[item.payload.operation_fence_id].append(item)

    partition_candidates: dict[str, set[str]] = {}
    for fence_key, expected_partition in expected_partitions.items():
        candidates: set[str] = set()
        for fence_id, observed_partition in observed_partitions.items():
            if len(expected_partition) != len(observed_partition):
                continue
            operation_candidates = {
                operation.operation_key: {
                    introduction.payload.operation_id
                    for introduction in observed_partition
                    if _operation_matches(operation, introduction)
                }
                for operation in expected_partition
            }
            matching = _unique_perfect_matching(operation_candidates, allow_ambiguous=True)
            if matching is not None:
                candidates.add(fence_id)
        partition_candidates[fence_key] = candidates

    fence_matching = _unique_perfect_matching(partition_candidates)
    if fence_matching is None:
        raise StructuralComparisonError("operation fence alignment has no solution")
    operation_ids: dict[str, str] = {}
    for fence_key, fence_id in fence_matching.items():
        operation_candidates = {
            operation.operation_key: {
                introduction.payload.operation_id
                for introduction in observed_partitions[fence_id]
                if _operation_matches(operation, introduction)
            }
            for operation in expected_partitions[fence_key]
        }
        matching = _unique_perfect_matching(operation_candidates)
        if matching is None:
            raise StructuralComparisonError("operation alignment has no solution")
        operation_ids.update(matching)
    return OperationAlignment(operation_ids, fence_matching)


def _unique_perfect_matching(
    candidates: Mapping[str, set[str]], *, allow_ambiguous: bool = False
) -> dict[str, str] | None:
    selected = _perfect_matching(candidates)
    if selected is None:
        return None
    if not allow_ambiguous:
        for left, right in selected.items():
            reduced = {key: set(values) for key, values in candidates.items()}
            reduced[left].discard(right)
            if _perfect_matching(reduced) is not None:
                raise StructuralComparisonError("operation alignment is ambiguous")
    return selected


def _perfect_matching(candidates: Mapping[str, set[str]]) -> dict[str, str] | None:
    if not candidates or any(not values for values in candidates.values()):
        return None
    right_to_left: dict[str, str] = {}

    def augment(left: str, seen: set[str]) -> bool:
        for right in sorted(candidates[left]):
            if right in seen:
                continue
            seen.add(right)
            incumbent = right_to_left.get(right)
            if incumbent is None or augment(incumbent, seen):
                right_to_left[right] = left
                return True
        return False

    for left in sorted(candidates):
        if not augment(left, set()):
            return None
    if len(right_to_left) != len(candidates):
        return None
    return {left: right for right, left in right_to_left.items()}


def _operation_matches(
    expected: ExpectedOperation, observed: OperationIntroductionStreamRecord
) -> bool:
    payload = observed.payload
    return (
        payload.source_id == expected.source_id
        and payload.source_digest == expected.source_digest
        and payload.operation_kind == expected.operation_kind
        and payload.predicate_id == expected.predicate_id
        and tuple(canonical_expected_span(span) for span in payload.owned_source_spans)
        == expected.owned_source_spans
    )


def _page_invariant(page: GraphObservationPage) -> tuple[object, ...]:
    return (
        page.graph_revision,
        page.observation_revision,
        page.snapshot_token,
        page.memory_plane_write_revision,
        page.cohort.model_dump_json(),
        page.page_policy_revision,
        page.page_policy_digest,
        page.view,
        page.valid_at,
        page.system_as_of,
        page.total_page_size,
        page.observation_schema_fingerprint,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


__all__ = [
    "CollectedGraphObservation",
    "ExpectedOperation",
    "OperationAlignment",
    "PublicGraphObservationPort",
    "StructuralComparisonError",
    "align_operations",
    "canonical_expected_span",
    "collect_graph_observation",
]

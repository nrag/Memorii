"""Independent public-page collection and operation/fence alignment.

This acceptance module consumes only the published observation contracts.  It
does not import production projection, cohort, storage, normalization, or
reconciliation helpers.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StructuralComparisonError(ValueError):
    """The public page chain or independently expected structure diverged."""


class PublicGraphObservationPort(Protocol):
    def observe_graph(
        self, *, host_ingress: object, request: object
    ) -> object: ...


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


class ExpectedSourceIntroduction(_ClosedExpectedModel):
    """Pre-ingest source/entity coordinates, deliberately without production IDs."""

    record_key: str = Field(min_length=1, max_length=1024)
    source_id: str = Field(min_length=1, max_length=16384)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mention_span: str
    entity_key: str = Field(min_length=1, max_length=1024)
    operation_key: str = Field(min_length=1, max_length=1024)
    independently_asserted_type_evidence_keys: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_coordinates(self) -> ExpectedSourceIntroduction:
        try:
            value = json.loads(self.mention_span)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("expected source mention span is not canonical JSON") from exc
        if _canonical_json(value) != self.mention_span:
            raise ValueError("expected source mention span is not canonical JSON")
        if self.independently_asserted_type_evidence_keys != tuple(
            sorted(set(self.independently_asserted_type_evidence_keys))
        ):
            raise ValueError("expected source type-proof keys must be sorted and unique")
        return self


class ExpectedOperationTerminalOutcome(_ClosedExpectedModel):
    """Pre-ingest terminal disposition for one already declared operation."""

    record_key: str = Field(min_length=1, max_length=1024)
    operation_key: str = Field(min_length=1, max_length=1024)
    source_id: str = Field(min_length=1, max_length=16384)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_status: Literal["committed", "evidence_only", "rejected", "unresolved", "failed"]
    graph_effect: Literal["exact_committed_delta", "no_graph_mutation"]
    reason_codes: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_reason_codes(self) -> ExpectedOperationTerminalOutcome:
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("expected operation terminal reason codes must be sorted and unique")
        return self


class ExpectedSourceTerminalOutcome(_ClosedExpectedModel):
    """Pre-ingest source completion semantics without runtime digest coordinates."""

    record_key: str = Field(min_length=1, max_length=1024)
    source_id: str = Field(min_length=1, max_length=16384)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_keys: tuple[str, ...]
    final_status: Literal[
        "fully_committed",
        "partially_committed",
        "evidence_only",
        "rejected",
        "unresolved",
        "failed",
    ]

    @model_validator(mode="after")
    def _validate_operation_keys(self) -> ExpectedSourceTerminalOutcome:
        if not self.operation_keys or self.operation_keys != tuple(sorted(set(self.operation_keys))):
            raise ValueError("expected source terminal operation keys must be sorted and unique")
        return self


class ExpectedObservationMembership(_ClosedExpectedModel):
    """Closed-world logical membership for one independently declared observation."""

    expected_record_keys: tuple[str, ...]
    exact_record_counts_by_kind: tuple[tuple[str, int], ...]

    @model_validator(mode="after")
    def _validate_membership(self) -> ExpectedObservationMembership:
        if len(set(self.expected_record_keys)) != len(self.expected_record_keys):
            raise ValueError("expected observation record keys are duplicated")
        count_kinds = tuple(kind for kind, _ in self.exact_record_counts_by_kind)
        if len(set(count_kinds)) != len(count_kinds) or any(
            not kind or type(count) is not int or count < 0
            for kind, count in self.exact_record_counts_by_kind
        ):
            raise ValueError("expected observation record counts are invalid")
        if sum(count for _, count in self.exact_record_counts_by_kind) != len(
            self.expected_record_keys
        ):
            raise ValueError("expected observation counts do not close membership")
        return self


@dataclass(frozen=True)
class CollectedGraphObservation:
    first_page: Any
    records: tuple[Any, ...]
    page_digests: tuple[str, ...]


@dataclass(frozen=True)
class OperationAlignment:
    operation_ids: Mapping[str, str]
    operation_fence_ids: Mapping[str, str]


@dataclass(frozen=True)
class SourceEntityAlignment:
    source_introduction_ids: Mapping[str, str]
    entity_revision_ids: Mapping[str, str]
    logical_entity_ids: Mapping[str, str]


@dataclass(frozen=True)
class TerminalOutcomeAlignment:
    operation_terminal_outcome_ids: Mapping[str, str]
    source_terminal_outcome_ids: Mapping[str, str]


def canonical_expected_span(value: BaseModel | Mapping[str, object]) -> str:
    """Encode one pre-ingest public span without production helper imports."""
    body = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    return _canonical_json(body)


def collect_graph_observation(
    *,
    observer: PublicGraphObservationPort,
    host_ingress: object,
    request: Any,
    maximum_pages: int,
    before_continuation: Callable[[int, str], None] | None = None,
) -> CollectedGraphObservation:
    """Collect one exact public snapshot while independently checking continuity."""
    if request.cursor is not None or type(maximum_pages) is not int or maximum_pages < 1:
        raise StructuralComparisonError("invalid initial observation collection request")
    response = observer.observe_graph(host_ingress=host_ingress, request=request)
    if getattr(response, "kind", None) != "page":
        raise StructuralComparisonError(f"observation failed:{response.reason}")
    first = response
    records: list[Any] = []
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
        if getattr(response, "kind", None) != "page":
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
    *, expected: Sequence[ExpectedOperation], records: Sequence[Any]
) -> OperationAlignment:
    """Require one unique global fence partition and operation bijection."""
    expected_values = tuple(expected)
    if not expected_values:
        raise StructuralComparisonError("expected operation inventory is empty")
    expected_keys = tuple(item.operation_key for item in expected_values)
    if len(set(expected_keys)) != len(expected_keys):
        raise StructuralComparisonError("expected operation keys are duplicated")
    introductions = tuple(
        item for item in records if getattr(item, "record_kind", None) == "operation_introduction"
    )
    if len(introductions) != len(expected_values):
        raise StructuralComparisonError("operation introduction count differs")

    expected_partitions: dict[str, list[ExpectedOperation]] = defaultdict(list)
    observed_partitions: dict[str, list[Any]] = defaultdict(list)
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


def align_source_introductions(
    *,
    expected: Sequence[ExpectedSourceIntroduction],
    operation_alignment: OperationAlignment,
    records: Sequence[Any],
) -> SourceEntityAlignment:
    """Align source introductions only through published fields and operation IDs."""
    expected_values = tuple(expected)
    _require_unique_expected_keys(
        (item.record_key for item in expected_values), "expected source introduction keys"
    )
    introductions = tuple(
        item for item in records if getattr(item, "record_kind", None) == "source_introduction"
    )
    if len(introductions) != len(expected_values):
        raise StructuralComparisonError("source introduction count differs")
    for item in expected_values:
        if item.independently_asserted_type_evidence_keys:
            raise StructuralComparisonError("unverifiable-type-proof: expected keys are nonempty")
    if any(item.payload.independently_asserted_type_evidence_ids for item in introductions):
        raise StructuralComparisonError("unverifiable-type-proof: observed IDs are nonempty")

    candidates = {
        item.record_key: {
            introduction.primary_key
            for introduction in introductions
            if _source_introduction_matches(item, introduction, operation_alignment)
        }
        for item in expected_values
    }
    try:
        matching = _unique_perfect_matching(candidates)
    except StructuralComparisonError as exc:
        if str(exc) == "operation alignment is ambiguous":
            raise StructuralComparisonError("source introduction alignment is ambiguous") from exc
        raise
    if matching is None:
        raise StructuralComparisonError("source introduction alignment has no solution")
    by_primary_key = {item.primary_key: item for item in introductions}
    entity_pairs: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for item in expected_values:
        entity = by_primary_key[matching[item.record_key]].payload.entity
        entity_pairs[item.entity_key].add((entity.entity_revision_id, entity.logical_entity_id))
    if any(len(pairs) != 1 for pairs in entity_pairs.values()):
        raise StructuralComparisonError("entity introduction alignment is inconsistent")
    resolved_entity_pairs = {
        entity_key: next(iter(pairs)) for entity_key, pairs in entity_pairs.items()
    }
    if len(set(resolved_entity_pairs.values())) != len(resolved_entity_pairs):
        raise StructuralComparisonError("entity introduction alignment is many-to-one")
    entity_revision_ids = {
        entity_key: pair[0] for entity_key, pair in resolved_entity_pairs.items()
    }
    logical_entity_ids = {
        entity_key: pair[1] for entity_key, pair in resolved_entity_pairs.items()
    }
    return SourceEntityAlignment(matching, entity_revision_ids, logical_entity_ids)


def align_terminal_outcomes(
    *,
    expected_operations: Sequence[ExpectedOperationTerminalOutcome],
    expected_sources: Sequence[ExpectedSourceTerminalOutcome],
    operation_alignment: OperationAlignment,
    records: Sequence[Any],
) -> TerminalOutcomeAlignment:
    """Require exact terminal semantics using only established operation mappings."""
    operation_values = tuple(expected_operations)
    source_values = tuple(expected_sources)
    _require_unique_expected_keys(
        (item.record_key for item in operation_values), "expected operation terminal keys"
    )
    _require_unique_expected_keys(
        (item.operation_key for item in operation_values), "expected terminal operation keys"
    )
    _require_unique_expected_keys(
        (item.record_key for item in source_values), "expected source terminal keys"
    )
    operation_outcomes = tuple(
        item for item in records if getattr(item, "record_kind", None) == "operation_terminal_outcome"
    )
    source_outcomes = tuple(
        item for item in records if getattr(item, "record_kind", None) == "source_terminal_outcome"
    )
    if len(operation_outcomes) != len(operation_values):
        raise StructuralComparisonError("operation terminal outcome count differs")
    if len(source_outcomes) != len(source_values):
        raise StructuralComparisonError("source terminal outcome count differs")

    operation_candidates = {
        item.record_key: {
            outcome.primary_key
            for outcome in operation_outcomes
            if _operation_terminal_matches(item, outcome, operation_alignment)
        }
        for item in operation_values
    }
    operation_matching = _unique_perfect_matching(operation_candidates)
    if operation_matching is None:
        raise StructuralComparisonError("operation terminal outcome alignment has no solution")

    source_candidates = {
        item.record_key: {
            outcome.primary_key
            for outcome in source_outcomes
            if _source_terminal_matches(item, outcome, operation_alignment)
        }
        for item in source_values
    }
    source_matching = _unique_perfect_matching(source_candidates)
    if source_matching is None:
        raise StructuralComparisonError("source terminal outcome alignment has no solution")
    return TerminalOutcomeAlignment(operation_matching, source_matching)


def validate_observation_membership(
    *,
    expected: ExpectedObservationMembership,
    resolved_record_keys: Mapping[str, tuple[str, str]],
    records: Sequence[Any],
) -> None:
    """Prove exact logical membership and counts against the observed cohort."""
    expected_keys = set(expected.expected_record_keys)
    if set(resolved_record_keys) != expected_keys:
        raise StructuralComparisonError("resolved logical record membership differs")
    observed_by_physical_key = {(item.record_kind, item.primary_key): item for item in records}
    if len(observed_by_physical_key) != len(records):
        raise StructuralComparisonError("observed record membership is duplicated")
    resolved_physical_keys = tuple(resolved_record_keys.values())
    if len(set(resolved_physical_keys)) != len(resolved_physical_keys):
        raise StructuralComparisonError("logical record membership is many-to-one")
    if set(resolved_physical_keys) != set(observed_by_physical_key):
        raise StructuralComparisonError("closed-world observation membership differs")
    actual_counts: dict[str, int] = defaultdict(int)
    for kind, primary_key in resolved_physical_keys:
        observed = observed_by_physical_key.get((kind, primary_key))
        if observed is None or observed.record_kind != kind:
            raise StructuralComparisonError("resolved record key does not name its observed kind")
        actual_counts[kind] += 1
    expected_counts = dict(expected.exact_record_counts_by_kind)
    if actual_counts != expected_counts:
        raise StructuralComparisonError("closed-world observation per-kind counts differ")


def _require_unique_expected_keys(values: Iterable[str], label: str) -> None:
    keys = tuple(values)
    if len(set(keys)) != len(keys):
        raise StructuralComparisonError(f"{label} are duplicated")


def _source_introduction_matches(
    expected: ExpectedSourceIntroduction,
    observed: Any,
    operation_alignment: OperationAlignment,
) -> bool:
    operation_id = operation_alignment.operation_ids.get(expected.operation_key)
    if operation_id is None:
        raise StructuralComparisonError("source introduction references an unmapped operation")
    payload = observed.payload
    return (
        payload.source_id == expected.source_id
        and payload.source_digest == expected.source_digest
        and canonical_expected_span(payload.mention_span) == expected.mention_span
        and payload.operation_id == operation_id
    )


def _operation_terminal_matches(
    expected: ExpectedOperationTerminalOutcome,
    observed: Any,
    operation_alignment: OperationAlignment,
) -> bool:
    operation_id = operation_alignment.operation_ids.get(expected.operation_key)
    if operation_id is None:
        raise StructuralComparisonError("operation terminal outcome references an unmapped operation")
    payload = observed.payload
    expected_delta = expected.graph_effect == "exact_committed_delta"
    return (
        payload.operation_id == operation_id
        and payload.source_id == expected.source_id
        and payload.source_digest == expected.source_digest
        and payload.final_status == expected.final_status
        and (payload.graph_revision_delta_digest is not None) == expected_delta
        and frozenset(payload.reason_codes) == frozenset(expected.reason_codes)
    )


def _source_terminal_matches(
    expected: ExpectedSourceTerminalOutcome,
    observed: Any,
    operation_alignment: OperationAlignment,
) -> bool:
    try:
        operation_ids = frozenset(operation_alignment.operation_ids[key] for key in expected.operation_keys)
    except KeyError as exc:
        raise StructuralComparisonError("source terminal outcome references an unmapped operation") from exc
    payload = observed.payload
    return (
        payload.source_id == expected.source_id
        and payload.source_digest == expected.source_digest
        and frozenset(payload.operation_ids) == operation_ids
        and payload.final_status == expected.final_status
    )


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
    expected: ExpectedOperation, observed: Any
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


def _page_invariant(page: Any) -> tuple[object, ...]:
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
    "ExpectedObservationMembership",
    "ExpectedOperation",
    "ExpectedOperationTerminalOutcome",
    "ExpectedSourceIntroduction",
    "ExpectedSourceTerminalOutcome",
    "OperationAlignment",
    "PublicGraphObservationPort",
    "SourceEntityAlignment",
    "StructuralComparisonError",
    "TerminalOutcomeAlignment",
    "align_source_introductions",
    "align_terminal_outcomes",
    "align_operations",
    "canonical_expected_span",
    "collect_graph_observation",
    "validate_observation_membership",
]

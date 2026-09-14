"""Detached, closed-world membership resolution for graph observation cohorts."""

from __future__ import annotations

from dataclasses import dataclass

from memorii.core.memory_evolution.atomic_store import DetachedSemanticObservationAuthority
from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalOperationIntroductionRecord,
    CanonicalOperationTerminalOutcomeRecord,
    GraphRevisionDelta,
    IngestionObservationDelta,
    SourceFinalizationObservationDelta,
)
from memorii.core.memory_evolution.graph_observation_contracts import GraphObservationCohortSelector
from memorii.core.memory_evolution.graph_observation_paging import ObservationCohortUnavailableError
from memorii.core.memory_evolution.graph_observation_public_contracts import AuthenticatedGraphObservationContext
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.observation_ledger_contracts import ObservationLedgerEntry
from memorii.domain.enums import CommitStatus, MemoryDomain


@dataclass(frozen=True)
class ResolvedObservationMembership:
    seed_source_ids: tuple[str, ...]
    seed_operation_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    operation_fence_ids: tuple[str, ...]
    source_finalizations: tuple[SourceFinalizationObservationDelta, ...]
    group_entries: tuple[ObservationLedgerEntry, ...]
    graph_deltas: tuple[GraphRevisionDelta, ...]


def resolve_observation_membership(
    authority: DetachedSemanticObservationAuthority,
    context: AuthenticatedGraphObservationContext,
    authorized_scope: MemoryScope,
    selector: GraphObservationCohortSelector,
) -> ResolvedObservationMembership:
    """Close terminal source/group membership against an already verified prefix."""
    finals: dict[str, list[SourceFinalizationObservationDelta]] = {}
    groups: dict[str, ObservationLedgerEntry] = {}
    transaction_groups: dict[str, list[IngestionObservationDelta]] = {}
    fence_groups: dict[str, list[IngestionObservationDelta]] = {}
    operation_groups: dict[str, list[ObservationLedgerEntry]] = {}
    graph_deltas = {delta.delta_digest: delta for delta in authority.graph_deltas}
    records = {record.memory_id: record for record in authority.records}
    if len(graph_deltas) != len(authority.graph_deltas) or len(records) != len(authority.records):
        raise ObservationCohortUnavailableError("duplicate detached authority identity")
    for entry in authority.observation.entries:
        delta = entry.delta
        if isinstance(delta, SourceFinalizationObservationDelta):
            finals.setdefault(delta.source_id, []).append(delta)
            continue
        if entry.result_digest in groups:
            raise ObservationCohortUnavailableError("duplicate group result digest")
        groups[entry.result_digest] = entry
        transaction_groups.setdefault(delta.transaction_group_id, []).append(delta)
        fence_groups.setdefault(delta.operation_fence_id, []).append(delta)
        introductions = tuple(m.record for m in delta.record_mutations if isinstance(m.record, CanonicalOperationIntroductionRecord))
        outcomes = tuple(m.record for m in delta.record_mutations if isinstance(m.record, CanonicalOperationTerminalOutcomeRecord))
        if (tuple(sorted(r.operation_id for r in introductions)) != delta.operation_ids
                or tuple(sorted(r.operation_id for r in outcomes)) != delta.operation_ids):
            raise ObservationCohortUnavailableError("group lacks exact terminal operation pairs")
        for operation_id in delta.operation_ids:
            operation_groups.setdefault(operation_id, []).append(entry)

    pending_sources = set(selector.seed_source_ids)
    pending_operations = set(selector.seed_operation_ids)
    selected_finals: dict[str, SourceFinalizationObservationDelta] = {}
    selected_groups: dict[str, ObservationLedgerEntry] = {}
    selected_graph: dict[str, GraphRevisionDelta] = {}
    selected_operations: set[str] = set()
    while pending_sources or pending_operations:
        for operation_id in tuple(pending_operations):
            pending_operations.remove(operation_id)
            matches = operation_groups.get(operation_id, ())
            if len(matches) != 1:
                raise ObservationCohortUnavailableError("operation is unknown or ambiguous")
            group = matches[0]
            if not isinstance(group.delta, IngestionObservationDelta):
                raise ObservationCohortUnavailableError("operation does not name a terminal group")
            selected_operations.add(operation_id)
            if group.delta.source_id not in selected_finals:
                pending_sources.add(group.delta.source_id)
        for source_id in tuple(pending_sources):
            pending_sources.remove(source_id)
            if source_id in selected_finals:
                continue
            matches = finals.get(source_id, ())
            source = records.get(source_id)
            if (len(matches) != 1 or source is None or source.source_kind != "semantic_ingestion_source"
                    or source.domain != MemoryDomain.TRANSCRIPT or source.status != CommitStatus.COMMITTED):
                raise ObservationCohortUnavailableError("source is not uniquely retained and terminal")
            final = matches[0]
            scopes = final.required_outcome_scopes
            if scopes.tenant_partition_id != context.tenant_partition_id or any(not authorized_scope.can_read(scope) for scope in scopes.scopes):
                raise ObservationCohortUnavailableError("source scope is unavailable")
            selected_finals[source_id] = final
            pending_operations.update(set(final.operation_ids) - selected_operations)
            for digest in final.source_outcome.group_result_digests:
                group = groups.get(digest)
                if group is None or not isinstance(group.delta, IngestionObservationDelta):
                    raise ObservationCohortUnavailableError("source group result is absent")
                delta = group.delta
                if (delta.source_id != source_id or delta.source_digest != final.source_digest
                        or delta.operation_fence_id != final.operation_fence_id):
                    raise ObservationCohortUnavailableError("source group coordinates differ")
                selected_groups[digest] = group
                pending_operations.update(set(delta.operation_ids) - selected_operations)
                for sibling in (*transaction_groups[delta.transaction_group_id], *fence_groups[delta.operation_fence_id]):
                    if sibling.source_id not in selected_finals:
                        pending_sources.add(sibling.source_id)
                    pending_operations.update(set(sibling.operation_ids) - selected_operations)
                if delta.terminal_status != "committed":
                    if delta.graph_revision_delta_digest is not None:
                        raise ObservationCohortUnavailableError("noncommitting group has graph effects")
                    continue
                graph = graph_deltas.get(delta.graph_revision_delta_digest or "")
                if (graph is None or graph.transaction_group_id != delta.transaction_group_id
                        or not set(delta.operation_ids).issubset(graph.operation_ids)
                        or source_id not in graph.source_ids):
                    raise ObservationCohortUnavailableError("committed group graph closure is absent")
                selected_graph[graph.delta_digest] = graph
                pending_sources.update(set(graph.source_ids) - selected_finals.keys())
                pending_operations.update(set(graph.operation_ids) - selected_operations)
    if any(operation_groups[operation_id][0].result_digest not in selected_groups for operation_id in selected_operations):
        raise ObservationCohortUnavailableError("source finalization omits a selected operation group")
    return ResolvedObservationMembership(
        seed_source_ids=selector.seed_source_ids, seed_operation_ids=selector.seed_operation_ids,
        source_ids=tuple(sorted(selected_finals)), operation_ids=tuple(sorted(selected_operations)),
        operation_fence_ids=tuple(sorted({f.operation_fence_id for f in selected_finals.values()})),
        source_finalizations=tuple(selected_finals[key] for key in sorted(selected_finals)),
        group_entries=tuple(sorted(selected_groups.values(), key=lambda entry: entry.sequence)),
        graph_deltas=tuple(sorted(selected_graph.values(), key=lambda delta: delta.graph_revision_delta_id)),
    )

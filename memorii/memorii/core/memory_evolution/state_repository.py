"""Typed reads of persisted memory-evolution state."""

from __future__ import annotations

from memorii.core.memory_evolution.models import (
    ClaimState,
    ContradictionSet,
    EntityLinkState,
    ExtractedAction,
    SourceObservation,
)
from memorii.core.memory_evolution.record_projection import source_observation_from_record
from memorii.core.memory_evolution.temporal_contracts import TemporalAnchor, TemporalAnchorCatalog
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.domain.enums import MemoryDomain


class EvolutionStateRepository:
    """Decode typed evolution state from the canonical memory plane."""

    _memory_plane: MemoryPlaneService | None
    _snapshot_records: tuple[CanonicalMemoryRecord, ...] | None

    def __init__(self, *, memory_plane: MemoryPlaneService) -> None:
        self._memory_plane = memory_plane
        self._snapshot_records: tuple[CanonicalMemoryRecord, ...] | None = None

    @classmethod
    def from_snapshot(cls, records: tuple[CanonicalMemoryRecord, ...]) -> EvolutionStateRepository:
        """Decode only the supplied detached canonical clone; never a live store."""

        repository = cls.__new__(cls)
        repository._memory_plane = None
        repository._snapshot_records = tuple(record.model_copy(deep=True) for record in records)
        return repository

    def _records(self, domains: list[MemoryDomain]) -> list[CanonicalMemoryRecord]:
        if self._snapshot_records is not None:
            return [record for record in self._snapshot_records if record.domain in domains]
        if self._memory_plane is None:
            raise RuntimeError("snapshot repository has no live memory-plane fallback")
        return self._memory_plane.list_records(domains=domains)

    def list_claim_states(self) -> list[ClaimState]:
        return [
            ClaimState.model_validate(record.content["claim_state"])
            for record in self._records([MemoryDomain.SEMANTIC, MemoryDomain.USER, MemoryDomain.EXECUTION])
            if record.content.get("memory_evolution_kind") == "claim_state"
        ]

    def list_entity_links(self) -> list[EntityLinkState]:
        return [
            EntityLinkState.model_validate(record.content["entity_link"])
            for record in self._records([MemoryDomain.SEMANTIC])
            if record.content.get("memory_evolution_kind") == "entity_link"
        ]

    def list_contradiction_sets(self) -> list[ContradictionSet]:
        return [
            ContradictionSet.model_validate(record.content["contradiction_set"])
            for record in self._records([MemoryDomain.SEMANTIC])
            if record.content.get("memory_evolution_kind") == "contradiction_set"
        ]

    def list_actions(self) -> list[ExtractedAction]:
        return [
            ExtractedAction.model_validate(record.content["action"])
            for record in self._records([MemoryDomain.EXECUTION])
            if record.content.get("memory_evolution_kind") == "action"
        ]

    def list_source_observations(self) -> list[SourceObservation]:
        return [
            source_observation_from_record(record)
            for record in self._records([MemoryDomain.TRANSCRIPT])
            if record.is_raw_event
        ]

    def hydrate_temporal_anchors(self, catalog: TemporalAnchorCatalog) -> None:
        for record in self._records([MemoryDomain.SEMANTIC]):
            if record.content.get("memory_evolution_kind") == "temporal_anchor":
                catalog.register(TemporalAnchor.model_validate(record.content["temporal_anchor"]))

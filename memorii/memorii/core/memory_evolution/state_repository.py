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
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.domain.enums import MemoryDomain


class EvolutionStateRepository:
    """Decode typed evolution state from the canonical memory plane."""

    def __init__(self, *, memory_plane: MemoryPlaneService) -> None:
        self._memory_plane = memory_plane

    def list_claim_states(self) -> list[ClaimState]:
        return [
            ClaimState.model_validate(record.content["claim_state"])
            for record in self._memory_plane.list_records(
                domains=[MemoryDomain.SEMANTIC, MemoryDomain.USER, MemoryDomain.EXECUTION]
            )
            if record.content.get("memory_evolution_kind") == "claim_state"
        ]

    def list_entity_links(self) -> list[EntityLinkState]:
        return [
            EntityLinkState.model_validate(record.content["entity_link"])
            for record in self._memory_plane.list_records(domains=[MemoryDomain.SEMANTIC])
            if record.content.get("memory_evolution_kind") == "entity_link"
        ]

    def list_contradiction_sets(self) -> list[ContradictionSet]:
        return [
            ContradictionSet.model_validate(record.content["contradiction_set"])
            for record in self._memory_plane.list_records(domains=[MemoryDomain.SEMANTIC])
            if record.content.get("memory_evolution_kind") == "contradiction_set"
        ]

    def list_actions(self) -> list[ExtractedAction]:
        return [
            ExtractedAction.model_validate(record.content["action"])
            for record in self._memory_plane.list_records(domains=[MemoryDomain.EXECUTION])
            if record.content.get("memory_evolution_kind") == "action"
        ]

    def list_source_observations(self) -> list[SourceObservation]:
        return [
            source_observation_from_record(record)
            for record in self._memory_plane.list_records(domains=[MemoryDomain.TRANSCRIPT])
            if record.is_raw_event
        ]

    def hydrate_temporal_anchors(self, catalog: TemporalAnchorCatalog) -> None:
        for record in self._memory_plane.list_records(domains=[MemoryDomain.SEMANTIC]):
            if record.content.get("memory_evolution_kind") == "temporal_anchor":
                catalog.register(TemporalAnchor.model_validate(record.content["temporal_anchor"]))

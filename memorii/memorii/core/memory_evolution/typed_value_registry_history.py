"""Immutable protected history for verified profile-3 registry publications.

This owner is intentionally a construction object.  A future composition owner
must supply activation authority before it can select an active writer and must
atomically replace its held history pointer after successful construction.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    CanonicalTypedValueProfileBinding,
    NativeObservationDecoder,
    native_observation_decoder_table,
)
from memorii.core.memory_evolution.typed_value_publication import (
    VerifiedTypedValuePublication,
)
from memorii.core.memory_evolution.typed_value_registry_compilation import (
    CompiledRegistryEntry,
)


class TypedValueRegistryHistoryError(ValueError):
    """A publication cannot be retained as immutable registry history."""


class TypedValueRegistryReadRoute(StrEnum):
    """The closed body-read routes permitted by the profile-3 contract."""

    PUBLIC = "public"
    INTERNAL_REPLAY = "internal_replay"
    RETAINED_VERIFICATION = "retained_verification"


@dataclass(frozen=True)
class ResolvedTypedValueRegistryHistoryEntry:
    """The original publication, entry, and static decoder selected by a binding."""

    publication: VerifiedTypedValuePublication
    entry: CompiledRegistryEntry
    decoder: NativeObservationDecoder


_Coordinate = tuple[str, str, str, str]
_Binding = tuple[str, int, str, str, int, str]
_READ_STATUSES = frozenset(("active", "replay_only", "retired"))
_DECODER_ID_PREFIX = "memorii.semantic_ingestion.observation."


@dataclass(frozen=True)
class ProtectedTypedValueRegistryHistory:
    """Append-only verified publications with exact coordinate and binding lookup.

    The history exposes no writer-selection operation.  Activation epoch and
    writer authority are intentionally absent until their owning lifecycle
    composition can provide and verify both.
    """

    publications: tuple[VerifiedTypedValuePublication, ...]
    _by_coordinate: Mapping[_Coordinate, ResolvedTypedValueRegistryHistoryEntry] = field(
        init=False, repr=False, compare=False
    )
    _by_binding: Mapping[_Binding, ResolvedTypedValueRegistryHistoryEntry] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.publications) is not tuple or not self.publications:
            raise TypedValueRegistryHistoryError("typed_value_registry_history_publications_required")
        coordinate_index, binding_index = _index_publications(self.publications)
        object.__setattr__(self, "_by_coordinate", MappingProxyType(coordinate_index))
        object.__setattr__(self, "_by_binding", MappingProxyType(binding_index))

    def append(self, publication: VerifiedTypedValuePublication) -> ProtectedTypedValueRegistryHistory:
        """Return a new history after a strictly append-only publication addition.

        Re-adding the exact full publication is idempotent.  A new publication
        must introduce at least one new immutable coordinate; changing any
        previously retained coordinate is rejected before a replacement can be
        selected.
        """
        if type(publication) is not VerifiedTypedValuePublication:
            raise TypedValueRegistryHistoryError("typed_value_registry_history_publication_invalid")
        for retained in self.publications:
            if retained.publication_manifest.publication_digest == publication.publication_manifest.publication_digest:
                if retained == publication:
                    return self
                raise TypedValueRegistryHistoryError("typed_value_registry_history_publication_identity_conflict")

        candidate_coordinates, _ = _index_publications((publication,))
        new_coordinates = 0
        for coordinate, candidate in candidate_coordinates.items():
            retained = self._by_coordinate.get(coordinate)
            if retained is None:
                new_coordinates += 1
            elif retained.entry != candidate.entry:
                raise TypedValueRegistryHistoryError("typed_value_registry_history_coordinate_immutable")
        if new_coordinates == 0:
            raise TypedValueRegistryHistoryError("typed_value_registry_history_publication_has_no_new_entries")
        return ProtectedTypedValueRegistryHistory(self.publications + (publication,))

    def resolve(
        self,
        binding: CanonicalTypedValueProfileBinding,
        *,
        route: TypedValueRegistryReadRoute,
    ) -> ResolvedTypedValueRegistryHistoryEntry:
        """Resolve one complete embedded binding under its declared read permission."""
        if type(binding) is not CanonicalTypedValueProfileBinding:
            raise TypedValueRegistryHistoryError("typed_value_registry_history_binding_invalid")
        if type(route) is not TypedValueRegistryReadRoute:
            raise TypedValueRegistryHistoryError("typed_value_registry_history_read_route_invalid")
        try:
            binding.validate()
        except CanonicalTypedValueError as exc:
            raise TypedValueRegistryHistoryError("typed_value_registry_history_binding_invalid") from exc
        selected = self._by_binding.get(_binding_key(binding))
        if selected is None:
            raise TypedValueRegistryHistoryError("typed_value_registry_history_binding_not_found")
        if _coordinate_for_binding(binding) != _coordinate_for_entry(selected.entry):
            raise TypedValueRegistryHistoryError("typed_value_registry_history_binding_coordinate_mismatch")
        if not _route_permitted(selected.entry.read_status, route):
            raise TypedValueRegistryHistoryError("typed_value_registry_history_read_status_forbidden")
        return selected


def _index_publications(
    publications: tuple[VerifiedTypedValuePublication, ...],
) -> tuple[dict[_Coordinate, ResolvedTypedValueRegistryHistoryEntry], dict[_Binding, ResolvedTypedValueRegistryHistoryEntry]]:
    static_decoders = native_observation_decoder_table()
    by_coordinate: dict[_Coordinate, ResolvedTypedValueRegistryHistoryEntry] = {}
    by_binding: dict[_Binding, ResolvedTypedValueRegistryHistoryEntry] = {}
    publication_digests: set[str] = set()
    for publication in publications:
        _verify_publication_identity(publication)
        publication_digest = publication.publication_manifest.publication_digest
        if publication_digest in publication_digests:
            raise TypedValueRegistryHistoryError("typed_value_registry_history_publication_duplicate")
        publication_digests.add(publication_digest)
        coordinates_in_publication: set[_Coordinate] = set()
        for entry in publication.compiled_registry.entries:
            _verify_entry_publication_join(entry, publication, static_decoders)
            coordinate = _coordinate_for_entry(entry)
            binding = _binding_for_entry(entry)
            if coordinate in coordinates_in_publication:
                raise TypedValueRegistryHistoryError("typed_value_registry_history_publication_coordinate_duplicate")
            coordinates_in_publication.add(coordinate)
            retained_coordinate = by_coordinate.get(coordinate)
            retained_binding = by_binding.get(binding)
            if retained_coordinate is not None:
                if retained_coordinate.entry != entry:
                    raise TypedValueRegistryHistoryError("typed_value_registry_history_coordinate_immutable")
                if retained_binding is not retained_coordinate:
                    raise TypedValueRegistryHistoryError("typed_value_registry_history_binding_duplicate")
                continue
            if retained_binding is not None:
                raise TypedValueRegistryHistoryError("typed_value_registry_history_binding_duplicate")
            resolved = ResolvedTypedValueRegistryHistoryEntry(publication, entry, static_decoders[entry.decoder_id])
            by_coordinate[coordinate] = resolved
            by_binding[binding] = resolved
    return by_coordinate, by_binding


def _verify_publication_identity(publication: VerifiedTypedValuePublication) -> None:
    if type(publication) is not VerifiedTypedValuePublication:
        raise TypedValueRegistryHistoryError("typed_value_registry_history_publication_invalid")
    registry = publication.compiled_registry
    manifest = publication.publication_manifest
    pins = publication.pins
    sources = publication.verified_decoder_sources
    if (
        registry.registry_digest != manifest.registry_digest
        or registry.registry_digest != pins.registry_digest
        or manifest.publication_digest != pins.publication_digest
        or registry.profile.profile_id != manifest.profile_id
        or registry.profile.profile_version != manifest.profile_version
        or registry.profile.profile_id != sources.manifest.profile_id
        or registry.profile.profile_version != sources.manifest.profile_version
        or publication.independent_vector_manifest_digest != pins.independent_vector_manifest_digest
    ):
        raise TypedValueRegistryHistoryError("typed_value_registry_history_publication_registry_identity_mismatch")
    published_snapshots = tuple(
        (item.decoder_id, item.source_snapshot_digest)
        for item in manifest.decoder_source_snapshots
    )
    verified_snapshots = tuple(
        (item.decoder_id, item.source_snapshot_digest)
        for item in sources.snapshots
    )
    pinned_snapshots = tuple(
        (item.decoder_id, item.source_snapshot_digest)
        for item in pins.decoder_source_snapshots
    )
    if published_snapshots != verified_snapshots or published_snapshots != pinned_snapshots:
        raise TypedValueRegistryHistoryError("typed_value_registry_history_publication_snapshot_identity_mismatch")


def _verify_entry_publication_join(
    entry: CompiledRegistryEntry,
    publication: VerifiedTypedValuePublication,
    static_decoders: Mapping[str, NativeObservationDecoder],
) -> None:
    if entry.read_status not in _READ_STATUSES:
        raise TypedValueRegistryHistoryError("typed_value_registry_history_entry_status_invalid")
    if entry.profile != publication.compiled_registry.profile:
        raise TypedValueRegistryHistoryError("typed_value_registry_history_entry_profile_mismatch")
    expected_decoder_id = f"{_DECODER_ID_PREFIX}{entry.schema_id}.v{entry.schema_version}"
    if entry.decoder_id != expected_decoder_id:
        raise TypedValueRegistryHistoryError("typed_value_registry_history_decoder_coordinate_mismatch")
    if entry.decoder_id not in static_decoders:
        raise TypedValueRegistryHistoryError("typed_value_registry_history_decoder_not_static")
    snapshots = {
        item.decoder_id: item.source_snapshot_digest
        for item in publication.verified_decoder_sources.snapshots
    }
    if snapshots.get(entry.decoder_id) != entry.implementation_source_digest:
        raise TypedValueRegistryHistoryError("typed_value_registry_history_decoder_source_mismatch")
    if publication.verified_decoder_sources.manifest.manifest_digest != publication.publication_manifest.decoder_source_manifest_digest:
        raise TypedValueRegistryHistoryError("typed_value_registry_history_decoder_manifest_mismatch")


def _coordinate_for_entry(entry: CompiledRegistryEntry) -> _Coordinate:
    return (entry.profile.profile_id, entry.profile.profile_version, entry.schema_id, entry.schema_version)


def _coordinate_for_binding(binding: CanonicalTypedValueProfileBinding) -> _Coordinate:
    return (binding.profile_id, str(binding.profile_version), binding.schema_id, str(binding.schema_version))


def _binding_for_entry(entry: CompiledRegistryEntry) -> _Binding:
    return (
        entry.profile.profile_id,
        int(entry.profile.profile_version),
        entry.profile.profile_digest,
        entry.schema_id,
        int(entry.schema_version),
        entry.binding_digest,
    )


def _binding_key(binding: CanonicalTypedValueProfileBinding) -> _Binding:
    return (
        binding.profile_id,
        binding.profile_version,
        binding.profile_digest,
        binding.schema_id,
        binding.schema_version,
        binding.binding_digest,
    )


def _route_permitted(status: str, route: TypedValueRegistryReadRoute) -> bool:
    if status == "active":
        return True
    if status == "replay_only":
        return route in (TypedValueRegistryReadRoute.INTERNAL_REPLAY, TypedValueRegistryReadRoute.RETAINED_VERIFICATION)
    return status == "retired" and route is TypedValueRegistryReadRoute.RETAINED_VERIFICATION

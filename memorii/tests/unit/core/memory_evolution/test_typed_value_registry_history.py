from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest
from memorii.core.memory_evolution.ingestion_contracts import CanonicalTypedValueProfileBinding
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifest,
    DecoderSourceSnapshot,
    VerifiedDecoderSourceManifest,
)
from memorii.core.memory_evolution.typed_value_publication import (
    DecoderSourceSnapshotPin,
    ProtectedTypedValuePublicationPins,
    PublicationDecoderSourceSnapshot,
    TypedValuePublicationManifest,
    VerifiedTypedValuePublication,
)
from memorii.core.memory_evolution.typed_value_registry_compilation import (
    CompiledPolicyDigests,
    CompiledProfile,
    CompiledRegistryEntry,
    CompiledTypedValueRegistry,
)
from memorii.core.memory_evolution.typed_value_registry_history import (
    ProtectedTypedValueRegistryHistory,
    TypedValueRegistryHistoryError,
    TypedValueRegistryReadRoute,
)

_DECODER_ID = "memorii.semantic_ingestion.observation.MemoryScope.v1"
_TYPED_LITERAL_DECODER_ID = "memorii.semantic_ingestion.observation.TypedLiteral.v1"
_PROFILE = CompiledProfile("semantic_ingestion_typed_value", "3", "operational-3", "a" * 64, "b" * 64)
_POLICIES = ("c" * 64, "d" * 64, "e" * 64, "f" * 64)


def _entry(
    *,
    schema_id: str = "MemoryScope",
    status: str = "active",
    source_digest: str = "1" * 64,
    decoder_id: str | None = None,
    binding: str = "2" * 64,
) -> CompiledRegistryEntry:
    resolved_decoder_id = decoder_id or f"memorii.semantic_ingestion.observation.{schema_id}.v1"
    return CompiledRegistryEntry(
        _PROFILE,
        schema_id,
        "1",
        "3" * 64,
        CompiledPolicyDigests(*_POLICIES),
        binding,
        resolved_decoder_id,
        source_digest,
        "4" * 64,
        "5" * 64,
        status,
    )


def _publication(*entries: CompiledRegistryEntry, publication_digest: str = "6" * 64) -> VerifiedTypedValuePublication:
    registry = CompiledTypedValueRegistry(_PROFILE, entries, "7" * 64, ())
    snapshots = tuple(
        DecoderSourceSnapshot(entry.decoder_id, entry.implementation_source_digest, ())
        for index, entry in enumerate(entries)
        if all(prior.decoder_id != entry.decoder_id for prior in entries[:index])
    )
    published = tuple(PublicationDecoderSourceSnapshot(item.decoder_id, item.source_snapshot_digest) for item in snapshots)
    pins = tuple(DecoderSourceSnapshotPin(item.decoder_id, item.source_snapshot_digest) for item in snapshots)
    return VerifiedTypedValuePublication(
        registry,
        VerifiedDecoderSourceManifest(DecoderSourceManifest(b"{}", "8" * 64, _PROFILE.profile_id, _PROFILE.profile_version, ()), (), snapshots),
        TypedValuePublicationManifest(b"{}", publication_digest, _PROFILE.profile_id, _PROFILE.profile_version, (), "8" * 64, published, registry.registry_digest),
        ProtectedTypedValuePublicationPins(publication_digest, registry.registry_digest, pins, "a" * 64),
        "a" * 64,
    )


def _binding(entry: CompiledRegistryEntry) -> CanonicalTypedValueProfileBinding:
    return CanonicalTypedValueProfileBinding(
        entry.profile.profile_id,
        int(entry.profile.profile_version),
        entry.profile.profile_digest,
        entry.schema_id,
        int(entry.schema_version),
        entry.binding_digest,
    )


def test_resolves_original_entry_publication_and_static_memory_scope_decoder_after_append() -> None:
    original = _entry()
    later = _entry(schema_id="TypedLiteral", decoder_id=_TYPED_LITERAL_DECODER_ID, binding="b" * 64)
    history = ProtectedTypedValueRegistryHistory((_publication(original),)).append(
        _publication(original, later, publication_digest="c" * 64)
    )

    resolved = history.resolve(_binding(original), route=TypedValueRegistryReadRoute.PUBLIC)

    assert resolved.entry is original
    assert resolved.publication.publication_manifest.publication_digest == "6" * 64
    assert resolved.decoder is not None
    assert resolved.decoder({"session_id": None, "task_id": None, "user_id": None}) == MemoryScope()


@pytest.mark.parametrize(
    ("changed", "failure"),
    (
        (lambda entry: replace(entry, read_status="replay_only"), "coordinate_immutable"),
        (lambda entry: replace(entry, implementation_source_digest="a" * 64), "coordinate_immutable"),
        (lambda entry: replace(entry, decoder_id="memorii.semantic_ingestion.observation.TypedLiteral.v1"), "decoder_coordinate_mismatch"),
        (lambda entry: replace(entry, schema_fingerprint="a" * 64), "coordinate_immutable"),
        (lambda entry: replace(entry, binding_digest="a" * 64), "coordinate_immutable"),
    ),
    ids=("status", "source", "decoder", "closure", "binding"),
)
def test_rejects_changed_retained_coordinate(changed: Callable[[CompiledRegistryEntry], CompiledRegistryEntry], failure: str) -> None:
    original = _entry()
    history = ProtectedTypedValueRegistryHistory((_publication(original),))
    candidate = changed(original)

    with pytest.raises(TypedValueRegistryHistoryError, match=failure):
        history.append(_publication(candidate, publication_digest="c" * 64))


def test_enforces_status_routes_and_exact_full_publication_idempotence() -> None:
    replay = _entry(status="replay_only")
    retired = _entry(schema_id="TypedLiteral", status="retired", decoder_id=_TYPED_LITERAL_DECODER_ID, binding="b" * 64)
    publication = _publication(replay, retired)
    history = ProtectedTypedValueRegistryHistory((publication,))

    assert history.append(publication) is history
    assert history.resolve(_binding(replay), route=TypedValueRegistryReadRoute.INTERNAL_REPLAY).entry is replay
    assert history.resolve(_binding(replay), route=TypedValueRegistryReadRoute.RETAINED_VERIFICATION).entry is replay
    assert history.resolve(_binding(retired), route=TypedValueRegistryReadRoute.RETAINED_VERIFICATION).entry is retired
    with pytest.raises(TypedValueRegistryHistoryError, match="read_status_forbidden"):
        history.resolve(_binding(replay), route=TypedValueRegistryReadRoute.PUBLIC)
    with pytest.raises(TypedValueRegistryHistoryError, match="read_status_forbidden"):
        history.resolve(_binding(retired), route=TypedValueRegistryReadRoute.INTERNAL_REPLAY)


def test_rejects_unknown_status_duplicate_coordinate_and_publication_identity_conflict() -> None:
    original = _entry()
    with pytest.raises(TypedValueRegistryHistoryError, match="entry_status_invalid"):
        ProtectedTypedValueRegistryHistory((_publication(replace(original, read_status="unknown")),))
    with pytest.raises(TypedValueRegistryHistoryError, match="publication_coordinate_duplicate"):
        ProtectedTypedValueRegistryHistory((_publication(original, original),))

    history = ProtectedTypedValueRegistryHistory((_publication(original),))
    conflicting = replace(history.publications[0], independent_vector_manifest_digest="b" * 64)
    assert conflicting != history.publications[0]
    with pytest.raises(TypedValueRegistryHistoryError, match="publication_identity_conflict"):
        history.append(conflicting)


def test_rejects_mismatched_registry_publication_identity() -> None:
    publication = _publication(_entry())
    mismatched = replace(
        publication,
        publication_manifest=replace(publication.publication_manifest, registry_digest="b" * 64),
    )

    with pytest.raises(TypedValueRegistryHistoryError, match="publication_registry_identity_mismatch"):
        ProtectedTypedValueRegistryHistory((mismatched,))


def test_rejects_mismatched_decoder_source_manifest_identity() -> None:
    publication = _publication(_entry())
    mismatched = replace(
        publication,
        publication_manifest=replace(publication.publication_manifest, decoder_source_manifest_digest="b" * 64),
    )

    with pytest.raises(TypedValueRegistryHistoryError, match="decoder_manifest_mismatch"):
        ProtectedTypedValueRegistryHistory((mismatched,))

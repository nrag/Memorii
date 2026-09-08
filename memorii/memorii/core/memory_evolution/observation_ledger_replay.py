"""Verify a complete observation prefix against independently loaded authority.

The atomic store supplies artifacts and immutable result verification from one
detached snapshot. This owner never reads live state or reconstructs provenance.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalIngestionObservationRecord,
    CanonicalOperationIntroductionRecord,
    CanonicalOperationTerminalOutcomeRecord,
    CanonicalSourceIntroductionRecord,
    IngestionObservationDelta,
)
from memorii.core.memory_evolution.observation_activation_runtime import (
    RegisteredObservationArtifact,
    emit_registered_observation_artifact,
    observation_successor_revision,
    registered_genesis_head_artifact,
    registered_semantic_payload,
    semantic_payload_digest,
    validate_registered_artifact,
)
from memorii.core.memory_evolution.observation_ledger_contracts import (
    ObservationLedgerActivation,
    ObservationLedgerEntry,
    ObservationLedgerHead,
)
from memorii.core.memory_evolution.observation_replay_contracts import ObservationReplayState
from memorii.core.memory_evolution.typed_value_artifact_reader import ProtectedTypedValueArtifactReaderLimits
from memorii.core.memory_evolution.typed_value_publication import VerifiedTypedValuePublication
from memorii.core.memory_evolution.typed_value_registry_history import ProtectedTypedValueRegistryHistory


class ObservationLedgerReplayError(ValueError):
    """The retained audit does not prove the independently expected head."""


def replay_observation_ledger(
    *,
    repository_id: str,
    activation_digest: str,
    activation_artifact: bytes,
    expected_head_artifact: bytes,
    entry_artifacts: tuple[bytes, ...],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
    verify_immutable_result: Callable[[ObservationLedgerEntry], None],
) -> RegisteredObservationArtifact:
    """Return registered replay state only after every exact result join passes.

    ``verify_immutable_result`` belongs to the canonical atomic-store owner. It
    must resolve the locator and all graph/member links solely from the same
    snapshot as these artifacts, rejecting missing or substituted members.
    """
    # Bound the whole retained prefix before decoding entries, not only each
    # individually valid artifact. Final state emission applies the body budget
    # again to the complete materialization, including duplicated audit records.
    if (
        len(entry_artifacts) > limits.body_limits.maximum_nodes
        or sum(len(raw) for raw in entry_artifacts) > limits.maximum_envelope_bytes
    ):
        raise ObservationLedgerReplayError("observation replay prefix exceeds protected limits")
    activation = _selected_value(
        activation_artifact, "ObservationLedgerActivation", history, publication, limits,
    )
    expected_head = _selected_value(
        expected_head_artifact, "ObservationLedgerHead", history, publication, limits,
    )
    if not isinstance(activation, ObservationLedgerActivation) or not isinstance(expected_head, ObservationLedgerHead):
        raise ObservationLedgerReplayError("observation authority type is invalid")
    if (
        activation.repository_id != repository_id
        or activation.activation_digest != activation_digest
        or expected_head.repository_id != repository_id
        or expected_head.activation_digest != activation_digest
        or len(entry_artifacts) != expected_head.sequence
    ):
        raise ObservationLedgerReplayError("observation replay authority or prefix length is invalid")

    head, _ = registered_genesis_head_artifact(activation, history=history, publication=publication, limits=limits)
    entries: list[ObservationLedgerEntry] = []
    records: dict[tuple[str, str], CanonicalIngestionObservationRecord] = {}
    delta_ids: set[str] = set()
    operation_keys: set[tuple[str, str]] = set()
    finalized_sources: set[str] = set()
    source_groups: dict[str, list[ObservationLedgerEntry]] = {}
    for raw in entry_artifacts:
        entry = _selected_value(raw, "ObservationLedgerEntry", history, publication, limits)
        if not isinstance(entry, ObservationLedgerEntry):
            raise ObservationLedgerReplayError("observation entry type is invalid")
        delta = entry.delta
        if (
            entry.repository_id != repository_id
            or entry.activation_digest != activation_digest
            or entry.sequence != head.sequence + 1
            or entry.previous_entry_digest != head.last_entry_digest
            or delta.observation_revision_before != head.observation_revision
            or delta.observation_delta_id in delta_ids
            or delta.operation_fence_id in finalized_sources
            or delta.observation_schema_fingerprint != activation.observation_schema_fingerprint
        ):
            raise ObservationLedgerReplayError("observation entry chain is invalid")
        payload = registered_semantic_payload(delta, history=history, publication=publication, limits=limits)
        commitment = semantic_payload_digest(payload, history=history, publication=publication, limits=limits)
        if (
            entry.semantic_payload_digest != commitment
            or delta.observation_revision_after != observation_successor_revision(
                head, repository_id=repository_id, activation_digest=activation_digest,
                payload_digest=commitment,
            )
        ):
            raise ObservationLedgerReplayError("observation payload or successor is invalid")

        if isinstance(delta, IngestionObservationDelta):
            additions = tuple(mutation.record for mutation in delta.record_mutations)
            introductions = tuple(record for record in additions if isinstance(record, CanonicalOperationIntroductionRecord))
            outcomes = tuple(record for record in additions if isinstance(record, CanonicalOperationTerminalOutcomeRecord))
            if (
                any(record.ingestion_record_kind == "source_terminal_outcome" for record in additions)
                or tuple(sorted(record.operation_id for record in introductions)) != delta.operation_ids
                or tuple(sorted(record.operation_id for record in outcomes)) != delta.operation_ids
                or any((delta.operation_fence_id, operation_id) in operation_keys for operation_id in delta.operation_ids)
            ):
                raise ObservationLedgerReplayError("observation operation membership is invalid")
            operation_keys.update((delta.operation_fence_id, operation_id) for operation_id in delta.operation_ids)
            source_groups.setdefault(delta.operation_fence_id, []).append(entry)
        else:
            groups = source_groups.get(delta.operation_fence_id, [])
            if (
                tuple(group.result_digest for group in groups) != delta.source_outcome.group_result_digests
                or tuple(sorted(operation_id for group in groups for operation_id in group.delta.operation_ids)) != delta.operation_ids
                or any(group.delta.source_id != delta.source_id or group.delta.source_digest != delta.source_digest for group in groups)
            ):
                raise ObservationLedgerReplayError("observation source finalization membership is invalid")
            finalized_sources.add(delta.operation_fence_id)
            additions = (delta.source_outcome,)
        for record in additions:
            key = (
                record.ingestion_record_kind,
                record.introduction_id if isinstance(record, (CanonicalSourceIntroductionRecord, CanonicalOperationIntroductionRecord)) else record.outcome_id,
            )
            if key in records:
                raise ObservationLedgerReplayError("observation record is introduced more than once")
            records[key] = record
        verify_immutable_result(entry)
        next_head = emit_registered_observation_artifact(
            ObservationLedgerHead(
                schema_version=1, repository_id=repository_id, activation_digest=activation_digest,
                sequence=entry.sequence, observation_revision=delta.observation_revision_after,
                last_delta_id=delta.observation_delta_id, last_delta_digest=delta.delta_digest,
                last_entry_digest=entry.entry_digest, head_digest="0" * 64,
            ),
            schema_id="ObservationLedgerHead", history=history, publication=publication, limits=limits,
        ).value
        if not isinstance(next_head, ObservationLedgerHead):
            raise ObservationLedgerReplayError("observation head type is invalid")
        head = next_head
        entries.append(entry)
        delta_ids.add(delta.observation_delta_id)
    if head != expected_head:
        raise ObservationLedgerReplayError("observation replay does not reach the expected head")
    return emit_registered_observation_artifact(
        ObservationReplayState(
            schema_version=1, repository_id=repository_id, activation_digest=activation_digest,
            head=head, entries=tuple(entries), records=tuple(records[key] for key in sorted(records)),
            state_digest="0" * 64,
        ),
        schema_id="ObservationReplayState", history=history, publication=publication, limits=limits,
    )


def _selected_value(raw: bytes, schema_id: str, history: ProtectedTypedValueRegistryHistory, publication: VerifiedTypedValuePublication, limits: ProtectedTypedValueArtifactReaderLimits) -> BaseModel:
    value = validate_registered_artifact(raw, schema_id=schema_id, history=history, limits=limits)
    selected = emit_registered_observation_artifact(value, schema_id=schema_id, history=history, publication=publication, limits=limits)
    if selected.raw != raw:
        raise ObservationLedgerReplayError("observation artifact differs from its selected publication")
    return value

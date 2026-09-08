from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.observation_ledger_contracts import (
    ObservationGroupResultLocator,
    ObservationLedgerEntry,
    ObservationLedgerHead,
)
from memorii.core.memory_evolution.observation_replay_contracts import (
    IngestionObservationReplayCheckpoint,
    ObservationCheckpointBundle,
    ObservationCheckpointLifecycle,
    ObservationCheckpointPublicationReceipt,
    ObservationCheckpointSigningPreimage,
    ObservationReplayState,
    _record_identity,
)
from pydantic import ValidationError
from tests.unit.core.memory_evolution.test_observation_record_contracts import (
    _source_material,
    _terminal_group_delta,
)


def _digest(value: str) -> str:
    return sha256(value.encode("ascii")).hexdigest()


def _checkpoint_bundle() -> ObservationCheckpointBundle:
    delta = _terminal_group_delta(_source_material())
    entry_digest = _digest("entry")
    head = ObservationLedgerHead(
        schema_version=1,
        repository_id="repository:observation",
        activation_digest=_digest("activation"),
        sequence=1,
        observation_revision=delta.observation_revision_after,
        last_delta_id=delta.observation_delta_id,
        last_delta_digest=delta.delta_digest,
        last_entry_digest=entry_digest,
        head_digest=_digest("head"),
    )
    locator = ObservationGroupResultLocator(
        schema_version=1,
        kind="group_primary",
        immutable_record_id="record:group",
        source_id=delta.source_id,
        source_digest=delta.source_digest,
        source_operation_id="operation:observation-record",
        operation_fence_id=delta.operation_fence_id,
        transaction_group_id=delta.transaction_group_id,
        operation_ids=delta.operation_ids,
        request_ctv_digest=_digest("request"),
    )
    entry = ObservationLedgerEntry(
        schema_version=1,
        repository_id=head.repository_id,
        activation_digest=head.activation_digest,
        sequence=1,
        previous_entry_digest=None,
        semantic_payload_digest=_digest("payload"),
        delta=delta,
        result_locator=locator,
        result_digest=_digest("result"),
        entry_digest=entry_digest,
    )
    records = tuple(
        sorted(
            (mutation.record for mutation in delta.record_mutations),
            key=lambda record: (
                record.ingestion_record_kind,
                _record_identity(record),
            ),
        )
    )
    state = ObservationReplayState(
        schema_version=1,
        repository_id=head.repository_id,
        activation_digest=head.activation_digest,
        head=head,
        entries=(entry,),
        records=records,
        state_digest=_digest("state"),
    )
    lifecycle = ObservationCheckpointLifecycle(
        repository_id=head.repository_id,
        authority_revision=1,
        registry_revision=1,
        registry_digest=_digest("registry"),
        registry_history_digest=_digest("registry-history"),
        trust_policy_revision=1,
        trust_policy_digest=_digest("trust"),
        minimum_checkpoint_sequence=1,
        predecessor_authority_digest=None,
        authority_digest=_digest("authority"),
    )
    checkpoint = IngestionObservationReplayCheckpoint(
        checkpoint_id="checkpoint:one",
        observation_revision=head.observation_revision,
        last_observation_delta_id=delta.observation_delta_id,
        last_observation_delta_digest=delta.delta_digest,
        materialized_observation_ledger_digest=state.state_digest,
        observation_schema_fingerprint=_digest("schema"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        signing_key_id="checkpoint-key",
        trust_policy_digest=lifecycle.trust_policy_digest,
        checkpoint_digest=_digest("checkpoint"),
        signature="a" * 128,
    )
    receipt = ObservationCheckpointPublicationReceipt(
        repository_id=head.repository_id,
        activation_digest=head.activation_digest,
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_digest=checkpoint.checkpoint_digest,
        lifecycle_authority_digest=lifecycle.authority_digest,
        state_digest=state.state_digest,
        head_digest=head.head_digest,
        receipt_digest=_digest("receipt"),
    )
    return ObservationCheckpointBundle(
        schema_version=1,
        repository_id=head.repository_id,
        activation_digest=head.activation_digest,
        sequence=head.sequence,
        head=head,
        state=state,
        checkpoint=checkpoint,
        lifecycle=lifecycle,
        publication_receipt=receipt,
        bundle_digest=_digest("bundle"),
    )


def _signing_preimage(bundle: ObservationCheckpointBundle, *, created_at: datetime) -> ObservationCheckpointSigningPreimage:
    return ObservationCheckpointSigningPreimage(
        purpose="observation_checkpoint",
        repository_id=bundle.repository_id,
        activation_digest=bundle.activation_digest,
        sequence=bundle.sequence,
        head=bundle.head,
        lifecycle=bundle.lifecycle,
        checkpoint_id=bundle.checkpoint.checkpoint_id,
        observation_revision=bundle.checkpoint.observation_revision,
        last_observation_delta_id=bundle.checkpoint.last_observation_delta_id,
        last_observation_delta_digest=bundle.checkpoint.last_observation_delta_digest,
        materialized_observation_ledger_digest=bundle.state.state_digest,
        observation_schema_fingerprint=bundle.checkpoint.observation_schema_fingerprint,
        created_at=created_at,
        signing_key_id=bundle.checkpoint.signing_key_id,
        trust_policy_digest=bundle.lifecycle.trust_policy_digest,
    )


def test_checkpoint_bundle_accepts_real_ledger_and_native_record_values() -> None:
    bundle = _checkpoint_bundle()
    preimage = _signing_preimage(bundle, created_at=bundle.checkpoint.created_at)

    assert preimage.materialized_observation_ledger_digest == bundle.state.state_digest


def test_checkpoint_bundle_rejects_substituted_receipt_coordinate() -> None:
    bundle = _checkpoint_bundle()
    receipt = bundle.publication_receipt.model_copy(update={"checkpoint_id": "checkpoint:other"})

    with pytest.raises(ValidationError, match="bundle coordinates"):
        ObservationCheckpointBundle(**{**bundle.model_dump(mode="python"), "publication_receipt": receipt})


def test_lifecycle_requires_null_predecessor_only_for_genesis_authority() -> None:
    lifecycle = _checkpoint_bundle().lifecycle
    with pytest.raises(ValidationError, match="predecessor shape"):
        ObservationCheckpointLifecycle(
            **{**lifecycle.model_dump(mode="python"), "authority_revision": 1, "predecessor_authority_digest": _digest("prior")}
        )


def test_checkpoint_bundle_rejects_boolean_schema_version() -> None:
    bundle = _checkpoint_bundle()

    with pytest.raises(ValidationError, match="schema version"):
        ObservationCheckpointBundle(**{**bundle.model_dump(mode="python"), "schema_version": True})


@pytest.mark.parametrize(
    "created_at",
    (datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1)))),
)
def test_checkpoint_and_preimage_reject_non_utc_created_at(created_at: datetime) -> None:
    bundle = _checkpoint_bundle()

    with pytest.raises(ValidationError, match="created_at must be timezone-aware UTC"):
        IngestionObservationReplayCheckpoint(
            **{**bundle.checkpoint.model_dump(mode="python"), "created_at": created_at}
        )
    with pytest.raises(ValidationError, match="created_at must be timezone-aware UTC"):
        _signing_preimage(bundle, created_at=created_at)


def test_replay_state_rejects_tail_entry_revision_substitution() -> None:
    state = _checkpoint_bundle().state
    head = state.head.model_copy(update={"observation_revision": "observation:substituted"})

    with pytest.raises(ValidationError, match="state coordinates"):
        ObservationReplayState(**{**state.model_dump(mode="python"), "head": head})

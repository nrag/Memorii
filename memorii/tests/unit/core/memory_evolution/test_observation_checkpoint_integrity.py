from __future__ import annotations

import json
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution import observation_checkpoint_integrity as integrity_module
from memorii.core.memory_evolution.ingestion_contracts import CanonicalTypedValueProfileBinding
from memorii.core.memory_evolution.observation_checkpoint_integrity import (
    ObservationCheckpointIntegrityError,
    ObservationCheckpointIntegrityResult,
    ObservationCheckpointPreimageConstruction,
    construct_observation_checkpoint_v1_preimage,
    verify_observation_checkpoint_integrity,
)
from memorii.core.memory_evolution.observation_ledger_contracts import ObservationLedgerHead
from memorii.core.memory_evolution.observation_replay_contracts import (
    IngestionObservationReplayCheckpoint,
    ObservationCheckpointBundle,
    ObservationCheckpointLifecycle,
    ObservationReplayState,
)
from memorii.core.memory_evolution.typed_value_artifact_integrity import (
    TrustedTypedValueArtifactVerificationKey,
)
from memorii.core.memory_evolution.typed_value_model_codec import (
    MaterializedTypedValueModel,
)
from memorii.core.memory_evolution.typed_value_publication import (
    VerifiedTypedValuePublication,
)
from memorii.core.memory_evolution.typed_value_registry_compilation import (
    CompiledRegistryEntry,
)
from memorii.core.memory_evolution.typed_value_registry_history import (
    ProtectedTypedValueRegistryHistory,
    ResolvedTypedValueRegistryHistoryEntry,
    TypedValueRegistryReadRoute,
)
from pydantic import BaseModel
from tests.unit.core.memory_evolution.test_observation_replay_contracts import (
    _checkpoint_bundle,
)
from tests.unit.core.memory_evolution.test_typed_value_artifact_integrity import (
    _publication,
)

_MAXIMUM_BYTES = 60_000
_MAXIMUM_NODES = 1_000
_MAXIMUM_DEPTH = 80


@dataclass(frozen=True)
class _CheckpointFixture:
    history: ProtectedTypedValueRegistryHistory
    selected: ResolvedTypedValueRegistryHistoryEntry
    bundle: ObservationCheckpointBundle


@dataclass(frozen=True)
class _VerificationInvocation:
    selected_checkpoint: ResolvedTypedValueRegistryHistoryEntry
    replay_state: ObservationReplayState
    independently_loaded_head: ObservationLedgerHead
    lifecycle: ObservationCheckpointLifecycle
    checkpoint: IngestionObservationReplayCheckpoint
    repository_id: str
    activation_digest: str
    sequence: int
    verification_key: TrustedTypedValueArtifactVerificationKey
    maximum_bytes: int = _MAXIMUM_BYTES
    maximum_nodes: int = _MAXIMUM_NODES
    maximum_depth: int = _MAXIMUM_DEPTH

    def construct(self) -> ObservationCheckpointPreimageConstruction:
        return construct_observation_checkpoint_v1_preimage(
            selected_checkpoint=self.selected_checkpoint,
            replay_state=self.replay_state,
            independently_loaded_head=self.independently_loaded_head,
            lifecycle=self.lifecycle,
            checkpoint=self.checkpoint,
            repository_id=self.repository_id,
            activation_digest=self.activation_digest,
            sequence=self.sequence,
            maximum_bytes=self.maximum_bytes,
            maximum_nodes=self.maximum_nodes,
            maximum_depth=self.maximum_depth,
        )

    def verify(self) -> ObservationCheckpointIntegrityResult:
        return verify_observation_checkpoint_integrity(
            selected_checkpoint=self.selected_checkpoint,
            replay_state=self.replay_state,
            independently_loaded_head=self.independently_loaded_head,
            lifecycle=self.lifecycle,
            checkpoint=self.checkpoint,
            repository_id=self.repository_id,
            activation_digest=self.activation_digest,
            sequence=self.sequence,
            verification_key=self.verification_key,
            maximum_bytes=self.maximum_bytes,
            maximum_nodes=self.maximum_nodes,
            maximum_depth=self.maximum_depth,
        )


def _fixture(tmp_path: Path) -> _CheckpointFixture:
    history = _publication(tmp_path)
    entry = history.publications[0].compiled_registry.entry_for(
        "IngestionObservationReplayCheckpoint", "1"
    )
    binding = CanonicalTypedValueProfileBinding(
        entry.profile.profile_id,
        int(entry.profile.profile_version),
        entry.profile.profile_digest,
        entry.schema_id,
        int(entry.schema_version),
        entry.binding_digest,
    )
    return _CheckpointFixture(
        history=history,
        selected=history.resolve(binding, route=TypedValueRegistryReadRoute.PUBLIC),
        bundle=_checkpoint_bundle(),
    )


def _lp(*parts: bytes) -> bytes:
    return b"".join(len(part).to_bytes(8, "big") + part for part in parts)


def _map(**fields: object) -> dict[str, object]:
    return {"$type": "map", "entries": [[key, fields[key]] for key in sorted(fields)]}


def _integer(value: int) -> dict[str, str]:
    return {"$type": "integer", "value": str(value)}


def _raw_tree_limits(raw_bytes: bytes) -> tuple[int, int]:
    pending: list[tuple[object, int]] = [(json.loads(raw_bytes), 1)]
    nodes = 0
    maximum_depth = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        maximum_depth = max(maximum_depth, depth)
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return nodes, maximum_depth


def _preimage_oracle(bundle: ObservationCheckpointBundle) -> bytes:
    head = bundle.head
    lifecycle = bundle.lifecycle
    checkpoint = bundle.checkpoint
    value = _map(
        activation_digest=bundle.activation_digest,
        checkpoint_id=checkpoint.checkpoint_id,
        created_at={
            "$type": "datetime",
            "value": checkpoint.created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        },
        head=_map(
            activation_digest=head.activation_digest,
            head_digest=head.head_digest,
            last_delta_digest=head.last_delta_digest,
            last_delta_id=head.last_delta_id,
            last_entry_digest=head.last_entry_digest,
            observation_revision=head.observation_revision,
            repository_id=head.repository_id,
            schema_version=_integer(head.schema_version),
            sequence=_integer(head.sequence),
        ),
        last_observation_delta_digest=checkpoint.last_observation_delta_digest,
        last_observation_delta_id=checkpoint.last_observation_delta_id,
        lifecycle=_map(
            authority_digest=lifecycle.authority_digest,
            authority_revision=_integer(lifecycle.authority_revision),
            minimum_checkpoint_sequence=_integer(lifecycle.minimum_checkpoint_sequence),
            predecessor_authority_digest=lifecycle.predecessor_authority_digest,
            registry_digest=lifecycle.registry_digest,
            registry_history_digest=lifecycle.registry_history_digest,
            registry_revision=_integer(lifecycle.registry_revision),
            repository_id=lifecycle.repository_id,
            trust_policy_digest=lifecycle.trust_policy_digest,
            trust_policy_revision=_integer(lifecycle.trust_policy_revision),
        ),
        materialized_observation_ledger_digest=(
            checkpoint.materialized_observation_ledger_digest
        ),
        observation_revision=checkpoint.observation_revision,
        observation_schema_fingerprint=checkpoint.observation_schema_fingerprint,
        purpose="observation_checkpoint",
        repository_id=bundle.repository_id,
        sequence=_integer(bundle.sequence),
        signing_key_id=checkpoint.signing_key_id,
        trust_policy_digest=checkpoint.trust_policy_digest,
    )
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _members(selected: ResolvedTypedValueRegistryHistoryEntry) -> tuple[bytes, ...]:
    entry = selected.entry
    return (
        entry.profile.profile_id.encode(),
        str(entry.profile.profile_version).encode(),
        entry.profile.profile_digest.encode(),
        entry.schema_id.encode(),
        str(entry.schema_version).encode(),
        entry.binding_digest.encode(),
    )


def _signed_invocation(
    fixture: _CheckpointFixture,
) -> tuple[_VerificationInvocation, bytes, str]:
    oracle_bytes = _preimage_oracle(fixture.bundle)
    members = _members(fixture.selected)
    schema_preimage = _lp(
        b"memorii.semantic_ingestion.observation.IngestionObservationReplayCheckpoint.v1",
        *members,
        oracle_bytes,
    )
    digest = sha256(schema_preimage).hexdigest()
    private = Ed25519PrivateKey.generate()
    message = _lp(
        b"observation_checkpoint",
        *members,
        schema_preimage,
        digest.encode("ascii"),
    )
    checkpoint = fixture.bundle.checkpoint.model_copy(
        update={
            "checkpoint_digest": digest,
            "signature": private.sign(message).hex(),
        }
    )
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return (
        _VerificationInvocation(
            selected_checkpoint=fixture.selected,
            replay_state=fixture.bundle.state,
            independently_loaded_head=fixture.bundle.head,
            lifecycle=fixture.bundle.lifecycle,
            checkpoint=checkpoint,
            repository_id=fixture.bundle.repository_id,
            activation_digest=fixture.bundle.activation_digest,
            sequence=fixture.bundle.sequence,
            verification_key=TrustedTypedValueArtifactVerificationKey(public),
        ),
        oracle_bytes,
        digest,
    )


def test_fixed_checkpoint_constructor_and_signature_use_independent_oracle(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    invocation, oracle_bytes, digest = _signed_invocation(fixture)

    construction = invocation.construct()
    assert construction.canonical_preimage_bytes == oracle_bytes
    assert fixture.bundle.lifecycle.authority_digest.encode("ascii") in oracle_bytes
    result = invocation.verify()
    assert result.canonical_preimage_bytes == oracle_bytes
    assert result.checkpoint_digest == digest
    assert result.signature_verified is True


def test_checkpoint_rejects_crypto_and_body_mutations(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    invocation, oracle_bytes, digest = _signed_invocation(fixture)
    members = _members(fixture.selected)
    schema_preimage = _lp(
        b"memorii.semantic_ingestion.observation.IngestionObservationReplayCheckpoint.v1",
        *members,
        oracle_bytes,
    )
    private = Ed25519PrivateKey.generate()
    wrong_purpose = _lp(
        b"wrong-purpose",
        *members,
        schema_preimage,
        digest.encode("ascii"),
    )
    raw_digest_message = _lp(
        b"observation_checkpoint",
        *members,
        schema_preimage,
        sha256(schema_preimage).digest(),
    )
    invalid_invocations = (
        replace(
            invocation,
            verification_key=TrustedTypedValueArtifactVerificationKey(b"k" * 32),
        ),
        replace(
            invocation,
            checkpoint=invocation.checkpoint.model_copy(
                update={"checkpoint_digest": "f" * 64}
            ),
        ),
        replace(
            invocation,
            checkpoint=invocation.checkpoint.model_copy(
                update={"checkpoint_id": "checkpoint:changed"}
            ),
        ),
        replace(
            invocation,
            checkpoint=invocation.checkpoint.model_copy(
                update={"signature": private.sign(b"wrong").hex()}
            ),
        ),
        replace(
            invocation,
            checkpoint=invocation.checkpoint.model_copy(
                update={"signature": private.sign(wrong_purpose).hex()}
            ),
        ),
        replace(
            invocation,
            checkpoint=invocation.checkpoint.model_copy(
                update={"signature": private.sign(raw_digest_message).hex()}
            ),
        ),
        replace(
            invocation,
            checkpoint=invocation.checkpoint.model_copy(update={"signature": ""}),
        ),
        replace(
            invocation,
            checkpoint=invocation.checkpoint.model_copy(update={"signature": "00" * 63}),
        ),
    )
    for invalid in invalid_invocations:
        with pytest.raises(ObservationCheckpointIntegrityError):
            invalid.verify()


def test_checkpoint_rejects_all_fixed_join_mutations(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    invocation, _, _ = _signed_invocation(fixture)
    changed_head = fixture.bundle.head.model_copy(update={"head_digest": "f" * 64})
    changed_state = fixture.bundle.state.model_copy(update={"state_digest": "f" * 64})
    changed_lifecycle = fixture.bundle.lifecycle.model_copy(
        update={"repository_id": "repository:other"}
    )
    changed_authority = fixture.bundle.lifecycle.model_copy(
        update={"authority_digest": "f" * 64}
    )
    invalid_invocations = (
        replace(invocation, independently_loaded_head=changed_head),
        replace(invocation, replay_state=changed_state),
        replace(invocation, lifecycle=changed_lifecycle),
        replace(invocation, lifecycle=changed_authority),
        replace(
            invocation,
            checkpoint=invocation.checkpoint.model_copy(
                update={"trust_policy_digest": "f" * 64}
            ),
        ),
        replace(
            invocation,
            checkpoint=invocation.checkpoint.model_copy(
                update={"observation_revision": "observation:other"}
            ),
        ),
        replace(
            invocation,
            checkpoint=invocation.checkpoint.model_copy(
                update={"last_observation_delta_id": "delta:other"}
            ),
        ),
        replace(
            invocation,
            checkpoint=invocation.checkpoint.model_copy(
                update={"last_observation_delta_digest": "f" * 64}
            ),
        ),
        replace(invocation, repository_id="repository:other"),
        replace(invocation, activation_digest="f" * 64),
        replace(invocation, sequence=2),
    )
    for invalid in invalid_invocations:
        with pytest.raises(
            ObservationCheckpointIntegrityError,
            match="(join_invalid|digest_mismatch)",
        ):
            invalid.verify()


def test_checkpoint_forwards_exact_limits_and_rejects_one_below(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    invocation, oracle_bytes, _ = _signed_invocation(fixture)
    exact_nodes, exact_depth = _raw_tree_limits(oracle_bytes)
    exact = replace(
        invocation,
        maximum_bytes=len(oracle_bytes),
        maximum_nodes=exact_nodes,
        maximum_depth=exact_depth,
    )
    original_encode = integrity_module.encode_typed_value_model_candidate
    seen: list[tuple[CompiledRegistryEntry, VerifiedTypedValuePublication, int, int, int]] = []

    def forwarding_spy(
        value: BaseModel,
        *,
        entry: CompiledRegistryEntry,
        publication: VerifiedTypedValuePublication,
        maximum_bytes: int,
        maximum_nodes: int,
        maximum_depth: int,
    ) -> MaterializedTypedValueModel:
        seen.append((entry, publication, maximum_bytes, maximum_nodes, maximum_depth))
        return original_encode(
            value,
            entry=entry,
            publication=publication,
            maximum_bytes=maximum_bytes,
            maximum_nodes=maximum_nodes,
            maximum_depth=maximum_depth,
        )

    monkeypatch.setattr(integrity_module, "encode_typed_value_model_candidate", forwarding_spy)
    assert exact.verify().canonical_preimage_bytes == oracle_bytes
    assert seen == [
        (
            fixture.selected.publication.compiled_registry.entry_for(
                "ObservationCheckpointSigningPreimage", "1"
            ),
            fixture.selected.publication,
            len(oracle_bytes),
            exact_nodes,
            exact_depth,
        )
    ]
    for below in (
        replace(exact, maximum_bytes=len(oracle_bytes) - 1),
        replace(exact, maximum_nodes=exact_nodes - 1),
        replace(exact, maximum_depth=exact_depth - 1),
    ):
        with pytest.raises(
            ObservationCheckpointIntegrityError,
            match="preimage_encoding_invalid",
        ):
            below.verify()


def test_checkpoint_rejects_preimage_entry_as_selected_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    invocation, _, _ = _signed_invocation(fixture)
    entry = fixture.selected.publication.compiled_registry.entry_for(
        "ObservationCheckpointSigningPreimage", "1"
    )
    binding = CanonicalTypedValueProfileBinding(
        entry.profile.profile_id,
        int(entry.profile.profile_version),
        entry.profile.profile_digest,
        entry.schema_id,
        int(entry.schema_version),
        entry.binding_digest,
    )
    selected_preimage = fixture.history.resolve(
        binding,
        route=TypedValueRegistryReadRoute.PUBLIC,
    )

    def encoder_must_not_run(*args: object, **kwargs: object) -> object:
        raise AssertionError("checkpoint entry rejection must precede preimage encoding")

    monkeypatch.setattr(
        integrity_module,
        "encode_typed_value_model_candidate",
        encoder_must_not_run,
    )
    invalid = replace(invocation, selected_checkpoint=selected_preimage)
    with pytest.raises(
        ObservationCheckpointIntegrityError,
        match="checkpoint_entry_invalid",
    ):
        invalid.verify()

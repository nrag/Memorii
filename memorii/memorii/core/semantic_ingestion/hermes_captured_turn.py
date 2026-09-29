"""Typed durable identity for a Hermes user turn captured before completion."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.admission import PreparedSourceAdmission
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.contracts import TextPreparationRequest
from memorii.core.semantic_ingestion.source_preparation import TextPreparationService


class HermesCapturedTurnLedger(BaseModel):
    installation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    principal_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    turn_ordinal: int = Field(ge=1)
    message_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    captured_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def capture_id(self) -> str:
        return "hermes-captured-turn:v1:" + sha256(
            b"memorii.hermes.captured-turn.v1\0" + encode_typed_value(
                self.model_dump(mode="python", exclude={"captured_at", "source_id", "source_digest", "preparation_fingerprint"})
            )
        ).hexdigest()


class HermesCapturedTurnCoordination(BaseModel):
    """Durable ownership state joining a captured source to later work."""

    schema_version: Literal[1] = 1
    capture_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    installation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    principal_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    turn_ordinal: int = Field(ge=1)
    message_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: Literal["captured", "structured_pending", "completed_structured", "completed_ordinary"]
    first_structured_operation_fence_id: str | None = None
    completion_digest: str | None = None
    assistant_source_id: str | None = None
    assistant_source_digest: str | None = None
    ordinary_operation_fence_id: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_state(self) -> HermesCapturedTurnCoordination:
        completed = self.state in {"completed_structured", "completed_ordinary"}
        if self.state == "captured" and self.first_structured_operation_fence_id is not None:
            raise ValueError("captured coordination cannot have a structured operation")
        if self.state == "structured_pending" and not self.first_structured_operation_fence_id:
            raise ValueError("structured coordination requires its first operation")
        if completed and (not self.completion_digest or not self.assistant_source_id or not self.assistant_source_digest):
            raise ValueError("completed coordination requires completion evidence")
        if self.state == "completed_ordinary":
            if not self.ordinary_operation_fence_id:
                raise ValueError("ordinary completion requires its operation")
        elif self.ordinary_operation_fence_id is not None:
            raise ValueError("only ordinary completion may have an ordinary operation")
        return self

    @classmethod
    def captured(cls, ledger: HermesCapturedTurnLedger) -> HermesCapturedTurnCoordination:
        return cls(
            capture_id=ledger.capture_id, source_id=ledger.source_id,
            source_digest=ledger.source_digest, installation_id=ledger.installation_id,
            session_id=ledger.session_id, principal_id=ledger.principal_id,
            agent_id=ledger.agent_id, turn_ordinal=ledger.turn_ordinal,
            message_digest=ledger.message_digest, state="captured",
        )

    @property
    def memory_id(self) -> str:
        return self.memory_id_for_source(self.source_id)

    @staticmethod
    def memory_id_for_source(source_id: str) -> str:
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("captured coordination source ID is invalid")
        return "semantic_ingestion:hermes_capture_coordination:" + sha256(
            b"memorii.hermes.capture-coordination.v1\0" + source_id.encode("utf-8")
        ).hexdigest()


class HermesCapturedTurnCompletion(BaseModel):
    """Closed callback evidence used to finish one durable captured turn."""

    schema_version: Literal[1] = 1
    capture_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    principal_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    turn_ordinal: int = Field(ge=1)
    user_message_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    assistant_message_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transcript_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def completion_digest(self) -> str:
        return sha256(
            b"memorii.hermes.capture-completion.v1\0" + encode_typed_value(
                self.model_dump(mode="python")
            )
        ).hexdigest()


class HermesCapturedTurnSourceOwner:
    """Prepare a captured user source without starting ordinary semantic work."""

    def __init__(self, *, atomic_store: object, preparation: TextPreparationService, policy: object, writer_binding) -> None:
        self._atomic_store = atomic_store
        self._preparation = preparation
        self._policy = policy
        self._writer_binding = writer_binding

    def capture(self, *, admission: PreparedSourceAdmission, ledger: HermesCapturedTurnLedger):
        prepared = self._preparation.prepare(
            TextPreparationRequest(observation=admission.accepted.observation, policy=self._policy)
        )
        if (
            ledger.source_id != prepared.source_id
            or ledger.source_digest != prepared.source_digest
            or ledger.preparation_fingerprint != prepared.preparation_fingerprint
        ):
            raise ValueError("captured turn ledger does not bind prepared source")
        return self._atomic_store.publish_admitted_source_with_prepared_source(
            prepared=admission, prepared_source=prepared, capture_ledger=ledger,
            writer_binding=self._writer_binding(),
        )


__all__ = [
    "HermesCapturedTurnCoordination",
    "HermesCapturedTurnCompletion",
    "HermesCapturedTurnLedger",
    "HermesCapturedTurnSourceOwner",
]

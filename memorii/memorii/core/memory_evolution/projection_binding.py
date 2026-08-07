"""Neutral replay binding for independently owned projection history."""

from __future__ import annotations

from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value

ProjectionKind = Literal["temporal", "trust"]
_REPLAY_BINDING_DOMAIN = b"memorii.projection-history-replay-binding.v1\0"


def _strict_digest(value: object) -> object:
    if not isinstance(value, str):
        raise TypeError("projection digest must be a string")
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("projection digest must be lowercase hexadecimal")
    return value


def _binding_digest(value: object) -> str:
    return sha256(
        _REPLAY_BINDING_DOMAIN + encode_typed_value(value)
    ).hexdigest()


class ProjectionHistoryReplayBinding(BaseModel):
    projection_kind: ProjectionKind
    repository_id: str = Field(min_length=1)
    history_prefix_digest: str
    active_pointer_digest: str
    generation_digest: str
    binding_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "history_prefix_digest",
        "active_pointer_digest",
        "generation_digest",
        "binding_digest",
    )(_strict_digest)

    @model_validator(mode="after")
    def validate_binding(self) -> ProjectionHistoryReplayBinding:
        body = self.model_dump(mode="python", exclude={"binding_digest"})
        if self.binding_digest != _binding_digest(body):
            raise ValueError("projection replay binding digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> ProjectionHistoryReplayBinding:
        return cls.model_validate(
            {
                **values,
                "binding_digest": _binding_digest(values),
            }
        )


__all__ = ["ProjectionHistoryReplayBinding", "ProjectionKind"]

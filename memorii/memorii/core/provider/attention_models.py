"""Versioned provider envelopes for the opt-in conflict-attention protocol."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Generic, Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, PrivateAttr, field_validator, model_serializer, model_validator

from memorii.core.memory_evolution.conflict_attention import (
    CONFLICT_ATTENTION_PROTOCOL,
    EMBEDDED_PAGE_SIZE,
    ConflictAttentionPage,
)
from memorii.core.provider.models import ProviderPrefetchResult
from memorii.core.provider.tools import ProviderToolCallResult

PrefetchDecisionT = TypeVar("PrefetchDecisionT", bound=BaseModel)


def _wire_snapshot(*, protocol: str, legacy_result: BaseModel, attention_required: ConflictAttentionPage) -> str:
    """Detach protocol bytes from subsequently mutable nested legacy models."""

    payload = {
        "protocol": protocol,
        "legacy_result": json.loads(legacy_result.model_dump_json(exclude_none=False)),
        "attention_required": json.loads(attention_required.model_dump_json(exclude_none=False)),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class ProviderPrefetchAttentionEnvelope(BaseModel, Generic[PrefetchDecisionT]):
    """Opt-in attention protocol around the unchanged prefetch result."""

    protocol: Literal["memorii.conflict-attention.v1"] = CONFLICT_ATTENTION_PROTOCOL
    legacy_result: ProviderPrefetchResult[PrefetchDecisionT]
    attention_required: ConflictAttentionPage

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _wire_payload: str = PrivateAttr(default="")

    @field_validator("legacy_result", mode="before")
    @classmethod
    def validate_legacy_result(cls, value: object) -> object:
        if not isinstance(value, ProviderPrefetchResult):
            raise ValueError("legacy_result must be a validated ProviderPrefetchResult instance")
        return value.model_copy(deep=True)

    def model_post_init(self, __context: object) -> None:
        self._wire_payload = _wire_snapshot(
            protocol=self.protocol,
            legacy_result=self.legacy_result,
            attention_required=self.attention_required,
        )

    @model_serializer(mode="plain")
    def serialize_wire(self) -> dict[str, object]:
        return json.loads(self._wire_payload)

    def model_copy(self, *, update: Mapping[str, object] | None = None, deep: bool = False) -> Self:
        if update:
            raise ValueError("attention envelope copies cannot update wire-bound fields")
        return super().model_copy(deep=deep)

    @model_validator(mode="after")
    def validate_embedded_page(self) -> ProviderPrefetchAttentionEnvelope[PrefetchDecisionT]:
        if len(self.attention_required.items) > EMBEDDED_PAGE_SIZE:
            raise ValueError("provider attention envelope exceeds embedded page size")
        return self


class ProviderToolAttentionEnvelope(BaseModel):
    """Opt-in attention protocol around the unchanged tool result."""

    protocol: Literal["memorii.conflict-attention.v1"] = CONFLICT_ATTENTION_PROTOCOL
    legacy_result: ProviderToolCallResult
    attention_required: ConflictAttentionPage

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _wire_payload: str = PrivateAttr(default="")

    @field_validator("legacy_result", mode="before")
    @classmethod
    def validate_legacy_result(cls, value: object) -> object:
        if not isinstance(value, ProviderToolCallResult):
            raise ValueError("legacy_result must be a validated ProviderToolCallResult instance")
        return value.model_copy(deep=True)

    def model_post_init(self, __context: object) -> None:
        self._wire_payload = _wire_snapshot(
            protocol=self.protocol,
            legacy_result=self.legacy_result,
            attention_required=self.attention_required,
        )

    @model_serializer(mode="plain")
    def serialize_wire(self) -> dict[str, object]:
        return json.loads(self._wire_payload)

    def model_copy(self, *, update: Mapping[str, object] | None = None, deep: bool = False) -> Self:
        if update:
            raise ValueError("attention envelope copies cannot update wire-bound fields")
        return super().model_copy(deep=deep)

    @model_validator(mode="after")
    def validate_embedded_page(self) -> ProviderToolAttentionEnvelope:
        if len(self.attention_required.items) > EMBEDDED_PAGE_SIZE:
            raise ValueError("provider attention envelope exceeds embedded page size")
        return self

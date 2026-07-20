"""Shared JSON primitives and scalar contracts for benchmark artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

from memorii.core.prompts.sensitivity import sanitize_json_value

BenchmarkSuiteName: TypeAlias = Literal["memory_evolution_sim_v1", "memory_evolution_runtime_v1"]
DecisionMode: TypeAlias = Literal["auto", "rule", "llm", "hybrid"]
CheckpointVerdict: TypeAlias = Literal["pass", "fail", "abstain"]
AlignmentVerdict: TypeAlias = Literal[
    "aligned",
    "partial",
    "missing_expected",
    "unmatched_runtime",
    "ambiguous_alignment",
]
FinalOutputSource: TypeAlias = Literal["rule", "fake_oracle", "live_llm", "mixed", "reused_runtime_state"]
ProviderCountScope: TypeAlias = Literal["scenario_extractor_calls"]
ProviderHealthStatus: TypeAlias = Literal["pass", "fail", "not_applicable"]


def execution_source_from_counts(counts: Mapping[str, int]) -> FinalOutputSource:
    sources = {source for source, count in counts.items() if count > 0}
    if len(sources) != 1:
        return "mixed"
    source = next(iter(sources))
    if source not in {"rule", "fake_oracle", "live_llm", "reused_runtime_state"}:
        raise ValueError(f"unknown final output source: {source}")
    return cast(FinalOutputSource, source)
ActionSupportMode: TypeAlias = Literal[
    "runtime_action_item_exact",
    "runtime_action_semantic",
    "runtime_action_work_state_bridge",
    "claim_derived_action",
    "partial_action",
    "missing_action",
    "ambiguous_action",
    "ambiguous_work_state_bridge",
]
AlignmentItemType: TypeAlias = Literal["entity", "claim", "relation", "action", "evidence"]
JsonScalar: TypeAlias = str | int | float | bool | None
NonNegativeCount: TypeAlias = Annotated[int, Field(ge=0)]
CountMap: TypeAlias = dict[str, NonNegativeCount]


class ArtifactJsonObject(RootModel[dict[str, object]], Mapping[str, object]):
    """Explicitly open JSON object for intentionally dynamic report payloads.

    Benchmark metric namespaces evolve independently of the stable report
    envelope. Keeping this boundary recursive and JSON-only prevents arbitrary
    Python objects from entering artifacts while avoiding a false schema for
    every suite-specific metric.
    """

    def __getitem__(self, key: str) -> object:
        return self.root[key]

    def __iter__(self):
        return iter(self.root)

    def __len__(self) -> int:
        return len(self.root)

    @field_validator("root")
    @classmethod
    def _json_only(cls, value: dict[str, object]) -> dict[str, object]:
        try:
            normalized = sanitize_json_value(value)
        except TypeError as exc:
            raise ValueError(str(exc)) from exc
        if not isinstance(normalized, dict):
            raise TypeError("artifact JSON object root must remain an object")
        return cast(dict[str, object], normalized)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ArtifactJsonObject):
            return self.root == other.root
        if isinstance(other, dict):
            return self.root == other
        return NotImplemented

    def to_json_object(self) -> dict[str, object]:
        return self.root


def empty_json_object() -> ArtifactJsonObject:
    return ArtifactJsonObject(root={})


class FlatArtifactModel(BaseModel):
    """Strict artifact model with an explicit JSON serialization boundary."""

    model_config = ConfigDict(extra="forbid")

    def to_json_row(self) -> dict[str, object]:
        return cast(dict[str, object], _artifact_value_to_json(self.model_dump(mode="python")))


def artifact_row_to_json(row: FlatArtifactModel) -> dict[str, object]:
    """Serialize a validated artifact row at an explicit JSON boundary."""

    return row.to_json_row()


def artifact_rows_to_json(rows: Sequence[FlatArtifactModel]) -> list[dict[str, object]]:
    """Serialize artifact rows at explicit JSON/report boundaries."""

    return [artifact_row_to_json(row) for row in rows]


def _artifact_value_to_json(value: object) -> object:
    if isinstance(value, FlatArtifactModel):
        return value.to_json_row()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_artifact_value_to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _artifact_value_to_json(item) for key, item in value.items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value

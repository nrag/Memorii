"""Shared temporal value contracts with no semantic-ingestion dependencies."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class TimeInterval(BaseModel):
    start: datetime
    end: datetime | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_interval(self) -> TimeInterval:
        if self.end is not None and self.end <= self.start:
            raise ValueError("interval end must be later than start")
        return self


__all__ = ["TimeInterval"]

"""Closed literal codecs used by the shipped default ontology catalog."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.semantic_ingestion.catalog_authority import contract_digest

_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_CURRENCY = re.compile(r"[A-Z]{3}\Z")

_STATUS_POLICIES: dict[str, tuple[frozenset[str], dict[str, str]]] = {
    "work_item_status": (
        frozenset({"todo", "in_progress", "blocked", "done", "canceled"}),
        {
            "open": "todo", "to do": "todo", "started": "in_progress",
            "working": "in_progress", "complete": "done", "completed": "done",
            "cancelled": "canceled",
        },
    ),
    "opportunity_stage": (
        frozenset({"lead", "qualified", "proposal", "negotiation", "won", "lost"}),
        {
            "prospect": "lead", "qualified lead": "qualified", "offer": "proposal",
            "negotiating": "negotiation", "closed won": "won", "closed lost": "lost",
        },
    ),
}


class CatalogValuePolicyDeclaration(BaseModel):
    schema_version: Literal[1]
    value_policy_id: Literal[
        "local_date", "work_item_status", "time_interval", "money_iso4217",
        "opportunity_stage",
    ]
    codec_id: Literal["local_date_v1", "status_text_v1", "time_interval_v1", "money_iso4217_v1"]
    canonical_values: tuple[str, ...] = ()
    aliases: tuple[tuple[str, str], ...] = ()
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_policy(self) -> CatalogValuePolicyDeclaration:
        if (
            self.canonical_values != tuple(sorted(set(self.canonical_values)))
            or self.aliases != tuple(sorted(set(self.aliases)))
            or any(target not in self.canonical_values for _alias, target in self.aliases)
        ):
            raise ValueError("catalog value policy is not canonical")
        body = self.model_dump(mode="python", exclude={"policy_digest"})
        if self.policy_digest != contract_digest(
            b"memorii.learned-ontology.value-policy.v1", body
        ):
            raise ValueError("catalog value policy digest is invalid")
        return self

    @classmethod
    def create(
        cls,
        *,
        value_policy_id: Literal[
            "local_date", "work_item_status", "time_interval", "money_iso4217",
            "opportunity_stage",
        ],
        codec_id: Literal[
            "local_date_v1", "status_text_v1", "time_interval_v1", "money_iso4217_v1",
        ],
        canonical_values: tuple[str, ...] = (),
        aliases: tuple[tuple[str, str], ...] = (),
    ) -> CatalogValuePolicyDeclaration:
        body = {
            "schema_version": 1, "value_policy_id": value_policy_id,
            "codec_id": codec_id,
            "canonical_values": tuple(sorted(canonical_values)),
            "aliases": tuple(sorted(aliases)),
        }
        return cls(
            **body,
            policy_digest=contract_digest(
                b"memorii.learned-ontology.value-policy.v1", body
            ),
        )


DEFAULT_CATALOG_VALUE_POLICIES = {
    "local_date": CatalogValuePolicyDeclaration.create(
        value_policy_id="local_date", codec_id="local_date_v1",
    ),
    "time_interval": CatalogValuePolicyDeclaration.create(
        value_policy_id="time_interval", codec_id="time_interval_v1",
    ),
    "money_iso4217": CatalogValuePolicyDeclaration.create(
        value_policy_id="money_iso4217", codec_id="money_iso4217_v1",
    ),
    **{
        policy_id: CatalogValuePolicyDeclaration.create(
            value_policy_id=policy_id,
            codec_id="status_text_v1",
            canonical_values=tuple(canonical),
            aliases=tuple(aliases.items()),
        )
        for policy_id, (canonical, aliases) in _STATUS_POLICIES.items()
    },
}


def _index_value_policies(
    policies: Iterable[CatalogValuePolicyDeclaration],
) -> dict[tuple[str, str], CatalogValuePolicyDeclaration]:
    index: dict[tuple[str, str], CatalogValuePolicyDeclaration] = {}
    for policy in policies:
        coordinate = (policy.value_policy_id, policy.policy_digest)
        if coordinate in index:
            raise ValueError("catalog value policy coordinate is duplicated")
        index[coordinate] = policy
    return index


DEFAULT_CATALOG_VALUE_POLICY_HISTORY = _index_value_policies(
    DEFAULT_CATALOG_VALUE_POLICIES.values()
)


class CatalogLocalDate(BaseModel):
    value: date
    source_calendar: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogTimeInterval(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
    start_bound: Literal["closed", "open"]
    end_bound: Literal["exclusive", "open"]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_interval(self) -> CatalogTimeInterval:
        if (self.start is None) != (self.start_bound == "open"):
            raise ValueError("time interval start bound is inconsistent")
        if (self.end is None) != (self.end_bound == "open"):
            raise ValueError("time interval end bound is inconsistent")
        for value in (self.start, self.end):
            if value is not None and value.tzinfo is None:
                raise ValueError("time interval bounds must be timezone-aware")
        if self.start is not None:
            TimeInterval(start=self.start, end=self.end)
        return self


class CatalogMoney(BaseModel):
    decimal_amount: str
    currency: str

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_money(self) -> CatalogMoney:
        if not _DECIMAL.fullmatch(self.decimal_amount) or not _CURRENCY.fullmatch(self.currency):
            raise ValueError("money value is not canonical")
        try:
            amount = Decimal(self.decimal_amount)
        except InvalidOperation as exc:  # pragma: no cover - regex excludes it
            raise ValueError("money value is not canonical") from exc
        if not amount.is_finite() or amount == 0 and self.decimal_amount.startswith("-"):
            raise ValueError("money value is not canonical")
        return self


class CatalogStatusText(BaseModel):
    value_policy_id: Literal["work_item_status", "opportunity_stage"]
    value_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_value: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_status(self, info: ValidationInfo) -> CatalogStatusText:
        policy_history: Mapping[tuple[str, str], CatalogValuePolicyDeclaration] = (
            DEFAULT_CATALOG_VALUE_POLICY_HISTORY
        )
        if info.context is not None and "value_policy_history" in info.context:
            candidate = info.context["value_policy_history"]
            if not isinstance(candidate, Mapping):
                raise ValueError("catalog value policy history is invalid")
            policy_history = candidate
        policy = policy_history.get((self.value_policy_id, self.value_policy_digest))
        if policy is None or self.canonical_value not in policy.canonical_values:
            raise ValueError("status text is not a canonical catalog value")
        return self

    @classmethod
    def decode(
        cls,
        payload: Mapping[str, Any],
        *,
        historical_policies: Iterable[CatalogValuePolicyDeclaration],
    ) -> CatalogStatusText:
        """Decode against the declarations carried by the selected historical bundle."""
        return cls.model_validate(
            payload,
            context={"value_policy_history": _index_value_policies(historical_policies)},
        )

    @classmethod
    def parse(
        cls,
        *,
        value_policy_id: Literal["work_item_status", "opportunity_stage"],
        source_text: str,
    ) -> CatalogStatusText:
        selected_policy = DEFAULT_CATALOG_VALUE_POLICIES[value_policy_id]
        normalized = " ".join(source_text.casefold().split())
        canonical = frozenset(selected_policy.canonical_values)
        aliases = dict(selected_policy.aliases)
        selected = normalized if normalized in canonical else aliases.get(normalized)
        if selected is None:
            raise ValueError("status text is unresolved")
        return cls.model_validate(
            {
                "value_policy_id": value_policy_id,
                "value_policy_digest": selected_policy.policy_digest,
                "canonical_value": selected,
            },
            context={
                "value_policy_history": _index_value_policies((selected_policy,))
            },
        )


DefaultCatalogLiteralValue = CatalogLocalDate | CatalogTimeInterval | CatalogMoney | CatalogStatusText

__all__ = [
    "CatalogLocalDate", "CatalogMoney", "CatalogStatusText", "CatalogTimeInterval",
    "CatalogValuePolicyDeclaration", "DEFAULT_CATALOG_VALUE_POLICIES",
    "DEFAULT_CATALOG_VALUE_POLICY_HISTORY",
    "DefaultCatalogLiteralValue",
]

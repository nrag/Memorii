"""Closed protected-clock owner for ingestion-time retention authority.

One clock instance is the single time authority behind raw-source retention:
the provider raw-source construction sites, governance derivation, and the
atomic store ``now_provider`` all sample through it.  Its ``identity`` is a
stable protected configuration identifier (never a caller string or a
hostname guess) that later seals record verbatim; provisioning policy is a
separate owner decision.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

# Composition-root default: the stable protected identifier carried by the
# production clock when no host configuration supplies an explicit one.
PRODUCTION_INGESTION_TIME_CLOCK_IDENTITY = (
    "memorii.semantic_ingestion.ingestion_time_clock.production.v1"
)


class IngestionTimeClock:
    """Immutable protected clock; construction requires both members.

    The closed posture mirrors the ingestion-time wire contracts
    (graph_ingestion_time_contracts.py): strict construction with both
    members required, no extra attributes, and timezone-aware UTC samples
    only.  Naive and non-UTC samples fail closed rather than being guessed
    into retention time.
    """

    __slots__ = ("_identity", "_now_provider")

    def __init__(
        self,
        *,
        identity: str,
        now_provider: Callable[[], datetime],
    ) -> None:
        if not isinstance(identity, str) or not identity:
            raise ValueError("ingestion time clock identity is required")
        if not callable(now_provider):
            raise TypeError("ingestion time clock requires a callable now provider")
        self._identity = identity
        self._now_provider = now_provider

    @property
    def identity(self) -> str:
        """Stable protected configuration identifier recorded by every seal."""
        return self._identity

    def now_utc(self) -> datetime:
        """One timezone-aware UTC sample; naive and non-UTC values raise."""
        value = self._now_provider()
        offset = value.utcoffset() if isinstance(value, datetime) else None
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or offset is None
            or offset.total_seconds() != 0
        ):
            raise ValueError("ingestion time clock samples must be timezone-aware UTC")
        return value.astimezone(UTC)


__all__ = [
    "IngestionTimeClock",
    "PRODUCTION_INGESTION_TIME_CLOCK_IDENTITY",
]

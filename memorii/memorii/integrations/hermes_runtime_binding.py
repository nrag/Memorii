"""Hermes runtime binding shared by the optional bridge and first-party factory."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.provider.service import ProviderMemoryService


@dataclass(frozen=True)
class HermesProviderRuntimeBinding:
    """One configured service and its host-owned authenticated ingress issuer."""

    service: ProviderMemoryService
    issue_ingress: Callable[[object], AuthenticatedHostIngress]
    completed_turn_runtime: object | None = None
    absent_author_id: str = "memorii.hermes.author.absent.v1"


__all__ = ["HermesProviderRuntimeBinding"]

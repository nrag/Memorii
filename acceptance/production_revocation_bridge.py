"""Read-only serialized boundary for production revocation evidence.

Acceptance receives bytes only.  The production provider owns the on-disk
layout and never imports acceptance schemas or verification code.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SerializedProductionRevocationEvidence:
    receipt: bytes
    checkpoint: bytes


@runtime_checkable
class SerializedProductionRevocationReader(Protocol):
    def read_for_prior_release(
        self, prior_approval_release_digest: str
    ) -> SerializedProductionRevocationEvidence: ...

    def load_checkpoint(self, checkpoint_digest: str) -> bytes: ...


@runtime_checkable
class ProductionRevocationReaderFactory(Protocol):
    def from_fixed_configuration(
        self, configuration: object
    ) -> SerializedProductionRevocationReader: ...


@runtime_checkable
class SerializedProductionRevocationPublisher(Protocol):
    """Production storage boundary for acceptance-verified opaque bytes."""

    def publish_verified(
        self, *, prior_approval_release_digest: str, receipt: bytes, checkpoint: bytes
    ) -> None: ...


@runtime_checkable
class ProductionRevocationPublisherFactory(Protocol):
    def from_fixed_configuration(
        self, configuration: object
    ) -> SerializedProductionRevocationPublisher: ...


def configured_revocation_reader(
    configuration: object,
) -> SerializedProductionRevocationReader:
    providers = tuple(entry_points(group="memorii.acceptance_production_revocation_reader"))
    if len(providers) != 1:
        raise ValueError("acceptance_production_revocation_provider")
    factory = providers[0].load()()
    if not isinstance(factory, ProductionRevocationReaderFactory):
        raise ValueError("acceptance_production_revocation_provider")
    reader = factory.from_fixed_configuration(configuration)
    if not isinstance(reader, SerializedProductionRevocationReader):
        raise ValueError("acceptance_production_revocation_provider")
    return reader


def configured_revocation_publisher(
    configuration: object,
) -> SerializedProductionRevocationPublisher:
    providers = tuple(entry_points(group="memorii.acceptance_production_revocation_publisher"))
    if len(providers) != 1:
        raise ValueError("acceptance_production_revocation_publisher")
    factory = providers[0].load()()
    if not isinstance(factory, ProductionRevocationPublisherFactory):
        raise ValueError("acceptance_production_revocation_publisher")
    publisher = factory.from_fixed_configuration(configuration)
    if not isinstance(publisher, SerializedProductionRevocationPublisher):
        raise ValueError("acceptance_production_revocation_publisher")
    return publisher

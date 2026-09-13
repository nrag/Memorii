"""Serialized boundary to the production deployment-authority owner.

The acceptance package never imports production code.  A fixed installed entry
point supplies the production publisher and only canonical JSON bytes cross the
boundary.
"""
from __future__ import annotations

from importlib.metadata import entry_points
from typing import Protocol, runtime_checkable


@runtime_checkable
class SerializedDeploymentPublisher(Protocol):
    def prepare_verified(self, request: bytes) -> bytes: ...

    def publish_prepared(self, artifact: bytes) -> bytes: ...


@runtime_checkable
class DeploymentPublisherFactory(Protocol):
    def from_fixed_configuration(self, configuration: object) -> SerializedDeploymentPublisher: ...


def configured_publisher(configuration: object) -> SerializedDeploymentPublisher:
    providers = tuple(entry_points(group="memorii.acceptance_deployment_publisher"))
    if len(providers) != 1:
        raise ValueError("acceptance_deployment_provider")
    factory = providers[0].load()()
    if not isinstance(factory, DeploymentPublisherFactory):
        raise ValueError("acceptance_deployment_provider")
    publisher = factory.from_fixed_configuration(configuration)
    if not isinstance(publisher, SerializedDeploymentPublisher):
        raise ValueError("acceptance_deployment_provider")
    return publisher

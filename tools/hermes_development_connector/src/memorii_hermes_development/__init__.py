"""Development-only Hermes runtime binding over Memorii's real provider path.

The connector deliberately depends on repository test authority.  It exists so
an interactive Hermes trial can exercise durable ingestion and retrieval before
release keys are available; it must not be installed in a production runtime.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path
from shutil import rmtree
from typing import TYPE_CHECKING, Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

if TYPE_CHECKING:
    from memorii.integrations.hermes_memory_provider import (
        HermesIngressRequest,
        HermesProviderRuntimeBinding,
        HermesProviderServiceContext,
    )

_DEVELOPMENT_KEY_SEED = sha256(b"memorii-hermes-development-activation-key-v1").digest()
_PATCHES: list[Any] = []


def _repository_python_root() -> Path:
    connector = Path(__file__).resolve()
    for parent in connector.parents:
        candidate = parent / "memorii" / "tests" / "integration" / "test_observation_ledger_activation.py"
        if candidate.is_file():
            return parent / "memorii"
    raise RuntimeError(
        "Memorii Hermes development connector requires its editable Memorii repository checkout"
    )


def _load_development_factory(authority_root: Path):
    repository_python_root = _repository_python_root()
    if str(repository_python_root) not in sys.path:
        sys.path.insert(0, str(repository_python_root))

    from pytest import MonkeyPatch
    from tests.integration.test_observation_ledger_activation import (
        _provider_factory,
        _seed_provider,
    )
    from tests.unit.core.memory_evolution import test_observation_activation_configuration

    class _DeterministicDevelopmentKey:
        @staticmethod
        def generate() -> Ed25519PrivateKey:
            return Ed25519PrivateKey.from_private_bytes(_DEVELOPMENT_KEY_SEED)

    rmtree(authority_root, ignore_errors=True)
    authority_root.mkdir(parents=True)
    patches = MonkeyPatch()
    patches.setattr(
        test_observation_activation_configuration,
        "Ed25519PrivateKey",
        _DeterministicDevelopmentKey,
    )
    build_service, _, _ = _provider_factory(
        authority_root,
        patches,
        normalization=True,
        complete_registry=True,
    )
    _PATCHES.append(patches)
    return build_service, _seed_provider


def _issue_ingress(request: HermesIngressRequest):
    from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress

    return AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=(request.user_id or "user:alice"),
        session_handle=request.session_id,
        received_at=request.received_at,
    )


def build_runtime_binding(
    context: HermesProviderServiceContext,
) -> HermesProviderRuntimeBinding:
    """Build one persistent development service for the active Hermes profile."""

    from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
    from memorii.integrations.hermes_memory_provider import (
        HermesProviderRuntimeBinding,
        HermesProviderServiceContext,
    )

    if type(context) is not HermesProviderServiceContext:
        raise TypeError("Hermes development factory requires HermesProviderServiceContext")
    context.storage_root.mkdir(parents=True, exist_ok=True)
    storage_root = context.storage_root.resolve()
    build_service, seed_provider = _load_development_factory(
        storage_root / ".development-authority"
    )
    service = build_service(
        MemoryPlaneService(
            record_store=JsonlMemoryPlaneStore(storage_root / "memory-plane")
        )
    )
    seed_provider(service)
    return HermesProviderRuntimeBinding(service=service, issue_ingress=_issue_ingress)


def probe() -> dict[str, object]:
    """Return installation state without starting or mutating a provider."""

    from importlib.metadata import entry_points

    factories = tuple(entry_points(group="memorii.hermes.provider_service"))
    providers = tuple(entry_points(group="hermes_agent.memory_providers"))
    try:
        hermes_abc_installed = find_spec("agent.memory_provider") is not None
    except ModuleNotFoundError:
        hermes_abc_installed = False
    return {
        "development_factory_count": len(factories),
        "development_factory_names": [item.name for item in factories],
        "hermes_abc_installed": hermes_abc_installed,
        "memorii_provider_installed": any(item.name == "memorii" for item in providers),
        "checked_at": datetime.now(UTC).isoformat(),
    }


__all__ = ["build_runtime_binding", "probe"]

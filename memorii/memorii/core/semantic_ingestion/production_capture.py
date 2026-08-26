"""Production-owned isolated caller for canonical-evidence capture cells."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from multiprocessing import get_context
from multiprocessing.queues import Queue
from pathlib import Path
from queue import Empty
from tempfile import mkdtemp
from typing import Literal

from memorii.core.filesystem_storage.bundle import build_filesystem_provider
from memorii.core.memory_evolution.bootstrap_profile import (
    HostBootstrapCapability,
    HostBootstrapMaterialVerifier,
)
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.production_authority import (
    ProductionAuthorityCompositionReceipt,
    VerifiedProductionHostAuthority,
    build_verified_production_host_authority,
)
from memorii.domain.enums import SourceModality
from memorii.integrations.hermes_provider import HermesMemoryProvider

CaptureRoot = Literal["direct", "factory", "filesystem", "hermes"]
CaptureBackend = Literal["memory", "jsonl"]


@dataclass(frozen=True)
class CanonicalEvidenceCaptureCell:
    """Pinned inputs for exactly one isolated public-root invocation."""

    root: CaptureRoot
    backend: CaptureBackend
    host_bootstrap_capability: HostBootstrapCapability
    host_bootstrap_material_verifier: HostBootstrapMaterialVerifier
    server_time: datetime
    operation: ProviderOperation
    content: str
    operation_identity: str
    authenticated_host_ingress: AuthenticatedHostIngress
    storage_root: Path | None = None
    role: str | None = None
    target: str | None = None
    action: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    language: str = "en"
    speaker_id: str | None = None
    source_modality: SourceModality | None = None


@dataclass(frozen=True)
class CanonicalEvidenceCaptureResult:
    """Serialized production result plus the factory-issued ephemeral receipt."""

    root: CaptureRoot
    backend: CaptureBackend
    result: dict[str, object]
    receipt: dict[str, str]


class CanonicalEvidenceCaptureSupervisor:
    """The sole non-test production caller for an isolated capture cell."""

    def __init__(self, *, child_timeout_seconds: float = 30.0) -> None:
        if child_timeout_seconds <= 0:
            raise ValueError("capture child timeout must be positive")
        self._child_timeout_seconds = child_timeout_seconds

    def capture_cell(
        self, cell: CanonicalEvidenceCaptureCell
    ) -> CanonicalEvidenceCaptureResult:
        """Run one public ``sync_event`` in a fresh supervised child process."""

        context = get_context("spawn")
        queue = context.Queue(maxsize=1)
        child = context.Process(target=_capture_child, args=(cell, queue))
        child.start()
        try:
            payload = queue.get(timeout=self._child_timeout_seconds)
        except Empty as exc:
            child.terminate()
            child.join()
            raise TimeoutError("canonical evidence capture child timed out") from exc
        finally:
            child.join()
        if child.exitcode != 0:
            raise RuntimeError("canonical evidence capture child failed")
        if not isinstance(payload, CanonicalEvidenceCaptureResult):
            raise RuntimeError("canonical evidence capture child returned an invalid result")
        return payload


def _capture_child(
    cell: CanonicalEvidenceCaptureCell,
    queue: Queue[CanonicalEvidenceCaptureResult],
) -> None:
    authority = build_verified_production_host_authority(
        host_bootstrap_capability=cell.host_bootstrap_capability,
        host_bootstrap_material_verifier=cell.host_bootstrap_material_verifier,
        server_time=cell.server_time,
    )
    if authority is None:
        raise ValueError("production host authority verification failed")
    storage_root = cell.storage_root or Path(mkdtemp(prefix="memorii-canonical-evidence-"))
    service = _build_root(cell=cell, storage_root=storage_root, authority=authority)
    result = service.sync_event(
        operation=cell.operation,
        content=cell.content,
        operation_id=cell.operation_identity,
        role=cell.role,
        target=cell.target,
        action=cell.action,
        session_id=cell.session_id,
        task_id=cell.task_id,
        user_id=cell.user_id,
        language=cell.language,
        speaker_id=cell.speaker_id,
        timestamp=cell.server_time,
        source_modality=cell.source_modality,
        authenticated_host_ingress=cell.authenticated_host_ingress,
    )
    queue.put(
        CanonicalEvidenceCaptureResult(
            root=cell.root,
            backend=cell.backend,
            result=result.model_dump(mode="json"),
            receipt=_receipt_projection(authority.receipt),
        )
    )


def _build_root(
    *,
    cell: CanonicalEvidenceCaptureCell,
    storage_root: Path,
    authority: VerifiedProductionHostAuthority,
) -> ProviderMemoryService | HermesMemoryProvider:
    if cell.backend == "memory":
        memory_plane = MemoryPlaneService()
    else:
        storage_root.mkdir(parents=True, exist_ok=True)
        memory_plane = MemoryPlaneService(
            record_store=JsonlMemoryPlaneStore(storage_root / "memory_plane")
        )
    if cell.root == "direct":
        return ProviderMemoryService(
            memory_plane=memory_plane,
            verified_production_host_authority=authority,
        )
    if cell.root == "factory":
        return build_provider_memory_service_from_env(
            memory_plane=memory_plane,
            verified_production_host_authority=authority,
        )
    if cell.root == "filesystem":
        return build_filesystem_provider(
            storage_root=storage_root,
            memory_plane=memory_plane,
            verified_production_host_authority=authority,
        )
    if cell.root == "hermes":
        if cell.backend == "jsonl":
            return HermesMemoryProvider(
                storage_root=str(storage_root),
                verified_production_host_authority=authority,
            )
        return HermesMemoryProvider(
            memory_plane=memory_plane,
            verified_production_host_authority=authority,
        )
    raise ValueError("unsupported canonical evidence capture root")


def _receipt_projection(receipt: ProductionAuthorityCompositionReceipt) -> dict[str, str]:
    """Serialize only public receipt fields; the operation token never leaves the child."""

    return {
        "authority_digest": receipt.authority_digest,
        "verified_material_digest": receipt.verified_material_digest,
        "verification_digest": receipt.verification_digest,
        "trust_domain": receipt.trust_domain,
        "factory_symbol": receipt.factory_symbol,
        "verification_symbol": receipt.verification_symbol,
    }


__all__ = [
    "CanonicalEvidenceCaptureCell",
    "CanonicalEvidenceCaptureResult",
    "CanonicalEvidenceCaptureSupervisor",
]

"""Content-free operational summaries drawn from verified owner records."""

from __future__ import annotations

import json
import re
import sqlite3
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.persistence.contracts import RuntimePublicationState
from memorii.stores.sqlite.partition import PartitionDataRepository


class QueueStatus(BaseModel):
    pending_count: int = Field(ge=0)
    held_count: int = Field(ge=0)
    oldest_pending_age_seconds: int | None = Field(default=None, ge=0)
    oldest_held_age_seconds: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class InstalledArtifactStatus(BaseModel):
    distribution: Literal["memorii"] = "memorii"
    version: str | None = None
    install_kind: Literal["archive", "editable", "unknown"] = "unknown"
    installed_archive_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


def installed_artifact_status() -> InstalledArtifactStatus:
    """Report installation metadata without treating it as a signed release record."""
    import memorii

    try:
        installed = distribution("memorii")
    except PackageNotFoundError:
        return InstalledArtifactStatus()
    version = installed.version
    if not version or re.fullmatch(r"[0-9][0-9A-Za-z.!+_-]{0,127}", version) is None:
        return InstalledArtifactStatus()
    raw = installed.read_text("direct_url.json")
    if raw is None or memorii.__file__ is None:
        return InstalledArtifactStatus(version=version)
    try:
        origin = json.loads(raw)
    except ValueError:
        return InstalledArtifactStatus(version=version)
    if not isinstance(origin, dict):
        return InstalledArtifactStatus(version=version)
    location = origin.get("dir_info")
    if isinstance(location, dict) and location.get("editable") is True:
        return InstalledArtifactStatus(version=version, install_kind="editable")
    if Path(memorii.__file__).resolve() != Path(str(installed.locate_file("memorii/__init__.py"))).resolve():
        return InstalledArtifactStatus(version=version)
    archive = origin.get("archive_info")
    if not isinstance(archive, dict):
        return InstalledArtifactStatus(version=version)
    hashes = archive.get("hashes")
    sha256 = hashes.get("sha256") if isinstance(hashes, dict) else None
    if not isinstance(sha256, str) or len(sha256) != 64 or set(sha256) - set("0123456789abcdef"):
        sha256 = None
    return InstalledArtifactStatus(
        version=version, install_kind="archive", installed_archive_sha256=sha256,
    )


def delivery_queue_status(
    connection: sqlite3.Connection, publication: RuntimePublicationState,
) -> QueueStatus:
    """Count dispatchable and unresolved outbox work in a verified partition."""
    from memorii.core.persistence.runtime_api import LegacyUnresolvedDelivery, RuntimeOutboxDelivery
    from memorii.core.persistence.writeback_decisions import CandidateDeliveryEntry
    from memorii.core.work_state.runtime_projection import ManagedWorkProjectionDelivery

    pending = held = 0
    rejected = _selected_restore_rejections(connection, publication)
    for (delivery_id,), payload in PartitionDataRepository.restore_inventory_rows(
        connection, "runtime_outbox_deliveries",
    ):
        record = json.loads(payload)
        if not isinstance(record, dict):
            raise ValueError("delivery inventory row must be an object")
        kind = record.get("record_type")
        if kind == "legacy_unresolved_delivery":
            if LegacyUnresolvedDelivery.model_validate(record).delivery_id != delivery_id:
                raise ValueError("legacy delivery identity differs from its inventory")
            held += 1
            continue
        if kind is None:
            legacy = RuntimeOutboxDelivery.model_validate(record)
            if legacy.delivery_id != delivery_id:
                raise ValueError("legacy delivery identity differs from its inventory")
            pending += legacy.status in {"pending", "delivering"}
            held += legacy.status == "needs_reconciliation"
            continue
        if kind == "managed_work_projection":
            delivery = ManagedWorkProjectionDelivery.model_validate(record).delivery
        else:
            delivery = CandidateDeliveryEntry.model_validate(record).delivery
        if (
            delivery.request.delivery_id != delivery_id
            or delivery.request.authority.installation_id != publication.installation_id
            or delivery.request.authority.scope.partition_id != publication.repository_id
        ):
            raise ValueError("managed delivery identity differs from its inventory")
        status = delivery.progress.status
        if status in {"delivered", "rejected"}:
            continue
        if delivery.generation_id == publication.data_generation_id:
            pending += status in {"pending", "delivering"}
            held += status == "needs_reconciliation"
            continue
        # Any nonterminal prior-generation row cannot dispatch. Exclude an
        # explicit owner rejection recorded under the selected generation.
        held += delivery_id not in rejected
    # The supported outbox rows contain retry/lease deadlines, not enqueue
    # timestamps. A deadline cannot establish age.
    return QueueStatus(pending_count=pending, held_count=held)


def _selected_restore_rejections(
    connection: sqlite3.Connection, publication: RuntimePublicationState,
) -> frozenset[str]:
    from memorii.core.persistence.managed_delivery import DeliveryRestoreHold, DeliveryRestoreRejection
    from memorii.core.persistence.runtime_contracts import canonical_runtime_digest

    if not PartitionDataRepository.supports_runtime_replay_checkpoints(connection):
        return frozenset()
    holds: set[str] = set()
    rejected: list[DeliveryRestoreRejection] = []
    for key, payload, status in connection.execute(
        "SELECT hold_id, record_json, json_extract(record_json, '$.status') FROM runtime_delivery_restore_holds"
        " WHERE json_extract(record_json, '$.restored_generation_id') = ?",
        (publication.data_generation_id,),
    ):
        if status == "needs_reconciliation":
            hold = DeliveryRestoreHold.model_validate_json(payload)
            if hold.hold_id == key:
                holds.add(key)
        elif status == "rejected":
            decision = DeliveryRestoreRejection.model_validate_json(payload)
            if decision.record_id == key:
                rejected.append(decision)
    return frozenset(
        item.delivery_id for item in rejected
        if item.hold_id in holds and item.installation_id == publication.installation_id
        and item.partition_id == publication.repository_id
        and item.record_id == canonical_runtime_digest(("delivery_restore_rejection", item.hold_id, item.delivery_id))
    )

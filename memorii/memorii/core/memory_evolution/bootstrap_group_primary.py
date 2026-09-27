"""Verification of immutable native group-primary records."""

from __future__ import annotations

from hashlib import sha256

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphGroupCommitReloadV3,
    BootstrapGraphGroupCommitRequestV3,
    decode_semantic_contract,
    encode_semantic_contract,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

_PRIMARY_CONTENT_KEYS = frozenset({"semantic_ingestion_kind", "request_hex", "reload_hex"})
_PRIMARY_SOURCE_KIND = "semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
_PRIMARY_KIND = "bootstrap_graph_v3_group_commit_primary"


class BootstrapGroupPrimaryVerificationError(ValueError):
    """The immutable group-primary record is absent, corrupt, or substituted."""


def bootstrap_graph_group_commit_primary_id(
    request: BootstrapGraphGroupCommitRequestV3,
) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:group-commit:" + sha256(
        encode_typed_value((
            request.source_operation_id,
            request.transaction_group_id,
            request.operation_ids,
            request.request_ctv_digest,
        ))
    ).hexdigest()


def decode_verified_bootstrap_graph_group_commit_primary(
    record: CanonicalMemoryRecord,
    *,
    require_committed_result: bool,
) -> tuple[BootstrapGraphGroupCommitRequestV3, BootstrapGraphGroupCommitReloadV3]:
    """Return one complete native group primary only after its closed joins verify."""
    if (
        record.source_kind != _PRIMARY_SOURCE_KIND
        or record.domain != MemoryDomain.EXECUTION
        or record.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
        or record.status != CommitStatus.COMMITTED
        or set(record.content) != _PRIMARY_CONTENT_KEYS
        or record.content.get("semantic_ingestion_kind") != _PRIMARY_KIND
    ):
        raise BootstrapGroupPrimaryVerificationError("group primary metadata is invalid")
    try:
        request_raw = bytes.fromhex(record.content["request_hex"])
        reload_raw = bytes.fromhex(record.content["reload_hex"])
        request = decode_semantic_contract(
            request_raw, BootstrapGraphGroupCommitRequestV3,
        )
        reload = decode_semantic_contract(
            reload_raw, BootstrapGraphGroupCommitReloadV3,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise BootstrapGroupPrimaryVerificationError("group primary payload is invalid") from exc
    if (
        encode_semantic_contract(request) != request_raw
        or encode_semantic_contract(reload) != reload_raw
        or record.memory_id != bootstrap_graph_group_commit_primary_id(request)
        or reload.source_operation_id != request.source_operation_id
        or reload.transaction_group_id != request.transaction_group_id
        or reload.operation_ids != request.operation_ids
        or reload.request_ctv_digest != request.request_ctv_digest
        or (
            require_committed_result
            and reload.persisted_result.core.disposition != "committed"
        )
    ):
        raise BootstrapGroupPrimaryVerificationError("group primary closure is invalid")
    return request, reload

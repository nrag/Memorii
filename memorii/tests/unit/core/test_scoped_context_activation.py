from datetime import UTC, datetime, timedelta

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import MemoryPlaneCorruptionError
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.scoped_context.authority import InProcessScopedReadAuthority, ScopedNamespaceGrantRow
from memorii.core.scoped_context.contracts import (
    ScopedContextActivation,
    ScopedContextBudget,
    ScopedContextChannel,
    ScopedContextOmission,
    ScopedContextRequest,
    ScopedContextStatus,
    ScopedOmissionReason,
    ScopedRecordReference,
)
from memorii.domain.enums import CommitStatus, MemoryDomain


def _request() -> ScopedContextRequest:
    return ScopedContextRequest(
        host_task_id="task",
        host_state_id="state",
        declared_complete_mandatory_set=True,
        mandatory_record_references=(ScopedRecordReference(record_id="semantic:one", purpose="state"),),
        optional_query="context",
        optional_domains=(MemoryDomain.SEMANTIC,),
        budget=ScopedContextBudget(
            max_mandatory_items=2, max_optional_items=2, max_optional_omission_ids=2, max_rendered_utf8_bytes=1000
        ),
        reference_time=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_scoped_context_requires_authority_before_snapshot() -> None:
    service = ProviderMemoryService(memory_plane=MemoryPlaneService())
    result = service.retrieve_context(_request(), opaque_host_ingress=object())
    assert result.status.value == "denied"
    assert result.memory_snapshot_revision is None


def test_scoped_context_releases_authorized_snapshot_items() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    plane = MemoryPlaneService()
    plane.write_records(
        (
            CanonicalMemoryRecord(
                memory_id="semantic:one",
                domain=MemoryDomain.SEMANTIC,
                text="context value",
                status=CommitStatus.COMMITTED,
                task_id="task",
                source_kind="test",
            ),
        )
    )
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task",
        host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle
    )
    assert result.status.value == "complete"
    assert [item.record_id for item in result.mandatory_items] == ["semantic:one"]
    assert result.authority_binding_receipt is not None


def test_revoked_handle_denies_without_record_disclosure() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task",
        host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    authority.revoke(handle)
    result = ProviderMemoryService(scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle
    )
    assert result.status.value == "denied"
    assert result.mandatory_items == ()


def test_optional_byte_budget_omits_whole_ranked_records() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    plane = MemoryPlaneService()
    plane.write_records(
        (
            CanonicalMemoryRecord(
                memory_id="semantic:one",
                domain=MemoryDomain.SEMANTIC,
                text="context value",
                status=CommitStatus.COMMITTED,
                task_id="task",
                source_kind="test",
            ),
            CanonicalMemoryRecord(
                memory_id="semantic:two",
                domain=MemoryDomain.SEMANTIC,
                text="context " + "x" * 300,
                status=CommitStatus.COMMITTED,
                task_id="task",
                source_kind="test",
            ),
        )
    )
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task",
        host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    request = _request().model_copy(
        update={
            "budget": ScopedContextBudget(
                max_mandatory_items=2, max_optional_items=2, max_optional_omission_ids=1, max_rendered_utf8_bytes=80
            )
        }
    )
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        request, opaque_host_ingress=handle
    )
    assert result.status.value == "partial_optional"
    assert result.optional_items == ()
    assert result.omissions[0].reason.value == "rendered_byte_limit"
    assert result.omissions[0].omitted_count == 1


def test_malformed_owned_snapshot_payload_is_unavailable() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    plane = MemoryPlaneService()
    plane.write_records(
        (
            CanonicalMemoryRecord(
                memory_id="semantic:one",
                domain=MemoryDomain.SEMANTIC,
                text="context value",
                content={"memory_evolution_kind": "claim_state", "claim_state": {"bad": "payload"}},
                status=CommitStatus.COMMITTED,
                task_id="task",
                source_kind="test",
            ),
        )
    )
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task",
        host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle
    )
    assert result.status.value == "unavailable"
    assert result.memory_snapshot_revision is None


def test_request_and_failure_envelopes_reject_blank_identity_and_empty_echo() -> None:
    with pytest.raises(ValueError, match="nonblank"):
        ScopedContextRequest.model_validate(_request().model_dump() | {"host_task_id": "   "})
    with pytest.raises(ValueError, match="record_id"):
        ScopedRecordReference(record_id=" ", purpose="state")
    with pytest.raises(ValueError, match="must not disclose"):
        ScopedContextActivation(
            status=ScopedContextStatus.DENIED,
            request_task_id="",
            request_state_id=None,
            authority_binding_receipt=None,
            memory_snapshot_revision=None,
            mandatory_items=(), optional_items=(), omissions=(), structured_outcome=None,
        )


def test_snapshot_corruption_is_typed_unavailable(monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task", host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    plane = MemoryPlaneService()
    def corrupt_snapshot():
        raise MemoryPlaneCorruptionError("bad jsonl")
    monkeypatch.setattr(plane, "read_snapshot", corrupt_snapshot)
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle
    )
    assert result.status is ScopedContextStatus.UNAVAILABLE
    assert result.memory_snapshot_revision is None


def test_missing_optional_provenance_is_reported_with_capped_identifiers() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    plane = MemoryPlaneService()
    plane.write_records((
        CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="context value", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),
        CanonicalMemoryRecord(memory_id="semantic:missing-source", domain=MemoryDomain.SEMANTIC, text="context missing", status=CommitStatus.COMMITTED, task_id="task", source_kind="test", source_record_ids=("raw:missing",)),
    ))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task", host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle
    )
    omission = next(item for item in result.omissions if item.reason.value == "provenance_unavailable")
    assert omission.omitted_count == 1
    assert omission.omitted_record_ids == ("semantic:missing-source",)

    common = {
        "channel": ScopedContextChannel.SEMANTIC_BM25,
        "reason": ScopedOmissionReason.OPTIONAL_LIMIT,
    }
    assert ScopedContextOmission(
        **common, omitted_count=0, omitted_record_ids=(), identifiers_truncated=False
    ).omitted_count == 0
    assert ScopedContextOmission(
        **common, omitted_count=2, omitted_record_ids=("semantic:one",), identifiers_truncated=True
    ).omitted_record_ids == ("semantic:one",)
    with pytest.raises(ValueError, match="nonblank"):
        ScopedContextOmission(
            **common, omitted_count=1, omitted_record_ids=(" ",), identifiers_truncated=False
        )
    with pytest.raises(ValueError, match="unique"):
        ScopedContextOmission(
            **common, omitted_count=2, omitted_record_ids=("semantic:one", "semantic:one"), identifiers_truncated=False
        )
    with pytest.raises(ValueError, match="cannot be less"):
        ScopedContextOmission(
            **common, omitted_count=1, omitted_record_ids=("semantic:one", "semantic:two"), identifiers_truncated=False
        )
    with pytest.raises(ValueError, match="identifiers_truncated"):
        ScopedContextOmission(
            **common, omitted_count=2, omitted_record_ids=("semantic:one",), identifiers_truncated=False
        )
    with pytest.raises(ValueError, match="identifiers_truncated"):
        ScopedContextOmission(
            **common, omitted_count=1, omitted_record_ids=("semantic:one",), identifiers_truncated=True
        )

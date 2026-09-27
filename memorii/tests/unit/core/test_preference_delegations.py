from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, MemoryPlaneRevisionConflictError
from memorii.core.user_context.preference_delegations import (
    PreferenceDelegationRepository,
    new_preference_delegation,
)
from memorii.core.user_context.preferences import (
    PreferenceAccessPolicy,
    PreferenceHolderAuthority,
    PreferenceService,
)

NOW = datetime(2026, 9, 27, tzinfo=UTC)
EVIDENCE = ("source:grant", sha256(b"grant").hexdigest(), 0, 5)


def _service(plane: MemoryPlaneService) -> tuple[PreferenceService, PreferenceDelegationRepository]:
    repository = PreferenceDelegationRepository(plane)
    policy = PreferenceAccessPolicy(
        holder_authorities=(PreferenceHolderAuthority(holder_user_id="user:a", primary_agent_id="agent:primary"),),
        grants=(),
        delegation_repository=repository,
    )
    return (
        PreferenceService(
            memory_plane=plane,
            policy=policy,
            delegation_repository=repository,
            now=lambda: NOW,
        ),
        repository,
    )


def test_primary_grants_and_revokes_dynamic_delegate_access() -> None:
    service, repository = _service(MemoryPlaneService())
    assert not service.can_access(holder_user_id="user:a", agent_id="agent:delegate")
    active = service.set_delegation(
        holder_user_id="user:a",
        acting_agent_id="agent:primary",
        delegated_agent_id="agent:delegate",
        state="active",
        evidence=EVIDENCE,
    )
    assert active is not None and active.revision == 1
    assert repository.active("user:a", "agent:delegate")
    assert service.can_access(holder_user_id="user:a", agent_id="agent:delegate")
    assert service.set_delegation(
        holder_user_id="user:a",
        acting_agent_id="agent:delegate",
        delegated_agent_id="agent:other",
        state="active",
        evidence=EVIDENCE,
    ) is None
    revoked = service.set_delegation(
        holder_user_id="user:a",
        acting_agent_id="agent:primary",
        delegated_agent_id="agent:delegate",
        state="revoked",
        evidence=EVIDENCE,
    )
    assert revoked is not None and revoked.revision == 2
    assert not service.can_access(holder_user_id="user:a", agent_id="agent:delegate")


def test_delegation_reopen_tamper_and_stale_cas_fail_closed(tmp_path) -> None:
    root = tmp_path / "plane"
    service, repository = _service(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(root)))
    active = service.set_delegation(
        holder_user_id="user:a",
        acting_agent_id="agent:primary",
        delegated_agent_id="agent:delegate",
        state="active",
        evidence=EVIDENCE,
    )
    assert active is not None
    reopened_service, reopened = _service(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(root)))
    assert reopened_service.can_access(holder_user_id="user:a", agent_id="agent:delegate")

    replacement = new_preference_delegation(
        holder_user_id="user:a",
        primary_agent_id="agent:primary",
        delegated_agent_id="agent:delegate",
        state="revoked",
        evidence=EVIDENCE,
        occurred_at=NOW,
        previous=active,
    )
    reopened.write(replacement, previous=active)
    with pytest.raises(MemoryPlaneRevisionConflictError):
        repository.write(replacement, previous=active)

    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(root))
    stored = plane.get_record(reopened.record_id("user:a", "agent:delegate"))
    assert stored is not None
    forged = stored.model_copy(update={"content": {**stored.content, "delegation": {**stored.content["delegation"], "state": "active"}}})
    plane.write_records((forged,))
    tampered_service, tampered = _service(plane)
    assert tampered.load("user:a", "agent:delegate") is None
    assert not tampered_service.can_access(holder_user_id="user:a", agent_id="agent:delegate")

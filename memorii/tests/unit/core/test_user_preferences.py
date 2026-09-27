from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, MemoryPlaneRevisionConflictError
from memorii.core.user_context.preferences import (
    PreferenceAccessGrant,
    PreferenceAccessPolicy,
    PreferenceHolderAuthority,
    PreferenceReadRequest,
    PreferenceService,
    PreferenceWriteRequest,
)

NOW = datetime(2026, 9, 27, tzinfo=UTC)
APPROVAL_EVIDENCE = ("source:approval", sha256(b"approval").hexdigest(), 0, 8)


def request(
    value: str = "tea", source: str = "one", *, origin: str = "user_assertion", until: datetime | None = None
) -> PreferenceWriteRequest:
    return PreferenceWriteRequest(
        holder_user_id="user:a",
        authenticated_author_id="user:a",
        authenticated_source_id="source:" + source,
        authenticated_agent_id="agent:a",
        topic_type="ProductService",
        canonical_topic_id="product:tea",
        preference_key="drink",
        value=value,
        source_id="source:" + source,
        source_digest=sha256(source.encode()).hexdigest(),
        assertion_start=0,
        assertion_end=3,
        origin=origin,
        event_time=NOW,
        valid_until=until,
    )


def service(plane: MemoryPlaneService | None = None, *, now=lambda: NOW) -> PreferenceService:
    return PreferenceService(
        memory_plane=plane or MemoryPlaneService(),
        policy=PreferenceAccessPolicy(
            holder_authorities=(PreferenceHolderAuthority(holder_user_id="user:a", primary_agent_id="agent:a"),),
            grants=(
                PreferenceAccessGrant(holder_user_id="user:a", agent_id="agent:a"),
                PreferenceAccessGrant(holder_user_id="user:a", agent_id="agent:delegate", delegated=True),
                PreferenceAccessGrant(holder_user_id="user:a", agent_id="agent:nondelegate"),
            ),
        ),
        now=now,
    )


def confirm(owner: PreferenceService, candidate, *, agent_id: str = "agent:a", value: str | None = None):
    return owner.confirm(
        preference_id=candidate.preference_id,
        holder_user_id="user:a",
        agent_id=agent_id,
        preference_key=candidate.preference_key,
        value=candidate.value if value is None else value,
        source_digest=candidate.source_digest,
        approval_evidence=APPROVAL_EVIDENCE,
    )


def current(owner: PreferenceService, *, agent_id: str = "agent:a"):
    return owner.read(PreferenceReadRequest(holder_user_id="user:a", agent_id=agent_id))


def history(owner: PreferenceService, *, agent_id: str = "agent:a"):
    return owner.read(PreferenceReadRequest(holder_user_id="user:a", agent_id=agent_id, history=True))


def test_candidate_admission_abstention_coalescing_and_exact_confirmation() -> None:
    owner = service()
    candidate = owner.create_candidate(request())
    assert candidate is not None
    assert candidate.authenticated_source_id == candidate.source_id
    assert owner.create_candidate(request()) == candidate
    for origin in ("agent_summary", "inference", "third_party"):
        assert owner.create_candidate(request(origin=origin)) is None
    assert (
        owner.create_candidate(request(source="untrusted").model_copy(update={"authenticated_author_id": "user:b"}))
        is None
    )
    assert (
        owner.create_candidate(
            request(source="untrusted").model_copy(update={"authenticated_source_id": "source:other"})
        )
        is None
    )

    assert confirm(owner, candidate, value="coffee") is None
    assert (
        owner.confirm(
            preference_id=candidate.preference_id,
            holder_user_id="user:a",
            agent_id="agent:a",
            preference_key=candidate.preference_key,
            value=candidate.value,
            source_digest=sha256(b"substituted").hexdigest(),
        )
        is None
    )
    assert current(owner) == ()
    confirmed = confirm(owner, candidate)
    assert confirmed is not None
    assert current(owner) == (confirmed,)
    rejected_candidate = owner.create_candidate(request("coffee", "rejected"))
    assert rejected_candidate is not None
    rejected = owner.close(
        preference_id=rejected_candidate.preference_id,
        holder_user_id="user:a",
        agent_id="agent:a",
        preference_key=rejected_candidate.preference_key,
        value=rejected_candidate.value,
        source_digest=rejected_candidate.source_digest,
        state="rejected",
        evidence=APPROVAL_EVIDENCE,
    )
    assert rejected is not None and rejected.state == "rejected"


def test_correction_atomically_supersedes_prior_current_and_history_is_protected() -> None:
    owner = service()
    original = owner.create_candidate(request())
    assert original is not None
    first = confirm(owner, original)
    assert first is not None
    replacement = owner.create_candidate(request("coffee", "two"))
    assert replacement is not None
    assert replacement.predecessor_id == first.preference_id
    second = confirm(owner, replacement)
    assert second is not None
    assert second.predecessor_id == first.preference_id
    assert current(owner) == (second,)
    assert [(item.preference_id, item.state) for item in history(owner)] == [
        (first.preference_id, "superseded"),
        (second.preference_id, "confirmed"),
    ]
    assert history(owner, agent_id="agent:delegate") == history(owner)
    assert current(owner, agent_id="agent:nondelegate") == ()
    assert current(owner, agent_id="agent:no") == ()
    assert owner.read(PreferenceReadRequest(holder_user_id="user:b", agent_id="agent:a", history=True)) == ()


def test_expiry_requires_explicit_valid_until_and_retraction_requires_confirmed_revocation() -> None:
    clock = [NOW]
    owner = service(now=lambda: clock[0])
    expiring = owner.create_candidate(request(until=NOW + timedelta(minutes=1)))
    assert expiring is not None
    clock[0] += timedelta(minutes=2)
    assert (
        owner.close(
            preference_id=expiring.preference_id,
            holder_user_id="user:a",
            agent_id="agent:a",
            preference_key=expiring.preference_key,
            value=expiring.value,
            source_digest=expiring.source_digest,
            state="expired",
            evidence=APPROVAL_EVIDENCE,
        )
        is None
    )
    clock[0] = NOW
    expiring_confirmed = confirm(owner, expiring)
    assert expiring_confirmed is not None
    assert (
        owner.close(
            preference_id=expiring_confirmed.preference_id,
            holder_user_id="user:a",
            agent_id="agent:a",
            preference_key=expiring_confirmed.preference_key,
            value=expiring_confirmed.value,
            source_digest=expiring_confirmed.source_digest,
            state="expired",
            evidence=APPROVAL_EVIDENCE,
        )
        is None
    )
    clock[0] += timedelta(minutes=2)
    expired = owner.close(
        preference_id=expiring_confirmed.preference_id,
        holder_user_id="user:a",
        agent_id="agent:a",
        preference_key=expiring_confirmed.preference_key,
        value=expiring_confirmed.value,
        source_digest=expiring_confirmed.source_digest,
        state="expired",
        evidence=APPROVAL_EVIDENCE,
    )
    assert expired is not None and expired.state == "expired"

    retained = owner.create_candidate(request("coffee", "two"))
    assert retained is not None
    retained_confirmed = confirm(owner, retained)
    assert retained_confirmed is not None
    retracted = owner.close(
        preference_id=retained_confirmed.preference_id,
        holder_user_id="user:a",
        agent_id="agent:a",
        preference_key=retained_confirmed.preference_key,
        value=retained_confirmed.value,
        source_digest=retained_confirmed.source_digest,
        state="retracted",
        evidence=APPROVAL_EVIDENCE,
    )
    assert retracted is not None and retracted.state == "retracted"
    assert current(owner) == ()
    assert {item.state for item in history(owner)} == {"expired", "retracted"}


def test_stale_write_is_rejected_by_conditional_precondition() -> None:
    owner = service()
    candidate = owner.create_candidate(request())
    assert candidate is not None
    assert confirm(owner, candidate) is not None
    stale_candidate = candidate.model_copy(update={"value": "coffee"})
    with pytest.raises(MemoryPlaneRevisionConflictError, match="record_digest"):
        owner._write(
            stale_candidate,
            predecessor=candidate,
            events=(owner._event(stale_candidate, event_type="confirmed", actor_id="agent:a"),),
        )


def test_tampered_state_and_event_digests_fail_closed() -> None:
    plane = MemoryPlaneService()
    owner = service(plane)
    candidate = owner.create_candidate(request())
    assert candidate is not None
    confirmed = confirm(owner, candidate)
    assert confirmed is not None

    state_record = plane.get_record(confirmed.preference_id)
    assert state_record is not None
    tampered_preference = {**state_record.content["preference"], "record_digest": "0" * 64}
    plane.write_records(
        (state_record.model_copy(update={"content": {**state_record.content, "preference": tampered_preference}}),)
    )
    assert current(owner) == ()

    event = owner.read_events(PreferenceReadRequest(holder_user_id="user:a", agent_id="agent:a"))[0]
    event_record = plane.get_record(event.event_id)
    assert event_record is not None
    tampered_event = {**event_record.content["event"], "event_digest": "0" * 64}
    plane.write_records(
        (event_record.model_copy(update={"content": {**event_record.content, "event": tampered_event}}),)
    )
    assert event not in owner.read_events(PreferenceReadRequest(holder_user_id="user:a", agent_id="agent:a"))


def test_jsonl_reopen_preserves_protected_current_and_history(tmp_path) -> None:
    path = tmp_path / "preferences"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    owner = service(plane)
    candidate = owner.create_candidate(request())
    assert candidate is not None
    confirmed = confirm(owner, candidate)
    assert confirmed is not None
    correction_candidate = owner.create_candidate(request("coffee", "correction"))
    assert correction_candidate is not None
    corrected = confirm(owner, correction_candidate)
    assert corrected is not None
    reopened = service(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    assert current(reopened) == (corrected,)
    assert {item.state for item in history(reopened)} == {"confirmed", "superseded"}
    assert {
        event.event_type
        for event in reopened.read_events(PreferenceReadRequest(holder_user_id="user:a", agent_id="agent:a"))
    } == {
        "candidate_observed",
        "confirmed",
        "superseded",
    }

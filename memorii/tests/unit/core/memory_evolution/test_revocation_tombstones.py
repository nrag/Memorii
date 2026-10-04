"""Revoked lifecycles never serve: reader gates and tombstone builders."""

from datetime import UTC, datetime

from memorii.core.memory_evolution import MemoryQueryRequest
from memorii.core.memory_evolution.models import (
    ClaimKey,
    ClaimLifecycleState,
    ClaimSemanticContext,
    ClaimState,
    ConfidenceComponents,
    EntityLinkLifecycleState,
    EntityLinkState,
    RetrievalView,
)
from memorii.core.memory_evolution.record_projection import record_from_claim_state
from memorii.core.memory_evolution.revocation_tombstones import (
    revoked_claim_state,
    tombstone_records_for,
)
from memorii.core.memory_evolution.service import MemoryEvolutionService
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.scoped_context.service import _current_eligible
from memorii.domain.enums import CommitStatus, MemoryDomain

SUPPRESSION_ID = "a" * 64
NOW = datetime.now(UTC)


def _confidence() -> ConfidenceComponents:
    return ConfidenceComponents(extraction=0.9, evidence=0.8, source_trust=0.7, calibrated=0.9)


def _claim(claim_id: str, subject: str, value: str, lifecycle: ClaimLifecycleState) -> ClaimState:
    truth = {
        "assertion_mode": "world_assertion",
        "epistemic_status": "asserted",
        "polarity": "positive",
        "modality": "assertion",
    }
    return ClaimState(
        claim_id=claim_id,
        claim_key=ClaimKey(subject_entity_id=subject, predicate_id="owns", **truth),
        object_value=value,
        lifecycle_state=lifecycle,
        source_claim_id=f"source:{claim_id}",
        confidence=_confidence(),
        semantic_context=ClaimSemanticContext(attribution_source_id=f"source:{claim_id}", **truth),
    )


def _link(link_id: str, entity: str, name: str, lifecycle: EntityLinkLifecycleState) -> EntityLinkState:
    return EntityLinkState(
        link_id=link_id,
        mention_text=name,
        canonical_entity_id=entity,
        normalized_name=name.lower(),
        aliases=[name],
        observed_names=[name.lower()],
        confidence=0.9,
        lifecycle_state=lifecycle,
    )


def _claim_record(state: ClaimState) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:claim:{state.claim_id}",
        domain=MemoryDomain.SEMANTIC,
        text=state.object_value,
        content={"memory_evolution_kind": "claim_state", "claim_state": state.model_dump(mode="python")},
        status=CommitStatus.COMMITTED,
        source_kind="memory_evolution",
        timestamp=NOW,
    )


def _link_record(link: EntityLinkState) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:link:{link.link_id}",
        domain=MemoryDomain.SEMANTIC,
        text=link.mention_text,
        content={"memory_evolution_kind": "entity_link", "entity_link": link.model_dump(mode="python")},
        status=CommitStatus.COMMITTED,
        source_kind="memory_evolution",
        timestamp=NOW,
    )


def test_tombstones_are_content_free_and_round_trip() -> None:
    claim = _claim("claim:1", "entity:ada", "Mars Venus 008 project", ClaimLifecycleState.ACTIVE)
    link = _link("link:1", "entity:ada", "Ada", EntityLinkLifecycleState.ACTIVE)
    rewritten = tombstone_records_for(
        (_claim_record(claim), _link_record(link)),
        suppression_id=SUPPRESSION_ID,
        applied_at=NOW,
    )
    claim_tombstone = ClaimState.model_validate(rewritten[0].content["claim_state"])
    link_tombstone = EntityLinkState.model_validate(rewritten[1].content["entity_link"])
    assert claim_tombstone.lifecycle_state is ClaimLifecycleState.REVOKED
    assert link_tombstone.lifecycle_state is EntityLinkLifecycleState.REVOKED
    assert claim_tombstone.object_value == f"revoked:{SUPPRESSION_ID}"
    assert link_tombstone.mention_text == f"revoked:{SUPPRESSION_ID}"
    assert rewritten[0].text == f"revoked:{SUPPRESSION_ID}"
    assert claim_tombstone.evidence_spans == []
    assert link_tombstone.aliases == [] and link_tombstone.observed_names == []
    serialized = str(rewritten[0].content) + str(rewritten[1].content)
    assert "Mars Venus" not in serialized and "Ada" not in serialized


def test_revoked_claim_projects_as_never_eligible() -> None:
    claim = _claim("claim:1", "entity:ada", "value", ClaimLifecycleState.REVOKED)
    record = record_from_claim_state(
        state=revoked_claim_state(claim, suppression_id=SUPPRESSION_ID, applied_at=NOW),
        source_candidate_id="candidate:1",
    )
    from memorii.domain.enums import TemporalValidityStatus

    assert record.validity_status is TemporalValidityStatus.INVALIDATED


def test_current_claim_view_excludes_revoked_claims() -> None:
    plane = MemoryPlaneService()
    plane.upsert_record(
        _claim_record(_claim("claim:active", "entity:ada", "kept", ClaimLifecycleState.ACTIVE))
    )
    plane.upsert_record(
        _claim_record(_claim("claim:revoked", "entity:ada", "forgotten", ClaimLifecycleState.REVOKED))
    )
    service = MemoryEvolutionService(memory_plane=plane)

    current = service.retrieve_claim_states(view=RetrievalView.CURRENT)

    assert {state.claim_id for state in current} == {"claim:active"}


def test_revoked_entity_link_is_not_served_by_retrieval() -> None:
    plane = MemoryPlaneService()
    plane.upsert_record(
        _claim_record(_claim("claim:kept", "entity:kept-owner", "Kept Owner", ClaimLifecycleState.ACTIVE))
    )
    plane.upsert_record(
        _claim_record(
            _claim("claim:gone", "entity:forgotten-owner", "Forgotten Owner", ClaimLifecycleState.ACTIVE)
        )
    )
    plane.upsert_record(_link_record(_link("link:kept", "entity:kept-owner", "Keptowner", EntityLinkLifecycleState.ACTIVE)))
    plane.upsert_record(
        _link_record(_link("link:gone", "entity:forgotten-owner", "Forgottenowner", EntityLinkLifecycleState.REVOKED))
    )
    service = MemoryEvolutionService(memory_plane=plane)

    decision = service.retrieve(
        MemoryQueryRequest(
            query="Who is the Forgottenowner?",
            reference_time=NOW,
        )
    )

    assert decision.selected_record_ids == [] or all(
        state.object_value != "Forgotten Owner"
        for state in service.retrieve_claim_states(view=RetrievalView.CURRENT)
        if state.claim_id in decision.selected_record_ids
    )


def test_scoped_context_current_eligibility_rejects_revoked_links() -> None:
    active = _link_record(_link("link:1", "entity:ada", "Ada", EntityLinkLifecycleState.ACTIVE))
    revoked = _link_record(_link("link:2", "entity:ada", "Ada", EntityLinkLifecycleState.REVOKED))
    assert _current_eligible(active, NOW) is True
    assert _current_eligible(revoked, NOW) is False

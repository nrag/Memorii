"""Canonical memory-plane projections for memory-evolution state."""

from __future__ import annotations

import base64
from hashlib import sha256

from memorii.core.memory_evolution.admission import source_admission_source_digest
from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value
from memorii.core.memory_evolution.models import (
    ClaimLifecycleState,
    ClaimState,
    ContradictionSet,
    EntityLinkState,
    SourceModality,
    SourceObservation,
)
from memorii.core.memory_evolution.temporal_contracts import TemporalAnchor
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain, SourceType, TemporalValidityStatus


def source_observation_from_record(record: CanonicalMemoryRecord) -> SourceObservation:
    governed = record.source_kind in {
        "semantic_ingestion_source",
        "semantic_ingestion_metadata_poor_snapshot",
    }
    delivery_key_digest = (
        record.memory_id.removeprefix("semantic_ingestion:source:")
        if governed and record.memory_id.startswith("semantic_ingestion:source:")
        else None
    )
    step_one = _step_one_observation_fields(record) if governed else {}
    return SourceObservation(
        source_id=record.memory_id,
        text=record.text,
        source_type=source_type_from_record(record),
        timestamp=record.timestamp,
        domain=record.domain,
        session_id=record.session_id,
        task_id=record.task_id,
        user_id=record.user_id,
        language=record.language,
        speaker_id=_declared_source_speaker_from_record(record),
        source_digest=source_admission_source_digest(record) if governed else None,
        delivery_key_digest=delivery_key_digest,
        **step_one,
    )


def _step_one_observation_fields(record: CanonicalMemoryRecord) -> dict[str, object]:
    """Reload the sealed Step-1 payload; older source records remain legacy."""

    admission = record.content.get("source_admission")
    if not isinstance(admission, dict):
        return {}
    encoded_material = admission.get("step_one_material_ctv")
    if not isinstance(encoded_material, str):
        return {}
    try:
        material = decode_typed_value(base64.b64decode(encoded_material, validate=True))
    except (ValueError, TypeError) as exc:
        raise ValueError("persisted Step-1 source observation payload is invalid") from exc
    if not isinstance(material, dict):
        raise ValueError("persisted Step-1 source observation payload is invalid")
    from memorii.core.memory_evolution.bootstrap_profile import (
        BootstrapAuthenticatedLanguageEvidence,
    )
    from memorii.core.memory_evolution.source_governance import AdmissionScopeAuthorizationProof
    from memorii.core.semantic_ingestion.contracts import (
        GovernanceCarrierArtifact,
        MessageAdmissionCarrierSet,
        RequiredOutcomeScopeSet,
        SegmentGovernanceCarrierSet,
        SourceSemanticContext,
        SourceSemanticTextProjection,
        _restore_closed_wire_enums,
    )

    material = _restore_closed_wire_enums(material)

    try:
        values = {
            "required_outcome_scopes": RequiredOutcomeScopeSet.model_validate(material["required_outcome_scopes"]),
            "semantic_context": SourceSemanticContext.model_validate(material["semantic_context"]),
            "semantic_text_projection": SourceSemanticTextProjection.model_validate(material["semantic_text_projection"]),
            "segment_governance_carriers": SegmentGovernanceCarrierSet.model_validate(material["segment_governance_carriers"]),
            "message_admission_carriers": MessageAdmissionCarrierSet.model_validate(material["message_admission_carriers"]),
            "governance_carrier_artifact": GovernanceCarrierArtifact.model_validate(material["governance_carrier_artifact"]),
            "admission_scope_authorization_proof": AdmissionScopeAuthorizationProof.model_validate(
                material["admission_scope_authorization_proof"]
            ),
            "bootstrap_language_evidence": (
                None
                if admission.get("bootstrap_language_evidence") is None
                else BootstrapAuthenticatedLanguageEvidence.model_validate(admission["bootstrap_language_evidence"])
            ),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("persisted Step-1 source observation is invalid") from exc
    source_digest = source_admission_source_digest(record)
    context = values["semantic_context"]
    projection = values["semantic_text_projection"]
    if (
        context.source_id != record.memory_id
        or context.source_digest != source_digest
        or projection.retained_source_digest != source_digest
        or projection.retained_text_artifact.content_digest
        != sha256(record.text.encode("utf-8")).hexdigest()
        or (
            values["bootstrap_language_evidence"] is not None
            and (
                values["bootstrap_language_evidence"].source_id != record.memory_id
                or values["bootstrap_language_evidence"].source_digest != source_digest
            )
        )
    ):
        raise ValueError("persisted Step-1 source observation is substituted")
    values["retained_text_artifact"] = projection.retained_text_artifact
    return values


def declared_source_modality_from_record(
    record: CanonicalMemoryRecord,
) -> SourceModality | None:
    value = record.content.get("source_modality")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("declared source modality must be a string")
    try:
        return SourceModality(value)
    except ValueError as exc:
        raise ValueError(f"unknown declared source modality: {value!r}") from exc


def _declared_source_speaker_from_record(record: CanonicalMemoryRecord) -> str | None:
    value = record.content.get("source_speaker_id")
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("declared source speaker must be a non-empty string")
    return value


def record_from_entity_link(link: EntityLinkState) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:entity-link:{link.link_id}",
        domain=MemoryDomain.SEMANTIC,
        text=f"{link.canonical_entity_id} aliases: {', '.join(link.aliases)}",
        content={
            "memory_evolution_kind": "entity_link",
            "entity_link": link.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=TemporalValidityStatus.ACTIVE,
        source_kind="memory_evolution",
        timestamp=link.updated_at,
        task_id=link.scope.task_id,
        session_id=link.scope.session_id,
        user_id=link.scope.user_id,
    )


def record_from_temporal_anchor(anchor: TemporalAnchor) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:temporal-anchor:{anchor.anchor_id}",
        domain=MemoryDomain.SEMANTIC,
        text=f"Temporal anchor {anchor.anchor_id}: {', '.join(anchor.names)}",
        content={
            "memory_evolution_kind": "temporal_anchor",
            "temporal_anchor": anchor.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=TemporalValidityStatus.ACTIVE,
        source_kind="memory_evolution",
        timestamp=anchor.valid_to,
        task_id=anchor.scope.task_id,
        session_id=anchor.scope.session_id,
        user_id=anchor.scope.user_id,
    )


def record_from_claim_state(*, state: ClaimState, source_candidate_id: str) -> CanonicalMemoryRecord:
    validity = {
        ClaimLifecycleState.ACTIVE: TemporalValidityStatus.ACTIVE,
        ClaimLifecycleState.EXPIRED: TemporalValidityStatus.EXPIRED,
        ClaimLifecycleState.SUPERSEDED: TemporalValidityStatus.INVALIDATED,
        ClaimLifecycleState.INVALIDATED: TemporalValidityStatus.INVALIDATED,
        ClaimLifecycleState.ARCHIVED: TemporalValidityStatus.INVALIDATED,
        ClaimLifecycleState.CANDIDATE: TemporalValidityStatus.UNKNOWN,
    }[state.lifecycle_state]
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:claim:{state.claim_id}",
        domain=domain_for_predicate(state.claim_key.predicate_id),
        text=f"{state.claim_key.subject_entity_id} {state.claim_key.predicate_id} is {state.object_value}",
        content={
            "memory_evolution_kind": "claim_state",
            "claim_state": state.model_dump(mode="json"),
            "claim_key": state.claim_key.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=validity,
        source_kind="memory_evolution",
        timestamp=state.updated_at,
        valid_from=state.valid_from,
        valid_to=state.valid_to,
        task_id=state.claim_key.scope.task_id,
        session_id=state.claim_key.scope.session_id,
        user_id=state.claim_key.scope.user_id,
        source_record_ids=sorted({span.source_id for span in state.evidence_spans}),
        source_candidate_id=source_candidate_id,
        supersedes_memory_ids=[f"mem:evolution:claim:{claim_id}" for claim_id in state.supersedes_claim_ids],
        conflict_with_memory_ids=[f"mem:evolution:claim:{claim_id}" for claim_id in state.conflict_with_claim_ids],
    )


def record_from_contradiction_set(contradiction_set: ContradictionSet) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:contradiction:{contradiction_set.contradiction_set_id}",
        domain=MemoryDomain.SEMANTIC,
        text=f"Contradiction for {contradiction_set.claim_key.stable_id()}",
        content={
            "memory_evolution_kind": "contradiction_set",
            "contradiction_set": contradiction_set.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=TemporalValidityStatus.ACTIVE,
        source_kind="memory_evolution",
        timestamp=contradiction_set.updated_at,
        task_id=contradiction_set.claim_key.scope.task_id,
        session_id=contradiction_set.claim_key.scope.session_id,
        user_id=contradiction_set.claim_key.scope.user_id,
    )


def source_type_from_record(record: CanonicalMemoryRecord) -> SourceType:
    source_kind = record.source_kind.lower()
    operation = str(record.content.get("operation") or "").lower()
    if operation in {"memory_write_longterm", "memory_write_user", "memory_write_dailylog"}:
        return SourceType.USER
    if operation == "delegation_result":
        return SourceType.TOOL
    if "user" in source_kind:
        return SourceType.USER
    if "tool" in source_kind:
        return SourceType.TOOL
    if "environment" in source_kind:
        return SourceType.ENVIRONMENT
    if "agent" in source_kind:
        return SourceType.AGENT
    if "system" in source_kind:
        return SourceType.SYSTEM
    return SourceType.DERIVED


def domain_for_predicate(predicate_id: str) -> MemoryDomain:
    if predicate_id == "preference":
        return MemoryDomain.USER
    if predicate_id == "action_state":
        return MemoryDomain.EXECUTION
    return MemoryDomain.SEMANTIC

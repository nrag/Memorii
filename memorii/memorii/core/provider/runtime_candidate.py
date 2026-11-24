"""Provider-owned staging shapes for accepted managed writeback offers."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from memorii.core.consolidation.runtime_outputs import (
    BoundedText,
    ConsolidationResult,
    EpisodicSummary,
    SemanticCandidate,
    SkillCandidate,
    SourceReferences,
    UserCandidate,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import record_digest
from memorii.core.persistence.contracts import canonical_json_digest
from memorii.core.persistence.managed_delivery import (
    DeliveryAuthorityBinding,
    MemoryPlaneCandidateScope,
    ProtectedSkillCandidateScope,
)
from memorii.core.storage_administration.revoked_identity_view import RevokedIdentityServingGate
from memorii.domain.enums import (
    CommitStatus,
    MemoryDomain,
    MemoryRecordVisibility,
    TemporalValidityStatus,
)

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CandidateTargetScope = Annotated[
    MemoryPlaneCandidateScope | ProtectedSkillCandidateScope, Field(discriminator="kind")
]


class CandidateStageError(RuntimeError):
    """A sealed accepted offer cannot be staged under current provider policy."""


class AcceptedCandidateOffer(BaseModel):
    """Projection of a verified signed acceptance, never an authorization token."""

    decision_id: Digest
    result_id: Digest
    output_id: Digest
    payload_digest: Digest
    accepted_at: AwareDatetime
    offer_version: Literal[2] = 2
    target_scope: CandidateTargetScope

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class ProtectedSkillCandidate(BaseModel):
    """Protected derived skill artifact with no memory-domain assignment."""

    candidate_id: BoundedText
    output_id: Digest
    originating_result_id: Digest
    origin_revision: int = Field(ge=1)
    scope: ProtectedSkillCandidateScope
    title: BoundedText
    summary: BoundedText
    ordered_steps: tuple[BoundedText, ...] = Field(min_length=1, max_length=32)
    source_refs: SourceReferences
    provenance: Literal["derived"] = "derived"

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    def digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))


def prepare_candidate_stage(
    *,
    result: ConsolidationResult,
    acceptance: AcceptedCandidateOffer,
    authority: DeliveryAuthorityBinding,
    current_sources: tuple[CanonicalMemoryRecord, ...],
    revoked: RevokedIdentityServingGate,
    now: datetime,
) -> CanonicalMemoryRecord | ProtectedSkillCandidate:
    """Derive an inert staging record from verified inputs, without writing it.

    The caller owns verifying the signed acceptance and current grant and
    loading source rows inside its publication transaction. This function
    verifies closure against those inputs. It cannot make an accepted claim
    out of an offer or publish an effect or a target receipt.
    """
    if now.utcoffset() is None:
        raise CandidateStageError("invalid_request: candidate stage time must be timezone-aware")
    result = ConsolidationResult.model_validate(result)
    scope = acceptance.target_scope
    if (
        acceptance.result_id != result.result_id
        or scope.partition_id != result.origin.partition_id
        or scope.task_id != result.origin.task_id
        or authority.installation_id != result.origin.installation_id
        or authority.scope != scope
    ):
        raise CandidateStageError("denied: candidate acceptance does not match its authorized origin")
    if revoked.is_revoked_task(scope.task_id):
        raise CandidateStageError("denied: candidate task is suppressed")
    output = next((item for item in result.outputs if item.output_id == acceptance.output_id), None)
    if output is None or output.payload_digest != acceptance.payload_digest:
        raise CandidateStageError("integrity_error: accepted output does not match sealed result")
    payload = output.payload
    if not isinstance(payload, EpisodicSummary | SkillCandidate | SemanticCandidate | UserCandidate):
        raise CandidateStageError("invalid_request: selected output is not a candidate")
    if payload.source_refs != authority.source_refs:
        raise CandidateStageError("denied: sealed source closure differs from delivery authority")
    if not isinstance(payload, EpisodicSummary) and not payload.source_refs:
        raise CandidateStageError("denied: candidate requires retained source evidence")
    _require_eligible_sources(authority, payload.source_refs, current_sources, revoked, now=now)

    candidate_id = f"cand:runtime:{output.output_id}"
    if revoked.is_revoked_record(candidate_id):
        raise CandidateStageError("denied: candidate record is suppressed")
    if isinstance(payload, SkillCandidate):
        if not isinstance(scope, ProtectedSkillCandidateScope):
            raise CandidateStageError("denied: skill candidate requires its protected target")
        return ProtectedSkillCandidate(
            candidate_id=candidate_id,
            output_id=output.output_id,
            originating_result_id=result.result_id,
            origin_revision=result.origin_revision,
            scope=scope,
            title=payload.title,
            summary=payload.summary,
            ordered_steps=payload.steps,
            source_refs=payload.source_refs,
        )

    domain, text = _memory_content(payload)
    if not isinstance(scope, MemoryPlaneCandidateScope) or scope.domain != domain.value:
        raise CandidateStageError("denied: candidate domain does not match exact target scope")
    return CanonicalMemoryRecord(
        memory_id=candidate_id,
        domain=domain,
        text=text,
        content={
            "consolidation_result_id": result.result_id,
            "consolidation_output_id": output.output_id,
            "origin_revision": result.origin_revision,
            "decision_id": acceptance.decision_id,
            "provenance": payload.provenance,
        },
        status=CommitStatus.CANDIDATE,
        source_kind="runtime_writeback_candidate",
        timestamp=acceptance.accepted_at,
        valid_from=payload.valid_from if isinstance(payload, UserCandidate) else None,
        valid_to=payload.valid_to if isinstance(payload, UserCandidate) else None,
        task_id=scope.task_id,
        user_id=authority.principal,
        solver_run_id=payload.solver_run_id,
        execution_node_id=payload.execution_node_id,
        is_raw_event=False,
        source_record_ids=[ref.source_id for ref in payload.source_refs],
        promotion_state="staged",
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _memory_content(
    payload: EpisodicSummary | SemanticCandidate | UserCandidate,
) -> tuple[MemoryDomain, str]:
    if isinstance(payload, EpisodicSummary):
        return MemoryDomain.EPISODIC, payload.summary
    if isinstance(payload, SemanticCandidate):
        return MemoryDomain.SEMANTIC, payload.abstraction
    return MemoryDomain.USER, payload.preference


def _require_eligible_sources(
    authority: DeliveryAuthorityBinding,
    refs: SourceReferences,
    records: tuple[CanonicalMemoryRecord, ...],
    revoked: RevokedIdentityServingGate,
    *,
    now: datetime,
) -> None:
    by_id = {record.memory_id: record for record in records}
    if len(by_id) != len(records) or set(by_id) != {ref.source_id for ref in refs}:
        raise CandidateStageError("denied: candidate source closure is not complete")
    for ref in refs:
        record = by_id[ref.source_id]
        if (
            record.user_id != authority.principal
            or record.task_id != authority.scope.task_id
            or record.status != CommitStatus.COMMITTED
            or record.visibility != MemoryRecordVisibility.RUNTIME_CONTEXT
            or record.validity_status in (TemporalValidityStatus.EXPIRED, TemporalValidityStatus.INVALIDATED)
            or (record.valid_from is not None and (record.valid_from.utcoffset() is None or now < record.valid_from))
            or (record.valid_to is not None and (record.valid_to.utcoffset() is None or now >= record.valid_to))
            or revoked.is_revoked_source(ref.source_id)
            or revoked.is_revoked_record(ref.source_id)
            or not revoked.keeps_record(record)
            or record_digest(record) != ref.source_digest
        ):
            raise CandidateStageError("denied: candidate source is no longer eligible")

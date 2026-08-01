"""Recoverable provider ingestion composed with default-on memory evolution."""

from __future__ import annotations

from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService
from memorii.core.memory_evolution.bootstrap_profile import VerifiedBootstrapProfile, classify_bootstrap_input
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedIngressContext, DeliveryIdentity
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.provider.models import ProviderEvent, ProviderEvolutionOutcome, ProviderSyncResult
from memorii.domain.enums import MemoryRecordVisibility


class ProviderIngestionCoordinator:
    def __init__(
        self,
        *,
        memory_plane: MemoryPlaneService,
        admission_service: GovernedSourceAdmissionService,
        bootstrap_profile: VerifiedBootstrapProfile | None,
        bootstrap_unavailable_reason: str,
    ) -> None:
        self._memory_plane = memory_plane
        self._admission_service = admission_service
        self._bootstrap_profile = bootstrap_profile
        self._bootstrap_unavailable_reason = bootstrap_unavailable_reason

    def ingest(
        self,
        event: ProviderEvent,
        *,
        defer_assertions: bool = False,
        authenticated_ingress: AuthenticatedIngressContext | None = None,
    ) -> tuple[ProviderSyncResult, None, None]:
        result, source_records = self._memory_plane.prepare_provider_event(event)
        metadata_poor = event.operation.value in {"session_end", "pre_compress"}
        if metadata_poor:
            # Metadata-poor events are evidence-only, but still require the
            # same authenticated governed-admission boundary as every M1 input.
            if authenticated_ingress is None:
                return (
                    result.model_copy(update={"transcript_ids": [], "candidate_ids": [], "allowed_candidate_domains": [], "blocked_reasons": {**result.blocked_reasons, "semantic_ingestion": "ingress_unavailable"}}),
                    None,
                    None,
                )
            raw_sources = tuple(record for record in source_records if record.is_raw_event)
            if len(raw_sources) != 1:
                raise RuntimeError("governed provider admission requires one raw source")
            identity = DeliveryIdentity.create(authenticated_ingress.delivery_principal_binding, event.event_id)
            outcome = "unavailable"
            reason = self._bootstrap_unavailable_reason
            if self._bootstrap_profile is not None:
                if self._bootstrap_profile.enabled:
                    outcome = "abstained"
                    reason = "extractor_abstained"
                else:
                    outcome = "disabled"
                    reason = "operator_disabled"
            self._admission_service.admit(
                source=_governed_source(raw_sources[0], identity, metadata_poor=True),
                delivery_identity=identity,
                ingress=authenticated_ingress,
                operation_id=event.event_id,
                outcome_kind=outcome,
                outcome_reason=reason,
                normalized_input=(event.content or "").encode("utf-8"),
                evidence_only=True,
                selection_digest=(self._bootstrap_profile.selection_digest if self._bootstrap_profile else None),
                verification_digest=(self._bootstrap_profile.verification_digest if self._bootstrap_profile else None),
            )
            return (
                result.model_copy(update={"transcript_ids": [f"semantic_ingestion:source:{identity.delivery_key_digest}"], "candidate_ids": [], "allowed_candidate_domains": [], "blocked_reasons": {**result.blocked_reasons, "semantic_ingestion": "source_only"}}),
                None,
                None,
            )
        if authenticated_ingress is None:
            return (
                result.model_copy(
                    update={
                        "transcript_ids": [],
                        "candidate_ids": [],
                        "allowed_candidate_domains": [],
                        "blocked_reasons": {**result.blocked_reasons, "semantic_ingestion": "ingress_unavailable"},
                    }
                ),
                None,
                None,
            )
        raw_sources = tuple(record for record in source_records if record.is_raw_event)
        if len(raw_sources) != 1:
            raise RuntimeError("governed provider admission requires one raw source")
        identity = DeliveryIdentity.create(authenticated_ingress.delivery_principal_binding, event.event_id)
        governed_source = _governed_source(raw_sources[0], identity)
        outcome = "unavailable"
        reason = self._bootstrap_unavailable_reason
        matched_case_id = None
        if self._bootstrap_profile is not None:
            outcome, reason, matched_case_id = classify_bootstrap_input(
                profile=self._bootstrap_profile,
                ingress=authenticated_ingress,
                normalized_segment=(event.content or "").encode("utf-8"),
            )
        self._admission_service.admit(
            source=governed_source,
            delivery_identity=identity,
            ingress=authenticated_ingress,
            operation_id=event.event_id,
            outcome_kind=outcome,
            outcome_reason=reason,
            normalized_input=(event.content or "").encode("utf-8"),
            matched_corpus_case_id=matched_case_id,
            selection_digest=(self._bootstrap_profile.selection_digest if self._bootstrap_profile else None),
            verification_digest=(self._bootstrap_profile.verification_digest if self._bootstrap_profile else None),
        )
        return (result.model_copy(update={"transcript_ids": [governed_source.memory_id], "candidate_ids": [], "allowed_candidate_domains": [], "blocked_reasons": {**result.blocked_reasons, "semantic_ingestion": "source_only"}}), None, None)

    def reconcile(self) -> list[ProviderEvolutionOutcome]:
        return []


def _governed_source(
    source: CanonicalMemoryRecord,
    identity: DeliveryIdentity,
    *,
    metadata_poor: bool = False,
) -> CanonicalMemoryRecord:
    update: dict[str, object] = {
        "memory_id": f"semantic_ingestion:source:{identity.delivery_key_digest}",
        "source_kind": "semantic_ingestion_source",
        "visibility": MemoryRecordVisibility.INTERNAL_CONTROL,
    }
    if metadata_poor:
        update.update(
            {
                "source_kind": "semantic_ingestion_metadata_poor_snapshot",
                "text": "",
                "content": {
                    "schema_version": 1,
                    "source_kind": "conversation_snapshot",
                    "snapshot_utf8_bytes": source.text.encode("utf-8"),
                    "hook_kind": source.content.get("operation"),
                    "reason": "missing_message_governance",
                },
                "role": None,
                "session_id": None,
                "task_id": None,
                "user_id": None,
                "language": "und",
            }
        )
    return source.model_copy(update=update)

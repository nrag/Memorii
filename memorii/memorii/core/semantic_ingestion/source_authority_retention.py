"""Retain authenticated source authority required for process-loss recovery."""

from __future__ import annotations

from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedIngressContext
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.semantic_ingestion.contracts import (
    AuthenticatedSourceIntervalEvidence,
    SourceAuthority,
    SourceAuthorityEvidence,
    TimeInterval,
)


def retain_source_authority_evidence(
    *,
    source: CanonicalMemoryRecord,
    source_id: str,
    source_digest: str,
    ingress: AuthenticatedIngressContext,
) -> CanonicalMemoryRecord:
    """Seal typed ingress and source authority into an admitted source."""

    metadata = ingress.semantic_source_authority
    if metadata is None:
        raise ValueError("semantic source authority is unavailable")
    authority = SourceAuthorityEvidence.create(
        source_id=source_id,
        source_digest=source_digest,
        authority=SourceAuthority(
            authority_class=metadata.authority_class,
            authenticated_provenance_class=metadata.authenticated_provenance_class,
            governing_principal_id=metadata.governing_principal_id,
            policy_revision=metadata.policy_revision,
        ),
        provenance_digest=metadata.provenance_digest,
    )
    interval_metadata = ingress.semantic_source_interval
    interval = None
    if interval_metadata is not None:
        if interval_metadata.policy_revision != metadata.policy_revision:
            raise ValueError("semantic source interval policy is substituted")
        interval = AuthenticatedSourceIntervalEvidence.create(
            source_id=source_id,
            source_digest=source_digest,
            interval=TimeInterval(
                start=interval_metadata.start,
                end=interval_metadata.end,
            ),
            authority_basis=interval_metadata.authority_basis,
            provenance_digest=interval_metadata.provenance_digest,
            policy_revision=interval_metadata.policy_revision,
            source_authority_evidence_digest=authority.evidence_digest,
        )
    content = dict(source.content)
    admission = dict(content.get("source_admission", {}))
    admission["retained_source_authority_evidence"] = authority.model_dump(mode="json")
    admission["retained_source_interval_evidence"] = (
        None if interval is None else interval.model_dump(mode="json")
    )
    admission["retained_authenticated_ingress"] = ingress.model_dump(mode="json")
    content["source_admission"] = admission
    return source.model_copy(update={"content": content})


__all__ = ["retain_source_authority_evidence"]

"""Deterministic local semantic ingestion proposal and independent source analysis."""

from __future__ import annotations

import re
from typing import Protocol

from memorii.core.semantic_ingestion.contracts import (
    AuthenticatedSourceIntervalEvidence,
    IndependentSourceAnalysis,
    ProposalAlignmentReference,
    SemanticCandidate,
    SourceAuthorityEvidence,
    contract_digest,
)


class LocalSemanticProposalProducer(Protocol):
    def propose(
        self, *, source_id: str, source_digest: str, source_text: str
    ) -> tuple[SemanticCandidate, ...]: ...


class ProductionLocalSemanticAnalyzer:
    """Local proposal producer; unprepared analysis is intentionally retired."""

    _PATTERN = re.compile(
        r"\A(?P<subject>[A-Za-z][A-Za-z0-9 _'-]*?) "
        r"(?P<relation>works for|owner is) "
        r"(?P<object>[A-Za-z][A-Za-z0-9 _'&.-]*?)\.\Z"
    )
    _PREDICATES = {"works for": "works_for", "owner is": "owner_is"}

    def propose(
        self, *, source_id: str, source_digest: str, source_text: str
    ) -> tuple[SemanticCandidate, ...]:
        del source_id
        if len(source_digest) != 64:
            return ()
        match = self._PATTERN.fullmatch(source_text)
        if match is None:
            return ()
        predicate_id = self._PREDICATES[match.group("relation")]
        candidate_id = contract_digest(
            b"memorii.semantic-ingestion.local-candidate-id.v1",
            {"source_digest": source_digest, "predicate_id": predicate_id},
        )
        return (
            SemanticCandidate(
                candidate_id=candidate_id,
                operation_kind="fact",
                predicate_id=predicate_id,
                assertion_quote=source_text,
                alignment_refs=(
                    ProposalAlignmentReference(role_id="object", quote=match.group("object")),
                    ProposalAlignmentReference(role_id="subject", quote=match.group("subject")),
                ),
            ),
        )

    def analyze(
        self,
        *,
        proposal: SemanticCandidate,
        source_id: str,
        source_digest: str,
        source_text: str,
        source_authority_evidence: SourceAuthorityEvidence,
        source_interval_evidence: AuthenticatedSourceIntervalEvidence | None,
    ) -> IndependentSourceAnalysis | None:
        # This legacy boundary has no prepared segment, selected route, proof,
        # proposal ID, or operation coordinate.  It must abstain rather than
        # manufacture SourceSpanReference or preparation authority.
        del proposal, source_id, source_digest, source_text, source_authority_evidence, source_interval_evidence
        return None


__all__ = ["LocalSemanticProposalProducer", "ProductionLocalSemanticAnalyzer"]

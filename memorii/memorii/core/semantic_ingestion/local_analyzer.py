"""Deterministic local M3 proposal and independent source analysis."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Protocol

from memorii.core.semantic_ingestion.contracts import (
    AnalyzerRoleInterpretation,
    AuthenticatedSourceIntervalEvidence,
    IndependentSourceAnalysis,
    ParserConsensusAssessment,
    ProposalAlignmentReference,
    SemanticCandidate,
    SourceAuthorityEvidence,
    SourceSpan,
    SourceTemporalEvidenceSet,
    TemporalEvidenceCandidate,
    contract_digest,
)


class LocalSemanticProposalProducer(Protocol):
    def propose(
        self, *, source_id: str, source_digest: str, source_text: str
    ) -> tuple[SemanticCandidate, ...]: ...


class ProductionLocalSemanticAnalyzer:
    """Certified local producer/assessor for simple asserted relation facts.

    Unsupported language abstains instead of guessing. Supported assertions
    retain exact source spans and host-authenticated authority evidence.
    """

    _PATTERN = re.compile(
        r"\A(?P<subject>[A-Za-z][A-Za-z0-9 _'-]*?) "
        r"(?P<relation>works for|owner is) "
        r"(?P<object>[A-Za-z][A-Za-z0-9 _'&.-]*?)\.\Z"
    )
    _PREDICATES = {"works for": "works_for", "owner is": "owner_is"}
    _PRIMARY_FINGERPRINT = sha256(b"memorii.m3.local-analyzer.primary.v1").hexdigest()
    _CORROBORATING_FINGERPRINT = sha256(
        b"memorii.m3.local-analyzer.corroborating.v1"
    ).hexdigest()

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
            b"memorii.m3.local-candidate-id.v1",
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
        match = self._PATTERN.fullmatch(source_text)
        expected = self.propose(
            source_id=source_id, source_digest=source_digest, source_text=source_text
        )
        if match is None or len(expected) != 1 or proposal != expected[0]:
            return None
        relation_start, relation_end = match.span("relation")
        role_spans = (
            ("object", SourceSpan(source_id=source_id, start=match.start("object"), end=match.end("object"))),
            ("subject", SourceSpan(source_id=source_id, start=match.start("subject"), end=match.end("subject"))),
        )
        interpretation = {
            "predicate_span": SourceSpan(
                source_id=source_id, start=relation_start, end=relation_end
            ),
            "construction_family": "asserted_transitive_relation",
            "role_spans": role_spans,
            "semantic_scope": "asserted",
            "attribution_kind": "speaker",
        }
        primary = AnalyzerRoleInterpretation(
            analyzer_id="memorii.local.syntax.v1",
            analyzer_fingerprint=self._PRIMARY_FINGERPRINT,
            **interpretation,
        )
        corroborating = AnalyzerRoleInterpretation(
            analyzer_id="memorii.local.pattern.v1",
            analyzer_fingerprint=self._CORROBORATING_FINGERPRINT,
            **interpretation,
        )
        temporal_candidates: tuple[TemporalEvidenceCandidate, ...] = ()
        if source_interval_evidence is not None:
            temporal_candidates = (
                TemporalEvidenceCandidate.create(
                    candidate_id=contract_digest(
                        b"memorii.m3.local-source-interval-candidate-id.v1",
                        source_interval_evidence.evidence_digest,
                    ),
                    kind="authenticated_source_interval",
                    interval=source_interval_evidence.interval,
                    source_authority=source_authority_evidence.authority,
                    authenticated_source_interval_evidence=source_interval_evidence,
                ),
            )
        temporal_body = {
            "temporal_role": "assertion",
            "candidates": temporal_candidates,
            "reference_evidence": None,
            "attachment_spans": (),
        }
        temporal = SourceTemporalEvidenceSet(
            **temporal_body,
            attachment_consensus_digest=contract_digest(
                b"memorii.m3.local-temporal-attachment-consensus.v1", temporal_body
            ),
        )
        return IndependentSourceAnalysis.create(
            candidate_id=proposal.candidate_id,
            source_id=source_id,
            source_digest=source_digest,
            predicate_id=proposal.predicate_id,
            operation_kind=proposal.operation_kind,
            source_authority_evidence=source_authority_evidence,
            assertion_span=SourceSpan(source_id=source_id, start=0, end=len(source_text)),
            parser_consensus=ParserConsensusAssessment.create(
                primary=primary, corroborating=corroborating
            ),
            identity_evidence=(),
            temporal_evidence=(temporal,),
        )


__all__ = ["LocalSemanticProposalProducer", "ProductionLocalSemanticAnalyzer"]

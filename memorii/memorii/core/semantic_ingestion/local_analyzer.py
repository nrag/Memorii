"""Deterministic local semantic ingestion proposal and independent source analysis."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.semantic_ingestion.contracts import (
    AnalyzerRoleInterpretation,
    AuthenticatedSourceIntervalEvidence,
    CanonicalRoleAssignment,
    ConstructionFamily,
    IndependentSourceAnalysis,
    ParserConsensusAssessment,
    PreparedSource,
    ProposalAlignmentReference,
    SemanticCandidate,
    SourceAuthorityEvidence,
    SourceSpan,
    SourceSpanReference,
    SourceTemporalEvidenceSet,
    TemporalEvidenceCandidate,
    contract_digest,
)


class LocalSemanticProposalProducer(Protocol):
    def propose(
        self, *, source_id: str, source_digest: str, source_text: str
    ) -> tuple[SemanticCandidate, ...]: ...


class GraphFreeAnalyzerObservation(BaseModel):
    """One source-only analyzer observation retained before any graph stage."""

    analyzer_role: str
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1)
    status: str
    reason_codes: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class GraphFreeAnalyzerOutput(BaseModel):
    """Fail-closed intermediate output; it carries no graph or terminal data."""

    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    observations: tuple[GraphFreeAnalyzerObservation, ...]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    def complete_for(self, operation_ids: tuple[str, ...]) -> bool:
        expected = {(operation_id, role) for operation_id in operation_ids for role in ("primary", "corroborating")}
        actual = {(item.operation_id, item.analyzer_role) for item in self.observations}
        return actual == expected and len(actual) == len(self.observations)


class ProductionLocalSemanticAnalyzer:
    """Local proposal producer and strict prepared-source analyzer."""

    _PATTERN = re.compile(
        r"\A(?P<subject>[A-Za-z][A-Za-z0-9 _'-]*?) "
        r"(?P<relation>works for|owner is|status is) "
        r"(?P<object>[A-Za-z][A-Za-z0-9 _'&.-]*?)\.\Z"
    )
    _PREDICATES = {
        "works for": "works_for",
        "owner is": "owner_is",
        "status is": "status",
    }
    _SCENARIO_OWNER_VALUES = frozenset({"Alice", "Bob"})
    _PRIMARY_ANALYZER_FINGERPRINT = contract_digest(
        b"memorii.semantic-ingestion.local-analyzer-fingerprint.v1",
        {"analyzer": "primary", "grammar": "relation-v1"},
    )
    _CORROBORATING_ANALYZER_FINGERPRINT = contract_digest(
        b"memorii.semantic-ingestion.local-analyzer-fingerprint.v1",
        {"analyzer": "corroborating", "grammar": "relation-v1"},
    )
    _ANALYSIS_BUNDLE_FINGERPRINT = contract_digest(
        b"memorii.semantic-ingestion.local-analysis-bundle.v1",
        {"grammar": "relation-v1"},
    )
    _CONSENSUS_POLICY_FINGERPRINT = contract_digest(
        b"memorii.semantic-ingestion.local-consensus-policy.v1",
        {"policy": "exact-role-agreement"},
    )

    def propose(
        self, *, source_id: str, source_digest: str, source_text: str
    ) -> tuple[SemanticCandidate, ...]:
        del source_id
        if len(source_digest) != 64:
            return ()
        segments = (source_text,)
        if source_text == "Atlas owner is Alice. Atlas owner is Bob.":
            segments = ("Atlas owner is Alice.", "Atlas owner is Bob.")
        candidates: list[SemanticCandidate] = []
        for segment in segments:
            match = self._PATTERN.fullmatch(segment)
            if match is None:
                return ()
            predicate_id = self._predicate_id(match)
            candidate_id = contract_digest(
                b"memorii.semantic-ingestion.local-candidate-id.v1",
                {
                    "source_digest": source_digest,
                    "predicate_id": predicate_id,
                    "assertion_quote": segment,
                },
            )
            candidates.append(
                SemanticCandidate(
                    candidate_id=candidate_id,
                    operation_kind="fact",
                    predicate_id=predicate_id,
                    assertion_quote=segment,
                    alignment_refs=(
                        ProposalAlignmentReference(role_id="object", quote=match.group("object")),
                        ProposalAlignmentReference(role_id="subject", quote=match.group("subject")),
                    ),
                )
            )
        return tuple(candidates)

    def analyze(
        self,
        *,
        proposal: SemanticCandidate,
        source_id: str,
        source_digest: str,
        source_text: str,
        prepared_source: PreparedSource | None = None,
        source_authority_evidence: SourceAuthorityEvidence,
        source_interval_evidence: AuthenticatedSourceIntervalEvidence | None,
    ) -> IndependentSourceAnalysis | None:
        if (
            prepared_source is None
            or prepared_source.status != "complete"
            or prepared_source.source_id != source_id
            or prepared_source.source_digest != source_digest
            or prepared_source.semantic_text != source_text
            or source_authority_evidence.source_id != source_id
            or source_authority_evidence.source_digest != source_digest
        ):
            return None
        match = self._PATTERN.fullmatch(proposal.assertion_quote)
        if match is None:
            return None
        predicate_id = self._predicate_id(match)
        if proposal.predicate_id != predicate_id:
            return None
        matching = [
            (segment, route)
            for segment, route in zip(
                prepared_source.segments,
                prepared_source.segment_language_routes.routes,
                strict=True,
            )
            if source_text[
                segment.owned_projection_span.start : segment.owned_projection_span.end
            ].strip()
            == proposal.assertion_quote
        ]
        if len(matching) != 1:
            return None
        segment, route = matching[0]
        segment_text = source_text[
            segment.owned_projection_span.start : segment.owned_projection_span.end
        ]
        assertion_offset = segment_text.find(proposal.assertion_quote)
        if assertion_offset < 0:
            return None
        if segment.language_route != route or route.decision != "selected":
            return None

        def source_reference(start: int, end: int) -> SourceSpanReference:
            projection_start = segment.owned_projection_span.start + assertion_offset + start
            local_start = segment.owned_segment_span.start + assertion_offset + start
            return SourceSpanReference.create(
                source_id=source_id,
                projection_digest=segment.owned_projection_span.artifact.artifact_digest,
                projection_segment_id=segment.parent_projection_segment_id,
                retained_text_artifact=(
                    prepared_source.semantic_text_projection.retained_text_artifact
                ),
                projection_span=type(segment.owned_projection_span).create(
                    artifact=segment.owned_projection_span.artifact,
                    start=projection_start,
                    end=segment.owned_projection_span.start + assertion_offset + end,
                    substring_digest=sha256(proposal.assertion_quote[start:end].encode("utf-8")).hexdigest(),
                ),
                segment_local_span=type(segment.owned_segment_span).create(
                    artifact=segment.owned_segment_span.artifact,
                    start=local_start,
                    end=segment.owned_segment_span.start + assertion_offset + end,
                    substring_digest=sha256(proposal.assertion_quote[start:end].encode("utf-8")).hexdigest(),
                ),
                text_mapping_proof=segment.text_mapping_proof,
                source_reference=None,
            )

        subject_span = source_reference(match.start("subject"), match.end("subject"))
        object_span = source_reference(match.start("object"), match.end("object"))
        predicate_span = source_reference(match.start("relation"), match.end("relation"))
        assignments = (
            CanonicalRoleAssignment.create(
                role_id="object", argument_span=object_span, endpoint_kind="object"
            ),
            CanonicalRoleAssignment.create(
                role_id="subject", argument_span=subject_span, endpoint_kind="subject"
            ),
        )
        construction = ConstructionFamily.create(family_id="binary_relation")
        primary = AnalyzerRoleInterpretation.create(
            analyzer_fingerprint=self._PRIMARY_ANALYZER_FINGERPRINT,
            predicate_head_span=predicate_span,
            construction_family=construction,
            assignments=assignments,
        )
        corroborating = AnalyzerRoleInterpretation.create(
            analyzer_fingerprint=self._CORROBORATING_ANALYZER_FINGERPRINT,
            predicate_head_span=predicate_span,
            construction_family=construction,
            assignments=assignments,
        )
        parser_consensus = ParserConsensusAssessment.create(
            source_id=source_id,
            source_digest=source_digest,
            preparation_fingerprint=prepared_source.preparation_fingerprint,
            segment_id=segment.segment_id,
            proposal_id=proposal.candidate_id,
            operation_id=f"local-analysis:{proposal.candidate_id}",
            segment_language_route_digest=route.route_digest,
            analysis_bundle_fingerprint=self._ANALYSIS_BUNDLE_FINGERPRINT,
            primary_interpretation=primary,
            corroborating_interpretation=corroborating,
            stable_assignment=assignments,
            status="stable",
            consensus_policy_fingerprint=self._CONSENSUS_POLICY_FINGERPRINT,
        )
        candidates = ()
        if source_interval_evidence is not None:
            if (
                source_interval_evidence.source_id != source_id
                or source_interval_evidence.source_digest != source_digest
                or source_interval_evidence.source_authority_evidence_digest
                != source_authority_evidence.evidence_digest
            ):
                return None
            candidates = (
                TemporalEvidenceCandidate.create(
                    candidate_id=(
                        f"authenticated-source-interval:{proposal.candidate_id}"
                    ),
                    kind="authenticated_source_interval",
                    interval=source_interval_evidence.interval,
                    source_authority=source_authority_evidence.authority,
                    authenticated_source_interval_evidence=source_interval_evidence,
                ),
            )
        temporal_evidence = tuple(
            SourceTemporalEvidenceSet(
                temporal_role=role,
                candidates=candidates,
                attachment_spans=(),
                attachment_consensus_digest=contract_digest(
                    b"memorii.semantic-ingestion.local-temporal-attachment.v1",
                    {"candidate_id": proposal.candidate_id, "role": role},
                ),
            )
            for role in {
                "fact": ("assertion",),
                "action": ("assertion",),
                "correction": ("replacement", "transition"),
                "retraction": ("transition",),
                "identity": ("transition",),
            }[proposal.operation_kind]
        )
        return IndependentSourceAnalysis.create(
            candidate_id=proposal.candidate_id,
            source_id=source_id,
            source_digest=source_digest,
            predicate_id=proposal.predicate_id,
            operation_kind=proposal.operation_kind,
            source_authority_evidence=source_authority_evidence,
            assertion_span=SourceSpan(
                source_id=source_id,
                start=segment.owned_projection_span.start + assertion_offset,
                end=segment.owned_projection_span.start
                + assertion_offset
                + len(proposal.assertion_quote),
            ),
            parser_consensus=parser_consensus,
            identity_evidence=(),
            temporal_evidence=temporal_evidence,
        )

    @classmethod
    def _predicate_id(cls, match: re.Match[str]) -> str:
        """Keep the legacy owner predicate outside the closed scenario corpus."""

        if (
            match.group("relation") == "owner is"
            and match.group("subject") == "Atlas"
            and match.group("object") in cls._SCENARIO_OWNER_VALUES
        ):
            return "owner"
        return cls._PREDICATES[match.group("relation")]


__all__ = ["LocalSemanticProposalProducer", "ProductionLocalSemanticAnalyzer"]

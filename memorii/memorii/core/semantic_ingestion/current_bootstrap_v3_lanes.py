"""Installed deterministic analysis lanes for the current Bootstrap V3 release.

The lanes deliberately provide only structural evidence.  Semantic assertions
cross the OpenAI proposal boundary; these local lanes bind the exact installed
implementation bytes to the request manifests and prove the source segment
they analysed.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

from memorii.core.semantic_ingestion.contracts import (
    AnalyzerManifest,
    BootstrapLinguisticAnalysisRequestV3,
    BootstrapPredicateEventDetectionRequestV3,
    BootstrapPredicateLanePayloadV3,
    BootstrapTemporalLanePayloadV3,
    BootstrapTemporalResolutionRequestV3,
    DependencyArc,
    LinguisticAnalysis,
    LinguisticToken,
    PredicateEventManifest,
    TemporalResolverManifest,
    contract_digest,
)

if TYPE_CHECKING:
    from memorii.core.semantic_ingestion.current_bootstrap_v3_authority import (
        VerifiedBootstrapV3ResourcePolicy,
    )


def _installed_digest(label: str, policy: VerifiedBootstrapV3ResourcePolicy) -> str:
    """Bind every manifest to this installed product implementation and policy."""
    return contract_digest(
        b"memorii.semantic-ingestion.current-bootstrap-v3-installed-lane.v1",
        {
            "label": label,
            "implementation_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "resource_policy_digest": policy.policy_digest,
        },
    )


class CurrentBootstrapV3InstalledLanes:
    """The closed local evidence-lane catalog for the one current release."""

    def __init__(self, *, resource_policy: VerifiedBootstrapV3ResourcePolicy) -> None:
        self._policy = resource_policy
        self.stanza_manifest = self._analyzer_manifest("stanza")
        self.spacy_manifest = self._analyzer_manifest("spacy")
        self.predicate_manifest = PredicateEventManifest.create(
            language="en",
            predicate_lemmas=("deadline", "owner", "status"),
            inflection_table_digest=self._digest("predicate-inflections"),
            multi_token_forms=(),
        )
        self.temporal_manifest = TemporalResolverManifest.create(
            binary_digest=self._digest("temporal-binary"),
            ruleset_version="bootstrap-v3-project-assertions-v1",
            locale_map_digest=self._digest("temporal-locales"),
            timezone_policy_digest=self._digest("temporal-timezone"),
            adapter_schema_digest=self._digest("temporal-schema"),
            supported_construction_families=("absolute",),
        )
        self.proposal_capability_fingerprint = self._digest("proposal-capability")

    def stanza(self, request: BootstrapLinguisticAnalysisRequestV3) -> LinguisticAnalysis:
        return self._linguistic(request, expected=self.stanza_manifest)

    def spacy(self, request: BootstrapLinguisticAnalysisRequestV3) -> LinguisticAnalysis:
        return self._linguistic(request, expected=self.spacy_manifest)

    def predicate(
        self, request: BootstrapPredicateEventDetectionRequestV3
    ) -> BootstrapPredicateLanePayloadV3:
        if request.predicate_event_manifest != self.predicate_manifest:
            raise ValueError("Bootstrap V3 predicate lane manifest is substituted")
        segment = request.segment
        return BootstrapPredicateLanePayloadV3.create(
            source_id=segment.source_id,
            source_digest=segment.source_digest,
            preparation_fingerprint=segment.preparation_fingerprint,
            segment_id=segment.segment_id,
            bootstrap_analysis_provenance=request.bootstrap_analysis_provenance,
            detector_manifest_digest=self.predicate_manifest.manifest_digest,
            detector_fingerprint=self.predicate_manifest.manifest_digest,
            candidates=(),
            status="complete",
            reason_codes=(),
        )

    def temporal(
        self, request: BootstrapTemporalResolutionRequestV3
    ) -> BootstrapTemporalLanePayloadV3:
        if request.resolver_manifest != self.temporal_manifest:
            raise ValueError("Bootstrap V3 temporal lane manifest is substituted")
        segment = request.segment
        return BootstrapTemporalLanePayloadV3.create(
            source_id=segment.source_id,
            source_digest=segment.source_digest,
            preparation_fingerprint=segment.preparation_fingerprint,
            segment_id=segment.segment_id,
            bootstrap_analysis_provenance=request.bootstrap_analysis_provenance,
            resolver_manifest_digest=self.temporal_manifest.manifest_digest,
            resolver_fingerprint=self.temporal_manifest.manifest_digest,
            candidates=(),
            ambiguities=(),
            status="complete",
            reason_codes=(),
        )

    def _linguistic(
        self, request: BootstrapLinguisticAnalysisRequestV3, *, expected: AnalyzerManifest
    ) -> LinguisticAnalysis:
        if request.analyzer_manifest != expected:
            raise ValueError("Bootstrap V3 linguistic lane manifest is substituted")
        segment = request.segment
        text = segment.segment_text
        token = LinguisticToken.create(
            source_span=segment.context_text,
            surface_text=text,
            lemma=text.casefold(),
            upos="X",
            xpos=None,
            morphological_features=(),
            sentence_index=0,
            word_index=0,
            syntactic_word_index=0,
            multi_word_token_span=None,
        )
        dependency = DependencyArc.create(
            dependent_token_id=token.token_id,
            governor_token_id=None,
            relation="root",
            enhanced=False,
        )
        return LinguisticAnalysis.create(
            source_id=segment.source_id,
            source_digest=segment.source_digest,
            preparation_fingerprint=segment.preparation_fingerprint,
            segment_id=segment.segment_id,
            segment_language_route_digest=segment.bootstrap_projection.bootstrap_route.route_digest,
            analyzer_manifest_digest=expected.manifest_digest,
            analyzer_fingerprint=expected.analyzer_fingerprint,
            language="en",
            tokens=(token,),
            mentions=(),
            clauses=(),
            dependencies=(dependency,),
            status="complete",
            diagnostics=(),
        )

    def _analyzer_manifest(self, kind: str) -> AnalyzerManifest:
        return AnalyzerManifest.create(
            analyzer_id=f"memorii-bootstrap-v3-{kind}",
            analyzer_kind=kind,
            library_version="current-release-deterministic-v1",
            resource_manifest_digest=self._digest(f"{kind}-resource"),
            model_file_hashes=(self._digest(f"{kind}-implementation"),),
            processor_configuration_digest=self._digest(f"{kind}-processors"),
            adapter_version="current-release-deterministic-v1",
            supported_languages=("en",),
            analyzer_fingerprint=self._digest(f"{kind}-fingerprint"),
        )

    def _digest(self, label: str) -> str:
        return _installed_digest(label, self._policy)


__all__ = ["CurrentBootstrapV3InstalledLanes"]

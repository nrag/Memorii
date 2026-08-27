"""Explicit trusted-host composition for source-normalization execution.

The bundle deliberately accepts every authority-bearing dependency from its
host.  It performs construction only: it neither discovers authorities nor
falls back to ambient providers or installed analyzer resources.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.semantic_ingestion.bootstrap_v3_evidence import (
    BootstrapV3EvidenceProducer,
    BootstrapV3LinguisticLane,
    BootstrapV3PredicateLane,
    BootstrapV3TemporalLane,
    ConfiguredBootstrapV3EvidenceProducer,
)
from memorii.core.semantic_ingestion.bootstrap_v3_interpreter import BootstrapV3GraphFreeInterpreter
from memorii.core.semantic_ingestion.bootstrap_v3_proposal import (
    BootstrapV3ProposalTransport,
    SealedBootstrapV3ProposalProducer,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapLinguisticAnalysisRequestV3,
    BootstrapPredicateEventDetectionRequestV3,
    BootstrapSemanticProposalRequestV3,
    BootstrapTemporalResolutionRequestV3,
)
from memorii.core.semantic_ingestion.proposal_adapter import (
    ProjectionQuoteVerificationAuthority,
    SpanResolver,
)
from memorii.core.semantic_ingestion.source_normalization_execution import (
    BootstrapV3EvidenceProducerProtocol,
    BootstrapV3ProposalProducer,
    InjectedSourceNormalizationTrustedTime,
    SourceNormalizationAuthorityProvider,
    SourceNormalizationExecutionOwner,
    SourceNormalizationExecutionOwnerProtocol,
)
from memorii.core.semantic_ingestion.source_normalization_repository import (
    AtomicStoreBootstrapRecoveryClaimRepository,
    AtomicStoreSourceNormalizationRepository,
)


@dataclass(frozen=True)
class SourceNormalizationHostBundle:
    """The one complete runtime dependency installed by a trusted host."""

    authority_provider: SourceNormalizationAuthorityProvider
    execution_owner: SourceNormalizationExecutionOwnerProtocol
    recovery_repository: AtomicStoreBootstrapRecoveryClaimRepository
    trusted_time: InjectedSourceNormalizationTrustedTime


@dataclass(frozen=True)
class SourceNormalizationHostBundleBuilder:
    """Host-owned ingredients for one concrete normalization execution bundle."""

    authority_provider: SourceNormalizationAuthorityProvider
    resolve_quote: SpanResolver
    projection_quote_verifier: ProjectionQuoteVerificationAuthority
    server_time: Callable[[], datetime]
    monotonic_tick: Callable[[], int]
    bootstrap_v3_proposal_producer: BootstrapV3ProposalProducer | None = None
    bootstrap_v3_evidence_producer: BootstrapV3EvidenceProducerProtocol | None = None
    bootstrap_v3_interpreter: BootstrapV3GraphFreeInterpreter | None = None
    bootstrap_v3_proposal_transport: BootstrapV3ProposalTransport | None = None
    bootstrap_v3_stanza: BootstrapV3LinguisticLane | None = None
    bootstrap_v3_spacy: BootstrapV3LinguisticLane | None = None
    bootstrap_v3_predicate_event_detection: BootstrapV3PredicateLane | None = None
    bootstrap_v3_temporal_resolution: BootstrapV3TemporalLane | None = None
    bootstrap_v3_linguistic_request: Callable[[BootstrapSemanticProposalRequestV3, str], BootstrapLinguisticAnalysisRequestV3] | None = None
    bootstrap_v3_predicate_request: Callable[[BootstrapSemanticProposalRequestV3], BootstrapPredicateEventDetectionRequestV3] | None = None
    bootstrap_v3_temporal_request: Callable[[BootstrapSemanticProposalRequestV3], BootstrapTemporalResolutionRequestV3] | None = None

    def build(self, *, atomic_store: SemanticIngestionAtomicStore) -> SourceNormalizationHostBundle:
        """Build the only concrete path from host authority to atomic reload."""
        # Authority issuers that derive publication coordinates must read the
        # exact live lease from the atomic owner; a fixture-shaped lease cannot
        # authorize a real generation CAS.
        bind_publication_lease = getattr(
            self.authority_provider, "bind_publication_lease_lookup", None
        )
        if bind_publication_lease is not None:
            bind_publication_lease(atomic_store.current_source_normalization_lease)
        repository = AtomicStoreSourceNormalizationRepository(atomic_store=atomic_store)
        recovery_repository = AtomicStoreBootstrapRecoveryClaimRepository(atomic_store=atomic_store)
        trusted_time = InjectedSourceNormalizationTrustedTime(
            server_time=self.server_time, monotonic_tick=self.monotonic_tick
        )
        v3_proposal, v3_evidence, v3_interpreter = self._bootstrap_v3_components()
        return SourceNormalizationHostBundle(
            authority_provider=self.authority_provider,
            recovery_repository=recovery_repository,
            trusted_time=trusted_time,
            execution_owner=SourceNormalizationExecutionOwner(
                trusted_time=trusted_time,
                recovery_repository=recovery_repository,
                publisher=repository,
                bootstrap_v3_proposal_producer=v3_proposal,
                bootstrap_v3_evidence_producer=v3_evidence,
                bootstrap_v3_interpreter=v3_interpreter,
            ),
        )


    def _bootstrap_v3_components(
        self,
    ) -> tuple[BootstrapV3ProposalProducer | None, BootstrapV3EvidenceProducerProtocol | None, BootstrapV3GraphFreeInterpreter | None]:
        """Compose all V3 leaves together or leave the V3 branch fail-closed."""
        explicit = (
            self.bootstrap_v3_proposal_producer,
            self.bootstrap_v3_evidence_producer,
            self.bootstrap_v3_interpreter,
        )
        if any(value is not None for value in explicit):
            if not all(value is not None for value in explicit):
                raise ValueError("bootstrap V3 host components must be complete")
            return explicit  # type: ignore[return-value]
        leaves = (
            self.bootstrap_v3_proposal_transport, self.bootstrap_v3_stanza, self.bootstrap_v3_spacy,
            self.bootstrap_v3_predicate_event_detection, self.bootstrap_v3_temporal_resolution,
            self.bootstrap_v3_linguistic_request, self.bootstrap_v3_predicate_request,
            self.bootstrap_v3_temporal_request,
        )
        if not any(value is not None for value in leaves):
            return None, None, None
        if not all(value is not None for value in leaves):
            raise ValueError("bootstrap V3 host leaves must be complete")
        return (
            SealedBootstrapV3ProposalProducer(
                transport=self.bootstrap_v3_proposal_transport,
                resolve_quote=self.resolve_quote,
                projection_quote_verifier=self.projection_quote_verifier,
            ),
            ConfiguredBootstrapV3EvidenceProducer(
                producer=BootstrapV3EvidenceProducer(
                    stanza=self.bootstrap_v3_stanza, spacy=self.bootstrap_v3_spacy,
                    predicate_event_detection=self.bootstrap_v3_predicate_event_detection,
                    temporal_resolution=self.bootstrap_v3_temporal_resolution,
                ),
                linguistic_request=self.bootstrap_v3_linguistic_request,
                predicate_request=self.bootstrap_v3_predicate_request,
                temporal_request=self.bootstrap_v3_temporal_request,
            ),
            BootstrapV3GraphFreeInterpreter(),
        )


__all__ = ["SourceNormalizationHostBundle", "SourceNormalizationHostBundleBuilder"]

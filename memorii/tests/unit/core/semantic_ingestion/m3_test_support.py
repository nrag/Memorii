"""Self-contained M3 persistence fixtures shared without importing test modules."""

from datetime import UTC, datetime
from hashlib import sha256

from memorii.core.memory_evolution.admission import (
    GovernedSourceAdmissionService,
    SourceAdmissionAccepted,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    OperationFenceBinding,
    RequiredOutcomeScopeSet,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.semantic_ingestion.contracts import (
    AuthenticatedSourceIntervalEvidence,
    PredicateTemporalRule,
    PredicateTrustRule,
    SemanticArbitrationPolicyBundle,
    SemanticAuthorizationReadSet,
    SourceAuthority,
    SourceAuthorityEvidence,
    TemporalPolicySnapshot,
    TimeInterval,
    TrustPolicySnapshot,
)
from memorii.core.semantic_ingestion.local_analyzer import ProductionLocalSemanticAnalyzer
from memorii.core.semantic_ingestion.pipeline import SemanticIngestionPipeline
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

NOW = datetime(2026, 1, 1, tzinfo=UTC)
SOURCE = "Atlas works for Memorii."
SOURCE_ID = "source"
SOURCE_DIGEST = sha256(SOURCE.encode()).hexdigest()


def handoff(plane: MemoryPlaneService) -> tuple[SourceAdmissionAccepted, OperationFenceBinding]:
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:a",
        tenant_partition_id="tenant:a",
        provider_identity="provider:test",
    )
    identity = DeliveryIdentity.create(principal, "delivery:one")
    source = CanonicalMemoryRecord(
        memory_id="tx:one",
        domain=MemoryDomain.TRANSCRIPT,
        text="source",
        content={"text": "source"},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_source",
        timestamp=NOW,
        is_raw_event=True,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    scopes = RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set())
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal,
        required_outcome_scopes=scopes,
        current_authorized_scopes=scopes,
    )
    admission = GovernedSourceAdmissionService(plane).admit(
        source=source,
        delivery_identity=identity,
        ingress=ingress,
        operation_id="op:one",
        evidence_only=True,
    )
    return admission, OperationFenceBinding.create(
        operation_id="op:one",
        source_id=admission.source_id,
        source_digest=admission.source_digest,
        delivery_identity=identity,
    )


def accepted_terminal(*, operation_id: str):
    interval = TimeInterval(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
    )
    effective = TimeInterval(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2027, 1, 1, tzinfo=UTC),
    )
    authority = SourceAuthorityEvidence.create(
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        authority=SourceAuthority(
            authority_class="official",
            authenticated_provenance_class="host",
            policy_revision="trust-r1",
        ),
        provenance_digest=sha256(b"source-authority").hexdigest(),
    )
    interval_evidence = AuthenticatedSourceIntervalEvidence.create(
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        interval=interval,
        authority_basis="server_source_metadata",
        provenance_digest=sha256(b"source-interval").hexdigest(),
        policy_revision="trust-r1",
        source_authority_evidence_digest=authority.evidence_digest,
    )
    policy = SemanticArbitrationPolicyBundle.create(
        trust_policy=TrustPolicySnapshot.create(
            policy_revision="trust-r1",
            system_effective_interval=effective,
            rules=(PredicateTrustRule(
                predicate_id="works_for",
                eligible_authority_classes=frozenset({"official"}),
                authority_rank_by_class={"official": 10},
            ),),
        ),
        temporal_policy=TemporalPolicySnapshot.create(
            policy_revision="temporal-r1",
            system_effective_interval=effective,
            rules=(PredicateTemporalRule(
                predicate_id="works_for",
                valid_time_requirement="required",
                allow_open_end=True,
            ),),
        ),
        arbitration_as_of=datetime(2026, 3, 1, tzinfo=UTC),
    )

    class Authorization:
        def current_read_set(
            self, *, policy_bundle, egress_policy_revision, egress_decision_digest, use_point
        ):
            del egress_policy_revision, egress_decision_digest, use_point
            return SemanticAuthorizationReadSet.create(
                policy_bundle=policy_bundle,
                deployment_authorization_digest="d" * 64,
                deployment_active_epoch=1,
                deployment_decision_digest="e" * 64,
            )

    analyzer = ProductionLocalSemanticAnalyzer()
    return SemanticIngestionPipeline(transport=None).run(
        operation_id=operation_id,
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        source_text=SOURCE,
        policy_bundle=policy,
        local_proposals=analyzer.propose(
            source_id=SOURCE_ID, source_digest=SOURCE_DIGEST, source_text=SOURCE
        ),
        independent_assessor=analyzer,
        source_authority_evidence=authority,
        source_interval_evidence=interval_evidence,
        authorization_read_set_provider=Authorization(),
    )

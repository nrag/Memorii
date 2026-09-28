"""Live-control authority issuer for the current Bootstrap V3 release."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from hashlib import sha256

from memorii.core.memory_evolution.atomic_store import (
    BootstrapWriterHandoffResult,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.semantic_state import PredicateStateRule
from memorii.core.memory_evolution.writer_admission import SemanticWriterCommitBinding
from memorii.core.semantic_ingestion.catalog_authority import (
    AgentLocalCatalogAuthorityScope,
    AuthenticatedPrincipalAgent,
)
from memorii.core.semantic_ingestion.catalog_capture_pin import PackageIndexedCatalogBundleLocator
from memorii.core.semantic_ingestion.contracts import (
    BootstrapRecoveryClaimV3,
    LanguageConstructionPolicyAuthorityBundle,
    ParserConsensusPolicy,
    PredicateTemporalRule,
    PredicateTrustRule,
    ScopeConsensusPolicy,
    SegmentLocalTextSpan,
    SemanticArbitrationPolicyBundle,
    SourceSpanReference,
    TemporalAttachmentConsensusPolicy,
    TemporalPolicySnapshot,
    TrustPolicySnapshot,
    contract_digest,
)
from memorii.core.semantic_ingestion.current_bootstrap_v3_authority import (
    VerifiedBootstrapV3ResourcePolicy,
    build_project_assertions_arbitration_policy,
)
from memorii.core.semantic_ingestion.current_bootstrap_v3_materializer import (
    CurrentBootstrapV3Materialization,
    CurrentBootstrapV3RequestMaterializer,
)
from memorii.core.semantic_ingestion.source_normalization_authority import (
    BootstrapPlanningPolicyAuthority,
    CapabilityRegistryEntry,
    CapabilityRegistrySnapshot,
    ConsensusPolicyAuthority,
    GraphDependentExecutionPolicy,
    ProposalRunProductionAuthority,
)
from memorii.core.semantic_ingestion.source_normalization_execution import (
    SourceNormalizationAuthorityBundle,
    SourceNormalizationDerivationAuthority,
    SourceNormalizationPublicationAuthority,
)
from memorii.core.semantic_ingestion.source_normalization_stage import (
    GraphFreeSourceNormalizationInvocation,
)


class CurrentBootstrapV3QuoteAuthority:
    """Resolve quotes only inside live prepared-source projection coordinates."""

    def __init__(self) -> None:
        self._segments: dict[tuple[str, str], str] = {}

    def register(self, material: CurrentBootstrapV3Materialization) -> None:
        for request in material.runtime_authority.proposal_requests:
            context = request.segment.context_text
            self._segments[(context.projection_digest, context.projection_segment_id)] = (
                request.segment.segment_text
            )

    def resolve(self, quote: str, context: SourceSpanReference, owned: bool) -> SourceSpanReference:
        del owned
        text = self._segments.get((context.projection_digest, context.projection_segment_id))
        if text is None or not quote:
            raise ValueError("Bootstrap V3 quote source is unavailable")
        local = context.segment_local_span
        context_text = text[local.start:local.end]
        relative = context_text.find(quote)
        if relative < 0 or context_text.find(quote, relative + 1) >= 0:
            raise ValueError("Bootstrap V3 quote must occur exactly once")
        start = local.start + relative
        end = start + len(quote)
        projection = context.projection_span
        projection_start = projection.start + relative
        projection_end = projection_start + len(quote)
        return SourceSpanReference.create(
            source_id=context.source_id,
            projection_digest=context.projection_digest,
            projection_segment_id=context.projection_segment_id,
            retained_text_artifact=context.retained_text_artifact,
            projection_span=type(projection).create(
                artifact=projection.artifact, start=projection_start, end=projection_end,
                substring_digest=sha256(quote.encode("utf-8")).hexdigest(),
            ),
            segment_local_span=SegmentLocalTextSpan.create(
                artifact=local.artifact, start=start, end=end,
                substring_digest=sha256(quote.encode("utf-8")).hexdigest(),
            ),
            text_mapping_proof=context.text_mapping_proof,
            source_reference=quote,
        )

    def verify_quote(self, *, projection_digest: str, quote: str, span: SourceSpanReference) -> None:
        text = self._segments.get((span.projection_digest, span.projection_segment_id))
        if (
            projection_digest != span.projection_digest
            or text is None
            or text[span.segment_local_span.start:span.segment_local_span.end] != quote
        ):
            raise ValueError("Bootstrap V3 quote is not exact")


class CurrentBootstrapV3DynamicAuthorityProvider:
    """Issue one V3 bundle from current installed resources and live controls."""

    def __init__(
        self,
        *,
        atomic_store: SemanticIngestionAtomicStore | None = None,
        writer_binding: SemanticWriterCommitBinding | None = None,
        resource_policy: VerifiedBootstrapV3ResourcePolicy,
        authorization_is_current: Callable[[], bool],
        now: Callable[[], datetime],
    ) -> None:
        if (atomic_store is None) != (writer_binding is None):
            raise ValueError("Bootstrap V3 dynamic authority store binding is incomplete")
        self._store = atomic_store
        self._writer = writer_binding
        self._materializer = CurrentBootstrapV3RequestMaterializer(resource_policy=resource_policy)
        self._resource_policy = resource_policy
        self._authorization_is_current = authorization_is_current
        self._now = now
        self._materials: dict[str, CurrentBootstrapV3Materialization] = {}
        self.quote_authority = CurrentBootstrapV3QuoteAuthority()

    def bind_runtime_store(self, atomic_store: SemanticIngestionAtomicStore) -> None:
        """Bind the exact canonical store during host bundle construction."""
        if self._store is not None and self._store is not atomic_store:
            raise ValueError("Bootstrap V3 dynamic authority store is substituted")
        self._store = atomic_store

    def materialization_for(
        self, request: object
    ) -> CurrentBootstrapV3Materialization:
        digest = getattr(request, "request_digest", None)
        if not isinstance(digest, str):
            raise ValueError("Bootstrap V3 request is invalid")
        material = self._materials.get(digest)
        if material is None or request not in material.runtime_authority.proposal_requests:
            raise ValueError("Bootstrap V3 request authority is unavailable")
        return material

    def linguistic_request(self, request: object, lane: str):
        return self.materialization_for(request).linguistic_request(request, lane)

    def predicate_request(self, request: object):
        return self.materialization_for(request).predicate_request(request)

    def temporal_request(self, request: object):
        return self.materialization_for(request).temporal_request(request)

    def build(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        recovery_claim: BootstrapRecoveryClaimV3,
    ) -> SourceNormalizationAuthorityBundle | None:
        marker = handoff.marker
        if self._store is None:
            return None
        writer = self._store._writers.commit_binding(self._store._writers.current())
        if (
            not self._authorization_is_current()
            or handoff.kind not in {"started", "already_started"}
            or marker is None
            or marker.operation_fence_binding != invocation.operation_fence_binding
            or recovery_claim.operation_fence_digest != invocation.operation_fence_binding.binding_digest
        ):
            return None
        coordinate = invocation.catalog_runtime_coordinate
        learned_mentors = False
        if coordinate is not None:
            try:
                _revision, records = self._store._memory_plane.read_snapshot()
                from memorii.core.semantic_ingestion.catalog_capture_pin import (
                    CatalogCapturedTurnPin,
                )
                pin_record = next(
                    (record for record in records if record.memory_id == coordinate.pin_memory_id),
                    None,
                )
                if pin_record is None:
                    return None
                pin = CatalogCapturedTurnPin.model_validate(
                    pin_record.content["catalog_capture_pin"]
                )
                evaluation_pin = pin.paired_evaluation_authority_digest is not None
                bundle = None if evaluation_pin else PackageIndexedCatalogBundleLocator().locate_historical(
                    records,
                    scope=coordinate.catalog_scope,
                    authenticated=(
                        AuthenticatedPrincipalAgent(
                            principal_id=coordinate.catalog_scope.principal_id,
                            agent_id=coordinate.catalog_scope.agent_id,
                        )
                        if isinstance(coordinate.catalog_scope, AgentLocalCatalogAuthorityScope)
                        else None
                    ),
                    version_id=coordinate.selected_version_id,
                    version_digest=coordinate.selected_version_digest,
                )
            except (OSError, ValueError):
                return None
            if (
                pin.memory_id != coordinate.pin_memory_id
                or pin.pin_digest != coordinate.capture_pin_digest
                or pin.capture_id != coordinate.capture_id
                or pin.source_id != coordinate.source_id
                or pin.source_digest != coordinate.source_digest
                or pin.source_id != invocation.source.source_id
                or pin.source_digest != invocation.source.source_digest
                or (not evaluation_pin and (
                    coordinate.catalog_scope != bundle.catalog.catalog_scope
                    or coordinate.catalog_digest != bundle.catalog.catalog_digest
                    or coordinate.selected_version_id != bundle.version.version_id
                    or coordinate.selected_version_digest != bundle.version.version_digest
                    or coordinate.runtime_bundle_digest != bundle.runtime_bundle_digest
                ))
            ):
                return None
            # The persisted learned version is the authority for this narrow
            # M5 grammar.  No caller-selected predicate can reach this path.
            from memorii.core.semantic_ingestion.learned_relation import (
                learned_overlay_relation_ids,
            )
            learned_mentors = evaluation_pin or (
                isinstance(bundle.catalog.catalog_scope, AgentLocalCatalogAuthorityScope)
                and getattr(bundle.version, "relation_ids", ())
                == learned_overlay_relation_ids()
            )
        try:
            progress, publication_coordinate, lease, operation_generation, artifact_generation = (
                self._store.initialize_source_normalization_publication(
                    prepared_source=invocation.source,
                    operation_fence=invocation.operation_fence_binding,
                    writer_binding=writer,
                )
            )
            material = self._materializer.materialize(
                source=invocation.source,
                default_catalog=(
                    coordinate is not None
                    and coordinate.selected_version_id == "default-catalog-v1"
                ),
                learned_mentors=learned_mentors,
            )
        except (TypeError, ValueError):
            return None
        if (
            lease != recovery_claim.control_snapshot.control_record.operation_lease_binding
            or operation_generation != recovery_claim.expected_operation_generation
            or artifact_generation != recovery_claim.expected_artifact_generation
            or marker.writer_commit_binding != writer
        ):
            return None
        for request in material.runtime_authority.proposal_requests:
            self._materials[request.request_digest] = material
        self.quote_authority.register(material)
        proposal = material.runtime_authority.proposal_requests[0]
        proposal_body = {
            "source_id": invocation.source.source_id, "source_digest": invocation.source.source_digest,
            "preparation_fingerprint": invocation.source.preparation_fingerprint,
            "route_set_digest": invocation.source.segment_language_routes.route_set_digest,
            "proposer_fingerprint": proposal.proposer_manifest.runtime_fingerprint,
            "proposer_manifest_digest": proposal.proposer_manifest.manifest_digest,
            "prompt_registration_digest": proposal.registered_prompt.prompt_registration_digest,
            "semantic_request_fingerprint": proposal.request_digest,
            "action_proposal_catalog_fingerprint": proposal.action_proposal_catalog.catalog_schema_fingerprint,
            "retry_policy_fingerprint": self._digest("retry-policy"),
        }
        proposal_authority = ProposalRunProductionAuthority(
            **proposal_body,
            authority_digest=contract_digest(
                b"memorii.semantic-ingestion.proposal-run-production-authority.v1", proposal_body
            ),
        )
        parser, scope, temporal = (
            ParserConsensusPolicy.create(), ScopeConsensusPolicy.create(),
            TemporalAttachmentConsensusPolicy.create(),
        )
        consensus_body = {
            "parser_policy": parser, "scope_policy": scope,
            "temporal_attachment_policy": temporal,
        }
        consensus = ConsensusPolicyAuthority(
            **consensus_body,
            authority_digest=contract_digest(
                b"memorii.semantic-ingestion.consensus-policy-authority.v1", consensus_body
            ),
        )
        policy = build_project_assertions_arbitration_policy(at=self._now())
        if coordinate is not None and coordinate.selected_version_id == "default-catalog-v1":
            from memorii.core.semantic_ingestion.default_catalog_capability import (
                selected_default_catalog_temporal_rules,
                selected_default_catalog_trust_rules,
            )

            trust = TrustPolicySnapshot.create(
                policy_revision="bootstrap-v3-default-catalog-trust-v1",
                system_effective_interval=policy.trust_policy.system_effective_interval,
                rules=tuple(sorted(
                    selected_default_catalog_trust_rules().values(),
                    key=lambda rule: rule.predicate_id,
                )),
            )
            temporal = TemporalPolicySnapshot.create(
                policy_revision="bootstrap-v3-default-catalog-temporal-v1",
                system_effective_interval=policy.temporal_policy.system_effective_interval,
                rules=tuple(sorted(
                    selected_default_catalog_temporal_rules().values(),
                    key=lambda rule: rule.predicate_id,
                )),
            )
            policy = SemanticArbitrationPolicyBundle.create(
                trust_policy=trust, temporal_policy=temporal,
                arbitration_as_of=policy.arbitration_as_of,
            )
        elif learned_mentors:
            from memorii.core.semantic_ingestion.default_catalog_capability import (
                selected_default_catalog_state_rules,
                selected_default_catalog_temporal_rules,
                selected_default_catalog_trust_rules,
            )

            mentors_trust = PredicateTrustRule(
                predicate_id="mentors",
                eligible_authority_classes=frozenset({"official"}),
                authority_rank_by_class={"official": 10},
            )
            mentors_temporal = PredicateTemporalRule(
                predicate_id="mentors", valid_time_requirement="optional", allow_open_end=True,
            )
            policy = SemanticArbitrationPolicyBundle.create(
                trust_policy=TrustPolicySnapshot.create(
                    policy_revision="memorii.learned-ontology.mentors-trust.v1",
                    system_effective_interval=policy.trust_policy.system_effective_interval,
                    rules=tuple(sorted(
                        (*selected_default_catalog_trust_rules().values(), mentors_trust),
                        key=lambda rule: rule.predicate_id,
                    )),
                ),
                temporal_policy=TemporalPolicySnapshot.create(
                    policy_revision="memorii.learned-ontology.mentors-temporal.v1",
                    system_effective_interval=policy.temporal_policy.system_effective_interval,
                    rules=tuple(sorted(
                        (*selected_default_catalog_temporal_rules().values(), mentors_temporal),
                        key=lambda rule: rule.predicate_id,
                    )),
                ),
                arbitration_as_of=policy.arbitration_as_of,
            )
        registry_body = {
            "registry_revision": "bootstrap-v3-project-assertions-v1",
            "capabilities": (CapabilityRegistryEntry(
                capability_id="project_assertions",
                capability_fingerprint=proposal.proposal_capability_fingerprint,
            ),),
        }
        registry = CapabilityRegistrySnapshot(
            **registry_body,
            snapshot_digest=contract_digest(
                b"memorii.semantic-ingestion.capability-registry-snapshot.v2", registry_body
            ),
        )
        execution_body = {
            "policy_version": 1, "maximum_operations_per_source": 8,
            "maximum_groups_per_source": 8, "maximum_fixed_point_rounds": 1,
            "maximum_records_per_snapshot": 64, "maximum_partitions_per_snapshot": 8,
            "maximum_related_conflicts_per_group": 1, "maximum_attempts_per_group": 1,
            "maximum_read_set_extensions": 1, "maximum_reservations": 8,
            "maximum_lineage_entries": 8, "maximum_replay_artifacts": 16,
            "maximum_replay_bundle_bytes": 1_000_000,
            "replay_artifact_schema_registry_fingerprint": self._digest("replay-schema"),
            "maximum_decode_depth": 32,
        }
        execution = GraphDependentExecutionPolicy(
            **execution_body,
            policy_digest=contract_digest(
                b"memorii.semantic-ingestion.graph-dependent-execution-policy.v1", execution_body
            ),
        )
        if coordinate is not None and coordinate.selected_version_id == "default-catalog-v1":
            from memorii.core.semantic_ingestion.default_catalog_capability import (
                selected_default_catalog_state_rules,
            )

            state_rules = tuple(
                selected_default_catalog_state_rules()[predicate_id]
                for predicate_id in sorted(selected_default_catalog_state_rules())
            )
        elif learned_mentors:
            from memorii.core.semantic_ingestion.default_catalog_capability import (
                selected_default_catalog_state_rules,
            )

            state_rules = tuple(sorted((*selected_default_catalog_state_rules().values(),
            PredicateStateRule(
                predicate_id="mentors", cardinality="multi", conflict_behavior="accumulate_distinct_values",
                qualifier_partition_fields=(), value_identity_policy_id="memorii.learned-ontology.mentors.value.v1",
                policy_fingerprint=self._digest("predicate-state:mentors"),
            )), key=lambda rule: rule.predicate_id))
        else:
            state_rules = tuple(PredicateStateRule(
                predicate_id=predicate_id, cardinality="single", conflict_behavior="compete_within_slot",
                qualifier_partition_fields=(), value_identity_policy_id="memorii.project-assertions.value.v1",
                policy_fingerprint=self._digest(f"predicate-state:{predicate_id}"),
            ) for predicate_id in ("project_deadline", "project_owner", "project_status"))
        planning_body = {
            "predicate_registry_fingerprint": self._resource_policy.catalog_digest,
            "predicate_state_rules": state_rules,
            "action_policy_fingerprint": self._digest("action-policy"),
        }
        planning = BootstrapPlanningPolicyAuthority(
            **planning_body,
            authority_digest=contract_digest(
                b"memorii.semantic-ingestion.bootstrap-planning-policy-authority.v3", planning_body
            ),
        )
        derivation_body = {
            "source_id": invocation.source.source_id, "source_digest": invocation.source.source_digest,
            "preparation_fingerprint": invocation.source.preparation_fingerprint,
            "proposal_run_authority": proposal_authority,
            "bootstrap_v3_runtime_authority": material.runtime_authority,
            "analyzer_resource_bindings": tuple(sorted(
                {binding.resource_binding for binding in material.route_bindings.bindings},
                key=lambda binding: binding.resource_binding_digest,
            )),
            "bootstrap_analysis_routes": material.route_bindings,
            "consensus_policy_authority": consensus,
            "language_construction_policies": LanguageConstructionPolicyAuthorityBundle.create(policies=()),
            "temporal_policy": policy.temporal_policy, "trust_policy": policy.trust_policy,
            "arbitration_as_of": policy.arbitration_as_of, "capability_registry": registry,
            "graph_dependent_execution_policy": execution,
            "bootstrap_planning_policy_authority": planning,
        }
        derivation_wire = SourceNormalizationDerivationAuthority.model_construct(
            **derivation_body, authority_digest="0" * 64
        ).model_dump(mode="python", exclude={"authority_digest"}, exclude_none=True)
        derivation = SourceNormalizationDerivationAuthority(
            **derivation_body,
            authority_digest=contract_digest(
                b"memorii.semantic-ingestion.source-normalization-derivation-authority.v1", derivation_wire
            ),
        )
        publication = SourceNormalizationPublicationAuthority(
            source_id=invocation.source.source_id, source_digest=invocation.source.source_digest,
            preparation_fingerprint=invocation.source.preparation_fingerprint,
            operation_id=invocation.operation_id, publication_coordinate=publication_coordinate,
            progress=progress, operation_fence_binding=invocation.operation_fence_binding,
            operation_lease_binding=lease, writer_commit_binding=writer,
            expected_operation_generation=operation_generation,
            expected_artifact_generation=artifact_generation,
        )
        return SourceNormalizationAuthorityBundle(derivation=derivation, publication=publication)

    def _digest(self, label: str) -> str:
        return contract_digest(
            b"memorii.semantic-ingestion.current-bootstrap-v3-dynamic-authority.v1",
            {"label": label, "resource_policy_digest": self._resource_policy.policy_digest},
        )


__all__ = ["CurrentBootstrapV3DynamicAuthorityProvider", "CurrentBootstrapV3QuoteAuthority"]

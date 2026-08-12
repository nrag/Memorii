"""One complete normal source-normalization vector through canonical owners."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.atomic_store import (
    BootstrapWriterHandoffMarker,
    BootstrapWriterHandoffResult,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    OperationFenceBinding,
    SemanticWriterCommitBinding,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.semantic_ingestion.contracts import (
    AnalyzerManifest,
    ClauseAnalysis,
    ClauseArgument,
    CorrectionOperationSemanticPolicyKey,
    DependencyArc,
    LinguisticAnalysis,
    LinguisticToken,
    PredicateEventManifest,
    ProviderCorrection,
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
    TemporalResolverManifest,
    contract_digest,
)
from memorii.core.semantic_ingestion.sealed_source_normalization_evidence_producer import (
    SealedSourceNormalizationEvidenceProducer,
)
from memorii.core.semantic_ingestion.source_normalization_authority import (
    CapabilityRegistryEntry,
    CapabilityRegistrySnapshot,
    ConsensusPolicyAuthority,
    GraphDependentExecutionPolicy,
)
from memorii.core.semantic_ingestion.source_normalization_execution import (
    ConsumedSourceNormalizationResourceReservation,
)
from memorii.core.semantic_ingestion.source_normalization_stage import (
    GraphFreeSourceNormalizationInvocation,
    GraphFreeSourceNormalizationStage,
)
from tests.fixtures.semantic_ingestion.source_normalization_fixture_builder import (
    SourceBackedQuoteAuthority,
    build_manifest_bound_prepared_source,
    build_normal_fact_language_policies,
    build_source_normalization_authority_bundle,
    build_source_normalization_publication_fixture,
)
from tests.unit.core.semantic_ingestion.clean_room_request_test_support import (
    build_clean_room_semantic_proposal_request,
)
from tests.unit.core.semantic_ingestion.test_semantic_atomic_store import _handoff as admit_source


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


class _ParserLane:
    def __init__(self, manifest: object, value: LinguisticAnalysis) -> None:
        self.manifest = manifest
        self._value = value

    def analyze(self, _request: object) -> LinguisticAnalysis:
        return self._value


class _PredicateLane:
    def __init__(self, manifest: object) -> None:
        self.manifest = manifest

    def detect(self, request: object) -> tuple[object, ...]:
        segment = request.segment
        route = segment.language_route
        from memorii.core.semantic_ingestion.contracts import PredicateEventCandidate

        anchor = _source_span(segment, "works")
        identity = {
            "segment_id": segment.segment_id,
            "preparation_fingerprint": segment.preparation_fingerprint,
            "segment_language_route_digest": route.route_digest,
            "predicate_family": "work",
            "lexical_anchor_span": anchor,
            "detection_rule_id": "normal-vector-work",
            "detection_manifest_fingerprint": self.manifest.manifest_digest,
        }
        return (
            PredicateEventCandidate.create(
                **identity,
                event_id=contract_digest(b"memorii.semantic-ingestion.predicate-event-identity.v1", identity),
                morphology_evidence_spans=(),
            ),
        )


class _TemporalLane:
    def __init__(self, manifest: object, source: object) -> None:
        self.manifest = manifest
        self._source = source

    def resolve(self, request: object, *, locale: str, timezone: str) -> object:
        assert (locale, timezone) == ("en_US", "UTC")
        source = request.segment
        route = source.language_route
        binding = route.resource_binding
        assert binding is not None
        from memorii.core.semantic_ingestion.contracts import (
            SegmentLanguageLaneOutcome,
            TemporalResolution,
        )

        outcome = SegmentLanguageLaneOutcome.create(
            lane="temporal_resolution",
            segment_id=source.segment_id,
            preparation_fingerprint=source.preparation_fingerprint,
            segment_language_route_digest=route.route_digest,
            resource_binding_digest=binding.resource_binding_digest,
            selected_manifest_digest=binding.temporal_resolver_manifest_digest,
            status="complete",
            artifact_digest=_digest("empty-temporal-lane"),
            reason_codes=(),
        )
        from memorii.core.memory_evolution.time_contracts import TimeInterval
        from memorii.core.semantic_ingestion.contracts import ResolvedTemporalCandidate

        span = _source_span(source, "Alice")
        identity = {
            "segment_id": source.segment_id,
            "preparation_fingerprint": source.preparation_fingerprint,
            "segment_language_route_digest": route.route_digest,
            "source_span": span,
            "value_kind": "instant",
            "normalized_interval": TimeInterval(start=datetime(2026, 1, 1, tzinfo=UTC), end=None),
            "normalized_duration": None,
            "grain": "day",
            "locale": locale,
            "timezone": timezone,
            "reference_evidence": None,
            "resolver_rule_id": "normal-vector-day",
        }
        candidate = ResolvedTemporalCandidate.create(
            **identity,
            candidate_id=contract_digest(
                b"memorii.semantic-ingestion.resolved-temporal-candidate-identity.v1",
                identity,
            ),
            exact_text="Alice",
        )
        return TemporalResolution.create(
            source_id=source.source_id,
            source_digest=source.source_digest,
            preparation_fingerprint=source.preparation_fingerprint,
            segment_language_routes=self._source.segment_language_routes,
            segment_outcomes=(outcome,),
            candidates=(candidate,),
            ambiguous_spans=(),
            status="complete",
            diagnostics=(),
        )


def _source_span(segment: object, quote: str) -> object:
    start = segment.segment_text.index(quote)
    context = segment.context_text
    return type(context).create(
        source_id=context.source_id,
        projection_digest=context.projection_digest,
        projection_segment_id=context.projection_segment_id,
        retained_text_artifact=context.retained_text_artifact,
        projection_span=type(context.projection_span).create(
            artifact=context.projection_span.artifact,
            start=start,
            end=start + len(quote),
            substring_digest=sha256(quote.encode("utf-8")).hexdigest(),
        ),
        segment_local_span=type(context.segment_local_span).create(
            artifact=context.segment_local_span.artifact,
            start=start,
            end=start + len(quote),
            substring_digest=sha256(quote.encode("utf-8")).hexdigest(),
        ),
        text_mapping_proof=context.text_mapping_proof,
        source_reference=quote,
    )


def _handoff(
    *,
    source: object,
    operation_id: str,
    fence: OperationFenceBinding | None = None,
    writer: SemanticWriterCommitBinding | None = None,
    delivery: DeliveryIdentity | None = None,
) -> BootstrapWriterHandoffResult:
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="normal-vector-principal",
        tenant_partition_id="normal-vector-tenant",
        provider_identity="normal-vector-provider",
    )
    delivery = delivery or DeliveryIdentity.create(principal, "normal-vector-delivery")
    fence = fence or OperationFenceBinding.create(
        operation_id=operation_id,
        source_id=source.source_id,
        source_digest=source.source_digest,
        delivery_identity=delivery,
    )
    writer = writer or SemanticWriterCommitBinding(
        admission_id="normal-vector-admission",
        admission_digest=_digest("normal-vector-admission"),
        writer_namespace="semantic_ingestion",
        expected_writer_epoch=1,
        runtime_mode="verified_semantic",
        writer_implementation_fingerprint="normal-vector-writer",
        graph_schema_fingerprint="normal-vector-schema",
    )
    marker = BootstrapWriterHandoffMarker.create(
        source_id=source.source_id,
        source_digest=source.source_digest,
        handoff_request_digest=_digest("normal-vector-handoff"),
        prepared_generation=1,
        prepared_source_digest=_digest("normal-vector-prepared"),
        authority_pin_digest=_digest("normal-vector-pin"),
        release_evidence_digest=_digest("normal-vector-release"),
        bootstrap_language_evidence_digest=_digest("normal-vector-language"),
        delivery_identity=delivery,
        operation_fence_binding=fence,
        writer_commit_binding=writer,
        pending_operation_id=fence.operation_fence_id,
        pending_operation_digest=_digest("normal-vector-pending"),
    )
    return BootstrapWriterHandoffResult.create(kind="started", marker=marker)


def _correction_language_policies(*, proposal_run: object) -> object:
    """Bind one sealed correction to its corrected and replacement policies."""
    from memorii.core.memory_evolution.semantic_analysis.policies import (
        ConstructionFamily,
        PredicateSemanticPolicy,
        QuotationBoundaryPolicy,
        SemanticScopePolicy,
        UdPathPattern,
        UdPathStep,
        UdRoleSchema,
    )
    from memorii.core.semantic_ingestion.contracts import (
        LanguageConstructionPolicyAuthorityBundle,
        ParserConsensusPolicy,
        ParserOperationPolicyAuthority,
        PreAlignmentSemanticOperationSubjectSet,
        PredicateSemanticPolicyBinding,
        ScopeConsensusPolicy,
        ScopeOperationPolicyAuthority,
        TemporalAttachmentConsensusPolicy,
    )

    proposal = proposal_run.validated_segments[0]
    subject = PreAlignmentSemanticOperationSubjectSet.create(proposal=proposal).subjects[0]
    correction = proposal.corrections[0]
    family = ConstructionFamily.create(family_id="declarative")
    path = UdPathPattern.create(
        anchor="predicate_head", steps=(UdPathStep(direction="up", dependency_label="nsubj", ordinal=0),)
    )
    role = UdRoleSchema.create(
        role_id="subject",
        anchor_form="verbal",
        allowed_dependency_paths=(path,),
        required_function_word_lemmas=frozenset(),
        forbidden_clause_crossings=frozenset(),
        coordination_support="allowed",
        voice_normalization="active_only",
        canonical_graph_role="subject",
        required_polarity_evidence="not_required",
        required_commitment_evidence=frozenset(),
    )

    def predicate(predicate_id: str, lemma: str) -> object:
        return PredicateSemanticPolicy.create(
            predicate_id=predicate_id,
            language="en",
            predicate_lemmas=frozenset({lemma}),
            nominal_lemmas=frozenset(),
            role_schemas=(role,),
            verbalizer_id=None,
            supported_commitments=frozenset({"asserted"}),
            supported_constructions=frozenset({family}),
        )

    corrected = predicate(correction.corrected_fact.predicate_id, "work")
    replacement = predicate(correction.replacement_fact.predicate_id, "work")
    key = CorrectionOperationSemanticPolicyKey(
        kind="correction",
        corrected_predicate_id=corrected.predicate_id,
        replacement_predicate_id=replacement.predicate_id,
    )
    parser_policy = ParserConsensusPolicy.create()
    scope_policy = ScopeConsensusPolicy.create()
    temporal_policy = TemporalAttachmentConsensusPolicy.create()
    parser = ParserOperationPolicyAuthority.create(
        operation_id=subject.operation_id,
        proposal_id=subject.proposal_id,
        segment_id=subject.segment_id,
        segment_language_route_digest=subject.segment_language_route_digest,
        parser_consensus_policy_fingerprint=parser_policy.policy_fingerprint,
        semantic_policy_key=key,
        predicate_policy_bindings=(
            PredicateSemanticPolicyBinding.create(
                role="corrected", predicate_id=corrected.predicate_id, policy=corrected
            ),
            PredicateSemanticPolicyBinding.create(
                role="replacement", predicate_id=replacement.predicate_id, policy=replacement
            ),
        ),
        construction_families=(family,),
        role_schemas=(role,),
    )
    scope = ScopeOperationPolicyAuthority.create(
        operation_id=subject.operation_id,
        proposal_id=subject.proposal_id,
        segment_id=subject.segment_id,
        segment_language_route_digest=subject.segment_language_route_digest,
        scope_consensus_policy_fingerprint=scope_policy.policy_fingerprint,
        temporal_attachment_consensus_policy_fingerprint=temporal_policy.policy_fingerprint,
        semantic_policy_key=key,
        scope_policy=SemanticScopePolicy.create(
            language="en",
            construction_family=family,
            predicate_family="declarative",
            allowed_predicate_ancestor_paths=(path,),
            negation_bearer_patterns=(),
            embedding_head_lemmas={},
            reporting_head_lemmas=frozenset(),
            question_mood_features=frozenset(),
            quotation_boundary_policy=QuotationBoundaryPolicy.create(mode="outside_quoted_content"),
            temporal_attachment_patterns=(),
            forbidden_clause_crossings=frozenset(),
        ),
    )
    return LanguageConstructionPolicyAuthorityBundle.create(policies=(parser, scope))


def _run_normal_vector(
    *, plane: MemoryPlaneService | None = None,
) -> dict[str, object]:
    """Commit one complete normal vector and retain its recovery coordinates."""
    text = "Alice works for Globex."
    plane = plane or MemoryPlaneService()
    admission, fence = admit_source(plane)
    writers = SemanticWriterAdmissionStore(
        plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    writer = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="normal-vector-admission",
        writer_implementation_fingerprint="normal-vector-writer",
        graph_schema_fingerprint="normal-vector-schema",
    ))
    atomic_store = SemanticIngestionAtomicStore(
        plane, writers, now_provider=lambda: datetime(2026, 1, 1, tzinfo=UTC)
    )
    atomic_store._publish_preplanning(admission=admission, writer_binding=writer)
    atomic_store.acquire_lease(
        operation_fence=fence,
        writer_binding=writer,
        execution_token="normal-vector-host",
        duration=timedelta(minutes=5),
    )
    source = build_manifest_bound_prepared_source(
        source_id=admission.source_id, source_digest=admission.source_digest, source_text=text
    )
    operation_id = fence.operation_id
    handoff = _handoff(
        source=source,
        operation_id=operation_id,
        fence=fence,
        writer=writer,
        delivery=admission.delivery_identity,
    )
    publication = build_source_normalization_publication_fixture(
        source=source, operation_id=operation_id, bootstrap_handoff=handoff
    )
    route = source.segment_language_routes.routes[0]
    binding = route.resource_binding
    assert binding is not None
    base_request = build_clean_room_semantic_proposal_request(
        source_id=source.source_id,
        source_digest=source.source_digest,
        source_text=text,
        require_text_digest=False,
    )
    from memorii.core.memory_evolution.time_contracts import TimeInterval
    from memorii.core.semantic_ingestion.contracts import (
        LanguageConstructionPolicyAuthorityBundle,
        ParserConsensusPolicy,
        ScopeConsensusPolicy,
        SemanticProposalRequest,
        TemporalAttachmentConsensusPolicy,
        TemporalPolicySnapshot,
        TrustPolicySnapshot,
    )

    request = SemanticProposalRequest.create(
        **(
            base_request.model_dump(mode="python", exclude={"semantic_request_fingerprint"})
            | {"preparation_fingerprint": source.preparation_fingerprint, "language_route": route}
        )
    )
    parser_policy = ParserConsensusPolicy.create()
    scope_policy = ScopeConsensusPolicy.create()
    temporal_attachment_policy = TemporalAttachmentConsensusPolicy.create()
    consensus_values = {
        "parser_policy": parser_policy,
        "scope_policy": scope_policy,
        "temporal_attachment_policy": temporal_attachment_policy,
    }
    consensus = ConsensusPolicyAuthority(
        **consensus_values,
        authority_digest=__import__(
            "memorii.core.semantic_ingestion.contracts", fromlist=["contract_digest"]
        ).contract_digest(b"memorii.semantic-ingestion.consensus-policy-authority.v1", consensus_values),
    )
    interval = TimeInterval(start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2027, 1, 1, tzinfo=UTC))
    trust = TrustPolicySnapshot.create(
        policy_revision="normal-vector-trust", system_effective_interval=interval, rules=()
    )
    temporal = TemporalPolicySnapshot.create(
        policy_revision="normal-vector-temporal", system_effective_interval=interval, rules=()
    )
    registry_values = {
        "registry_revision": "normal-vector",
        "capabilities": (
            CapabilityRegistryEntry(
                capability_id="local", capability_fingerprint=request.proposal_capability_fingerprint
            ),
        ),
    }
    registry = CapabilityRegistrySnapshot(
        **registry_values,
        snapshot_digest=__import__(
            "memorii.core.semantic_ingestion.contracts", fromlist=["contract_digest"]
        ).contract_digest(b"memorii.semantic-ingestion.capability-registry-snapshot.v2", registry_values),
    )
    limits = {
        "policy_version": 1,
        "maximum_operations_per_source": 1,
        "maximum_groups_per_source": 1,
        "maximum_fixed_point_rounds": 1,
        "maximum_records_per_snapshot": 1,
        "maximum_partitions_per_snapshot": 1,
        "maximum_related_conflicts_per_group": 1,
        "maximum_attempts_per_group": 1,
        "maximum_read_set_extensions": 1,
        "maximum_reservations": 1,
        "maximum_lineage_entries": 1,
        "maximum_replay_artifacts": 1,
        "maximum_replay_bundle_bytes": 1,
        "replay_artifact_schema_registry_fingerprint": _digest("normal-vector-replay"),
        "maximum_decode_depth": 1,
    }
    execution_policy = GraphDependentExecutionPolicy(
        **limits,
        policy_digest=__import__(
            "memorii.core.semantic_ingestion.contracts", fromlist=["contract_digest"]
        ).contract_digest(b"memorii.semantic-ingestion.graph-dependent-execution-policy.v1", limits),
    )
    empty_policies = LanguageConstructionPolicyAuthorityBundle.create(policies=())
    authority = build_source_normalization_authority_bundle(
        source=source,
        publication=publication,
        proposal_request=request,
        consensus_policy_authority=consensus,
        language_construction_policies=empty_policies,
        temporal_policy=temporal,
        trust_policy=trust,
        capability_registry=registry,
        graph_dependent_execution_policy=execution_policy,
        retry_policy_fingerprint=_digest("normal-vector-retry"),
    )
    invocation = GraphFreeSourceNormalizationInvocation(
        operation_id=operation_id,
        source=source,
        source_authority_evidence=source.semantic_context,
        source_interval_evidence=None,
        policy_bundle=trust,
        authorization_read_set_provider=object(),
        operation_fence_binding=publication.operation_fence_binding,
    )
    proposal = ProviderSemanticProposal(
        mentions=(
            ProviderMention(local_id="alice", mention_quote="Alice", mention_context_quote=text),
            ProviderMention(local_id="globex", mention_quote="Globex", mention_context_quote=text),
        ),
        facts=(
            ProviderFact(
                local_id="fact",
                predicate_id="employs",
                subject_entity_ref="alice",
                object=ProviderEntityObject(entity_ref="globex"),
                assertion_quote=text,
                predicate_anchor_quote="works",
                polarity="positive",
                commitment="asserted",
                temporal_qualifier_quotes=(),
            ),
        ),
        abstained=False,
    )
    sealed = __import__(
        "tests.fixtures.semantic_ingestion.source_normalization_fixture_builder",
        fromlist=["seal_source_normalization_proposal_run"],
    ).seal_source_normalization_proposal_run(
        invocation=invocation,
        handoff=handoff,
        authority=authority,
        proposal_request=request,
        provider_proposal=proposal,
        retry_policy_fingerprint=_digest("normal-vector-retry"),
    )
    policies = build_normal_fact_language_policies(proposal_run=sealed)
    authority = build_source_normalization_authority_bundle(
        source=source,
        publication=publication,
        proposal_request=request,
        consensus_policy_authority=consensus,
        language_construction_policies=policies,
        temporal_policy=temporal,
        trust_policy=trust,
        capability_registry=registry,
        graph_dependent_execution_policy=execution_policy,
        retry_policy_fingerprint=_digest("normal-vector-retry"),
    )

    def span(name: str) -> object:

        return SourceBackedQuoteAuthority(source).resolve(name, request.owned_text, True)

    alice, works, globex = span("Alice"), span("works"), span("Globex")
    tokens = tuple(
        LinguisticToken.create(
            source_span=item,
            surface_text=name,
            lemma=name.lower().rstrip("s"),
            upos="PROPN" if name != "works" else "VERB",
            xpos=None,
            morphological_features=(),
            sentence_index=0,
            word_index=index,
            syntactic_word_index=index,
            multi_word_token_span=None,
        )
        for index, (name, item) in enumerate((("Alice", alice), ("works", works), ("Globex", globex)))
    )
    arcs = tuple(
        DependencyArc.create(
            dependent_token_id=token.token_id,
            governor_token_id=None if index == 0 else tokens[index - 1].token_id,
            relation="root" if index == 0 else "dep",
            enhanced=False,
        )
        for index, token in enumerate(tokens)
    )
    from memorii.core.semantic_ingestion.contracts import SourceMention

    mentions = tuple(
        sorted(
            (
                SourceMention.create(
                    kind="noun_phrase",
                    source_span=item,
                    token_ids=(token.token_id,),
                    head_token_id=token.token_id,
                    entity_label=None,
                    coordination_group_id=None,
                )
                for item, token in ((alice, tokens[0]), (globex, tokens[2]))
            ),
            key=lambda item: (item.source_span.reference_digest, item.kind, item.mention_digest),
        )
    )
    alice_mention = next(item for item in mentions if item.source_span == alice)
    clause = ClauseAnalysis.create(
        source_span=request.owned_text,
        parent_clause_id=None,
        predicate_head_token_id=tokens[1].token_id,
        predicate_span=works,
        arguments=(
            ClauseArgument.create(
                grammatical_role="subject",
                head_token_id=tokens[0].token_id,
                source_span=alice,
                mention_digest=alice_mention.mention_digest,
            ),
        ),
        voice="active",
        negation_token_ids=(),
        dependency_arc_ids=tuple(arc.arc_id for arc in arcs),
        morphological_polarity_features=(),
        mood_features=(),
        modality_features=(),
        quotation_evidence=None,
        coordination_group_ids=(),
        limitations=(),
    )

    def analysis(manifest_digest: str, fingerprint: str) -> LinguisticAnalysis:
        return LinguisticAnalysis.create(
            source_id=source.source_id,
            source_digest=source.source_digest,
            preparation_fingerprint=source.preparation_fingerprint,
            segment_id=route.segment_id,
            segment_language_route_digest=route.route_digest,
            analyzer_manifest_digest=manifest_digest,
            analyzer_fingerprint=fingerprint,
            language="en",
            tokens=tokens,
            mentions=mentions,
            clauses=(clause,),
            dependencies=arcs,
            status="complete",
            diagnostics=(),
        )

    primary = analysis(binding.stanza_analyzer_manifest_digest, _digest("normal-vector-stanza"))
    corroborating = analysis(binding.spacy_analyzer_manifest_digest, _digest("normal-vector-spacy"))
    reservation = ConsumedSourceNormalizationResourceReservation(
        source_id=source.source_id,
        source_digest=source.source_digest,
        preparation_fingerprint=source.preparation_fingerprint,
        operation_id=operation_id,
        operation_fence_digest=publication.operation_fence_binding.binding_digest,
        required_lane_manifest_digests=tuple(
            sorted(
                (
                    binding.stanza_analyzer_manifest_digest,
                    binding.spacy_analyzer_manifest_digest,
                    binding.predicate_event_manifest_digest,
                    binding.temporal_resolver_manifest_digest,
                )
            )
        ),
        resource_envelope_digest=_digest("normal-vector-reservation"),
        reservation_nonce="normal-vector",
        issued_server_time=datetime(2026, 1, 1, tzinfo=UTC),
        expires_server_time=datetime(2026, 1, 2, tzinfo=UTC),
        issued_monotonic_tick=1,
        expires_monotonic_tick=2,
        consumed_server_time=datetime(2026, 1, 1, tzinfo=UTC),
        consumed_monotonic_tick=1,
        consumption_digest=_digest("normal-vector-consumption"),
    )

    def manifest_digest(label: str) -> str:
        return contract_digest(b"memorii.fixture.source-normalization.manifest.v1", {"label": label})

    stanza_manifest = AnalyzerManifest.create(
        analyzer_id="fixture-stanza",
        analyzer_kind="stanza",
        library_version="1",
        resource_manifest_digest=manifest_digest("stanza-resource"),
        model_file_hashes=(manifest_digest("stanza-model"),),
        processor_configuration_digest=manifest_digest("stanza-processors"),
        adapter_version="1",
        supported_languages=("en",),
        analyzer_fingerprint=manifest_digest("stanza"),
    )
    spacy_manifest = AnalyzerManifest.create(
        analyzer_id="fixture-spacy",
        analyzer_kind="spacy",
        library_version="1",
        resource_manifest_digest=manifest_digest("spacy-resource"),
        model_file_hashes=(manifest_digest("spacy-model"),),
        processor_configuration_digest=manifest_digest("spacy-processors"),
        adapter_version="1",
        supported_languages=("en",),
        analyzer_fingerprint=manifest_digest("spacy"),
    )
    predicate_manifest = PredicateEventManifest.create(
        language="en",
        predicate_lemmas=("work",),
        inflection_table_digest=manifest_digest("predicate-inflections"),
        multi_token_forms=(),
    )
    temporal_manifest = TemporalResolverManifest.create(
        binary_digest=manifest_digest("duckling-binary"),
        ruleset_version="1",
        locale_map_digest=manifest_digest("duckling-locales"),
        timezone_policy_digest=manifest_digest("duckling-timezone"),
        adapter_schema_digest=manifest_digest("duckling-schema"),
        supported_construction_families=("absolute",),
    )
    assert (
        stanza_manifest.manifest_digest,
        spacy_manifest.manifest_digest,
        predicate_manifest.manifest_digest,
        temporal_manifest.manifest_digest,
    ) == (
        binding.stanza_analyzer_manifest_digest,
        binding.spacy_analyzer_manifest_digest,
        binding.predicate_event_manifest_digest,
        binding.temporal_resolver_manifest_digest,
    )
    producer = SealedSourceNormalizationEvidenceProducer.with_typed_interpreter(
        stanza=_ParserLane(stanza_manifest, primary),
        spacy=_ParserLane(spacy_manifest, corroborating),
        predicate_detector=_PredicateLane(predicate_manifest),
        duckling=_TemporalLane(temporal_manifest, source),
        locale_by_language={"en": "en_US"},
        timezone="UTC",
    )
    analyses = producer._analyses(invocation=invocation, authority=authority)
    assert analyses is not None
    predicate_events = producer._predicate_events(invocation=invocation, authority=authority)
    assert predicate_events is not None
    temporal_resolution = producer._temporal(invocation=invocation, authority=authority)
    assert temporal_resolution is not None
    assert (
        producer._interpretation_producer.produce(
            invocation=invocation,
            proposal_run=sealed,
            analyses=analyses,
            temporal_resolution=temporal_resolution,
            authority=authority,
        )
        is not None
    )
    inputs = producer.produce(invocation=invocation, proposal_run=sealed, authority=authority, resources=reservation)
    assert not hasattr(inputs, "reason")
    assert len(inputs.interpretation_bundle.scope_observations) == 2
    assert inputs.parser_consensus[0].status == "stable"
    assert len(inputs.interpretation_bundle.identity_partition_evidence.mentions) == 2
    request_value = GraphFreeSourceNormalizationStage.build_request(inputs)
    assert request_value.source_normalization_result.source_alignment.source_id == source.source_id
    assert request_value.required_artifact_digests == tuple(member.payload_digest for member in request_value.members)
    from memorii.core.semantic_ingestion.contracts import (
        SourceNormalizationAtomicWriteRequest,
        decode_semantic_contract,
        encode_semantic_contract,
    )

    revalidated_request = SourceNormalizationAtomicWriteRequest.model_validate(
        request_value.model_dump(mode="python")
    )
    assert revalidated_request == request_value
    assert revalidated_request.request_digest == request_value.request_digest
    encoded_request = encode_semantic_contract(request_value)
    assert encoded_request == encode_semantic_contract(revalidated_request)
    assert (
        decode_semantic_contract(encoded_request, SourceNormalizationAtomicWriteRequest)
        == revalidated_request
    )

    # This is the V2/generic closure vector.  Publication/recovery belongs to
    # the separate V3 declared-route vector; never reintroduce the removed V2
    # recovery-owner APIs here merely to make this generic test look end-to-end.


def test_normal_vector_closes_graph_free_source_normalization_request() -> None:
    _run_normal_vector()


def test_correction_vector_closes_two_temporal_roles_through_canonical_owners() -> None:
    """A correction retains both required temporal roles through atomic request closure."""
    text = "Alice worked for Globex; now works for Acme."
    source = build_manifest_bound_prepared_source(
        source_id="correction-vector-source", source_digest=_digest(text), source_text=text
    )
    operation_id = "correction-vector-operation"
    handoff = _handoff(source=source, operation_id=operation_id)
    publication = build_source_normalization_publication_fixture(
        source=source, operation_id=operation_id, bootstrap_handoff=handoff
    )
    route = source.segment_language_routes.routes[0]
    binding = route.resource_binding
    assert binding is not None
    base_request = build_clean_room_semantic_proposal_request(
        source_id=source.source_id, source_digest=source.source_digest, source_text=text
    )
    from memorii.core.memory_evolution.time_contracts import TimeInterval
    from memorii.core.semantic_ingestion.contracts import (
        AnalyzerManifest,
        LanguageConstructionPolicyAuthorityBundle,
        ParserConsensusPolicy,
        ScopeConsensusPolicy,
        SemanticProposalRequest,
        TemporalAttachmentConsensusPolicy,
        TemporalPolicySnapshot,
        TrustPolicySnapshot,
    )

    request = SemanticProposalRequest.create(
        **(
            base_request.model_dump(mode="python", exclude={"semantic_request_fingerprint"})
            | {"preparation_fingerprint": source.preparation_fingerprint, "language_route": route}
        )
    )
    consensus_values = {
        "parser_policy": ParserConsensusPolicy.create(),
        "scope_policy": ScopeConsensusPolicy.create(),
        "temporal_attachment_policy": TemporalAttachmentConsensusPolicy.create(),
    }
    consensus = ConsensusPolicyAuthority(
        **consensus_values,
        authority_digest=contract_digest(b"memorii.semantic-ingestion.consensus-policy-authority.v1", consensus_values),
    )
    interval = TimeInterval(start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2027, 1, 1, tzinfo=UTC))
    trust = TrustPolicySnapshot.create(
        policy_revision="correction-vector-trust", system_effective_interval=interval, rules=()
    )
    temporal = TemporalPolicySnapshot.create(
        policy_revision="correction-vector-temporal", system_effective_interval=interval, rules=()
    )
    registry_values = {
        "registry_revision": "correction-vector",
        "capabilities": (
            CapabilityRegistryEntry(
                capability_id="local", capability_fingerprint=request.proposal_capability_fingerprint
            ),
        ),
    }
    registry = CapabilityRegistrySnapshot(
        **registry_values,
        snapshot_digest=contract_digest(b"memorii.semantic-ingestion.capability-registry-snapshot.v2", registry_values),
    )
    limits = {
        "policy_version": 1,
        "maximum_operations_per_source": 1,
        "maximum_groups_per_source": 1,
        "maximum_fixed_point_rounds": 1,
        "maximum_records_per_snapshot": 1,
        "maximum_partitions_per_snapshot": 1,
        "maximum_related_conflicts_per_group": 1,
        "maximum_attempts_per_group": 1,
        "maximum_read_set_extensions": 1,
        "maximum_reservations": 1,
        "maximum_lineage_entries": 1,
        "maximum_replay_artifacts": 1,
        "maximum_replay_bundle_bytes": 1,
        "replay_artifact_schema_registry_fingerprint": _digest("correction-vector-replay"),
        "maximum_decode_depth": 1,
    }
    execution_policy = GraphDependentExecutionPolicy(
        **limits,
        policy_digest=contract_digest(b"memorii.semantic-ingestion.graph-dependent-execution-policy.v1", limits),
    )
    empty_policies = LanguageConstructionPolicyAuthorityBundle.create(policies=())
    authority = build_source_normalization_authority_bundle(
        source=source,
        publication=publication,
        proposal_request=request,
        consensus_policy_authority=consensus,
        language_construction_policies=empty_policies,
        temporal_policy=temporal,
        trust_policy=trust,
        capability_registry=registry,
        graph_dependent_execution_policy=execution_policy,
        retry_policy_fingerprint=_digest("correction-vector-retry"),
    )
    invocation = GraphFreeSourceNormalizationInvocation(
        operation_id=operation_id,
        source=source,
        source_authority_evidence=source.semantic_context,
        source_interval_evidence=None,
        policy_bundle=trust,
        authorization_read_set_provider=object(),
        operation_fence_binding=publication.operation_fence_binding,
    )
    corrected = ProviderFact(
        local_id="old",
        predicate_id="employs",
        subject_entity_ref="alice",
        object=ProviderEntityObject(entity_ref="globex"),
        assertion_quote=text,
        predicate_anchor_quote="worked",
        polarity="positive",
        commitment="asserted",
    )
    replacement = ProviderFact(
        local_id="new",
        predicate_id="employs",
        subject_entity_ref="alice",
        object=ProviderEntityObject(entity_ref="acme"),
        assertion_quote=text,
        predicate_anchor_quote="works",
        polarity="positive",
        commitment="asserted",
    )
    proposal = ProviderSemanticProposal(
        mentions=(
            ProviderMention(local_id="alice", mention_quote="Alice", mention_context_quote=text),
            ProviderMention(local_id="globex", mention_quote="Globex", mention_context_quote=text),
            ProviderMention(local_id="acme", mention_quote="Acme", mention_context_quote=text),
        ),
        corrections=(
            ProviderCorrection(
                local_id="correction",
                corrected_fact=corrected,
                replacement_fact=replacement,
                assertion_quote=text,
                correction_anchor_quote="works",
            ),
        ),
        abstained=False,
    )
    from tests.fixtures.semantic_ingestion.source_normalization_fixture_builder import (
        seal_source_normalization_proposal_run,
    )

    sealed = seal_source_normalization_proposal_run(
        invocation=invocation,
        handoff=handoff,
        authority=authority,
        proposal_request=request,
        provider_proposal=proposal,
        retry_policy_fingerprint=_digest("correction-vector-retry"),
    )
    policies = _correction_language_policies(proposal_run=sealed)
    authority = build_source_normalization_authority_bundle(
        source=source,
        publication=publication,
        proposal_request=request,
        consensus_policy_authority=consensus,
        language_construction_policies=policies,
        temporal_policy=temporal,
        trust_policy=trust,
        capability_registry=registry,
        graph_dependent_execution_policy=execution_policy,
        retry_policy_fingerprint=_digest("correction-vector-retry"),
    )

    def span(quote: str) -> object:

        return SourceBackedQuoteAuthority(source).resolve(quote, request.owned_text, True)

    alice, works, globex, acme = span("Alice"), span("works"), span("Globex"), span("Acme")
    token_data = (("Alice", alice), ("works", works), ("Globex", globex), ("Acme", acme))
    tokens = tuple(
        LinguisticToken.create(
            source_span=item,
            surface_text=name,
            lemma="work" if name == "works" else name.lower(),
            upos="VERB" if name == "works" else "PROPN",
            xpos=None,
            morphological_features=(),
            sentence_index=0,
            word_index=index,
            syntactic_word_index=index,
            multi_word_token_span=None,
        )
        for index, (name, item) in enumerate(token_data)
    )
    arcs = tuple(
        DependencyArc.create(
            dependent_token_id=token.token_id,
            governor_token_id=None if index == 0 else tokens[index - 1].token_id,
            relation="root" if index == 0 else "dep",
            enhanced=False,
        )
        for index, token in enumerate(tokens)
    )
    from memorii.core.semantic_ingestion.contracts import SourceMention

    mentions = tuple(
        sorted(
            (
                SourceMention.create(
                    kind="noun_phrase",
                    source_span=item,
                    token_ids=(token.token_id,),
                    head_token_id=token.token_id,
                    entity_label=None,
                    coordination_group_id=None,
                )
                for item, token in ((alice, tokens[0]), (globex, tokens[2]), (acme, tokens[3]))
            ),
            key=lambda item: (item.source_span.reference_digest, item.kind, item.mention_digest),
        )
    )
    alice_mention = next(item for item in mentions if item.source_span == alice)
    clause = ClauseAnalysis.create(
        source_span=request.owned_text,
        parent_clause_id=None,
        predicate_head_token_id=tokens[1].token_id,
        predicate_span=works,
        arguments=(
            ClauseArgument.create(
                grammatical_role="subject",
                head_token_id=tokens[0].token_id,
                source_span=alice,
                mention_digest=alice_mention.mention_digest,
            ),
        ),
        voice="active",
        negation_token_ids=(),
        dependency_arc_ids=tuple(arc.arc_id for arc in arcs),
        morphological_polarity_features=(),
        mood_features=(),
        modality_features=(),
        quotation_evidence=None,
        coordination_group_ids=(),
        limitations=(),
    )

    def analysis(manifest_digest: str, fingerprint: str) -> LinguisticAnalysis:
        return LinguisticAnalysis.create(
            source_id=source.source_id,
            source_digest=source.source_digest,
            preparation_fingerprint=source.preparation_fingerprint,
            segment_id=route.segment_id,
            segment_language_route_digest=route.route_digest,
            analyzer_manifest_digest=manifest_digest,
            analyzer_fingerprint=fingerprint,
            language="en",
            tokens=tokens,
            mentions=mentions,
            clauses=(clause,),
            dependencies=arcs,
            status="complete",
            diagnostics=(),
        )

    primary = analysis(binding.stanza_analyzer_manifest_digest, _digest("correction-vector-stanza"))
    corroborating = analysis(binding.spacy_analyzer_manifest_digest, _digest("correction-vector-spacy"))
    reservation = ConsumedSourceNormalizationResourceReservation(
        source_id=source.source_id,
        source_digest=source.source_digest,
        preparation_fingerprint=source.preparation_fingerprint,
        operation_id=operation_id,
        operation_fence_digest=publication.operation_fence_binding.binding_digest,
        required_lane_manifest_digests=tuple(
            sorted(
                (
                    binding.stanza_analyzer_manifest_digest,
                    binding.spacy_analyzer_manifest_digest,
                    binding.predicate_event_manifest_digest,
                    binding.temporal_resolver_manifest_digest,
                )
            )
        ),
        resource_envelope_digest=_digest("correction-vector-reservation"),
        reservation_nonce="correction-vector",
        issued_server_time=datetime(2026, 1, 1, tzinfo=UTC),
        expires_server_time=datetime(2026, 1, 2, tzinfo=UTC),
        issued_monotonic_tick=1,
        expires_monotonic_tick=2,
        consumed_server_time=datetime(2026, 1, 1, tzinfo=UTC),
        consumed_monotonic_tick=1,
        consumption_digest=_digest("correction-vector-consumption"),
    )

    def manifest_digest(label: str) -> str:
        return contract_digest(b"memorii.fixture.source-normalization.manifest.v1", {"label": label})

    stanza_manifest = AnalyzerManifest.create(
        analyzer_id="fixture-stanza",
        analyzer_kind="stanza",
        library_version="1",
        resource_manifest_digest=manifest_digest("stanza-resource"),
        model_file_hashes=(manifest_digest("stanza-model"),),
        processor_configuration_digest=manifest_digest("stanza-processors"),
        adapter_version="1",
        supported_languages=("en",),
        analyzer_fingerprint=manifest_digest("stanza"),
    )
    spacy_manifest = AnalyzerManifest.create(
        analyzer_id="fixture-spacy",
        analyzer_kind="spacy",
        library_version="1",
        resource_manifest_digest=manifest_digest("spacy-resource"),
        model_file_hashes=(manifest_digest("spacy-model"),),
        processor_configuration_digest=manifest_digest("spacy-processors"),
        adapter_version="1",
        supported_languages=("en",),
        analyzer_fingerprint=manifest_digest("spacy"),
    )
    predicate_manifest = PredicateEventManifest.create(
        language="en",
        predicate_lemmas=("work",),
        inflection_table_digest=manifest_digest("predicate-inflections"),
        multi_token_forms=(),
    )
    temporal_manifest = TemporalResolverManifest.create(
        binary_digest=manifest_digest("duckling-binary"),
        ruleset_version="1",
        locale_map_digest=manifest_digest("duckling-locales"),
        timezone_policy_digest=manifest_digest("duckling-timezone"),
        adapter_schema_digest=manifest_digest("duckling-schema"),
        supported_construction_families=("absolute",),
    )
    assert (
        stanza_manifest.manifest_digest,
        spacy_manifest.manifest_digest,
        predicate_manifest.manifest_digest,
        temporal_manifest.manifest_digest,
    ) == (
        binding.stanza_analyzer_manifest_digest,
        binding.spacy_analyzer_manifest_digest,
        binding.predicate_event_manifest_digest,
        binding.temporal_resolver_manifest_digest,
    )
    producer = SealedSourceNormalizationEvidenceProducer.with_typed_interpreter(
        stanza=_ParserLane(stanza_manifest, primary),
        spacy=_ParserLane(spacy_manifest, corroborating),
        predicate_detector=_PredicateLane(predicate_manifest),
        duckling=_TemporalLane(temporal_manifest, source),
        locale_by_language={"en": "en_US"},
        timezone="UTC",
    )
    inputs = producer.produce(invocation=invocation, proposal_run=sealed, authority=authority, resources=reservation)
    assert not hasattr(inputs, "reason")
    assert len(inputs.interpretation_bundle.scope_observations) == 2
    assert len(inputs.interpretation_bundle.temporal_attachment_observations) == 4
    assert {
        selection.temporal_role
        for selection in inputs.consensus_policy_selections.selections
        if selection.kind == "temporal_attachment"
    } == {"replacement", "transition"}
    assert inputs.parser_consensus[0].status == "stable"
    assert len(inputs.interpretation_bundle.identity_partition_evidence.mentions) == 3
    request_value = GraphFreeSourceNormalizationStage.build_request(inputs)
    assert request_value.required_artifact_digests == tuple(member.payload_digest for member in request_value.members)

    temporal_selections = tuple(
        selection
        for selection in inputs.consensus_policy_selections.selections
        if selection.kind == "temporal_attachment"
    )
    for selections in (
        tuple(
            selection
            for selection in inputs.consensus_policy_selections.selections
            if selection.temporal_role != "transition"
        ),
        tuple(
            selection if selection is not temporal_selections[1] else temporal_selections[0]
            for selection in inputs.consensus_policy_selections.selections
        ),
        tuple(reversed(inputs.consensus_policy_selections.selections)),
    ):
        malformed_bundle = type(inputs.consensus_policy_selections).model_construct(
            schema_version=2,
            selections=selections,
            bundle_digest=inputs.consensus_policy_selections.bundle_digest,
        )
        with pytest.raises(ValueError, match="role-complete"):
            GraphFreeSourceNormalizationStage.build_request(
                type(inputs)(**{**inputs.__dict__, "consensus_policy_selections": malformed_bundle})
            )
    missing_lane = SealedSourceNormalizationEvidenceProducer.with_typed_interpreter(
        stanza=_ParserLane(stanza_manifest, primary),
        spacy=_ParserLane(spacy_manifest, primary),
        predicate_detector=_PredicateLane(predicate_manifest),
        duckling=_TemporalLane(temporal_manifest, source),
        locale_by_language={"en": "en_US"},
        timezone="UTC",
    ).produce(invocation=invocation, proposal_run=sealed, authority=authority, resources=reservation)
    assert missing_lane.reason == "analysis_unavailable"

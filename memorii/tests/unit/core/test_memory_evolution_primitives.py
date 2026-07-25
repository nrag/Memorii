from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution import (
    ClaimKey,
    EnglishRuleMemoryExtractor,
    EntityIdentityDecision,
    EntityIdentityDecisionType,
    EntityLinkState,
    EntityMention,
    EntityResolutionOutcome,
    EntityResolutionService,
    EntityType,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractionFailureCode,
    ExtractionRun,
    ExtractionRunStatus,
    ExtractionTriggerMode,
    FinalExtractionSource,
    MemoryEvolutionMutationValidationError,
    MemoryEvolutionService,
    MemoryEvolutionValidator,
    MemoryGraphEdgeType,
    MemoryScope,
    PredicateRegistry,
    ProviderAttemptStatus,
    RetrievalView,
    SourceModality,
    SourceModalityClassifier,
    build_memory_extractor_from_env,
)
from memorii.core.memory_evolution.claim_policy import claim_precedence
from memorii.core.memory_evolution.extraction import models_from_llm_output
from memorii.core.memory_evolution.extraction_contracts import (
    MemoryExtractionOutput,
    MemoryExtractionRunError,
)
from memorii.core.memory_evolution.modality import classify_and_mark_observation
from memorii.core.memory_evolution.models import ConfidenceComponents
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.domain.enums import CommitStatus, MemoryDomain, SourceType


def _record(
    memory_id: str,
    text: str,
    *,
    source_kind: str = "user",
    timestamp: datetime | None = None,
    task_id: str | None = "task:evolution",
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.TRANSCRIPT,
        text=text,
        content={"text": text},
        status=CommitStatus.COMMITTED,
        source_kind=source_kind,
        timestamp=timestamp or datetime(2026, 1, 1, tzinfo=UTC),
        task_id=task_id,
        is_raw_event=True,
    )


def test_ambiguous_entity_reference_rejects_atomic_mutation() -> None:
    plane = MemoryPlaneService()
    baseline = _record("tx:baseline", "Existing source record.")
    plane.stage_record(baseline)
    service = MemoryEvolutionService(
        memory_plane=plane,
        extractor=_UnresolvedClaimExtractor(),
        entity_resolver=_AbstainingEntityResolver(),
    )
    before = [record.model_dump(mode="json") for record in plane.list_records()]

    with pytest.raises(
        MemoryEvolutionMutationValidationError,
        match="unresolved_entity_reference:claim",
    ):
        service.evolve_records([_record("tx:ambiguous", "Atlas status is active.")])

    assert [record.model_dump(mode="json") for record in plane.list_records()] == before
    assert service.retrieve_graph_snapshot().nodes == []
    assert service.retrieve_graph_snapshot().edges == []


def test_successful_extraction_cannot_silently_omit_an_eligible_source() -> None:
    class EmptySuccessfulExtractor:
        provider = "test"
        model = None
        prompt_hash = None

        def extract(self, observations):
            return (
                ExtractionRun(
                    extraction_run_id="run:empty-success",
                    provider=self.provider,
                    input_source_ids=[observation.source_id for observation in observations],
                ),
                [],
                [],
                [],
            )

    plane = MemoryPlaneService()
    service = MemoryEvolutionService(
        memory_plane=plane,
        extractor=EmptySuccessfulExtractor(),
    )

    with pytest.raises(MemoryExtractionRunError, match="failed:output_validation") as exc:
        service.evolve_records([_record("tx:omitted", "Atlas owner is Alice.")])

    assert exc.value.run.errors == ["source_unaccounted:tx:omitted"]
    assert service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS) == []


class _EntitySequenceExtractor:
    provider = "test"
    model = None
    prompt_hash = None

    def extract(self, observations):
        observation = observations[0]
        is_service = "service" in observation.text.casefold()
        entity_id = "ent:atlas-service" if is_service else "ent:atlas-project"
        entity_type = EntityType.SERVICE if is_service else EntityType.PROJECT
        aliases = ["Atlas", "Atlas service"] if is_service else ["Atlas"]
        mention = EntityMention(
            entity_id=entity_id,
            mention_text="Atlas Platform Service" if is_service else "Atlas Billing Migration",
            normalized_name="atlas platform service" if is_service else "atlas billing migration",
            aliases=aliases,
            entity_type=entity_type,
            evidence_spans=[
                EvidenceSpan(
                    source_id=observation.source_id,
                    quote=observation.text,
                    source_type=observation.source_type,
                    timestamp=observation.timestamp,
                )
            ],
            confidence=0.9,
        )
        return (
            ExtractionRun(
                extraction_run_id=f"run:{observation.source_id}",
                provider=self.provider,
                input_source_ids=[observation.source_id],
                entity_ids=[entity_id],
            ),
            [mention],
            [],
            [],
        )


class _StableClaimIdExtractor:
    provider = "test"
    model = None
    prompt_hash = None

    def extract(self, observations):
        observation = observations[0]
        span = EvidenceSpan(
            source_id=observation.source_id,
            quote="Atlas owner is Bob.",
            source_type=observation.source_type,
            timestamp=observation.timestamp,
        )
        entities = [
            EntityMention(
                entity_id="ent:atlas",
                mention_text="Atlas",
                normalized_name="atlas",
                entity_type=EntityType.PROJECT,
                evidence_spans=[span],
                confidence=0.9,
                scope=MemoryScope(task_id="task:evolution"),
            ),
            EntityMention(
                entity_id="ent:bob",
                mention_text="Bob",
                normalized_name="bob",
                entity_type=EntityType.PERSON,
                evidence_spans=[span],
                confidence=0.9,
                scope=MemoryScope(task_id="task:evolution"),
            ),
        ]
        claim = ExtractedClaim(
            claim_id="claim:atlas-owner-bob",
            claim_key=ClaimKey(
                subject_entity_id="ent:atlas",
                predicate_id="owner",
                scope=MemoryScope(task_id="task:evolution"),
            ),
            object_value="Bob",
            object_entity_id="ent:bob",
            valid_from=observation.timestamp,
            evidence_spans=[span],
            confidence=ConfidenceComponents(
                extraction=0.9,
                evidence=0.9,
                source_trust=0.9,
                calibrated=0.9,
            ),
            extraction_run_id=f"run:{observation.source_id}",
        )
        return (
            ExtractionRun(
                extraction_run_id=f"run:{observation.source_id}",
                provider=self.provider,
                input_source_ids=[observation.source_id],
                entity_ids=[entity.entity_id for entity in entities],
                claim_ids=[claim.claim_id],
            ),
            entities,
            [claim],
            [],
        )


class _UnresolvedClaimExtractor:
    provider = "test"
    model = None
    prompt_hash = None

    def extract(self, observations):
        observation = observations[0]
        scope = MemoryScope(task_id="task:evolution")
        span = EvidenceSpan(
            source_id=observation.source_id,
            quote=observation.text,
            source_type=observation.source_type,
            timestamp=observation.timestamp,
        )
        mention = EntityMention(
            entity_id="mention:ambiguous-atlas",
            mention_text="Atlas",
            normalized_name="atlas",
            entity_type=EntityType.PROJECT,
            evidence_spans=[span],
            confidence=0.9,
            scope=scope,
        )
        claim = ExtractedClaim(
            claim_id="claim:ambiguous-atlas-status",
            claim_key=ClaimKey(
                subject_entity_id=mention.entity_id,
                predicate_id="status",
                scope=scope,
            ),
            object_value="active",
            valid_from=observation.timestamp,
            evidence_spans=[span],
            confidence=ConfidenceComponents(
                extraction=0.9,
                evidence=0.9,
                source_trust=0.9,
                calibrated=0.9,
            ),
            extraction_run_id=f"run:{observation.source_id}",
        )
        return (
            ExtractionRun(
                extraction_run_id=f"run:{observation.source_id}",
                provider=self.provider,
                input_source_ids=[observation.source_id],
                entity_ids=[mention.entity_id],
                claim_ids=[claim.claim_id],
            ),
            [mention],
            [claim],
            [],
        )


class _AbstainingEntityResolver(EntityResolutionService):
    def resolve_mentions(self, mentions, existing_links):
        del existing_links
        return EntityResolutionOutcome(
            decisions=[
                EntityIdentityDecision(
                    decision_id="decision:ambiguous-atlas",
                    decision_type=EntityIdentityDecisionType.ABSTAIN,
                    mention_entity_id=mention.entity_id,
                    candidate_entity_ids=["entity:atlas-project", "entity:atlas-service"],
                    evidence_source_ids=[
                        span.source_id
                        for span in mention.evidence_spans
                    ],
                    scope=mention.scope,
                    confidence=0.0,
                    rationale="two grounded scoped candidates remain ambiguous",
                    failure_code="entity_identity_ambiguous",
                )
                for mention in mentions
            ]
        )


class _RequestLocalIdentityExtractor:
    provider = "test"
    model = None
    prompt_hash = None

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, observations):
        self.calls += 1
        observation = observations[0]
        project_id = f"request:{self.calls}:atlas"
        project_name = "Atlas" if self.calls == 1 else "Atlas Billing Migration"
        person_name = "Bob" if self.calls == 1 else "Alice"
        person_id = f"request:{self.calls}:{person_name.casefold()}"
        span = EvidenceSpan(
            source_id=observation.source_id,
            quote=observation.text,
            source_type=observation.source_type,
            timestamp=observation.timestamp,
        )
        scope = MemoryScope(task_id="task:evolution")
        entities = [
            EntityMention(
                entity_id=project_id,
                mention_text=project_name,
                normalized_name=project_name.casefold(),
                aliases=([project_name, "Atlas"] if self.calls > 1 else [project_name]),
                entity_type=EntityType.PROJECT,
                evidence_spans=[span],
                confidence=0.9,
                scope=scope,
            ),
            EntityMention(
                entity_id=person_id,
                mention_text=person_name,
                normalized_name=person_name.casefold(),
                aliases=[person_name],
                entity_type=EntityType.PERSON,
                evidence_spans=[span],
                confidence=0.9,
                scope=scope,
            ),
        ]
        claim = ExtractedClaim(
            claim_id=f"claim:{self.calls}:owner",
            claim_key=ClaimKey(
                subject_entity_id=project_id,
                predicate_id="owner",
                scope=scope,
            ),
            object_value=person_name,
            object_entity_id=person_id,
            valid_from=observation.timestamp,
            evidence_spans=[span],
            confidence=ConfidenceComponents(
                extraction=0.9,
                evidence=0.9,
                source_trust=0.9,
                calibrated=0.9,
            ),
            extraction_run_id=f"run:{self.calls}",
        )
        return (
            ExtractionRun(
                extraction_run_id=f"run:{self.calls}",
                provider=self.provider,
                input_source_ids=[observation.source_id],
                entity_ids=[project_id, person_id],
                claim_ids=[claim.claim_id],
            ),
            entities,
            [claim],
            [],
        )


class _RequestLocalActionRelationExtractor:
    provider = "test"
    model = None
    prompt_hash = None

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, observations):
        self.calls += 1
        observation = observations[0]
        work_id = f"request:{self.calls}:migration"
        blocker_id = f"request:{self.calls}:oauth"
        span = EvidenceSpan(
            source_id=observation.source_id,
            quote=observation.text,
            source_type=observation.source_type,
            timestamp=observation.timestamp,
        )
        scope = MemoryScope(task_id="task:evolution")
        entities = [
            EntityMention(
                entity_id=work_id,
                mention_text="Atlas migration",
                normalized_name="atlas migration",
                aliases=["Atlas migration"],
                entity_type=EntityType.TASK,
                evidence_spans=[span],
                confidence=0.9,
                scope=scope,
            ),
            EntityMention(
                entity_id=blocker_id,
                mention_text="OAuth rollout",
                normalized_name="oauth rollout",
                aliases=["OAuth rollout"],
                entity_type=EntityType.TASK,
                evidence_spans=[span],
                confidence=0.9,
                scope=scope,
            ),
        ]
        action = ExtractedAction(
            action_id=f"action:{self.calls}:migration",
            action_type="work_state",
            target_entity_ids=[work_id],
            status="blocked",
            dependency_entity_ids=[blocker_id],
            blocking_entity_ids=[blocker_id],
            timestamp=observation.timestamp,
            scope=scope,
            evidence_spans=[span],
            extraction_run_id=f"run:{self.calls}",
        )
        return (
            ExtractionRun(
                extraction_run_id=f"run:{self.calls}",
                provider=self.provider,
                input_source_ids=[observation.source_id],
                entity_ids=[work_id, blocker_id],
                action_ids=[action.action_id],
            ),
            entities,
            [],
            [action],
        )


def test_claim_key_is_stable_and_excludes_object_value() -> None:
    first = ClaimKey(
        subject_entity_id="ent:atlas",
        predicate_id="owner",
        scope=MemoryScope(task_id="task:1"),
        qualifier_key="default",
    )
    second = ClaimKey(
        subject_entity_id="ent:atlas",
        predicate_id="owner",
        scope=MemoryScope(task_id="task:1"),
        qualifier_key="default",
    )

    assert first.stable_id() == second.stable_id()
    assert first.stable_id() == "ent:atlas|owner|||task:1|default"


def test_memory_scope_visibility_is_hierarchical_and_identity_safe() -> None:
    request_scope = MemoryScope(
        task_id="task:deploy",
        session_id="session:1",
        user_id="user:1",
    )

    assert request_scope.can_read(MemoryScope())
    assert request_scope.can_read(MemoryScope(user_id="user:1"))
    assert request_scope.can_read(MemoryScope(session_id="session:1", user_id="user:1"))
    assert request_scope.can_read(
        MemoryScope(
            task_id="task:deploy",
            session_id="session:1",
            user_id="user:1",
        )
    )
    assert not request_scope.can_read(MemoryScope(session_id="session:2", user_id="user:1"))
    assert not request_scope.can_read(MemoryScope(user_id="user:2"))
    assert not MemoryScope().can_read(MemoryScope(user_id="user:1"))

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        MemoryScope.model_validate({"scope_key": "task:other", "task_id": "task:deploy"})


def test_entity_resolution_keeps_same_name_entities_distinct_and_uses_injected_clock() -> None:
    now = datetime(2026, 2, 1, tzinfo=UTC)
    resolver = EntityResolutionService(now_provider=lambda: now)
    mentions = [
        EntityMention(
            entity_id="ent:project",
            mention_text="Atlas",
            normalized_name="atlas",
            entity_type=EntityType.PROJECT,
            evidence_spans=[
                EvidenceSpan(
                    source_id="event:project",
                    quote="Atlas project",
                    source_type=SourceType.USER,
                    timestamp=now,
                )
            ],
            confidence=0.9,
        ),
        EntityMention(
            entity_id="ent:service",
            mention_text="Atlas",
            normalized_name="atlas",
            entity_type=EntityType.SERVICE,
            evidence_spans=[
                EvidenceSpan(
                    source_id="event:service",
                    quote="Atlas service",
                    source_type=SourceType.USER,
                    timestamp=now,
                )
            ],
            confidence=0.8,
        ),
    ]

    outcome = resolver.resolve_mentions(mentions, [])

    assert {link.canonical_entity_id for link in outcome.links} == {"ent:project", "ent:service"}
    assert outcome.links[1].created_at == now
    assert outcome.links[1].lineage_parent_entity_id == "ent:project"
    assert [decision.decision_type.value for decision in outcome.decisions] == [
        "create_distinct",
        "split_existing",
    ]
    assert [transition.transition_type.value for transition in outcome.transitions] == ["entity_split"]


def test_entity_resolution_persists_same_entity_independently_by_scope() -> None:
    resolver = EntityResolutionService(now_provider=lambda: datetime(2026, 2, 1, tzinfo=UTC))
    mentions = [
        EntityMention(
            entity_id="ent:atlas",
            mention_text="Atlas",
            normalized_name="atlas",
            confidence=0.9,
        ),
        EntityMention(
            entity_id="ent:atlas",
            mention_text="Atlas",
            normalized_name="atlas",
            confidence=0.9,
            scope=MemoryScope(task_id="task:incident"),
        ),
    ]

    links = resolver.resolve_mentions(mentions, []).links

    assert len(links) == 2
    assert len({link.link_id for link in links}) == 2
    assert {link.scope.scope_key for link in links} == {"global", "task:incident"}
    assert (
        resolver.link_for_entity(
            "ent:atlas",
            links,
            scope=MemoryScope(task_id="task:incident"),
        )
        == links[1]
    )


def test_entity_resolution_reuses_unique_typed_alias_across_request_local_mentions() -> None:
    now = datetime(2026, 2, 1, tzinfo=UTC)
    resolver = EntityResolutionService(now_provider=lambda: now)
    first = EntityMention(
        entity_id="mention:request-1:atlas",
        mention_text="Atlas billing migration",
        normalized_name="atlas billing migration",
        entity_type=EntityType.PROJECT,
        confidence=0.8,
    )
    existing = resolver.resolve_mentions([first], []).links
    second = EntityMention(
        entity_id="mention:request-2:atlas",
        mention_text="Atlas Billing Migration",
        normalized_name="atlas billing migration",
        entity_type=EntityType.PROJECT,
        aliases=["Atlas billing migration"],
        confidence=0.9,
    )

    outcome = resolver.resolve_mentions([second], existing)

    assert len(outcome.links) == 1
    assert outcome.links[0].canonical_entity_id == first.entity_id
    assert outcome.decisions[0].decision_type == EntityIdentityDecisionType.REUSE_EXISTING
    assert outcome.decisions[0].resolved_entity_id == first.entity_id


def test_entity_resolution_converges_on_explicit_scoped_alias() -> None:
    resolver = EntityResolutionService(now_provider=lambda: datetime(2026, 2, 1, tzinfo=UTC))
    existing = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="request:1:atlas",
                mention_text="Atlas",
                normalized_name="atlas",
                entity_type=EntityType.PROJECT,
                confidence=0.9,
            )
        ],
        [],
    ).links

    outcome = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="request:2:atlas",
                mention_text="Atlas Billing Migration",
                normalized_name="atlas billing migration",
                aliases=["Atlas"],
                entity_type=EntityType.PROJECT,
                confidence=0.9,
            )
        ],
        existing,
    )

    assert len(outcome.links) == 1
    assert outcome.links[0].canonical_entity_id == "request:1:atlas"
    assert outcome.links[0].normalized_name == "atlas billing migration"
    assert outcome.decisions[0].decision_type == EntityIdentityDecisionType.REUSE_EXISTING


def test_entity_resolution_does_not_merge_same_type_entities_from_descriptive_overlap() -> None:
    now = datetime(2026, 2, 1, tzinfo=UTC)
    resolver = EntityResolutionService(now_provider=lambda: now)
    existing = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="request:1:atlas",
                mention_text="Atlas",
                normalized_name="atlas",
                entity_type=EntityType.PROJECT,
                confidence=0.9,
                evidence_spans=[
                    EvidenceSpan(
                        source_id="event:definition",
                        quote="Atlas is the billing migration project",
                        source_type=SourceType.USER,
                        timestamp=now,
                    )
                ],
            )
        ],
        [],
    ).links

    outcome = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="request:2:atlas-billing",
                mention_text="Atlas Storage Migration",
                normalized_name="atlas storage migration",
                entity_type=EntityType.PROJECT,
                confidence=0.9,
                evidence_spans=[
                    EvidenceSpan(
                        source_id="event:owner",
                        quote="Atlas storage migration project owner is Nadia",
                        source_type=SourceType.TOOL,
                        timestamp=now,
                    )
                ],
            )
        ],
        existing,
    )

    assert [link.canonical_entity_id for link in outcome.links] == [
        "request:2:atlas-billing"
    ]
    assert outcome.decisions[0].decision_type == EntityIdentityDecisionType.CREATE_DISTINCT


def test_entity_resolution_does_not_use_lexical_overlap_without_typed_grounding() -> None:
    now = datetime(2026, 2, 1, tzinfo=UTC)
    resolver = EntityResolutionService(now_provider=lambda: now)
    existing = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="ent:sam",
                mention_text="Sam",
                normalized_name="sam",
                entity_type=EntityType.PERSON,
                confidence=0.9,
                evidence_spans=[
                    EvidenceSpan(
                        source_id="event:sam",
                        quote="Sam joined the review",
                        source_type=SourceType.USER,
                        timestamp=now,
                    )
                ],
            )
        ],
        [],
    ).links

    outcome = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="ent:sam-rivera",
                mention_text="Sam Rivera",
                normalized_name="sam rivera",
                entity_type=EntityType.PERSON,
                confidence=0.9,
                evidence_spans=[
                    EvidenceSpan(
                        source_id="event:sam-rivera",
                        quote="Sam Rivera joined the review",
                        source_type=SourceType.USER,
                        timestamp=now,
                    )
                ],
            )
        ],
        existing,
    )

    assert outcome.decisions[0].decision_type == EntityIdentityDecisionType.CREATE_DISTINCT
    assert outcome.links[0].canonical_entity_id == "ent:sam-rivera"


def test_entity_resolution_requires_whole_word_type_grounding() -> None:
    now = datetime(2026, 2, 1, tzinfo=UTC)
    resolver = EntityResolutionService(now_provider=lambda: now)
    existing = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="ent:atlas",
                mention_text="Atlas",
                normalized_name="atlas",
                entity_type=EntityType.SERVICE,
                confidence=0.9,
                evidence_spans=[
                    EvidenceSpan(
                        source_id="event:atlas",
                        quote="Atlas passed the serviceability review",
                        source_type=SourceType.USER,
                        timestamp=now,
                    )
                ],
            )
        ],
        [],
    ).links

    outcome = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="ent:atlas-service",
                mention_text="Atlas Service",
                normalized_name="atlas service",
                entity_type=EntityType.SERVICE,
                confidence=0.9,
                evidence_spans=[
                    EvidenceSpan(
                        source_id="event:atlas-service",
                        quote="Atlas service is available",
                        source_type=SourceType.USER,
                        timestamp=now,
                    )
                ],
            )
        ],
        existing,
    )

    assert outcome.decisions[0].decision_type == EntityIdentityDecisionType.CREATE_DISTINCT


def test_entity_resolution_splits_grounded_descriptive_alias_with_distinct_type() -> None:
    now = datetime(2026, 2, 1, tzinfo=UTC)
    resolver = EntityResolutionService(now_provider=lambda: now)
    existing = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="ent:atlas-project",
                mention_text="Atlas",
                normalized_name="atlas",
                entity_type=EntityType.PROJECT,
                confidence=0.9,
                evidence_spans=[
                    EvidenceSpan(
                        source_id="event:project",
                        quote="Atlas is the billing migration project",
                        source_type=SourceType.USER,
                        timestamp=now,
                    )
                ],
            )
        ],
        [],
    ).links

    outcome = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="ent:atlas-service",
                mention_text="Atlas service",
                normalized_name="atlas service",
                aliases=["Atlas"],
                entity_type=EntityType.SERVICE,
                confidence=0.9,
                evidence_spans=[
                    EvidenceSpan(
                        source_id="event:service",
                        quote="Atlas service is the internal platform service",
                        source_type=SourceType.USER,
                        timestamp=now,
                    )
                ],
            )
        ],
        existing,
    )

    assert outcome.decisions[0].decision_type == EntityIdentityDecisionType.SPLIT_EXISTING
    assert outcome.decisions[0].parent_entity_id == "ent:atlas-project"
    assert outcome.links[0].canonical_entity_id == "ent:atlas-service"


def test_entity_resolution_alias_closure_is_invariant_to_mention_permutation() -> None:
    resolver = EntityResolutionService(now_provider=lambda: datetime(2026, 2, 1, tzinfo=UTC))
    mentions = [
        EntityMention(
            entity_id="request:z:atlas-billing",
            mention_text="Atlas Billing Migration",
            normalized_name="atlas billing migration",
            aliases=["Atlas"],
            entity_type=EntityType.PROJECT,
            confidence=0.9,
        ),
        EntityMention(
            entity_id="request:a:atlas",
            mention_text="Atlas",
            normalized_name="atlas",
            aliases=["Atlas"],
            entity_type=EntityType.PROJECT,
            confidence=0.9,
        ),
    ]

    def resolved_ids(items: list[EntityMention]) -> dict[str, str | None]:
        outcome = resolver.resolve_mentions(items, [])
        return {decision.mention_entity_id: decision.resolved_entity_id for decision in outcome.decisions}

    forward = resolved_ids(mentions)
    reverse = resolved_ids(list(reversed(mentions)))

    assert forward == reverse
    assert set(forward.values()) == {"request:a:atlas"}


def test_entity_resolution_does_not_conflate_structured_siblings_or_people() -> None:
    resolver = EntityResolutionService(now_provider=lambda: datetime(2026, 2, 1, tzinfo=UTC))
    existing = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="ent:atlas-migration",
                mention_text="Atlas Migration",
                normalized_name="atlas migration",
                entity_type=EntityType.PROJECT,
                confidence=0.9,
            ),
            EntityMention(
                entity_id="ent:sam",
                mention_text="Sam",
                normalized_name="sam",
                entity_type=EntityType.PERSON,
                confidence=0.9,
            ),
        ],
        [],
    ).links

    outcome = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="ent:atlas-analytics",
                mention_text="Atlas Analytics",
                normalized_name="atlas analytics",
                entity_type=EntityType.PROJECT,
                confidence=0.9,
            ),
            EntityMention(
                entity_id="ent:sam-rivera",
                mention_text="Sam Rivera",
                normalized_name="sam rivera",
                entity_type=EntityType.PERSON,
                confidence=0.9,
            ),
        ],
        existing,
    )

    assert [decision.decision_type for decision in outcome.decisions] == [
        EntityIdentityDecisionType.CREATE_DISTINCT,
        EntityIdentityDecisionType.CREATE_DISTINCT,
    ]


def test_entity_resolution_abstains_when_typed_alias_is_not_unique() -> None:
    resolver = EntityResolutionService(now_provider=lambda: datetime(2026, 2, 1, tzinfo=UTC))
    existing = [
        resolver.resolve_mentions(
            [
                EntityMention(
                    entity_id="ent:sam-1",
                    mention_text="Sam",
                    normalized_name="sam",
                    entity_type=EntityType.PERSON,
                    confidence=0.9,
                )
            ],
            [],
        ).links[0],
        resolver.resolve_mentions(
            [
                EntityMention(
                    entity_id="ent:sam-2",
                    mention_text="Sam",
                    normalized_name="sam",
                    entity_type=EntityType.PERSON,
                    confidence=0.9,
                )
            ],
            [],
        ).links[0],
    ]
    ambiguous = EntityMention(
        entity_id="mention:request-3:sam",
        mention_text="Sam",
        normalized_name="sam",
        entity_type=EntityType.PERSON,
        confidence=0.9,
    )

    outcome = resolver.resolve_mentions([ambiguous], existing)

    assert outcome.links == []
    assert outcome.decisions[0].decision_type == EntityIdentityDecisionType.ABSTAIN
    assert outcome.decisions[0].resolved_entity_id is None


def test_entity_resolution_rejects_cross_scope_merge_and_preserves_split_scope() -> None:
    resolver = EntityResolutionService(now_provider=lambda: datetime(2026, 2, 1, tzinfo=UTC))
    global_link, task_link = resolver.resolve_mentions(
        [
            EntityMention(
                entity_id="ent:atlas-global",
                mention_text="Atlas",
                normalized_name="atlas",
                confidence=0.9,
            ),
            EntityMention(
                entity_id="ent:atlas-task",
                mention_text="Atlas",
                normalized_name="atlas",
                confidence=0.9,
                scope=MemoryScope(task_id="task:incident"),
            ),
        ],
        [],
    ).links

    with pytest.raises(ValueError, match="different scopes"):
        resolver.merge_links(primary=global_link, duplicate=task_link)

    _, split_link, _ = resolver.split_link(
        existing=task_link,
        mention=EntityMention(
            entity_id="ent:atlas-task-child",
            mention_text="Atlas Child",
            normalized_name="atlas child",
            entity_type=EntityType.SERVICE,
            confidence=0.8,
            scope=task_link.scope,
            evidence_spans=[
                EvidenceSpan(
                    source_id="event:child",
                    quote="Atlas Child",
                    source_type=SourceType.USER,
                    timestamp=datetime(2026, 2, 1, tzinfo=UTC),
                )
            ],
        ),
    )
    assert split_link.scope == task_link.scope


def test_rule_extraction_preserves_same_entity_mentions_across_scopes() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:global-atlas",
                "text": "Atlas owner is Alice.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        ),
        validator_source_from_dict(
            {
                "source_id": "tx:task-atlas",
                "text": "Atlas owner is Bob.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 2, tzinfo=UTC),
                "task_id": "task:incident",
            }
        ),
    ]

    run, entities, claims, _ = EnglishRuleMemoryExtractor().extract(observations)

    atlas_mentions = [entity for entity in entities if entity.entity_id == "ent:atlas"]
    assert len(atlas_mentions) == 2
    assert {entity.scope.scope_key for entity in atlas_mentions} == {"global", "task:incident"}
    assert {claim.claim_key.scope_key for claim in claims} == {"global", "task:incident"}
    assert run.entity_ids.count("ent:atlas") == 1


def test_rule_extraction_applies_grounded_type_declaration_to_subject() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:atlas-definition",
            "text": "Atlas project is a project.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )

    run, entities, claims, _ = EnglishRuleMemoryExtractor().extract([observation])

    type_claim = next(
        claim
        for claim in claims
        if claim.claim_key.predicate_id == "entity_type"
    )
    subject = next(
        entity
        for entity in entities
        if entity.entity_id == type_claim.claim_key.subject_entity_id
    )
    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert type_claim.object_value == "project"
    assert subject.entity_type == EntityType.PROJECT


def test_predicate_registry_rejects_missing_policies() -> None:
    registry = PredicateRegistry()

    assert registry.require("owner").predicate_id == "owner"
    with pytest.raises(KeyError):
        registry.require("unknown_predicate")


def test_evidence_span_requires_valid_offset_pair() -> None:
    with pytest.raises(ValueError):
        EvidenceSpan(
            source_id="tx:1",
            quote="Atlas owner is Bob",
            char_start=10,
            source_type=SourceType.USER,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_validator_requires_evidence_quote_to_exist_in_source() -> None:
    validator = MemoryEvolutionValidator()
    source = _record("tx:1", "Atlas owner is Bob.")
    observation = {
        "source_id": source.memory_id,
        "text": source.text,
        "source_type": SourceType.USER,
        "timestamp": source.timestamp,
        "domain": source.domain,
        "task_id": source.task_id,
    }
    claim = ExtractedClaim(
        claim_id="claim:bad",
        claim_key=ClaimKey(
            subject_entity_id="ent:atlas",
            predicate_id="owner",
            scope=MemoryScope(task_id="task:evolution"),
        ),
        object_value="Alice",
        evidence_spans=[
            EvidenceSpan(
                source_id="tx:1",
                quote="Atlas owner is Alice",
                source_type=SourceType.USER,
                timestamp=source.timestamp,
            )
        ],
        confidence=ConfidenceComponents(
            extraction=0.7,
            evidence=0.1,
            source_trust=0.9,
            calibrated=0.5,
        ),
        extraction_run_id="run:1",
    )

    results = validator.validate_claim(
        claim=claim,
        observation_by_id={"tx:1": validator_source_from_dict(observation)},
    )

    assert not validator.accepted(results)
    assert any(result.validator_name == "evidence_span_support" for result in results)


def test_validator_rejects_wrong_predicate_even_when_quote_exists() -> None:
    validator = MemoryEvolutionValidator()
    source = _record("tx:wrong-predicate", "Atlas approver is Bob.")
    claim = ExtractedClaim(
        claim_id="claim:wrong-predicate",
        claim_key=ClaimKey(
            subject_entity_id="ent:atlas",
            predicate_id="owner",
            scope=MemoryScope(task_id="task:evolution"),
        ),
        object_value="Bob",
        object_entity_id="ent:bob-local",
        evidence_spans=[
            EvidenceSpan(
                source_id=source.memory_id,
                quote="Atlas approver is Bob",
                source_type=SourceType.USER,
                timestamp=source.timestamp,
            )
        ],
        confidence=ConfidenceComponents(
            extraction=0.7,
            evidence=0.8,
            source_trust=0.9,
            calibrated=0.8,
        ),
        extraction_run_id="run:wrong-predicate",
    )

    results = validator.validate_claim(
        claim=claim,
        observation_by_id={
            source.memory_id: validator_source_from_dict(
                {
                    "source_id": source.memory_id,
                    "text": source.text,
                    "source_type": SourceType.USER,
                    "timestamp": source.timestamp,
                    "domain": source.domain,
                    "task_id": source.task_id,
                }
            )
        },
    )

    assert not validator.accepted(results)
    assert any(result.validator_name == "predicate_support" and result.verdict.value == "fail" for result in results)


def test_source_modality_classifier_identifies_non_assertions() -> None:
    classifier = SourceModalityClassifier()

    assert (
        classifier.classify(
            validator_source_from_dict(
                {
                    "source_id": "tx:q",
                    "text": "Is Atlas owner Bob?",
                    "source_type": SourceType.USER,
                    "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                }
            )
        )
        == SourceModality.QUESTION
    )
    assert (
        classifier.classify(
            validator_source_from_dict(
                {
                    "source_id": "tx:paste",
                    "text": "Here is a doc: Atlas owner is Bob.",
                    "source_type": SourceType.USER,
                    "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                }
            )
        )
        == SourceModality.QUOTED_OR_PASTED
    )
    assert (
        classifier.classify(
            validator_source_from_dict(
                {
                    "source_id": "tx:hypo",
                    "text": "Suppose Atlas owner is Bob.",
                    "source_type": SourceType.USER,
                    "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                }
            )
        )
        == SourceModality.HYPOTHETICAL
    )


def test_declared_modality_is_authoritative_but_absence_keeps_lexical_classification() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:declared-modality",
            "text": "Debug scratchpad says owner maybe TBD, but no source confirms it.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )

    declared = classify_and_mark_observation(
        observation,
        declared_modality=SourceModality.NOISE,
    )
    inferred = classify_and_mark_observation(observation)

    assert declared.modality == SourceModality.NOISE
    assert declared.trigger_mode == ExtractionTriggerMode.SKIP
    assert inferred.modality == SourceModality.THIRD_PARTY_CLAIM
    assert inferred.trigger_mode == ExtractionTriggerMode.DEFERRED


def test_empty_extraction_is_a_deterministic_abstention() -> None:
    run, entities, claims, actions = EnglishRuleMemoryExtractor().extract([])

    assert run.status == ExtractionRunStatus.ABSTAINED
    assert run.provider_attempt_status.value == "not_attempted"
    assert run.final_output_source.value == "none"
    assert entities == []
    assert claims == []
    assert actions == []


def test_failed_abstention_cannot_use_deterministic_no_output_contract() -> None:
    with pytest.raises(ValueError, match="deterministic abstention"):
        ExtractionRun(
            extraction_run_id="run:invalid-abstention",
            provider="test",
            input_source_ids=[],
            status=ExtractionRunStatus.ABSTAINED,
            provider_attempt_status=ProviderAttemptStatus.NOT_ATTEMPTED,
            final_output_source=FinalExtractionSource.NONE,
            failure_code=ExtractionFailureCode.OUTPUT_VALIDATION,
        )


def test_rule_extractor_handles_runtime_fact_phrasings() -> None:
    extractor = EnglishRuleMemoryExtractor()
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:owns",
                "text": "Marta owns Atlas for now.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                "task_id": "task:evolution",
            }
        ),
        validator_source_from_dict(
            {
                "source_id": "tx:eq",
                "text": "org_directory result: Atlas billing migration owner = Nadia.",
                "source_type": SourceType.TOOL,
                "timestamp": datetime(2026, 3, 1, tzinfo=UTC),
                "task_id": "task:evolution",
            }
        ),
        validator_source_from_dict(
            {
                "source_id": "tx:type",
                "text": "The Atlas workstream is the Q2 billing migration project owned by Finance Ops.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                "task_id": "task:evolution",
            }
        ),
    ]

    _, entities, claims, _ = extractor.extract(observations)

    claim_pairs = {
        (claim.claim_key.subject_entity_id, claim.claim_key.predicate_id, claim.object_value) for claim in claims
    }
    assert ("ent:atlas", "owner", "Marta") in claim_pairs
    assert ("ent:atlas-billing-migration", "owner", "Nadia") in claim_pairs
    assert any(
        claim.claim_key.predicate_id == "entity_type" and claim.object_value.lower() == "project" for claim in claims
    )
    assert {entity.entity_id for entity in entities} >= {
        "ent:atlas",
        "ent:marta",
        "ent:atlas-billing-migration",
        "ent:nadia",
    }


def test_llm_extraction_binds_request_local_references_to_deterministic_runtime_ids() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:one",
                "text": "Atlas owner is Alice.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        ),
        validator_source_from_dict(
            {
                "source_id": "tx:two",
                "text": "Atlas owner is Bob.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 2, 1, tzinfo=UTC),
            }
        ),
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": "tx:one",
                "quote": "Atlas",
            },
            {
                "entity_ref": "alice",
                "mention_text": "Alice",
                "entity_type": "person",
                "source_id": "tx:one",
                "quote": "Alice",
            },
            {
                "entity_ref": "bob",
                "mention_text": "Bob",
                "entity_type": "person",
                "source_id": "tx:two",
                "quote": "Bob",
            },
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "owner",
                "object_value": "Alice",
                "object_entity_ref": "alice",
                "source_id": "tx:one",
                "quote": "Atlas owner is Alice",
                "confidence": 0.8,
            },
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "owner",
                "object_value": "Bob",
                "object_entity_ref": "bob",
                "source_id": "tx:two",
                "quote": "Atlas owner is Bob",
                "confidence": 0.8,
            },
        ],
        "actions": [
            {
                "action_ref": "blocked",
                "actor_entity_ref": None,
                "action_type": "work_state",
                "target_entity_refs": ["atlas"],
                "status": "blocked",
                "dependency_entity_refs": [],
                "blocking_entity_refs": [],
                "source_id": "tx:one",
                "quote": "Atlas",
            },
            {
                "action_ref": "resumed",
                "actor_entity_ref": None,
                "action_type": "work_state",
                "target_entity_refs": ["atlas"],
                "status": "resumed",
                "dependency_entity_refs": [],
                "blocking_entity_refs": [],
                "source_id": "tx:two",
                "quote": "Atlas",
            },
        ],
    }

    run, entities, claims, actions = models_from_llm_output(
        run_id="run:llm-local-ids",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert run.errors == []
    assert len({entity.entity_id for entity in entities}) == 3
    assert len({claim.claim_id for claim in claims}) == 2
    assert len({action.action_id for action in actions}) == 2
    repeated = models_from_llm_output(
        run_id="run:llm-local-ids",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )
    assert [entity.entity_id for entity in repeated[1]] == [entity.entity_id for entity in entities]
    assert [claim.claim_id for claim in repeated[2]] == [claim.claim_id for claim in claims]
    assert [action.action_id for action in repeated[3]] == [action.action_id for action in actions]


def test_llm_action_extraction_preserves_observation_execution_context() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:incident-progress",
            "text": "Atlas cleanup is in progress.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            "task_id": "task:incident",
            "session_id": "session:incident",
            "user_id": "user:one",
        }
    )
    run, _, _, actions = models_from_llm_output(
        run_id="run:execution-context",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "atlas-cleanup",
                    "mention_text": "Atlas cleanup",
                    "source_id": observation.source_id,
                    "quote": "Atlas cleanup",
                }
            ],
            "claims": [],
            "actions": [
                {
                    "action_ref": "progress",
                    "action_type": "progress",
                    "target_entity_refs": ["atlas-cleanup"],
                    "status": "in_progress",
                    "dependency_entity_refs": [],
                    "blocking_entity_refs": [],
                    "source_id": observation.source_id,
                    "quote": "Atlas cleanup is in progress",
                }
            ],
        },
    )

    assert run.errors == []
    assert len(actions) == 1
    assert actions[0].task_id == "task:incident"
    assert actions[0].session_id == "session:incident"
    assert actions[0].user_id == "user:one"
    assert actions[0].scope_key == "task:incident"


def test_llm_extraction_compiles_grounded_entity_type_and_removes_only_duplicate_generic_fact() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:atlas-definition",
            "text": "Atlas is the billing migration project and launches Friday.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )

    run, entities, claims, _ = models_from_llm_output(
        run_id="run:atlas-definition",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "atlas",
                    "mention_text": "Atlas",
                    "aliases": [],
                    "entity_type": "project",
                    "source_id": observation.source_id,
                    "quote": "Atlas is the billing migration project",
                    "confidence": 0.9,
                }
            ],
            "claims": [
                {
                    "subject_entity_ref": "atlas",
                    "predicate_id": "semantic_fact",
                    "object_value": "project",
                    "object_entity_ref": None,
                    "source_id": observation.source_id,
                    "quote": "Atlas is the billing migration project",
                    "confidence": 0.8,
                },
                {
                    "subject_entity_ref": "atlas",
                    "predicate_id": "semantic_fact",
                    "object_value": "launches Friday",
                    "object_entity_ref": None,
                    "source_id": observation.source_id,
                    "quote": "launches Friday",
                    "confidence": 0.8,
                },
            ],
            "actions": [],
        },
    )

    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert len(entities) == 1
    assert {
        (claim.claim_key.predicate_id, claim.object_value)
        for claim in claims
    } == {
        ("entity_type", "project"),
        ("semantic_fact", "launches Friday"),
    }


def test_llm_extraction_does_not_derive_person_type_from_role_alone() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:atlas-owner",
            "text": "Alice owns Atlas.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )

    run, _, claims, _ = models_from_llm_output(
        run_id="run:atlas-owner",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "alice",
                    "mention_text": "Alice",
                    "aliases": [],
                    "entity_type": "person",
                    "source_id": observation.source_id,
                    "quote": "Alice",
                    "confidence": 0.9,
                },
                {
                    "entity_ref": "atlas",
                    "mention_text": "Atlas",
                    "aliases": [],
                    "entity_type": "project",
                    "source_id": observation.source_id,
                    "quote": "Atlas",
                    "confidence": 0.9,
                },
            ],
            "claims": [
                {
                    "subject_entity_ref": "atlas",
                    "predicate_id": "owner",
                    "object_value": "Alice",
                    "object_entity_ref": "alice",
                    "source_id": observation.source_id,
                    "quote": "Alice owns Atlas",
                    "confidence": 0.8,
                }
            ],
            "actions": [],
        },
    )

    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert [claim.claim_key.predicate_id for claim in claims] == ["owner"]


def test_llm_extraction_requires_whole_word_entity_type_evidence() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:personal-workspace",
            "text": "Alice's personal workspace is ready.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )

    run, _, claims, _ = models_from_llm_output(
        run_id="run:personal-workspace",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "alice",
                    "mention_text": "Alice",
                    "aliases": [],
                    "entity_type": "person",
                    "source_id": observation.source_id,
                    "quote": "Alice's personal workspace",
                    "confidence": 0.9,
                }
            ],
            "claims": [],
            "actions": [],
        },
    )

    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert claims == []


def test_llm_action_relations_resolve_only_declared_entity_references() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:blocked-migration",
            "text": "Atlas migration is blocked by the OAuth rollout.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )
    run, entities, _, actions = models_from_llm_output(
        run_id="run:entity-relations",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "migration",
                    "mention_text": "Atlas migration",
                    "source_id": observation.source_id,
                    "quote": "Atlas migration",
                },
                {
                    "entity_ref": "oauth",
                    "mention_text": "OAuth rollout",
                    "source_id": observation.source_id,
                    "quote": "OAuth rollout",
                },
            ],
            "claims": [],
            "actions": [
                {
                    "action_ref": "blocked",
                    "actor_entity_ref": None,
                    "action_type": "work_state",
                    "target_entity_refs": ["migration"],
                    "status": "blocked",
                    "dependency_entity_refs": ["oauth"],
                    "blocking_entity_refs": ["oauth"],
                    "source_id": observation.source_id,
                    "quote": "Atlas migration is blocked by the OAuth rollout",
                }
            ],
        },
    )

    entity_id_by_name = {entity.normalized_name: entity.entity_id for entity in entities}
    assert run.errors == []
    assert actions[0].target_entity_ids == [entity_id_by_name["atlas migration"]]
    assert actions[0].dependency_entity_ids == [entity_id_by_name["oauth rollout"]]
    assert actions[0].blocking_entity_ids == [entity_id_by_name["oauth rollout"]]


def test_llm_action_relations_reject_undeclared_entity_references() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:bad-relation",
            "text": "Atlas migration is blocked.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )
    run, entities, _, actions = models_from_llm_output(
        run_id="run:bad-entity-relation",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "migration",
                    "mention_text": "Atlas migration",
                    "source_id": observation.source_id,
                    "quote": "Atlas migration",
                }
            ],
            "claims": [],
            "actions": [
                {
                    "action_ref": "blocked",
                    "actor_entity_ref": None,
                    "action_type": "work_state",
                    "target_entity_refs": ["migration"],
                    "status": "blocked",
                    "dependency_entity_refs": ["missing"],
                    "blocking_entity_refs": [],
                    "source_id": observation.source_id,
                    "quote": "Atlas migration is blocked",
                }
            ],
        },
    )

    assert entities
    assert actions == []
    assert run.status == ExtractionRunStatus.PARTIAL
    assert any("action[0]: KeyError" in error for error in run.errors)


def test_llm_extraction_binds_unknown_echo_to_the_only_source_observation() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:known",
            "text": "Atlas owner is Alice.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )

    run, entities, claims, actions = models_from_llm_output(
        run_id="run:unknown-source",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "atlas",
                    "mention_text": "Atlas",
                    "source_id": "tx:hallucinated",
                    "quote": "Atlas",
                }
            ],
            "claims": [],
            "actions": [],
        },
    )

    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert run.failure_code is None
    assert len(entities) == 1
    assert entities[0].evidence_spans[0].source_id == observation.source_id
    assert claims == []
    assert actions == []
    assert run.errors == []


def test_llm_extraction_single_source_binding_restores_dependent_claim() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:benchmark:runtime:opaque-source-id",
            "text": "Priya owns Atlas for now.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )

    run, entities, claims, actions = models_from_llm_output(
        run_id="run:single-source-binding",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "e1",
                    "mention_text": "Priya",
                    "entity_type": "person",
                    "source_id": "tx:benchmark:runtime:opaque-source-i",
                    "quote": "Priya",
                },
                {
                    "entity_ref": "e2",
                    "mention_text": "Atlas",
                    "entity_type": "project",
                    "source_id": "tx:benchmark:runtime:opaque-source-id-id",
                    "quote": "Atlas",
                },
            ],
            "claims": [
                {
                    "subject_entity_ref": "e1",
                    "predicate_id": "owner",
                    "object_value": "Atlas",
                    "object_entity_ref": "e2",
                    "source_id": "tx:benchmark:runtime:opaque-source-i",
                    "quote": "Priya owns Atlas for now.",
                }
            ],
            "actions": [],
        },
    )

    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert len(entities) == 2
    assert len(claims) == 1
    assert actions == []
    assert {span.source_id for item in [*entities, *claims] for span in item.evidence_spans} == {observation.source_id}


def test_llm_extraction_single_source_binding_stabilizes_action_identity() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:benchmark:runtime:opaque-source-id",
            "text": "Atlas cleanup is blocked.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )

    def extract(source_id: str):
        return models_from_llm_output(
            run_id="run:single-source-action",
            provider="llm",
            model="test-model",
            prompt_hash="prompt-hash",
            observations=[observation],
            output={
                "entities": [
                    {
                        "entity_ref": "cleanup",
                        "mention_text": "Atlas cleanup",
                        "source_id": source_id,
                        "quote": "Atlas cleanup",
                    }
                ],
                "claims": [],
                "actions": [
                    {
                        "action_ref": "blocked-cleanup",
                        "actor_entity_ref": None,
                        "action_type": "work_state",
                        "target_entity_refs": ["cleanup"],
                        "status": "blocked",
                        "dependency_entity_refs": [],
                        "blocking_entity_refs": [],
                        "source_id": source_id,
                        "quote": "Atlas cleanup is blocked",
                    }
                ],
            },
        )

    exact_run, _, _, exact_actions = extract(observation.source_id)
    malformed_run, _, _, malformed_actions = extract("tx:benchmark:runtime:opaque-source-id-id")

    assert exact_run.status == ExtractionRunStatus.SUCCEEDED
    assert malformed_run.status == ExtractionRunStatus.SUCCEEDED
    assert [action.action_id for action in malformed_actions] == [action.action_id for action in exact_actions]
    assert malformed_actions[0].evidence_spans[0].source_id == observation.source_id


def test_llm_extraction_rejects_unknown_source_for_multi_source_request() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:first",
                "text": "Atlas owner is Alice.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        ),
        validator_source_from_dict(
            {
                "source_id": "tx:second",
                "text": "Atlas owner is Priya.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 2, tzinfo=UTC),
            }
        ),
    ]

    run, entities, claims, actions = models_from_llm_output(
        run_id="run:unknown-multi-source",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output={
            "entities": [
                {
                    "entity_ref": "atlas",
                    "mention_text": "Atlas",
                    "source_id": "tx:hallucinated",
                    "quote": "Atlas",
                }
            ],
            "claims": [],
            "actions": [],
        },
    )

    assert run.status == ExtractionRunStatus.FAILED
    assert run.failure_code == ExtractionFailureCode.OUTPUT_VALIDATION
    assert entities == []
    assert claims == []
    assert actions == []
    assert "unknown source_id" in run.errors[0]


def test_llm_extraction_preserves_valid_items_and_marks_ambiguous_provenance_partial() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:known",
            "text": "Atlas owner is Alice.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )
    other_observation = validator_source_from_dict(
        {
            "source_id": "tx:other",
            "text": "Atlas owner is Priya.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 2, tzinfo=UTC),
        }
    )

    run, entities, _, _ = models_from_llm_output(
        run_id="run:mixed-provenance",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation, other_observation],
        output={
            "entities": [
                {
                    "entity_ref": "atlas",
                    "mention_text": "Atlas",
                    "source_id": observation.source_id,
                    "quote": "Atlas",
                },
                {
                    "entity_ref": "alice",
                    "mention_text": "Alice",
                    "source_id": "tx:hallucinated",
                    "quote": "Alice",
                },
            ],
            "claims": [],
            "actions": [],
        },
    )

    assert run.status == ExtractionRunStatus.PARTIAL
    assert len(entities) == 1
    assert entities[0].mention_text == "Atlas"
    assert len(run.errors) == 1


def test_llm_extraction_distinguishes_explicit_abstention_from_invalid_output() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "源:東京",
            "text": "東京プロジェクトの担当者は葵です。",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            "language": "ja",
        }
    )

    abstained, _, _, _ = models_from_llm_output(
        run_id="run:abstained",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation],
        output={"entities": [], "claims": [], "actions": []},
    )
    succeeded, entities, _, _ = models_from_llm_output(
        run_id="run:unicode-provenance",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "tokyo-project",
                    "mention_text": "東京プロジェクト",
                    "source_id": observation.source_id,
                    "quote": "東京プロジェクト",
                }
            ],
            "claims": [],
            "actions": [],
        },
    )

    assert abstained.status == ExtractionRunStatus.ABSTAINED
    assert abstained.failure_code is None
    assert succeeded.status == ExtractionRunStatus.SUCCEEDED
    assert entities[0].evidence_spans[0].source_id == "源:東京"


def test_llm_extraction_rejects_nonverbatim_evidence_and_duplicate_source_ids() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:known",
            "text": "Atlas owner is Alice.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "source_id": observation.source_id,
                "quote": "atlas",
            }
        ],
        "claims": [],
        "actions": [],
    }

    nonverbatim, _, _, _ = models_from_llm_output(
        run_id="run:nonverbatim",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation],
        output=output,
    )
    duplicates, _, _, _ = models_from_llm_output(
        run_id="run:duplicate-sources",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation, observation],
        output={"entities": [], "claims": [], "actions": []},
    )

    assert nonverbatim.status == ExtractionRunStatus.FAILED
    assert "not verbatim" in nonverbatim.errors[0]
    assert duplicates.status == ExtractionRunStatus.FAILED
    assert "must be unique" in duplicates.errors[0]


def test_rule_extraction_inherits_session_scope_from_source_observation() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:session-scope",
            "text": "Atlas owner is Alice. Atlas cleanup started.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            "session_id": "session:incident",
            "user_id": "user:one",
        }
    )

    run, entities, claims, actions = EnglishRuleMemoryExtractor().extract([observation])

    assert run.errors == []
    assert claims
    assert actions
    assert {entity.scope.scope_key for entity in entities} == {"session:incident"}
    assert {claim.claim_key.scope_key for claim in claims} == {"session:incident"}
    assert {action.scope_key for action in actions} == {"session:incident"}
    assert all(action.task_id is None for action in actions)
    assert all(action.session_id == "session:incident" for action in actions)
    assert all(action.user_id == "user:one" for action in actions)


@pytest.mark.parametrize(
    ("field_name", "outside_value"),
    [
        ("scope_key", "task:other"),
        ("task_id", "task:other"),
        ("session_id", "session:other"),
        ("user_id", "user:other"),
        ("entity_id", "ent:persistent"),
        ("claim_id", "claim:persistent"),
        ("action_id", "action:persistent"),
        ("timestamp", "2026-01-01T00:00:00Z"),
        ("valid_from", "2026-01-01T00:00:00Z"),
        ("valid_to", "2026-02-01T00:00:00Z"),
    ],
)
def test_memory_extraction_transport_rejects_runtime_owned_metadata(
    field_name: str,
    outside_value: str,
) -> None:
    payload = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "aliases": [],
                "entity_type": "project",
                "source_id": "tx:scoped",
                "quote": "Atlas",
                "confidence": 0.9,
            }
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "owner",
                "object_value": "Alice",
                "object_entity_ref": None,
                "source_id": "tx:scoped",
                "quote": "Atlas owner is Alice",
                "confidence": 0.9,
            }
        ],
        "actions": [
            {
                "action_ref": "cleanup",
                "actor_entity_ref": None,
                "action_type": "work_state",
                "target_entity_refs": ["atlas"],
                "status": "started",
                "dependency_entity_refs": [],
                "blocking_entity_refs": [],
                "source_id": "tx:scoped",
                "quote": "Atlas cleanup started",
            }
        ],
    }
    target = (
        payload["entities"][0]
        if field_name == "entity_id"
        else payload["actions"][0]
        if field_name in {"action_id", "timestamp"}
        else payload["claims"][0]
    )
    target[field_name] = outside_value

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        MemoryExtractionOutput.model_validate(payload)


def test_llm_extraction_canonicalizes_inverse_owner_claim_arguments() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:owns",
                "text": "Iris owns Atlas Service.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "iris",
                "mention_text": "Iris",
                "entity_type": "person",
                "source_id": "tx:owns",
                "quote": "Iris",
                "confidence": 0.8,
            },
            {
                "entity_ref": "atlas-service",
                "mention_text": "Atlas Service",
                "entity_type": "service",
                "source_id": "tx:owns",
                "quote": "Atlas Service",
                "confidence": 0.8,
            },
        ],
        "claims": [
            {
                "subject_entity_ref": "iris",
                "predicate_id": "owner",
                "object_value": "Atlas Service",
                "object_entity_ref": "atlas-service",
                "source_id": "tx:owns",
                "quote": "Iris owns Atlas Service",
                "confidence": 0.8,
            }
        ],
        "actions": [],
    }

    run, entities, claims, _ = models_from_llm_output(
        run_id="run:inverse-owner",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert run.errors == []
    owner_claims = [claim for claim in claims if claim.claim_key.predicate_id == "owner"]
    assert len(owner_claims) == 1
    claim = owner_claims[0]
    ids_by_name = {entity.mention_text: entity.entity_id for entity in entities}
    assert claim.claim_key.subject_entity_id == ids_by_name["Atlas Service"]
    assert claim.object_entity_id == ids_by_name["Iris"]
    assert claim.object_value == "Iris"
    assert claim.qualifiers["argument_normalization"] == "owner_inverse_subject_object_swap"


@pytest.mark.parametrize(
    ("predicate_id", "object_entity_ref", "object_entity_type", "object_value", "error"),
    [
        ("owner", "target", "service", "Target", "owner object must be a person entity"),
        (
            "dependency",
            "target",
            "preference",
            "Target",
            "dependency object cannot be a preference entity",
        ),
        (
            "entity_type",
            "target",
            "person",
            "project",
            "entity_type requires a literal object",
        ),
        ("entity_type", None, "person", "spaceship", "unsupported entity_type value"),
        (
            "entity_type",
            None,
            "person",
            "person",
            "entity_type literal conflicts with the grounded subject type",
        ),
    ],
)
def test_captured_typed_claim_outputs_fail_closed_on_invalid_endpoint_contracts(
    predicate_id: str,
    object_entity_ref: str | None,
    object_entity_type: str,
    object_value: str,
    error: str,
) -> None:
    source_id = f"tx:{predicate_id}"
    observations = [
        validator_source_from_dict(
            {
                "source_id": source_id,
                "text": "Atlas is related to Target.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": source_id,
                "quote": "Atlas",
            },
            {
                "entity_ref": "target",
                "mention_text": "Target",
                "entity_type": object_entity_type,
                "source_id": source_id,
                "quote": "Target",
            },
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": predicate_id,
                "object_value": object_value,
                "object_entity_ref": object_entity_ref,
                "source_id": source_id,
                "quote": "Atlas is related to Target",
                "confidence": 0.8,
            }
        ],
        "actions": [],
    }

    run, entities, claims, actions = models_from_llm_output(
        run_id=f"run:{predicate_id}",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert len(entities) == 2
    assert claims == []
    assert actions == []
    assert run.status == ExtractionRunStatus.PARTIAL
    assert run.failure_code == ExtractionFailureCode.OUTPUT_VALIDATION
    assert any(error in item for item in run.errors)


@pytest.mark.parametrize(
    ("predicate_id", "object_entity_ref", "expected_error"),
    [
        ("owner", None, "owner requires a grounded object_entity_ref"),
        ("approver", "undeclared-person", "KeyError:'undeclared-person'"),
        ("api_owner", "undeclared-person", "KeyError:'undeclared-person'"),
        ("dependency", "undeclared-service", "KeyError:'undeclared-service'"),
    ],
)
def test_llm_extraction_does_not_infer_or_materialize_claim_endpoints(
    predicate_id: str,
    object_entity_ref: str | None,
    expected_error: str,
) -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:grounded-endpoint",
                "text": "Atlas is related to Rina.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": "tx:grounded-endpoint",
                "quote": "Atlas",
            }
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": predicate_id,
                "object_value": "Rina",
                "object_entity_ref": object_entity_ref,
                "source_id": "tx:grounded-endpoint",
                "quote": "Atlas is related to Rina",
                "confidence": 0.8,
            }
        ],
        "actions": [],
    }

    run, entities, claims, actions = models_from_llm_output(
        run_id=f"run:grounded-{predicate_id}",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert run.status == ExtractionRunStatus.PARTIAL
    assert len(entities) == 1
    assert claims == []
    assert actions == []
    assert any(expected_error in error for error in run.errors)


def test_llm_extraction_reuses_one_declared_endpoint_for_repeated_local_ref() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:repeated-endpoint",
                "text": "Atlas owner and API owner are Owen.",
                "source_type": SourceType.TOOL,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": "tx:repeated-endpoint",
                "quote": "Atlas",
            },
            {
                "entity_ref": "e2",
                "mention_text": "Owen",
                "entity_type": "person",
                "source_id": "tx:repeated-endpoint",
                "quote": "Owen",
            }
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": predicate_id,
                "object_value": "Owen",
                "object_entity_ref": "e2",
                "source_id": "tx:repeated-endpoint",
                "quote": "Atlas owner and API owner are Owen",
                "confidence": 0.8,
            }
            for predicate_id in ("owner", "api_owner")
        ],
        "actions": [],
    }

    run, entities, claims, _ = models_from_llm_output(
        run_id="run:repeated-endpoint",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert len([entity for entity in entities if entity.mention_text == "Owen"]) == 1
    assert len({claim.object_entity_id for claim in claims}) == 1
    assert claims[0].qualifiers == {}
    assert claims[1].qualifiers == {}


@pytest.mark.parametrize("object_value", ["", "temporary"])
def test_llm_extraction_canonicalizes_object_value_from_declared_entity_ref(
    object_value: str,
) -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:declared-ref-value",
                "text": "Eli is the temporary Atlas owner.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": "tx:declared-ref-value",
                "quote": "Atlas",
            },
            {
                "entity_ref": "eli",
                "mention_text": "Eli",
                "entity_type": "person",
                "source_id": "tx:declared-ref-value",
                "quote": "Eli",
            },
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "owner",
                "object_value": object_value,
                "object_entity_ref": "eli",
                "source_id": "tx:declared-ref-value",
                "quote": "Eli is the temporary Atlas owner",
                "confidence": 0.8,
            }
        ],
        "actions": [],
    }

    run, entities, claims, _ = models_from_llm_output(
        run_id=f"run:declared-ref-value:{object_value}",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert run.errors == []
    eli = next(entity for entity in entities if entity.mention_text == "Eli")
    assert claims[0].object_entity_id == eli.entity_id
    assert claims[0].object_value == "Eli"
    assert claims[0].qualifiers == {
        "object_endpoint_grounding": "declared_entity_ref",
        "object_value_normalization": "from_grounded_entity",
        **({"original_object_value": object_value} if object_value else {}),
    }


def test_llm_extraction_rejects_conflicting_values_for_one_local_endpoint_ref() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:conflicting-endpoint",
                "text": "Atlas owner is Owen, not Alice.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": "tx:conflicting-endpoint",
                "quote": "Atlas",
            },
            {
                "entity_ref": "alice",
                "mention_text": "Alice",
                "entity_type": "person",
                "source_id": "tx:conflicting-endpoint",
                "quote": "Alice",
            },
            {
                "entity_ref": "e2",
                "mention_text": "Owen",
                "entity_type": "person",
                "source_id": "tx:conflicting-endpoint",
                "quote": "Owen",
            },
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "owner",
                "object_value": object_value,
                "object_entity_ref": "e2",
                "source_id": "tx:conflicting-endpoint",
                "quote": "Atlas owner is Owen, not Alice",
                "confidence": 0.8,
            }
            for object_value in ("Owen", "Alice")
        ],
        "actions": [],
    }

    run, entities, claims, _ = models_from_llm_output(
        run_id="run:conflicting-endpoint",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert run.status == ExtractionRunStatus.PARTIAL
    assert len(entities) == 3
    assert [claim.object_value for claim in claims] == ["Owen"]
    assert any("conflicts with object_value 'Alice'" in error for error in run.errors)


def test_llm_extraction_binds_missing_ref_to_unique_verbatim_entity() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:declared-endpoint",
                "text": "Atlas owner is Rina.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": "tx:declared-endpoint",
                "quote": "Atlas",
            },
            {
                "entity_ref": "rina",
                "mention_text": "Rina",
                "entity_type": "person",
                "source_id": "tx:declared-endpoint",
                "quote": "Rina",
            },
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "owner",
                "object_value": "Rina",
                "object_entity_ref": None,
                "source_id": "tx:declared-endpoint",
                "quote": "Atlas owner is Rina",
                "confidence": 0.8,
            }
        ],
        "actions": [],
    }

    run, entities, claims, _ = models_from_llm_output(
        run_id="run:declared-endpoint",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert run.status == ExtractionRunStatus.SUCCEEDED
    endpoint = next(entity for entity in entities if entity.mention_text == "Rina")
    assert claims[0].object_entity_id == endpoint.entity_id
    assert claims[0].qualifiers == {"object_endpoint_grounding": "matched_verbatim_entity"}


@pytest.mark.parametrize(
    ("object_value", "object_entity_ref", "expected_error"),
    [
        ("Charlie", None, "owner requires a grounded object_entity_ref"),
        ("Rin", "e2", "KeyError:'e2'"),
    ],
)
def test_llm_extraction_does_not_materialize_ungrounded_or_substring_endpoints(
    object_value: str,
    object_entity_ref: str | None,
    expected_error: str,
) -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:ungrounded-endpoint",
                "text": "Atlas owner is Rina.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": "tx:ungrounded-endpoint",
                "quote": "Atlas",
            }
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "owner",
                "object_value": object_value,
                "object_entity_ref": object_entity_ref,
                "source_id": "tx:ungrounded-endpoint",
                "quote": "Atlas owner is Rina",
                "confidence": 0.8,
            }
        ],
        "actions": [],
    }

    run, entities, claims, _ = models_from_llm_output(
        run_id="run:ungrounded-endpoint",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert run.status == ExtractionRunStatus.PARTIAL
    assert len(entities) == 1
    assert claims == []
    assert any(expected_error in error for error in run.errors)


def test_llm_extraction_rejects_ungrounded_type_claim_before_typed_edge() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:ungrounded-type",
                "text": "Atlas owner is Alice.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": "tx:ungrounded-type",
                "quote": "Atlas",
            },
            {
                "entity_ref": "alice",
                "mention_text": "Alice",
                "entity_type": "unknown",
                "source_id": "tx:ungrounded-type",
                "quote": "Alice",
            },
        ],
        "claims": [
            {
                "subject_entity_ref": "alice",
                "predicate_id": "entity_type",
                "object_value": "person",
                "object_entity_ref": None,
                "source_id": "tx:ungrounded-type",
                "quote": "Alice",
                "confidence": 0.9,
            },
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "owner",
                "object_value": "Alice",
                "object_entity_ref": "alice",
                "source_id": "tx:ungrounded-type",
                "quote": "Atlas owner is Alice",
                "confidence": 0.9,
            },
        ],
        "actions": [],
    }

    run, entities, claims, _ = models_from_llm_output(
        run_id="run:ungrounded-type",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert run.status == ExtractionRunStatus.PARTIAL
    assert next(entity for entity in entities if entity.mention_text == "Alice").entity_type == EntityType.UNKNOWN
    assert claims == []
    assert any(
        "entity_type declaration is not grounded in its evidence quote" in error
        for error in run.errors
    )
    assert any("owner object must be a person entity" in error for error in run.errors)


def test_llm_extraction_does_not_infer_person_type_from_owner_relation() -> None:
    observation = validator_source_from_dict(
        {
            "source_id": "tx:circular-owner-type",
            "text": "Atlas owner is Dashboard.",
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )
    run, entities, claims, _ = models_from_llm_output(
        run_id="run:circular-owner-type",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "atlas",
                    "mention_text": "Atlas",
                    "entity_type": "project",
                    "source_id": observation.source_id,
                    "quote": "Atlas",
                },
                {
                    "entity_ref": "dashboard",
                    "mention_text": "Dashboard",
                    "entity_type": "unknown",
                    "source_id": observation.source_id,
                    "quote": "Dashboard",
                },
            ],
            "claims": [
                {
                    "subject_entity_ref": "atlas",
                    "predicate_id": "owner",
                    "object_value": "Dashboard",
                    "object_entity_ref": "dashboard",
                    "source_id": observation.source_id,
                    "quote": "Atlas owner is Dashboard",
                }
            ],
            "actions": [],
        },
    )

    assert run.status == ExtractionRunStatus.PARTIAL
    assert next(
        entity for entity in entities if entity.mention_text == "Dashboard"
    ).entity_type == EntityType.UNKNOWN
    assert claims == []
    assert any("owner object must be a person entity" in error for error in run.errors)


def test_memory_evolution_rejects_multi_source_extraction_batch() -> None:
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService())

    with pytest.raises(
        ValueError,
        match="one extractable source observation per call",
    ):
        service.evolve_records(
            [
                _record("tx:alice", "Atlas owner is Alice."),
                _record("tx:bob", "Beacon owner is Bob."),
            ]
        )


def test_llm_extraction_does_not_guess_between_ambiguous_endpoint_entities() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:ambiguous-endpoint",
                "text": "Rina told Rina that Atlas has an owner.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": "tx:ambiguous-endpoint",
                "quote": "Atlas",
            },
            *[
                {
                    "entity_ref": entity_ref,
                    "mention_text": "Rina",
                    "entity_type": "person",
                    "source_id": "tx:ambiguous-endpoint",
                    "quote": "Rina",
                }
                for entity_ref in ("rina-one", "rina-two")
            ],
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "owner",
                "object_value": "Rina",
                "object_entity_ref": None,
                "source_id": "tx:ambiguous-endpoint",
                "quote": "Atlas has an owner",
                "confidence": 0.8,
            }
        ],
        "actions": [],
    }

    run, entities, claims, _ = models_from_llm_output(
        run_id="run:ambiguous-endpoint",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert run.status == ExtractionRunStatus.PARTIAL
    assert len(entities) == 3
    assert claims == []
    assert any("ambiguous grounded object endpoint" in error for error in run.errors)


def test_llm_extraction_does_not_materialize_refs_for_literal_predicates() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:literal-ref",
                "text": "Atlas has a semantic association with Rina.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": "tx:literal-ref",
                "quote": "Atlas",
            }
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "semantic_fact",
                "object_value": "Rina",
                "object_entity_ref": "e2",
                "source_id": "tx:literal-ref",
                "quote": "Atlas has a semantic association with Rina",
                "confidence": 0.8,
            }
        ],
        "actions": [],
    }

    run, entities, claims, _ = models_from_llm_output(
        run_id="run:literal-ref",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert run.status == ExtractionRunStatus.PARTIAL
    assert len(entities) == 1
    assert claims == []
    assert any("KeyError:'e2'" in error for error in run.errors)


def test_captured_action_output_requires_a_grounded_target() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:action",
                "text": "Alice started cleanup.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "alice",
                "mention_text": "Alice",
                "entity_type": "person",
                "source_id": "tx:action",
                "quote": "Alice",
            }
        ],
        "claims": [],
        "actions": [
            {
                "action_ref": "cleanup",
                "actor_entity_ref": "alice",
                "action_type": "cleanup",
                "target_entity_refs": [],
                "status": "started",
                "dependency_entity_refs": [],
                "blocking_entity_refs": [],
                "source_id": "tx:action",
                "quote": "Alice started cleanup",
            }
        ],
    }

    run, entities, claims, actions = models_from_llm_output(
        run_id="run:action",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert len(entities) == 1
    assert claims == []
    assert actions == []
    assert run.status == ExtractionRunStatus.PARTIAL
    assert run.failure_code == ExtractionFailureCode.OUTPUT_VALIDATION
    assert any("action requires at least one grounded target_entity_ref" in item for item in run.errors)


def test_llm_extraction_derives_temporal_metadata_from_source_observation() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:quarter",
                "text": "Atlas owner is Bob in Q2.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 5, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": "tx:quarter",
                "quote": "Atlas",
            },
            {
                "entity_ref": "bob",
                "mention_text": "Bob",
                "entity_type": "person",
                "source_id": "tx:quarter",
                "quote": "Bob",
            },
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "owner",
                "object_value": "Bob",
                "object_entity_ref": "bob",
                "source_id": "tx:quarter",
                "quote": "Atlas owner is Bob",
                "confidence": 0.8,
            }
        ],
        "actions": [],
    }

    run, _, claims, _ = models_from_llm_output(
        run_id="run:quarter-date",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert run.errors == []
    assert len(claims) == 1
    assert claims[0].valid_from == observations[0].timestamp
    assert claims[0].valid_to is None
    assert claims[0].qualifiers == {}


def test_llm_extraction_rejects_unknown_request_local_entity_reference() -> None:
    observations = [
        validator_source_from_dict(
            {
                "source_id": "tx:bad-date",
                "text": "Atlas owner is Bob.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 5, 1, tzinfo=UTC),
            }
        )
    ]
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "source_id": "tx:bad-date",
                "quote": "Atlas",
            }
        ],
        "claims": [
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "owner",
                "object_value": "Charlie",
                "object_entity_ref": "missing-bob",
                "source_id": "tx:bad-date",
                "quote": "Atlas owner is Bob",
                "confidence": 0.8,
            }
        ],
        "actions": [],
    }

    run, _, claims, _ = models_from_llm_output(
        run_id="run:bad-date",
        provider="llm",
        model="test-model",
        prompt_hash="prompt-hash",
        observations=observations,
        output=output,
    )

    assert claims == []
    assert run.status == ExtractionRunStatus.PARTIAL
    assert run.failure_code == ExtractionFailureCode.OUTPUT_VALIDATION
    assert "missing-bob" in run.errors[0]
    assert run.validation_summary["claim_binding_errors"] == 1
    assert run.validation_summary["accepted_entities"] == 1


def test_current_and_historical_truth_are_both_addressable() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    jan = _record(
        "tx:jan",
        "Atlas owner is Alice.",
        timestamp=datetime(2026, 1, 10, tzinfo=UTC),
    )
    mar = _record(
        "tx:mar",
        "Atlas owner is Bob.",
        timestamp=datetime(2026, 3, 20, tzinfo=UTC),
    )

    plane.stage_record(jan)
    service.evolve_records([jan])
    plane.stage_record(mar)
    service.evolve_records([mar])

    current = service.retrieve_claim_states(
        view=RetrievalView.CURRENT,
        predicate_id="owner",
        subject_entity_id="ent:atlas",
    )
    historical = service.retrieve_claim_states(
        view=RetrievalView.HISTORICAL_AT,
        valid_at=datetime(2026, 1, 20, tzinfo=UTC),
        predicate_id="owner",
        subject_entity_id="ent:atlas",
    )

    assert [state.object_value for state in current] == ["Bob"]
    assert [state.object_value for state in historical] == ["Alice"]


def test_pasted_and_question_text_are_not_evolved_into_active_claims() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    pasted = _record("tx:pasted", "Here is a doc: Atlas owner is Bob.")
    question = _record("tx:question", "Is Atlas owner Bob?")

    result = service.evolve_records([pasted, question])

    assert result.claims
    assert all(state.lifecycle_state.value == "invalidated" for state in result.claim_states)
    assert result.deferred_observation_ids == ["tx:pasted"]
    assert result.skipped_observation_ids == ["tx:question"]
    assert service.retrieve_claim_states(view=RetrievalView.CURRENT) == []


def test_rejected_reobservation_cannot_overwrite_existing_claim_history() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(
        memory_plane=plane,
        extractor=_StableClaimIdExtractor(),
    )
    asserted = _record(
        "tx:asserted",
        "Atlas owner is Bob.",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    quoted = _record(
        "tx:quoted",
        "Here is a doc: Atlas owner is Bob.",
        timestamp=datetime(2026, 2, 1, tzinfo=UTC),
    )

    service.evolve_records([asserted])
    original = service.retrieve_claim_states(view=RetrievalView.CURRENT)[0]
    service.evolve_records([quoted])

    states = service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)
    by_id = {state.claim_id: state for state in states}
    assert by_id[original.claim_id].lifecycle_state.value == "active"
    rejected = [state for state in states if state.claim_id != original.claim_id]
    assert len(rejected) == 1
    assert rejected[0].lifecycle_state.value == "invalidated"
    assert rejected[0].source_claim_id == original.claim_id


def test_higher_trust_correction_blocks_later_transcript_chatter() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    transcript = _record(
        "tx:deploy:tool",
        "Atlas deploy succeeded.",
        source_kind="tool",
        timestamp=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
    )
    correction = _record(
        "tx:deploy:user",
        "Atlas deploy failed.",
        source_kind="user",
        timestamp=datetime(2026, 3, 1, 12, 5, tzinfo=UTC),
    )
    late_chatter = _record(
        "tx:deploy:late",
        "Atlas deploy succeeded.",
        source_kind="provider",
        timestamp=datetime(2026, 3, 1, 12, 10, tzinfo=UTC),
    )

    for record in [transcript, correction, late_chatter]:
        plane.stage_record(record)
        service.evolve_records([record])

    current = service.retrieve_claim_states(
        view=RetrievalView.CURRENT,
        predicate_id="status",
        subject_entity_id="ent:atlas",
    )
    conflicts = service.retrieve_claim_states(view=RetrievalView.CONFLICTS)

    assert [state.object_value for state in current] == ["failed"]
    assert any(state.object_value == "succeeded" for state in conflicts)
    assert service.retrieve_claim_states(view=RetrievalView.EVIDENCE_ONLY)


def test_reinforcement_updates_existing_claim_confidence_instead_of_duplicating() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    first = _record("tx:first", "Atlas owner is Bob.", timestamp=datetime(2026, 1, 1, tzinfo=UTC))
    second = _record("tx:second", "Atlas owner is Bob.", timestamp=datetime(2026, 1, 2, tzinfo=UTC))

    service.evolve_records([first])
    service.evolve_records([second])

    current = service.retrieve_claim_states(
        view=RetrievalView.CURRENT,
        predicate_id="owner",
        subject_entity_id="ent:atlas",
    )
    assert [state.object_value for state in current] == ["Bob"]
    assert len(current) == 1
    assert current[0].confidence_history
    assert current[0].confidence.calibrated > first_confidence_floor()


def test_single_value_precedence_is_invariant_to_model_confidence() -> None:
    timestamp = datetime(2026, 3, 1, tzinfo=UTC)
    span = EvidenceSpan(
        source_id="tx:owner",
        quote="Atlas owner is Alice.",
        source_type=SourceType.USER,
        timestamp=timestamp,
    )
    claim = ExtractedClaim(
        claim_id="claim:owner",
        claim_key=ClaimKey(subject_entity_id="ent:atlas", predicate_id="owner"),
        object_value="Alice",
        valid_from=timestamp,
        evidence_spans=[span],
        confidence=ConfidenceComponents(
            extraction=0.01,
            evidence=0.01,
            source_trust=0.01,
            calibrated=0.01,
        ),
        extraction_run_id="run:owner",
    )
    perturbed = claim.model_copy(
        update={
            "confidence": claim.confidence.model_copy(
                update={
                    "extraction": 0.99,
                    "evidence": 0.99,
                    "source_trust": 0.99,
                    "calibrated": 0.99,
                }
            )
        }
    )

    registry = PredicateRegistry()
    assert claim_precedence(claim, predicate_registry=registry) == claim_precedence(
        perturbed,
        predicate_registry=registry,
    )


def test_equal_time_single_value_precedence_uses_predicate_authority() -> None:
    timestamp = datetime(2026, 3, 1, tzinfo=UTC)

    def precedence(source_type: SourceType, claim_id: str):
        claim = ExtractedClaim(
            claim_id=claim_id,
            claim_key=ClaimKey(subject_entity_id="ent:atlas", predicate_id="owner"),
            object_value=claim_id,
            valid_from=timestamp,
            evidence_spans=[
                EvidenceSpan(
                    source_id=f"tx:{claim_id}",
                    quote=claim_id,
                    source_type=source_type,
                    timestamp=timestamp,
                )
            ],
            confidence=ConfidenceComponents(
                extraction=0.5,
                evidence=0.5,
                source_trust=0.5,
                calibrated=0.5,
            ),
            extraction_run_id=f"run:{claim_id}",
        )
        return claim_precedence(claim, predicate_registry=PredicateRegistry())

    assert precedence(SourceType.USER, "user") > precedence(SourceType.TOOL, "tool")


def test_single_value_precedence_uses_effective_time_before_source_authority() -> None:
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService())
    newer_tool_result = _record(
        "tx:newer-tool-owner",
        "Atlas owner is Bob.",
        source_kind="tool",
        timestamp=datetime(2026, 3, 1, tzinfo=UTC),
    )
    older_user_statement = _record(
        "tx:older-user-owner",
        "Atlas owner is Alice.",
        source_kind="user",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )

    service.evolve_records([newer_tool_result])
    service.evolve_records([older_user_statement])

    current = service.retrieve_claim_states(
        view=RetrievalView.CURRENT,
        predicate_id="owner",
        subject_entity_id="ent:atlas",
    )
    history = service.retrieve_claim_states(
        view=RetrievalView.ALL_VERSIONS,
        predicate_id="owner",
        subject_entity_id="ent:atlas",
    )

    assert [state.object_value for state in current] == ["Bob"]
    assert {state.object_value: state.lifecycle_state.value for state in history} == {
        "Alice": "invalidated",
        "Bob": "active",
    }


def test_status_precedence_prefers_authority_and_is_input_order_invariant() -> None:
    older_user = _record(
        "tx:status:user",
        "Atlas deploy failed.",
        source_kind="user",
        timestamp=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
    )
    newer_environment = _record(
        "tx:status:environment",
        "Atlas deploy succeeded.",
        source_kind="environment",
        timestamp=datetime(2026, 3, 1, 12, 5, tzinfo=UTC),
    )

    current_values: list[list[str]] = []
    for records in ([older_user, newer_environment], [newer_environment, older_user]):
        service = MemoryEvolutionService(memory_plane=MemoryPlaneService())
        for record in records:
            service.evolve_records([record])
        current_values.append(
            [
                state.object_value
                for state in service.retrieve_claim_states(
                    view=RetrievalView.CURRENT,
                    predicate_id="status",
                    subject_entity_id="ent:atlas",
                )
            ]
        )

    assert current_values == [["failed"], ["failed"]]


def test_single_value_lifecycle_isolated_by_complete_scope() -> None:
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService())
    service.evolve_records(
        [_record("tx:task-a", "Atlas owner is Alice.", task_id="task:a")]
    )
    service.evolve_records(
        [_record("tx:task-b", "Atlas owner is Bob.", task_id="task:b")]
    )

    current = service.retrieve_claim_states(
        view=RetrievalView.CURRENT,
        predicate_id="owner",
        subject_entity_id="ent:atlas",
    )

    assert {(state.claim_key.scope.task_id, state.object_value) for state in current} == {
        ("task:a", "Alice"),
        ("task:b", "Bob"),
    }


def test_entity_links_and_contradiction_sets_are_recorded() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    alice = _record("tx:alice", "Atlas owner is Alice.", timestamp=datetime(2026, 1, 1, tzinfo=UTC))
    bob = _record("tx:bob", "Atlas owner is Bob.", timestamp=datetime(2026, 2, 1, tzinfo=UTC))

    first_result = service.evolve_records([alice])
    second_result = service.evolve_records([bob])

    assert {link.canonical_entity_id for link in first_result.entity_links} >= {"ent:atlas", "ent:alice"}
    assert second_result.contradiction_sets
    assert second_result.contradiction_sets[0].active_claim_id in {
        state.claim_id for state in second_result.claim_states
    }
    assert any(transition.transition_type.value == "supersede" for transition in second_result.transitions)


def test_service_projects_grounded_alias_split_lineage_end_to_end() -> None:
    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        extractor=_EntitySequenceExtractor(),
    )

    service.evolve_records([_record("event:project", "Atlas is the billing project.")])
    result = service.evolve_records([_record("event:service", "Atlas service is the internal platform service.")])

    assert [decision.decision_type for decision in result.entity_identity_decisions] == [
        EntityIdentityDecisionType.SPLIT_EXISTING
    ]
    assert result.entity_links[0].lineage_parent_entity_id == "ent:atlas-project"
    split_edges = [edge for edge in result.graph_edges if edge.edge_type == MemoryGraphEdgeType.SPLIT_FROM]
    assert len(split_edges) == 1


def test_entity_resolution_exposes_merge_split_and_claim_rekey_transitions() -> None:
    resolver = EntityResolutionService()
    primary = EntityLinkState(
        link_id="link:atlas",
        mention_text="Atlas",
        canonical_entity_id="ent:atlas",
        normalized_name="atlas",
        aliases=["Atlas"],
        confidence=0.8,
    )
    duplicate = EntityLinkState(
        link_id="link:atlas-project",
        mention_text="Atlas Project",
        canonical_entity_id="ent:atlas-project",
        normalized_name="atlas project",
        aliases=["Atlas Project"],
        confidence=0.7,
    )
    merged, invalidated, merge_transition = resolver.merge_links(primary=primary, duplicate=duplicate)
    split_old, split_new, split_transition = resolver.split_link(
        existing=merged,
        mention=EntityMention(
            entity_id="ent:atlas-billing",
            mention_text="Atlas Billing",
            normalized_name="atlas billing",
            entity_type=EntityType.PROJECT,
            confidence=0.8,
            evidence_spans=[
                EvidenceSpan(
                    source_id="event:atlas-billing",
                    quote="Atlas Billing",
                    source_type=SourceType.USER,
                    timestamp=datetime(2026, 2, 1, tzinfo=UTC),
                )
            ],
        ),
    )
    claim = ExtractedClaim(
        claim_id="claim:rekey",
        claim_key=ClaimKey(
            subject_entity_id="ent:atlas-project",
            predicate_id="owner",
            scope=MemoryScope(task_id="task:evolution"),
        ),
        object_value="Bob",
        object_entity_id="ent:bob-local",
        confidence=ConfidenceComponents(
            extraction=0.7,
            evidence=0.8,
            source_trust=0.9,
            calibrated=0.8,
        ),
        extraction_run_id="run:rekey",
    )
    rekeyed, rekey_transition = resolver.canonicalize_claim_entities(
        claim=claim,
        references={
            (
                "ent:atlas-project",
                claim.claim_key.scope.identity,
            ): "ent:atlas",
            (
                "ent:bob-local",
                claim.claim_key.scope.identity,
            ): "ent:bob",
        },
    )
    action = ExtractedAction(
        action_id="action:local",
        actor_entity_id="ent:bob-local",
        action_type="start",
        target_entity_ids=["ent:atlas-project"],
        status="started",
        dependency_entity_ids=["ent:atlas-project"],
        blocking_entity_ids=["ent:bob-local"],
        timestamp=datetime(2026, 2, 1, tzinfo=UTC),
        scope=claim.claim_key.scope,
        extraction_run_id="run:rekey",
    )
    canonical_action = resolver.canonicalize_action_entities(
        action=action,
        references={
            (
                "ent:atlas-project",
                action.scope.identity,
            ): "ent:atlas",
            (
                "ent:bob-local",
                action.scope.identity,
            ): "ent:bob",
        },
    )

    assert "Atlas Project" in merged.aliases
    assert invalidated.lifecycle_state.value == "merged"
    assert split_old.lifecycle_state.value == "active"
    assert split_new.canonical_entity_id == "ent:atlas-billing"
    assert rekeyed.claim_key.subject_entity_id == "ent:atlas"
    assert rekeyed.object_entity_id == "ent:bob"
    assert canonical_action.actor_entity_id == "ent:bob"
    assert canonical_action.target_entity_ids == ["ent:atlas"]
    assert canonical_action.dependency_entity_ids == ["ent:atlas"]
    assert canonical_action.blocking_entity_ids == ["ent:bob"]
    assert rekey_transition is not None
    assert merge_transition.transition_type.value == "entity_merge"
    assert split_transition.transition_type.value == "entity_split"
    assert rekey_transition.transition_type.value == "claim_rekey"


def test_service_propagates_canonical_identity_across_request_local_outputs() -> None:
    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        extractor=_RequestLocalIdentityExtractor(),
    )

    first = service.evolve_records(
        [
            _record(
                "event:first-owner",
                "Atlas owner is Bob.",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]
    )
    second = service.evolve_records(
        [
            _record(
                "event:second-owner",
                "Atlas Billing Migration owner is Alice.",
                timestamp=datetime(2026, 1, 2, tzinfo=UTC),
            )
        ]
    )

    canonical_project = next(link.canonical_entity_id for link in first.entity_links if link.normalized_name == "atlas")
    canonical_alice = next(link.canonical_entity_id for link in second.entity_links if link.normalized_name == "alice")
    assert second.claims[0].claim_key.subject_entity_id == canonical_project
    assert second.claims[0].object_entity_id == canonical_alice
    assert {transition.transition_type.value for transition in second.transitions} >= {"claim_rekey"}
    current = service.retrieve_claim_states(
        view=RetrievalView.CURRENT,
        predicate_id="owner",
        subject_entity_id=canonical_project,
    )
    assert len(current) == 1
    canonical_person_link_ids = {
        link.link_id for link in second.entity_links if link.canonical_entity_id == canonical_alice
    }
    assert current[0].object_link_id in canonical_person_link_ids
    assert current[0].object_value == "Alice"
    history = service.retrieve_claim_states(
        view=RetrievalView.ALL_VERSIONS,
        predicate_id="owner",
        subject_entity_id=canonical_project,
    )
    assert {state.object_value: state.lifecycle_state.value for state in history} == {
        "Alice": "active",
        "Bob": "superseded",
    }


def test_service_preserves_cross_event_action_relation_identity() -> None:
    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        extractor=_RequestLocalActionRelationExtractor(),
    )

    first = service.evolve_records(
        [
            _record(
                "event:first-blocked",
                "Atlas migration is blocked by the OAuth rollout.",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]
    )
    second = service.evolve_records(
        [
            _record(
                "event:still-blocked",
                "Atlas migration remains blocked by the OAuth rollout.",
                timestamp=datetime(2026, 1, 2, tzinfo=UTC),
            )
        ]
    )

    first_action = first.actions[0]
    second_action = second.actions[0]
    assert second_action.target_entity_ids == first_action.target_entity_ids
    assert second_action.dependency_entity_ids == first_action.dependency_entity_ids
    assert second_action.blocking_entity_ids == first_action.blocking_entity_ids
    dependency_id = second_action.dependency_entity_ids[0]
    relation_targets = {
        edge.target_node_id
        for edge in second.graph_edges
        if edge.edge_type in {MemoryGraphEdgeType.DEPENDS_ON, MemoryGraphEdgeType.BLOCKS}
    }
    assert {node.node_id for node in second.graph_nodes if node.canonical_id == dependency_id} <= relation_targets


def test_provider_chat_ingestion_is_deferred_when_evolution_is_opted_in() -> None:
    service = ProviderMemoryService(
        memory_evolution_extractor=EnglishRuleMemoryExtractor(),
    )

    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="test:deferred-chat",
        role="user",
        task_id="task:evolution",
    )

    result = service.last_memory_evolution_result()
    assert result is not None
    assert result.claims
    assert all(state.lifecycle_state.value == "invalidated" for state in result.claim_states)
    assert result.deferred_observation_ids


def test_explicit_provider_memory_write_triggers_runtime_memory_evolution() -> None:
    service = ProviderMemoryService(
        memory_evolution_extractor=EnglishRuleMemoryExtractor(),
    )

    service.apply_memory_write(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas owner is Bob.",
        session_id=None,
        task_id="task:evolution",
        user_id=None,
        action="upsert",
        target="memory",
        operation_id="test:explicit-memory-write",
    )

    result = service.last_memory_evolution_result()
    assert result is not None
    assert [claim.object_value for claim in result.claims] == ["Bob"]
    assert result.observations[0].trigger_mode == ExtractionTriggerMode.IMMEDIATE
    assert any(record_id.startswith("mem:evolution:claim:") for record_id in result.written_record_ids)
    assert result.graph_nodes
    assert result.graph_edges
    assert result.graph_validation_errors == []


def test_memory_extractor_factory_defaults_to_rule_without_live_provider() -> None:
    extractor = build_memory_extractor_from_env(
        env={
            "MEMORII_ENV": "test",
            "MEMORII_SECRET_SOURCE": "process",
            "MEMORII_LLM_PROVIDER": "none",
            "MEMORII_DECISION_MODE": "auto",
        }
    )

    assert isinstance(extractor, EnglishRuleMemoryExtractor)


def validator_source_from_dict(payload: dict[str, object]):
    from memorii.core.memory_evolution.models import SourceObservation

    return SourceObservation.model_validate(payload)


def first_confidence_floor() -> float:
    return 0.8

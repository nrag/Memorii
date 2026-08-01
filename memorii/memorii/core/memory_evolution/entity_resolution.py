"""Entity-link lifecycle helpers for memory evolution."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from memorii.core.memory_evolution.models import (
    ClaimLifecycleTransition,
    ClaimTransitionType,
    EntityIdentityDecision,
    EntityIdentityDecisionType,
    EntityIdentityRelationType,
    EntityLinkLifecycleState,
    EntityLinkState,
    EntityMention,
    EntityResolutionOutcome,
    EntityType,
    ExtractedAction,
    ExtractedClaim,
    ExtractedIdentityRelation,
    MemoryScope,
)

ScopedEntityReference = tuple[
    str,
    tuple[str | None, str | None, str | None],
]


def _scope_identity(scope: MemoryScope) -> tuple[str | None, str | None, str | None]:
    return scope.identity


class EntityResolutionService:
    def __init__(self, *, now_provider: Callable[[], datetime] | None = None) -> None:
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def resolve_mentions(
        self,
        mentions: list[EntityMention],
        existing_links: list[EntityLinkState],
        *,
        identity_relations: list[ExtractedIdentityRelation] | None = None,
    ) -> EntityResolutionOutcome:
        links_by_key = {
            (link.normalized_name, link.canonical_entity_id, _scope_identity(link.scope)): link
            for link in existing_links
            if link.lifecycle_state == EntityLinkLifecycleState.ACTIVE
        }
        resolved: list[EntityLinkState] = []
        decisions: list[EntityIdentityDecision] = []
        transitions: list[ClaimLifecycleTransition] = []
        relations_by_source = {relation.source_entity_id: relation for relation in identity_relations or []}
        relation_target_ids = {relation.target_entity_id for relation in identity_relations or []}
        resolved_entity_by_mention: dict[str, str] = {}
        now = self._now_provider()
        ordered_mentions = sorted(
            mentions,
            key=lambda mention: (
                0 if mention.entity_id in relation_target_ids else 1,
                *_mention_resolution_key(mention),
            ),
        )
        for mention in ordered_mentions:
            scope_identity = _scope_identity(mention.scope)
            explicit_relation = relations_by_source.get(mention.entity_id)
            if explicit_relation is not None:
                target_entity_id = resolved_entity_by_mention.get(explicit_relation.target_entity_id)
                target_link = next(
                    (
                        link
                        for link in links_by_key.values()
                        if link.canonical_entity_id == target_entity_id
                        and _scope_identity(link.scope) == scope_identity
                    ),
                    None,
                )
                if target_link is None:
                    decisions.append(
                        self._decision(
                            mention=mention,
                            decision_type=EntityIdentityDecisionType.ABSTAIN,
                            resolved_entity_id=None,
                            candidates=[],
                            confidence=0.0,
                            rationale="explicit identity relation target did not resolve in scope",
                            failure_code="identity_relation_target_unresolved",
                        )
                    )
                    continue
                if explicit_relation.relation_type == EntityIdentityRelationType.SPLIT_FROM:
                    _, link, transition = self.split_link(
                        existing=target_link,
                        mention=mention,
                    )
                    links_by_key[(link.normalized_name, link.canonical_entity_id, scope_identity)] = link
                    resolved.append(link)
                    transitions.append(transition)
                    resolved_entity_by_mention[mention.entity_id] = link.canonical_entity_id
                    decisions.append(
                        self._decision(
                            mention=mention,
                            decision_type=EntityIdentityDecisionType.SPLIT_EXISTING,
                            resolved_entity_id=link.canonical_entity_id,
                            candidates=[target_link],
                            parent_entity_id=target_link.canonical_entity_id,
                            confidence=link.confidence,
                            rationale="explicit grounded split relation preserves distinct lineage",
                        )
                    )
                    continue
                if explicit_relation.relation_type == EntityIdentityRelationType.MERGED_INTO:
                    duplicate_candidates = [
                        link
                        for link in links_by_key.values()
                        if link.canonical_entity_id != target_link.canonical_entity_id
                        and _scope_identity(link.scope) == scope_identity
                        and _shares_identity_alias(link=link, mention=mention)
                    ]
                    if len(duplicate_candidates) > 1:
                        decisions.append(
                            self._decision(
                                mention=mention,
                                decision_type=EntityIdentityDecisionType.ABSTAIN,
                                resolved_entity_id=None,
                                candidates=duplicate_candidates,
                                confidence=0.0,
                                rationale="merge source resolves to multiple scoped entities",
                                failure_code="entity_merge_source_ambiguous",
                            )
                        )
                        continue
                    if duplicate_candidates:
                        merged, invalidated, transition = self.merge_links(
                            primary=target_link,
                            duplicate=duplicate_candidates[0],
                        )
                        links_by_key[
                            (
                                merged.normalized_name,
                                merged.canonical_entity_id,
                                scope_identity,
                            )
                        ] = merged
                        resolved.extend([merged, invalidated])
                        transitions.append(transition)
                        resolved_entity_by_mention[mention.entity_id] = merged.canonical_entity_id
                        decisions.append(
                            self._decision(
                                mention=mention,
                                decision_type=EntityIdentityDecisionType.MERGE_EXISTING,
                                resolved_entity_id=merged.canonical_entity_id,
                                candidates=[duplicate_candidates[0], target_link],
                                confidence=merged.confidence,
                                rationale="explicit grounded merge retires the duplicate entity",
                            )
                        )
                        continue
                updated = self._reinforce_link(
                    existing=target_link,
                    mention=mention,
                    now=now,
                    explicit_alias=True,
                )
                links_by_key[(target_link.normalized_name, target_link.canonical_entity_id, scope_identity)] = updated
                resolved.append(updated)
                resolved_entity_by_mention[mention.entity_id] = updated.canonical_entity_id
                decisions.append(
                    self._decision(
                        mention=mention,
                        decision_type=(
                            EntityIdentityDecisionType.MERGE_EXISTING
                            if explicit_relation.relation_type == EntityIdentityRelationType.MERGED_INTO
                            else EntityIdentityDecisionType.REUSE_EXISTING
                        ),
                        resolved_entity_id=updated.canonical_entity_id,
                        candidates=[target_link],
                        confidence=updated.confidence,
                        rationale=("explicit grounded identity relation maps the mention to the resolved target"),
                    )
                )
                continue
            existing = links_by_key.get((mention.normalized_name, mention.entity_id, scope_identity))
            if existing is not None:
                updated = self._reinforce_link(existing=existing, mention=mention, now=now)
                links_by_key[(mention.normalized_name, mention.entity_id, scope_identity)] = updated
                resolved.append(updated)
                resolved_entity_by_mention[mention.entity_id] = updated.canonical_entity_id
                decisions.append(
                    self._decision(
                        mention=mention,
                        decision_type=EntityIdentityDecisionType.REUSE_EXISTING,
                        resolved_entity_id=existing.canonical_entity_id,
                        candidates=[existing],
                        confidence=updated.confidence,
                        rationale="exact entity identity and scope matched an active link",
                    )
                )
                continue

            same_entity = [
                link
                for link in links_by_key.values()
                if link.canonical_entity_id == mention.entity_id and _scope_identity(link.scope) == scope_identity
            ]
            if len(same_entity) == 1:
                existing = same_entity[0]
                updated = self._reinforce_link(existing=existing, mention=mention, now=now)
                links_by_key[(existing.normalized_name, mention.entity_id, scope_identity)] = updated
                resolved.append(updated)
                resolved_entity_by_mention[mention.entity_id] = updated.canonical_entity_id
                decisions.append(
                    self._decision(
                        mention=mention,
                        decision_type=EntityIdentityDecisionType.REUSE_EXISTING,
                        resolved_entity_id=existing.canonical_entity_id,
                        candidates=same_entity,
                        confidence=updated.confidence,
                        rationale="canonical entity identity and scope matched an active alias",
                    )
                )
                continue

            exact_alias_candidates = [
                link
                for link in links_by_key.values()
                if _shares_identity_alias(link=link, mention=mention)
                and link.canonical_entity_id != mention.entity_id
                and _scope_identity(link.scope) == scope_identity
            ]
            same_name = exact_alias_candidates
            type_consistent_aliases = [
                link
                for link in same_name
                if mention.entity_type == EntityType.UNKNOWN
                or link.entity_type == EntityType.UNKNOWN
                or link.entity_type == mention.entity_type
            ]
            if len(type_consistent_aliases) == 1:
                existing = type_consistent_aliases[0]
                updated = self._reinforce_link(existing=existing, mention=mention, now=now)
                links_by_key[(existing.normalized_name, existing.canonical_entity_id, scope_identity)] = updated
                resolved.append(updated)
                resolved_entity_by_mention[mention.entity_id] = updated.canonical_entity_id
                decisions.append(
                    self._decision(
                        mention=mention,
                        decision_type=EntityIdentityDecisionType.REUSE_EXISTING,
                        resolved_entity_id=existing.canonical_entity_id,
                        candidates=type_consistent_aliases,
                        confidence=updated.confidence,
                        rationale="one scoped alias candidate has a compatible grounded entity type",
                    )
                )
                continue
            split_parent = self._split_parent(mention=mention, candidates=same_name)
            if split_parent is not None:
                _, link, transition = self.split_link(existing=split_parent, mention=mention)
                links_by_key[(mention.normalized_name, mention.entity_id, scope_identity)] = link
                resolved.append(link)
                resolved_entity_by_mention[mention.entity_id] = link.canonical_entity_id
                transitions.append(transition)
                decisions.append(
                    self._decision(
                        mention=mention,
                        decision_type=EntityIdentityDecisionType.SPLIT_EXISTING,
                        resolved_entity_id=mention.entity_id,
                        candidates=same_name,
                        parent_entity_id=split_parent.canonical_entity_id,
                        confidence=link.confidence,
                        rationale="grounded same-name mention has a distinct known entity type",
                        semantic_discriminators=[
                            f"parent_type:{split_parent.entity_type.value}",
                            f"child_type:{mention.entity_type.value}",
                        ],
                    )
                )
                continue
            if same_name:
                decisions.append(
                    self._decision(
                        mention=mention,
                        decision_type=EntityIdentityDecisionType.ABSTAIN,
                        resolved_entity_id=None,
                        candidates=same_name,
                        confidence=0.0,
                        rationale="same-name candidates lack sufficient grounded identity discriminators",
                        failure_code=(
                            "entity_identity_evidence_missing"
                            if not mention.evidence_spans
                            else "entity_identity_ambiguous"
                        ),
                    )
                )
                continue
            visible_typed_candidates = _visible_typed_identity_candidates(
                mention=mention,
                links=links_by_key.values(),
            )
            if len(visible_typed_candidates) == 1:
                existing = visible_typed_candidates[0]
                updated = self._project_link_into_scope(
                    existing=existing,
                    mention=mention,
                    now=now,
                )
                links_by_key[
                    (
                        updated.normalized_name,
                        updated.canonical_entity_id,
                        _scope_identity(updated.scope),
                    )
                ] = updated
                resolved.append(updated)
                resolved_entity_by_mention[mention.entity_id] = updated.canonical_entity_id
                decisions.append(
                    self._decision(
                        mention=mention,
                        decision_type=EntityIdentityDecisionType.REUSE_EXISTING,
                        resolved_entity_id=existing.canonical_entity_id,
                        candidates=visible_typed_candidates,
                        confidence=updated.confidence,
                        rationale=(
                            "one readable less-specific entity has an exact identity name and the same grounded type"
                        ),
                    )
                )
                continue
            if visible_typed_candidates:
                decisions.append(
                    self._decision(
                        mention=mention,
                        decision_type=EntityIdentityDecisionType.ABSTAIN,
                        resolved_entity_id=None,
                        candidates=visible_typed_candidates,
                        confidence=0.0,
                        rationale=("multiple readable less-specific entities share the exact typed identity"),
                        failure_code="entity_identity_ambiguous",
                    )
                )
                continue
            link = EntityLinkState(
                link_id=_entity_link_id(
                    entity_id=mention.entity_id,
                    normalized_name=mention.normalized_name,
                    scope=mention.scope,
                ),
                mention_text=mention.mention_text,
                canonical_entity_id=mention.entity_id,
                normalized_name=mention.normalized_name,
                entity_type=mention.entity_type,
                aliases=sorted(set(mention.aliases)),
                observed_names=sorted({mention.mention_text, mention.normalized_name}),
                evidence_spans=list(mention.evidence_spans),
                confidence=mention.confidence,
                scope=mention.scope,
                created_at=now,
                updated_at=now,
            )
            links_by_key[(mention.normalized_name, mention.entity_id, scope_identity)] = link
            resolved.append(link)
            resolved_entity_by_mention[mention.entity_id] = link.canonical_entity_id
            decisions.append(
                self._decision(
                    mention=mention,
                    decision_type=EntityIdentityDecisionType.CREATE_DISTINCT,
                    resolved_entity_id=mention.entity_id,
                    candidates=[],
                    confidence=mention.confidence,
                    rationale="no active entity candidate matched this scoped identity",
                )
            )
        return EntityResolutionOutcome(
            decisions=decisions,
            links=_final_link_states(resolved),
            transitions=transitions,
        )

    @staticmethod
    def _reinforce_link(
        *,
        existing: EntityLinkState,
        mention: EntityMention,
        now: datetime,
        explicit_alias: bool = False,
    ) -> EntityLinkState:
        aliases = {*existing.aliases, *mention.aliases}
        if explicit_alias:
            aliases.update({mention.mention_text, mention.normalized_name})
        return existing.model_copy(
            update={
                "entity_type": (
                    mention.entity_type
                    if existing.entity_type == EntityType.UNKNOWN and mention.entity_type != EntityType.UNKNOWN
                    else existing.entity_type
                ),
                "aliases": sorted(aliases),
                "observed_names": sorted(
                    {
                        *existing.observed_names,
                        mention.mention_text,
                        mention.normalized_name,
                    }
                ),
                "evidence_spans": [*existing.evidence_spans, *mention.evidence_spans],
                "confidence": min(1.0, max(existing.confidence, mention.confidence) + 0.05),
                "updated_at": now,
            }
        )

    @staticmethod
    def _project_link_into_scope(
        *,
        existing: EntityLinkState,
        mention: EntityMention,
        now: datetime,
    ) -> EntityLinkState:
        return existing.model_copy(
            update={
                "link_id": _entity_link_id(
                    entity_id=existing.canonical_entity_id,
                    normalized_name=existing.normalized_name,
                    scope=mention.scope,
                ),
                "aliases": sorted({*existing.aliases, *mention.aliases}),
                "observed_names": sorted(
                    {
                        *existing.observed_names,
                        mention.mention_text,
                        mention.normalized_name,
                    }
                ),
                "evidence_spans": [
                    *existing.evidence_spans,
                    *mention.evidence_spans,
                ],
                "confidence": min(
                    1.0,
                    max(existing.confidence, mention.confidence) + 0.05,
                ),
                "scope": mention.scope,
                "created_at": now,
                "updated_at": now,
            }
        )

    @staticmethod
    def _split_parent(
        *,
        mention: EntityMention,
        candidates: list[EntityLinkState],
    ) -> EntityLinkState | None:
        if not mention.evidence_spans or mention.entity_type == EntityType.UNKNOWN:
            return None
        typed_candidates = [
            candidate
            for candidate in candidates
            if candidate.entity_type != EntityType.UNKNOWN and candidate.entity_type != mention.entity_type
        ]
        return typed_candidates[0] if len(typed_candidates) == 1 else None

    @staticmethod
    def _decision(
        *,
        mention: EntityMention,
        decision_type: EntityIdentityDecisionType,
        resolved_entity_id: str | None,
        candidates: list[EntityLinkState],
        confidence: float,
        rationale: str,
        parent_entity_id: str | None = None,
        semantic_discriminators: list[str] | None = None,
        failure_code: str | None = None,
    ) -> EntityIdentityDecision:
        candidate_ids = sorted({candidate.canonical_entity_id for candidate in candidates})
        evidence_ids = sorted({span.source_id for span in mention.evidence_spans})
        identity = "|".join(
            [
                mention.entity_id,
                mention.scope.stable_id(),
                decision_type.value,
                parent_entity_id or "",
                *candidate_ids,
                *evidence_ids,
            ]
        )
        return EntityIdentityDecision(
            decision_id=_stable_id("entity-decision", identity),
            decision_type=decision_type,
            mention_entity_id=mention.entity_id,
            resolved_entity_id=resolved_entity_id,
            candidate_entity_ids=candidate_ids,
            parent_entity_id=parent_entity_id,
            evidence_source_ids=evidence_ids,
            semantic_discriminators=semantic_discriminators or [],
            scope=mention.scope,
            confidence=confidence,
            rationale=rationale,
            failure_code=failure_code,
        )

    def link_for_entity(
        self,
        entity_id: str | None,
        links: list[EntityLinkState],
        *,
        scope: MemoryScope,
    ) -> EntityLinkState | None:
        if entity_id is None:
            return None
        for link in links:
            if link.canonical_entity_id == entity_id and link.scope == scope:
                return link
        return None

    @staticmethod
    def canonical_reference_map(
        outcome: EntityResolutionOutcome,
    ) -> dict[ScopedEntityReference, str]:
        """Map request-local entity references to resolved scoped identities."""

        return {
            (
                decision.mention_entity_id,
                _scope_identity(decision.scope),
            ): decision.resolved_entity_id
            for decision in outcome.decisions
            if decision.resolved_entity_id is not None
        }

    def canonicalize_claim_entities(
        self,
        *,
        claim: ExtractedClaim,
        references: dict[ScopedEntityReference, str],
    ) -> tuple[ExtractedClaim, ClaimLifecycleTransition | None]:
        """Resolve every entity-bearing claim field before persistence."""

        old_key = claim.claim_key
        scope_identity = _scope_identity(old_key.scope)
        subject_entity_id = references.get(
            (old_key.subject_entity_id, scope_identity),
            old_key.subject_entity_id,
        )
        object_entity_id = (
            references.get(
                (claim.object_entity_id, scope_identity),
                claim.object_entity_id,
            )
            if claim.object_entity_id is not None
            else None
        )
        belief_holder_entity_id = (
            references.get(
                (claim.semantic_context.belief_holder_entity_id, scope_identity),
                claim.semantic_context.belief_holder_entity_id,
            )
            if claim.semantic_context.belief_holder_entity_id is not None
            else None
        )
        if (
            subject_entity_id == old_key.subject_entity_id
            and object_entity_id == claim.object_entity_id
            and belief_holder_entity_id == claim.semantic_context.belief_holder_entity_id
        ):
            return claim, None
        updated_key = old_key.model_copy(
            update={
                "subject_entity_id": subject_entity_id,
                "belief_holder_entity_id": belief_holder_entity_id,
            }
        )
        updated_context = claim.semantic_context.model_copy(
            update={"belief_holder_entity_id": belief_holder_entity_id}
        )
        updated_claim = claim.model_copy(
            update={
                "claim_key": updated_key,
                "object_entity_id": object_entity_id,
                "semantic_context": updated_context,
            }
        )
        transition = ClaimLifecycleTransition(
            transition_id=_stable_id(
                "transition",
                "|".join(
                    [
                        claim.claim_id,
                        "claim_rekey",
                        subject_entity_id,
                        object_entity_id or "",
                        belief_holder_entity_id or "",
                    ]
                ),
            ),
            transition_type=ClaimTransitionType.CLAIM_REKEY,
            claim_id=claim.claim_id,
            related_claim_ids=[],
            rationale=(
                "claim entity references canonicalized "
                f"from subject={old_key.subject_entity_id},object={claim.object_entity_id or ''} "
                f"to subject={subject_entity_id},object={object_entity_id or ''},"
                f"belief_holder={belief_holder_entity_id or ''}"
            ),
            timestamp=self._now_provider(),
        )
        return updated_claim, transition

    @staticmethod
    def canonicalize_action_entities(
        *,
        action: ExtractedAction,
        references: dict[ScopedEntityReference, str],
    ) -> ExtractedAction:
        """Resolve every entity-bearing action reference in one explicit boundary."""

        scope_identity = _scope_identity(action.scope)

        def resolve(entity_id: str) -> str:
            return references.get((entity_id, scope_identity), entity_id)

        return action.model_copy(
            update={
                "actor_entity_id": (resolve(action.actor_entity_id) if action.actor_entity_id is not None else None),
                "target_entity_ids": [resolve(entity_id) for entity_id in action.target_entity_ids],
                "dependency_entity_ids": [resolve(entity_id) for entity_id in action.dependency_entity_ids],
                "blocking_entity_ids": [resolve(entity_id) for entity_id in action.blocking_entity_ids],
            }
        )

    def merge_links(
        self,
        *,
        primary: EntityLinkState,
        duplicate: EntityLinkState,
    ) -> tuple[EntityLinkState, EntityLinkState, ClaimLifecycleTransition]:
        if _scope_identity(primary.scope) != _scope_identity(duplicate.scope):
            raise ValueError("entity links from different scopes cannot be merged")
        now = self._now_provider()
        merged = primary.model_copy(
            update={
                "aliases": sorted({*primary.aliases, *duplicate.aliases}),
                "observed_names": sorted(
                    {
                        *primary.observed_names,
                        *duplicate.observed_names,
                        duplicate.mention_text,
                        duplicate.normalized_name,
                    }
                ),
                "evidence_spans": [*primary.evidence_spans, *duplicate.evidence_spans],
                "confidence": min(1.0, max(primary.confidence, duplicate.confidence) + 0.05),
                "updated_at": now,
            }
        )
        invalidated = duplicate.model_copy(
            update={
                "lifecycle_state": EntityLinkLifecycleState.MERGED,
                "superseded_by_entity_id": primary.canonical_entity_id,
                "valid_to": now,
                "updated_at": now,
            }
        )
        transition = ClaimLifecycleTransition(
            transition_id=_stable_id("transition", f"{primary.link_id}:entity_merge:{duplicate.link_id}"),
            transition_type=ClaimTransitionType.ENTITY_MERGE,
            claim_id=primary.canonical_entity_id,
            related_claim_ids=[duplicate.canonical_entity_id],
            rationale=f"entity link {duplicate.canonical_entity_id} merged into {primary.canonical_entity_id}",
        )
        return merged, invalidated, transition

    def split_link(
        self,
        *,
        existing: EntityLinkState,
        mention: EntityMention,
    ) -> tuple[EntityLinkState, EntityLinkState, ClaimLifecycleTransition]:
        now = self._now_provider()
        if _scope_identity(existing.scope) != _scope_identity(mention.scope):
            raise ValueError("entity links from different scopes cannot be split")
        if not mention.evidence_spans:
            raise ValueError("entity split requires grounded evidence")
        new_link = EntityLinkState(
            link_id=_entity_link_id(
                entity_id=mention.entity_id,
                normalized_name=mention.normalized_name,
                scope=existing.scope,
            ),
            mention_text=mention.mention_text,
            canonical_entity_id=mention.entity_id,
            normalized_name=mention.normalized_name,
            entity_type=mention.entity_type,
            aliases=sorted(set(mention.aliases)),
            observed_names=sorted({mention.mention_text, mention.normalized_name}),
            evidence_spans=list(mention.evidence_spans),
            confidence=mention.confidence,
            scope=existing.scope,
            lineage_parent_entity_id=existing.canonical_entity_id,
            valid_from=now,
            created_at=now,
            updated_at=now,
        )
        transition = ClaimLifecycleTransition(
            transition_id=_stable_id("transition", f"{existing.link_id}:entity_split:{mention.entity_id}"),
            transition_type=ClaimTransitionType.ENTITY_SPLIT,
            claim_id=existing.canonical_entity_id,
            related_claim_ids=[mention.entity_id],
            rationale=f"entity link {existing.canonical_entity_id} split to preserve distinct entity {mention.entity_id}",
            timestamp=now,
        )
        return existing, new_link, transition


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"


def _final_link_states(links: Iterable[EntityLinkState]) -> list[EntityLinkState]:
    order: list[str] = []
    latest: dict[str, EntityLinkState] = {}
    for link in links:
        if link.link_id not in latest:
            order.append(link.link_id)
        latest[link.link_id] = link
    return [latest[link_id] for link_id in order]


def _shares_identity_alias(*, link: EntityLinkState, mention: EntityMention) -> bool:
    link_names = {
        key
        for value in [
            link.mention_text,
            link.normalized_name,
            *link.observed_names,
            *link.aliases,
        ]
        for key in _identity_keys(value)
    }
    mention_names = {
        key
        for value in [mention.normalized_name, mention.mention_text, *mention.aliases]
        for key in _identity_keys(value)
    }
    link_names.discard("")
    mention_names.discard("")
    return bool(link_names & mention_names)


def _visible_typed_identity_candidates(
    *,
    mention: EntityMention,
    links: Iterable[EntityLinkState],
) -> list[EntityLinkState]:
    if mention.entity_type == EntityType.UNKNOWN:
        return []
    candidates_by_id = {
        link.link_id: link
        for link in links
        if link.entity_type == mention.entity_type
        and link.entity_type != EntityType.UNKNOWN
        and link.scope != mention.scope
        and mention.scope.can_read(link.scope)
        and _shares_identity_alias(link=link, mention=mention)
    }
    if not candidates_by_id:
        return []
    most_specific = max(link.scope.specificity for link in candidates_by_id.values())
    return sorted(
        (link for link in candidates_by_id.values() if link.scope.specificity == most_specific),
        key=lambda link: (link.canonical_entity_id, link.link_id),
    )


def _mention_resolution_key(mention: EntityMention) -> tuple[str, str, str, str]:
    return (
        mention.scope.stable_id(),
        mention.entity_type.value,
        mention.entity_id,
        mention.normalized_name,
    )


def _identity_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _identity_keys(value: str) -> set[str]:
    base = _identity_key(value)
    return {base} if base else set()


def _entity_link_id(
    *,
    entity_id: str,
    normalized_name: str,
    scope: MemoryScope,
) -> str:
    scope_identity = "|".join(value or "" for value in _scope_identity(scope))
    return _stable_id("entity-link", f"{entity_id}:{normalized_name}:{scope_identity}")

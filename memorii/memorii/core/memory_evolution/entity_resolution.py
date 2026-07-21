"""Entity-link lifecycle helpers for memory evolution."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from memorii.core.memory_evolution.models import (
    ClaimLifecycleTransition,
    ClaimTransitionType,
    EntityIdentityDecision,
    EntityIdentityDecisionType,
    EntityLinkLifecycleState,
    EntityLinkState,
    EntityMention,
    EntityResolutionOutcome,
    EntityType,
    ExtractedClaim,
    MemoryScope,
)


def _scope_identity(scope: MemoryScope) -> tuple[str | None, str | None, str | None]:
    return scope.identity


class EntityResolutionService:
    def __init__(self, *, now_provider: Callable[[], datetime] | None = None) -> None:
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def resolve_mentions(
        self,
        mentions: list[EntityMention],
        existing_links: list[EntityLinkState],
    ) -> EntityResolutionOutcome:
        links_by_key = {
            (link.normalized_name, link.canonical_entity_id, _scope_identity(link.scope)): link
            for link in existing_links
            if link.lifecycle_state == EntityLinkLifecycleState.ACTIVE
        }
        resolved: list[EntityLinkState] = []
        decisions: list[EntityIdentityDecision] = []
        transitions: list[ClaimLifecycleTransition] = []
        now = self._now_provider()
        for mention in mentions:
            scope_identity = _scope_identity(mention.scope)
            existing = links_by_key.get((mention.normalized_name, mention.entity_id, scope_identity))
            if existing is not None:
                updated = self._reinforce_link(existing=existing, mention=mention, now=now)
                links_by_key[(mention.normalized_name, mention.entity_id, scope_identity)] = updated
                resolved.append(updated)
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
                links_by_key.pop((existing.normalized_name, existing.canonical_entity_id, scope_identity))
                links_by_key[(mention.normalized_name, mention.entity_id, scope_identity)] = updated
                resolved.append(updated)
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

            same_name = [
                link
                for link in links_by_key.values()
                if _shares_identity_alias(link=link, mention=mention)
                and link.canonical_entity_id != mention.entity_id
                and _scope_identity(link.scope) == scope_identity
            ]
            split_parent = self._split_parent(mention=mention, candidates=same_name)
            if split_parent is not None:
                _, link, transition = self.split_link(existing=split_parent, mention=mention)
                links_by_key[(mention.normalized_name, mention.entity_id, scope_identity)] = link
                resolved.append(link)
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
                aliases=sorted({mention.mention_text, mention.normalized_name, *mention.aliases}),
                evidence_spans=list(mention.evidence_spans),
                confidence=mention.confidence,
                scope=mention.scope,
                created_at=now,
                updated_at=now,
            )
            links_by_key[(mention.normalized_name, mention.entity_id, scope_identity)] = link
            resolved.append(link)
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
            links=resolved,
            transitions=transitions,
        )

    @staticmethod
    def _reinforce_link(
        *,
        existing: EntityLinkState,
        mention: EntityMention,
        now: datetime,
    ) -> EntityLinkState:
        return existing.model_copy(
            update={
                "mention_text": mention.mention_text,
                "normalized_name": mention.normalized_name,
                "entity_type": (
                    mention.entity_type if mention.entity_type != EntityType.UNKNOWN else existing.entity_type
                ),
                "aliases": sorted({*existing.aliases, mention.mention_text, mention.normalized_name, *mention.aliases}),
                "evidence_spans": [*existing.evidence_spans, *mention.evidence_spans],
                "confidence": min(1.0, max(existing.confidence, mention.confidence) + 0.05),
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

    def rekey_claim(
        self,
        *,
        claim: ExtractedClaim,
        new_subject_entity_id: str,
    ) -> tuple[ExtractedClaim, ClaimLifecycleTransition]:
        old_key = claim.claim_key
        updated_key = old_key.model_copy(update={"subject_entity_id": new_subject_entity_id})
        updated_claim = claim.model_copy(update={"claim_key": updated_key})
        transition = ClaimLifecycleTransition(
            transition_id=_stable_id("transition", f"{claim.claim_id}:claim_rekey:{new_subject_entity_id}"),
            transition_type=ClaimTransitionType.CLAIM_REKEY,
            claim_id=claim.claim_id,
            related_claim_ids=[],
            rationale=f"claim rekeyed from {old_key.subject_entity_id} to {new_subject_entity_id}",
        )
        return updated_claim, transition

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
                "aliases": sorted({*primary.aliases, *duplicate.aliases, duplicate.mention_text}),
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
            aliases=sorted({mention.mention_text, mention.normalized_name, *mention.aliases}),
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


def _shares_identity_alias(*, link: EntityLinkState, mention: EntityMention) -> bool:
    link_names = {_identity_key(value) for value in [link.normalized_name, *link.aliases]}
    mention_names = {
        _identity_key(value) for value in [mention.normalized_name, mention.mention_text, *mention.aliases]
    }
    return bool((link_names - {""}) & (mention_names - {""}))


def _identity_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _entity_link_id(
    *,
    entity_id: str,
    normalized_name: str,
    scope: MemoryScope,
) -> str:
    scope_identity = "|".join(value or "" for value in _scope_identity(scope))
    return _stable_id("entity-link", f"{entity_id}:{normalized_name}:{scope_identity}")

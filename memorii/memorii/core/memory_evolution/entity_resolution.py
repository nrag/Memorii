"""Entity-link lifecycle helpers for memory evolution."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from memorii.core.memory_evolution.models import (
    ClaimLifecycleTransition,
    ClaimTransitionType,
    EntityLinkLifecycleState,
    EntityLinkState,
    EntityMention,
    ExtractedClaim,
)


class EntityResolutionService:
    def __init__(self, *, now_provider: Callable[[], datetime] | None = None) -> None:
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def resolve_mentions(self, mentions: list[EntityMention], existing_links: list[EntityLinkState]) -> list[EntityLinkState]:
        links_by_key = {
            (link.normalized_name, link.canonical_entity_id): link
            for link in existing_links
            if link.lifecycle_state == EntityLinkLifecycleState.ACTIVE
        }
        links_by_name = {}
        for link in links_by_key.values():
            links_by_name.setdefault(link.normalized_name, []).append(link)
        resolved: list[EntityLinkState] = []
        now = self._now_provider()
        for mention in mentions:
            existing = links_by_key.get((mention.normalized_name, mention.entity_id))
            if existing is not None:
                aliases = sorted({*existing.aliases, mention.mention_text, mention.normalized_name})
                evidence = [*existing.evidence_spans, *mention.evidence_spans]
                confidence = min(1.0, max(existing.confidence, mention.confidence) + 0.05)
                updated = existing.model_copy(
                    update={
                        "aliases": aliases,
                        "evidence_spans": evidence,
                        "confidence": confidence,
                        "updated_at": now,
                    }
                )
                links_by_key[(mention.normalized_name, mention.entity_id)] = updated
                resolved.append(updated)
                continue
            link = EntityLinkState(
                link_id=_stable_id("entity-link", f"{mention.entity_id}:{mention.normalized_name}"),
                mention_text=mention.mention_text,
                canonical_entity_id=mention.entity_id,
                normalized_name=mention.normalized_name,
                entity_type=mention.entity_type,
                aliases=sorted({mention.mention_text, mention.normalized_name}),
                evidence_spans=list(mention.evidence_spans),
                confidence=mention.confidence,
                created_at=now,
                updated_at=now,
                lineage_parent_entity_id=(
                    links_by_name[mention.normalized_name][0].canonical_entity_id
                    if links_by_name.get(mention.normalized_name)
                    and links_by_name[mention.normalized_name][0].canonical_entity_id != mention.entity_id
                    else None
                ),
            )
            links_by_key[(mention.normalized_name, mention.entity_id)] = link
            links_by_name.setdefault(mention.normalized_name, []).append(link)
            resolved.append(link)
        return resolved

    def link_for_entity(self, entity_id: str | None, links: list[EntityLinkState]) -> EntityLinkState | None:
        if entity_id is None:
            return None
        for link in links:
            if link.canonical_entity_id == entity_id:
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
        new_entity_id: str,
        mention_text: str,
    ) -> tuple[EntityLinkState, EntityLinkState, ClaimLifecycleTransition]:
        now = self._now_provider()
        split_existing = existing.model_copy(
            update={
                "lifecycle_state": EntityLinkLifecycleState.SPLIT,
                "valid_to": now,
                "updated_at": now,
            }
        )
        new_link = EntityLinkState(
            link_id=_stable_id("entity-link", f"{new_entity_id}:{mention_text.lower()}"),
            mention_text=mention_text,
            canonical_entity_id=new_entity_id,
            normalized_name=mention_text.lower(),
            entity_type=existing.entity_type,
            aliases=[mention_text, mention_text.lower()],
            evidence_spans=[],
            confidence=max(0.5, existing.confidence - 0.1),
            lineage_parent_entity_id=existing.canonical_entity_id,
            valid_from=now,
        )
        transition = ClaimLifecycleTransition(
            transition_id=_stable_id("transition", f"{existing.link_id}:entity_split:{new_entity_id}"),
            transition_type=ClaimTransitionType.ENTITY_SPLIT,
            claim_id=existing.canonical_entity_id,
            related_claim_ids=[new_entity_id],
            rationale=f"entity link {existing.canonical_entity_id} split to preserve distinct entity {new_entity_id}",
        )
        return split_existing, new_link, transition


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"

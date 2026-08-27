"""Resolve certified complete temporal intervals by policy rank.

The resolver never combines bounds and accepts only complete, revalidated
policy snapshots; it is the one owner of rank-based temporal evidence
selection for both projection history and policy migration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from memorii.core.semantic_ingestion.contracts import (
    PredicateTrustRule,
    TemporalEvidenceCandidate,
    TemporalEvidenceDecisionClosure,
    TemporalPolicySnapshot,
    TemporalReferenceEvidence,
    TimeInterval,
    TrustPolicySnapshot,
    contract_digest,
)


class TemporalEvidenceResolver:
    """Resolve certified complete intervals by policy rank; never combine bounds."""

    def resolve(
        self,
        *,
        predicate_id: str,
        candidates: tuple[TemporalEvidenceCandidate, ...],
        reference_evidence: TemporalReferenceEvidence | None = None,
        source_present_attachment: bool = False,
        trust_policy: TrustPolicySnapshot,
        temporal_policy: TemporalPolicySnapshot,
        arbitration_as_of: datetime,
    ) -> TemporalEvidenceDecisionClosure:
        # Revalidate model-copy/replay inputs and both complete policy snapshots
        # before any authority value can influence selection.
        TrustPolicySnapshot.model_validate(trust_policy.model_dump(mode="python"))
        TemporalPolicySnapshot.model_validate(temporal_policy.model_dump(mode="python"))
        rule = trust_policy.rule_for(predicate_id)
        temporal_rule = temporal_policy.rule_for(predicate_id)
        ordered = tuple(sorted(candidates, key=lambda candidate: candidate.candidate_id))
        if len({candidate.candidate_id for candidate in ordered}) != len(ordered):
            return self._closure("unknown", ordered, (), (), None, "unresolved", trust_policy, temporal_policy, arbitration_as_of)
        if temporal_rule.valid_time_requirement == "atemporal":
            if ordered or source_present_attachment:
                return self._closure("unknown", ordered, (), (), None, "unresolved", trust_policy, temporal_policy, arbitration_as_of)
            return self._closure("pass", (), (), (), None, "atemporal", trust_policy, temporal_policy, arbitration_as_of)
        if not ordered:
            if reference_evidence is not None and (
                temporal_rule.allow_reference_as_effective_start and temporal_rule.allow_open_end
            ):
                return self._closure(
                    "pass", (), (), (), TimeInterval(start=reference_evidence.reference_instant),
                    "authenticated_reference_open_start", trust_policy, temporal_policy,
                    arbitration_as_of,
                )
            if temporal_rule.valid_time_requirement == "optional" and not source_present_attachment:
                return self._closure("pass", (), (), (), None, "atemporal", trust_policy, temporal_policy, arbitration_as_of)
            return self._closure("unknown", (), (), (), None, "unresolved", trust_policy, temporal_policy, arbitration_as_of)
        try:
            for candidate in ordered:
                TemporalEvidenceCandidate.model_validate(candidate.model_dump(mode="python"))
                if candidate.interval.end is None and not temporal_rule.allow_open_end:
                    raise ValueError("open interval is disallowed")
                if candidate.source_authority.authority_class not in rule.authority_rank_by_class:
                    raise ValueError("unknown source authority class")
        except ValueError:
            return self._closure("unknown", ordered, (), (), None, "unresolved", trust_policy, temporal_policy, arbitration_as_of)
        eligible = tuple(
            item for item in ordered
            if item.source_authority.authority_class in rule.eligible_authority_classes
        )
        if not eligible:
            return self._closure("unknown", ordered, (), (), None, "unresolved", trust_policy, temporal_policy, arbitration_as_of)
        top = tuple(
            item for item in eligible
            if not any(self._dominates(other, item, rule) for other in eligible)
        )
        if len({(item.interval.start, item.interval.end) for item in top}) != 1:
            return self._closure(
                "contested", ordered, (), tuple(sorted(item.candidate_id for item in top)), None,
                "trust_contested_nonidentical_top_evidence", trust_policy, temporal_policy, arbitration_as_of,
            )
        interval = top[0].interval
        supporters = tuple(sorted(item.candidate_id for item in eligible if item.interval == interval))
        kinds = {item.kind for item in eligible if item.interval == interval}
        resolution = "trust_co_supported_equal_interval" if len(supporters) > 1 else (
            "trust_selected_text_interval" if kinds == {"certified_text_interval"}
            else "trust_selected_source_interval"
        )
        return self._closure(
            "pass", ordered, supporters, (), interval, resolution,
            trust_policy, temporal_policy, arbitration_as_of,
        )

    @staticmethod
    def _dominates(
        left: TemporalEvidenceCandidate,
        right: TemporalEvidenceCandidate,
        rule: PredicateTrustRule,
    ) -> bool:
        pair = tuple(sorted((left.source_authority.authority_class, right.source_authority.authority_class)))
        if left.source_authority.authority_class != right.source_authority.authority_class and pair in rule.incomparable_class_pairs:
            return False
        return rule.authority_rank_by_class[left.source_authority.authority_class] > rule.authority_rank_by_class[right.source_authority.authority_class]

    @staticmethod
    def _closure(
        outcome: Literal["pass", "unknown", "contested"],
        candidates: tuple[TemporalEvidenceCandidate, ...],
        selected: tuple[str, ...],
        contested: tuple[str, ...],
        interval: TimeInterval | None,
        resolution: str,
        trust: TrustPolicySnapshot,
        temporal: TemporalPolicySnapshot,
        coordinate: datetime,
    ) -> TemporalEvidenceDecisionClosure:
        body = {
            "outcome": outcome,
            "candidates": candidates,
            "selected_candidate_ids": selected,
            "contested_candidate_ids": contested,
            "resolved_interval": interval,
            "resolution_rule": resolution,
            "temporal_policy_fingerprint": temporal.fingerprint,
            "temporal_policy_snapshot_digest": temporal.snapshot_digest,
            "trust_policy_fingerprint": trust.fingerprint,
            "trust_policy_snapshot_digest": trust.snapshot_digest,
            "arbitration_as_of": coordinate,
        }
        return TemporalEvidenceDecisionClosure(
            **body,
            closure_digest=contract_digest(b"memorii.semantic-ingestion.temporal-decision-closure.v1", body),
        )


__all__ = ["TemporalEvidenceResolver"]

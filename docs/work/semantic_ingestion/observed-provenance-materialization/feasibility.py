"""Nonproduction feasibility of retained native provenance materialization.

This module demonstrates field availability and fail-closed joins. It is not
the runtime materializer and does not certify a provider or public endpoint.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from memorii.core.memory_evolution.graph_planning import (
    PlanningCommitValues,
    materialize_canonical_planning_payload,
)
from memorii.core.memory_evolution.graph_records import graph_record_id
from memorii.core.semantic_ingestion.contracts import (
    BootstrapNativeAcceptedOperationEffectV3,
    BootstrapNativeActionStateEffectV3,
    BootstrapNativeCorrectionEffectV3,
    BootstrapNativeEvidenceProjectionV3,
    BootstrapNativeFactEffectV3,
    BootstrapNativeIdentityEffectV3,
    BootstrapNativeOperationCompilationV3,
    BootstrapNativePlanningRecordV3,
    BootstrapNativeRetractionEffectV3,
)


@dataclass(frozen=True)
class RetainedProvenanceContext:
    """The exact tuple the proposed public record would copy from authority."""

    target_kind: str
    target_id: str
    proof_ancestry_ids: tuple[str, ...]
    policy_fingerprints: tuple[str, ...]


def _effect_authority(
    effect: BootstrapNativeAcceptedOperationEffectV3,
) -> tuple[tuple[BootstrapNativeEvidenceProjectionV3, ...], tuple[BootstrapNativePlanningRecordV3, ...], tuple[str, ...]]:
    """Select retained records and the closed digest path for every native arm."""
    if isinstance(effect, BootstrapNativeFactEffectV3):
        return effect.evidence_projections, effect.planning_records, (effect.effect_digest,)
    if isinstance(effect, BootstrapNativeCorrectionEffectV3):
        replacement = effect.replacement_effect
        expected_transitions = tuple(item for item in replacement.planning_records
                                     if item.record_kind == "temporal_transition")
        if effect.transition_records != expected_transitions:
            raise ValueError("correction transition view differs from its canonical record owner")
        return (
            replacement.evidence_projections,
            replacement.planning_records,
            (effect.effect_digest, replacement.effect_digest),
        )
    if isinstance(effect, BootstrapNativeRetractionEffectV3):
        return effect.evidence_projections, effect.transition_records, (effect.effect_digest,)
    if isinstance(effect, BootstrapNativeActionStateEffectV3):
        return effect.evidence_projections, effect.planning_records, (effect.effect_digest,)
    if isinstance(effect, BootstrapNativeIdentityEffectV3):
        materialization = effect.materialization
        return (
            effect.evidence_projections,
            (
                *materialization.revision_and_alias_records,
                materialization.lineage_record,
                *materialization.reference_disposition_records,
            ),
            (effect.effect_digest,),
        )
    raise TypeError(f"unsupported accepted effect: {type(effect)!r}")


def _exact_payload_value(record: BootstrapNativePlanningRecordV3, name: str) -> str:
    value = record.planning_payload.planning_record.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError("retained planning payload lacks exact record coordinate")
    return value


def _retained_materialization(
    record: BootstrapNativePlanningRecordV3,
    *,
    retained_records: Sequence[BaseModel],
    commit_values: PlanningCommitValues,
    authorizing_transaction_group_id: str,
) -> BaseModel:
    materialized = materialize_canonical_planning_payload(
        record.planning_payload,
        commit_values=commit_values,
        authorizing_transaction_group_id=authorizing_transaction_group_id,
    )
    if record.record_id != graph_record_id(materialized) or record.record_kind != materialized.record_kind:
        raise ValueError("native record metadata differs from canonical materialized identity")
    matches = tuple(
        item for item in retained_records
        if getattr(item, "record_kind", None) == materialized.record_kind
        and graph_record_id(item) == graph_record_id(materialized)
    )
    if len(matches) != 1 or matches[0] != materialized:
        raise ValueError("retained graph inventory does not match native materialization")
    return materialized


def _policy_context(compilation: BootstrapNativeOperationCompilationV3) -> tuple[str, ...]:
    authority = compilation.operation_input.planning_construction_authority
    if authority is None:
        raise ValueError("missing retained planning authority")
    values = {
        authority.predicate_registry_fingerprint,
        authority.predicate_state_rule.policy_fingerprint,
        authority.action_policy_fingerprint,
        *(item.temporal_policy_fingerprint for item in authority.temporal_constructions),
    }
    if authority.identity_construction is not None:
        values.add(authority.identity_construction.identity_policy_fingerprint)
    if authority.arbitration_policy_bundle is not None:
        values.update((
            authority.arbitration_policy_bundle.trust_policy.fingerprint,
            authority.arbitration_policy_bundle.temporal_policy.fingerprint,
        ))
    return tuple(sorted(values))


def retained_context(
    compilation: BootstrapNativeOperationCompilationV3,
    effect: BootstrapNativeAcceptedOperationEffectV3,
    projection: BootstrapNativeEvidenceProjectionV3,
    *,
    commit_values: PlanningCommitValues,
    authorizing_transaction_group_id: str,
    retained_records: Sequence[BaseModel],
) -> RetainedProvenanceContext:
    """Resolve one exact P/E/K/C retained-native provenance join."""
    authority = compilation.operation_input.planning_construction_authority
    if authority is None:
        raise ValueError("missing retained planning authority")
    if (
        authority.source_id != compilation.operation_input.source_id
        or authority.source_digest != compilation.operation_input.source_digest
        or authority.operation_execution_id != compilation.operation_execution_id
        or authority.operation_id != compilation.operation_id
        or projection.operation_execution_id != compilation.operation_execution_id
    ):
        raise ValueError("foreign retained operation authority")

    projections, records, effect_digests = _effect_authority(effect)
    if projection not in projections:
        raise ValueError("projection is absent from accepted effect")
    citation = projection.citation_record
    provenance = projection.provenance_record
    if (
        citation.operation_execution_id != compilation.operation_execution_id
        or provenance.operation_execution_id != compilation.operation_execution_id
        or citation.record_kind != "citation"
        or provenance.record_kind != "provenance"
        or _exact_payload_value(citation, "citation_id") != citation.record_id
        or _exact_payload_value(provenance, "provenance_id") != provenance.record_id
    ):
        raise ValueError("foreign or substituted paired evidence record")
    same_provenance = tuple(
        item for item in projections
        if item.provenance_record.record_id == provenance.record_id
    )
    if len(same_provenance) != 1:
        raise ValueError("nonunique retained provenance projection")

    constructions = tuple(
        item for item in authority.evidence_constructions
        if item.evidence_item_digest == projection.evidence_item_digest
    )
    if len(constructions) != 1:
        raise ValueError("nonunique retained evidence construction")
    construction = constructions[0]
    if (
        construction.citation_id != citation.record_id
        or construction.provenance_id != provenance.record_id
        or construction.source_span.source_id != authority.source_id
        or construction.source_authority != authority.source_authority_evidence.authority
    ):
        raise ValueError("substituted retained evidence pair")

    cited_record_id = _exact_payload_value(citation, "cited_record_id")
    targets = tuple(record for record in records if record.record_id == cited_record_id)
    if len(targets) != 1:
        raise ValueError("nonunique or missing cited native target")
    target = targets[0]
    if target.operation_execution_id != compilation.operation_execution_id:
        raise ValueError("foreign cited native target")
    # Reuse the canonical commit-time owner for P, its paired citation, and C.
    # A planning payload alone does not license a hand-written graph payload or
    # an invented digest; each result must match the retained graph inventory.
    materialized_citation = _retained_materialization(
        citation,
        commit_values=commit_values,
        authorizing_transaction_group_id=authorizing_transaction_group_id,
        retained_records=retained_records,
    )
    materialized_provenance = _retained_materialization(
        provenance,
        commit_values=commit_values,
        authorizing_transaction_group_id=authorizing_transaction_group_id,
        retained_records=retained_records,
    )
    materialized = _retained_materialization(
        target,
        commit_values=commit_values,
        authorizing_transaction_group_id=authorizing_transaction_group_id,
        retained_records=retained_records,
    )
    if (
        any(getattr(item, "operation_id", None) != compilation.operation_id for item in (
            materialized_citation,
            materialized_provenance,
            materialized,
        ))
        or getattr(materialized_provenance, "source_id", None) != authority.source_id
    ):
        raise ValueError("foreign retained graph materialization")

    ancestry = tuple(sorted({
        compilation.compilation_digest,
        authority.authority_digest,
        authority.source_authority_evidence.evidence_digest,
        authority.source_authority_evidence.provenance_digest,
        construction.evidence_digest,
        projection.projection_digest,
        *effect_digests,
    }))
    return RetainedProvenanceContext(
        target_kind=materialized.record_kind,
        target_id=graph_record_id(materialized),
        proof_ancestry_ids=ancestry,
        policy_fingerprints=_policy_context(compilation),
    )

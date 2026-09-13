"""Nonproduction feasibility of the proposed retained context recipes."""
from memorii.core.semantic_ingestion.contracts import (
    BootstrapNativeEvidenceProjectionV3,
    BootstrapNativeFactEffectV3,
    BootstrapNativeOperationCompilationV3,
)


def retained_context(
    compilation: BootstrapNativeOperationCompilationV3,
    effect: BootstrapNativeFactEffectV3,
    projection: BootstrapNativeEvidenceProjectionV3,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    authority = compilation.operation_input.planning_construction_authority
    if authority is None or projection not in effect.evidence_projections:
        raise ValueError("missing retained evidence authority")
    if projection.operation_execution_id != compilation.operation_execution_id:
        raise ValueError("foreign evidence operation")
    matches = tuple(item for item in authority.evidence_constructions
                    if item.evidence_item_digest == projection.evidence_item_digest)
    if len(matches) != 1:
        raise ValueError("nonunique evidence construction")
    construction = matches[0]
    if (construction.citation_id != projection.citation_record.record_id
            or construction.provenance_id != projection.provenance_record.record_id):
        raise ValueError("substituted evidence pair")
    ancestry = tuple(sorted({
        compilation.compilation_digest, authority.authority_digest,
        authority.source_authority_evidence.evidence_digest,
        authority.source_authority_evidence.provenance_digest,
        construction.evidence_digest, projection.projection_digest, effect.effect_digest,
    }))
    policies = {
        authority.predicate_registry_fingerprint, authority.predicate_state_rule.policy_fingerprint,
        authority.action_policy_fingerprint,
        *(item.temporal_policy_fingerprint for item in authority.temporal_constructions),
    }
    if authority.arbitration_policy_bundle is not None:
        policies.update((authority.arbitration_policy_bundle.trust_policy.fingerprint,
                         authority.arbitration_policy_bundle.temporal_policy.fingerprint))
    return ancestry, tuple(sorted(policies))

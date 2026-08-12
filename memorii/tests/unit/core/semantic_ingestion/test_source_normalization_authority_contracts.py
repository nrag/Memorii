"""Closed-wire proofs for the host source-normalization authority leaves."""

from __future__ import annotations

import pytest
from memorii.core.semantic_ingestion.contracts import (
    ParserConsensusPolicy,
    ScopeConsensusPolicy,
    TemporalAttachmentConsensusPolicy,
    contract_digest,
)
from memorii.core.semantic_ingestion.source_normalization_authority import (
    CapabilityRegistryEntry,
    CapabilityRegistrySnapshot,
    ConsensusPolicyAuthority,
    GraphDependentExecutionPolicy,
    ProposalRunProductionAuthority,
)


def _digest() -> str:
    return "a" * 64


def _proposal_values() -> dict[str, str]:
    return {
        "source_id": "source",
        "source_digest": _digest(),
        "preparation_fingerprint": _digest(),
        "route_set_digest": _digest(),
        "proposer_fingerprint": _digest(),
        "proposer_manifest_digest": _digest(),
        "prompt_registration_digest": _digest(),
        "semantic_request_fingerprint": _digest(),
        "action_proposal_catalog_fingerprint": _digest(),
        "retry_policy_fingerprint": _digest(),
    }


def test_proposal_run_authority_is_exact_closed_wire_and_every_leaf_is_hashed() -> None:
    values = _proposal_values()
    authority = ProposalRunProductionAuthority(
        **values,
        authority_digest=contract_digest(
            b"memorii.semantic-ingestion.proposal-run-production-authority.v1", values
        ),
    )

    assert tuple(ProposalRunProductionAuthority.model_fields) == (*values, "authority_digest")
    for name in values:
        mutated = {**values, name: "b" * 64 if name != "source_id" else "other"}
        with pytest.raises(ValueError, match="digest mismatch"):
            ProposalRunProductionAuthority(**mutated, authority_digest=authority.authority_digest)


def test_consensus_and_capability_authorities_reject_leaf_mutation_and_extra_values() -> None:
    parser = ParserConsensusPolicy.create()
    scope = ScopeConsensusPolicy.create()
    temporal = TemporalAttachmentConsensusPolicy.create()
    consensus_values = {
        "parser_policy": parser,
        "scope_policy": scope,
        "temporal_attachment_policy": temporal,
    }
    ConsensusPolicyAuthority(
        **consensus_values,
        authority_digest=contract_digest(b"memorii.semantic-ingestion.consensus-policy-authority.v1", consensus_values),
    )
    with pytest.raises(ValueError, match="digest mismatch"):
        ConsensusPolicyAuthority(**consensus_values, authority_digest="b" * 64)

    entry = CapabilityRegistryEntry(capability_id="local", capability_fingerprint=_digest())
    registry_values = {"registry_revision": "r1", "capabilities": (entry,)}
    registry = CapabilityRegistrySnapshot(
        **registry_values,
        snapshot_digest=contract_digest(b"memorii.semantic-ingestion.capability-registry-snapshot.v2", registry_values),
    )
    with pytest.raises(ValueError, match="digest mismatch"):
        CapabilityRegistrySnapshot(
            registry_revision="r2", capabilities=registry.capabilities, snapshot_digest=registry.snapshot_digest
        )
    with pytest.raises(ValueError):
        CapabilityRegistrySnapshot.model_validate({**registry.model_dump(), "unexpected": "value"})


def test_graph_execution_policy_hashes_each_declared_limit() -> None:
    values = {
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
        "replay_artifact_schema_registry_fingerprint": _digest(),
        "maximum_decode_depth": 1,
    }
    policy = GraphDependentExecutionPolicy(
        **values,
        policy_digest=contract_digest(b"memorii.semantic-ingestion.graph-dependent-execution-policy.v1", values),
    )
    for name in values:
        mutated = {**values, name: 2 if isinstance(values[name], int) else "b" * 64}
        with pytest.raises(ValueError):
            GraphDependentExecutionPolicy(**mutated, policy_digest=policy.policy_digest)

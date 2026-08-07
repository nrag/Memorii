from __future__ import annotations

from hashlib import sha256

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.semantic_ingestion.contracts import (
    GovernanceCarrierArtifact,
    GroupPlanningAuthorization,
    MessageAdmissionCarrierSet,
    MessageAdmissionIdentity,
    PlanningArtifactReference,
    RequiredOutcomeScopeSet,
    SegmentGovernanceBinding,
    SegmentGovernanceCarrierSet,
    SemanticContractCodecError,
    SourceTransactionPlanLineage,
    SourceTransactionPlanLineageReference,
    TransactionGroupPlanLineageEntry,
    TransactionSemanticGroupPlanReference,
    decode_semantic_contract,
    encode_semantic_contract,
)
from memorii.domain.enums import SourceModality
from pydantic import BaseModel


def _plan_reference() -> TransactionSemanticGroupPlanReference:
    return TransactionSemanticGroupPlanReference(
        plan_id="plan-1",
        plan_digest="a" * 64,
        repository_id="repo-1",
        repository_contract_fingerprint="b" * 64,
    )


def _entry() -> TransactionGroupPlanLineageEntry:
    authorization = GroupPlanningAuthorization.create(
        transaction_group_id="group-1",
        group_plan=_plan_reference(),
        planned_execution_digest="e" * 64,
        planning_artifact=PlanningArtifactReference(
            artifact_id="artifact-1",
            artifact_digest="f" * 64,
            repository_id="repo-1",
            repository_contract_fingerprint="b" * 64,
        ),
        independence_certificate_digests=("1" * 64, "2" * 64),
    )
    return TransactionGroupPlanLineageEntry.create(
        transaction_group_id="group-1",
        operation_ids=("operation-1", "operation-2"),
        attempt_id="attempt-1",
        authorizing_attempt_digest="c" * 64,
        authorizing_group_plan=_plan_reference(),
        planning_authorization_digest=authorization.authorization_digest,
        planning_authorization=authorization,
        supersedes_entry_digest=None,
    )


def _planning_artifact_reference() -> PlanningArtifactReference:
    return PlanningArtifactReference(
        artifact_id="artifact-1",
        artifact_digest="f" * 64,
        repository_id="repo-1",
        repository_contract_fingerprint="b" * 64,
    )


def _carrier_artifact() -> GovernanceCarrierArtifact:
    binding = SegmentGovernanceBinding.create(
        source_id="source-1", segment_id="segment-1", message_semantic_context_digest="1" * 64,
        effective_scope_digest="2" * 64, authority_digest="3" * 64, data_classification="internal",
        modality=SourceModality.ASSERTION, provider_egress_decision_digest="4" * 64,
        egress_disposition="allow_verbatim",
    )
    governance = SegmentGovernanceCarrierSet.create(source_id="source-1", bindings=(binding,))
    admissions = MessageAdmissionCarrierSet.create(source_id="source-1", identities=(
        MessageAdmissionIdentity.create(
            delivery_principal_binding_digest="5" * 64, authenticated_source_reference="source-ref-1",
            authenticated_source_reference_key_digest="6" * 64, message_bytes_digest="7" * 64,
            segment_governance_binding_digest=binding.binding_digest,
        ),
    ))
    scopes = RequiredOutcomeScopeSet.create(tenant_partition_id="tenant-1", scopes=(MemoryScope(user_id="user-1"),))
    return GovernanceCarrierArtifact.create(
        artifact_id="governance-1", atomic_generation=1, segment_governance=governance,
        message_admissions=admissions, required_outcome_scopes=scopes,
    )


def _entry_for_group(
    group_id: str,
    operation_ids: tuple[str, ...],
    *,
    attempt_id: str,
    plan_id: str,
    supersedes_entry_digest: str | None = None,
    repository_id: str = "repo-1",
    planning_authorization: GroupPlanningAuthorization | None = None,
) -> TransactionGroupPlanLineageEntry:
    plan = TransactionSemanticGroupPlanReference(
        plan_id=plan_id,
        plan_digest=sha256(plan_id.encode()).hexdigest(),
        repository_id=repository_id,
        repository_contract_fingerprint="b" * 64,
    )
    authorization = planning_authorization or GroupPlanningAuthorization.create(
        transaction_group_id=group_id,
        group_plan=plan,
        planned_execution_digest="e" * 64,
        planning_artifact=PlanningArtifactReference(
            artifact_id=f"artifact-{plan_id}",
            artifact_digest="f" * 64,
            repository_id=repository_id,
            repository_contract_fingerprint="b" * 64,
        ),
        independence_certificate_digests=("1" * 64,),
    )
    return TransactionGroupPlanLineageEntry.create(
        transaction_group_id=group_id,
        operation_ids=operation_ids,
        attempt_id=attempt_id,
        authorizing_attempt_digest="c" * 64,
        authorizing_group_plan=plan,
        planning_authorization_digest=authorization.authorization_digest,
        planning_authorization=authorization,
        supersedes_entry_digest=supersedes_entry_digest,
    )


def _lineage(
    entries: tuple[TransactionGroupPlanLineageEntry, ...], *, final_entry_digests: tuple[str, ...] | None = None
) -> SourceTransactionPlanLineage:
    ordered = tuple(sorted(entries, key=lambda entry: encode_typed_value(entry.model_dump(mode="python"))))
    successor_digests = {entry.supersedes_entry_digest for entry in ordered if entry.supersedes_entry_digest is not None}
    finals = tuple(entry.entry_digest for entry in ordered if entry.entry_digest not in successor_digests)
    artifact = _carrier_artifact()
    return SourceTransactionPlanLineage.create(
        lineage_id="lineage-1",
        repository_id="repo-1",
        source_id="source-1",
        source_digest="a" * 64,
        segment_governance_carriers=artifact.segment_governance,
        message_admission_carriers=artifact.message_admissions,
        governance_carrier_artifact=artifact,
        required_outcome_scopes=artifact.required_outcome_scopes,
        initial_group_plan=_plan_reference(),
        entries=ordered,
        final_entry_digests=finals if final_entry_digests is None else final_entry_digests,
    )


@pytest.mark.parametrize(
    ("value", "expected_type"),
    [
        (_entry(), TransactionGroupPlanLineageEntry),
        (
            GroupPlanningAuthorization.create(
                transaction_group_id="group-1",
                group_plan=_plan_reference(),
                planned_execution_digest="e" * 64,
                planning_artifact=_planning_artifact_reference(),
                independence_certificate_digests=("1" * 64, "2" * 64),
            ),
            GroupPlanningAuthorization,
        ),
        (
            SourceTransactionPlanLineageReference(
                lineage_id="lineage-1", lineage_digest="3" * 64, repository_id="repo-1"
            ),
            SourceTransactionPlanLineageReference,
        ),
    ],
)
def test_plan_lineage_contracts_round_trip_exactly(
    value: BaseModel, expected_type: type[BaseModel]
) -> None:
    encoded = encode_semantic_contract(value)
    assert decode_semantic_contract(encoded, expected_type) == value


def test_plan_lineage_codec_rejects_unknown_variant_and_coercible_tuple() -> None:
    encoded = encode_semantic_contract(_entry())
    envelope = decode_typed_value(encoded)
    assert isinstance(envelope, dict)

    unknown = {**envelope, "kind": "future_group_lineage"}
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(
            encode_typed_value(unknown), TransactionGroupPlanLineageEntry
        )

    payload = dict(envelope["payload"])
    payload["operation_ids"] = ["operation-1", "operation-2"]
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(
            encode_typed_value({**envelope, "payload": payload}),
            TransactionGroupPlanLineageEntry,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        {"operation_ids": ("operation-2", "operation-1")},
        {"operation_ids": ("operation-1", "operation-1")},
        {"entry_digest": "0" * 64},
    ],
)
def test_plan_lineage_entry_rejects_noncanonical_or_digest_mutation(
    mutation: dict[str, object],
) -> None:
    values = _entry().model_dump(mode="python")
    values.update(mutation)
    with pytest.raises(ValueError):
        TransactionGroupPlanLineageEntry.model_validate(values)


def test_group_planning_authorization_rejects_unsorted_certificates() -> None:
    authorization = GroupPlanningAuthorization.create(
        transaction_group_id="group-1",
        group_plan=_plan_reference(),
        planned_execution_digest="e" * 64,
        planning_artifact=_planning_artifact_reference(),
        independence_certificate_digests=("1" * 64, "2" * 64),
    )
    values = authorization.model_dump(mode="python")
    values["independence_certificate_digests"] = ("2" * 64, "1" * 64)
    with pytest.raises(ValueError):
        GroupPlanningAuthorization.model_validate(values)


def test_source_plan_lineage_keeps_unaffected_group_authorization_at_its_final_tail() -> None:
    group_a = _entry_for_group("group-a", ("operation-a",), attempt_id="attempt-a", plan_id="plan-a")
    group_b_original = _entry_for_group("group-b", ("operation-b",), attempt_id="attempt-b-1", plan_id="plan-b-1")
    group_b_replanned = _entry_for_group(
        "group-b", ("operation-b",), attempt_id="attempt-b-2", plan_id="plan-b-2",
        supersedes_entry_digest=group_b_original.entry_digest,
    )

    lineage = _lineage((group_a, group_b_original, group_b_replanned))

    assert lineage.final_entry_digests == tuple(
        entry.entry_digest for entry in lineage.entries if entry in {group_a, group_b_replanned}
    )
    final_by_digest = {entry.entry_digest: entry for entry in lineage.entries}
    assert final_by_digest[group_a.entry_digest].planning_authorization == group_a.planning_authorization
    assert decode_semantic_contract(encode_semantic_contract(lineage), SourceTransactionPlanLineage) == lineage


def test_source_plan_lineage_rejects_forks_orphans_cross_group_and_cross_repository_links() -> None:
    original = _entry_for_group("group-a", ("operation-a",), attempt_id="attempt-a-1", plan_id="plan-a-1")
    fork_one = _entry_for_group("group-a", ("operation-a",), attempt_id="attempt-a-2", plan_id="plan-a-2", supersedes_entry_digest=original.entry_digest)
    fork_two = _entry_for_group("group-a", ("operation-a",), attempt_id="attempt-a-3", plan_id="plan-a-3", supersedes_entry_digest=original.entry_digest)
    with pytest.raises(ValueError, match="cannot fork"):
        _lineage((original, fork_one, fork_two))

    orphan = _entry_for_group("group-a", ("operation-a",), attempt_id="attempt-a-2", plan_id="plan-a-2", supersedes_entry_digest="0" * 64)
    with pytest.raises(ValueError, match="unknown"):
        _lineage((original, orphan))

    other_group = _entry_for_group("group-b", ("operation-b",), attempt_id="attempt-b-1", plan_id="plan-b-1", supersedes_entry_digest=original.entry_digest)
    with pytest.raises(ValueError, match="cross-group"):
        _lineage((original, other_group))

    foreign = _entry_for_group("group-a", ("operation-a",), attempt_id="attempt-a-2", plan_id="plan-a-2", repository_id="repo-2")
    with pytest.raises(ValueError, match="repository mismatch"):
        _lineage((foreign,))


def test_source_plan_lineage_rejects_cycle_and_stale_final_tail() -> None:
    first = _entry_for_group("group-a", ("operation-a",), attempt_id="attempt-a-1", plan_id="plan-a-1")
    second = _entry_for_group("group-a", ("operation-a",), attempt_id="attempt-a-2", plan_id="plan-a-2", supersedes_entry_digest=first.entry_digest)
    # The cyclic coordinates cannot be produced through the entry factory; construct them only to isolate aggregate topology validation.
    cyclic_first = first.model_copy(update={"supersedes_entry_digest": second.entry_digest})
    baseline = _lineage((first, second))
    cyclic_lineage = baseline.model_construct(
        **(baseline.__dict__ | {"entries": (cyclic_first, second), "final_entry_digests": ()})
    )
    with pytest.raises(ValueError, match="cannot cycle"):
        cyclic_lineage.validate_lineage()

    with pytest.raises(ValueError, match="final entries"):
        _lineage((first, second), final_entry_digests=(first.entry_digest,))


def test_plan_lineage_entry_rejects_mismatched_planning_authorization() -> None:
    entry = _entry()
    values = entry.model_dump(mode="python")
    values["planning_authorization"] = GroupPlanningAuthorization.create(
        transaction_group_id="group-1", group_plan=TransactionSemanticGroupPlanReference(
            plan_id="other-plan", plan_digest="9" * 64, repository_id="repo-1", repository_contract_fingerprint="b" * 64,
        ), planned_execution_digest="e" * 64, planning_artifact=_planning_artifact_reference(),
        independence_certificate_digests=("1" * 64,),
    )
    with pytest.raises(ValueError, match="exactly authorize"):
        TransactionGroupPlanLineageEntry.model_validate(values)


@pytest.mark.parametrize("field", ["planning_authorization_digest", "planning_authorization"])
def test_plan_lineage_entry_rejects_absent_planning_authorization(field: str) -> None:
    entry = _entry()
    values = entry.model_dump(mode="python")
    values[field] = None
    with pytest.raises(ValueError, match=field):
        TransactionGroupPlanLineageEntry.model_validate(values)

    values["planning_authorization_digest"] = None
    values["planning_authorization"] = None
    values.pop("entry_digest")
    with pytest.raises(ValueError):
        TransactionGroupPlanLineageEntry.create(**values)


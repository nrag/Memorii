from datetime import UTC, datetime

import pytest
from memorii.core.consolidation.runtime_outputs import (
    ArchivePackage,
    ArchivePackageRef,
    ConsolidationOmission,
    ConsolidationOrigin,
    ConsolidationPayload,
    ConsolidationResult,
    ConsolidationSourceReference,
    EpisodicSummary,
    FollowUpItem,
    SemanticCandidate,
    SkillCandidate,
    UnresolvedFollowUpSummary,
    UserCandidate,
    build_consolidation_result,
    runtime_delivery_id,
)
from pydantic import TypeAdapter, ValidationError


def _origin() -> ConsolidationOrigin:
    return ConsolidationOrigin(
        installation_id="install",
        partition_id="partition",
        operation_generation="generation",
        task_id="task",
        client_namespace="client",
        operation_id="op",
        request_digest="1" * 64,
    )


def _archive(**changes: str) -> ArchivePackage:
    return ArchivePackage(reference=ArchivePackageRef(
        installation_id="install",
        partition_id="partition",
        task_id=changes.get("task_id", "task"),
        origin_revision=7,
        checkpoint_id="checkpoint",
        checkpoint_digest="a" * 64,
        manifest_id="manifest",
        manifest_digest="b" * 64,
    ))


def test_complete_output_family_round_trips_in_producer_order() -> None:
    ref = ConsolidationSourceReference(source_id="source", source_digest="2" * 64)
    result = build_consolidation_result(
        _origin(),
        origin_revision=7,
        outputs=(
            _archive(),
            SemanticCandidate(abstraction="validated observation", source_refs=(ref,)),
            EpisodicSummary(summary="first summary", source_refs=(ref,)),
            UserCandidate(preference="retained preference", source_refs=(ref,), valid_from=datetime(2026, 1, 1, tzinfo=UTC)),
            UnresolvedFollowUpSummary(items=(FollowUpItem(node_id="node", reason="awaiting evidence"),)),
            SkillCandidate(title="Skill", summary="Validated steps", steps=("check", "confirm")),
            EpisodicSummary(summary="second summary"),
        ),
        omissions=(ConsolidationOmission(kind="user_candidate", reason="insufficient_evidence"),),
    )
    assert [output.payload.kind for output in result.outputs] == [
        "episodic_summary", "episodic_summary", "skill_candidate", "semantic_candidate",
        "user_candidate", "unresolved_follow_up_summary", "archive_package",
    ]
    assert [output.ordinal for output in result.outputs] == [0, 1, 0, 0, 0, 0, 0]
    assert len({output.output_id for output in result.outputs}) == len(result.outputs)
    restored = ConsolidationResult.model_validate_json(result.model_dump_json())
    assert restored.canonical_bytes() == result.canonical_bytes()
    assert restored == result


def test_identity_vectors_bind_origin_kind_ordinal_and_target() -> None:
    origin = _origin()
    result = build_consolidation_result(
        origin, origin_revision=7, outputs=(EpisodicSummary(summary="Done."), EpisodicSummary(summary="Second.")),
    )
    assert result.result_id == "69b33130e6cbb42a7f59211c46ab4d963fae4c32e0af786e5c6cae3c26e23b11"
    first, second = result.outputs
    assert first.output_id == "59d0191c44aebe006b979b2a3563aeb3a6dd71c6b956dee6ffacfa6cc80a6d52"
    assert second.output_id == "2f1bf2bb2187eae1167a88d284aded70f24f9fced37aaf1d80c7d96bac38643a"
    assert first.payload_digest == "d3a54deabea967559db2912e24cd88a79a520949e36ed25291309e4d7e74341a"
    assert (
        runtime_delivery_id("partition", "writeback_candidate", first.output_id)
        == "8eac747902985c8554385d3d922b85899fa421f5edd84f94ea82166056e1f186"
    )
    assert (
        runtime_delivery_id("partition", "work_projection", origin)
        == "c8839e75a50ae8a6060862736f626b5cd0b51be23192aa0c0cf8544e96f3a8da"
    )
    with pytest.raises(ValueError, match="target partition"):
        runtime_delivery_id("foreign", "work_projection", origin)

    changed = build_consolidation_result(
        origin.model_copy(update={"operation_generation": "generation-next"}),
        origin_revision=7,
        outputs=(EpisodicSummary(summary="Done."),),
    )
    assert changed.result_id != result.result_id
    assert changed.outputs[0].output_id != first.output_id
    divergent = build_consolidation_result(origin, origin_revision=7, outputs=(EpisodicSummary(summary="Changed."),))
    assert divergent.outputs[0].output_id == first.output_id
    assert divergent.outputs[0].payload_digest != first.payload_digest


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "unregistered", "summary": "text"},
        {"kind": "episodic_summary", "summary": "text", "status": "committed"},
        {"kind": "semantic_candidate", "abstraction": "text", "provenance": "user"},
        {"kind": "semantic_candidate", "abstraction": "text", "is_validated": True},
        {"kind": "skill_candidate", "title": "x", "summary": "y", "steps": ["z"], "target_domain": "semantic"},
        {"kind": "user_candidate", "preference": "text", "valid_from": "2026-01-01T00:00:00"},
    ],
)
def test_payload_rejects_unowned_discriminators_fields_and_authority(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(ConsolidationPayload).validate_python(fields)


def test_retained_result_rejects_modified_payload_and_foreign_archive() -> None:
    result = build_consolidation_result(_origin(), origin_revision=7, outputs=(EpisodicSummary(summary="Done."),))
    original = result.outputs[0]
    modified = original.model_copy(update={"payload": EpisodicSummary(summary="Altered.")})
    with pytest.raises(ValidationError, match="payload digest"):
        ConsolidationResult.model_validate(result.model_copy(update={"outputs": (modified,)}))
    with pytest.raises(ValidationError, match="archive reference"):
        build_consolidation_result(_origin(), origin_revision=7, outputs=(_archive(task_id="other"),))


def test_limits_are_measured_in_utf8_bytes_and_total_reference_count() -> None:
    EpisodicSummary(summary="é" * 2048)
    with pytest.raises(ValidationError, match="4 KiB"):
        EpisodicSummary(summary="é" * 2049)
    with pytest.raises(ValidationError):
        SkillCandidate(title="x", summary="y", steps=("z",) * 33)

    refs = tuple(ConsolidationSourceReference(source_id=f"source-{i}", source_digest="3" * 64) for i in range(65))
    with pytest.raises(ValidationError, match="64"):
        EpisodicSummary(summary="x", source_refs=refs)
    with pytest.raises(ValidationError, match="unique"):
        EpisodicSummary(summary="x", source_refs=(refs[0], refs[0]))
    items = (
        FollowUpItem(node_id="node-a", reason="reason", source_refs=refs[:64]),
        FollowUpItem(node_id="node-b", reason="reason", source_refs=refs[64:]),
    )
    with pytest.raises(ValidationError, match="64 source"):
        UnresolvedFollowUpSummary(items=items)
    with pytest.raises(ValueError, match="32 outputs"):
        build_consolidation_result(_origin(), origin_revision=7, outputs=(EpisodicSummary(summary="x"),) * 33)

"""Focused graph-free identity derivation proof."""

from memorii.core.semantic_ingestion.contracts import (
    SourceLocalIdentityAssertion,
    SourceLocalIdentityPartitionEvidence,
    SourcePrePartitionMention,
)
from memorii.core.semantic_ingestion.source_alignment import resolve_source_local_identity
from tests.unit.core.semantic_ingestion.clean_room_request_test_support import (
    build_clean_room_semantic_proposal_request,
)


def _mention(*, label: str):
    request = build_clean_room_semantic_proposal_request()
    return SourcePrePartitionMention(
        schema_version=2,
        source_id=request.source_id,
        source_digest=request.source_digest,
        segment_id=request.segment_id,
        segment_language_route_digest=request.language_route.route_digest,
        language_policy_fingerprint="1" * 64,
        mention_span=request.owned_text,
        mention_digest=label * 64,
    )


def test_identity_component_propagates_unresolved_hyperedge() -> None:
    request = build_clean_room_semantic_proposal_request()
    first, second, third = (_mention(label=value) for value in ("a", "b", "c"))
    alias = SourceLocalIdentityAssertion.create(
        segment_id=request.segment_id,
        segment_language_route_digest=request.language_route.route_digest,
        language_policy_fingerprint="1" * 64,
        mention_digests=("a" * 64, "b" * 64),
        proof_kind="explicit_alias",
        source_evidence=(request.owned_text,),
    )
    uncertain = SourceLocalIdentityAssertion.create(
        segment_id=request.segment_id,
        segment_language_route_digest=request.language_route.route_digest,
        language_policy_fingerprint="1" * 64,
        mention_digests=("b" * 64, "c" * 64),
        proof_kind="insufficient_evidence",
        source_evidence=(request.owned_text,),
    )
    evidence = SourceLocalIdentityPartitionEvidence.create(
        source_id=request.source_id,
        source_digest=request.source_digest,
        mentions=tuple(sorted((first, second, third), key=lambda item: item.mention_digest)),
        assertions=tuple(sorted((alias, uncertain), key=lambda item: item.assertion_digest)),
    )

    resolution = resolve_source_local_identity(evidence)

    assert resolution.grounded_mention_refs == ("a" * 64, "b" * 64, "c" * 64)
    assert len(resolution.clusters) == 1
    assert resolution.clusters[0].decision == "unresolved"
    assert resolution.clusters[0].proof_kind == "insufficient_evidence"


def test_identity_unasserted_mention_is_singleton() -> None:
    request = build_clean_room_semantic_proposal_request()
    mention = _mention(label="d")
    evidence = SourceLocalIdentityPartitionEvidence.create(
        source_id=request.source_id,
        source_digest=request.source_digest,
        mentions=(mention,),
        assertions=(),
    )

    resolution = resolve_source_local_identity(evidence)

    assert resolution.clusters[0].decision == "singleton_distinct"

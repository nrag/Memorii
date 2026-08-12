"""Fixed closure vectors for the source-normalization atomic request."""

from __future__ import annotations

from hashlib import sha256

import pytest
from memorii.core.memory_evolution.atomic_store import AtomicGenerationMember, generation_request_digest
from memorii.core.semantic_ingestion.contracts import SourceNormalizationAtomicWriteRequest
from pydantic import BaseModel


class _Policy(BaseModel):
    pass


_CATEGORIES = (
    "progress", "source_normalization_request", "graph_free_interpretation_bundle",
    "source_local_identity_partition_evidence", "parser_consensus", "semantic_scope_consensus",
    "temporal_attachment_consensus", "source_local_identity_resolution", "source_proposal_alignment",
    "source_dependency_groups", "source_normalization_result", "source_normalization_evidence_manifest",
    "graph_dependent_execution_policy", "consensus_policy_selection_bundle",
    "language_construction_policy_bundle",
)


def _member(kind: str, index: int) -> AtomicGenerationMember:
    payload = f"{kind}:{index}".encode()
    return AtomicGenerationMember(
        member_id=f"{index:02d}-{kind}", kind=kind, canonical_payload=payload,
        payload_digest=sha256(payload).hexdigest(),
    )


def _request(*, parser_rows: int = 1, scope_rows: int = 1, temporal_rows: int = 1):
    members = []
    index = 0
    for category in _CATEGORIES:
        count = {"parser_consensus": parser_rows, "semantic_scope_consensus": scope_rows,
                 "temporal_attachment_consensus": temporal_rows}.get(category, 1)
        for _ in range(count):
            members.append(_member(category, index))
            index += 1
    request = SourceNormalizationAtomicWriteRequest.model_construct(
        schema_version=2, kind="source_normalization_checkpoint", progress_state="preplanning",
        publication_generation=1, members=tuple(members),
        required_artifact_digests=tuple(member.payload_digest for member in members),
        source_normalization_request=type("Request", (), {"request_digest": "1" * 64})(),
        source_normalization_request_digest="1" * 64,
        source_normalization_result=type("Result", (), {"result_digest": "2" * 64})(),
        source_normalization_result_digest="2" * 64,
        evidence_manifest=type("Manifest", (), {"manifest_digest": "3" * 64})(),
        evidence_manifest_digest="3" * 64,
        graph_dependent_execution_policy=_Policy(), graph_dependent_execution_policy_digest="4" * 64,
        consensus_policy_selection_bundle=type("Selections", (), {"bundle_digest": "5" * 64})(),
        consensus_policy_selection_bundle_digest="5" * 64,
        language_construction_policy_bundle=type("Policies", (), {"bundle_digest": "6" * 64})(),
        language_construction_policy_bundle_digest="6" * 64,
        request_digest="0" * 64,
    )
    return request.model_copy(update={"request_digest": generation_request_digest(request)})


@pytest.mark.parametrize(("parser_rows", "scope_rows", "temporal_rows", "expected"), ((1, 1, 1, 15), (3, 3, 3, 21), (1, 1, 2, 16)))
def test_atomic_category_vectors_have_exact_variable_run_counts(parser_rows: int, scope_rows: int, temporal_rows: int, expected: int) -> None:
    request = _request(parser_rows=parser_rows, scope_rows=scope_rows, temporal_rows=temporal_rows)
    assert len(request.members) == expected
    assert request.validate_source_normalization_closure() == request


@pytest.mark.parametrize("mutation", ("omit", "extra", "reorder", "duplicate", "manifest"))
def test_atomic_category_mutations_reject_before_publication(mutation: str) -> None:
    request = _request()
    members = list(request.members)
    if mutation == "omit":
        members.pop(0)
    elif mutation == "extra":
        members.append(_member("progress", 99))
    elif mutation == "reorder":
        members[0], members[1] = members[1], members[0]
    elif mutation == "duplicate":
        members[1] = members[0]
    else:
        request = request.model_copy(update={"evidence_manifest_digest": "f" * 64})
    request = request.model_copy(update={"members": tuple(members), "required_artifact_digests": tuple(member.payload_digest for member in members)})
    request = request.model_copy(update={"request_digest": generation_request_digest(request)})
    with pytest.raises(ValueError):
        request.validate_source_normalization_closure()


def test_atomic_member_registry_includes_bootstrap_graph_normalization_authority_kind() -> None:
    payload = b"bootstrap-graph-normalization-authority"
    member = AtomicGenerationMember(
        member_id="00-bootstrap-graph-normalization-authority",
        kind="bootstrap_graph_normalization_authority",
        canonical_payload=payload,
        payload_digest=sha256(payload).hexdigest(),
    )

    assert member.kind == "bootstrap_graph_normalization_authority"

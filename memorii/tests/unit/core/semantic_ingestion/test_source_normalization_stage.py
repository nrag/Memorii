"""Fail-closed input gating for the graph-free normalization stage."""

from types import SimpleNamespace

import pytest
from memorii.core.semantic_ingestion.source_normalization_stage import (
    GraphFreeSourceNormalizationInputs,
    GraphFreeSourceNormalizationStage,
)

_DIGEST = "a" * 64


def _selection(kind: str, role: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        kind=kind,
        operation_id=_DIGEST,
        proposal_id="proposal",
        segment_id="segment",
        segment_language_route_digest=_DIGEST,
        temporal_role=role,
    )


def _selection_bundle(kind: str, roles: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(
        selections=(
            _selection("parser", None),
            _selection("scope", None),
            *(_selection("temporal_attachment", role) for role in roles),
        )
    )


def _inputs(*, kind: str) -> GraphFreeSourceNormalizationInputs:
    digest = _DIGEST
    fence = object()
    source = SimpleNamespace(
        source_id="source", source_digest=digest, preparation_fingerprint=digest
    )
    bundle = SimpleNamespace(
        source_id="source",
        source_digest=digest,
        preparation_fingerprint=digest,
        proposal_run_fingerprint=digest,
        analysis_bundle_fingerprint=digest,
        temporal_resolution_fingerprint=digest,
        subject_sets=(
            SimpleNamespace(
                subjects=(
                    SimpleNamespace(
                        kind=kind,
                        operation_id=digest,
                        proposal_id="proposal",
                        segment_id="segment",
                        segment_language_route_digest=digest,
                    ),
                )
            ),
        ),
    )
    lease = SimpleNamespace(operation_fence_binding=fence)
    return GraphFreeSourceNormalizationInputs(
        source=source,
        proposal_run=SimpleNamespace(
            status="complete", source_id="source", source_digest=digest,
            preparation_fingerprint=digest, run_fingerprint=digest,
        ),
        analyses=SimpleNamespace(status="complete", bundle_fingerprint=digest),
        interpretation_bundle=bundle,
        predicate_events=SimpleNamespace(status="complete"),
        temporal_resolution=SimpleNamespace(status="complete", resolver_fingerprint=digest),
        consensus_policy_selections=_selection_bundle(
            kind,
            {"fact": ("assertion",), "correction": ("replacement", "transition")}[kind],
        ),
        language_construction_policies=SimpleNamespace(),
        publication_coordinate=SimpleNamespace(
            operation_fence_binding=fence, expected_current_artifact_generation=1
        ),
        temporal_policy=SimpleNamespace(), trust_policy=SimpleNamespace(),
        arbitration_as_of=object(), capability_registry=SimpleNamespace(),
        parser_consensus=(SimpleNamespace(assessment_digest=digest),),
        evidence_entries=(), capability_selections=(),
        graph_dependent_execution_policy=SimpleNamespace(policy_digest=digest),
        graph_dependent_execution_policy_digest=digest,
        progress=SimpleNamespace(operation_lease_binding=lease),
        operation_fence_binding=fence, operation_lease_binding=lease,
        writer_commit_binding=SimpleNamespace(), expected_operation_generation=1,
        expected_artifact_generation=1,
    )


def test_correction_requires_and_accepts_replacement_and_transition_selections() -> None:
    GraphFreeSourceNormalizationStage._validate_inputs(_inputs(kind="correction"))


@pytest.mark.parametrize(
    ("roles", "description"),
    (
        (("replacement",), "missing"),
        (("replacement", "replacement"), "duplicate"),
        (("transition", "replacement"), "swapped"),
        (("replacement", "unknown"), "unknown"),
    ),
)
def test_correction_rejects_non_role_complete_selection_closures(
    roles: tuple[str, ...], description: str
) -> None:
    inputs = _inputs(kind="correction")
    malformed = GraphFreeSourceNormalizationInputs(
        **{
            **inputs.__dict__,
            "consensus_policy_selections": _selection_bundle("correction", roles),
        }
    )
    with pytest.raises(ValueError, match="role-complete"):
        GraphFreeSourceNormalizationStage._validate_inputs(malformed)


def test_missing_parser_consensus_stops_before_alignment_or_publication() -> None:
    inputs = _inputs(kind="fact")
    with pytest.raises(ValueError, match="parser consensus"):
        GraphFreeSourceNormalizationStage._validate_inputs(
            GraphFreeSourceNormalizationInputs(
                **{**inputs.__dict__, "parser_consensus": ()}
            )
        )

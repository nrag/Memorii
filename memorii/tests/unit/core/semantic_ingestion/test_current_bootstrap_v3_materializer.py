from hashlib import sha256

import pytest
from memorii.core.semantic_ingestion.current_bootstrap_v3_authority import (
    VerifiedBootstrapV3ResourcePolicy,
)
from memorii.core.semantic_ingestion.current_bootstrap_v3_lanes import (
    CurrentBootstrapV3InstalledLanes,
)
from memorii.core.semantic_ingestion.current_bootstrap_v3_materializer import (
    CurrentBootstrapV3MaterializationError,
    CurrentBootstrapV3RequestMaterializer,
)
from memorii.core.semantic_ingestion.project_assertions_profile import (
    load_project_assertions_bundle,
)
from tests.fixtures.semantic_ingestion.source_normalization_fixture_builder import (
    build_bootstrap_freeform_prepared_source,
)


def _source():
    text = "Mars Venus 001 project owner is Ada."
    return build_bootstrap_freeform_prepared_source(
        source_id="source:current-v3",
        source_digest=sha256(text.encode("utf-8")).hexdigest(),
        source_text=text,
    )


def _materializer() -> CurrentBootstrapV3RequestMaterializer:
    policy = VerifiedBootstrapV3ResourcePolicy.from_bundle(load_project_assertions_bundle())
    return CurrentBootstrapV3RequestMaterializer(resource_policy=policy)


def test_materializes_closed_current_v3_request_and_lanes() -> None:
    material = _materializer().materialize(source=_source())

    request = material.runtime_authority.proposal_requests[0]
    assert tuple(item.predicate_id for item in request.predicate_catalog.predicates) == (
        "project_deadline", "project_owner", "project_status",
    )
    assert material.linguistic_request(request, "stanza").analyzer_manifest == material.stanza_manifest
    assert material.linguistic_request(request, "spacy").analyzer_manifest == material.spacy_manifest
    assert material.predicate_request(request).predicate_event_manifest == material.predicate_manifest
    assert material.temporal_request(request).resolver_manifest == material.temporal_manifest


def test_rejects_source_without_current_bootstrap_freeform_routes() -> None:
    source = _source()
    route = source.segment_language_routes.routes[0]
    source = source.model_copy(
        update={
            "segment_language_routes": source.segment_language_routes.model_copy(
                update={"routes": ()}
            )
        }
    )

    with pytest.raises(CurrentBootstrapV3MaterializationError, match="freeform route"):
        _materializer().materialize(source=source)

    assert route.segment_id


def test_installed_lanes_bind_generated_manifests_and_reject_substitution() -> None:
    policy = VerifiedBootstrapV3ResourcePolicy.from_bundle(load_project_assertions_bundle())
    material = CurrentBootstrapV3RequestMaterializer(resource_policy=policy).materialize(source=_source())
    lanes = CurrentBootstrapV3InstalledLanes(resource_policy=policy)
    request = material.runtime_authority.proposal_requests[0]
    stanza_request = material.linguistic_request(request, "stanza")

    analysis = lanes.stanza(stanza_request)

    assert analysis.analyzer_manifest_digest == lanes.stanza_manifest.manifest_digest
    with pytest.raises(ValueError, match="substituted"):
        lanes.stanza(stanza_request.model_copy(update={"analyzer_manifest": lanes.spacy_manifest}))

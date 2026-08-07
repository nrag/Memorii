"""Closed parent/child topology vectors for real prepared sources."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from itertools import product
from typing import Any

import pytest
from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value, encode_typed_value
from memorii.core.memory_evolution.models import ExtractionTriggerMode, MemoryScope
from memorii.core.semantic_ingestion.contracts import (
    GovernanceCarrierArtifact,
    LanguageCandidate,
    MessageAdmissionCarrierSet,
    MessageAdmissionIdentity,
    PreparedSegment,
    PreparedSource,
    ProjectionTextSpan,
    RequiredOutcomeScopeSet,
    RetainedSourceTextArtifact,
    RetainedSourceTextSpan,
    SegmentGovernanceBinding,
    SegmentGovernanceCarrierSet,
    SegmentLanguageResourceBinding,
    SegmentLanguageRoute,
    SegmentLanguageRouteSet,
    SegmentLocalTextArtifact,
    SegmentLocalTextSpan,
    SemanticContractCodecError,
    SemanticProjectionSegment,
    SemanticProjectionTextArtifact,
    SourceSemanticContext,
    SourceSemanticTextProjection,
    TextPreparationPolicy,
    VerbatimTextArtifactMappingProof,
    canonical_contract_value,
    contract_digest,
    decode_semantic_contract,
    encode_semantic_contract,
)
from memorii.domain.enums import SourceModality

_POLICY_DOMAIN = b"memorii.semantic-ingestion.text-preparation-policy.v1\0"
_PREPARED_DOMAIN = b"memorii.semantic-ingestion.prepared-source.v1\0"
_SOURCE = "prepared-source-vector"


def _hex(label: str) -> str:
    return sha256(label.encode("ascii")).hexdigest()


def _tree(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="python")
    if isinstance(value, Enum):
        value = value.value
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, bytes):
        import base64
        return {"$type": "bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, datetime):
        utc = value.astimezone(UTC)
        return {"$type": "datetime", "value": utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond:06d}Z"}
    if isinstance(value, int):
        return {"$type": "integer", "value": str(value)}
    if isinstance(value, frozenset):
        return {"$type": "frozenset", "items": sorted((_tree(item) for item in value), key=lambda item: json.dumps(item, ensure_ascii=True, separators=(",", ":")))}
    if isinstance(value, (tuple, list)):
        return {"$type": "tuple", "items": [_tree(item) for item in value]}
    if isinstance(value, dict):
        return {"$type": "map", "entries": [[key, _tree(value[key])] for key in sorted(value)]}
    raise TypeError(type(value).__name__)


def _ctv(value: Any) -> bytes:
    return json.dumps(_tree(value), ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _policy(limit: int = 128) -> TextPreparationPolicy:
    return TextPreparationPolicy.create(max_segment_characters=limit, supported_languages=("en", "es"), segmentation_algorithm="memorii.semantic-ingestion.safe-sentence-first-paragraph-bounded.v1", context_window_algorithm="memorii.semantic-ingestion.owned-partition-whole-boundary-context.v1")


def _parent_artifacts(parent: str, text: str):
    digest = sha256(text.encode()).hexdigest()
    retained = RetainedSourceTextArtifact.create(artifact_id=f"retained-{parent}", content_digest=digest, unicode_scalar_length=len(text))
    projection = SemanticProjectionTextArtifact.create(artifact_id=f"projection-{parent}", content_digest=digest, unicode_scalar_length=len(text))
    local = SegmentLocalTextArtifact.create(artifact_id=f"local-{parent}", content_digest=digest, unicode_scalar_length=len(text), projection_segment_id=parent)
    retained_span = RetainedSourceTextSpan.create(artifact=retained, start=0, end=len(text), substring_digest=digest)
    projection_span = ProjectionTextSpan.create(artifact=projection, start=0, end=len(text), substring_digest=digest)
    local_span = SegmentLocalTextSpan.create(artifact=local, start=0, end=len(text), substring_digest=digest)
    proof = VerbatimTextArtifactMappingProof.create(retained_span=retained_span, projection_span=projection_span, segment_span=local_span)
    return retained, projection, local, retained_span, projection_span, local_span, proof


def _prepared(
    parent_text: dict[str, str] | None = None,
    child_windows: dict[str, tuple[tuple[str, int, int], ...]] | None = None,
) -> PreparedSource:
    parent_text = parent_text or {"P0": "Alpha. Beta.", "P1": "Gamma."}
    source_digest = sha256("\n".join(parent_text.values()).encode("utf-8")).hexdigest()
    bindings = tuple(SegmentGovernanceBinding.create(source_id=_SOURCE, segment_id=parent, message_semantic_context_digest=_hex(f"context {parent}"), effective_scope_digest=_hex(f"scope {parent}"), authority_digest=_hex(f"authority {parent}"), data_classification="internal", modality=SourceModality.ASSERTION, provider_egress_decision_digest=_hex(f"egress {parent}"), egress_disposition="allow_verbatim") for parent in parent_text)
    carriers = SegmentGovernanceCarrierSet.create(source_id=_SOURCE, bindings=tuple(sorted(bindings, key=lambda item: encode_typed_value(canonical_contract_value(item)))))
    admissions = None
    for salts in product(range(16), repeat=len(carriers.bindings)):
        admission_values = tuple(MessageAdmissionIdentity.create(delivery_principal_binding_digest=_hex(f"principal {binding.segment_id} {salt}"), authenticated_source_reference=f"reference-{salt:02d}-{binding.segment_id}", authenticated_source_reference_key_digest=_hex(f"key {binding.segment_id} {salt}"), message_bytes_digest=_hex(f"message {binding.segment_id}"), segment_governance_binding_digest=binding.binding_digest) for binding, salt in zip(carriers.bindings, salts, strict=True))
        ordered = tuple(sorted(admission_values, key=lambda item: encode_typed_value(canonical_contract_value(item))))
        if tuple(item.segment_governance_binding_digest for item in ordered) == tuple(item.binding_digest for item in carriers.bindings):
            admissions = MessageAdmissionCarrierSet.create(source_id=_SOURCE, identities=ordered)
            break
    assert admissions is not None
    scopes = RequiredOutcomeScopeSet.create(tenant_partition_id="tenant-vector", scopes=(MemoryScope(user_id="user-vector"),))
    artifact = GovernanceCarrierArtifact.create(artifact_id="prepared-governance", atomic_generation=1, segment_governance=carriers, message_admissions=admissions, required_outcome_scopes=scopes)
    resource = SegmentLanguageResourceBinding.create(selected_language="en", proposal_capability_fingerprint=_hex("capability"), stanza_analyzer_manifest_digest=_hex("stanza"), spacy_analyzer_manifest_digest=_hex("spacy"), predicate_event_manifest_digest=_hex("predicate"), temporal_resolver_manifest_digest=_hex("temporal"))
    parent_parts = {parent: _parent_artifacts(parent, text) for parent, text in parent_text.items()}
    ordered_parents = tuple(binding.segment_id for binding in carriers.bindings)
    semantic_text = "\n".join(parent_text[parent] for parent in ordered_parents)
    aggregate = SemanticProjectionTextArtifact.create(artifact_id="projection-all", content_digest=sha256(semantic_text.encode()).hexdigest(), unicode_scalar_length=len(semantic_text))
    projection_segments = []
    parent_projection_spans = {}
    parent_proofs = {}
    offset = 0
    for binding in carriers.bindings:
        parent = binding.segment_id
        retained, _projection, local, _rspan, _pspan, _lspan, _proof = parent_parts[parent]
        admission = next(item for item in admissions.identities if item.segment_governance_binding_digest == binding.binding_digest)
        pspan = ProjectionTextSpan.create(artifact=aggregate, start=offset, end=offset + len(parent_text[parent]), substring_digest=sha256(parent_text[parent].encode()).hexdigest())
        parent_projection_spans[parent] = pspan
        proof = VerbatimTextArtifactMappingProof.create(
            retained_span=_rspan, projection_span=pspan, segment_span=_lspan
        )
        parent_proofs[parent] = proof
        projection_segments.append(SemanticProjectionSegment.create(segment_id=parent, projection_span=pspan, segment_text_artifact=local, text_mapping_proof=proof, semantic_text=parent_text[parent], source_variant="verbatim_text", source_reference=f"source-{parent}", message_semantic_context_digest=binding.message_semantic_context_digest, segment_governance=binding, message_admission_identity=admission))
        offset = pspan.end + 1
    projection = SourceSemanticTextProjection(schema_version=1, retained_source_digest=source_digest, retained_text_artifact=parent_parts["P0"][0], required_outcome_scopes=scopes, projection_text_artifact=aggregate, projection_text=semantic_text, separator="\n", segments=tuple(projection_segments), segment_governance_carriers=carriers, message_admission_carriers=admissions, envelope_manifest_digest=None, projection_digest=aggregate.artifact_digest)
    child_windows = child_windows or {"P0": (("C0", 0, 7), ("C1", 7, 12)), "P1": (("C2", 0, 6),)}
    children = tuple(
        (child, parent, start, end)
        for parent in ordered_parents
        for child, start, end in child_windows[parent]
    )
    prepared = []
    routes = []
    for child, parent, start, end in children:
        retained, _project_artifact, local, _rspan, _pspan, _lspan, _proof = parent_parts[parent]
        proof = parent_proofs[parent]
        content = sha256(parent_text[parent][start:end].encode()).hexdigest()
        parent_projection = parent_projection_spans[parent]
        owned_projection = ProjectionTextSpan.create(artifact=aggregate, start=parent_projection.start + start, end=parent_projection.start + end, substring_digest=content)
        owned_local = SegmentLocalTextSpan.create(artifact=local, start=start, end=end, substring_digest=content)
        binding = next(item for item in carriers.bindings if item.segment_id == parent)
        admission = next(item for item in admissions.identities if item.segment_governance_binding_digest == binding.binding_digest)
        route = SegmentLanguageRoute.create(source_id=_SOURCE, source_digest=source_digest, segment_id=child, parent_projection_segment_id=parent, segment_text_artifact_id=local.artifact_id, segment_text_artifact_digest=local.artifact_digest, segment_text_content_digest=local.content_digest, declared_language="en", candidates=(LanguageCandidate(language="en", probability_ppm=1_000_000, model_fingerprint=_hex("router-model")),), code_switch_spans=(), selected_language="en", decision="selected", minimum_probability_ppm=1, minimum_margin_ppm=1, routing_policy_fingerprint=_hex("routing"), router_manifest_fingerprint=_hex("router"), resource_binding=resource)
        routes.append(route)
        prepared.append(PreparedSegment(segment_id=child, parent_projection_segment_id=parent, owned_projection_span=owned_projection, context_projection_span=parent_projection, owned_segment_span=owned_local, context_segment_span=_lspan, text_mapping_proof=proof, segment_governance=binding, message_admission_identity=admission, language_route=route, code_switch_spans=(), boundary_flags=frozenset()))
    context = SourceSemanticContext.create(source_id=_SOURCE, source_digest=source_digest, trigger_mode=ExtractionTriggerMode.IMMEDIATE, provenance_digest=_hex("provenance"), temporal_references=(), received_at=datetime(2026, 8, 5, tzinfo=UTC), retained_at=datetime(2026, 8, 5, tzinfo=UTC), source_effective_interval_evidence=None, provider_egress_policy_fingerprint=_hex("egress policy"), governance_policy_fingerprint=_hex("governance policy"), trust_policy_fingerprint=_hex("trust policy"))
    policy = _policy()
    body = dict(source_id=_SOURCE, semantic_text=semantic_text, semantic_text_projection=projection, source_digest=source_digest, semantic_context=context, segment_language_routes=SegmentLanguageRouteSet.create(source_id=_SOURCE, source_digest=source_digest, routes=tuple(routes)), segment_governance_carriers=carriers, message_admission_carriers=admissions, governance_carrier_artifact=artifact, sentence_spans=(), segments=tuple(prepared), token_spans=(), preparation_policy=policy, status="complete", diagnostics=())
    return PreparedSource(**body, preparation_fingerprint=contract_digest(b"memorii.semantic-ingestion.prepared-source.v1", body))


def _rebuild(source: PreparedSource, **changes: Any) -> PreparedSource:
    body = {name: getattr(source, name) for name in PreparedSource.model_fields if name != "preparation_fingerprint"} | changes
    return PreparedSource(**body, preparation_fingerprint=contract_digest(b"memorii.semantic-ingestion.prepared-source.v1", body))


def test_real_prepared_source_closes_two_parents_and_three_children() -> None:
    source = _prepared()
    assert tuple(item.parent_projection_segment_id for item in source.segments) == tuple(
        parent.segment_id for parent in source.semantic_text_projection.segments for _child in (
            ("C0", "C1") if parent.segment_id == "P0" else ("C2",)
        )
    )
    assert sha256(_POLICY_DOMAIN + _ctv(source.preparation_policy.model_dump(mode="python", exclude={"policy_fingerprint"}))).hexdigest() == source.preparation_policy.policy_fingerprint
    body = {name: getattr(source, name) for name in PreparedSource.model_fields if name != "preparation_fingerprint"}
    assert sha256(_PREPARED_DOMAIN + _ctv(body)).hexdigest() == source.preparation_fingerprint


@pytest.mark.parametrize("mutation", ("missing_child", "duplicate_child", "orphan_parent", "duplicate_parent", "route_order", "cross_parent", "sibling_window"))
def test_prepared_source_rejects_parent_child_closure_mutations(mutation: str) -> None:
    source = _prepared()
    body = {name: getattr(source, name) for name in PreparedSource.model_fields if name != "preparation_fingerprint"}
    if mutation == "missing_child":
        body["segments"] = tuple(body["segments"][:-1])
        body["segment_language_routes"] = SegmentLanguageRouteSet.create(source_id=_SOURCE, source_digest=source.source_digest, routes=tuple(body["segment_language_routes"].routes[:-1]))
    elif mutation == "duplicate_child":
        with pytest.raises(ValueError, match="unique"):
            SegmentLanguageRouteSet.create(source_id=_SOURCE, source_digest=source.source_digest, routes=(*body["segment_language_routes"].routes, body["segment_language_routes"].routes[0]))
        return
    elif mutation == "orphan_parent":
        bindings = tuple(item for item in source.segment_governance_carriers.bindings if item.segment_id != "P1")
        body["segment_governance_carriers"] = SegmentGovernanceCarrierSet.create(source_id=_SOURCE, bindings=bindings)
    elif mutation == "duplicate_parent":
        with pytest.raises(ValueError, match="unique"):
            SegmentLanguageRouteSet.create(source_id=_SOURCE, source_digest=source.source_digest, routes=(*body["segment_language_routes"].routes, body["segment_language_routes"].routes[0]))
        return
    elif mutation == "route_order":
        routes = body["segment_language_routes"].routes
        body["segment_language_routes"] = SegmentLanguageRouteSet.create(source_id=_SOURCE, source_digest=source.source_digest, routes=(routes[1], routes[0], routes[2]))
    elif mutation == "cross_parent":
        segment = body["segments"][2]
        body["segments"] = (*body["segments"][:2], segment.model_copy(update={"segment_governance": body["segments"][0].segment_governance}))
    else:
        first, second, *rest = body["segments"]
        body["segments"] = (first.model_copy(update={"owned_projection_span": second.owned_projection_span, "owned_segment_span": second.owned_segment_span}), second.model_copy(update={"owned_projection_span": first.owned_projection_span, "owned_segment_span": first.owned_segment_span}), *rest)
    with pytest.raises(ValueError):
        _rebuild(source, **body)


def test_prepared_source_allows_proof_bound_sentence_context_subwindow_and_rejects_mapping_mutations() -> None:
    source = _prepared()
    parent = next(item for item in source.semantic_text_projection.segments if item.segment_id == "P0")
    child_index = next(index for index, item in enumerate(source.segments) if item.segment_id == "C0")
    child = source.segments[child_index]
    context_text = parent.semantic_text[:7]
    context_projection = ProjectionTextSpan.create(
        artifact=parent.projection_span.artifact,
        start=parent.projection_span.start,
        end=parent.projection_span.start + len(context_text),
        substring_digest=sha256(context_text.encode()).hexdigest(),
    )
    context_segment = SegmentLocalTextSpan.create(
        artifact=parent.segment_text_artifact,
        start=0,
        end=len(context_text),
        substring_digest=sha256(context_text.encode()).hexdigest(),
    )
    narrowed = child.model_copy(update={
        "context_projection_span": context_projection,
        "context_segment_span": context_segment,
    })
    segments = (*source.segments[:child_index], narrowed, *source.segments[child_index + 1:])
    accepted = _rebuild(source, segments=segments)
    assert accepted.segments[child_index].context_projection_span != parent.projection_span

    foreign_proof = next(item.text_mapping_proof for item in source.semantic_text_projection.segments if item.segment_id == "P1")
    with pytest.raises(ValueError, match="partition exact parent projection coordinates"):
        _rebuild(source, segments=(*source.segments[:child_index], narrowed.model_copy(update={"text_mapping_proof": foreign_proof}), *source.segments[child_index + 1:]))
    shifted_projection = ProjectionTextSpan.create(
        artifact=parent.projection_span.artifact,
        start=parent.projection_span.start + 1,
        end=parent.projection_span.start + 7,
        substring_digest=sha256(parent.semantic_text[1:7].encode()).hexdigest(),
    )
    with pytest.raises(ValueError, match="owned and context spans must preserve coordinates"):
        _rebuild(source, segments=(*source.segments[:child_index], narrowed.model_copy(update={"context_projection_span": shifted_projection}), *source.segments[child_index + 1:]))


def test_stale_policy_bytes_and_no_output_policy_change_are_not_authority_equivalent() -> None:
    source = _prepared()
    stale = source.preparation_policy.model_copy(update={"max_segment_characters": 129})
    with pytest.raises(ValueError, match="policy_fingerprint mismatch"):
        _rebuild(source, preparation_policy=stale)
    changed = _policy(129)
    assert changed.policy_fingerprint != source.preparation_policy.policy_fingerprint
    assert _ctv(changed.model_dump(mode="python", exclude={"policy_fingerprint"})) != _ctv(source.preparation_policy.model_dump(mode="python", exclude={"policy_fingerprint"}))


def test_unicode_scalar_parent_child_vector_preserves_exact_offsets_and_rejects_swaps() -> None:
    parent_text = {"P0": "e\u0301🙂e\u0301🙂", "P1": "🙂e\u0301🙂"}
    source = _prepared(
        parent_text,
        {"P0": (("C0", 0, 3), ("C1", 3, 6)), "P1": (("C2", 0, 4),)},
    )
    expected_text = "\n".join(parent_text[parent.segment_id] for parent in source.semantic_text_projection.segments)
    assert source.semantic_text == expected_text
    assert len(source.semantic_text) == 11
    children = {child.segment_id: child for child in source.segments}
    c0, c1, c2 = children["C0"], children["C1"], children["C2"]
    assert source.semantic_text[c0.owned_projection_span.start:c0.owned_projection_span.end] == "e\u0301🙂"
    assert source.semantic_text[c1.owned_projection_span.start:c1.owned_projection_span.end] == "e\u0301🙂"
    assert source.semantic_text[c2.owned_projection_span.start:c2.owned_projection_span.end] == "🙂e\u0301🙂"
    assert sha256(_PREPARED_DOMAIN + _ctv({name: getattr(source, name) for name in PreparedSource.model_fields if name != "preparation_fingerprint"})).hexdigest() == source.preparation_fingerprint
    p0_start = next(parent.projection_span.start for parent in source.semantic_text_projection.segments if parent.segment_id == "P0")
    p1_start = next(parent.projection_span.start for parent in source.semantic_text_projection.segments if parent.segment_id == "P1")
    assert (c0.owned_projection_span.start, c0.owned_projection_span.end) == (p0_start, p0_start + 3)
    assert (c1.owned_projection_span.start, c1.owned_projection_span.end) == (p0_start + 3, p0_start + 6)
    assert (c2.owned_projection_span.start, c2.owned_projection_span.end) == (p1_start, p1_start + 4)
    assert c0.text_mapping_proof.projection_span.start == p0_start
    assert c1.text_mapping_proof.projection_span.start == p0_start
    with pytest.raises(ValueError):
        _rebuild(source, segments=(
            c0.model_copy(update={"owned_projection_span": c1.owned_projection_span, "owned_segment_span": c1.owned_segment_span}),
            c1.model_copy(update={"owned_projection_span": c0.owned_projection_span, "owned_segment_span": c0.owned_segment_span}),
            c2,
        ))
    shortened = "e\u0301"
    shortened_digest = sha256(shortened.encode("utf-8")).hexdigest()
    shortened_projection = ProjectionTextSpan.create(
        artifact=c0.owned_projection_span.artifact, start=p0_start, end=p0_start + 2, substring_digest=shortened_digest
    )
    shortened_local = SegmentLocalTextSpan.create(
        artifact=c0.owned_segment_span.artifact, start=0, end=2, substring_digest=shortened_digest
    )
    with pytest.raises(ValueError):
        _rebuild(source, segments=(
            c0.model_copy(update={"owned_projection_span": shortened_projection, "owned_segment_span": shortened_local}),
            c1,
            c2,
        ))


def test_prepared_source_direct_strict_codec_matrix() -> None:
    source = _prepared()
    encoded = encode_semantic_contract(source)
    envelope = decode_typed_value(encoded)
    assert isinstance(envelope, dict)
    assert decode_semantic_contract(encoded, PreparedSource) == source
    for field in PreparedSource.model_fields:
        mutated = dict(envelope)
        payload = dict(envelope["payload"])
        payload.pop(field)
        mutated["payload"] = payload
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value(mutated), PreparedSource)
    for mutation in ("extra", "alias", "foreign_schema", "legacy_kind"):
        mutated = dict(envelope)
        if mutation == "extra":
            mutated["unexpected"] = True
        elif mutation == "alias":
            payload = dict(envelope["payload"])
            payload["source"] = payload.pop("source_id")
            mutated["payload"] = payload
        elif mutation == "foreign_schema":
            mutated["schema"] = "foreign.schema.v1"
        else:
            mutated["kind"] = "prepared_source_v0"
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value(mutated), PreparedSource)
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(encoded, TextPreparationPolicy)
    with pytest.raises(SemanticContractCodecError):
        encode_semantic_contract(source.model_copy(update={"preparation_fingerprint": "f" * 64}))

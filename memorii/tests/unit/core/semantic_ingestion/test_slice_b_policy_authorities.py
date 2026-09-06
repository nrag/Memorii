"""Focused strict-wire proof for Slice B policy authorities."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.semantic_analysis.policies import (
    ConstructionFamily,
    PredicateSemanticPolicy,
    QuotationBoundaryPolicy,
    SemanticScopePolicy,
    UdPathPattern,
    UdPathStep,
    UdRoleSchema,
)
from memorii.core.semantic_ingestion.contracts import (
    ActionStateOperationSemanticPolicyKey,
    ConsensusPolicySelection,
    CorrectionOperationSemanticPolicyKey,
    FactOperationSemanticPolicyKey,
    IdentityOperationSemanticPolicyKey,
    LanguageConstructionPolicyAuthorityBundle,
    ParserConsensusPolicy,
    ParserOperationPolicyAuthority,
    PredicateSemanticPolicyBinding,
    RetractionOperationSemanticPolicyKey,
    ScopeConsensusPolicy,
    ScopeOperationPolicyAuthority,
    SemanticContractCodecError,
    TemporalAttachmentConsensusPolicy,
    decode_semantic_contract,
    encode_semantic_contract,
)
from pydantic import ValidationError


def _hex(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _clean_ctv(value: object) -> bytes:
    """Tiny independent CTV writer for hand-authored Slice B vectors."""
    def wire(item: object) -> object:
        if item is None or isinstance(item, (bool, str)):
            return item
        if isinstance(item, int):
            return {"$type": "integer", "value": str(item)}
        if isinstance(item, bytes):
            return {"$type": "bytes", "value": base64.b64encode(item).decode("ascii")}
        if hasattr(item, "items") and not isinstance(item, dict):
            return {"$type": "map", "entries": [[key, wire(value)] for key, value in item.items()]}
        if isinstance(item, tuple):
            return {"$type": "tuple", "items": [wire(child) for child in item]}
        if isinstance(item, frozenset):
            items = [wire(child) for child in item]
            return {"$type": "frozenset", "items": sorted(items, key=emit)}
        if isinstance(item, Mapping):
            return {"$type": "map", "entries": [[key, wire(item[key])] for key in sorted(item)]}
        raise TypeError(f"unhandled CTV value: {type(item).__name__}")

    def emit(item: object) -> bytes:
        return json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")

    return emit(wire(value))


def _clean_digest(domain: str, body: dict[str, object]) -> str:
    return sha256(domain.encode("ascii") + b"\0" + _clean_ctv(body)).hexdigest()


class _TestMap(dict[str, object]):
    def __hash__(self) -> int:
        return hash(_clean_ctv(dict(self)))


def _payload(value: object) -> object:
    """Independently lower Pydantic test values into the CTV data algebra."""
    if hasattr(value, "model_dump"):
        return _TestMap({name: _payload(getattr(value, name)) for name in type(value).model_fields})
    if isinstance(value, tuple):
        return tuple(_payload(item) for item in value)
    if isinstance(value, frozenset):
        return frozenset(_payload(item) for item in value)
    if isinstance(value, dict):
        return _TestMap({key: _payload(item) for key, item in value.items()})
    return value


def _digest_payload(value: object) -> object:
    """Mirror only the documented canonical policy preimage normalization."""
    if isinstance(value, frozenset):
        return frozenset(_TestMap(_digest_payload(item)) if isinstance(_digest_payload(item), dict) else _digest_payload(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_digest_payload(item) for item in value)
    if isinstance(value, dict):
        return {key: _digest_payload(item) for key, item in value.items()}
    return value


def _leaves():
    family = ConstructionFamily.create(family_id="declarative")
    path = UdPathPattern.create(anchor="predicate_head", steps=(UdPathStep(direction="up", dependency_label="ccomp", ordinal=0),))
    quote = QuotationBoundaryPolicy.create(mode="outside_quoted_content")
    role = UdRoleSchema.create(
        role_id="agent", anchor_form="verbal", allowed_dependency_paths=(path,), required_function_word_lemmas=frozenset(),
        forbidden_clause_crossings=frozenset(), coordination_support="allowed", voice_normalization="active_only",
        canonical_graph_role="agent", required_polarity_evidence="not_required", required_commitment_evidence=frozenset(),
    )
    scope = SemanticScopePolicy.create(
        language="en", construction_family=family, predicate_family="declarative",
        allowed_predicate_ancestor_paths=(path,), negation_bearer_patterns=(), embedding_head_lemmas={},
        reporting_head_lemmas=frozenset(), question_mood_features=frozenset(), quotation_boundary_policy=quote,
        temporal_attachment_patterns=(), forbidden_clause_crossings=frozenset(),
    )
    predicate = PredicateSemanticPolicy.create(
        predicate_id="works_for", language="en", predicate_lemmas=frozenset({"work"}), nominal_lemmas=frozenset(),
        role_schemas=(role,), verbalizer_id=None, supported_commitments=frozenset({"asserted"}),
        supported_constructions=frozenset({family}),
    )
    return family, path, quote, role, scope, predicate


def _fixed_leaf_vectors() -> tuple[tuple[object, str, str, bytes], ...]:
    """Hand-authored wire vectors: no production digest, creator, or encoder oracle."""
    family = {"family_id": "declarative", "family_digest": "f0d79742a746f8177f3b61140e4f449783155b832d65cbc3edb731c21c59b791"}
    step = {"direction": "up", "dependency_label": "ccomp", "ordinal": 0}
    path = {"anchor": "predicate_head", "steps": (step,), "pattern_digest": "aaf2a555b51c416750e541cfe7c4ca1759e18a7baa45605449ed454a4be4dade"}
    quote = {"mode": "outside_quoted_content", "policy_digest": "6310de1783f75b3529330f4b9082d0627693a255a443772a235dc04251f88dc3"}
    role = {
        "role_id": "agent", "anchor_form": "verbal", "allowed_dependency_paths": (path,),
        "required_function_word_lemmas": frozenset(), "forbidden_clause_crossings": frozenset(),
        "coordination_support": "allowed", "voice_normalization": "active_only", "canonical_graph_role": "agent",
        "required_polarity_evidence": "not_required", "required_commitment_evidence": frozenset(),
        "schema_digest": "838b2e6b1fa09383269d444326b116fac5ff469ce34b453ca5e06b40ebe190de",
    }
    scope = {
        "language": "en", "construction_family": family, "predicate_family": "declarative",
        "allowed_predicate_ancestor_paths": (path,), "negation_bearer_patterns": (), "embedding_head_lemmas": {},
        "reporting_head_lemmas": frozenset(), "question_mood_features": frozenset(),
        "quotation_boundary_policy": quote, "temporal_attachment_patterns": (), "forbidden_clause_crossings": frozenset(),
        "policy_fingerprint": "4c10967564cf3d5278f4bc2a5b9b927656e0b2d8700cbe4dd14788eabd6ec086",
    }
    predicate = {
        "predicate_id": "works_for", "language": "en", "predicate_lemmas": frozenset({"work"}),
        "nominal_lemmas": frozenset(), "role_schemas": (role,), "verbalizer_id": None,
        "supported_commitments": frozenset({"asserted"}), "supported_constructions": frozenset({_TestMap(family)}),
        "policy_fingerprint": "d4ed514454b6fa5153ea0f89b403b99ffc19b0ba331eb2d742b1e596b84d64dc",
    }
    values = (
        (ConstructionFamily, family, "memorii.semantic-ingestion.construction-family.v1", "family_digest", "construction_family"),
        (UdPathPattern, path, "memorii.semantic-ingestion.ud-path-pattern.v1", "pattern_digest", "ud_path_pattern"),
        (QuotationBoundaryPolicy, quote, "memorii.semantic-ingestion.quotation-boundary-policy.v1", "policy_digest", "quotation_boundary_policy"),
        (SemanticScopePolicy, scope, "memorii.semantic-ingestion.semantic-scope-policy.v1", "policy_fingerprint", "semantic_scope_policy"),
        (UdRoleSchema, role, "memorii.semantic-ingestion.ud-role-schema.v1", "schema_digest", "ud_role_schema"),
        (PredicateSemanticPolicy, predicate, "memorii.semantic-ingestion.predicate-semantic-policy.v1", "policy_fingerprint", "predicate_semantic_policy"),
    )
    return tuple(
        (cls.model_validate(body), domain, digest_field, _clean_ctv({
            "schema": "memorii.semantic-ingestion.contract-envelope.v1", "kind": kind, "payload": body,
        }))
        for cls, body, domain, digest_field, kind in values
    )


def _selection(
    kind: str, operation: str, *, temporal_role: str | None = None
) -> ConsensusPolicySelection:
    rules = {
        "parser": ParserConsensusPolicy.create(),
        "scope": ScopeConsensusPolicy.create(),
        "temporal_attachment": TemporalAttachmentConsensusPolicy.create(),
    }
    rule = rules[kind]
    return ConsensusPolicySelection.create(
        schema_version=2, kind=kind, operation_id=_hex(operation), proposal_id="proposal", segment_id="segment",
        segment_language_route_digest=_hex("route"),
        temporal_role=temporal_role,
        request_dependency_kind="temporal_resolution" if kind == "temporal_attachment" else "analyses",
        request_dependency_fingerprint=_hex(f"dependency-{kind}"),
        selected_policy_fingerprint=rule.policy_fingerprint, selected_policy=rule,
    )


def _key_values() -> tuple[object, ...]:
    return (
        FactOperationSemanticPolicyKey(kind="fact", predicate_id="predicate"),
        CorrectionOperationSemanticPolicyKey(kind="correction", corrected_predicate_id="old", replacement_predicate_id="new"),
        RetractionOperationSemanticPolicyKey(kind="retraction", retracted_predicate_id="predicate"),
        ActionStateOperationSemanticPolicyKey(kind="action_state", logical_action_digest=_hex("logical"), action_state_digest=_hex("state"), state_id="open", role_ids=("agent", "object")),
        IdentityOperationSemanticPolicyKey(kind="identity", identity_operation_digest=_hex("identity"), operation="alias", predecessor_mention_digests=(_hex("before"),), successor_mention_digests=(_hex("after"),), reference_assignment_digests=(_hex("assignment"),)),
    )




def _codec_values() -> tuple[object, ...]:
    family, path, quote, role, scope, predicate = _leaves()
    fact_key = FactOperationSemanticPolicyKey(kind="fact", predicate_id=predicate.predicate_id)
    binding = PredicateSemanticPolicyBinding.create(role="fact", predicate_id=predicate.predicate_id, policy=predicate)
    parser = ParserOperationPolicyAuthority.create(
        operation_id=_hex("operation"), proposal_id="proposal", segment_id="segment",
        segment_language_route_digest=_hex("route"), parser_consensus_policy_fingerprint=ParserConsensusPolicy.create().policy_fingerprint,
        semantic_policy_key=fact_key, predicate_policy_bindings=(binding,), construction_families=(family,), role_schemas=(role,),
    )
    scope_authority = ScopeOperationPolicyAuthority.create(
        operation_id=_hex("operation"), proposal_id="proposal", segment_id="segment",
        segment_language_route_digest=_hex("route"), scope_consensus_policy_fingerprint=ScopeConsensusPolicy.create().policy_fingerprint,
        temporal_attachment_consensus_policy_fingerprint=TemporalAttachmentConsensusPolicy.create().policy_fingerprint,
        semantic_policy_key=fact_key, scope_policy=scope,
    )
    selections = tuple(
        _selection(
            kind,
            f"selection-{kind}",
            temporal_role="assertion" if kind == "temporal_attachment" else None,
        )
        for kind in ("parser", "scope", "temporal_attachment")
    )
    return (
        family, UdPathStep(direction="up", dependency_label="nsubj", ordinal=None), path, quote, scope, role, predicate,
        ParserConsensusPolicy.create(), ScopeConsensusPolicy.create(), TemporalAttachmentConsensusPolicy.create(),
        *selections, *(_key_values()), binding,
        parser, scope_authority, LanguageConstructionPolicyAuthorityBundle.create(policies=(parser, scope_authority)),
    )


@pytest.mark.parametrize(
    "value",
    (
        *_leaves(),
        *(
            value
            for value in _codec_values()
            if isinstance(
                value,
                (
                    PredicateSemanticPolicyBinding,
                    ParserOperationPolicyAuthority,
                    ScopeOperationPolicyAuthority,
                    LanguageConstructionPolicyAuthorityBundle,
                ),
            )
        ),
    ),
    ids=lambda value: type(value).__name__,
)
def test_slice_b_policy_family_python_dumps_round_trip_through_validation_and_ctv(value: object) -> None:
    dumped = value.model_dump(mode="python")
    assert type(value).model_validate(dumped) == value
    assert encode_typed_value(dumped)
    assert encode_semantic_contract(type(value).model_validate(dumped)) == encode_semantic_contract(value)


def test_policy_leaves_are_closed_content_addressed_codec_values() -> None:
    for value in _leaves():
        raw = encode_semantic_contract(value)
        assert decode_semantic_contract(raw, type(value)) == value
        envelope = decode_typed_value(raw)
        assert isinstance(envelope, dict) and isinstance(envelope["payload"], dict)
        envelope["payload"]["extra"] = True
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value(envelope), type(value))


def test_scope_and_predicate_policy_fixed_vector_canonicalizes_two_maps_and_two_families() -> None:
    """A two-by-two vector exercises canonical nested-model frozenset members."""
    quoted = QuotationBoundaryPolicy.create(mode="outside_quoted_content")
    direct = ConstructionFamily.create(family_id="direct")
    reported = ConstructionFamily.create(family_id="reported")
    role = UdRoleSchema.create(
        role_id="subject",
        anchor_form="verbal",
        allowed_dependency_paths=(),
        required_function_word_lemmas=frozenset(),
        forbidden_clause_crossings=frozenset(),
        coordination_support="allowed",
        voice_normalization="active_only",
        canonical_graph_role="subject",
        required_polarity_evidence="not_required",
        required_commitment_evidence=frozenset(),
    )
    first_scope = SemanticScopePolicy.create(
        language="en",
        construction_family=direct,
        predicate_family="assertion",
        allowed_predicate_ancestor_paths=(),
        negation_bearer_patterns=(),
        embedding_head_lemmas={"say": "reported", "believe": "believed"},
        reporting_head_lemmas=frozenset({"say", "report"}),
        question_mood_features=frozenset({"interrogative", "question"}),
        quotation_boundary_policy=quoted,
        temporal_attachment_patterns=(),
        forbidden_clause_crossings=frozenset({"ccomp", "parataxis"}),
    )
    second_scope = SemanticScopePolicy.create(
        language="en",
        construction_family=direct,
        predicate_family="assertion",
        allowed_predicate_ancestor_paths=(),
        negation_bearer_patterns=(),
        embedding_head_lemmas={"believe": "believed", "say": "reported"},
        reporting_head_lemmas=frozenset({"report", "say"}),
        question_mood_features=frozenset({"question", "interrogative"}),
        quotation_boundary_policy=quoted,
        temporal_attachment_patterns=(),
        forbidden_clause_crossings=frozenset({"parataxis", "ccomp"}),
    )
    first_policy = PredicateSemanticPolicy.create(
        predicate_id="state",
        language="en",
        predicate_lemmas=frozenset({"state", "say"}),
        nominal_lemmas=frozenset({"statement", "report"}),
        role_schemas=(role,),
        verbalizer_id=None,
        supported_commitments=frozenset({"asserted", "reported"}),
        supported_constructions=frozenset({direct, reported}),
    )
    second_policy = PredicateSemanticPolicy.create(
        predicate_id="state",
        language="en",
        predicate_lemmas=frozenset({"say", "state"}),
        nominal_lemmas=frozenset({"report", "statement"}),
        role_schemas=(role,),
        verbalizer_id=None,
        supported_commitments=frozenset({"reported", "asserted"}),
        supported_constructions=frozenset({reported, direct}),
    )

    # The former frozenset branch encoded raw BaseModel members and rejected
    # this supported policy shape before a fingerprint could be derived.
    with pytest.raises(CanonicalTypedValueError):
        encode_typed_value(direct)
    assert first_scope.policy_fingerprint == second_scope.policy_fingerprint
    assert first_policy.policy_fingerprint == second_policy.policy_fingerprint
    assert first_scope.policy_fingerprint == "4b55214e389b7f357e6306f743bd738bca89aab37a1ec961aa05104252dbe629"
    assert first_policy.policy_fingerprint == "620d41ca16e3b464bd1e411cb306e17c419b5656fe95a30094cb61c4c8427df1"






def test_operation_policy_authorities_bind_exact_policy_material() -> None:
    family, _, _, role, scope_policy, predicate_policy = _leaves()
    key = FactOperationSemanticPolicyKey(kind="fact", predicate_id=predicate_policy.predicate_id)
    binding = PredicateSemanticPolicyBinding.create(role="fact", predicate_id=predicate_policy.predicate_id, policy=predicate_policy)
    parser = ParserOperationPolicyAuthority.create(
        kind="parser_operation", operation_id=_hex("parser-operation"), proposal_id="proposal", segment_id="segment",
        segment_language_route_digest=_hex("route"), parser_consensus_policy_fingerprint=ParserConsensusPolicy.create().policy_fingerprint,
        semantic_policy_key=key, predicate_policy_bindings=(binding,), construction_families=(family,), role_schemas=(role,),
    )
    scope = ScopeOperationPolicyAuthority.create(
        kind="scope_operation", operation_id=_hex("parser-operation"), proposal_id="proposal", segment_id="segment",
        segment_language_route_digest=_hex("route"), scope_consensus_policy_fingerprint=ScopeConsensusPolicy.create().policy_fingerprint,
        temporal_attachment_consensus_policy_fingerprint=TemporalAttachmentConsensusPolicy.create().policy_fingerprint,
        semantic_policy_key=key, scope_policy=scope_policy,
    )
    bundle = LanguageConstructionPolicyAuthorityBundle.create(policies=(parser, scope))
    assert decode_semantic_contract(encode_semantic_contract(bundle), LanguageConstructionPolicyAuthorityBundle) == bundle
    with pytest.raises(ValidationError, match="exactly match"):
        ParserOperationPolicyAuthority.create(
            kind="parser_operation", operation_id=_hex("bad-parser"), proposal_id="proposal", segment_id="segment",
            segment_language_route_digest=_hex("route"), parser_consensus_policy_fingerprint=ParserConsensusPolicy.create().policy_fingerprint,
            semantic_policy_key=key, predicate_policy_bindings=(), construction_families=(family,), role_schemas=(role,),
        )


def test_slice_b_keys_and_rules_are_direct_closed_codecs() -> None:
    keys = (
        FactOperationSemanticPolicyKey(kind="fact", predicate_id="predicate"),
        CorrectionOperationSemanticPolicyKey(kind="correction", corrected_predicate_id="old", replacement_predicate_id="new"),
        RetractionOperationSemanticPolicyKey(kind="retraction", retracted_predicate_id="predicate"),
        ActionStateOperationSemanticPolicyKey(kind="action_state", logical_action_digest=_hex("logical"), action_state_digest=_hex("state"), state_id="open", role_ids=("agent", "object")),
        IdentityOperationSemanticPolicyKey(kind="identity", identity_operation_digest=_hex("identity"), operation="alias", predecessor_mention_digests=(_hex("before"),), successor_mention_digests=(_hex("after"),), reference_assignment_digests=(_hex("assignment"),)),
    )
    values = (*keys, ParserConsensusPolicy.create(), ScopeConsensusPolicy.create(), TemporalAttachmentConsensusPolicy.create())
    for value in values:
        assert decode_semantic_contract(encode_semantic_contract(value), type(value)) == value


def test_hand_authored_ctv_vectors_cover_leaf_rule_and_selection_digests() -> None:
    # These literals deliberately do not use a production create/encoder/digest helper.
    family_body = {"family_id": "declarative"}
    family_digest = _clean_digest("memorii.semantic-ingestion.construction-family.v1", family_body)
    family = ConstructionFamily.model_validate({**family_body, "family_digest": family_digest})
    assert family.family_digest == family_digest
    assert encode_semantic_contract(family) == _clean_ctv({
        "schema": "memorii.semantic-ingestion.contract-envelope.v1", "kind": "construction_family", "payload": {**family_body, "family_digest": family_digest},
    })
    quote_body = {"mode": "outside_quoted_content"}
    quote_digest = _clean_digest("memorii.semantic-ingestion.quotation-boundary-policy.v1", quote_body)
    quote = QuotationBoundaryPolicy.model_validate({**quote_body, "policy_digest": quote_digest})
    assert quote.policy_digest == quote_digest
    for cls, kind, domain, algorithm, dependency in (
        (ParserConsensusPolicy, "parser", "memorii.semantic-ingestion.parser-consensus-rule.v1", "memorii.semantic-ingestion.parser-consensus.exact-two-analyzer.v1", "analyses"),
        (ScopeConsensusPolicy, "scope", "memorii.semantic-ingestion.scope-consensus-rule.v1", "memorii.semantic-ingestion.scope-consensus.exact-two-analyzer.v1", "analyses"),
        (TemporalAttachmentConsensusPolicy, "temporal_attachment", "memorii.semantic-ingestion.temporal-attachment-consensus-rule.v1", "memorii.semantic-ingestion.temporal-attachment-consensus.exact-two-analyzer.v1", "temporal_resolution"),
    ):
        body = {"kind": kind, "algorithm": algorithm, "required_independent_analyzers": 2}
        fingerprint = _clean_digest(domain, body)
        rule = cls.model_validate({**body, "policy_fingerprint": fingerprint})
        assert encode_semantic_contract(rule) == _clean_ctv({
            "schema": "memorii.semantic-ingestion.contract-envelope.v1", "kind": f"{kind}_consensus_policy" if kind != "temporal_attachment" else "temporal_attachment_consensus_policy", "payload": {**body, "policy_fingerprint": fingerprint},
        })
        temporal_role = "assertion" if kind == "temporal_attachment" else None
        selection_body = {
            "schema_version": 2, "kind": kind, "operation_id": _hex(f"operation-{kind}"), "proposal_id": "proposal", "segment_id": "segment",
            "segment_language_route_digest": _hex("route"), "request_dependency_kind": dependency,
            "temporal_role": temporal_role,
            "request_dependency_fingerprint": _hex(dependency), "selected_policy_fingerprint": fingerprint,
            "selected_policy": {**body, "policy_fingerprint": fingerprint},
        }
        selection_digest = _clean_digest("memorii.semantic-ingestion.consensus-policy-selection.v2", selection_body)
        selection = ConsensusPolicySelection.model_validate({**selection_body, "selection_digest": selection_digest})
        assert selection.selection_digest == selection_digest


def test_revalidation_rejects_forged_models_and_nullable_ordinal_is_required() -> None:
    with pytest.raises(ValidationError):
        UdPathStep(direction="up", dependency_label="nsubj")
    step = UdPathStep(direction="up", dependency_label="nsubj", ordinal=None)
    assert decode_semantic_contract(encode_semantic_contract(step), UdPathStep) == step
    forged = ParserConsensusPolicy.create().model_copy(update={"required_independent_analyzers": 3})
    with pytest.raises(SemanticContractCodecError, match="validation failed"):
        encode_semantic_contract(forged)
    family, path, quote, _, _, _ = _leaves()
    first = SemanticScopePolicy.create(
        language="en", construction_family=family, predicate_family="declarative", allowed_predicate_ancestor_paths=(path,),
        negation_bearer_patterns=(), embedding_head_lemmas={"say": "reported", "believe": "believed"}, reporting_head_lemmas=frozenset(),
        question_mood_features=frozenset(), quotation_boundary_policy=quote, temporal_attachment_patterns=(), forbidden_clause_crossings=frozenset(),
    )
    second = SemanticScopePolicy.create(
        language="en", construction_family=family, predicate_family="declarative", allowed_predicate_ancestor_paths=(path,),
        negation_bearer_patterns=(), embedding_head_lemmas={"believe": "believed", "say": "reported"}, reporting_head_lemmas=frozenset(),
        question_mood_features=frozenset(), quotation_boundary_policy=quote, temporal_attachment_patterns=(), forbidden_clause_crossings=frozenset(),
    )
    assert first.policy_fingerprint == second.policy_fingerprint


def test_clean_room_leaf_vectors_pin_every_policy_byte_and_digest() -> None:
    """The expected wire images use only the small CTV writer above."""
    for value, domain, digest_field, expected_wire in _fixed_leaf_vectors():
        body = _payload(value)
        assert isinstance(body, dict)
        digest = body.pop(digest_field)
        assert isinstance(digest, str)
        assert digest == _clean_digest(domain, _digest_payload(body))
        assert encode_semantic_contract(value) == expected_wire


@pytest.mark.parametrize(
    ("factory", "domain", "digest_field"),
    (
        (lambda: UdPathPattern.create(anchor="predicate_head", steps=(UdPathStep(direction="up", dependency_label="ccomp", ordinal=0),)), "memorii.semantic-ingestion.ud-path-pattern.v1", "pattern_digest"),
        (lambda: _leaves()[4], "memorii.semantic-ingestion.semantic-scope-policy.v1", "policy_fingerprint"),
        (lambda: _leaves()[3], "memorii.semantic-ingestion.ud-role-schema.v1", "schema_digest"),
        (lambda: _leaves()[5], "memorii.semantic-ingestion.predicate-semantic-policy.v1", "policy_fingerprint"),
    ),
)
def test_clean_room_policy_field_mutations_change_only_the_addressed_leaf(factory, domain: str, digest_field: str) -> None:
    value = factory()
    body = _payload(value)
    assert isinstance(body, dict)
    mutations: dict[str, object]
    if isinstance(value, UdPathPattern):
        mutations = {
            "anchor": "role_head",
            "steps.direction": (UdPathStep(direction="down", dependency_label="ccomp", ordinal=0),),
            "steps.dependency_label": (UdPathStep(direction="up", dependency_label="xcomp", ordinal=0),),
            "steps.ordinal": (UdPathStep(direction="up", dependency_label="ccomp", ordinal=1),),
        }
    elif isinstance(value, SemanticScopePolicy):
        alternate = UdPathPattern.create(anchor="role_head", steps=())
        alternate_family = ConstructionFamily.create(family_id="nominal")
        alternate_quote = QuotationBoundaryPolicy.create(mode="inside_quoted_content")
        mutations = {
            "language": "fr", "construction_family": alternate_family, "predicate_family": "nominal",
            "allowed_predicate_ancestor_paths": (alternate,), "negation_bearer_patterns": (alternate,),
            "embedding_head_lemmas": {"say": "reported"}, "reporting_head_lemmas": frozenset({"say"}),
            "question_mood_features": frozenset({"interrogative"}), "quotation_boundary_policy": alternate_quote,
            "temporal_attachment_patterns": (alternate,), "forbidden_clause_crossings": frozenset({"ccomp"}),
        }
    elif isinstance(value, UdRoleSchema):
        alternate = UdPathPattern.create(anchor="role_head", steps=())
        mutations = {
            "role_id": "patient", "anchor_form": "nominal", "allowed_dependency_paths": (alternate,),
            "required_function_word_lemmas": frozenset({"by"}), "forbidden_clause_crossings": frozenset({"ccomp"}),
            "coordination_support": "forbidden", "voice_normalization": "active_passive_equivalent",
            "canonical_graph_role": "patient", "required_polarity_evidence": "must_support_negative",
            "required_commitment_evidence": frozenset({"reported"}),
        }
    else:
        _, path, _, alternate_role, _, _ = _leaves()
        alternate_family = ConstructionFamily.create(family_id="nominal")
        alternate_role = UdRoleSchema.create(
            role_id="patient", anchor_form="nominal", allowed_dependency_paths=(path,), required_function_word_lemmas=frozenset(),
            forbidden_clause_crossings=frozenset(), coordination_support="allowed", voice_normalization="active_only",
            canonical_graph_role="patient", required_polarity_evidence="not_required", required_commitment_evidence=frozenset(),
        )
        mutations = {
            "predicate_id": "employs", "language": "fr", "predicate_lemmas": frozenset({"employ"}),
            "nominal_lemmas": frozenset({"employment"}), "role_schemas": (alternate_role,), "verbalizer_id": "verb-1",
            "supported_commitments": frozenset({"reported"}), "supported_constructions": frozenset({alternate_family}),
        }
    for field, replacement in mutations.items():
        changed = dict(body)
        changed.pop(digest_field, None)
        changed.pop(digest_field, None)
        if field.startswith("steps."):
            changed["steps"] = replacement
        else:
            changed[field] = replacement
        candidate = type(value).create(**changed)
        candidate_body = _payload(candidate)
        assert isinstance(candidate_body, dict)
        candidate_digest = candidate_body.pop(digest_field)
        assert candidate_digest == _clean_digest(domain, _digest_payload(candidate_body))
        assert candidate_digest != getattr(value, digest_field), field


@pytest.mark.parametrize("value", _codec_values(), ids=lambda value: type(value).__name__)
def test_every_slice_b_codec_rejects_the_full_strict_envelope_matrix(value: object) -> None:
    expected_type = type(value)
    raw = encode_semantic_contract(value)
    assert decode_semantic_contract(raw, expected_type) == value
    envelope = decode_typed_value(raw)
    assert isinstance(envelope, dict) and isinstance(envelope["payload"], dict)
    alternate = next(candidate for candidate in _codec_values() if type(candidate) is not expected_type)
    cases: list[dict[str, object]] = []
    for field in ("schema", "kind", "payload"):
        changed = dict(envelope)
        changed.pop(field)
        cases.append(changed)
        changed = dict(envelope)
        changed[f"extra_{field}"] = True
        cases.append(changed)
    changed = dict(envelope)
    changed["kind"] = "unknown_slice_b_kind"
    cases.append(changed)
    changed = dict(envelope)
    changed["schema"] = "memorii.semantic-ingestion.contract-envelope.v0"
    cases.append(changed)
    payload = dict(envelope["payload"])
    required = next(name for name, field in expected_type.model_fields.items() if field.is_required())
    changed = dict(envelope)
    changed["payload"] = {key: item for key, item in payload.items() if key != required}
    cases.append(changed)
    changed = dict(envelope)
    changed["payload"] = {**payload, "unexpected": True}
    cases.append(changed)
    digest_field = getattr(value, "_digest_field", None)
    if digest_field is not None:
        changed = dict(envelope)
        changed["payload"] = {**payload, digest_field: "a" * 63 + "g"}
        cases.append(changed)
    for malformed in cases:
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value(malformed), expected_type)
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(raw, type(alternate))
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(_clean_ctv(payload), expected_type)


def test_ud_path_step_nullable_ordinal_distinguishes_omission_from_explicit_null() -> None:
    step = UdPathStep(direction="up", dependency_label="nsubj", ordinal=None)
    envelope = decode_typed_value(encode_semantic_contract(step))
    assert isinstance(envelope, dict) and isinstance(envelope["payload"], dict)
    omitted = dict(envelope)
    omitted["payload"] = {"direction": "up", "dependency_label": "nsubj"}
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(encode_typed_value(omitted), UdPathStep)
    assert decode_semantic_contract(encode_semantic_contract(step), UdPathStep).ordinal is None


def test_scope_policy_canonicalizes_maps_and_rejects_noncanonical_or_duplicate_pattern_tuples() -> None:
    family, path, quote, _, scope, _ = _leaves()
    reordered = SemanticScopePolicy.create(
        language=scope.language, construction_family=family, predicate_family=scope.predicate_family,
        allowed_predicate_ancestor_paths=scope.allowed_predicate_ancestor_paths,
        negation_bearer_patterns=scope.negation_bearer_patterns,
        embedding_head_lemmas={"say": "reported", "believe": "believed"},
        reporting_head_lemmas=scope.reporting_head_lemmas, question_mood_features=scope.question_mood_features,
        quotation_boundary_policy=quote, temporal_attachment_patterns=scope.temporal_attachment_patterns,
        forbidden_clause_crossings=scope.forbidden_clause_crossings,
    )
    reverse_inserted = SemanticScopePolicy.create(
        language=scope.language, construction_family=family, predicate_family=scope.predicate_family,
        allowed_predicate_ancestor_paths=scope.allowed_predicate_ancestor_paths,
        negation_bearer_patterns=scope.negation_bearer_patterns,
        embedding_head_lemmas={"believe": "believed", "say": "reported"},
        reporting_head_lemmas=scope.reporting_head_lemmas, question_mood_features=scope.question_mood_features,
        quotation_boundary_policy=quote, temporal_attachment_patterns=scope.temporal_attachment_patterns,
        forbidden_clause_crossings=scope.forbidden_clause_crossings,
    )
    assert reordered.policy_fingerprint == reverse_inserted.policy_fingerprint
    assert encode_semantic_contract(reordered) == encode_semantic_contract(reverse_inserted)
    other = UdPathPattern.create(anchor="role_head", steps=())
    ordered = tuple(sorted((path, other), key=lambda item: item.pattern_digest))
    reverse = tuple(reversed(ordered))
    for field in ("allowed_predicate_ancestor_paths", "negation_bearer_patterns", "temporal_attachment_patterns"):
        body = scope.model_dump(mode="python", exclude={"policy_fingerprint"})
        body[field] = reverse
        with pytest.raises(ValidationError, match="canonical"):
            SemanticScopePolicy.create(**body)
        body[field] = (path, path)
        with pytest.raises(ValidationError, match="canonical"):
            SemanticScopePolicy.create(**body)


def test_closed_union_discriminators_reject_unknown_rule_and_policy_key_shapes() -> None:
    selection = _selection("parser", "union")
    envelope = decode_typed_value(encode_semantic_contract(selection))
    assert isinstance(envelope, dict) and isinstance(envelope["payload"], dict)
    bad_rule = dict(envelope)
    bad_rule["payload"] = {**envelope["payload"], "selected_policy": {**envelope["payload"]["selected_policy"], "kind": "unknown"}}
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(encode_typed_value(bad_rule), ConsensusPolicySelection)
    parser = next(value for value in _codec_values() if isinstance(value, ParserOperationPolicyAuthority))
    envelope = decode_typed_value(encode_semantic_contract(parser))
    assert isinstance(envelope, dict) and isinstance(envelope["payload"], dict)
    bad_key = dict(envelope)
    bad_key["payload"] = {**envelope["payload"], "semantic_policy_key": {"kind": "unknown"}}
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(encode_typed_value(bad_key), ParserOperationPolicyAuthority)




def _parser_authority_for(key: object, bindings: tuple[PredicateSemanticPolicyBinding, ...], role_schemas: tuple[UdRoleSchema, ...] = ()) -> ParserOperationPolicyAuthority:
    family = _leaves()[0]
    return ParserOperationPolicyAuthority.create(
        operation_id=_hex("authority-operation"), proposal_id="proposal", segment_id="segment",
        segment_language_route_digest=_hex("route"), parser_consensus_policy_fingerprint=ParserConsensusPolicy.create().policy_fingerprint,
        semantic_policy_key=key, predicate_policy_bindings=bindings, construction_families=(family,), role_schemas=role_schemas,
    )


def test_parser_authority_enforces_fact_correction_and_retraction_binding_cardinality() -> None:
    _, _, _, role, _, policy = _leaves()
    replacement = PredicateSemanticPolicy.create(
        predicate_id="replacement", language="en", predicate_lemmas=frozenset({"replace"}), nominal_lemmas=frozenset(),
        role_schemas=(role,), verbalizer_id=None, supported_commitments=frozenset({"asserted"}), supported_constructions=frozenset({_leaves()[0]}),
    )
    fact = PredicateSemanticPolicyBinding.create(role="fact", predicate_id=policy.predicate_id, policy=policy)
    corrected = PredicateSemanticPolicyBinding.create(role="corrected", predicate_id=policy.predicate_id, policy=policy)
    replacement_binding = PredicateSemanticPolicyBinding.create(role="replacement", predicate_id=replacement.predicate_id, policy=replacement)
    retracted = PredicateSemanticPolicyBinding.create(role="retracted", predicate_id=policy.predicate_id, policy=policy)
    assert _parser_authority_for(FactOperationSemanticPolicyKey(kind="fact", predicate_id=policy.predicate_id), (fact,), (role,))
    assert _parser_authority_for(CorrectionOperationSemanticPolicyKey(kind="correction", corrected_predicate_id=policy.predicate_id, replacement_predicate_id=replacement.predicate_id), (corrected, replacement_binding), (role,))
    assert _parser_authority_for(CorrectionOperationSemanticPolicyKey(kind="correction", corrected_predicate_id=policy.predicate_id, replacement_predicate_id=policy.predicate_id), (corrected, PredicateSemanticPolicyBinding.create(role="replacement", predicate_id=policy.predicate_id, policy=policy)), (role,))
    assert _parser_authority_for(RetractionOperationSemanticPolicyKey(kind="retraction", retracted_predicate_id=policy.predicate_id), (retracted,), (role,))
    key = CorrectionOperationSemanticPolicyKey(kind="correction", corrected_predicate_id=policy.predicate_id, replacement_predicate_id=replacement.predicate_id)
    for bindings in ((corrected,), (replacement_binding, corrected), (corrected, corrected), (corrected, PredicateSemanticPolicyBinding.create(role="replacement", predicate_id=policy.predicate_id, policy=policy))):
        with pytest.raises(ValidationError, match="exactly match"):
            _parser_authority_for(key, bindings, (role,))


def test_action_and_identity_keys_preserve_zero_binding_and_canonical_tuple_contracts() -> None:
    _, path, _, agent, _, _ = _leaves()
    object_schema = UdRoleSchema.create(
        role_id="object", anchor_form="verbal", allowed_dependency_paths=(path,), required_function_word_lemmas=frozenset(),
        forbidden_clause_crossings=frozenset(), coordination_support="allowed", voice_normalization="active_only",
        canonical_graph_role="object", required_polarity_evidence="not_required", required_commitment_evidence=frozenset(),
    )
    action = ActionStateOperationSemanticPolicyKey(kind="action_state", logical_action_digest=_hex("logical"), action_state_digest=_hex("state"), state_id="open", role_ids=("agent", "object"))
    assert _parser_authority_for(action, (), (agent, object_schema)).predicate_policy_bindings == ()
    for schemas in ((object_schema, agent), (agent,), (agent, agent)):
        with pytest.raises(ValidationError, match="role schemas"):
            _parser_authority_for(action, (), schemas)
    identity = IdentityOperationSemanticPolicyKey(
        kind="identity", identity_operation_digest=_hex("identity"), operation="merge",
        predecessor_mention_digests=tuple(sorted((_hex("a"), _hex("b")))), successor_mention_digests=(_hex("c"),),
        reference_assignment_digests=(_hex("d"),),
    )
    assert _parser_authority_for(identity, ()).predicate_policy_bindings == ()
    for field, values in (
            ("predecessor_mention_digests", tuple(reversed(sorted((_hex("a"), _hex("b")))))),
        ("successor_mention_digests", (_hex("c"), _hex("c"))),
            ("reference_assignment_digests", tuple(reversed(sorted((_hex("d"), _hex("z")))))),
    ):
        payload = identity.model_dump(mode="python")
        payload[field] = values
        with pytest.raises(ValidationError, match="canonical"):
            IdentityOperationSemanticPolicyKey(**payload)


def test_paired_authorities_reject_orphans_and_crossed_request_owned_material() -> None:
    family, _, _, role, scope_policy, policy = _leaves()
    key = FactOperationSemanticPolicyKey(kind="fact", predicate_id=policy.predicate_id)
    binding = PredicateSemanticPolicyBinding.create(role="fact", predicate_id=policy.predicate_id, policy=policy)
    parser = _parser_authority_for(key, (binding,), (role,))
    scope = ScopeOperationPolicyAuthority.create(
        operation_id=parser.operation_id, proposal_id=parser.proposal_id, segment_id=parser.segment_id,
        segment_language_route_digest=parser.segment_language_route_digest,
        scope_consensus_policy_fingerprint=ScopeConsensusPolicy.create().policy_fingerprint,
        temporal_attachment_consensus_policy_fingerprint=TemporalAttachmentConsensusPolicy.create().policy_fingerprint,
        semantic_policy_key=key, scope_policy=scope_policy,
    )
    assert LanguageConstructionPolicyAuthorityBundle.create(policies=(parser, scope))
    with pytest.raises(ValidationError, match="requires parser then scope"):
        LanguageConstructionPolicyAuthorityBundle.create(policies=(parser,))
    with pytest.raises(ValidationError, match="requires parser then scope"):
        LanguageConstructionPolicyAuthorityBundle.create(policies=(scope, parser))
    crossed = ScopeOperationPolicyAuthority.create(
        operation_id=_hex("other-operation"), proposal_id=scope.proposal_id, segment_id=scope.segment_id,
        segment_language_route_digest=scope.segment_language_route_digest,
        scope_consensus_policy_fingerprint=scope.scope_consensus_policy_fingerprint,
        temporal_attachment_consensus_policy_fingerprint=scope.temporal_attachment_consensus_policy_fingerprint,
        semantic_policy_key=key, scope_policy=scope_policy,
    )
    with pytest.raises(ValidationError, match="requires parser then scope"):
        LanguageConstructionPolicyAuthorityBundle.create(policies=(parser, crossed))
    wrong_key = ScopeOperationPolicyAuthority.create(
        operation_id=scope.operation_id, proposal_id=scope.proposal_id, segment_id=scope.segment_id,
        segment_language_route_digest=scope.segment_language_route_digest,
        scope_consensus_policy_fingerprint=scope.scope_consensus_policy_fingerprint,
        temporal_attachment_consensus_policy_fingerprint=scope.temporal_attachment_consensus_policy_fingerprint,
        semantic_policy_key=FactOperationSemanticPolicyKey(kind="fact", predicate_id="other"), scope_policy=scope_policy,
    )
    with pytest.raises(ValidationError, match="same semantic policy key"):
        LanguageConstructionPolicyAuthorityBundle.create(policies=(parser, wrong_key))
    foreign_language_policy = PredicateSemanticPolicy.create(
        predicate_id=policy.predicate_id, language="fr", predicate_lemmas=policy.predicate_lemmas, nominal_lemmas=policy.nominal_lemmas,
        role_schemas=policy.role_schemas, verbalizer_id=None, supported_commitments=policy.supported_commitments,
        supported_constructions=policy.supported_constructions,
    )
    foreign_language_parser = _parser_authority_for(key, (PredicateSemanticPolicyBinding.create(role="fact", predicate_id=policy.predicate_id, policy=foreign_language_policy),), (role,))
    foreign_language_scope = scope.model_dump(mode="python", exclude={"authority_digest"})
    foreign_language_scope["operation_id"] = foreign_language_parser.operation_id
    foreign_language_scope["proposal_id"] = foreign_language_parser.proposal_id
    foreign_language_scope["segment_id"] = foreign_language_parser.segment_id
    foreign_language_scope["segment_language_route_digest"] = foreign_language_parser.segment_language_route_digest
    with pytest.raises(ValidationError, match="languages"):
        LanguageConstructionPolicyAuthorityBundle.create(policies=(foreign_language_parser, ScopeOperationPolicyAuthority.create(**foreign_language_scope)))
    other_family = ConstructionFamily.create(family_id="other")
    missing_family_parser = ParserOperationPolicyAuthority.create(
        operation_id=parser.operation_id, proposal_id=parser.proposal_id, segment_id=parser.segment_id,
        segment_language_route_digest=parser.segment_language_route_digest,
        parser_consensus_policy_fingerprint=parser.parser_consensus_policy_fingerprint, semantic_policy_key=key,
        predicate_policy_bindings=(binding,), construction_families=(other_family,), role_schemas=(role,),
    )
    with pytest.raises(ValidationError, match="construction family"):
        LanguageConstructionPolicyAuthorityBundle.create(policies=(missing_family_parser, scope))

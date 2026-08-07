"""Focused strict-v1 proof for persisted preparation and prompt catalog owners."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.models import SourceObservation
from memorii.core.semantic_ingestion.contracts import (
    ActionProposalCatalog,
    ActionProposalRoleContract,
    ActionProposalStateContract,
    PredicatePromptContract,
    PredicateProposalCatalog,
    SemanticContractCodecError,
    TextPreparationPolicy,
    TextPreparationRequest,
    decode_semantic_contract,
    encode_semantic_contract,
)
from memorii.domain.enums import SourceType

_MANIFEST = Path(__file__).parents[5] / "docs/design/semantic_ingestion/prompt-catalog-schema-manifest-v1.json"
_ACTION_SCHEMA = "0fb700ec5d56481e582f70d89a66627708cd95ad2393e9df78559e0f1f0b16fe"
_PREDICATE_SCHEMA = "7c2fef7072d3996b93949eab7db1701d5458379a6b65d96f5851415d748fb0e0"


def _digest(label: str) -> str:
    return sha256(label.encode("ascii")).hexdigest()


def _catalogs() -> tuple[ActionProposalCatalog, PredicateProposalCatalog]:
    role = ActionProposalRoleContract(
        role_id="actor", endpoint_kind="actor", description="Actor", grounding_requirement="verbatim_source_mention"
    )
    state = ActionProposalStateContract(
        state_id="started", description="Started", allowed_role_ids=("actor",), required_state_anchor=True
    )
    action = ActionProposalCatalog.create(
        vocabulary_namespace="vocabulary", proposal_capability_fingerprint=_digest("capability"),
        roles=(role,), states=(state,), catalog_schema_fingerprint=_ACTION_SCHEMA,
    )
    predicate = PredicatePromptContract.create(
        predicate_id="works_for", description="Employment", subject_value_kind="entity",
        object_value_kind="entity", object_literal_type=None, supported_commitments=("asserted",),
    )
    predicates = PredicateProposalCatalog.create(
        vocabulary_namespace="vocabulary", proposal_capability_fingerprint=_digest("capability"),
        predicates=(predicate,), catalog_schema_fingerprint=_PREDICATE_SCHEMA,
    )
    return action, predicates


def _policy() -> TextPreparationPolicy:
    return TextPreparationPolicy.create(
        max_segment_characters=128,
        supported_languages=("en", "es"),
        segmentation_algorithm="memorii.semantic-ingestion.safe-sentence-first-paragraph-bounded.v1",
        context_window_algorithm="memorii.semantic-ingestion.owned-partition-whole-boundary-context.v1",
    )


def _request() -> TextPreparationRequest:
    return TextPreparationRequest(
        observation=SourceObservation(
            source_id="clean-room-preparation",
            text="Clean-room source.",
            source_type=SourceType.USER,
            timestamp=datetime(2026, 8, 5, tzinfo=UTC),
        ),
        policy=_policy(),
    )


def _envelope(value: object) -> dict[str, object]:
    raw = encode_semantic_contract(value)  # type: ignore[arg-type]
    from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value

    envelope = decode_typed_value(raw)
    assert isinstance(envelope, dict)
    return envelope


@pytest.mark.parametrize("factory", (_policy, _request, lambda: _catalogs()[1], lambda: _catalogs()[0]))
def test_direct_strict_codec_matrix_for_preparation_and_catalog_contracts(factory: object) -> None:
    value = factory()  # type: ignore[operator]
    expected_type = type(value)
    envelope = _envelope(value)
    encoded = encode_semantic_contract(value)
    assert decode_semantic_contract(encoded, expected_type) == value
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    for field in expected_type.model_fields:
        mutated = copy.deepcopy(envelope)
        altered = mutated["payload"]
        assert isinstance(altered, dict)
        altered.pop(field)
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_semantic_contract_value(mutated), expected_type)
    for mutation in ("extra", "alias", "foreign_schema", "legacy_kind"):
        altered = copy.deepcopy(envelope)
        if mutation == "extra":
            altered["unexpected"] = True
        elif mutation == "alias":
            body = altered["payload"]
            assert isinstance(body, dict)
            first = next(iter(body))
            body["alias_" + first] = body.pop(first)
        elif mutation == "foreign_schema":
            altered["schema"] = "foreign.schema.v1"
        else:
            altered["kind"] = "legacy_" + str(altered["kind"])
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_semantic_contract_value(altered), expected_type)
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(encoded, TextPreparationPolicy if expected_type is not TextPreparationPolicy else TextPreparationRequest)
    digest_field = next(
        (
            name
            for name in ("policy_fingerprint", "catalog_fingerprint", "contract_digest")
            if name in expected_type.model_fields
        ),
        None,
    )
    forged = (
        value.model_copy(update={digest_field: "f" * 64})
        if digest_field is not None
        else value.model_copy(update={"policy": value.policy.model_copy(update={"policy_fingerprint": "f" * 64})})
    )
    with pytest.raises(SemanticContractCodecError):
        encode_semantic_contract(forged)


def encode_semantic_contract_value(envelope: dict[str, object]) -> bytes:
    from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value

    return encode_typed_value(envelope)


def test_request_rejects_stale_nested_policy_before_output() -> None:
    request = _request()
    stale = request.policy.model_copy(update={"max_segment_characters": 129})
    with pytest.raises(ValueError, match="policy_fingerprint mismatch"):
        TextPreparationRequest(observation=request.observation, policy=stale)


def test_pinned_manifest_bytes_and_schema_fingerprints_are_external_authority() -> None:
    raw = _MANIFEST.read_bytes()
    assert sha256(raw).hexdigest() == "57d3a0d7cf71198f838cbf71b694024f13cb558e1aff19623fe677d1a32567fa"
    manifest = json.loads(raw)
    assert {item["schema_id"] for item in manifest["catalog_schemas"]} == {
        "memorii.semantic-ingestion.action-proposal-catalog",
        "memorii.semantic-ingestion.predicate-proposal-catalog",
    }
    action, predicate = _catalogs()
    assert action.catalog_schema_fingerprint == _ACTION_SCHEMA
    assert predicate.catalog_schema_fingerprint == _PREDICATE_SCHEMA
    for value in (action, predicate):
        assert decode_semantic_contract(encode_semantic_contract(value), type(value)) == value


def test_catalogs_and_preparation_policy_are_strict_and_recompute_identity() -> None:
    policy = TextPreparationPolicy.create(
        max_segment_characters=128, supported_languages=("en", "es"),
        segmentation_algorithm="memorii.semantic-ingestion.safe-sentence-first-paragraph-bounded.v1",
        context_window_algorithm="memorii.semantic-ingestion.owned-partition-whole-boundary-context.v1",
    )
    changed = TextPreparationPolicy.create(
        max_segment_characters=129, supported_languages=("en", "es"),
        segmentation_algorithm="memorii.semantic-ingestion.safe-sentence-first-paragraph-bounded.v1",
        context_window_algorithm="memorii.semantic-ingestion.owned-partition-whole-boundary-context.v1",
    )
    assert policy.policy_fingerprint != changed.policy_fingerprint
    action, predicate = _catalogs()
    for value in (policy, action, predicate):
        envelope = encode_semantic_contract(value)
        assert decode_semantic_contract(envelope, type(value)) == value
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(envelope + b"x", type(value))
    with pytest.raises(ValueError):
        ActionProposalCatalog.create(**(action.model_dump(mode="python", exclude={"catalog_fingerprint"}) | {"catalog_schema_fingerprint": _digest("wrong")}))
    with pytest.raises(ValueError):
        TextPreparationPolicy.create(
            max_segment_characters=128, supported_languages=("es", "en"),
            segmentation_algorithm="memorii.semantic-ingestion.safe-sentence-first-paragraph-bounded.v1",
            context_window_algorithm="memorii.semantic-ingestion.owned-partition-whole-boundary-context.v1",
        )

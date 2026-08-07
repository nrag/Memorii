"""Independent known-answer vector for the capability-bound proposal request."""

from __future__ import annotations

import base64
import json
import zlib
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from clean_room_request_test_support import build_clean_room_semantic_proposal_request
from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value, encode_typed_value
from memorii.core.semantic_ingestion.contracts import (
    LanguageCandidate,
    SegmentLanguageRoute,
    SemanticContractCodecError,
    SemanticProposal,
    SemanticProposalRequest,
    _restore_closed_wire_enums,
    decode_semantic_contract,
    encode_semantic_contract,
)

_FIXTURE = Path(__file__).parents[3] / "fixtures/semantic_ingestion/normalization_contracts/semantic_proposal_request_v1.json"
_DOMAIN = b"memorii.semantic-ingestion.semantic-proposal-request.v1\0"
_ACTION_SCHEMA = "0fb700ec5d56481e582f70d89a66627708cd95ad2393e9df78559e0f1f0b16fe"
_PREDICATE_SCHEMA = "7c2fef7072d3996b93949eab7db1701d5458379a6b65d96f5851415d748fb0e0"


def _hex(label: str) -> str:
    return sha256(label.encode("ascii")).hexdigest()


def _tree(value: Any) -> Any:
    """Small clean-room CTV tree writer; deliberately not the production encoder."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="python")
    if hasattr(value, "value") and type(value).__module__ == "enum":
        value = value.value
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, bytes):
        return {"$type": "bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, int):
        return {"$type": "integer", "value": str(value)}
    if isinstance(value, tuple):
        return {"$type": "tuple", "items": [_tree(item) for item in value]}
    if isinstance(value, list):
        return {"$type": "tuple", "items": [_tree(item) for item in value]}
    if isinstance(value, dict):
        return {"$type": "map", "entries": [[key, _tree(value[key])] for key in sorted(value)]}
    raise TypeError(type(value).__name__)


def _ctv(value: Any) -> bytes:
    return json.dumps(_tree(value), ensure_ascii=True, separators=(",", ":")).encode("ascii")


def _proposal() -> SemanticProposal:
    raw = json.loads((Path(__file__).parents[3] / "fixtures/semantic_ingestion/normalization_contracts/semantic_proposal_literal_v1.json").read_text(encoding="ascii"))
    body = decode_typed_value(zlib.decompress(base64.b64decode(raw["expected_ctv_preimage_zlib_base64"])))
    body["preparation_fingerprint"] = _hex("preparation")
    route = body["language_route"]
    assert isinstance(route, dict)
    body["language_route"] = SegmentLanguageRoute.create(**({key: value for key, value in route.items() if key != "route_digest"} | {"parent_projection_segment_id": body["segment_id"], "candidates": (LanguageCandidate(language="en", probability_ppm=1_000_000, model_fingerprint=_hex("router-model")),)}))
    restored = _restore_closed_wire_enums(body)
    return SemanticProposal.create(**restored)


_request = build_clean_room_semantic_proposal_request


def test_request_vector_is_independent_and_round_trips() -> None:
    request = _request()
    body = request.model_dump(mode="python", exclude={"semantic_request_fingerprint"})
    expected = _ctv(body)
    assert sha256(_DOMAIN + expected).hexdigest() == request.semantic_request_fingerprint
    fixture = json.loads(_FIXTURE.read_text(encoding="ascii"))
    assert fixture["ctv_sha256"] == sha256(expected).hexdigest()
    assert fixture["fingerprint"] == request.semantic_request_fingerprint
    assert decode_semantic_contract(encode_semantic_contract(request), SemanticProposalRequest) == request
    assert request.action_proposal_catalog.catalog_schema_fingerprint == _ACTION_SCHEMA
    assert request.predicate_catalog.catalog_schema_fingerprint == _PREDICATE_SCHEMA


@pytest.mark.parametrize("field", ("proposal_capability_fingerprint", "segment_id"))
def test_request_rejects_authority_mutations(field: str) -> None:
    request = _request()
    with pytest.raises((ValueError, SemanticContractCodecError)):
        SemanticProposalRequest.create(**(request.model_dump(mode="python", exclude={"semantic_request_fingerprint"}) | {field: _hex(field)}))


def test_request_preparation_coordinate_changes_the_independent_preimage() -> None:
    request = _request()
    original = request.model_dump(mode="python", exclude={"semantic_request_fingerprint"})
    mutated = original | {"preparation_fingerprint": _hex("other-preparation")}
    assert _ctv(mutated) != _ctv(original)


def _request_envelope(request: SemanticProposalRequest) -> dict[str, Any]:
    envelope = decode_typed_value(encode_semantic_contract(request))
    assert isinstance(envelope, dict)
    return envelope


@pytest.mark.parametrize("field", tuple(SemanticProposalRequest.model_fields))
def test_request_closed_wire_rejects_each_missing_field(field: str) -> None:
    envelope = _request_envelope(_request())
    payload = dict(envelope["payload"])
    payload.pop(field)
    envelope["payload"] = payload
    with pytest.raises(SemanticContractCodecError, match="validation failed"):
        decode_semantic_contract(encode_typed_value(envelope), SemanticProposalRequest)


@pytest.mark.parametrize("mutation", ("extra", "alias", "legacy_schema", "legacy_kind", "wrong_expected_kind"))
def test_request_closed_wire_rejects_envelope_substitutions(mutation: str) -> None:
    request = _request()
    envelope = _request_envelope(request)
    if mutation == "extra":
        envelope["unexpected"] = True
    elif mutation == "alias":
        envelope["payload"]["source"] = envelope["payload"].pop("source_id")
    elif mutation == "legacy_schema":
        envelope["schema"] = "memorii.semantic-ingestion.contract-envelope.v0"
    elif mutation == "legacy_kind":
        envelope["kind"] = "semantic_proposal_request_v0"
    else:
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value(envelope), SemanticProposal)
        return
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(encode_typed_value(envelope), SemanticProposalRequest)


@pytest.mark.parametrize("path", (
    ("predicate_catalog", "catalog_schema_fingerprint"),
    ("action_proposal_catalog", "catalog_schema_fingerprint"),
    ("predicate_catalog", "predicates", 0, "description"),
    ("predicate_catalog", "predicates", 0, "supported_commitments"),
    ("action_proposal_catalog", "roles", 0, "description"),
    ("action_proposal_catalog", "states", 0, "state_id"),
    ("registered_prompt", "prompt_ref"),
    ("proposer_manifest", "runtime_fingerprint"),
    ("language_route", "parent_projection_segment_id"),
))
def test_request_rejects_nested_authority_substitution(path: tuple[object, ...]) -> None:
    envelope = _request_envelope(_request())
    target: Any = envelope["payload"]
    for key in path[:-1]:
        target = target[key]
    key = path[-1]
    target[key] = _hex("foreign-" + "-".join(map(str, path)))
    with pytest.raises(SemanticContractCodecError, match="validation failed"):
        decode_semantic_contract(encode_typed_value(envelope), SemanticProposalRequest)


@pytest.mark.parametrize("catalog_field,member_field", (("predicate_catalog", "predicates"), ("action_proposal_catalog", "roles"), ("action_proposal_catalog", "states")))
def test_request_rejects_catalog_member_order_and_duplicates(catalog_field: str, member_field: str) -> None:
    envelope = _request_envelope(_request())
    members = envelope["payload"][catalog_field][member_field]
    mutated = [members[0], members[0]] if len(members) == 1 else list(reversed(members))
    envelope["payload"][catalog_field][member_field] = mutated
    with pytest.raises(SemanticContractCodecError, match="validation failed"):
        decode_semantic_contract(encode_typed_value(envelope), SemanticProposalRequest)


def test_request_rejects_stale_fingerprint_after_valid_member_change() -> None:
    request = _request()
    body = request.model_dump(mode="python", exclude={"semantic_request_fingerprint"})
    prompt = request.registered_prompt.model_copy(update={"prompt_ref": "semantic-proposal-v2"})
    with pytest.raises(ValueError, match="semantic_request_fingerprint mismatch"):
        SemanticProposalRequest(**(body | {"registered_prompt": prompt, "semantic_request_fingerprint": request.semantic_request_fingerprint}))

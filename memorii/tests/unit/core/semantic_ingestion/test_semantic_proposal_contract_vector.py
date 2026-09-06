"""Independent fixed-byte proof for the normalized semantic-proposal wire."""

from __future__ import annotations

import base64
import copy
import json
import zlib
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.contracts import (
    SemanticContractCodecError,
    SemanticProposal,
    decode_semantic_contract,
    encode_semantic_contract,
)

_FIXTURE = (
    Path(__file__).parents[3]
    / "fixtures"
    / "semantic_ingestion"
    / "normalization_contracts"
    / "semantic_proposal_literal_v1.json"
)
_PROPOSAL_DOMAIN = b"memorii.semantic-ingestion.semantic-proposal.v1\0"


def _load_vector() -> tuple[dict[str, Any], bytes, str]:
    """Load the losslessly compressed static vector without production helpers."""
    raw = json.loads(_FIXTURE.read_text(encoding="ascii"))
    assert raw["format"] == "semantic-proposal-normalization-contract-vector.v1"
    assert raw["semantic_proposal_encoding"] == "zlib+base64+canonical-json"
    assert raw["expected_ctv_preimage_encoding"] == "zlib+base64"
    payload_bytes = zlib.decompress(base64.b64decode(raw["semantic_proposal_zlib_base64"], validate=True))
    expected = zlib.decompress(base64.b64decode(raw["expected_ctv_preimage_zlib_base64"], validate=True))
    return json.loads(payload_bytes), expected, raw["expected_proposal_digest"]


def _local_ctv(value: Any, *, encoded_bytes: bool = False) -> bytes:
    """Minimal clean-room CTV writer for the static JSON proposal vector only."""
    if encoded_bytes:
        assert isinstance(value, str)
        return _local_json({"$type": "bytes", "value": base64.b64encode(value.encode("utf-8")).decode("ascii")})
    if value is None or isinstance(value, (bool, str)):
        return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    if isinstance(value, int):
        return _local_json({"$type": "integer", "value": str(value)})
    if isinstance(value, list):
        # The closed wire has no list-valued fields: JSON arrays are persisted tuples.
        return _local_json({"$type": "tuple", "items": [_local_tree(item) for item in value]})
    if isinstance(value, dict):
        return _local_json(
            {
                "$type": "map",
                "entries": [
                    [key, _local_tree(value[key], encoded_bytes=key == "canonical_payload")]
                    for key in sorted(value)
                ],
            }
        )
    raise TypeError(f"unsupported local CTV value: {type(value).__name__}")


def _local_tree(value: Any, *, encoded_bytes: bool = False) -> Any:
    return json.loads(_local_ctv(value, encoded_bytes=encoded_bytes))


def _local_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def _mutate(value: Any) -> Any:
    if isinstance(value, str):
        return f"mutated-{value}"
    if value is None:
        return "mutated"
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, list):
        return [*value, "mutated"]
    if isinstance(value, dict):
        return {**value, "_vector_mutation": True}
    raise TypeError(type(value).__name__)


def _proposal_envelope(payload: dict[str, Any]) -> bytes:
    return _local_ctv(
        {
            "schema": "memorii.semantic-ingestion.contract-envelope.v1",
            "kind": "semantic_proposal",
            "payload": payload,
        }
    )


def test_fixed_normalized_proposal_vector_matches_independent_ctv_and_production_codec() -> None:
    payload, expected_preimage, expected_digest = _load_vector()
    body = {key: value for key, value in payload.items() if key != "proposal_digest"}

    # This first equality is intentionally independent of the production CTV and digest helpers.
    assert _local_ctv(body) == expected_preimage
    assert sha256(_PROPOSAL_DOMAIN + expected_preimage).hexdigest() == expected_digest
    assert payload["proposal_digest"] == expected_digest

    proposal = decode_semantic_contract(_proposal_envelope(payload), SemanticProposal)
    assert proposal.proposal_digest == expected_digest
    # Production is checked only after the independent known-answer calculation.
    assert encode_typed_value(proposal.model_dump(mode="python", exclude={"proposal_digest"})) == expected_preimage
    assert decode_semantic_contract(encode_semantic_contract(proposal), SemanticProposal) == proposal


@pytest.mark.parametrize("field", tuple(SemanticProposal.model_fields)[:-1])
def test_each_semantic_proposal_preimage_field_changes_the_independent_ctv(field: str) -> None:
    payload, expected_preimage, _expected_digest = _load_vector()
    body = {key: value for key, value in payload.items() if key != "proposal_digest"}
    mutated = copy.deepcopy(body)
    mutated[field] = _mutate(mutated[field])

    assert _local_ctv(mutated) != expected_preimage


def test_map_member_permutation_is_canonical_but_semantic_tuple_permutation_rejects() -> None:
    payload, expected_preimage, _expected_digest = _load_vector()
    body = {key: value for key, value in payload.items() if key != "proposal_digest"}
    permuted_map = dict(reversed(tuple(body.items())))
    assert _local_ctv(permuted_map) == expected_preimage

    noncanonical = copy.deepcopy(payload)
    noncanonical["mentions"].reverse()
    with pytest.raises(SemanticContractCodecError, match="validation failed"):
        decode_semantic_contract(_proposal_envelope(noncanonical), SemanticProposal)

    noncanonical = copy.deepcopy(payload)
    noncanonical["facts"].reverse()
    with pytest.raises(SemanticContractCodecError, match="validation failed"):
        decode_semantic_contract(_proposal_envelope(noncanonical), SemanticProposal)

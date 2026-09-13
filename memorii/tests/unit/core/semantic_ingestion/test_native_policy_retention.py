"""Focused compatibility and authority proof for retained native policy bundles."""

from __future__ import annotations

from pathlib import Path

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapNativePlanningConstructionAuthorityV3,
    canonical_contract_value,
    restore_closed_wire_enums,
)
from pydantic import BaseModel

_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures/semantic_ingestion/historical_terminal"
    / "native-planning-authority-without-policy-bundle.ctv"
)


class _TupleHookModel(BaseModel):
    retained: str
    omitted: str

    def _canonical_contract_field_names(self) -> tuple[str, ...]:
        return ("retained",)


class _ListHookModel(BaseModel):
    value: str

    def _canonical_contract_field_names(self) -> list[str]:
        return ["value"]


class _IteratorHookModel(BaseModel):
    value: str

    def _canonical_contract_field_names(self):
        return iter(("value",))


def test_historical_native_planning_authority_omits_bundle_and_reencodes() -> None:
    raw = _FIXTURE.read_bytes()
    body = decode_typed_value(raw)
    assert isinstance(body, dict)
    authority = BootstrapNativePlanningConstructionAuthorityV3.model_validate(
        restore_closed_wire_enums(body)
    )

    assert authority.arbitration_policy_bundle is None
    assert "arbitration_policy_bundle" not in authority.model_dump(mode="python")
    assert "arbitration_policy_bundle" not in authority.model_dump(mode="json")
    assert encode_typed_value(authority.model_dump(mode="python")) == raw


def test_canonical_contract_field_hook_requires_tuple() -> None:
    assert canonical_contract_value(_TupleHookModel(retained="kept", omitted="dropped")) == {
        "retained": "kept"
    }
    for value in (_ListHookModel(value="list"), _IteratorHookModel(value="iterator")):
        with pytest.raises(
            TypeError,
            match="canonical contract field names must be a tuple",
        ):
            canonical_contract_value(value)

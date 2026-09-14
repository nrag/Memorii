"""Schema-versioned group-result attestation binding and legacy byte freeze.

The schema-1 fixture envelope was produced by the pre-extension contracts, so
decoding and re-encoding it proves legacy group-core bytes are unchanged.
Schema-2 exclusion and schema-3 attestation rules are pinned on the same
contract; the reload binds its own version to the persisted core version.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphGroupCommitReloadV3,
    BootstrapGraphGroupCommitResultCoreV3,
    decode_semantic_contract,
    encode_semantic_contract,
    rebuild_bootstrap_graph_effect_contracts,
)

rebuild_bootstrap_graph_effect_contracts()

_SCHEMA_1_RELOAD = (
    Path(__file__).resolve().parents[3] / "fixtures/semantic_ingestion/persisted/schema1_group_commit_reload_v3.hex"
)
ATTESTATION = "b" * 64


def _schema_1_reload() -> BootstrapGraphGroupCommitReloadV3:
    envelope = bytes.fromhex(_SCHEMA_1_RELOAD.read_text())
    return decode_semantic_contract(envelope, BootstrapGraphGroupCommitReloadV3)


def test_schema_1_group_reload_bytes_are_frozen() -> None:
    envelope = bytes.fromhex(_SCHEMA_1_RELOAD.read_text())
    reload = _schema_1_reload()
    core = reload.persisted_result.core

    assert reload.group_result_schema_version == 1
    assert core.group_result_schema_version == 1
    assert core.core_digest == ("b1a86ed66276984a775fcfd4969e69b112e687378a43835afd4824fa53455aa3")
    # The exact persisted envelope re-encodes byte-for-byte after the
    # schema-2/3 extension.
    assert encode_semantic_contract(reload) == envelope
    dump = reload.model_dump(mode="python")
    assert "transaction_group_commit_attestation_digest" not in dump
    assert "transaction_group_commit_attestation_digest" not in dump["persisted_result"]["core"]
    assert core.transaction_group_commit_attestation_digest is None


def test_group_core_versioned_exclusions_are_exact() -> None:
    legacy = {
        "group_result_schema_version",
        "observation_delta",
        "native_projection_publication_receipt",
        "transaction_group_commit_attestation_digest",
    }
    assert BootstrapGraphGroupCommitResultCoreV3._versioned_digest_excluded_fields(
        {"group_result_schema_version": 1}
    ) == frozenset(legacy)
    assert BootstrapGraphGroupCommitResultCoreV3._versioned_digest_excluded_fields(
        {"group_result_schema_version": 2}
    ) == frozenset({"transaction_group_commit_attestation_digest"})
    assert (
        BootstrapGraphGroupCommitResultCoreV3._versioned_digest_excluded_fields({"group_result_schema_version": 3})
        == frozenset()
    )


def _construct_core(version: int, disposition: str, attestation: str | None):
    return _schema_1_reload().persisted_result.core.model_copy(
        update={
            "group_result_schema_version": version,
            "disposition": disposition,
            "transaction_group_commit_attestation_digest": attestation,
        }
    )


def test_group_core_serialization_excludes_the_attestation_below_schema_3() -> None:
    schema_1 = _schema_1_reload().persisted_result.core
    assert "transaction_group_commit_attestation_digest" not in schema_1.model_dump()
    schema_2 = _construct_core(2, "committed", None)
    schema_3 = _construct_core(3, "committed", ATTESTATION)
    assert "transaction_group_commit_attestation_digest" not in schema_2.model_dump()
    assert schema_3.model_dump()["transaction_group_commit_attestation_digest"] == ATTESTATION
    assert "transaction_group_commit_attestation_digest" not in schema_2._canonical_contract_field_names()
    assert "transaction_group_commit_attestation_digest" in schema_3._canonical_contract_field_names()


def _clause_core(disposition: str, attestation: str | None, *, version: int = 3):
    """A minimal closure-valid core body isolating the attestation clause."""
    group_id = "c" * 64
    delta = SimpleNamespace(
        transaction_group_id=group_id,
        operation_ids=("a" * 64,),
        observation_revision_before="revision:before",
        observation_revision_after="revision:after",
        terminal_status="committed" if disposition == "committed" else "evidence_only",
    )
    operation = SimpleNamespace(
        operation_id="a" * 64,
        final_status="accepted" if disposition == "committed" else "rejected",
        reduction=SimpleNamespace(transaction_group_id=group_id),
    )
    receipt = SimpleNamespace(
        source_operation_id="source-operation:1",
        transaction_group_id=group_id,
        request_ctv_digest="d" * 64,
        graph_revision_before="revision:graph:before",
        graph_revision_after="revision:graph:after",
    )
    return BootstrapGraphGroupCommitResultCoreV3.model_construct(
        group_result_schema_version=version,
        request_ctv_digest="d" * 64,
        disposition=disposition,
        ordered_operation_results=(operation,),
        graph_revision_before="revision:graph:before",
        graph_revision_after="revision:graph:after",
        event_revision_before="revision:graph:before",
        event_revision_after="revision:graph:after",
        observation_revision_before="revision:before",
        observation_revision_after="revision:after",
        publication_operation_generation=1,
        publication_artifact_generation=1,
        atomic_write_digest="e" * 64,
        transaction_group_commit_attestation_digest=attestation,
        observation_delta=delta,
        native_projection_publication_receipt=receipt if disposition == "committed" else None,
        core_digest="0" * 64,
    )


def test_schema_3_group_core_requires_attestation_exactly_when_committed() -> None:
    with pytest.raises(ValueError, match="schema-3 group result attestation binding"):
        _clause_core("committed", None).validate_core()
    with pytest.raises(ValueError, match="schema-3 group result attestation binding"):
        _clause_core("noncommitting", ATTESTATION).validate_core()
    assert _clause_core("committed", ATTESTATION).validate_core() is not None
    # Schema 2 gains no attestation requirement: any declared value passes
    # the disposition clauses and stays excluded from bytes.
    assert _clause_core("committed", None, version=2).validate_core() is not None
    assert _clause_core("committed", ATTESTATION, version=2).validate_core() is not None


def test_schema_1_group_core_forbids_the_attestation_digest() -> None:
    with pytest.raises(ValueError, match="legacy group result forbids ledger fields"):
        _clause_core("committed", ATTESTATION, version=1).validate_core()


def _reload_clause(reload_version: int, core_version: int):
    core = _clause_core(
        "committed" if core_version == 3 else "committed",
        ATTESTATION,
        version=core_version,
    )
    reload = BootstrapGraphGroupCommitReloadV3.model_construct(
        group_result_schema_version=reload_version,
        source_operation_id="source-operation:1",
        transaction_group_id="c" * 64,
        operation_ids=("a" * 64,),
        request_ctv_digest="d" * 64,
        persisted_result=SimpleNamespace(core=core),
        successor_generation=SimpleNamespace(operation_id="source-operation:1"),
        observation_delta=core.observation_delta,
        native_projection_publication_receipt=core.native_projection_publication_receipt,
        ledger_entry_id="ledger:entry",
        ledger_entry_digest="f" * 64,
        reload_digest="0" * 64,
    )
    return reload


def test_group_reload_binds_its_schema_version_to_the_persisted_core() -> None:
    assert "transaction_group_commit_attestation_digest" not in (BootstrapGraphGroupCommitReloadV3.model_fields)
    assert _reload_clause(3, 3).validate_reload() is not None
    assert _reload_clause(2, 2).validate_reload() is not None
    with pytest.raises(ValueError, match="schema-3 group reload ledger closure"):
        _reload_clause(3, 2).validate_reload()
    with pytest.raises(ValueError, match="schema-2 group reload ledger closure"):
        _reload_clause(2, 3).validate_reload()
    with pytest.raises(ValueError, match="schema-3 group reload ledger closure"):
        _reload_clause(3, 1).validate_reload()

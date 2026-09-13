"""Production reader boundary and acceptance revocation evidence proof."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from acceptance.production_revocation import (
    IndependentProductionRevocationEvidenceVerifier,
    ProductionRevocationEvidenceError,
)
from acceptance.production_revocation_bridge import SerializedProductionRevocationEvidence
from acceptance.schema_registry import canonical_digest, schema_for, signing_preimage, unsigned_artifact
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.deployment_authorization import InstalledProductionRevocationReader


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _artifact(
    schema: str, signer: Ed25519PrivateKey, coordinate: str, **fields: object
) -> tuple[str, bytes]:
    registered = schema_for(schema)
    value = dict(fields)
    digest_field = registered["digest_field"]
    value[digest_field] = "0" * 64
    value["signing_key_coordinate"] = coordinate
    value["signature"] = "0" * 128
    value[digest_field] = canonical_digest(
        registered["digest_domain"], "registered", unsigned_artifact(value, schema)
    )
    value["signature"] = signer.sign(signing_preimage(schema, value, coordinate)).hex()
    return value[digest_field], _json(value)


class _Reader:
    def __init__(self, evidence: SerializedProductionRevocationEvidence, parents: dict[str, bytes]) -> None:
        self.evidence = evidence
        self.parents = parents
        self.outage = False

    def read_for_prior_release(self, _: str) -> SerializedProductionRevocationEvidence:
        if self.outage:
            raise OSError("reader unavailable")
        return self.evidence

    def load_checkpoint(self, checkpoint_digest: str) -> bytes:
        return self.parents[checkpoint_digest]


def _evidence(checkpoint_epoch: int = 2) -> tuple[
    str, bytes, bytes, dict[str, bytes], Ed25519PrivateKey, str
]:
    key = Ed25519PrivateKey.generate()
    coordinate = "production-revocation-1"
    now = datetime(2026, 9, 13, tzinfo=UTC)
    prior_release = "a" * 64
    receipt_digest, receipt = _artifact(
        "ProductionRevocationReceipt",
        key,
        coordinate,
        schema_version=1,
        purpose="production_revocation_receipt",
        prior_approval_release_digest=prior_release,
        withdrawal_requested_at=_time(now),
        prior_production_epoch=1,
        advanced_production_epoch=2,
        completed_at=_time(now + timedelta(seconds=1)),
    )
    parent_digest, parent = _artifact(
        "ProductionEpochCheckpoint",
        key,
        coordinate,
        schema_version=1,
        purpose="production_epoch_checkpoint",
        production_authority_snapshot_digest="b" * 64,
        checkpoint_generation=1,
        predecessor_checkpoint_digest=None,
        active_production_epoch=1,
        active_authorization_digests=["c" * 64],
        revocation_receipt_digests=["d" * 64],
        observed_at=_time(now),
    )
    _, checkpoint = _artifact(
        "ProductionEpochCheckpoint",
        key,
        coordinate,
        schema_version=1,
        purpose="production_epoch_checkpoint",
        production_authority_snapshot_digest="b" * 64,
        checkpoint_generation=2,
        predecessor_checkpoint_digest=parent_digest,
        active_production_epoch=checkpoint_epoch,
        active_authorization_digests=["c" * 64],
        revocation_receipt_digests=[receipt_digest],
        observed_at=_time(now + timedelta(seconds=2)),
    )
    return prior_release, receipt, checkpoint, {parent_digest: parent}, key, coordinate


def _verifier(reader: _Reader, key: Ed25519PrivateKey, coordinate: str) -> IndependentProductionRevocationEvidenceVerifier:
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return IndependentProductionRevocationEvidenceVerifier(reader=reader, trust_keys={coordinate: public})


def test_independent_revocation_verifier_requires_current_signed_chain() -> None:
    prior, receipt, checkpoint, parents, key, coordinate = _evidence()
    reader = _Reader(SerializedProductionRevocationEvidence(receipt, checkpoint), parents)
    verifier = _verifier(reader, key, coordinate)
    verified_receipt, verified_checkpoint = verifier.verify(
        prior_approval_release_digest=prior,
        receipt=receipt,
        checkpoint=checkpoint,
        require_current_reader_bytes=True,
    )
    assert verified_receipt["prior_approval_release_digest"] == prior
    assert verified_checkpoint["checkpoint_generation"] == 2
    # Recovery re-reads the independently owned current mapping and bytes.
    verifier.verify(
        prior_approval_release_digest=prior,
        receipt=receipt,
        checkpoint=checkpoint,
        require_current_reader_bytes=True,
    )


def test_independent_revocation_verifier_allows_later_current_epoch() -> None:
    prior, receipt, checkpoint, parents, key, coordinate = _evidence(checkpoint_epoch=3)
    verifier = _verifier(_Reader(SerializedProductionRevocationEvidence(receipt, checkpoint), parents), key, coordinate)
    verifier.verify(
        prior_approval_release_digest=prior,
        receipt=receipt,
        checkpoint=checkpoint,
        require_current_reader_bytes=True,
    )


def test_independent_revocation_verifier_fails_closed_on_reader_outage_after_restart() -> None:
    prior, receipt, checkpoint, parents, key, coordinate = _evidence()
    reader = _Reader(SerializedProductionRevocationEvidence(receipt, checkpoint), parents)
    verifier = _verifier(reader, key, coordinate)
    verifier.verify(
        prior_approval_release_digest=prior,
        receipt=receipt,
        checkpoint=checkpoint,
        require_current_reader_bytes=True,
    )
    reader.outage = True
    with pytest.raises(ProductionRevocationEvidenceError, match="reader"):
        verifier.verify(
            prior_approval_release_digest=prior,
            receipt=receipt,
            checkpoint=checkpoint,
            require_current_reader_bytes=True,
        )


@pytest.mark.parametrize("mutation", ["wrong_signer", "stale", "membership", "epoch"])
def test_independent_revocation_verifier_fails_closed(mutation: str) -> None:
    prior, receipt, checkpoint, parents, key, coordinate = _evidence()
    reader = _Reader(SerializedProductionRevocationEvidence(receipt, checkpoint), parents)
    if mutation == "wrong_signer":
        verifier = IndependentProductionRevocationEvidenceVerifier(
            reader=reader, trust_keys={"other": b"x" * 32}
        )
    elif mutation == "stale":
        reader.evidence = SerializedProductionRevocationEvidence(receipt, checkpoint + b" ")
        verifier = _verifier(reader, key, coordinate)
    else:
        value = json.loads(checkpoint)
        if mutation == "membership":
            value["revocation_receipt_digests"] = ["e" * 64]
        else:
            value["active_production_epoch"] = 3
        # Mutating signed canonical bytes must fail before any weaker join could pass.
        checkpoint = _json(value)
        reader.evidence = SerializedProductionRevocationEvidence(receipt, checkpoint)
        verifier = _verifier(reader, key, coordinate)
    with pytest.raises(ProductionRevocationEvidenceError):
        verifier.verify(
            prior_approval_release_digest=prior,
            receipt=receipt,
            checkpoint=checkpoint,
            require_current_reader_bytes=True,
        )


def test_production_file_reader_returns_only_canonical_current_mapping(tmp_path: Path) -> None:
    prior, receipt, checkpoint, parents, _, _ = _evidence()
    root = tmp_path / "production"
    objects = root / "objects"
    current = root / "current"
    objects.mkdir(parents=True)
    current.mkdir()
    receipt_digest = json.loads(receipt)["receipt_digest"]
    checkpoint_digest = json.loads(checkpoint)["checkpoint_digest"]
    (objects / receipt_digest).write_bytes(receipt)
    (objects / checkpoint_digest).write_bytes(checkpoint)
    for digest, raw in parents.items():
        (objects / digest).write_bytes(raw)
    (current / f"{prior}.json").write_bytes(
        _json({"prior_approval_release_digest": prior, "receipt_digest": receipt_digest, "checkpoint_digest": checkpoint_digest})
    )
    reader = InstalledProductionRevocationReader().from_fixed_configuration({"reader_root": str(root)})
    observed = reader.read_for_prior_release(prior)
    assert observed.receipt == receipt
    assert observed.checkpoint == checkpoint
    (current / f"{prior}.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="production_revocation_current"):
        reader.read_for_prior_release(prior)

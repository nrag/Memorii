"""Independent recovery head transitions and public-only verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from memorii.core.persistence.key_owner import INSTALLATION_CONTROL_RECOVERY_SIGNATURE_PURPOSE, LocalSigningKeyOwner
from memorii.core.storage_administration.recovery_authority import (
    IndependentRecoveryCustody,
    InstallationControlRecoveryBundle,
    InstallationRecoveryAnchor,
    InstallationRecoveryHead,
    PendingRecoveryHead,
    RecoveryAuthorityError,
    RecoveryBundleMember,
    RecoveryParticipantExpectation,
    SealedRecoveryHead,
    sign_recovery_head,
)
from memorii.core.storage_administration.recovery_bundle import open_recovery_bundle, seal_recovery_bundle

_SIGNER = "recovery-owner"
AuthorityFixture = tuple[IndependentRecoveryCustody, LocalSigningKeyOwner, InstallationRecoveryHead]


@pytest.fixture
def authority(tmp_path: Path) -> AuthorityFixture:
    signer = LocalSigningKeyOwner(tmp_path / "keys")
    fingerprint = signer.create_key(_SIGNER)
    directory = tmp_path / "custody"
    directory.mkdir(mode=0o700)
    custody = IndependentRecoveryCustody(
        directory, custody_id="owner-custody", installation_id="installation", repository_id="partition",
        trusted_public_keys={_SIGNER: signer.public_key_bytes(_SIGNER)},
    )
    genesis = sign_recovery_head(
        SealedRecoveryHead(
            outcome="registered", anchor=InstallationRecoveryAnchor(
                installation_id="installation", repository_id="partition", custody_id="owner-custody",
                control_revision=2, journal_ordinal=3, journal_tip="a" * 64, eligibility_epoch=1,
                signer_fingerprint=fingerprint, publication_digest="b" * 64, bundle_digest="c" * 64,
            ),
        ),
        signer=signer, signer_key_id=_SIGNER,
    )
    custody.register(genesis)
    return custody, signer, genesis


def _prepare(
    custody: IndependentRecoveryCustody, signer: LocalSigningKeyOwner, genesis: InstallationRecoveryHead,
) -> InstallationRecoveryHead:
    assert isinstance(genesis.payload, SealedRecoveryHead)
    pending = sign_recovery_head(
        PendingRecoveryHead(
            predecessor=genesis.digest(), prior_anchor=genesis.payload.anchor,
            operation="grant", operation_digest="d" * 64,
            participants=(RecoveryParticipantExpectation(
                participant_id="read-grants", revision=1, pre_state_digest="e" * 64, effect_digest="f" * 64,
            ),),
        ),
        signer=signer, signer_key_id=_SIGNER,
    )
    custody.prepare(pending)
    return pending


def test_pending_prevents_recovery_until_exact_successor_seals(authority: AuthorityFixture) -> None:
    custody, signer, genesis = authority
    pending = _prepare(custody, signer, genesis)
    assert isinstance(pending.payload, PendingRecoveryHead)
    with pytest.raises(RecoveryAuthorityError, match="pending"):
        custody.current_sealed()
    assert custody.current() == pending
    with pytest.raises(RecoveryAuthorityError, match="exact current sealed"):
        custody.prepare(pending)
    successor = sign_recovery_head(
        SealedRecoveryHead(
            outcome="applied", predecessor=genesis.digest(), pending_digest=pending.digest(),
            operation_digest=pending.payload.operation_digest,
            anchor=pending.payload.prior_anchor.model_copy(update={
                "control_revision": 3, "journal_ordinal": 5, "journal_tip": "1" * 64,
                "eligibility_epoch": 2, "bundle_digest": "2" * 64,
            }),
        ),
        signer=signer, signer_key_id=_SIGNER,
    )
    with pytest.raises(RecoveryAuthorityError, match="exact successor evidence"):
        custody.seal(successor, effects={})
    custody.seal(successor, effects={"read-grants": "f" * 64})
    assert custody.current_sealed() == successor
    with pytest.raises(RecoveryAuthorityError, match="exact current pending"):
        custody.seal(successor, effects={"read-grants": "f" * 64})


def test_abort_requires_unchanged_authority_and_no_effect(authority: AuthorityFixture) -> None:
    custody, signer, genesis = authority
    pending = _prepare(custody, signer, genesis)
    assert isinstance(pending.payload, PendingRecoveryHead)
    aborted = sign_recovery_head(
        SealedRecoveryHead(
            outcome="aborted", predecessor=genesis.digest(), pending_digest=pending.digest(),
            operation_digest=pending.payload.operation_digest, anchor=pending.payload.prior_anchor,
        ),
        signer=signer, signer_key_id=_SIGNER,
    )
    with pytest.raises(RecoveryAuthorityError, match="unchanged"):
        custody.seal(aborted, effects={"read-grants": "f" * 64})
    custody.seal(aborted, effects={})
    assert custody.current_sealed() == aborted


def test_reference_uses_pinned_public_key_and_rejects_duplicate_fields(
    authority: AuthorityFixture, tmp_path: Path,
) -> None:
    custody, signer, genesis = authority
    public_key = signer.public_key_bytes(_SIGNER)
    (tmp_path / "keys" / f"{_SIGNER}.key").unlink()
    reopened = IndependentRecoveryCustody(
        tmp_path / "custody", custody_id="owner-custody", installation_id="installation", repository_id="partition",
        trusted_public_keys={_SIGNER: public_key},
    )
    assert reopened.current_sealed() == genesis
    data = json.dumps(genesis.model_dump(mode="json"))
    (tmp_path / "custody" / "head.json").write_text(
        data.replace('"protocol_version": 1', '"protocol_version": 1, "protocol_version": 1', 1),
        encoding="utf-8",
    )
    with pytest.raises(RecoveryAuthorityError, match="could not be read"):
        custody.current_sealed()


def test_bundle_verification_binds_exact_member_inventory_and_anchor(
    authority: AuthorityFixture, tmp_path: Path,
) -> None:
    _, signer, genesis = authority
    assert isinstance(genesis.payload, SealedRecoveryHead)
    prior = genesis.payload.anchor
    content = b"control snapshot"
    member_digest = hashlib.sha256(content).hexdigest()
    members = tuple(
        RecoveryBundleMember(
            owner_id="storage-owner", kind=kind, schema_version=1, size_bytes=len(content),
            digest=member_digest, source_coordinate="b" * 64,
        )
        for kind in (
            "control_journal", "control_snapshot", "finalized_publications", "participant_inventory", "public_trust",
        )
    )
    unsigned = InstallationControlRecoveryBundle(
        installation_id=prior.installation_id, repository_id=prior.repository_id, custody_id=prior.custody_id,
        generation_id="selected-generation", control_revision=prior.control_revision, journal_ordinal=prior.journal_ordinal,
        journal_tip=prior.journal_tip, eligibility_epoch=prior.eligibility_epoch,
        publication_digest=prior.publication_digest, trust_registry_digest="d" * 64,
        signer_key_id=_SIGNER, signer_fingerprint=prior.signer_fingerprint, members=members, signature="0" * 128,
    )
    bundle = unsigned.model_copy(update={"signature": signer.sign(
        _SIGNER, INSTALLATION_CONTROL_RECOVERY_SIGNATURE_PURPOSE, unsigned.unsigned_digest(),
    )})
    public_key = signer.public_key_bytes(_SIGNER)
    bundle.verify(bundle.anchor(), public_key)
    altered = bundle.model_copy(update={"journal_tip": "f" * 64})
    with pytest.raises(RecoveryAuthorityError, match="trusted anchor"):
        altered.verify(bundle.anchor(), public_key)
    with pytest.raises(RecoveryAuthorityError, match="trusted anchor"):
        altered.verify(altered.anchor(), public_key)
    inputs = []
    for member in members:
        path = tmp_path / member.kind
        path.write_bytes(content)
        path.chmod(0o600)
        inputs.append(path)
    sealed = tmp_path / "sealed"
    key = b"k" * 32
    anchor = seal_recovery_bundle(bundle, sources=inputs, destination=sealed, recovery_key=key, public_key=public_key)
    opened = tmp_path / "opened"
    assert open_recovery_bundle(
        sealed, anchor=anchor, public_key=public_key, recovery_key=key, destination=opened,
    ) == bundle
    assert [path.read_bytes() for path in sorted(opened.iterdir())] == [content] * len(members)
    damaged = sealed / "member-004.enc"
    damaged.write_bytes(b"!" * damaged.stat().st_size)
    unavailable = tmp_path / "unavailable"
    with pytest.raises(RecoveryAuthorityError, match="could not be verified"):
        open_recovery_bundle(sealed, anchor=anchor, public_key=public_key, recovery_key=key, destination=unavailable)
    assert not unavailable.exists()

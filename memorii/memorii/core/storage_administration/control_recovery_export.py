"""Collect typed control recovery evidence from storage and deny owners."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import TypeAdapter

from memorii.core.harness_state.grant_registry import GrantDenialSnapshot
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.key_owner import INSTALLATION_CONTROL_RECOVERY_SIGNATURE_PURPOSE
from memorii.core.storage_administration.recovery_authority import (
    InstallationControlRecoveryBundle,
    RecoveryBundleMember,
    decode_recovery_json,
)
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.core.storage_administration.suppression_journal import SuppressionRecord
from memorii.stores.sqlite.control import ControlDatabase
from memorii.stores.sqlite.private_storage import (
    open_private_file,
    read_private_file,
    require_private_directory,
    write_private_file,
)

_SUPPRESSION_RECORD = TypeAdapter(SuppressionRecord)
MAX_RECOVERY_METADATA_BYTES = 16 * 1024 * 1024


def read_recovery_suppressions(directory: Path) -> tuple[SuppressionRecord, ...]:
    """Read pinned v2 suppression records from one current owner directory."""
    if not directory.exists() and not directory.is_symlink():
        return ()
    require_private_directory(directory)
    records = []
    for path in sorted(directory.glob("forget-*.json")):
        content = read_private_file(path, limit=MAX_RECOVERY_METADATA_BYTES + 1)
        if len(content) > MAX_RECOVERY_METADATA_BYTES:
            raise ValueError("recovery suppression record exceeds the supported size")
        records.append(_SUPPRESSION_RECORD.validate_python(decode_recovery_json(content)))
    by_id = {record.suppression_id: record for record in records}
    if len(by_id) != len(records):
        raise ValueError("recovery suppression identifiers are not unique")
    return tuple(record.model_copy(update={"authority_capability_digest": None})
                 for record in sorted(records, key=lambda record: record.suppression_id))


def recovery_suppression_digests(
    suppressions: tuple[tuple[SuppressionRecord, ...], tuple[SuppressionRecord, ...]],
) -> tuple[str, str]:
    return (
        hashlib.sha256(_metadata_bytes([record.model_dump(mode="json") for record in suppressions[0]])).hexdigest(),
        hashlib.sha256(_metadata_bytes([record.model_dump(mode="json") for record in suppressions[1]])).hexdigest(),
    )


def _metadata_bytes(value: object) -> bytes:
    content = json.dumps(value, sort_keys=True).encode("utf-8")
    if len(content) > MAX_RECOVERY_METADATA_BYTES:
        raise ValueError("recovery metadata exceeds the supported size")
    return content


def export_control_recovery(
    service: StorageAdministrationService, *, snapshot: Path, state: InstallationControlState,
    publication: RuntimePublicationState, custody_id: str, output: Path,
    suppressions: tuple[tuple[SuppressionRecord, ...], tuple[SuppressionRecord, ...]],
    grant_denials: GrantDenialSnapshot | None,
) -> tuple[InstallationControlRecoveryBundle, tuple[Path, ...]]:
    """Build the signed manifest after the verified live views are pinned."""
    with ControlDatabase(snapshot, journal_verifier=service._verify_journal_signature) as control:
        control.validate_journal()
        if control.read_control_state() != state or control.read_publication_state(publication.repository_id) != publication:
            raise ValueError("recovery control copy does not match pinned authority")
        journal = control.read_journal()
        binding = control.read_managed_spool_binding()
        payloads = {
            ("storage-owner", "control_journal"): [entry.model_dump(mode="json") for entry in journal],
            ("storage-owner", "finalized_publications"): [publication.model_dump(mode="json")],
            ("storage-owner", "public_trust"): [entry.model_dump(mode="json") for entry in control.list_trust_entries()],
            ("storage-owner", "participant_inventory"): {
                "managed_spool": None if binding is None else binding.model_dump(mode="json"),
            },
            ("active", "suppression"): [record.model_dump(mode="json") for record in suppressions[0]],
            ("archived", "suppression"): [record.model_dump(mode="json") for record in suppressions[1]],
        }
    if grant_denials is not None:
        payloads["read-grants", "deny_state"] = grant_denials.model_dump(mode="json")
    sources = {("storage-owner", "control_snapshot"): snapshot}
    for (owner, kind), payload in payloads.items():
        path = output / f"{owner}-{kind}.json"
        write_private_file(path, _metadata_bytes(payload), exclusive=True)
        sources[owner, kind] = path
    journal_tip = journal[-1].entry_digest
    members, paths = [], []
    for (owner, kind), path in sorted(sources.items()):
        digest = hashlib.sha256()
        with open_private_file(path) as source:
            while chunk := source.read(1 << 20):
                digest.update(chunk)
        members.append(RecoveryBundleMember.model_validate({
            "owner_id": owner, "kind": kind, "schema_version": 1, "size_bytes": path.stat().st_size, "digest": digest.hexdigest(),
            "source_coordinate": grant_denials.digest() if owner == "read-grants" and grant_denials else journal_tip,
        }))
        paths.append(path)
    signer_key_id = service._signer_key_id
    manifest = InstallationControlRecoveryBundle(
        installation_id=publication.installation_id, repository_id=publication.repository_id,
        custody_id=custody_id, generation_id=publication.data_generation_id,
        control_revision=state.control_revision, journal_ordinal=len(journal), journal_tip=journal_tip,
        eligibility_epoch=state.eligibility_epoch, publication_digest=publication.payload_digest(),
        trust_registry_digest=publication.trust_registry_digest,
        signer_fingerprint=service._signing.public_key_fingerprint(signer_key_id), signer_key_id=signer_key_id,
        members=tuple(members), signature="0" * 128,
    )
    return manifest.model_copy(update={"signature": service._signing.sign(
        signer_key_id, INSTALLATION_CONTROL_RECOVERY_SIGNATURE_PURPOSE, manifest.unsigned_digest(),
    )}), tuple(paths)

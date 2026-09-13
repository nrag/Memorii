from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from acceptance.authority_repository import (
    AcceptanceAuthorityRepository,
    AcceptanceEvaluationSnapshot,
    AcceptanceFenceRegistration,
    AtomicEvaluationReceiptStore,
    AuthorityRepositoryUnavailable,
    SqliteAcceptanceAuthorityFence,
    repository_identity,
)
from acceptance.schema_registry import canonical_digest, schema_for, unsigned_artifact


def _artifact(schema_id: str, **overrides: object) -> bytes:
    schema = schema_for(schema_id)
    value: dict[str, object] = {}
    for field in schema["fields"]:
        name, kind = field["name"], field["type"]
        if field["nullable"]:
            value[name] = None
            continue
        if kind == "integer":
            value[name] = 1
        elif kind == "timestamp":
            value[name] = "2026-09-12T00:00:00Z"
        elif kind == "digest":
            value[name] = "a" * 64
        elif kind == "hex":
            value[name] = "0" * max(128, field.get("minimum_length", 0))
        elif kind == "string":
            value[name] = field.get("enum", ["x"])[0]
        elif kind == "array":
            item = field["item"]
            if field.get("minimum_items", 0) == 0:
                value[name] = []
            elif item.get("type") == "digest":
                value[name] = ["b" * 64]
            elif item.get("name") == "AcceptanceStaticKeyDeclaration":
                value[name] = [
                    {
                        "key_reference": "key",
                        "public_key": "1" * 64,
                        "valid_from": "2026-09-12T00:00:00Z",
                        "valid_until": None,
                        "allowed_purposes": ["x"],
                    }
                ]
            else:
                value[name] = [["b" * 64, "c" * 64]]
    value["approval_purpose" if schema_id == "CapabilityBaselineApprovalRelease" else "purpose"] = schema["purpose"]
    value["schema_version"] = schema["schema_version"]
    value.update(overrides)
    digest_name = schema["digest_field"]
    value[digest_name] = canonical_digest(schema["digest_domain"], "registered", unsigned_artifact(value, schema_id))
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def _registration(root: Path) -> AcceptanceFenceRegistration:
    return AcceptanceFenceRegistration(
        "memorii.acceptance.test",
        "test-fence",
        "sqlite",
        "fence-domain",
        repository_identity(root / "authority"),
        "test-credential",
        "test-signer",
        "test-signature",
    )


def _repository(tmp_path: Path) -> AcceptanceAuthorityRepository:
    registration = _registration(tmp_path)
    fence = SqliteAcceptanceAuthorityFence(
        tmp_path / "fence" / "fence.sqlite",
        registration,
        lambda body, signer, signature: signer == "test-signer" and signature == "test-signature",
    )
    return AcceptanceAuthorityRepository(tmp_path / "authority", fence)


def _commit_bundle(
    sequence: int, predecessor: str | None = None, observed_at: str = "2026-09-12T00:00:00Z"
) -> tuple[dict[str, bytes], bytes]:
    trust = _artifact("AcceptanceTrustSnapshot")
    trust_d = json.loads(trust)["snapshot_digest"]
    key = _artifact("KeyLifecycleEvent", issuance_trust_snapshot_digest=trust_d)
    key_d = json.loads(key)["event_digest"]
    release = _artifact("CapabilityBaselineApprovalRelease")
    release_d = json.loads(release)["release_digest"]
    issuance = _artifact(
        "AcceptanceApprovalIssuanceSnapshot",
        trust_snapshot_digest=trust_d,
        key_event_digests=[key_d],
        key_history_head_digest=key_d,
        key_history_head_sequence=1,
        signing_key_coordinate="x",
    )
    issuance_d = json.loads(issuance)["snapshot_digest"]
    checkpoint = _artifact(
        "AcceptanceCurrentCheckpoint",
        authority_snapshot_digest=trust_d,
        key_history_head_digest=key_d,
        release_history_head_digest=release_d,
        active_release_digest=release_d,
        observed_at=observed_at,
    )
    checkpoint_d = json.loads(checkpoint)["checkpoint_digest"]
    commit = _artifact(
        "AcceptanceAuthorityCommit",
        transaction_sequence=sequence,
        predecessor_commit_digest=predecessor,
        authority_snapshot_digest=trust_d,
        key_history_head_digest=key_d,
        release_history_head_digest=release_d,
        active_release_digest=release_d,
        active_release_epoch=1,
        active_release_sequence=1,
        current_checkpoint_digest=checkpoint_d,
        issuance_snapshot_digest=issuance_d,
        approval_release_digest=release_d,
    )
    prepared = {
        json.loads(raw)[schema_for(schema)["digest_field"]]: raw
        for schema, raw in (
            ("AcceptanceTrustSnapshot", trust),
            ("KeyLifecycleEvent", key),
            ("CapabilityBaselineApprovalRelease", release),
            ("AcceptanceCurrentCheckpoint", checkpoint),
            ("AcceptanceApprovalIssuanceSnapshot", issuance),
        )
    }
    return prepared, commit


def test_selected_snapshot_exposes_only_fenced_authority_prefix(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    prepared, commit = _commit_bundle(1)
    repo.compare_and_publish(prepared_objects=prepared, expected_commit_digest=None, expected_key_head=None, expected_status_generation=None, next_commit=commit)
    with repo.begin_evaluation(datetime(2026, 9, 12, tzinfo=UTC)) as snapshot:
        selected = repo.selected_evaluation_artifacts(snapshot)
    assert selected["commit"]["commit_digest"] == snapshot.commit_digest
    assert [item["event_digest"] for item in selected["keys"]] == [selected["commit"]["key_history_head_digest"]]


def test_registration_is_mandatory_and_persistent(tmp_path: Path) -> None:
    with pytest.raises(AuthorityRepositoryUnavailable, match="registration"):
        SqliteAcceptanceAuthorityFence(tmp_path / "x.sqlite", None, None)
    with pytest.raises(AuthorityRepositoryUnavailable, match="registration"):
        SqliteAcceptanceAuthorityFence(tmp_path / "invalid.sqlite", _registration(tmp_path), lambda *_: False)
    registration = _registration(tmp_path)
    path = tmp_path / "fence.sqlite"
    SqliteAcceptanceAuthorityFence(path, registration, lambda *_: True).current()
    altered = AcceptanceFenceRegistration(
        "other",
        "test-fence",
        "sqlite",
        "fence-domain",
        "test-repository",
        "test-credential",
        "test-signer",
        "test-signature",
    )
    with pytest.raises(AuthorityRepositoryUnavailable, match="registration_mismatch"):
        SqliteAcceptanceAuthorityFence(path, altered, lambda *_: True).current()


def test_fenced_full_commit_recovers_index_and_rejects_tampering(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    prepared, commit = _commit_bundle(1)
    digest = repo.compare_and_publish(
        prepared_objects=prepared,
        expected_commit_digest=None,
        expected_key_head=None,
        expected_status_generation=None,
        next_commit=commit,
    )
    (tmp_path / "authority" / "current.json").write_text("{}", encoding="ascii")
    assert repo.load_current()[:2] == (1, digest)
    path = tmp_path / "authority" / "objects" / json.loads(commit)["commit_digest"]
    path.write_bytes(b"tampered")
    with pytest.raises(AuthorityRepositoryUnavailable):
        repo.load_current()


def test_fence_gap_and_identity_tampering_fail_closed(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    prepared, commit = _commit_bundle(1)
    repo.compare_and_publish(
        prepared_objects=prepared,
        expected_commit_digest=None,
        expected_key_head=None,
        expected_status_generation=None,
        next_commit=commit,
    )
    db = sqlite3.connect(tmp_path / "fence" / "fence.sqlite")
    db.execute("UPDATE acceptance_fence SET sequence=2")
    db.commit()
    db.close()
    with pytest.raises(AuthorityRepositoryUnavailable, match="gap"):
        repo.load_current()


def test_unreachable_prepared_artifact_rejects_publish(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    prepared, commit = _commit_bundle(1)
    extra = _artifact("AcceptanceEvaluationReceipt")
    prepared[json.loads(extra)["receipt_digest"]] = extra
    with pytest.raises(AuthorityRepositoryUnavailable, match="prepared_unreachable"):
        repo.compare_and_publish(
            prepared_objects=prepared,
            expected_commit_digest=None,
            expected_key_head=None,
            expected_status_generation=None,
            next_commit=commit,
        )


def test_snapshot_is_opaque_and_enforces_observation_order(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    prepared, commit = _commit_bundle(1, observed_at="2026-09-13T00:00:00Z")
    repo.compare_and_publish(
        prepared_objects=prepared,
        expected_commit_digest=None,
        expected_key_head=None,
        expected_status_generation=None,
        next_commit=commit,
    )
    with (
        pytest.raises(AuthorityRepositoryUnavailable, match="future"),
        repo.begin_evaluation(datetime(2026, 9, 12, tzinfo=UTC)),
    ):
        pass
    with pytest.raises(AuthorityRepositoryUnavailable, match="constructor"):
        AcceptanceEvaluationSnapshot("a" * 64, "b" * 64, datetime.now(tz=UTC))


def test_receipt_requires_digest_and_canonical_schema(tmp_path: Path) -> None:
    store = AtomicEvaluationReceiptStore(tmp_path / "receipts")
    raw = _artifact("AcceptanceEvaluationReceipt")
    digest = json.loads(raw)["receipt_digest"]
    store.publish(digest, raw)
    store.publish(digest, raw)
    with pytest.raises(AuthorityRepositoryUnavailable):
        store.publish(digest, raw + b"x")


def test_configured_repository_rejects_unsigned_or_untrusted_loaded_artifact(tmp_path: Path) -> None:
    registration = _registration(tmp_path)
    fence = SqliteAcceptanceAuthorityFence(tmp_path / "fence.sqlite", registration, lambda *_: True)
    repository = AcceptanceAuthorityRepository(
        tmp_path / "authority", fence, artifact_signature_verifier=lambda *_: False
    )
    raw = _artifact("AcceptanceTrustSnapshot")
    digest = repository.put_typed(raw, "AcceptanceTrustSnapshot")
    with pytest.raises(AuthorityRepositoryUnavailable, match="artifact_signature"):
        repository._artifact(digest, "AcceptanceTrustSnapshot")


@pytest.mark.parametrize("operation", ["fsync", "link"])
def test_object_publication_failure_leaves_no_final_or_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    repo = _repository(tmp_path)
    raw = _artifact("AcceptanceTrustSnapshot")
    digest = json.loads(raw)["snapshot_digest"]
    original = getattr(__import__("acceptance.authority_repository", fromlist=[operation]).os, operation)

    def fail(*args: object, **kwargs: object) -> object:
        raise OSError("injected")

    monkeypatch.setattr("acceptance.authority_repository.os." + operation, fail)
    with pytest.raises(OSError):
        repo.put_typed(raw, "AcceptanceTrustSnapshot")
    monkeypatch.setattr("acceptance.authority_repository.os." + operation, original)
    assert not (tmp_path / "authority" / "objects" / digest).exists()
    assert not list((tmp_path / "authority" / "objects").glob(".*.tmp"))


def test_receipt_truncated_final_and_index_recovery(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    prepared, commit = _commit_bundle(1)
    digest = repo.compare_and_publish(
        prepared_objects=prepared,
        expected_commit_digest=None,
        expected_key_head=None,
        expected_status_generation=None,
        next_commit=commit,
    )
    index = tmp_path / "authority" / "current.json"
    index.write_text('{"digest":"' + ("0" * 64) + '"}', encoding="ascii")
    assert repo.load_current()[1] == digest
    raw = _artifact("AcceptanceEvaluationReceipt")
    receipt_digest = json.loads(raw)["receipt_digest"]
    store = AtomicEvaluationReceiptStore(tmp_path / "receipts")
    (tmp_path / "receipts").mkdir()
    (tmp_path / "receipts" / receipt_digest).write_bytes(b"truncated")
    with pytest.raises(AuthorityRepositoryUnavailable, match="receipt_conflict"):
        store.publish(receipt_digest, raw)


def test_concurrent_publish_has_one_winner(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    prepared_a, commit_a = _commit_bundle(1)
    prepared_b, commit_b = _commit_bundle(1, observed_at="2026-09-12T00:00:01Z")

    def publish(prepared: dict[str, bytes], commit: bytes) -> str:
        return repo.compare_and_publish(
            prepared_objects=prepared,
            expected_commit_digest=None,
            expected_key_head=None,
            expected_status_generation=None,
            next_commit=commit,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda pair: _attempt(publish, *pair), ((prepared_a, commit_a), (prepared_b, commit_b)))
        )
    assert sum(isinstance(result, str) for result in results) == 1
    assert sum(isinstance(result, AuthorityRepositoryUnavailable) for result in results) == 1
    assert repo.load_current()[0] == 1


def _attempt(callback: object, *args: object) -> object:
    try:
        return callback(*args)  # type: ignore[operator]
    except AuthorityRepositoryUnavailable as exc:
        return exc

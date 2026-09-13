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
    value["purpose"] = schema["purpose"]
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


def test_registration_mismatch_closes_setup_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "fence.sqlite"
    registration = _registration(tmp_path)
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
    real_connect = sqlite3.connect

    class TrackedConnection:
        def __init__(self) -> None:
            self.connection = real_connect(path, isolation_level=None)
            self.closed = False

        def execute(
            self, sql: str, parameters: tuple[object, ...] = ()
        ) -> sqlite3.Cursor:
            return self.connection.execute(sql, parameters)

        def close(self) -> None:
            self.closed = True
            self.connection.close()

    opened: list[TrackedConnection] = []

    def tracked_connect(*_args: object, **_kwargs: object) -> TrackedConnection:
        connection = TrackedConnection()
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    with pytest.raises(AuthorityRepositoryUnavailable, match="registration_mismatch"):
        SqliteAcceptanceAuthorityFence(path, altered, lambda *_: True).current()
    assert len(opened) == 1
    assert opened[0].closed is True


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


def test_active_release_replacement_cannot_commit_before_revocation_evidence(
    tmp_path: Path,
) -> None:
    repo = _repository(tmp_path)
    prepared, first = _commit_bundle(1)
    first_digest = repo.compare_and_publish(
        prepared_objects=prepared,
        expected_commit_digest=None,
        expected_key_head=None,
        expected_status_generation=None,
        next_commit=first,
    )
    proposed = json.loads(first)
    proposed.update(
        transaction_sequence=2,
        predecessor_commit_digest=first_digest,
        active_release_digest="f" * 64,
        active_release_epoch=2,
        active_release_sequence=2,
        production_revocation_evidence=[],
    )
    proposed.pop("commit_digest")
    replacement = _artifact("AcceptanceAuthorityCommit", **proposed)
    with pytest.raises(AuthorityRepositoryUnavailable, match="revocation_transition"):
        repo.compare_and_publish(
            prepared_objects={},
            expected_commit_digest=first_digest,
            expected_key_head=json.loads(first)["key_history_head_digest"],
            expected_status_generation=1,
            next_commit=replacement,
        )


def test_terminal_transition_appends_exactly_one_pair_and_revalidates_on_reopen(
    tmp_path: Path,
) -> None:
    class _Verifier:
        calls = 0

        def verify(self, **_: object) -> tuple[dict[str, object], dict[str, object]]:
            self.calls += 1
            return {}, {}

    verifier = _Verifier()
    registration = _registration(tmp_path)
    fence = SqliteAcceptanceAuthorityFence(
        tmp_path / "fence" / "fence.sqlite", registration, lambda *_: True
    )
    repo = AcceptanceAuthorityRepository(
        tmp_path / "authority", fence, production_revocation_verifier=verifier
    )
    prepared, first = _commit_bundle(1)
    first_digest = repo.compare_and_publish(
        prepared_objects=prepared,
        expected_commit_digest=None,
        expected_key_head=None,
        expected_status_generation=None,
        next_commit=first,
    )
    first_value = json.loads(first)
    old_release = first_value["active_release_digest"]
    release_value = json.loads(repo.get(old_release))
    release_value.update(
        acceptance_release_epoch=2,
        acceptance_release_sequence=2,
        supersedes_release_digest=old_release,
    )
    release_value.pop("release_digest")
    release_value.pop("signature")
    successor = _artifact("CapabilityBaselineApprovalRelease", **release_value)
    successor_digest = json.loads(successor)["release_digest"]
    receipt = _artifact(
        "ProductionRevocationReceipt",
        prior_approval_release_digest=old_release,
        prior_production_epoch=1,
        advanced_production_epoch=2,
    )
    receipt_digest = json.loads(receipt)["receipt_digest"]
    production_checkpoint = _artifact(
        "ProductionEpochCheckpoint",
        checkpoint_generation=1,
        predecessor_checkpoint_digest=None,
        active_production_epoch=2,
        revocation_receipt_digests=[receipt_digest],
    )
    production_checkpoint_digest = json.loads(production_checkpoint)["checkpoint_digest"]
    checkpoint_value = json.loads(repo.get(first_value["current_checkpoint_digest"]))
    checkpoint_value.update(
        checkpoint_generation=2,
        predecessor_checkpoint_digest=first_value["current_checkpoint_digest"],
        release_history_head_digest=successor_digest,
        release_history_head_sequence=2,
        active_release_digest=successor_digest,
        active_epoch=2,
        active_sequence=2,
        production_revocation_evidence=[[receipt_digest, production_checkpoint_digest]],
    )
    checkpoint_value.pop("checkpoint_digest")
    checkpoint_value.pop("signature")
    checkpoint = _artifact("AcceptanceCurrentCheckpoint", **checkpoint_value)
    checkpoint_digest = json.loads(checkpoint)["checkpoint_digest"]
    proposed = dict(first_value)
    proposed.update(
        transaction_sequence=2,
        predecessor_commit_digest=first_digest,
        release_history_head_digest=successor_digest,
        release_history_head_sequence=2,
        active_release_digest=successor_digest,
        active_release_epoch=2,
        active_release_sequence=2,
        current_checkpoint_digest=checkpoint_digest,
        approval_release_digest=successor_digest,
        production_revocation_evidence=[[receipt_digest, production_checkpoint_digest]],
    )
    proposed.pop("commit_digest")
    second = _artifact("AcceptanceAuthorityCommit", **proposed)
    repo.compare_and_publish(
        prepared_objects={
            successor_digest: successor,
            receipt_digest: receipt,
            production_checkpoint_digest: production_checkpoint,
            checkpoint_digest: checkpoint,
        },
        expected_commit_digest=first_digest,
        expected_key_head=first_value["key_history_head_digest"],
        expected_status_generation=1,
        next_commit=second,
    )
    second_digest = json.loads(second)["commit_digest"]

    rollback_receipt = _artifact(
        "ProductionRevocationReceipt",
        prior_approval_release_digest=successor_digest,
        prior_production_epoch=2,
        advanced_production_epoch=3,
    )
    rollback_receipt_digest = json.loads(rollback_receipt)["receipt_digest"]
    rollback_production_checkpoint = _artifact(
        "ProductionEpochCheckpoint",
        checkpoint_generation=2,
        predecessor_checkpoint_digest=production_checkpoint_digest,
        active_production_epoch=3,
        revocation_receipt_digests=[receipt_digest, rollback_receipt_digest],
    )
    rollback_production_checkpoint_digest = json.loads(
        rollback_production_checkpoint
    )["checkpoint_digest"]
    rollback_checkpoint_value = json.loads(checkpoint)
    rollback_checkpoint_value.update(
        checkpoint_generation=3,
        predecessor_checkpoint_digest=checkpoint_digest,
        active_release_digest=old_release,
        active_epoch=1,
        active_sequence=1,
        production_revocation_evidence=[
            [receipt_digest, production_checkpoint_digest],
            [rollback_receipt_digest, rollback_production_checkpoint_digest],
        ],
    )
    rollback_checkpoint_value.pop("checkpoint_digest")
    rollback_checkpoint_value.pop("signature")
    rollback_checkpoint = _artifact(
        "AcceptanceCurrentCheckpoint", **rollback_checkpoint_value
    )
    rollback_checkpoint_digest = json.loads(rollback_checkpoint)["checkpoint_digest"]
    rollback_value = json.loads(second)
    rollback_value.update(
        transaction_sequence=3,
        predecessor_commit_digest=second_digest,
        active_release_digest=old_release,
        active_release_epoch=1,
        active_release_sequence=1,
        current_checkpoint_digest=rollback_checkpoint_digest,
        approval_release_digest=old_release,
        production_revocation_evidence=[
            [receipt_digest, production_checkpoint_digest],
            [rollback_receipt_digest, rollback_production_checkpoint_digest],
        ],
    )
    rollback_value.pop("commit_digest")
    rollback_commit = _artifact("AcceptanceAuthorityCommit", **rollback_value)
    with pytest.raises(
        AuthorityRepositoryUnavailable, match="active_release_transition"
    ):
        repo.compare_and_publish(
            prepared_objects={
                rollback_receipt_digest: rollback_receipt,
                rollback_production_checkpoint_digest: rollback_production_checkpoint,
                rollback_checkpoint_digest: rollback_checkpoint,
            },
            expected_commit_digest=second_digest,
            expected_key_head=first_value["key_history_head_digest"],
            expected_status_generation=2,
            next_commit=rollback_commit,
        )
    assert repo.load_current()[1] == second_digest

    def invalid_follow_up(pairs: list[list[str]]) -> bytes:
        value = json.loads(second)
        value.update(
            transaction_sequence=3,
            predecessor_commit_digest=second_digest,
            active_release_digest="f" * 64,
            active_release_epoch=3,
            active_release_sequence=3,
            production_revocation_evidence=pairs,
        )
        value.pop("commit_digest")
        return _artifact("AcceptanceAuthorityCommit", **value)

    original_pair = [receipt_digest, production_checkpoint_digest]
    for invalid_pairs in (
        [
            original_pair,
            ["e" * 64, "f" * 64],
            ["1" * 64, "2" * 64],
        ],  # more than one append
        [["e" * 64, "f" * 64], original_pair],  # reordered history
        [["e" * 64, "f" * 64]],  # substituted prefix
    ):
        with pytest.raises(AuthorityRepositoryUnavailable, match="revocation_transition"):
            repo.compare_and_publish(
                prepared_objects={},
                expected_commit_digest=second_digest,
                expected_key_head=first_value["key_history_head_digest"],
                expected_status_generation=2,
                next_commit=invalid_follow_up(invalid_pairs),
            )
    # Prepared and staged transition checks validate current production bytes,
    # including the rejected rollback. Reopen invokes the verifier again.
    assert verifier.calls == 9
    repo.load_current()
    assert verifier.calls == 10


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


@pytest.mark.parametrize("corrupt", [b"{", b'{"authorization":"not-base64"}'])
def test_truncated_or_malformed_attempt_envelope_fails_closed(
    tmp_path: Path, corrupt: bytes
) -> None:
    store = AtomicEvaluationReceiptStore(tmp_path / "receipts")
    attempt = "d" * 64
    directory = tmp_path / "receipts" / "attempts"
    directory.mkdir(parents=True)
    (directory / attempt).write_bytes(corrupt)
    with pytest.raises(AuthorityRepositoryUnavailable, match="attempt_schema"):
        store.load_attempt(attempt)
    # A corrupt durable attempt cannot be replaced to manufacture a second
    # authorization/receipt identity.
    raw = _artifact("AcceptanceEvaluationReceipt")
    with pytest.raises(AuthorityRepositoryUnavailable, match="attempt_conflict"):
        store.prepare_attempt(attempt, _json_authorization(), raw)


def test_conflicting_attempt_envelope_rejects_second_authorization_bytes(tmp_path: Path) -> None:
    store = AtomicEvaluationReceiptStore(tmp_path / "receipts")
    raw = _artifact("AcceptanceEvaluationReceipt")
    attempt = "e" * 64
    first = _json_authorization()
    assert store.prepare_attempt(attempt, first, raw) == (first, raw)
    with pytest.raises(AuthorityRepositoryUnavailable, match="attempt_conflict"):
        store.prepare_attempt(attempt, b'{"authorization_digest":"b"}', raw)


def _json_authorization() -> bytes:
    return b'{"authorization_digest":"' + (b"a" * 64) + b'"}'


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

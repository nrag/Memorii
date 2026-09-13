"""Protected fenced persistence for acceptance authority state."""

from __future__ import annotations

import fcntl
import base64
import json
import os
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from acceptance.production_revocation import (
    ProductionRevocationEvidenceError,
    ProductionRevocationEvidenceVerifier,
)
from acceptance.schema_registry import decode_artifact, schema_for, signing_preimage


class AuthorityRepositoryUnavailable(ValueError):
    """Authority durable state is not safe to use."""


def _digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _not_link(path: Path, failure: str) -> None:
    if path.is_symlink():
        raise AuthorityRepositoryUnavailable(failure)


def repository_identity(root: Path) -> str:
    """Stable coordinate bound by the protected fence registration."""
    return _digest(str(root.resolve()).encode("utf-8"))


def _publish_absent(path: Path, raw: bytes, failure: str) -> None:
    """Fsync a temp file and hard-link it into place, never exposing partial bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _not_link(path.parent, failure)
    tmp = path.parent / f".{path.name}.{os.getpid()}.{os.urandom(8).hex()}.tmp"
    try:
        with tmp.open("xb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        try:
            os.link(tmp, path)
            _fsync_dir(path.parent)
        except FileExistsError as exc:
            try:
                _not_link(path, failure)
                if path.read_bytes() != raw:
                    raise AuthorityRepositoryUnavailable(failure) from exc
            except OSError as read_exc:
                raise AuthorityRepositoryUnavailable(failure) from read_exc
    finally:
        tmp.unlink(missing_ok=True)


@dataclass(frozen=True)
class AcceptanceFenceRegistration:
    namespace: str
    backend_id: str
    backend_kind: str
    failure_domain: str
    repository_id: str
    credential_reference: str
    signer_coordinate: str
    signature: str

    def __post_init__(self) -> None:
        if self.backend_kind != "sqlite" or not all(
            isinstance(x, str) and x for x in self.__dict__.values()
        ):
            raise AuthorityRepositoryUnavailable("acceptance_fence_registration")

    def body(self) -> bytes:
        return _json(
            {
                "backend_id": self.backend_id,
                "backend_kind": self.backend_kind,
                "credential_reference": self.credential_reference,
                "failure_domain": self.failure_domain,
                "namespace": self.namespace,
                "repository_id": self.repository_id,
                "signer_coordinate": self.signer_coordinate,
            }
        )

    def identity(self) -> dict[str, str]:
        return json.loads(self.body())

    @property
    def digest(self) -> str:
        return _digest(self.body())


_REGISTRATION = object()
_SNAPSHOT = object()


class AcceptanceEvaluationSnapshot:
    """Opaque capability whose lifetime is the repository transaction lease."""

    __slots__ = ("_commit_digest", "_checkpoint_digest", "_evaluated_at")

    def __init__(
        self,
        commit: str,
        checkpoint: str,
        evaluated: datetime,
        marker: object | None = None,
    ) -> None:
        if marker is not _SNAPSHOT:
            raise AuthorityRepositoryUnavailable("acceptance_snapshot_constructor")
        self._commit_digest, self._checkpoint_digest, self._evaluated_at = (
            commit,
            checkpoint,
            evaluated,
        )

    @property
    def commit_digest(self) -> str:
        return self._commit_digest

    @property
    def checkpoint_digest(self) -> str:
        return self._checkpoint_digest

    @property
    def evaluated_at(self) -> datetime:
        return self._evaluated_at


class SqliteAcceptanceAuthorityFence:
    """Registration-bound, append-only fence with a complete record chain."""

    def __init__(
        self,
        path: Path,
        registration: AcceptanceFenceRegistration | None,
        registration_verifier: Callable[[bytes, str, str], bool] | None,
    ) -> None:
        if path.is_symlink() or registration is None or registration_verifier is None:
            raise AuthorityRepositoryUnavailable("acceptance_fence_registration")
        try:
            valid = registration_verifier(
                registration.body(),
                registration.signer_coordinate,
                registration.signature,
            )
        except (TypeError, ValueError) as exc:
            raise AuthorityRepositoryUnavailable(
                "acceptance_fence_registration"
            ) from exc
        if valid is not True:
            raise AuthorityRepositoryUnavailable("acceptance_fence_registration")
        self._path, self._registration = path, registration

    @property
    def registration(self) -> AcceptanceFenceRegistration:
        return self._registration

    @property
    def path(self) -> Path:
        return self._path

    def _record(self, seq: int, commit: str, predecessor: str | None) -> str:
        return _digest(
            _json(
                {
                    **self.registration.identity(),
                    "sequence": seq,
                    "commit_digest": commit,
                    "predecessor_fence_digest": predecessor,
                }
            )
        )

    def _connect(self) -> sqlite3.Connection:
        if self._path.is_symlink():
            raise AuthorityRepositoryUnavailable("acceptance_fence_symlink")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        db: sqlite3.Connection | None = None
        try:
            db = sqlite3.connect(self._path, isolation_level=None)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS acceptance_fence_metadata (identity_json TEXT PRIMARY KEY, registration_digest TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS acceptance_fence (sequence INTEGER PRIMARY KEY, namespace TEXT NOT NULL, backend_id TEXT NOT NULL, backend_kind TEXT NOT NULL, failure_domain TEXT NOT NULL, repository_id TEXT NOT NULL, credential_reference TEXT NOT NULL, signer_coordinate TEXT NOT NULL, commit_digest TEXT NOT NULL UNIQUE, predecessor_fence_digest TEXT, record_digest TEXT NOT NULL UNIQUE)"
            )
            identity = _json(self.registration.identity()).decode("ascii")
            rows = db.execute(
                "SELECT identity_json, registration_digest FROM acceptance_fence_metadata"
            ).fetchall()
            if not rows:
                db.execute(
                    "INSERT INTO acceptance_fence_metadata VALUES (?,?)",
                    (identity, self.registration.digest),
                )
            elif len(rows) != 1 or rows[0] != (identity, self.registration.digest):
                raise AuthorityRepositoryUnavailable(
                    "acceptance_fence_registration_mismatch"
                )
            return db
        except AuthorityRepositoryUnavailable:
            if db is not None:
                db.close()
            raise
        except sqlite3.Error as exc:
            if db is not None:
                db.close()
            raise AuthorityRepositoryUnavailable("acceptance_fence") from exc

    def _rows(self, db: sqlite3.Connection) -> list[tuple[int, str, str]]:
        rows = db.execute(
            "SELECT sequence,namespace,backend_id,backend_kind,failure_domain,repository_id,credential_reference,signer_coordinate,commit_digest,predecessor_fence_digest,record_digest FROM acceptance_fence ORDER BY sequence"
        ).fetchall()
        prior = None
        answer = []
        identity = {key: value for key, value in self.registration.identity().items()}
        for row in rows:
            seq, *rest = row
            (
                namespace,
                backend_id,
                backend_kind,
                failure_domain,
                repository_id,
                credential_reference,
                signer_coordinate,
                commit,
                predecessor,
                record,
            ) = rest
            if seq != (1 if prior is None else prior[0] + 1):
                raise AuthorityRepositoryUnavailable("acceptance_fence_gap")
            if {
                "namespace": namespace,
                "backend_id": backend_id,
                "backend_kind": backend_kind,
                "failure_domain": failure_domain,
                "repository_id": repository_id,
                "credential_reference": credential_reference,
                "signer_coordinate": signer_coordinate,
            } != identity:
                raise AuthorityRepositoryUnavailable("acceptance_fence_identity")
            expected = None if prior is None else prior[2]
            if predecessor != expected or record != self._record(
                seq, commit, predecessor
            ):
                raise AuthorityRepositoryUnavailable("acceptance_fence_chain")
            prior = (seq, commit, record)
            answer.append(prior)
        return answer

    def current(self) -> tuple[int, str] | None:
        db = self._connect()
        try:
            rows = self._rows(db)
        finally:
            db.close()
        return None if not rows else rows[-1][:2]

    def compare_and_advance(
        self, *, sequence: int, digest: str, expected: tuple[int, str] | None
    ) -> None:
        if sequence < 1 or not _is_digest(digest):
            raise AuthorityRepositoryUnavailable("acceptance_fence_coordinate")
        db = self._connect()
        try:
            try:
                db.execute("BEGIN IMMEDIATE")
                rows = self._rows(db)
                current = None if not rows else rows[-1][:2]
                if current == (sequence, digest):
                    db.execute("COMMIT")
                    return
                if current != expected or sequence != (
                    1 if current is None else current[0] + 1
                ):
                    raise AuthorityRepositoryUnavailable("acceptance_fence_cas")
                predecessor = None if not rows else rows[-1][2]
                i = self.registration.identity()
                db.execute(
                    "INSERT INTO acceptance_fence VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        sequence,
                        i["namespace"],
                        i["backend_id"],
                        i["backend_kind"],
                        i["failure_domain"],
                        i["repository_id"],
                        i["credential_reference"],
                        i["signer_coordinate"],
                        digest,
                        predecessor,
                        self._record(sequence, digest, predecessor),
                    ),
                )
                db.execute("COMMIT")
            except AuthorityRepositoryUnavailable:
                raise
            except sqlite3.Error as exc:
                raise AuthorityRepositoryUnavailable("acceptance_fence") from exc
        finally:
            db.close()


class AcceptanceAuthorityRepository:
    def __init__(
        self,
        root: Path,
        fence: SqliteAcceptanceAuthorityFence,
        *,
        maximum_object_bytes: int = 1_048_576,
        artifact_signature_verifier: Callable[[str, bytes, str, str], bool] | None = None,
        production_revocation_verifier: ProductionRevocationEvidenceVerifier | None = None,
    ) -> None:
        if (
            maximum_object_bytes < 1
            or root.is_symlink()
            or root.resolve() == fence.path.resolve()
            or root.resolve() in fence.path.resolve().parents
            or root.resolve() == fence.path.parent.resolve()
            or fence.registration.repository_id != repository_identity(root)
            or fence.registration.failure_domain
            == f"repository-recovery:{repository_identity(root)}"
        ):
            raise AuthorityRepositoryUnavailable("acceptance_fence_failure_domain")
        self._root, self._fence, self._maximum_object_bytes = (
            root,
            fence,
            maximum_object_bytes,
        )
        self._objects = root / "objects"
        self._index = root / "current.json"
        self._lease_path = root / ".transaction.lock"
        # Test-only repositories may omit this verifier while constructing their
        # synthetic unsigned fixtures. Installed composition always supplies it.
        self._artifact_signature_verifier = artifact_signature_verifier
        self._production_revocation_verifier = production_revocation_verifier

    @contextmanager
    def _lease(self) -> Iterator[None]:
        self._root.mkdir(parents=True, exist_ok=True)
        _not_link(self._root, "acceptance_repository_symlink")
        with self._lease_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def put(self, raw: bytes) -> str:
        """Untyped persistence is forbidden for authority state."""
        raise AuthorityRepositoryUnavailable("acceptance_object_schema")

    def put_typed(self, raw: bytes, schema: str) -> str:
        if (
            not isinstance(raw, bytes)
            or not raw
            or len(raw) > self._maximum_object_bytes
        ):
            raise AuthorityRepositoryUnavailable("acceptance_object_bytes")
        try:
            value = decode_artifact(raw, schema)
        except ValueError as exc:
            raise AuthorityRepositoryUnavailable("acceptance_object_schema") from exc
        digest = value[schema_for(schema)["digest_field"]]
        _publish_absent(self._objects / digest, raw, "acceptance_object_conflict")
        return digest

    def get(self, digest: str) -> bytes:
        if not _is_digest(digest):
            raise AuthorityRepositoryUnavailable("acceptance_object_coordinate")
        try:
            path = self._objects / digest
            _not_link(path, "acceptance_object_symlink")
            raw = path.read_bytes()
        except OSError as exc:
            raise AuthorityRepositoryUnavailable("acceptance_object_missing") from exc
        if not raw or len(raw) > self._maximum_object_bytes:
            raise AuthorityRepositoryUnavailable("acceptance_object_digest")
        return raw

    def _artifact(self, digest: str, schema: str) -> dict[str, Any]:
        try:
            value = decode_artifact(self.get(digest), schema)
        except (AuthorityRepositoryUnavailable, ValueError) as exc:
            raise AuthorityRepositoryUnavailable("acceptance_artifact_schema") from exc
        if value[schema_for(schema)["digest_field"]] != digest:
            raise AuthorityRepositoryUnavailable("acceptance_artifact_digest")
        registered = schema_for(schema)
        verifier = self._artifact_signature_verifier
        if (
            registered["signature_field"] is not None
            and verifier is not None
            and not (
                self._production_revocation_verifier is not None
                and schema in {"ProductionRevocationReceipt", "ProductionEpochCheckpoint"}
            )
        ):
            signature = value[registered["signature_field"]]
            coordinate = value[registered["signer_coordinate_field"]]
            try:
                valid = verifier(schema, signing_preimage(schema, value, coordinate), coordinate, signature)
            except (TypeError, ValueError) as exc:
                raise AuthorityRepositoryUnavailable("acceptance_artifact_signature") from exc
            if valid is not True:
                raise AuthorityRepositoryUnavailable("acceptance_artifact_signature")
        return value

    def _commit(self, digest: str) -> dict[str, Any]:
        commit = self._artifact(digest, "AcceptanceAuthorityCommit")
        return commit

    def _time(self, value: str, failure: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise AuthorityRepositoryUnavailable(failure) from exc
        if parsed.utcoffset() is None:
            raise AuthorityRepositoryUnavailable(failure)
        return parsed.astimezone(UTC)

    def _walk_trust(self, digest: str, expected: int, seen: set[str]) -> dict[str, Any]:
        if digest in seen:
            raise AuthorityRepositoryUnavailable("acceptance_trust_fork")
        seen.add(digest)
        trust = self._artifact(digest, "AcceptanceTrustSnapshot")
        if trust["snapshot_sequence"] != expected:
            raise AuthorityRepositoryUnavailable("acceptance_trust_sequence")
        predecessor = trust["predecessor_snapshot_digest"]
        if expected == 1:
            if predecessor is not None:
                raise AuthorityRepositoryUnavailable("acceptance_trust_predecessor")
        elif predecessor is None:
            raise AuthorityRepositoryUnavailable("acceptance_trust_predecessor")
        else:
            prior = self._walk_trust(predecessor, expected - 1, seen)
            if self._time(prior["issued_at"], "acceptance_trust_time") > self._time(
                trust["issued_at"], "acceptance_trust_time"
            ):
                raise AuthorityRepositoryUnavailable("acceptance_trust_time")
        return trust

    def _walk_key(self, digest: str, expected: int, seen: set[str]) -> dict[str, Any]:
        if digest in seen:
            raise AuthorityRepositoryUnavailable("acceptance_key_fork")
        seen.add(digest)
        event = self._artifact(digest, "KeyLifecycleEvent")
        if event["global_sequence"] != expected:
            raise AuthorityRepositoryUnavailable("acceptance_key_sequence")
        predecessor = event["predecessor_event_digest"]
        if expected == 1:
            if predecessor is not None:
                raise AuthorityRepositoryUnavailable("acceptance_key_predecessor")
        elif predecessor is None:
            raise AuthorityRepositoryUnavailable("acceptance_key_predecessor")
        else:
            prior = self._walk_key(predecessor, expected - 1, seen)
            if self._time(prior["effective_at"], "acceptance_key_time") > self._time(
                event["effective_at"], "acceptance_key_time"
            ):
                raise AuthorityRepositoryUnavailable("acceptance_key_time")
        return event

    def _walk_checkpoint(self, digest: str, seen: set[str]) -> dict[str, Any]:
        if digest in seen:
            raise AuthorityRepositoryUnavailable("acceptance_checkpoint_fork")
        seen.add(digest)
        checkpoint = self._artifact(digest, "AcceptanceCurrentCheckpoint")
        predecessor = checkpoint["predecessor_checkpoint_digest"]
        generation = checkpoint["checkpoint_generation"]
        if generation == 1:
            if predecessor is not None:
                raise AuthorityRepositoryUnavailable(
                    "acceptance_checkpoint_predecessor"
                )
        elif predecessor is None:
            raise AuthorityRepositoryUnavailable("acceptance_checkpoint_predecessor")
        else:
            prior = self._walk_checkpoint(predecessor, seen)
            if prior["checkpoint_generation"] != generation - 1 or self._time(
                prior["observed_at"], "acceptance_checkpoint_time"
            ) > self._time(checkpoint["observed_at"], "acceptance_checkpoint_time"):
                raise AuthorityRepositoryUnavailable("acceptance_checkpoint_history")
        return checkpoint

    def _walk_production_checkpoint(
        self, digest: str, seen: set[str]
    ) -> dict[str, Any]:
        if digest in seen:
            raise AuthorityRepositoryUnavailable(
                "acceptance_production_checkpoint_fork"
            )
        seen.add(digest)
        checkpoint = self._artifact(digest, "ProductionEpochCheckpoint")
        predecessor = checkpoint["predecessor_checkpoint_digest"]
        generation = checkpoint["checkpoint_generation"]
        if generation == 1:
            if predecessor is not None:
                raise AuthorityRepositoryUnavailable(
                    "acceptance_production_checkpoint_predecessor"
                )
        elif predecessor is None:
            raise AuthorityRepositoryUnavailable(
                "acceptance_production_checkpoint_predecessor"
            )
        else:
            prior = self._walk_production_checkpoint(predecessor, seen)
            if (
                prior["checkpoint_generation"] != generation - 1
                or prior["active_production_epoch"]
                > checkpoint["active_production_epoch"]
                or self._time(
                    prior["observed_at"], "acceptance_production_checkpoint_time"
                )
                > self._time(
                    checkpoint["observed_at"], "acceptance_production_checkpoint_time"
                )
            ):
                raise AuthorityRepositoryUnavailable(
                    "acceptance_production_checkpoint_history"
                )
        return checkpoint

    def _validate_commit(
        self, digest: str, sequence: int, seen: set[str] | None = None
    ) -> dict[str, Any]:
        seen = set() if seen is None else seen
        if digest in seen:
            raise AuthorityRepositoryUnavailable("acceptance_commit_fork")
        seen.add(digest)
        c = self._commit(digest)
        if c["transaction_sequence"] != sequence:
            raise AuthorityRepositoryUnavailable("acceptance_commit_sequence")
        p = c["predecessor_commit_digest"]
        predecessor_commit: dict[str, Any] | None = None
        if sequence == 1:
            if p is not None:
                raise AuthorityRepositoryUnavailable("acceptance_genesis_predecessor")
        elif not _is_digest(p):
            raise AuthorityRepositoryUnavailable("acceptance_commit_predecessor")
        else:
            predecessor_commit = self._validate_commit(p, sequence - 1, seen)
        trust_seed = self._artifact(
            c["authority_snapshot_digest"], "AcceptanceTrustSnapshot"
        )
        trust = self._walk_trust(
            c["authority_snapshot_digest"], trust_seed["snapshot_sequence"], set()
        )
        key = self._walk_key(
            c["key_history_head_digest"], c["key_history_head_sequence"], set()
        )
        checkpoint = self._walk_checkpoint(c["current_checkpoint_digest"], set())
        if (
            trust["snapshot_digest"] != c["authority_snapshot_digest"]
            or key["global_sequence"] != c["key_history_head_sequence"]
            or key["issuance_trust_snapshot_digest"] != c["authority_snapshot_digest"]
        ):
            raise AuthorityRepositoryUnavailable("acceptance_history_join")
        if (
            checkpoint["authority_snapshot_digest"],
            checkpoint["key_history_head_digest"],
            checkpoint["key_history_head_sequence"],
            checkpoint["release_history_head_digest"],
            checkpoint["release_history_head_sequence"],
        ) != (
            c["authority_snapshot_digest"],
            c["key_history_head_digest"],
            c["key_history_head_sequence"],
            c["release_history_head_digest"],
            c["release_history_head_sequence"],
        ):
            raise AuthorityRepositoryUnavailable("acceptance_checkpoint_join")
        if (
            checkpoint["active_release_digest"],
            checkpoint["active_epoch"],
            checkpoint["active_sequence"],
        ) != (
            c["active_release_digest"],
            c["active_release_epoch"],
            c["active_release_sequence"],
        ):
            raise AuthorityRepositoryUnavailable("acceptance_active_release_join")
        release = self._walk_release(
            c["release_history_head_digest"], c["release_history_head_sequence"], set()
        )
        if release["release_digest"] != c["release_history_head_digest"]:
            raise AuthorityRepositoryUnavailable("acceptance_release_history")
        active = c["active_release_digest"]
        if active is not None:
            active_release = self._artifact(active, "CapabilityBaselineApprovalRelease")
            if (
                active_release["release_digest"] != active
                or active_release["acceptance_release_epoch"] != c["active_release_epoch"]
                or active_release["acceptance_release_sequence"] != c["active_release_sequence"]
            ):
                raise AuthorityRepositoryUnavailable("acceptance_active_release_history")
        if c["issuance_snapshot_digest"] is not None:
            issued = self._artifact(
                c["issuance_snapshot_digest"], "AcceptanceApprovalIssuanceSnapshot"
            )
            issuance_release = self._artifact(
                c["approval_release_digest"], "CapabilityBaselineApprovalRelease"
            )
            if (
                issued["trust_snapshot_digest"] != c["authority_snapshot_digest"]
                or issued["key_history_head_digest"] != c["key_history_head_digest"]
                or issued["key_history_head_sequence"] != c["key_history_head_sequence"]
                or issuance_release["release_digest"] != c["approval_release_digest"]
            ):
                raise AuthorityRepositoryUnavailable("acceptance_issuance_join")
            if (
                issued["key_event_digests"][-1] != c["key_history_head_digest"]
                or issued["signing_key_coordinate"] != key["signing_key_coordinate"]
            ):
                raise AuthorityRepositoryUnavailable("acceptance_issuance_history")
        if checkpoint["production_revocation_evidence"] != c["production_revocation_evidence"]:
            raise AuthorityRepositoryUnavailable("acceptance_revocation_evidence_exact")
        for pair in c["production_revocation_evidence"]:
            rec = self._artifact(pair[0], "ProductionRevocationReceipt")
            epoch = self._artifact(pair[1], "ProductionEpochCheckpoint")
            self._walk_production_checkpoint(pair[1], set())
            if (
                rec["receipt_digest"] != pair[0]
                or pair[0] not in epoch["revocation_receipt_digests"]
                or pair not in checkpoint["production_revocation_evidence"]
                or rec["advanced_production_epoch"] <= rec["prior_production_epoch"]
                or self._time(
                    rec["withdrawal_requested_at"], "acceptance_revocation_time"
                )
                > self._time(rec["completed_at"], "acceptance_revocation_time")
                or rec["advanced_production_epoch"] > epoch["active_production_epoch"]
            ):
                raise AuthorityRepositoryUnavailable("acceptance_revocation_join")
            if self._production_revocation_verifier is not None:
                try:
                    self._production_revocation_verifier.verify(
                        prior_approval_release_digest=rec["prior_approval_release_digest"],
                        receipt=self.get(pair[0]),
                        checkpoint=self.get(pair[1]),
                        require_current_reader_bytes=True,
                    )
                except ProductionRevocationEvidenceError as exc:
                    raise AuthorityRepositoryUnavailable(
                        "acceptance_production_revocation_evidence"
                    ) from exc
        self._validate_revocation_transition(predecessor_commit, c)
        return c

    def _validate_revocation_transition(
        self, predecessor: dict[str, Any] | None, proposed: dict[str, Any]
    ) -> None:
        """Bind append-only evidence to exactly one active-release terminal transition."""
        pairs = proposed["production_revocation_evidence"]
        if predecessor is None:
            if pairs:
                raise AuthorityRepositoryUnavailable("acceptance_revocation_genesis")
            return
        prior_pairs = predecessor["production_revocation_evidence"]
        old_active = predecessor["active_release_digest"]
        new_active = proposed["active_release_digest"]
        if new_active == old_active:
            if pairs != prior_pairs:
                raise AuthorityRepositoryUnavailable("acceptance_revocation_unexpected")
            return
        if old_active is None:
            raise AuthorityRepositoryUnavailable("acceptance_revocation_transition")
        if pairs[: len(prior_pairs)] != prior_pairs or len(pairs) != len(prior_pairs) + 1:
            raise AuthorityRepositoryUnavailable("acceptance_revocation_transition")
        receipt = self._artifact(pairs[-1][0], "ProductionRevocationReceipt")
        if receipt["prior_approval_release_digest"] != old_active:
            raise AuthorityRepositoryUnavailable("acceptance_revocation_prior_release")

    def _walk_release(self, digest: str, expected: int, seen: set[str]) -> dict[str, Any]:
        """Verify the complete release predecessor chain selected by the commit."""
        if digest in seen:
            raise AuthorityRepositoryUnavailable("acceptance_release_fork")
        seen.add(digest)
        release = self._artifact(digest, "CapabilityBaselineApprovalRelease")
        if release["acceptance_release_sequence"] != expected:
            raise AuthorityRepositoryUnavailable("acceptance_release_sequence")
        predecessor = release["supersedes_release_digest"]
        if expected == 1:
            if predecessor is not None:
                raise AuthorityRepositoryUnavailable("acceptance_release_predecessor")
        elif predecessor is None:
            raise AuthorityRepositoryUnavailable("acceptance_release_predecessor")
        else:
            prior = self._walk_release(predecessor, expected - 1, seen)
            if self._time(prior["issued_at"], "acceptance_release_time") > self._time(
                release["issued_at"], "acceptance_release_time"
            ):
                raise AuthorityRepositoryUnavailable("acceptance_release_time")
        return release

    def _repair(self, seq: int, digest: str, checkpoint: str) -> None:
        expected = _json(
            {"checkpoint_digest": checkpoint, "digest": digest, "sequence": seq}
        )
        try:
            _not_link(self._index, "acceptance_index_symlink")
            existing = self._index.read_bytes()
        except FileNotFoundError:
            existing = None
        if existing != expected:
            tmp = (
                self._index.parent
                / f".{self._index.name}.{os.getpid()}.{os.urandom(8).hex()}.tmp"
            )
            with tmp.open("xb") as out:
                out.write(expected)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, self._index)
            _fsync_dir(self._index.parent)
        else:
            # A previous successful replace can have lost its acknowledgement
            # before the directory entry reached durable storage.
            _fsync_dir(self._index.parent)

    def _current(self) -> tuple[int, str, dict[str, Any]] | None:
        fence = self._fence.current()
        if fence is None:
            if self._index.exists():
                raise AuthorityRepositoryUnavailable("acceptance_index_without_fence")
            return None
        commit = self._validate_commit(fence[1], fence[0])
        self._repair(fence[0], fence[1], commit["current_checkpoint_digest"])
        return fence[0], fence[1], commit

    def load_current(self) -> tuple[int, str, Mapping[str, Any]]:
        with self._lease():
            current = self._current()
            if current is None:
                raise AuthorityRepositoryUnavailable("acceptance_empty")
            return current[0], current[1], dict(current[2])

    def selected_evaluation_artifacts(
        self, snapshot: AcceptanceEvaluationSnapshot
    ) -> Mapping[str, Any]:
        """Read only the commit selected by a currently-held evaluation lease."""
        if not isinstance(snapshot, AcceptanceEvaluationSnapshot):
            raise AuthorityRepositoryUnavailable("acceptance_snapshot_type")
        current = self._current()
        if current is None or current[1] != snapshot.commit_digest:
            raise AuthorityRepositoryUnavailable("acceptance_snapshot_stale")
        commit = current[2]
        checkpoint = self._artifact(snapshot.checkpoint_digest, "AcceptanceCurrentCheckpoint")
        if checkpoint["checkpoint_digest"] != commit["current_checkpoint_digest"]:
            raise AuthorityRepositoryUnavailable("acceptance_snapshot_checkpoint")

        def prefix(head: str, schema: str, previous: str) -> list[dict[str, Any]]:
            values: list[dict[str, Any]] = []
            seen: set[str] = set()
            cursor: str | None = head
            while cursor is not None:
                if cursor in seen:
                    raise AuthorityRepositoryUnavailable("acceptance_snapshot_history")
                seen.add(cursor)
                value = self._artifact(cursor, schema)
                values.append(value)
                cursor = value[previous]
            values.reverse()
            return values

        issuance = commit["issuance_snapshot_digest"]
        if issuance is None or commit["approval_release_digest"] is None:
            raise AuthorityRepositoryUnavailable("acceptance_snapshot_issuance")
        return {
            "commit": dict(commit),
            "trust": self._artifact(commit["authority_snapshot_digest"], "AcceptanceTrustSnapshot"),
            "checkpoint": checkpoint,
            "issuance": self._artifact(issuance, "AcceptanceApprovalIssuanceSnapshot"),
            "keys": prefix(commit["key_history_head_digest"], "KeyLifecycleEvent", "predecessor_event_digest"),
            "releases": prefix(commit["release_history_head_digest"], "CapabilityBaselineApprovalRelease", "supersedes_release_digest"),
        }

    def compare_and_publish(
        self,
        *,
        prepared_objects: Mapping[str, bytes],
        expected_commit_digest: str | None,
        expected_key_head: str | None,
        expected_status_generation: int | None,
        next_commit: bytes,
    ) -> str:
        try:
            commit = decode_artifact(next_commit, "AcceptanceAuthorityCommit")
        except ValueError as exc:
            raise AuthorityRepositoryUnavailable("acceptance_commit_schema") from exc
        digest = commit["commit_digest"]
        with self._lease():
            current = self._current()
            current_digest = None if current is None else current[1]
            if current_digest != expected_commit_digest:
                raise AuthorityRepositoryUnavailable("acceptance_commit_cas")
            if current is None:
                if (
                    expected_key_head is not None
                    or expected_status_generation is not None
                ):
                    raise AuthorityRepositoryUnavailable("acceptance_genesis_cas")
            elif (
                current[2]["key_history_head_digest"] != expected_key_head
                or current[2]["release_history_head_sequence"]
                != expected_status_generation
            ):
                raise AuthorityRepositoryUnavailable("acceptance_head_cas")
            expected = 1 if current is None else current[0] + 1
            if (
                commit["transaction_sequence"] != expected
                or commit["predecessor_commit_digest"] != current_digest
            ):
                raise AuthorityRepositoryUnavailable("acceptance_next_commit")
            self._validate_prepared_revocation_transition(
                None if current is None else current[2], commit, prepared_objects
            )
            reachable = {
                commit["authority_snapshot_digest"],
                commit["key_history_head_digest"],
                commit["release_history_head_digest"],
                commit["current_checkpoint_digest"],
            }
            for name in ("issuance_snapshot_digest", "approval_release_digest"):
                if commit[name] is not None:
                    reachable.add(commit[name])
            for receipt_digest, checkpoint_digest in commit[
                "production_revocation_evidence"
            ]:
                reachable.update((receipt_digest, checkpoint_digest))
            for prepared_digest, raw in prepared_objects.items():
                if prepared_digest not in reachable:
                    raise AuthorityRepositoryUnavailable(
                        "acceptance_prepared_unreachable"
                    )
                schema = self._schema_from_raw(raw)
                if (
                    not _is_digest(prepared_digest)
                    or self.put_typed(raw, schema) != prepared_digest
                ):
                    raise AuthorityRepositoryUnavailable("acceptance_prepared_digest")
            self.put_typed(next_commit, "AcceptanceAuthorityCommit")
            self._validate_commit(digest, expected)
            self._fence.compare_and_advance(
                sequence=expected,
                digest=digest,
                expected=None if current is None else (current[0], current[1]),
            )
            # The fence is the commit point.  Repairing the advisory index only
            # after it advances prevents a genesis crash from advertising an
            # unfenced head.
            self._repair(expected, digest, commit["current_checkpoint_digest"])
            return digest

    def _validate_prepared_revocation_transition(
        self,
        predecessor: dict[str, Any] | None,
        proposed: dict[str, Any],
        prepared_objects: Mapping[str, bytes],
    ) -> None:
        """Require the just-appended pair to be the reader's exact current bytes."""
        pairs = proposed["production_revocation_evidence"]
        if predecessor is None:
            if pairs:
                raise AuthorityRepositoryUnavailable("acceptance_revocation_genesis")
            return
        prior_pairs = predecessor["production_revocation_evidence"]
        old_active = predecessor["active_release_digest"]
        if proposed["active_release_digest"] == old_active:
            if pairs != prior_pairs:
                raise AuthorityRepositoryUnavailable("acceptance_revocation_unexpected")
            return
        if (
            old_active is None
            or pairs[: len(prior_pairs)] != prior_pairs
            or len(pairs) != len(prior_pairs) + 1
        ):
            raise AuthorityRepositoryUnavailable("acceptance_revocation_transition")
        receipt_digest, checkpoint_digest = pairs[-1]
        receipt = prepared_objects.get(receipt_digest)
        checkpoint = prepared_objects.get(checkpoint_digest)
        if receipt is None or checkpoint is None:
            raise AuthorityRepositoryUnavailable("acceptance_revocation_prepared")
        try:
            decoded = decode_artifact(receipt, "ProductionRevocationReceipt")
        except ValueError as exc:
            raise AuthorityRepositoryUnavailable("acceptance_revocation_prepared") from exc
        if decoded["prior_approval_release_digest"] != old_active:
            raise AuthorityRepositoryUnavailable("acceptance_revocation_prior_release")
        verifier = self._production_revocation_verifier
        if verifier is not None:
            try:
                verifier.verify(
                    prior_approval_release_digest=old_active,
                    receipt=receipt,
                    checkpoint=checkpoint,
                    require_current_reader_bytes=True,
                )
            except ProductionRevocationEvidenceError as exc:
                raise AuthorityRepositoryUnavailable(
                    "acceptance_production_revocation_evidence"
                ) from exc

    @staticmethod
    def _schema_from_raw(raw: bytes) -> str:
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AuthorityRepositoryUnavailable("acceptance_prepared_schema") from exc
        if type(value) is not dict:
            raise AuthorityRepositoryUnavailable("acceptance_prepared_schema")
        purpose = value.get("approval_purpose", value.get("purpose"))
        matches = [
            row["id"]
            for row in (
                schema_for(name)
                for name in (
                    "AcceptanceTrustSnapshot",
                    "KeyLifecycleEvent",
                    "AcceptanceApprovalIssuanceSnapshot",
                    "CapabilityBaselineApprovalRelease",
                    "AcceptanceCurrentCheckpoint",
                    "ProductionRevocationReceipt",
                    "ProductionEpochCheckpoint",
                    "AcceptanceEvaluationReceipt",
                    "AcceptanceAuthorityCommit",
                )
            )
            if row["purpose"] == purpose
        ]
        if len(matches) != 1:
            raise AuthorityRepositoryUnavailable("acceptance_prepared_schema")
        return matches[0]

    @contextmanager
    def begin_evaluation(
        self, now: datetime | Callable[[], datetime]
    ) -> Iterator[AcceptanceEvaluationSnapshot]:
        with self._lease():
            current = self._current()
            if current is None:
                raise AuthorityRepositoryUnavailable("acceptance_empty")
            evaluated = now() if callable(now) else now
            if not isinstance(evaluated, datetime) or evaluated.utcoffset() is None:
                raise AuthorityRepositoryUnavailable("acceptance_evaluation_clock")
            checkpoint = self._artifact(
                current[2]["current_checkpoint_digest"], "AcceptanceCurrentCheckpoint"
            )
            try:
                observed = datetime.fromisoformat(
                    checkpoint["observed_at"].replace("Z", "+00:00")
                )
            except (AttributeError, ValueError) as exc:
                raise AuthorityRepositoryUnavailable(
                    "acceptance_checkpoint_observed_at"
                ) from exc
            if observed.astimezone(UTC) > evaluated.astimezone(UTC):
                raise AuthorityRepositoryUnavailable("acceptance_checkpoint_future")
            yield AcceptanceEvaluationSnapshot(
                current[1],
                current[2]["current_checkpoint_digest"],
                evaluated,
                _SNAPSHOT,
            )


class AtomicEvaluationReceiptStore:
    def __init__(self, root: Path, *, maximum_receipt_bytes: int = 131_072) -> None:
        self._root, self._maximum_receipt_bytes = root, maximum_receipt_bytes

    def publish(self, digest: str, raw: bytes) -> None:
        if (
            not _is_digest(digest)
            or not isinstance(raw, bytes)
            or not raw
            or len(raw) > self._maximum_receipt_bytes
        ):
            raise AuthorityRepositoryUnavailable("acceptance_receipt_bytes")
        try:
            receipt = decode_artifact(raw, "AcceptanceEvaluationReceipt")
        except ValueError as exc:
            raise AuthorityRepositoryUnavailable("acceptance_receipt_schema") from exc
        if receipt["receipt_digest"] != digest:
            raise AuthorityRepositoryUnavailable("acceptance_receipt_digest")
        _publish_absent(self._root / digest, raw, "acceptance_receipt_conflict")

    def load_attempt(self, attempt_digest: str) -> tuple[bytes, bytes] | None:
        """Load one immutable prepared publication attempt, if any."""
        if not _is_digest(attempt_digest):
            raise AuthorityRepositoryUnavailable("acceptance_attempt_coordinate")
        path = self._root / "attempts" / attempt_digest
        try:
            _not_link(path, "acceptance_attempt_conflict")
            raw = path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise AuthorityRepositoryUnavailable("acceptance_attempt_read") from exc
        try:
            value = json.loads(raw)
            if type(value) is not dict or set(value) != {"authorization", "receipt"}:
                raise ValueError
            authorization = base64.b64decode(value["authorization"], validate=True)
            receipt = base64.b64decode(value["receipt"], validate=True)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise AuthorityRepositoryUnavailable("acceptance_attempt_schema") from exc
        try:
            decode_artifact(receipt, "AcceptanceEvaluationReceipt")
        except ValueError as exc:
            raise AuthorityRepositoryUnavailable("acceptance_attempt_receipt") from exc
        return authorization, receipt

    def prepare_attempt(
        self, attempt_digest: str, authorization: bytes, receipt: bytes
    ) -> tuple[bytes, bytes]:
        """Persist exact publication bytes before either downstream publish."""
        if not _is_digest(attempt_digest) or not isinstance(authorization, bytes):
            raise AuthorityRepositoryUnavailable("acceptance_attempt_coordinate")
        try:
            decoded = decode_artifact(receipt, "AcceptanceEvaluationReceipt")
        except ValueError as exc:
            raise AuthorityRepositoryUnavailable("acceptance_attempt_receipt") from exc
        if not authorization or decoded["deployment_authorization_digest"] not in receipt.decode("ascii"):
            raise AuthorityRepositoryUnavailable("acceptance_attempt_binding")
        value = _json(
            {
                "authorization": base64.b64encode(authorization).decode("ascii"),
                "receipt": base64.b64encode(receipt).decode("ascii"),
            }
        )
        _publish_absent(self._root / "attempts" / attempt_digest, value, "acceptance_attempt_conflict")
        loaded = self.load_attempt(attempt_digest)
        if loaded is None:
            raise AuthorityRepositoryUnavailable("acceptance_attempt_missing")
        return loaded

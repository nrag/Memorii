"""Noncryptographic issuance-prefix proof composed with the preserved verifier.

Compact symbolic digests retain the predecessor model's abstraction. This is
not a CTV, signature, or production trust-repository implementation.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "acceptance-authority-successor"))
import authority_successor_feasibility as base

Rejected = base.Rejected
SNAPSHOT_PURPOSE = "semantic_ingestion_approval_issuance_snapshot"


class CommittedIssuanceLookup(Protocol):
    def load(self, snapshot_digest: str, release_digest: str) -> bytes | None: ...


def _declared_history(history, selected_key, cutoff):
    base._key_static_validity(history["keys"], selected_key, cutoff)
    declarations = {row["key"]: row for row in history["keys"]}
    seen = set()
    for event in history["events"]:
        key, _, _, state, _ = base._event(event)
        if key not in declarations:
            raise Rejected("undeclared_event_key")
        if key in seen and state == "active":
            raise Rejected("repeated_activation")
        seen.add(key)
    return declarations


class ComposedIssuanceVerifier:
    """One protected status read, bounded immutable snapshot lookup, then lifecycle."""

    def __init__(self, status: base.ProtectedCurrentStatus, snapshots: CommittedIssuanceLookup,
                 limits: base.Limits = base.Limits()):
        self._status = status
        self._snapshots = snapshots
        self._limits = limits

    def verify(self, release_bytes: bytes, baseline_bytes: bytes, evaluation_time: int) -> str:
        release = base.bounded_object(release_bytes, self._limits)
        base._closed(release, {"digest", "key", "issued_at", "expires_at", "state",
                              "baseline_digest", "sequence", "epoch",
                              "acceptance_authority_snapshot_digest"}, "release")
        snapshot_id = base._text(release["acceptance_authority_snapshot_digest"], "snapshot_id")
        snapshot_raw = self._snapshots.load(snapshot_id, base._text(release["digest"], "release_digest"))
        if snapshot_raw is None:
            raise Rejected("issuance_snapshot_missing")
        snapshot = base.bounded_object(snapshot_raw, self._limits)
        base._closed(snapshot, {"digest", "keys", "events", "head_digest", "head_sequence",
                                "signing_key"}, "issuance_snapshot")
        if snapshot["digest"] != snapshot_id:
            raise Rejected("issuance_snapshot_binding")
        key = base._text(release["key"], "release_key")
        issued = base._timestamp(release["issued_at"], "issued_at")
        # The preserved reducer validates every event independently of its cutoff.
        base.reduce_key_history(snapshot["events"], issued, key)
        declarations = _declared_history(snapshot, key, issued)
        if snapshot["signing_key"] != key or SNAPSHOT_PURPOSE not in declarations[key]["purposes"]:
            raise Rejected("snapshot_signer_authorization")
        last_key, _, sequence, _, _ = base._event(snapshot["events"][-1])
        if (base._positive(snapshot["head_sequence"], "issuance_head_sequence") != sequence
                or snapshot["head_digest"] != f"{last_key}:{sequence}"):
            raise Rejected("issuance_head")
        history_raw, checkpoint_raw, receipt_raw = self._status.current()
        history = base.bounded_object(history_raw, self._limits)
        base._closed(history, {"keys", "events"}, "history")
        base.reduce_key_history(history["events"], evaluation_time, key)
        current_declarations = _declared_history(history, key, issued)
        if (type(history["events"]) is not list
                or history["events"][:sequence] != snapshot["events"]
                or any(current_declarations.get(name) != row for name, row in declarations.items())):
            raise Rejected("current_issuance_prefix")
        preserved_release = {name: value for name, value in release.items()
                             if name != "acceptance_authority_snapshot_digest"}
        return base._verify(
            preserved_release, base.bounded_object(baseline_bytes, self._limits), history,
            base.bounded_object(checkpoint_raw, self._limits),
            base.bounded_object(receipt_raw, self._limits),
            base.bounded_object(self._status.predecessor(), self._limits), evaluation_time,
        )


class ProtectedIssuanceRepository:
    """Detached CAS model: immutable snapshot and release publish together.

    Signing is abstract, as in the preserved model. History updates represent a
    separate trusted status writer; public acceptance callers cannot call these
    issuance methods or choose the captured history.
    """

    def __init__(self, history_bytes: bytes, limits: base.Limits = base.Limits()):
        from threading import RLock

        self._lock = RLock()
        self._history_bytes = history_bytes
        self._generation = 1
        self._limits = limits
        self._drafts: dict[int, tuple[int, bytes, bytes, bytes]] = {}
        self._published: dict[str, tuple[bytes, bytes]] = {}
        self._next_token = 1

    def prepare(self, release_bytes: bytes) -> int:
        import json

        with self._lock:
            release = base.bounded_object(release_bytes, self._limits)
            snapshot_id = base._text(release.get("acceptance_authority_snapshot_digest"), "snapshot_id")
            key = base._text(release.get("key"), "release_key")
            issued = base._timestamp(release.get("issued_at"), "issued_at")
            history = base.bounded_object(self._history_bytes, self._limits)
            base._closed(history, {"keys", "events"}, "history")
            base.reduce_key_history(history["events"], issued, key)
            declarations = _declared_history(history, key, issued)
            if SNAPSHOT_PURPOSE not in declarations[key]["purposes"]:
                raise Rejected("snapshot_signer_authorization")
            last_key, _, sequence, _, _ = base._event(history["events"][-1])
            snapshot = {
                "digest": snapshot_id, "keys": history["keys"], "events": history["events"],
                "head_digest": f"{last_key}:{sequence}", "head_sequence": sequence, "signing_key": key,
            }
            snapshot_bytes = json.dumps(snapshot, separators=(",", ":")).encode()
            base.bounded_object(snapshot_bytes, self._limits)
            token = self._next_token
            self._next_token += 1
            self._drafts[token] = (self._generation, self._history_bytes, release_bytes, snapshot_bytes)
            return token

    def advance_history(self, history_bytes: bytes) -> None:
        with self._lock:
            old = base.bounded_object(self._history_bytes, self._limits)
            new = base.bounded_object(history_bytes, self._limits)
            base._closed(new, {"keys", "events"}, "history")
            if (type(new["events"]) is not list or len(new["events"]) <= len(old["events"])
                    or new["events"][:len(old["events"])] != old["events"]):
                raise Rejected("history_append")
            self._history_bytes = history_bytes
            self._generation += 1

    def publish(self, token: int) -> tuple[bytes, bytes]:
        with self._lock:
            if token not in self._drafts:
                raise Rejected("issuance_draft")
            generation, history, release_bytes, snapshot_bytes = self._drafts[token]
            if generation != self._generation or history != self._history_bytes:
                raise Rejected("issuance_capture_stale")
            release = base.bounded_object(release_bytes, self._limits)
            snapshot_id = release["acceptance_authority_snapshot_digest"]
            pair = release_bytes, snapshot_bytes
            if snapshot_id in self._published and self._published[snapshot_id] != pair:
                raise Rejected("immutable_issuance")
            self._published[snapshot_id] = pair
            return pair

    def advance_status_generation(self) -> None:
        with self._lock:
            self._generation += 1

    def load(self, snapshot_digest: str, release_digest: str) -> bytes | None:
        with self._lock:
            pair = self._published.get(snapshot_digest)
            if pair is None:
                return None
            release = base.bounded_object(pair[0], self._limits)
            return pair[1] if release["digest"] == release_digest else None

    def published(self, snapshot_id: str) -> tuple[bytes, bytes] | None:
        with self._lock:
            return self._published.get(snapshot_id)

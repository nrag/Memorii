"""Nonproduction proof for the proposed closed acceptance authority boundary.

This model deliberately has no cryptographic implementation.  It proves the
public byte-entry, closed-shape, and chronological reduction obligations that
the future acceptance-owned verifier must retain around its real signatures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, NoReturn


class Rejected(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    maximum_bytes: int = 4096
    maximum_depth: int = 16
    maximum_nodes: int = 256
    maximum_string_bytes: int = 512
    maximum_integer_digits: int = 12


def _reject(reason: str) -> NoReturn:
    raise Rejected(reason)


def _closed(value: Any, fields: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        _reject(name + "_shape")
    return value


def _text(value: Any, name: str) -> str:
    if type(value) is not str or not value:
        _reject(name + "_text")
    return value


def _positive(value: Any, name: str) -> int:
    if type(value) is not int or value < 1:
        _reject(name + "_positive")
    return value


def _timestamp(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        _reject(name + "_timestamp")
    return value


class _Scanner:
    """Complete JSON subset accounting before the allocating general decoder."""

    def __init__(self, raw: bytes, limits: Limits):
        self.raw, self.limits, self.index, self.nodes = raw, limits, 0, 0

    def _node(self, depth: int) -> None:
        if depth > self.limits.maximum_depth:
            _reject("depth_limit")
        self.nodes += 1
        if self.nodes > self.limits.maximum_nodes:
            _reject("node_limit")
        self._ws()
        if self.index >= len(self.raw):
            _reject("syntax")
        char = self.raw[self.index]
        if char == 34:
            self._string()
            return
        if char == 123:
            self._object(depth)
            return
        if char == 91:
            self._array(depth)
            return
        if self.raw.startswith(b"true", self.index):
            self.index += 4
            return
        if self.raw.startswith(b"false", self.index):
            self.index += 5
            return
        if self.raw.startswith(b"null", self.index):
            self.index += 4
            return
        if char == 45 or 48 <= char <= 57:
            self._integer()
            return
        _reject("subset")

    def _ws(self) -> None:
        while self.index < len(self.raw) and self.raw[self.index] in b" \t\r\n":
            self.index += 1

    def _string(self) -> None:
        self.index += 1
        decoded = bytearray()
        while self.index < len(self.raw):
            char = self.raw[self.index]
            self.index += 1
            if char == 34:
                try:
                    decoded.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise Rejected("syntax") from error
                if len(decoded) > self.limits.maximum_string_bytes:
                    _reject("string_limit")
                return
            if char < 32:
                _reject("syntax")
            if char != 92:
                decoded.append(char)
                continue
            if self.index >= len(self.raw):
                _reject("syntax")
            escape = self.raw[self.index]
            self.index += 1
            simple = {
                34: b'"',
                92: b"\\",
                47: b"/",
                98: b"\b",
                102: b"\f",
                110: b"\n",
                114: b"\r",
                116: b"\t",
            }
            if escape in simple:
                decoded.extend(simple[escape])
                continue
            if escape != 117 or self.index + 4 > len(self.raw):
                _reject("syntax")
            hex_bytes = self.raw[self.index : self.index + 4]
            if any(byte not in b"0123456789abcdefABCDEF" for byte in hex_bytes):
                _reject("syntax")
            scalar = int(hex_bytes, 16)
            self.index += 4
            if 0xD800 <= scalar <= 0xDBFF:
                if self.raw[self.index : self.index + 2] != b"\\u":
                    _reject("syntax")
                low = self.raw[self.index + 2 : self.index + 6]
                if len(low) != 4 or any(
                    byte not in b"0123456789abcdefABCDEF" for byte in low
                ):
                    _reject("syntax")
                low_scalar = int(low, 16)
                if not 0xDC00 <= low_scalar <= 0xDFFF:
                    _reject("syntax")
                scalar = 0x10000 + ((scalar - 0xD800) << 10) + low_scalar - 0xDC00
                self.index += 6
            elif 0xDC00 <= scalar <= 0xDFFF:
                _reject("syntax")
            decoded.extend(chr(scalar).encode("utf-8"))
        _reject("syntax")

    def _integer(self) -> None:
        negative = self.raw[self.index] == 45
        if negative:
            self.index += 1
        start = self.index
        while self.index < len(self.raw) and 48 <= self.raw[self.index] <= 57:
            self.index += 1
        if (
            self.index == start
            or self.index - start > self.limits.maximum_integer_digits
        ):
            _reject("integer_limit")
        digits = self.raw[start : self.index]
        if (len(digits) > 1 and digits[0] == 48) or (negative and digits == b"0"):
            _reject("integer_grammar")
        if self.index < len(self.raw) and self.raw[self.index] in b".eE":
            _reject("subset")

    def _array(self, depth: int) -> None:
        self.index += 1
        self._ws()
        if self.index < len(self.raw) and self.raw[self.index] == 93:
            self.index += 1
            return
        while True:
            self._node(depth + 1)
            self._ws()
            if self.index >= len(self.raw):
                _reject("syntax")
            if self.raw[self.index] == 93:
                self.index += 1
                return
            if self.raw[self.index] != 44:
                _reject("syntax")
            self.index += 1

    def _object(self, depth: int) -> None:
        self.index += 1
        self._ws()
        if self.index < len(self.raw) and self.raw[self.index] == 125:
            self.index += 1
            return
        while True:
            self._ws()
            if self.index >= len(self.raw) or self.raw[self.index] != 34:
                _reject("syntax")
            self.nodes += 1
            if self.nodes > self.limits.maximum_nodes:
                _reject("node_limit")
            self._string()
            self._ws()
            if self.index >= len(self.raw) or self.raw[self.index] != 58:
                _reject("syntax")
            self.index += 1
            self._node(depth + 1)
            self._ws()
            if self.index >= len(self.raw):
                _reject("syntax")
            if self.raw[self.index] == 125:
                self.index += 1
                return
            if self.raw[self.index] != 44:
                _reject("syntax")
            self.index += 1


def bounded_object(raw: bytes, limits: Limits) -> dict[str, Any]:
    """The public byte boundary: every input is scanned before json.loads."""
    if type(raw) is not bytes or len(raw) > limits.maximum_bytes:
        _reject("byte_limit")
    scanner = _Scanner(raw, limits)
    scanner._node(1)
    scanner._ws()
    if scanner.index != len(raw):
        _reject("syntax")
    try:
        value = json.loads(raw, object_pairs_hook=_unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Rejected("syntax") from error
    if type(value) is not dict:
        _reject("root_shape")
    for text in _walk_strings(value):
        if len(text.encode("utf-8")) > limits.maximum_string_bytes:
            _reject("string_limit")
    return value


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _reject("duplicate_key")
        value[key] = item
    return value


def _walk_strings(value: Any):
    if type(value) is str:
        yield value
    elif type(value) is list:
        for item in value:
            yield from _walk_strings(item)
    elif type(value) is dict:
        for key, item in value.items():
            yield key
            yield from _walk_strings(item)


def _event(value: Any) -> tuple[str, int, int, str, str | None]:
    event = _closed(
        value, {"key", "state", "effective_at", "sequence", "previous"}, "key_event"
    )
    key = _text(event["key"], "key")
    state = _text(event["state"], "state")
    if state not in {"active", "retired", "revoked", "compromised"}:
        _reject("key_state")
    when = _timestamp(event["effective_at"], "effective_at")
    sequence = _positive(event["sequence"], "sequence")
    if event["previous"] is not None and type(event["previous"]) is not str:
        _reject("key_previous")
    return key, when, sequence, state, event["previous"]


def reduce_key_history(events: list[Any], issue_time: int, selected_key: str) -> str:
    """Total order is (effective_at, sequence); future events cannot authorize issue."""
    if type(events) is not list or not events:
        _reject("key_history")
    ordered = [_event(event) for event in events]
    if ordered != sorted(ordered, key=lambda item: (item[1], item[2])):
        _reject("key_order")
    all_heads: dict[str, str] = {}
    cutoff_heads: dict[str, str] = {}
    last_sequence = 0
    previous_digest: str | None = None
    for key, when, sequence_value, state, predecessor in ordered:
        if sequence_value != last_sequence + 1:
            _reject("key_sequence")
        last_sequence = sequence_value
        if predecessor != previous_digest:
            _reject("key_predecessor")
        prior = all_heads.get(key)
        if prior is None and state != "active":
            _reject("key_initial")
        if prior is not None and prior != "active":
            _reject("key_terminal")
        all_heads[key] = state
        if when <= issue_time:
            cutoff_heads[key] = state
        previous_digest = f"{key}:{sequence_value}"
    if cutoff_heads.get(selected_key) != "active":
        _reject("issue_key_not_active")
    return cutoff_heads[selected_key]


class ProtectedCurrentStatus:
    """Fixture stand-in for the protected provider; callers cannot select history."""

    def __init__(
        self,
        history_bytes: bytes,
        checkpoint_bytes: bytes,
        receipt_bytes: bytes,
        predecessor_bytes: bytes | None = None,
        predecessor_result: Any = None,
    ):
        self._history_bytes = history_bytes
        self._checkpoint_bytes = checkpoint_bytes
        self._receipt_bytes = receipt_bytes
        self._predecessor_bytes = predecessor_bytes
        self._predecessor_result = predecessor_result

    def current(self) -> tuple[bytes, bytes, bytes]:
        return self._history_bytes, self._checkpoint_bytes, self._receipt_bytes

    def predecessor(self) -> bytes:
        if self._predecessor_result is not None:
            # The protected adapter runs the preserved verifier before exposing
            # its bounded result alias to this successor boundary.
            return self._predecessor_result()
        if self._predecessor_bytes is None:
            _reject("predecessor_unavailable")
        return self._predecessor_bytes


class PublicVerifier:
    def __init__(self, status: ProtectedCurrentStatus, limits: Limits = Limits()):
        self._status = status
        self._limits = limits

    def verify(
        self, release_bytes: bytes, baseline_bytes: bytes, evaluation_time: int
    ) -> str:
        release = bounded_object(release_bytes, self._limits)
        baseline = bounded_object(baseline_bytes, self._limits)
        history_raw, checkpoint_raw, receipt_raw = self._status.current()
        history = bounded_object(history_raw, self._limits)
        checkpoint = bounded_object(checkpoint_raw, self._limits)
        receipt = bounded_object(receipt_raw, self._limits)
        predecessor = bounded_object(self._status.predecessor(), self._limits)
        return _verify(
            release,
            baseline,
            history,
            checkpoint,
            receipt,
            predecessor,
            evaluation_time,
        )


def _verify(
    release: Any,
    baseline: Any,
    history: Any,
    checkpoint: Any,
    receipt: Any,
    predecessor: Any,
    evaluation_time: int,
) -> str:
    r = _closed(
        release,
        {
            "digest",
            "key",
            "issued_at",
            "expires_at",
            "state",
            "baseline_digest",
            "sequence",
            "epoch",
        },
        "release",
    )
    b = _closed(baseline, {"digest", "capability"}, "baseline")
    h = _closed(history, {"keys", "events"}, "history")
    c = _closed(
        checkpoint,
        {
            "release_digest",
            "release_sequence",
            "key_event_count",
            "observed_at",
            "receipt_digest",
        },
        "checkpoint",
    )
    receipt = _closed(
        receipt,
        {
            "withdrawn_release_digest",
            "withdrawal_requested_at",
            "prior_production_epoch",
            "advanced_production_epoch",
            "completed_at",
            "digest",
        },
        "receipt",
    )
    predecessor = _closed(
        predecessor,
        {
            "active_release_digest",
            "active_epoch",
            "active_sequence",
            "key_head_sequence",
            "receipt_withdrawn_digest",
            "receipt_digest",
            "receipt_prior_epoch",
            "receipt_advanced_epoch",
        },
        "predecessor",
    )
    receipt_digest = _text(receipt["digest"], "receipt_digest")
    _text(receipt["withdrawn_release_digest"], "withdrawn_release_digest")
    digest = _text(r["digest"], "release_digest")
    key = _text(r["key"], "release_key")
    issued = _timestamp(r["issued_at"], "issued_at")
    expires = _timestamp(r["expires_at"], "expires_at")
    if (
        expires <= issued
        or _timestamp(evaluation_time, "evaluation_time") < issued
        or evaluation_time >= expires
    ):
        _reject("release_time")
    if (
        r["state"] != "active"
        or _positive(r["sequence"], "release_sequence")
        != _positive(c["release_sequence"], "checkpoint_sequence")
        or _text(c["release_digest"], "checkpoint_release_digest") != digest
    ):
        _reject("current_release")
    if (
        r["baseline_digest"] != _text(b["digest"], "baseline_digest")
        or type(r["epoch"]) is not int
        or r["epoch"] < 1
    ):
        _reject("baseline_binding")
    if (
        predecessor["active_release_digest"] != digest
        or _positive(predecessor["active_epoch"], "predecessor_epoch") != r["epoch"]
        or _positive(predecessor["active_sequence"], "predecessor_sequence")
        != r["sequence"]
        or _positive(predecessor["key_head_sequence"], "predecessor_key_head")
        != c["key_event_count"]
        or predecessor["receipt_withdrawn_digest"]
        != receipt["withdrawn_release_digest"]
        or predecessor["receipt_digest"] != receipt_digest
        or c["receipt_digest"] != receipt_digest
        or predecessor["receipt_prior_epoch"] != receipt["prior_production_epoch"]
        or predecessor["receipt_advanced_epoch"] != receipt["advanced_production_epoch"]
    ):
        _reject("predecessor_binding")
    observed = _timestamp(c["observed_at"], "checkpoint_time")
    if observed < issued or observed != evaluation_time:
        _reject("checkpoint_time")
    if type(h["events"]) is not list or _positive(
        c["key_event_count"], "key_event_count"
    ) != len(h["events"]):
        _reject("checkpoint_history")
    if any(_event(event)[1] > observed for event in h["events"]):
        _reject("checkpoint_history")
    reduce_key_history(h["events"], issued, key)
    reduce_key_history(h["events"], evaluation_time, key)
    _key_static_validity(h["keys"], key, issued)
    # The receipt is required to be closed and chronologically usable for a withdrawal;
    # an active release has no withdrawal receipt relationship to consume.
    if _timestamp(
        receipt["completed_at"], "receipt_time"
    ) > evaluation_time or _timestamp(
        receipt["completed_at"], "receipt_time"
    ) < _timestamp(receipt["withdrawal_requested_at"], "withdrawal_requested_at"):
        _reject("receipt_time")
    if _positive(receipt["advanced_production_epoch"], "advanced_epoch") <= _positive(
        receipt["prior_production_epoch"], "prior_epoch"
    ):
        _reject("receipt_epoch")
    return digest


def _key_static_validity(keys: Any, selected: str, issued: int) -> None:
    if type(keys) is not list:
        _reject("key_static_shape")
    selected_row: dict[str, Any] | None = None
    seen: set[str] = set()
    for value in keys:
        row = _closed(
            value, {"key", "valid_from", "valid_until", "purposes"}, "key_static"
        )
        key = _text(row["key"], "key_static_key")
        if key in seen:
            _reject("key_static_duplicate")
        seen.add(key)
        valid_from = _timestamp(row["valid_from"], "key_valid_from")
        valid_until = row["valid_until"]
        if (
            valid_until is not None
            and _timestamp(valid_until, "key_valid_until") <= valid_from
        ):
            _reject("key_static_interval")
        if (
            type(row["purposes"]) is not list
            or not row["purposes"]
            or any(
                type(purpose) is not str or not purpose for purpose in row["purposes"]
            )
        ):
            _reject("key_static_purpose")
        if key == selected:
            if selected_row is not None:
                _reject("key_static_duplicate")
            selected_row = row
    if selected_row is None:
        _reject("key_static_missing")
    valid_from = _timestamp(selected_row["valid_from"], "key_valid_from")
    valid_until = selected_row["valid_until"]
    if valid_until is not None:
        valid_until = _timestamp(valid_until, "key_valid_until")
    if (
        "approval" not in selected_row["purposes"]
        or issued < valid_from
        or (valid_until is not None and issued >= valid_until)
    ):
        _reject("key_static_validity")

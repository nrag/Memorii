from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from memorii.core.memory_evolution import ingestion_contracts as codec
from memorii.core.semantic_ingestion import contracts as semantic


OUTPUT = Path(__file__).with_name("vcc-exp-006-complete-owner-seam-proof-v1.json")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class WriterSession:
    def __init__(self, *, reorder_callbacks: bool = False, extra_callback: bool = False) -> None:
        self.callback_trace: list[str] = []
        self.span_writer_calls = 0
        self.reorder_callbacks = reorder_callbacks
        self.extra_callback = extra_callback
        self._call_index = 0

    def emit(
        self,
        value: Any,
        *,
        check: Callable[[], None] | None,
        issue_spans: bool,
    ) -> tuple[bytes, tuple[dict[str, Any], ...]]:
        self._call_index += 1
        call_id = self._call_index
        if issue_spans:
            self.span_writer_calls += 1
        output = bytearray()
        spans: list[dict[str, Any]] = []
        event_number = 0

        def checked(label: str) -> None:
            nonlocal event_number
            event_number += 1
            recorded = label
            if issue_spans and self.reorder_callbacks and event_number in (1, 2):
                recorded = f"reordered:{3 - event_number}:{label}"
            self.callback_trace.append(f"call:{call_id}:{recorded}")
            if check is not None:
                check()
            if issue_spans and self.extra_callback and event_number == 1:
                self.callback_trace.append(f"call:{call_id}:extra:{label}")
                if check is not None:
                    check()

        def emit_node(node: Any, path: tuple[str | int, ...]) -> None:
            path_text = "/".join(str(item) for item in path) or "root"
            checked(f"node:{path_text}")
            start = len(output)
            if node is None:
                output.extend(b"null")
            elif node is True:
                output.extend(b"true")
            elif node is False:
                output.extend(b"false")
            elif isinstance(node, int) and not isinstance(node, bool):
                output.extend(str(node).encode("ascii"))
            elif isinstance(node, str):
                output.extend(json.dumps(node, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            elif isinstance(node, list):
                output.extend(b"[")
                for index, item in enumerate(node):
                    if index:
                        output.extend(b",")
                    emit_node(item, path + (index,))
                output.extend(b"]")
            elif isinstance(node, dict):
                output.extend(b"{")
                keys = []
                for key in node:
                    key_bytes = key_json(key, path + (f"sort:{key}",))
                    keys.append((key_bytes, key))
                for index, (_, key) in enumerate(sorted(keys)):
                    if index:
                        output.extend(b",")
                    output.extend(key_json(key, path + (f"key:{key}",)))
                    output.extend(b":")
                    emit_node(node[key], path + (key,))
                output.extend(b"}")
            else:
                raise TypeError(f"unsupported normalized value: {type(node)!r}")
            end = len(output)
            if issue_spans:
                spans.append({"path": path_text, "start": start, "end": end, "sha256": _sha(bytes(output[start:end]))})

        def key_json(key: str, path: tuple[str | int, ...]) -> bytes:
            path_text = "/".join(str(item) for item in path)
            checked(f"node:{path_text}")
            return json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

        emit_node(value, ())
        return bytes(output), tuple(spans)

    def ordering_json(self, value: Any, *, check: Callable[[], None] | None = None) -> bytes:
        return self.emit(value, check=check, issue_spans=False)[0]

    def span_json(self, value: Any, *, check: Callable[[], None] | None = None) -> tuple[bytes, tuple[dict[str, Any], ...]]:
        return self.emit(value, check=check, issue_spans=True)


@contextmanager
def _baseline_trace(session: WriterSession) -> Iterator[None]:
    original = codec._json
    codec._json = session.ordering_json
    try:
        yield
    finally:
        codec._json = original


@contextmanager
def _enabled_owner(
    session: WriterSession,
    *,
    duplicate_final_write: bool = False,
) -> Iterator[list[dict[str, Any]]]:
    original_json = codec._json
    original_encode = codec.encode_typed_value
    original_semantic_encode = semantic.encode_typed_value
    reports: list[dict[str, Any]] = []

    codec._json = session.ordering_json

    def enabled_encode(value: Any, *, check: Callable[[], None] | None = None) -> bytes:
        normalized = codec._normalized_typed_json(value, check=check)
        before = session.span_writer_calls
        raw, spans = session.span_json(normalized, check=check)
        if duplicate_final_write:
            session.span_json(normalized, check=check)
        if session.span_writer_calls - before != 1:
            raise AssertionError("final_span_writer_count")
        reports.append({"raw_sha256": _sha(raw), "spans": spans})
        return raw

    semantic_calls = 0

    def semantic_encode(value: Any, *, check: Callable[[], None] | None = None) -> bytes:
        nonlocal semantic_calls
        semantic_calls += 1
        if semantic_calls == 1:
            return original_semantic_encode(value, check=check)
        return enabled_encode(value, check=check)

    codec.encode_typed_value = enabled_encode
    semantic.encode_typed_value = semantic_encode
    try:
        yield reports
    finally:
        codec._json = original_json
        codec.encode_typed_value = original_encode
        semantic.encode_typed_value = original_semantic_encode


def _counting_check() -> tuple[Callable[[], None], list[int]]:
    count = [0]

    def check() -> None:
        count[0] += 1

    return check, count


def _fixtures() -> tuple[tuple[str, Any], ...]:
    decoded_map = codec.decode_typed_value(codec.encode_typed_value({"a": 1, "b": 2}))
    decoded_list = codec.decode_typed_value(codec.encode_typed_value([1, "a"]))
    decoded_tuple = codec.decode_typed_value(codec.encode_typed_value((1, "a")))
    decoded_set = codec.decode_typed_value(codec.encode_typed_value({1, 2}))
    decoded_frozenset = codec.decode_typed_value(codec.encode_typed_value(frozenset({1, 2})))
    return (
        ("null", None), ("boolean", True), ("integer", 7), ("string", "caf\u00e9"),
        ("bytes", b"canonical"), ("datetime", datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc)),
        ("timedelta", timedelta(days=2, seconds=3, microseconds=4)),
        ("list", [1, "a"]), ("tuple", (1, "a")), ("map", {"z": 1, "a": 2}),
        ("set", {"z", "a"}), ("frozenset", frozenset({3, 1})),
        ("decoded_immutable_map", decoded_map), ("decoded_immutable_list", decoded_list),
        ("decoded_immutable_tuple", decoded_tuple), ("decoded_immutable_set", decoded_set),
        ("decoded_immutable_frozenset", decoded_frozenset),
        ("nested_ordered", {"wrappers": [decoded_map, decoded_tuple], "sets": (decoded_set, decoded_frozenset)}),
    )


def _run_case(name: str, value: Any) -> dict[str, Any]:
    original = codec.encode_typed_value(value)
    baseline_session = WriterSession()
    baseline_check, baseline_count = _counting_check()
    with _baseline_trace(baseline_session):
        baseline = codec.encode_typed_value(value, check=baseline_check)
    enabled_session = WriterSession()
    enabled_check, enabled_count = _counting_check()
    with _enabled_owner(enabled_session) as reports:
        enabled = codec.encode_typed_value(value, check=enabled_check)
    if original != baseline or baseline != enabled:
        raise AssertionError(f"byte_mismatch:{name}")
    if baseline_session.callback_trace != enabled_session.callback_trace:
        raise AssertionError(f"callback_trace_mismatch:{name}")
    if baseline_count != enabled_count:
        raise AssertionError(f"callback_count_mismatch:{name}")
    if enabled_session.span_writer_calls != 1 or len(reports) != 1:
        raise AssertionError(f"writer_count_mismatch:{name}")
    restored = codec.decode_typed_value(enabled)
    if codec.encode_typed_value(restored) != original:
        raise AssertionError(f"decoder_mismatch:{name}")
    spans = reports[0]["spans"]
    for span in spans:
        if _sha(enabled[span["start"]:span["end"]]) != span["sha256"]:
            raise AssertionError(f"span_mismatch:{name}")
    return {"case": name, "sha256": _sha(enabled), "callback_events": len(enabled_session.callback_trace), "span_count": len(spans)}


def _attacks() -> dict[str, bool]:
    attacks = {}
    for name, value in (("duplicate_map_writer", {"b": 2, "a": 1}), ("duplicate_set_writer", {2, 1})):
        try:
            with _enabled_owner(WriterSession(), duplicate_final_write=True):
                codec.encode_typed_value(value)
        except AssertionError as exc:
            attacks[name] = str(exc) == "final_span_writer_count"
        else:
            attacks[name] = False
    value = {"nested": [1, 2]}
    baseline = WriterSession()
    with _baseline_trace(baseline):
        codec.encode_typed_value(value)
    for name, session in (
        ("reordered_callback", WriterSession(reorder_callbacks=True)),
        ("extra_callback", WriterSession(extra_callback=True)),
    ):
        with _enabled_owner(session):
            codec.encode_typed_value(value)
        attacks[name] = baseline.callback_trace != session.callback_trace
    return attacks


def main() -> None:
    cases = [_run_case(name, value) for name, value in _fixtures()]
    attacks = _attacks()
    if not all(attacks.values()):
        raise AssertionError("attack_not_detected")
    contract = semantic.ConstructionFamily.create(family_id="vcc-complete-owner-proof")
    baseline = WriterSession()
    with _baseline_trace(baseline):
        baseline_raw = semantic.encode_semantic_contract(contract)
    enabled = WriterSession()
    with _enabled_owner(enabled) as reports:
        enabled_raw = semantic.encode_semantic_contract(contract)
    if baseline_raw != enabled_raw or baseline.callback_trace != enabled.callback_trace or enabled.span_writer_calls != 1 or len(reports) != 1:
        raise AssertionError("semantic_contract_mismatch")
    result = {
        "schema": "memorii.vcc-complete-owner-seam-proof.v1",
        "passed": True,
        "production_code_changed": False,
        "tests_changed": False,
        "fixture_family_count": len(cases),
        "cases": cases,
        "semantic_contract": {"sha256": _sha(enabled_raw), "span_writer_calls": enabled.span_writer_calls},
        "attacks": attacks,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

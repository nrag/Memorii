from __future__ import annotations

import hashlib
import json
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from memorii.core.memory_evolution import ingestion_contracts as codec
from memorii.core.semantic_ingestion import contracts as semantic


OUTPUT = Path(__file__).with_name("vcc-exp-007-production-callback-wrapper-proof-v1.json")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "map"
    return type(value).__name__


def _fingerprint(value: Any) -> str:
    return _sha(repr(value).encode("utf-8"))


@dataclass(frozen=True)
class CallbackEvent:
    phase: Literal["normalize", "emit"]
    path: str
    node_kind: str
    fingerprint: str


@dataclass
class _Frame:
    path: str
    children: int = 0
    json_children: int = 0


class ProductionCallbackTrace:
    """Observe real production callback invocations without changing their count."""

    def __init__(self) -> None:
        self.events: list[CallbackEvent] = []
        self._normalization_stack: list[_Frame] = []
        self._json_stack: list[_Frame] = []
        self._original_normalize = codec._normalized_typed_json
        self._original_json = codec._json

    @staticmethod
    def _root_check(check: Callable[[], None] | None) -> Callable[[], None] | None:
        return getattr(check, "_vcc_root_check", check)

    def _normalization_path(self) -> str:
        if not self._normalization_stack:
            return "normalize:root"
        parent = self._normalization_stack[-1]
        path = f"{parent.path}/child:{parent.children}"
        parent.children += 1
        return path

    def _json_path(self) -> str:
        if self._json_stack:
            parent = self._json_stack[-1]
            path = f"{parent.path}/child:{parent.children}"
            parent.children += 1
            return path
        if self._normalization_stack:
            parent = self._normalization_stack[-1]
            path = f"{parent.path}/json:{parent.json_children}"
            parent.json_children += 1
            return path
        return "emit:root"

    def _traced_normalize(self, value: Any, *, check: Callable[[], None] | None = None) -> Any:
        path = self._normalization_path()
        frame = _Frame(path)
        self._normalization_stack.append(frame)
        root_check = self._root_check(check)

        def observed() -> None:
            self.events.append(CallbackEvent("normalize", path, _kind(value), _fingerprint(value)))
            if root_check is not None:
                root_check()

        observed._vcc_root_check = root_check  # type: ignore[attr-defined]
        try:
            return self._original_normalize(value, check=observed)
        finally:
            self._normalization_stack.pop()

    def _traced_json(self, value: Any, *, check: Callable[[], None] | None = None) -> bytes:
        path = self._json_path()
        frame = _Frame(path)
        self._json_stack.append(frame)
        root_check = self._root_check(check)

        def observed() -> None:
            self.events.append(CallbackEvent("emit", path, _kind(value), _fingerprint(value)))
            if root_check is not None:
                root_check()

        observed._vcc_root_check = root_check  # type: ignore[attr-defined]
        try:
            return self._original_json(value, check=observed)
        finally:
            self._json_stack.pop()

    def __enter__(self) -> ProductionCallbackTrace:
        codec._normalized_typed_json = self._traced_normalize
        codec._json = self._traced_json
        return self

    def __exit__(self, *_: object) -> None:
        codec._normalized_typed_json = self._original_normalize
        codec._json = self._original_json


class SpanWriter:
    def __init__(
        self,
        *,
        initial_events: tuple[CallbackEvent, ...] = (),
        reorder_pair: tuple[int, int] | None = None,
        omit_ordinal: int | None = None,
        extra_after: int | None = None,
    ) -> None:
        self.events = list(initial_events)
        self.span_writer_calls = 0
        self._ordinal = 0
        self._reorder_pair = reorder_pair
        self._omit_ordinal = omit_ordinal
        self._extra_after = extra_after
        self._buffered: tuple[CallbackEvent, Callable[[], None] | None] | None = None

    def _invoke(self, event: CallbackEvent, check: Callable[[], None] | None) -> None:
        self.events.append(event)
        if check is not None:
            check()

    def _checked(self, event: CallbackEvent, check: Callable[[], None] | None) -> None:
        self._ordinal += 1
        ordinal = self._ordinal
        if ordinal == self._omit_ordinal:
            return
        if self._reorder_pair is not None and ordinal == self._reorder_pair[0]:
            self._buffered = (event, check)
            return
        if self._reorder_pair is not None and ordinal == self._reorder_pair[1]:
            self._invoke(event, check)
            if self._buffered is None:
                raise AssertionError("missing_reorder_buffer")
            self._invoke(*self._buffered)
            self._buffered = None
        else:
            self._invoke(event, check)
        if ordinal == self._extra_after:
            self._invoke(event, check)

    def span_json(
        self, value: Any, *, check: Callable[[], None] | None = None
    ) -> tuple[bytes, tuple[dict[str, Any], ...]]:
        self.span_writer_calls += 1
        output = bytearray()
        spans: list[dict[str, Any]] = []

        def emit(node: Any, path: str) -> None:
            self._checked(CallbackEvent("emit", path, _kind(node), _fingerprint(node)), check)
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
                    emit(item, f"{path}/child:{index}")
                output.extend(b"]")
            elif isinstance(node, dict):
                output.extend(b"{")
                child = 0
                sortable: list[tuple[bytes, str]] = []
                for key in node:
                    key_path = f"{path}/child:{child}"
                    child += 1
                    key_bytes = scalar_key(key, key_path)
                    sortable.append((key_bytes, key))
                for index, (_, key) in enumerate(sorted(sortable)):
                    if index:
                        output.extend(b",")
                    key_path = f"{path}/child:{child}"
                    child += 1
                    output.extend(scalar_key(key, key_path))
                    output.extend(b":")
                    value_path = f"{path}/child:{child}"
                    child += 1
                    emit(node[key], value_path)
                output.extend(b"}")
            else:
                raise TypeError(f"unsupported normalized value: {type(node)!r}")
            end = len(output)
            spans.append({"path": path, "start": start, "end": end, "sha256": _sha(bytes(output[start:end]))})

        def scalar_key(key: str, path: str) -> bytes:
            self._checked(CallbackEvent("emit", path, "string", _fingerprint(key)), check)
            return json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

        emit(value, "emit:root")
        if self._buffered is not None:
            raise AssertionError("unflushed_reorder_buffer")
        return bytes(output), tuple(spans)


def _counting_check() -> tuple[Callable[[], None], list[int]]:
    count = [0]

    def check() -> None:
        count[0] += 1

    return check, count


def _enabled_encode(
    value: Any,
    *,
    check: Callable[[], None] | None = None,
    writer_options: dict[str, Any] | None = None,
) -> tuple[bytes, tuple[dict[str, Any], ...], SpanWriter]:
    with ProductionCallbackTrace() as normalization_trace:
        normalized = codec._normalized_typed_json(value, check=check)
    writer = SpanWriter(initial_events=tuple(normalization_trace.events), **(writer_options or {}))
    raw, spans = writer.span_json(normalized, check=check)
    return raw, spans, writer


def _validate_spans(raw: bytes, spans: tuple[dict[str, Any], ...]) -> None:
    for span in spans:
        if not 0 <= span["start"] <= span["end"] <= len(raw):
            raise AssertionError("span_bounds")
        if _sha(raw[span["start"]:span["end"]]) != span["sha256"]:
            raise AssertionError("span_digest")


def _run_case(name: str, value: Any) -> dict[str, Any]:
    public_raw = codec.encode_typed_value(value)
    baseline_check, baseline_count = _counting_check()
    with ProductionCallbackTrace() as baseline_trace:
        baseline_raw = codec.encode_typed_value(value, check=baseline_check)
    enabled_check, enabled_count = _counting_check()
    enabled_raw, spans, writer = _enabled_encode(value, check=enabled_check)
    if public_raw != baseline_raw or baseline_raw != enabled_raw:
        raise AssertionError(f"byte_mismatch:{name}")
    if baseline_trace.events != writer.events or baseline_count != enabled_count:
        raise AssertionError(f"callback_schedule_mismatch:{name}")
    if writer.span_writer_calls != 1:
        raise AssertionError(f"span_writer_count:{name}")
    if codec.encode_typed_value(codec.decode_typed_value(enabled_raw)) != enabled_raw:
        raise AssertionError(f"decoder_reencoder:{name}")
    _validate_spans(enabled_raw, spans)
    return {
        "case": name,
        "sha256": _sha(enabled_raw),
        "callback_events": len(writer.events),
        "span_count": len(spans),
    }


def _ordered_items(*items: Any) -> list[Any]:
    return [item for _, item in sorted((codec._json(item), item) for item in items)]


def _raw_map(*entries: tuple[str, Any]) -> dict[str, Any]:
    ordered = sorted(entries, key=lambda item: codec._json(item[0]))
    return {"$type": "map", "entries": [[key, value] for key, value in ordered]}


def _wrapper_fixtures() -> tuple[tuple[str, bytes, Callable[[Any], None]], ...]:
    integer_1 = {"$type": "integer", "value": "1"}
    integer_2 = {"$type": "integer", "value": "2"}
    map_item = _raw_map(("k", integer_1))
    list_item = {"$type": "list", "items": [integer_1, "a"]}
    tuple_item = {"$type": "tuple", "items": [integer_1, "a"]}
    set_item = {"$type": "set", "items": _ordered_items(integer_1, integer_2)}
    tag_set_item = {"$type": "set", "items": _ordered_items(True, integer_1)}
    tag_frozenset_item = {"$type": "frozenset", "items": _ordered_items(True, integer_1)}

    def outer(item: Any, *, frozen: bool = False) -> bytes:
        return codec._json({"$type": "frozenset" if frozen else "set", "items": _ordered_items(item)})

    def singleton(expected: type[Any]) -> Callable[[Any], None]:
        def assert_type(value: Any) -> None:
            if type(value) is not set or type(next(iter(value))) is not expected:
                raise AssertionError(f"wrapper_type:{expected.__name__}")
        return assert_type

    def tag(expected: type[Any]) -> Callable[[Any], None]:
        def assert_type(value: Any) -> None:
            if type(value) is not expected or Counter(value) != Counter((True, 1)):
                raise AssertionError(f"tag_wrapper_type:{expected.__name__}")
        return assert_type

    expected_types = Counter({
        codec._HashableCtvMap: 1,
        codec._ImmutableCtvList: 1,
        codec._ImmutableCtvTuple: 1,
        codec._ImmutableCtvSet: 1,
        codec._TagAwareCtvSet: 1,
        codec._TagAwareCtvFrozenSet: 1,
    })

    def mixed(expected_outer: type[Any]) -> Callable[[Any], None]:
        def assert_type(value: Any) -> None:
            if type(value) is not expected_outer or Counter(type(item) for item in value) != expected_types:
                raise AssertionError("mixed_wrapper_types")
        return assert_type

    mixed_items = _ordered_items(map_item, list_item, tuple_item, set_item, tag_set_item, tag_frozenset_item)
    return (
        ("decoded_hashable_map", outer(map_item), singleton(codec._HashableCtvMap)),
        ("decoded_immutable_list", outer(list_item), singleton(codec._ImmutableCtvList)),
        ("decoded_immutable_tuple", outer(tuple_item), singleton(codec._ImmutableCtvTuple)),
        ("decoded_immutable_set", outer(set_item), singleton(codec._ImmutableCtvSet)),
        ("decoded_tag_aware_set", codec._json(tag_set_item), tag(codec._TagAwareCtvSet)),
        ("decoded_tag_aware_frozenset", codec._json(tag_frozenset_item), tag(codec._TagAwareCtvFrozenSet)),
        ("decoded_mixed_wrapper_set", codec._json({"$type": "set", "items": mixed_items}), mixed(set)),
        ("decoded_mixed_wrapper_frozenset", codec._json({"$type": "frozenset", "items": mixed_items}), mixed(frozenset)),
    )


def _native_fixtures() -> tuple[tuple[str, Any], ...]:
    return (
        ("null", None), ("boolean", True), ("integer", 7), ("string", "caf\u00e9"),
        ("bytes", b"canonical"), ("datetime", datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc)),
        ("timedelta", timedelta(days=2, seconds=3, microseconds=4)),
        ("list", [1, "a"]), ("tuple", (1, "a")), ("map", {"z": 1, "a": 2}),
        ("set", {"z", "a"}), ("frozenset", frozenset({3, 1})),
        ("nested_ordered", {"wrappers": [(1, "a"), [2, "b"]], "sets": ({1, 2}, frozenset({3, 4}))}),
    )


def _attacks(value: Any) -> dict[str, bool]:
    with ProductionCallbackTrace() as baseline_trace:
        baseline_raw = codec.encode_typed_value(value)
    results: dict[str, bool] = {}
    for name, options, expected_delta in (
        ("actual_reorder", {"reorder_pair": (1, 2)}, 0),
        ("actual_omission", {"omit_ordinal": 1}, -1),
        ("actual_extra", {"extra_after": 1}, 1),
    ):
        attacked_raw, _, writer = _enabled_encode(value, writer_options=options)
        results[name] = (
            attacked_raw == baseline_raw
            and writer.events != baseline_trace.events
            and len(writer.events) == len(baseline_trace.events) + expected_delta
        )
    for name, duplicate_value in (("duplicate_map_writer", {"b": 2, "a": 1}), ("duplicate_set_writer", {2, 1})):
        raw, _, writer = _enabled_encode(duplicate_value)
        normalized = codec._normalized_typed_json(duplicate_value)
        writer.span_json(normalized)
        results[name] = raw == codec.encode_typed_value(duplicate_value) and writer.span_writer_calls != 1
    return results


def _semantic_contract_case() -> dict[str, Any]:
    contract = semantic.ConstructionFamily.create(family_id="vcc-production-callback-wrapper-proof")
    original = semantic.encode_typed_value
    baseline_calls: list[tuple[CallbackEvent, ...]] = []

    def baseline(value: Any, *, check: Callable[[], None] | None = None) -> bytes:
        with ProductionCallbackTrace() as trace:
            raw = original(value, check=check)
        baseline_calls.append(tuple(trace.events))
        return raw

    semantic.encode_typed_value = baseline
    try:
        baseline_raw = semantic.encode_semantic_contract(contract)
    finally:
        semantic.encode_typed_value = original

    calls = 0
    enabled_calls: list[tuple[CallbackEvent, ...]] = []
    writer_calls = 0

    def enabled(value: Any, *, check: Callable[[], None] | None = None) -> bytes:
        nonlocal calls, writer_calls
        calls += 1
        if calls == 1:
            with ProductionCallbackTrace() as trace:
                raw = original(value, check=check)
            enabled_calls.append(tuple(trace.events))
            return raw
        raw, _, writer = _enabled_encode(value, check=check)
        enabled_calls.append(tuple(writer.events))
        writer_calls += writer.span_writer_calls
        return raw

    semantic.encode_typed_value = enabled
    try:
        enabled_raw = semantic.encode_semantic_contract(contract)
    finally:
        semantic.encode_typed_value = original
    if baseline_raw != enabled_raw or baseline_calls != enabled_calls or writer_calls != 1:
        raise AssertionError("semantic_contract_schedule")
    return {
        "sha256": _sha(enabled_raw),
        "codec_invocations": len(enabled_calls),
        "callback_events": sum(len(events) for events in enabled_calls),
        "span_writer_calls": writer_calls,
    }


def main() -> None:
    cases = [_run_case(name, value) for name, value in _native_fixtures()]
    wrapper_types: dict[str, str] = {}
    attack_value: Any | None = None
    for name, raw, assert_type in _wrapper_fixtures():
        decoded = codec.decode_typed_value(raw)
        assert_type(decoded)
        if codec.encode_typed_value(decoded) != raw:
            raise AssertionError(f"wrapper_roundtrip:{name}")
        cases.append(_run_case(name, decoded))
        wrapper_types[name] = type(decoded).__name__
        if name == "decoded_mixed_wrapper_frozenset":
            attack_value = decoded
    if attack_value is None:
        raise AssertionError("missing_attack_fixture")
    attacks = _attacks(attack_value)
    if not all(attacks.values()):
        raise AssertionError(f"attack_not_detected:{attacks}")
    result = {
        "schema": "memorii.vcc-production-callback-wrapper-proof.v1",
        "passed": True,
        "production_code_changed": False,
        "tests_changed": False,
        "fixture_family_count": len(cases),
        "cases": cases,
        "wrapper_outer_types": wrapper_types,
        "semantic_contract": _semantic_contract_case(),
        "attacks": attacks,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

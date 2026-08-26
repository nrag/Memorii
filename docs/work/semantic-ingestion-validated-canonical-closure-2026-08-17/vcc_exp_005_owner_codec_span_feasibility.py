from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from memorii.core.memory_evolution import ingestion_contracts as typed_codec
from memorii.core.semantic_ingestion import contracts as semantic_contracts
from memorii.core.semantic_ingestion.contracts import (
    ConstructionFamily,
    decode_semantic_contract,
    encode_semantic_contract,
)


OUTPUT = Path(__file__).with_name("vcc-exp-005-owner-codec-span-feasibility-v1.json")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _path_token(path: tuple[str | int, ...]) -> str:
    return "/".join(f"i:{item}" if isinstance(item, int) else f"k:{item}" for item in path)


def _emit_with_spans(
    value: Any,
    scalar_json: Any,
    *,
    check: Any = None,
) -> tuple[bytes, tuple[dict[str, Any], ...]]:
    output = bytearray()
    spans: list[dict[str, Any]] = []

    def emit(node: Any, path: tuple[str | int, ...]) -> None:
        if check is not None:
            check()
        start = len(output)
        if isinstance(node, list):
            output.extend(b"[")
            for index, item in enumerate(node):
                if index:
                    output.extend(b",")
                emit(item, path + (index,))
            output.extend(b"]")
        elif isinstance(node, dict):
            output.extend(b"{")
            keys = sorted(node, key=lambda item: scalar_json(item, check=check))
            for index, key in enumerate(keys):
                if index:
                    output.extend(b",")
                output.extend(scalar_json(key, check=check))
                output.extend(b":")
                emit(node[key], path + (key,))
            output.extend(b"}")
        else:
            output.extend(scalar_json(node))
        end = len(output)
        emitted = bytes(output[start:end])
        spans.append(
            {
                "path": _path_token(path),
                "start": start,
                "end": end,
                "sha256": _digest(emitted),
            }
        )

    emit(value, ())
    return bytes(output), tuple(spans)


@contextmanager
def _owner_span_writer() -> Iterator[list[dict[str, Any]]]:
    original_json = typed_codec._json
    original_typed_encode = typed_codec.encode_typed_value
    original_semantic_typed_encode = semantic_contracts.encode_typed_value
    calls: list[dict[str, Any]] = []

    def traced_encode(value: Any, *, check: Any = None) -> bytes:
        normalized = typed_codec._normalized_typed_json(value, check=check)
        raw, spans = _emit_with_spans(normalized, original_json, check=check)
        calls.append({"raw_sha256": _digest(raw), "spans": spans})
        return raw

    semantic_typed_calls = 0

    def semantic_typed_encode(value: Any, *, check: Any = None) -> bytes:
        nonlocal semantic_typed_calls
        semantic_typed_calls += 1
        if semantic_typed_calls == 1:
            return original_semantic_typed_encode(value, check=check)
        return traced_encode(value, check=check)

    typed_codec.encode_typed_value = traced_encode
    semantic_contracts.encode_typed_value = semantic_typed_encode
    try:
        yield calls
    finally:
        typed_codec.encode_typed_value = original_typed_encode
        semantic_contracts.encode_typed_value = original_semantic_typed_encode


def _matching_call(calls: list[dict[str, Any]], raw: bytes) -> dict[str, Any]:
    matches = [item for item in calls if item["raw_sha256"] == _digest(raw)]
    if not matches:
        raise AssertionError("owner span writer did not observe final canonical bytes")
    return matches[-1]


def _validate_report(report: dict[str, Any], raw: bytes) -> None:
    spans = report["spans"]
    if not spans or not any(item["path"] == "" and item["start"] == 0 and item["end"] == len(raw) for item in spans):
        raise AssertionError("span report lacks the exact canonical root")
    for item in spans:
        start, end = item["start"], item["end"]
        if not (0 <= start < end <= len(raw)):
            raise AssertionError("span is outside canonical root bytes")
        if _digest(raw[start:end]) != item["sha256"]:
            raise AssertionError("span digest does not match exact canonical byte slice")


def _check_count(encoder: Any, value: Any) -> int:
    count = 0

    def check() -> None:
        nonlocal count
        count += 1

    encoder(value, check=check)
    return count


def _check_outcome(encoder: Any, value: Any, fail_at: int) -> tuple[str, int]:
    count = 0

    class Stop(Exception):
        pass

    def check() -> None:
        nonlocal count
        count += 1
        if count == fail_at:
            raise Stop

    try:
        encoder(value, check=check)
    except Stop:
        return "stopped", count
    return "completed", count


def main() -> None:
    samples: tuple[tuple[str, Any], ...] = (
        ("null", None),
        ("boolean", True),
        ("integer", 7),
        ("unicode_string", "caf\u00e9"),
        ("bytes", b"canonical"),
        ("list", [1, "a"]),
        ("tuple", (1, "a")),
        ("map_order", {"z": 1, "a": 2}),
        ("set_order", {"z", "a"}),
        ("frozenset_order", frozenset({3, 1})),
        ("nested", {"set": {2, 1}, "items": [{"b": 2, "a": 1}]}),
    )
    typed_results: list[dict[str, Any]] = []
    for name, value in samples:
        baseline = typed_codec.encode_typed_value(value)
        baseline_check_count = _check_count(typed_codec.encode_typed_value, value)
        with _owner_span_writer() as calls:
            enabled = typed_codec.encode_typed_value(value)
            enabled_check_count = _check_count(typed_codec.encode_typed_value, value)
        if len(calls) != 2:
            raise AssertionError(f"expected one final span write per public encode call for {name}")
        report = _matching_call(calls, enabled)
        _validate_report(report, enabled)
        decoded = typed_codec.decode_typed_value(enabled)
        passed = baseline == enabled and typed_codec.encode_typed_value(decoded) == baseline
        if not passed:
            raise AssertionError(f"typed codec mismatch for {name}")
        if baseline_check_count != enabled_check_count:
            raise AssertionError(
                f"check callback count mismatch for {name}: "
                f"baseline={baseline_check_count}, enabled={enabled_check_count}"
            )
        thresholds = sorted({1, max(1, baseline_check_count // 2), baseline_check_count, baseline_check_count + 1})
        threshold_results = []
        for threshold in thresholds:
            baseline_outcome = _check_outcome(typed_codec.encode_typed_value, value, threshold)
            with _owner_span_writer():
                enabled_outcome = _check_outcome(typed_codec.encode_typed_value, value, threshold)
            if baseline_outcome != enabled_outcome:
                raise AssertionError(f"stateful check mismatch for {name} at {threshold}")
            threshold_results.append({"fail_at": threshold, "outcome": baseline_outcome[0], "calls": baseline_outcome[1]})
        typed_results.append(
            {
                "case": name,
                "canonical_sha256": _digest(enabled),
                "span_count": len(report["spans"]),
                "byte_identical": baseline == enabled,
                "decoder_compatible": typed_codec.encode_typed_value(decoded) == baseline,
                "final_span_writer_calls_per_encode": 1,
                "check_callback_count": baseline_check_count,
                "stateful_check_equivalence": threshold_results,
            }
        )

    contract = ConstructionFamily.create(family_id="vcc-owner-codec-proof")
    contract_baseline = encode_semantic_contract(contract)
    with _owner_span_writer() as calls:
        contract_enabled = encode_semantic_contract(contract)
    if len(calls) != 1:
        raise AssertionError("semantic contract must issue exactly one final span report")
    contract_report = _matching_call(calls, contract_enabled)
    _validate_report(contract_report, contract_enabled)
    restored = decode_semantic_contract(contract_enabled, ConstructionFamily)
    contract_passed = contract_baseline == contract_enabled and restored == contract
    if not contract_passed:
        raise AssertionError("semantic contract codec mismatch")

    result = {
        "schema": "memorii.vcc-owner-codec-span-feasibility.v1",
        "passed": True,
        "production_code_changed": False,
        "tests_changed": False,
        "owner_seam": "memorii.core.memory_evolution.ingestion_contracts._json",
        "normalization_owner": "memorii.core.memory_evolution.ingestion_contracts._normalized_typed_json",
        "public_codec_entrypoints": [
            "encode_typed_value/decode_typed_value",
            "encode_semantic_contract/decode_semantic_contract",
        ],
        "proof_semantics": "The prototype replaces only the byte writer used by the real codec owner; production normalization, public codec entrypoints, and decoders execute unchanged.",
        "span_integrity": "Every recorded span is in bounds, the root span covers the complete canonical bytes, and every span digest equals its exact canonical byte slice.",
        "typed_cases": typed_results,
        "semantic_contract_case": {
            "contract_kind": "construction_family",
            "canonical_sha256": _digest(contract_enabled),
            "span_count": len(contract_report["spans"]),
            "byte_identical": contract_baseline == contract_enabled,
            "decoder_compatible": restored == contract,
        },
        "security_boundary": "Spans are observations over bytes emitted by the codec owner; they carry no validation, authorization, persistence, or writer authority.",
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

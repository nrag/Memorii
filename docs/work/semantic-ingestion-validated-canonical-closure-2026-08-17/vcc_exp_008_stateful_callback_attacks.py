from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "vcc-exp-008-stateful-callback-attacks-v1.json"
V7 = HERE / "vcc_exp_007_production_callback_wrapper_proof.py"
spec = importlib.util.spec_from_file_location("vcc_v7", V7)
if spec is None or spec.loader is None:
    raise RuntimeError("v7 proof unavailable")
v7 = importlib.util.module_from_spec(spec)
sys.modules["vcc_v7"] = v7
spec.loader.exec_module(v7)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class StatefulProbe:
    def __init__(self) -> None:
        self._next = 0
        self._armed: tuple[int, dict[str, str]] | None = None
        self.observed: list[tuple[int, dict[str, str]]] = []

    def arm(self, event: Any) -> tuple[int, dict[str, str]]:
        if self._armed is not None:
            raise AssertionError("probe_rearmed")
        self._next += 1
        token = (self._next, asdict(event))
        self._armed = token
        return token

    def check(self) -> None:
        if self._armed is None:
            raise AssertionError("callback_without_event")
        self.observed.append(self._armed)

    def disarm(self, token: tuple[int, dict[str, str]]) -> None:
        if self._armed != token or not self.observed or self.observed[-1] != token:
            raise AssertionError("callback_event_substitution")
        self._armed = None

    def assert_clear(self) -> None:
        if self._armed is not None:
            raise AssertionError("callback_event_left_armed")


class ProbedSpanWriter(v7.SpanWriter):
    def __init__(self, probe: StatefulProbe, **options: Any) -> None:
        super().__init__(**options)
        self._probe = probe

    def _invoke(self, event: Any, check: Any) -> None:
        token = self._probe.arm(event)
        self.events.append(event)
        if check is None:
            raise AssertionError("attack_callback_missing")
        check()
        self._probe.disarm(token)


def _run_writer(value: Any, options: dict[str, Any]) -> tuple[bytes, StatefulProbe, ProbedSpanWriter]:
    normalized = v7.codec._normalized_typed_json(value)
    probe = StatefulProbe()
    writer = ProbedSpanWriter(probe, **options)
    raw, _ = writer.span_json(normalized, check=probe.check)
    probe.assert_clear()
    if len(probe.observed) != len(writer.events):
        raise AssertionError("external_callback_count")
    if [token[1] for token in probe.observed] != [asdict(event) for event in writer.events]:
        raise AssertionError("external_callback_identity")
    return raw, probe, writer


def _sequence_digest(probe: StatefulProbe) -> str:
    return _sha(json.dumps(probe.observed, sort_keys=True, separators=(",", ":")).encode())


def _matrix(value: Any) -> dict[str, Any]:
    baseline_bytes, baseline_probe, _ = _run_writer(value, {})
    result: dict[str, Any] = {
        "canonical_sha256": _sha(baseline_bytes),
        "baseline_invocations": len(baseline_probe.observed),
        "baseline_sequence_sha256": _sequence_digest(baseline_probe),
        "attacks": {},
    }
    for name, options, delta in (
        ("reorder", {"reorder_pair": (1, 2)}, 0),
        ("omission", {"omit_ordinal": 1}, -1),
        ("extra", {"extra_after": 1}, 1),
    ):
        raw, probe, _ = _run_writer(value, options)
        detected = (
            raw == baseline_bytes
            and len(probe.observed) == len(baseline_probe.observed) + delta
            and _sequence_digest(probe) != _sequence_digest(baseline_probe)
        )
        if not detected:
            raise AssertionError(f"stateful_attack_not_detected:{name}")
        result["attacks"][name] = {
            "detected": True,
            "external_callback_invocations": len(probe.observed),
            "sequence_sha256": _sequence_digest(probe),
        }
    return result


def main() -> None:
    subjects: dict[str, Any] = {}
    for name, raw, assert_type in v7._wrapper_fixtures():
        if name not in {"decoded_mixed_wrapper_set", "decoded_mixed_wrapper_frozenset"}:
            continue
        value = v7.codec.decode_typed_value(raw)
        assert_type(value)
        subjects[name] = value
    if set(subjects) != {"decoded_mixed_wrapper_set", "decoded_mixed_wrapper_frozenset"}:
        raise AssertionError("mixed_subject_inventory")
    matrices = {name: _matrix(value) for name, value in subjects.items()}
    result = {
        "schema": "memorii.vcc-stateful-callback-attacks.v1",
        "passed": True,
        "production_code_changed": False,
        "tests_changed": False,
        "subjects": matrices,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()


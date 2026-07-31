"""Admission-cap tests for the immutable M0 generation transport."""

from __future__ import annotations

import json
import runpy
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from inspect import signature
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, cast

import pytest
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.tools import semantic_ingestion_execution_evidence as evidence
from memorii.tools import semantic_ingestion_traceability_checker as checker
from memorii.tools import semantic_ingestion_traceability_manifest as manifest
from memorii.tools.semantic_ingestion_traceability import extract_normative_units
from memorii.tools.semantic_ingestion_traceability_checker import (
    TraceabilityCoverageError,
    load_independent_registry_bytes,
)

UTC = timezone.utc  # noqa: UP017
ROOT = Path(__file__).parents[4]


def test_structural_builder_installs_default_parse_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter((0.0, 31.0))
    monkeypatch.setattr(manifest, "monotonic", lambda: next(ticks))
    with pytest.raises(manifest.StructuralManifestError, match="deadline exceeded"):
        manifest.build_structural_manifest(
            design_bytes=b"## 1. Scope\n",
            registry=cast(Any, SimpleNamespace(canonical_bytes=b"")),
        )


def test_structural_builder_propagates_cooperative_cancellation() -> None:
    def cancelled() -> None:
        raise manifest.StructuralManifestError("structural derivation cancelled")

    with pytest.raises(manifest.StructuralManifestError, match="cancelled"):
        manifest.build_structural_manifest(
            design_bytes=b"## 1. Scope\n",
            registry=cast(Any, SimpleNamespace(canonical_bytes=b"")),
            check=cancelled,
        )


def test_independent_checker_installs_default_parse_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter((0.0, 31.0))
    monkeypatch.setattr(checker, "monotonic", lambda: next(ticks))
    with pytest.raises(TraceabilityCoverageError, match="parser deadline exceeded"):
        checker.rebuild_structural_manifest_bytes(
            design_bytes=b"## 1. Scope\n",
            registry=cast(Any, SimpleNamespace(source={})),
        )


def test_independent_checker_installs_default_reconstruction_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter((0.0, 0.0, 0.0, 61.0))
    monkeypatch.setattr(checker, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(checker, "_independent_extract", lambda *_args, **_kwargs: ())
    with pytest.raises(TraceabilityCoverageError, match="reconstruction deadline exceeded"):
        checker.rebuild_structural_manifest_bytes(
            design_bytes=b"## 1. Scope\n",
            registry=cast(Any, SimpleNamespace(source={})),
        )


def test_registered_request_cannot_swap_composition_trust() -> None:
    assert not hasattr(evidence, "verify_registered_approval_execution")
    request_parameters = signature(evidence.RegisteredApprovalExecutor.execute).parameters
    assert {
        "authority",
        "resolver",
        "allow_test_watermark_fallback",
        "allow_test_file_fence",
        "independent_generation_verifier",
        "independent_verification",
    }.isdisjoint(request_parameters)


def test_pinned_isolated_verifier_executes_current_raw_byte_protocol() -> None:
    implementation = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/cgs_structural_manifest_prototype.py"
    design = (ROOT / "docs/design/semantic_ingestion_architecture.md").read_bytes()
    registry = (ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json").read_bytes()
    ledger = (ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json").read_bytes()
    with TemporaryDirectory() as directory:
        root = Path(directory)
        paths = [root / name for name in ("design", "registry", "ledger", "output")]
        for path, raw in zip(paths[:3], (design, registry, ledger), strict=True):
            path.write_bytes(raw)
        subprocess.run([sys.executable, "-I", str(implementation), *(str(path) for path in paths)], check=True, capture_output=True)
        emitted = json.loads(paths[3].read_bytes())
    body = bytes.fromhex(emitted["body_bytes_hex"])
    envelope = bytes.fromhex(emitted["envelope_bytes_hex"])
    emitted_spool = bytes.fromhex(emitted["structural_spool_bytes_hex"])
    verifier = evidence.PinnedIsolatedIndependentGenerationVerifier(implementation)
    result = verifier.verify(
        design_bytes=design, registry_bytes=registry, ledger_bytes=ledger,
        expected_body_bytes=body, expected_envelope_bytes=envelope,
    )
    evidence._verify_independent_structural_result(result, body=body, envelope=envelope)
    assert result.structural_spool_bytes == emitted_spool
    with pytest.raises(evidence.ExecutionEvidenceError, match="identity mismatch"):
        evidence.PinnedIsolatedIndependentGenerationVerifier(
            implementation, implementation_sha256="0" * 64
        ).verify(
            design_bytes=design, registry_bytes=registry, ledger_bytes=ledger,
            expected_body_bytes=body, expected_envelope_bytes=envelope,
        )
    with pytest.raises(evidence.ExecutionEvidenceError, match="disagrees"):
        verifier.verify(
            design_bytes=design, registry_bytes=registry, ledger_bytes=ledger,
            expected_body_bytes=body + b"x", expected_envelope_bytes=envelope,
        )


def test_clean_room_b_parser_and_parent_total_deadlines_are_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    implementation = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/cgs_structural_manifest_prototype.py"
    namespace = runpy.run_path(str(implementation), run_name="clean_room_b_test")
    derive = namespace["derive"]
    ticks = iter((0.0, 31.0))
    derive.__globals__["monotonic"] = lambda: next(ticks)
    with pytest.raises(TimeoutError, match="parser deadline exceeded"):
        derive(b"## 1. Scope\n", b"{}", b"{}")

    def total_timeout(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired("clean-room-b", 60)

    monkeypatch.setattr(evidence.subprocess, "run", total_timeout)
    with pytest.raises(evidence.ExecutionEvidenceError, match="total deadline exceeded"):
        evidence.PinnedIsolatedIndependentGenerationVerifier(implementation).verify(
            design_bytes=b"design", registry_bytes=b"registry", ledger_bytes=b"ledger",
            expected_body_bytes=b"body", expected_envelope_bytes=b"envelope",
        )


def test_a_unit_and_b_heading_extraction_expire_inside_scans() -> None:
    calls = 0

    def expire_a() -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise TimeoutError("A extraction expired")

    with pytest.raises(TimeoutError, match="A extraction expired"):
        extract_normative_units(
            b"## 1. Scope\nfirst paragraph\n## 5. End\nlast paragraph\n## 6. Outside\n",
            check=expire_a,
        )

    implementation = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/cgs_structural_manifest_prototype.py"
    headings = runpy.run_path(str(implementation), run_name="clean_room_b_headings")["headings"]
    calls = 0

    def expire_b() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TimeoutError("B headings expired")

    with pytest.raises(TimeoutError, match="B headings expired"):
        headings(b"## 1. Scope\n### 1.1 Detail\n", check=expire_b)


def test_a_and_b_no_heading_scans_remain_cooperatively_bounded() -> None:
    def expiring_check() -> None:
        expiring_check.calls += 1
        if expiring_check.calls == 4:
            raise TimeoutError("no-heading scan expired")

    expiring_check.calls = 0  # type: ignore[attr-defined]
    with pytest.raises(TimeoutError, match="no-heading scan expired"):
        extract_normative_units(b"plain\ntext\nwithout\nheadings\n", check=expiring_check)

    implementation = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/cgs_structural_manifest_prototype.py"
    headings = runpy.run_path(str(implementation), run_name="clean_room_b_no_headings")["headings"]
    expiring_check.calls = 0  # type: ignore[attr-defined]
    with pytest.raises(TimeoutError, match="no-heading scan expired"):
        headings(b"plain\ntext\nwithout\nheadings\n", check=expiring_check)


def test_b_internal_parse_watchdog_is_injectable_and_fail_closed() -> None:
    implementation = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/cgs_structural_manifest_prototype.py"
    watchdog = runpy.run_path(str(implementation), run_name="clean_room_b_watchdog")["parse_watchdog"]

    class FakeSignal:
        SIGALRM = 1
        ITIMER_REAL = 2
        handler: object = None

        @classmethod
        def getsignal(cls, _signal: int) -> object:
            return None

        @classmethod
        def signal(cls, _signal: int, handler: object) -> None:
            cls.handler = handler

        @classmethod
        def setitimer(cls, _timer: int, seconds: float) -> None:
            if seconds > 0:
                assert callable(cls.handler)
                cls.handler(cls.SIGALRM, None)

    with pytest.raises(TimeoutError, match="parser deadline exceeded"), watchdog(signal_module=FakeSignal):
            raise AssertionError("watchdog did not fire")


def test_non_nfc_design_rejects_at_both_a_boundaries() -> None:
    raw = "## 1. Cafe\u0301\n## 5. End\n".encode()
    with pytest.raises(manifest.StructuralManifestError, match="NFC-normalized"):
        manifest._validate_raw_design_bytes(raw)
    with pytest.raises(TraceabilityCoverageError, match="NFC-normalized"):
        checker._validate_raw_design_bytes(raw)


def test_b_single_parser_watchdog_covers_unicode_normalization() -> None:
    implementation = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/cgs_structural_manifest_prototype.py"
    namespace = runpy.run_path(str(implementation), run_name="clean_room_b_remaining")
    derive = namespace["derive"]
    observed: list[float] = []
    active = False

    @contextmanager
    def watchdog(seconds: float) -> Any:
        nonlocal active
        observed.append(seconds)
        active = True
        try:
            yield
        finally:
            active = False

    derive.__globals__["parse_watchdog"] = watchdog
    unicode_module = derive.__globals__["unicodedata"]

    def normalize(*_args: object) -> str:
        assert active
        raise TimeoutError("normalizer overrun")

    original = unicode_module.normalize
    unicode_module.normalize = normalize
    try:
        with pytest.raises(TimeoutError, match="normalizer overrun"):
            derive(b"## 1. Scope\n", b"{}", b"{}")
    finally:
        unicode_module.normalize = original
    assert observed == [30]


def test_checker_worker_thread_rejects_before_valid_or_stalled_raw_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    design = (ROOT / "docs/design/semantic_ingestion_architecture.md").read_bytes()
    registry = (ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json").read_bytes()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            checker.rebuild_structural_manifest_bytes,
            design_bytes=design,
            registry=cast(Any, SimpleNamespace(source={})),
            registry_bytes=registry,
        )
        with pytest.raises(TraceabilityCoverageError, match="unavailable outside the main thread"):
            future.result()

    def forbidden_parse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("worker reached raw parser")

    monkeypatch.setattr(checker, "_validate_raw_design_bytes", forbidden_parse)
    monkeypatch.setattr(checker, "load_independent_registry_bytes", forbidden_parse)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            checker.rebuild_structural_manifest_bytes,
            design_bytes=b"## 1. Scope\n",
            registry=cast(Any, SimpleNamespace(source={})),
        )
        with pytest.raises(TraceabilityCoverageError, match="unavailable outside the main thread"):
            future.result()


def _admit(
    *,
    manifest: bytes = b"{}",
    members: dict[str, bytes] | None = None,
    design: bytes = b"d",
    registry: bytes = b"r",
    deadline: datetime | None = None,
    cancelled: Callable[[], bool] | None = None,
    retries: int = 0,
) -> None:
    evidence._verify_generation_admission(
        generation_manifest_bytes=manifest,
        generation_member_bytes=members or {"member": b"{}"},
        design_document_bytes=design,
        registry_bytes=registry,
        verification_deadline=deadline,
        cancelled=cancelled,
        retry_count=retries,
    )


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("design", "design byte limit exceeded"),
        ("registry", "registry byte limit exceeded"),
        ("artifact", "member byte limit exceeded"),
        ("total", "total byte limit exceeded"),
    ],
)
def test_admission_byte_caps_reject_before_decoding_without_mutating_inputs(
    monkeypatch: pytest.MonkeyPatch, name: str, message: str
) -> None:
    monkeypatch.setattr(evidence, "_MAX_GENERATION_MEMBER_BYTES", 4)
    monkeypatch.setattr(evidence, "_MAX_GENERATION_TOTAL_BYTES", 3 if name == "total" else 64)
    sentinel = {"state": "unchanged"}
    members = {"member": b"{}"}
    snapshot = dict(members)
    with pytest.raises(evidence.ExecutionEvidenceError, match=message):
        if name == "design":
            _admit(design=b"12345", members=members)
        elif name == "registry":
            _admit(registry=b"12345", members=members)
        elif name == "artifact":
            _admit(manifest=b"12345", members=members)
        else:
            _admit(manifest=b"{}", members=members, design=b"12", registry=b"34")
    assert sentinel == {"state": "unchanged"}
    assert members == snapshot


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        (b"[" * 257 + b"0" + b"]" * 257, "nesting depth exceeded"),
        (b"[{},{}]", "container count exceeded"),
        (b'{"a":1,"b":2}', "field count exceeded"),
    ],
)
def test_admission_ctv_shape_caps_reject_before_typed_decode(
    monkeypatch: pytest.MonkeyPatch, manifest: bytes, message: str
) -> None:
    if "container" in message:
        monkeypatch.setattr(evidence, "_MAX_CTV_CONTAINERS", 2)
    if "field" in message:
        monkeypatch.setattr(evidence, "_MAX_CTV_FIELDS", 1)
    with pytest.raises(evidence.ExecutionEvidenceError, match=message):
        _admit(manifest=manifest)


def test_admission_rejects_retry_deadline_and_cancellation_without_mutation() -> None:
    state = {"watermark": "unchanged"}
    with pytest.raises(evidence.ExecutionEvidenceError, match="retry count"):
        _admit(retries=1)
    with pytest.raises(evidence.ExecutionEvidenceError, match="deadline exceeded"):
        _admit(deadline=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(evidence.ExecutionEvidenceError, match="was cancelled"):
        _admit(cancelled=lambda: True)
    assert state == {"watermark": "unchanged"}


def test_generation_manifest_binding_is_pinned_to_the_current_authority() -> None:
    binding = evidence._GENERATION_MANIFEST_BINDING
    assert binding.profile_digest == "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f"
    assert binding.binding_digest == "9a8157b88ff3ddc299030c877a8f2cf6e95114da331174bfc1bb47836841fe69"


def test_independent_registry_rejects_above_frozen_eight_mib_before_json() -> None:
    with pytest.raises(TraceabilityCoverageError, match="8 MiB"):
        load_independent_registry_bytes(b" " * (8 * 1024 * 1024 + 1))


def test_ctv_encoding_checks_cancellation_cooperatively() -> None:
    checks = 0

    def cancel() -> None:
        nonlocal checks
        checks += 1
        if checks == 5:
            raise evidence.ExecutionEvidenceError("generation verification was cancelled")

    with pytest.raises(evidence.ExecutionEvidenceError, match="was cancelled"):
        encode_typed_value({"items": list(range(100))}, check=cancel)
    assert checks == 5


def test_independent_structural_result_requires_allowlisted_exact_body_envelope_and_spool() -> None:
    body, envelope = b"body", b"envelope"
    valid = evidence.IndependentGenerationVerificationResult(
        "memorii-sia-clean-room-b-v1",
        "b655f474e4918d64447251e40b9a3af53daca0efd2e2cb6baa76890243bae5ed",
        body,
        envelope,
        evidence.structural_verification_spool(body, envelope),
    )
    evidence._verify_independent_structural_result(
        valid, body=body, envelope=envelope
    )
    mutations = (
        None,
        evidence.IndependentGenerationVerificationResult(
            "untrusted-executor",
            valid.implementation_sha256,
            body,
            envelope,
            valid.structural_spool_bytes,
        ),
        evidence.IndependentGenerationVerificationResult(
            valid.executor_id,
            valid.implementation_sha256,
            body + b"x",
            envelope,
            valid.structural_spool_bytes,
        ),
        evidence.IndependentGenerationVerificationResult(
            valid.executor_id,
            valid.implementation_sha256,
            body,
            envelope,
            valid.structural_spool_bytes + b"x",
        ),
    )
    for mutation in mutations:
        with pytest.raises(evidence.ExecutionEvidenceError, match="disagrees"):
            evidence._verify_independent_structural_result(
                mutation, body=body, envelope=envelope
            )

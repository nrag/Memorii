"""Fail-closed acceptance for lock-bound canonical-evidence run artifacts."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from canonical_evidence_lock_resolver import (
    ARTIFACT_NAMES,
    LockResolutionError,
    ResolvedLock,
    capture_ready_source_frames,
    resolve_lock,
    sha256,
)
from canonical_evidence_production_matrix import (
    MATRIX,
    verify_static_matrix,
)
from canonical_evidence_production_matrix import (
    self_test as static_fixture_contract_self_test,
)
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[4]


class ValidationError(RuntimeError):
    pass


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _receipt_digest(receipt: dict[str, Any]) -> str:
    value = dict(receipt)
    value.pop("receipt_digest", None)
    return _digest(value)


def _trace_identity(trace: list[dict[str, Any]]) -> str:
    return _digest(trace)


def _load_record(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"object required: {path}")
    return value


def _load_execution_lock(lock: ResolvedLock, path: Path, *, kind: str, diagnostic_path: Path, latency_path: Path) -> None:
    manifest = _load_record(path)
    errors = sorted(Draft202012Validator(lock.load_json("evidence_manifest_schema")).iter_errors(manifest), key=lambda error: list(error.path))
    if errors:
        raise ValidationError(f"execution lock schema: {errors[0].message}")
    if manifest["kind"] != kind or manifest["candidate_lock_hash"] != lock.lock_hash:
        raise ValidationError("execution lock authority differs")
    if manifest["comparison_schedule_authority_hash"] != _schedule_authority(lock)[1]:
        raise ValidationError("execution lock schedule authority differs")
    expected = {"diagnostic": diagnostic_path.resolve(), "latency": latency_path.resolve()}
    observed: set[str] = set()
    for artifact in manifest["artifacts"]:
        role, artifact_path = artifact["role"], Path(artifact["path"]).resolve()
        if role in observed or artifact_path != expected[role]:
            raise ValidationError("execution lock artifact path mismatch")
        observed.add(role)
    if set(observed) != set(expected):
        raise ValidationError("execution lock is incomplete")


def _load_result_lock(lock: ResolvedLock, path: Path, *, expected_hash: str, execution_lock: Path, diagnostic_path: Path, latency_path: Path) -> dict[str, Any]:
    if sha256(path) != expected_hash:
        raise ValidationError("expected result lock hash differs")
    manifest = _load_record(path)
    errors = sorted(Draft202012Validator(lock.load_json("result_lock_schema")).iter_errors(manifest), key=lambda error: list(error.path))
    if errors:
        raise ValidationError(f"result lock schema: {errors[0].message}")
    if manifest["candidate_lock_hash"] != lock.lock_hash or manifest["execution_lock_hash"] != sha256(execution_lock):
        raise ValidationError("result lock authority differs")
    if manifest["comparison_schedule_authority_hash"] != _schedule_authority(lock)[1]:
        raise ValidationError("result lock schedule authority differs")
    expected = {"diagnostic": diagnostic_path.resolve(), "latency": latency_path.resolve()}
    observed: dict[str, tuple[Path, str]] = {}
    for artifact in manifest["artifacts"]:
        role, artifact_path, digest = artifact["role"], Path(artifact["path"]).resolve(), artifact["sha256"]
        if role in observed or artifact_path != expected[role] or not artifact_path.is_file() or sha256(artifact_path) != digest:
            raise ValidationError("result lock artifact path or hash mismatch")
        observed[role] = (artifact_path, digest)
    if set(observed) != set(expected):
        raise ValidationError("result lock is incomplete")
    durable = manifest["terminal_durable_effect_receipts"]
    if len({receipt["operation_identity"] for receipt in durable}) != 8 or len({receipt["replay_identity"] for receipt in durable}) != 8:
        raise ValidationError("result lock durable-effect receipts are duplicated")
    return manifest


def _fixture_hash(lock: ResolvedLock) -> str:
    manifest = lock.load_json("fixture_manifest")
    errors = sorted(Draft202012Validator(lock.load_json("standard_fixture_schema")).iter_errors(manifest), key=lambda error: list(error.path))
    if errors:
        raise ValidationError(f"standard fixture manifest schema: {errors[0].message}")
    inputs = manifest.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValidationError("fixture manifest has no inputs")
    seen: set[str] = set()
    for item in inputs:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValidationError("fixture input shape is invalid")
        relative = item["path"]
        target = (lock.root / relative).resolve()
        if not isinstance(relative, str) or relative in seen or lock.root not in target.parents or not target.is_file():
            raise ValidationError("fixture input missing or duplicated")
        seen.add(relative)
        if sha256(target) != item["sha256"]:
            raise ValidationError("fixture input stale or substituted")
    return sha256(lock.path("fixture_manifest"))


def _schedule_authority(lock: ResolvedLock) -> tuple[dict[str, Any], str]:
    schedule = lock.load_json("comparison_schedule_authority")
    errors = sorted(Draft202012Validator(lock.load_json("comparison_authority_schema")).iter_errors(schedule), key=lambda error: list(error.path))
    if errors:
        raise ValidationError(f"comparison schedule authority schema: {errors[0].message}")
    if schedule["fixture_hash"] != _fixture_hash(lock):
        raise ValidationError("comparison schedule fixture authority differs")
    if schedule["tool_identity"] != lock.artifacts["runner"]["sha256"] or schedule["workload_identity"] != lock.artifacts["recipe"]["sha256"]:
        raise ValidationError("comparison schedule tool or workload authority differs")
    if schedule["matrix_order"] != [f"{root}/{backend}" for root, backend in MATRIX] or set(schedule["execution_order"]) != set(schedule["matrix_order"]):
        raise ValidationError("comparison schedule order differs")
    return schedule, sha256(lock.path("comparison_schedule_authority"))


def _source_identity(lock: ResolvedLock, record: dict[str, Any], *, allow_design_time_vector: bool) -> str:
    expected = lock.artifacts["production_sources"]
    if record.get("production_source_manifest") != expected:
        raise ValidationError("exact locked production source receipt required")
    manifest = lock.load_json("production_sources")
    if manifest.get("capture_status") != "capture_ready":
        if not allow_design_time_vector or record.get("evidence_stage") != "design_time_vector":
            raise ValidationError("capture-ready production source manifest required")
        return expected["sha256"]
    try:
        capture_ready_source_frames(lock)
    except LockResolutionError as error:
        raise ValidationError(f"capture-ready source-frame inventory: {error}") from error
    return expected["sha256"]


def _validate_production_proof(lock: ResolvedLock, cell: dict[str, Any], *, source_identity: str, allow_design_time_vector: bool) -> None:
    receipt = cell["production_receipt"]
    trace = cell["production_trace"]
    receipt_errors = sorted(Draft202012Validator(lock.load_json("receipt_schema")).iter_errors(receipt), key=lambda error: list(error.path))
    if receipt_errors:
        raise ValidationError(f"production receipt schema: {receipt_errors[0].message}")
    for frame in trace:
        frame_errors = sorted(Draft202012Validator(lock.load_json("event_schema")).iter_errors(frame), key=lambda error: list(error.path))
        if frame_errors:
            raise ValidationError(f"production trace schema: {frame_errors[0].message}")
    if receipt["receipt_digest"] != _receipt_digest(receipt):
        raise ValidationError("production receipt digest differs from frozen artifact bytes")
    if receipt["trace_identity"] != _trace_identity(trace):
        raise ValidationError("production trace identity mismatch")
    if receipt["authority_digest"] != trace[0]["authority_digest"] or any(frame["authority_digest"] != receipt["authority_digest"] for frame in trace):
        raise ValidationError("production authority identity mismatch")
    if receipt["operation_identity"] != cell["operation_identity"] or any(frame["operation_identity"] != cell["operation_identity"] for frame in trace):
        raise ValidationError("production operation linkage mismatch")
    if receipt["root"] != cell["root"] or receipt["backend"] != cell["backend"] or receipt["source_revision"] != source_identity:
        raise ValidationError("production receipt cell linkage mismatch")
    durable = cell["terminal_durable_effect_receipt"]
    durable_schema = lock.load_json("receipt_schema")["$defs"]["terminal_durable_effect_receipt"]
    durable_errors = sorted(Draft202012Validator(durable_schema).iter_errors(durable), key=lambda error: list(error.path))
    if durable_errors:
        raise ValidationError(f"terminal durable-effect receipt schema: {durable_errors[0].message}")
    if any(durable[key] != cell[key] for key in ("operation_identity", "root", "backend", "source_revision")):
        raise ValidationError("terminal durable-effect receipt cell linkage mismatch")
    if durable["transaction_or_memory_durable_identity"] == durable["replay_identity"]:
        raise ValidationError("terminal durable-effect receipt replay identity is not distinct")
    root_symbol = {"direct": "memorii.core.provider.service.ProviderMemoryService.__init__", "factory": "memorii.core.provider.factory.build_provider_memory_service_from_env", "filesystem": "memorii.core.filesystem_storage.bundle.build_filesystem_provider", "hermes": "memorii.integrations.hermes_provider.HermesMemoryProvider.__init__"}[cell["root"]]
    expected = [receipt["factory_symbol"], receipt["verification_symbol"], root_symbol, "memorii.core.provider.service.ProviderMemoryService.sync_event", "memorii.core.provider.service.ProviderMemoryService._ingest_event", "memorii.core.provider.ingestion.ProviderIngestionCoordinator.ingest", "memorii.core.provider.ingestion.ProviderIngestionCoordinator._run_semantic_ingestion"]
    if [frame["order"] for frame in trace] != list(range(7)) or [frame["symbol"] for frame in trace] != expected:
        raise ValidationError("production trace is missing, reordered, substituted, or terminal-incomplete")
    if [frame["status"] for frame in trace] != ["call", "call", "call", "call", "call", "call", "return"]:
        raise ValidationError("production trace call/return sequence is invalid")
    if not allow_design_time_vector:
        try:
            frame_map = capture_ready_source_frames(lock)
        except LockResolutionError as error:
            raise ValidationError(f"capture-ready source-frame inventory: {error}") from error
        for frame in trace:
            expected_source = frame_map.get(frame["symbol"])
            if expected_source != {"path": frame["source_path"], "sha256": frame["source_sha256"]}:
                raise ValidationError("production trace source path/hash is not the exact root-specific locked mapping")


def _validate_schema(lock: ResolvedLock, record: dict[str, Any]) -> None:
    errors = sorted(Draft202012Validator(lock.load_json("performance_schema")).iter_errors(record), key=lambda error: list(error.path))
    if errors:
        raise ValidationError(f"performance schema: {errors[0].message}")
    required = "profiled_code_identity" if record["mode"] == "diagnostic_profiled_non_latency" else "wall_ns_samples"
    if any(required not in cell for cell in record["cells"]):
        raise ValidationError(f"performance mode requires {required}")


def _validate_cells(lock: ResolvedLock, record: dict[str, Any], source_identity: str, *, allow_design_time_vector: bool) -> None:
    cells = record["cells"]
    if [(cell["root"], cell["backend"]) for cell in cells] != list(MATRIX) or [cell["ordinal"] for cell in cells] != list(range(8)):
        raise ValidationError("matrix cells are not exact")
    if len({cell["operation_identity"] for cell in cells}) != 8 or len({cell["trigger_receipt"] for cell in cells}) != 8:
        raise ValidationError("cross-cell operation or receipt reuse")
    nonces = [cell.get("arena_nonce") for cell in cells]
    if record["kind"] == "candidate" and (None in nonces or len(set(nonces)) != 8):
        raise ValidationError("candidate nonce absent or reused")
    schedule, schedule_hash = _schedule_authority(lock)
    if record["comparison_schedule_authority_hash"] != schedule_hash or record["execution_order"] != schedule["execution_order"] or record["retained_ordinals"] != schedule["retained_ordinals"]:
        raise ValidationError("record does not bind the shared pre-capture schedule authority")
    total = 0
    for cell in cells:
        if cell["source_revision"] != source_identity:
            raise ValidationError("cell source revision is not the verified production implementation identity")
        if cell["retained_ordinals"] != schedule["retained_ordinals"] or len(cell["wall_ns_samples"]) != len(schedule["retained_ordinals"]):
            raise ValidationError("warmup contamination or retained sample schedule mismatch")
        identities = cell["per_identity"]
        if cell["eligible"] != cell["unique"] + cell["repeated"] or cell["unique"] != len(identities):
            raise ValidationError("cell arithmetic failed")
        if record["kind"] == "candidate" and any(count != 1 for count in identities.values()):
            raise ValidationError("candidate digest count must equal one per eligible identity")
        if cell["global"] < cell["eligible"] + cell["direct_non_eligible"] or cell["global"] > 1000:
            raise ValidationError("cell global counter failed")
        total += cell["global"]
        _validate_production_proof(lock, cell, source_identity=source_identity, allow_design_time_vector=allow_design_time_vector)
    if record["aggregate_global"] != total or total > 8000:
        raise ValidationError("aggregate capacity exceeded")
    verify_static_matrix(
        binding_map=lock.load_json("binding_map"),
        runner_source=lock.path("runner").read_text(encoding="utf-8"),
        recipe_source=lock.path("recipe").read_text(encoding="utf-8"),
    )


def validate_record(record: dict[str, Any], *, allow_design_time_vector: bool = False, authority_lock: ResolvedLock | None = None) -> ResolvedLock:
    try:
        lock = authority_lock or resolve_lock(ROOT, expected_lock_hash=record.get("candidate_lock_hash"))
    except LockResolutionError as error:
        raise ValidationError(str(error)) from error
    _validate_schema(lock, record)
    if record.get("evidence_stage") == "design_time_vector" and not allow_design_time_vector:
        raise ValidationError("design-time vector is not acceptance evidence")
    if record["fixture_hash"] != _fixture_hash(lock):
        raise ValidationError("fixture hash is not the verified locked manifest hash")
    source_identity = _source_identity(lock, record, allow_design_time_vector=allow_design_time_vector)
    if record["implementation_identity"] != source_identity:
        raise ValidationError("arbitrary implementation identity")
    _validate_cells(lock, record, source_identity, allow_design_time_vector=allow_design_time_vector)
    return lock


def _record_hash(record: dict[str, Any]) -> str:
    return _digest(record)


def _terminal_receipts(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [cell["terminal_durable_effect_receipt"] for cell in record["cells"]]


def validate_pair(
    diagnostic: dict[str, Any],
    latency: dict[str, Any],
    *,
    allow_design_time_vector: bool = False,
    authority_lock: ResolvedLock | None = None,
) -> ResolvedLock:
    """Validate one side only against its already resolved authority lock."""
    diagnostic_lock = validate_record(
        diagnostic,
        allow_design_time_vector=allow_design_time_vector,
        authority_lock=authority_lock,
    )
    latency_lock = validate_record(
        latency,
        allow_design_time_vector=allow_design_time_vector,
        authority_lock=authority_lock,
    )
    if diagnostic_lock != latency_lock:
        raise ValidationError("paired records resolved different authority locks")
    if diagnostic["mode"] != "diagnostic_profiled_non_latency" or latency["mode"] != "latency_unprofiled":
        raise ValidationError("mode linkage failed")
    if latency.get("diagnostic_run_hash") != _record_hash(diagnostic):
        raise ValidationError("latency does not bind diagnostic")
    for key in ("kind", "fixture_hash", "candidate_lock_hash", "implementation_identity", "production_source_manifest", "environment_identity", "algorithm_identity"):
        if diagnostic[key] != latency[key]:
            raise ValidationError("paired evidence authority differs")
    for diagnostic_cell, latency_cell in zip(diagnostic["cells"], latency["cells"], strict=True):
        for key in ("ordinal", "root", "backend", "operation_identity", "trigger_receipt", "source_revision", "production_receipt", "production_trace", "terminal_durable_effect_receipt", "diagnostic_cell_hash"):
            if diagnostic_cell[key] != latency_cell[key]:
                raise ValidationError("latency cell does not bind exact diagnostic identity")
    return diagnostic_lock


def _q95(values: list[int]) -> float:
    values = sorted(values)
    return values[(95 * len(values) + 99) // 100 - 1]


def _accept(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    for base, proposed in zip(baseline["cells"], candidate["cells"], strict=True):
        if statistics.median(proposed["wall_ns_samples"]) > statistics.median(base["wall_ns_samples"]) * .75:
            raise ValidationError("candidate median threshold failed")
        if _q95(proposed["wall_ns_samples"]) / statistics.median(proposed["wall_ns_samples"]) > 1.5:
            raise ValidationError("candidate p95 threshold failed")
    if candidate["rss"]["delta_bytes"] > 134217728:
        raise ValidationError("candidate RSS threshold failed")


def _self_test_record(
    *,
    kind: str = "candidate",
    mode: str = "diagnostic_profiled_non_latency",
    authority_lock: ResolvedLock | None = None,
    evidence_stage: str = "design_time_vector",
) -> dict[str, Any]:
    lock = authority_lock or resolve_lock(ROOT)
    fixture = _fixture_hash(lock)
    schedule, schedule_hash = _schedule_authority(lock)
    source_identity = lock.artifacts["production_sources"]["sha256"]
    def proof(ordinal: int, root: str, backend: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        authority = f"{ordinal:064x}"
        root_symbol = {"direct": "memorii.core.provider.service.ProviderMemoryService.__init__", "factory": "memorii.core.provider.factory.build_provider_memory_service_from_env", "filesystem": "memorii.core.filesystem_storage.bundle.build_filesystem_provider", "hermes": "memorii.integrations.hermes_provider.HermesMemoryProvider.__init__"}[root]
        symbols = ["memorii.core.semantic_ingestion.production_authority.build_verified_production_host_authority", "memorii.core.memory_evolution.bootstrap_profile.HostBootstrapMaterialVerifier.verify", root_symbol, "memorii.core.provider.service.ProviderMemoryService.sync_event", "memorii.core.provider.service.ProviderMemoryService._ingest_event", "memorii.core.provider.ingestion.ProviderIngestionCoordinator.ingest", "memorii.core.provider.ingestion.ProviderIngestionCoordinator._run_semantic_ingestion"]
        frame_map = capture_ready_source_frames(lock) if evidence_stage != "design_time_vector" else None
        trace = [{"order": order, "symbol": symbol, "source_path": frame_map[symbol]["path"] if frame_map else "memorii/memorii/core/semantic_ingestion/production_authority.py" if order == 0 else "memorii/memorii/core/provider/service.py", "source_sha256": frame_map[symbol]["sha256"] if frame_map else source_identity, "status": "return" if order == 6 else "call", "authority_digest": authority, "operation_identity": f"o-{ordinal}"} for order, symbol in enumerate(symbols)]
        receipt = {"schema": "memorii.semantic-ingestion.canonical-evidence.production-receipt.v4", "receipt_digest": "", "authority_digest": authority, "verified_material_digest": source_identity, "verification_digest": source_identity, "trust_domain": "production", "factory_symbol": symbols[0], "verification_symbol": symbols[1], "root_symbol": root_symbol, "root": root, "backend": backend, "operation_identity": f"o-{ordinal}", "source_revision": source_identity, "trace_identity": _trace_identity(trace), "integrity_mechanism": "opaque-object-identity-pre-serialization-plus-frozen-result-lock-v2"}
        receipt["receipt_digest"] = _receipt_digest(receipt)
        return receipt, trace
    cells = [{
        "ordinal": ordinal, "root": root, "backend": backend, "trigger_receipt": f"r-{ordinal}",
        "operation_identity": f"o-{ordinal}", "source_revision": source_identity,
        "arena_nonce": f"n-{ordinal}", "eligible": 1, "unique": 1, "repeated": 0,
        "per_identity": {f"id-{ordinal}": 1}, "direct_non_eligible": 0, "global": 1,
        "diagnostic_cell_hash": _digest({"ordinal": ordinal, "root": root, "backend": backend}), "production_receipt": proof(ordinal, root, backend)[0], "production_trace": proof(ordinal, root, backend)[1],
        "terminal_durable_effect_receipt": {"schema": "memorii.semantic-ingestion.canonical-evidence.terminal-durable-effect-receipt.v1", "operation_identity": f"o-{ordinal}", "root": root, "backend": backend, "source_revision": source_identity, "transaction_or_memory_durable_identity": f"durable-{ordinal}", "effect_digest": f"{ordinal + 1:064x}", "terminal_status": "successful_durable_terminal", "replay_identity": f"replay-{ordinal}", "no_duplicate_count": 1},
        "wall_ns_samples": [100] * 20, "retained_ordinals": schedule["retained_ordinals"], "profiled_code_identity": "canonical-digest-code",
    } for ordinal, (root, backend) in enumerate(MATRIX)]
    return {
        "schema": "memorii.semantic-ingestion.canonical-evidence.performance-run.v5", "evidence_stage": evidence_stage, "kind": kind, "mode": mode,
        "fixture_hash": fixture, "candidate_lock_hash": lock.lock_hash, "implementation_identity": source_identity,
        "production_source_manifest": lock.artifacts["production_sources"], "environment_identity": schedule["environment_identity"],
        "algorithm_identity": "canonical-evidence-v4", "comparison_schedule_authority_hash": schedule_hash, "execution_order": schedule["execution_order"], "retained_ordinals": schedule["retained_ordinals"], "cells": cells, "aggregate_global": 8,
        "rss": {"source": "child:RUSAGE_SELF", "platform_units": "darwin_bytes", "delta_bytes": 0},
    }


def _must_reject(name: str, record: dict[str, Any]) -> None:
    try:
        validate_record(record, allow_design_time_vector=True)
    except ValidationError:
        return
    raise ValidationError(f"self-test mutation accepted: {name}")


def _must_reject_frozen_artifact_mutation(name: str, original: dict[str, Any], forged: dict[str, Any]) -> None:
    lock = resolve_lock(ROOT)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        diagnostic = root / "diagnostic.json"
        latency = root / "latency.json"
        manifest_path = root / "baseline-manifest.json"
        diagnostic.write_text(json.dumps(original, sort_keys=True), encoding="utf-8")
        latency.write_text(json.dumps(original, sort_keys=True), encoding="utf-8")
        manifest_path.write_text(json.dumps({"schema": "memorii.semantic-ingestion.canonical-evidence.execution-lock.v2", "kind": "baseline", "candidate_lock_hash": lock.lock_hash, "comparison_schedule_authority_hash": _schedule_authority(lock)[1], "artifacts": [{"role": "diagnostic", "path": str(diagnostic)}, {"role": "latency", "path": str(latency)}]}, sort_keys=True), encoding="utf-8")
        diagnostic.write_text(json.dumps(forged, sort_keys=True), encoding="utf-8")
        try:
            _load_execution_lock(lock, manifest_path, kind="baseline", diagnostic_path=diagnostic, latency_path=latency)
        except ValidationError:
            return
    raise ValidationError(f"self-test frozen mutation accepted: {name}")


def _must_reject_result_lock_replacement(name: str, original: dict[str, Any], forged: dict[str, Any]) -> None:
    lock = resolve_lock(ROOT)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        diagnostic, latency = root / "diagnostic.json", root / "latency.json"
        execution_lock, result_lock = root / "execution-lock.json", root / "result-lock.json"
        diagnostic.write_text(json.dumps(original, sort_keys=True), encoding="utf-8")
        latency.write_text(json.dumps(original, sort_keys=True), encoding="utf-8")
        execution_lock.write_text(json.dumps({"schema": "memorii.semantic-ingestion.canonical-evidence.execution-lock.v2", "kind": "baseline", "candidate_lock_hash": lock.lock_hash, "comparison_schedule_authority_hash": _schedule_authority(lock)[1], "artifacts": [{"role": "diagnostic", "path": str(diagnostic)}, {"role": "latency", "path": str(latency)}]}, sort_keys=True), encoding="utf-8")
        result_lock.write_text(json.dumps({"schema": "memorii.semantic-ingestion.canonical-evidence.result-lock.v2", "candidate_lock_hash": lock.lock_hash, "execution_lock_hash": sha256(execution_lock), "comparison_schedule_authority_hash": _schedule_authority(lock)[1], "artifacts": [{"role": "diagnostic", "path": str(diagnostic), "sha256": sha256(diagnostic)}, {"role": "latency", "path": str(latency), "sha256": sha256(latency)}], "terminal_durable_effect_receipts": _terminal_receipts(original)}, sort_keys=True), encoding="utf-8")
        expected_result_lock = sha256(result_lock)
        diagnostic.write_text(json.dumps(forged, sort_keys=True), encoding="utf-8")
        execution_lock.write_text(json.dumps({"schema": "memorii.semantic-ingestion.canonical-evidence.execution-lock.v2", "kind": "baseline", "candidate_lock_hash": lock.lock_hash, "comparison_schedule_authority_hash": _schedule_authority(lock)[1], "artifacts": [{"role": "diagnostic", "path": str(diagnostic)}, {"role": "latency", "path": str(latency)}]}, sort_keys=True), encoding="utf-8")
        result_lock.write_text(json.dumps({"schema": "memorii.semantic-ingestion.canonical-evidence.result-lock.v2", "candidate_lock_hash": lock.lock_hash, "execution_lock_hash": sha256(execution_lock), "comparison_schedule_authority_hash": _schedule_authority(lock)[1], "artifacts": [{"role": "diagnostic", "path": str(diagnostic), "sha256": sha256(diagnostic)}, {"role": "latency", "path": str(latency), "sha256": sha256(latency)}], "terminal_durable_effect_receipts": _terminal_receipts(forged)}, sort_keys=True), encoding="utf-8")
        try:
            _load_result_lock(lock, result_lock, expected_hash=expected_result_lock, execution_lock=execution_lock, diagnostic_path=diagnostic, latency_path=latency)
        except ValidationError:
            return
    raise ValidationError(f"self-test result-lock replacement accepted: {name}")


def _must_reject_fixture(name: str, lock: ResolvedLock, manifest: dict[str, Any]) -> None:
    original = lock.load_json
    object.__setattr__(lock, "load_json", lambda artifact: manifest if artifact == "fixture_manifest" else original(artifact))
    try:
        _fixture_hash(lock)
    except ValidationError:
        return
    finally:
        object.__setattr__(lock, "load_json", original)
    raise ValidationError(f"self-test fixture mutation accepted: {name}")


def _self_test_lock_artifacts() -> None:
    lock_path = ROOT / "docs/design/semantic_ingestion_canonical_evidence/candidate-lock-v1.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory) / "candidate-lock-v1.json"
        for name in ARTIFACT_NAMES:
            bad = copy.deepcopy(lock)
            bad["artifacts"][name]["sha256"] = "0" * 64
            temporary.write_text(json.dumps(bad, sort_keys=True), encoding="utf-8")
            try:
                resolve_lock(ROOT, lock_path=temporary)
            except LockResolutionError:
                continue
            raise ValidationError(f"self-test lock artifact mutation accepted: {name}")


def _self_test_source_frame_inventory() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        for relative, contents in (("production/a.py", "a\n"), ("production/b.py", "b\n")):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents, encoding="utf-8")
        sources = [{"path": relative, "sha256": sha256(root / relative)} for relative in ("production/a.py", "production/b.py")]
        frames = [
            {"symbol": "owner.a", **sources[0]},
            {"symbol": "owner.b", **sources[1]},
        ]
        transition = {"required_symbols": [frame["symbol"] for frame in frames], "required_paths": [source["path"] for source in sources], "rule": "self-test"}
        manifest = {"schema": "self-test", "capture_status": "capture_ready", "sources": sources, "source_frames": frames, "capture_ready_transition": transition}
        bindings = {"production_entrypoint_bindings": [{"requirement": "public_matrix", "source_frame_map": {frame["symbol"]: {"path": frame["path"], "sha256": frame["sha256"]} for frame in frames}}]}
        manifest_path, bindings_path = root / "manifest.json", root / "bindings.json"
        lock = ResolvedLock(root=root, lock_path=root / "lock.json", lock_hash="0" * 64, artifacts={"production_sources": {"path": "manifest.json", "sha256": "0" * 64}, "binding_map": {"path": "bindings.json", "sha256": "0" * 64}})

        def write_authorities(candidate: dict[str, Any]) -> None:
            manifest_path.write_text(json.dumps(candidate), encoding="utf-8")
            bindings_path.write_text(json.dumps(bindings), encoding="utf-8")

        write_authorities(manifest)
        capture_ready_source_frames(lock)
        mutations = {
            "source_frame_duplicate": lambda value: value["source_frames"][1].__setitem__("symbol", "owner.a"),
            "source_frame_omission": lambda value: value["source_frames"].pop(),
            "source_frame_extra": lambda value: value["source_frames"].append({"symbol": "owner.extra", **sources[0]}),
            "source_frame_wrong_owner": lambda value: value["source_frames"][0].__setitem__("symbol", "owner.wrong"),
            "source_frame_fake_digest": lambda value: value["source_frames"][0].__setitem__("sha256", "0" * 64),
            "source_frame_sentinel": lambda value: value["source_frames"][0].__setitem__("sha256", "unavailable_until_capture_ready"),
            "source_frame_all_symbols_one_valid_source": lambda value: value["source_frames"][1].update(path=sources[0]["path"], sha256=sources[0]["sha256"]),
        }
        for name, mutate in mutations.items():
            candidate = copy.deepcopy(manifest)
            mutate(candidate)
            write_authorities(candidate)
            try:
                capture_ready_source_frames(lock)
            except LockResolutionError:
                continue
            raise ValidationError(f"self-test source-frame mutation accepted: {name}")


def _self_test_preimport_source_frame_rejections() -> None:
    """Prove the shell trust boundary rejects locked malformed frames before Python."""
    static_lock_path = ROOT / "docs/design/semantic_ingestion_canonical_evidence/candidate-lock-v1.json"
    static_lock = json.loads(static_lock_path.read_text(encoding="utf-8"))
    if not isinstance(static_lock, dict):
        raise ValidationError("self-test candidate lock must be an object")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        for artifact in static_lock["artifacts"].values():
            source = ROOT / artifact["path"]
            target = root / artifact["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        launcher = root / static_lock["artifacts"]["preimport_launcher"]["path"]
        lock_path = root / "docs/design/semantic_ingestion_canonical_evidence/candidate-lock-v1.json"
        source_paths = ("production/a.py", "production/b.py")
        for relative, contents in zip(source_paths, ("owner_a\n", "owner_b\n"), strict=True):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents, encoding="utf-8")
        sources = [{"path": relative, "sha256": sha256(root / relative)} for relative in source_paths]
        frames = [
            {"symbol": "owner.a", **sources[0]},
            {"symbol": "owner.b", **sources[1]},
        ]
        transition = {
            "required_symbols": [frame["symbol"] for frame in frames],
            "required_paths": [source["path"] for source in sources],
            "rule": "isolated launcher self-test",
        }
        manifest = {
            "schema": "self-test",
            "capture_status": "capture_ready",
            "sources": sources,
            "source_frames": frames,
            "capture_ready_transition": transition,
        }
        binding_map = {
            "production_entrypoint_bindings": [{
                "requirement": "public_matrix",
                "source_frame_map": {
                    frame["symbol"]: {"path": frame["path"], "sha256": frame["sha256"]}
                    for frame in frames
                },
            }],
        }
        runner_path = root / static_lock["artifacts"]["runner"]["path"]
        runner_source = runner_path.read_text(encoding="utf-8")
        grammar_validator = root / static_lock["artifacts"]["recipe"]["path"]
        fake_interpreter = root / ".venv/bin/python"
        fake_interpreter.parent.mkdir(parents=True)
        fake_interpreter.write_text(
            "#!/bin/sh\n"
            "if [ \"$2\" = \"$CANONICAL_EVIDENCE_GRAMMAR_VALIDATOR\" ]; then\n"
            "  printf verifier > \"$CANONICAL_EVIDENCE_VERIFIER_SENTINEL\"\n"
            f"  exec {shlex.quote(sys.executable)} \"$@\"\n"
            "fi\n"
            "if [ \"$2\" = \"$CANONICAL_EVIDENCE_RUNNER_TARGET\" ]; then\n"
            "  printf target > \"$CANONICAL_EVIDENCE_RUNNER_TARGET_SENTINEL\"\n"
            "  exit 97\n"
            "fi\n"
            "exit 98\n",
            encoding="utf-8",
        )
        fake_interpreter.chmod(0o755)

        def write_candidate(candidate: dict[str, Any], candidate_runner_source: str = runner_source) -> str:
            production_sources = root / static_lock["artifacts"]["production_sources"]["path"]
            production_sources.write_text(json.dumps(candidate, sort_keys=True), encoding="utf-8")
            bindings = root / static_lock["artifacts"]["binding_map"]["path"]
            bindings.write_text(json.dumps(binding_map, sort_keys=True), encoding="utf-8")
            runner_path.write_text(candidate_runner_source, encoding="utf-8")
            lock = copy.deepcopy(static_lock)
            for artifact in lock["artifacts"].values():
                artifact["sha256"] = sha256(root / artifact["path"])
            lock_path.write_text(json.dumps(lock, sort_keys=True), encoding="utf-8")
            return sha256(lock_path)

        def assert_rejected(name: str, expected_lock: str, *, verifier_expected: bool) -> None:
            execution_lock = root / f"{name}.execution-lock.json"
            result_lock = root / f"{name}.result-lock.json"
            verifier_sentinel = root / f"{name}.verifier-invoked"
            runner_target_sentinel = root / f"{name}.runner-target-invoked"
            environment = dict(os.environ)
            environment["CANONICAL_EVIDENCE_GRAMMAR_VALIDATOR"] = str(grammar_validator)
            environment["CANONICAL_EVIDENCE_RUNNER_TARGET"] = str(runner_path)
            environment["CANONICAL_EVIDENCE_VERIFIER_SENTINEL"] = str(verifier_sentinel)
            environment["CANONICAL_EVIDENCE_RUNNER_TARGET_SENTINEL"] = str(runner_target_sentinel)
            completed = subprocess.run(
                [
                    str(launcher), expected_lock, sha256(launcher), "capture",
                    "--execution-lock", str(execution_lock),
                    "--result-lock", str(result_lock),
                    "--diagnostic", str(root / f"{name}.diagnostic.json"),
                    "--latency", str(root / f"{name}.latency.json"),
                    "--kind", "candidate",
                ],
                cwd=root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            if (
                completed.returncode != 64
                or execution_lock.exists()
                or result_lock.exists()
                or verifier_sentinel.exists() != verifier_expected
                or runner_target_sentinel.exists()
            ):
                raise ValidationError(f"pre-import launcher mutation did not preserve verifier/runner/lock ordering: {name}")

        outer_lock = write_candidate(manifest)
        lock_path.write_text(lock_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        assert_rejected("outer_lock_tamper", outer_lock, verifier_expected=False)
        mutations = {
            "source_frame_duplicate": lambda value: value["source_frames"][1].__setitem__("symbol", "owner.a"),
            "source_frame_omission": lambda value: value["source_frames"].pop(),
            "source_frame_extra": lambda value: value["source_frames"].append({"symbol": "owner.extra", **sources[0]}),
            "source_frame_wrong_owner": lambda value: value["source_frames"][0].__setitem__("symbol", "owner.wrong"),
            "source_frame_fake_digest": lambda value: value["source_frames"][0].__setitem__("sha256", "0" * 64),
            "source_frame_sentinel": lambda value: value["source_frames"][0].__setitem__("sha256", "unavailable_until_capture_ready"),
            "source_frame_all_symbols_one_valid_source": lambda value: value["source_frames"][1].update(path=sources[0]["path"], sha256=sources[0]["sha256"]),
        }
        for name, mutate in mutations.items():
            candidate = copy.deepcopy(manifest)
            mutate(candidate)
            assert_rejected(name, write_candidate(candidate), verifier_expected=False)
        grammar_mutations = {
            "preimport_function_type_comment": runner_source.replace("operation):", "operation):  # type: (object, object, object, object) -> object", 1),
            "preimport_assignment_type_comment": runner_source.replace('server_time=cell["server_time"])', 'server_time=cell["server_time"])  # type: object', 1),
            "preimport_type_ignore": runner_source.replace('CAPTURE_ENTRYPOINT = "_execute_declared_cell"', 'CAPTURE_ENTRYPOINT = "_execute_declared_cell"  # type: ignore', 1),
        }
        for name, candidate_runner_source in grammar_mutations.items():
            assert_rejected(
                name,
                write_candidate(manifest, candidate_runner_source),
                verifier_expected=True,
            )


def _self_test_external_preimport_topology() -> None:
    """Exercise bind and validate through the real external pre-import CLI."""
    static_lock = resolve_lock(ROOT)
    launcher = ROOT / static_lock.artifacts["preimport_launcher"]["path"]

    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory).resolve()

        def authority_root(name: str) -> tuple[Path, ResolvedLock]:
            root = workspace / name
            lock_data = json.loads(static_lock.lock_path.read_text(encoding="utf-8"))
            for artifact in lock_data["artifacts"].values():
                source, target = ROOT / artifact["path"], root / artifact["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            fixture_inputs = json.loads((root / lock_data["artifacts"]["fixture_manifest"]["path"]).read_text(encoding="utf-8"))["inputs"]
            for fixture_input in fixture_inputs:
                source, target = ROOT / fixture_input["path"], root / fixture_input["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            manifest_path = root / lock_data["artifacts"]["production_sources"]["path"]
            binding_path = root / lock_data["artifacts"]["binding_map"]["path"]
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            binding = json.loads(binding_path.read_text(encoding="utf-8"))
            source_by_path: dict[str, str] = {}
            for relative in manifest["capture_ready_transition"]["required_paths"]:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f"{name}:{relative}\n", encoding="utf-8")
                source_by_path[relative] = sha256(target)
            manifest["capture_status"] = "capture_ready"
            manifest["sources"] = [{"path": path, "sha256": digest} for path, digest in source_by_path.items()]
            manifest["source_frames"] = [
                {"symbol": frame["symbol"], "path": frame["path"], "sha256": source_by_path[frame["path"]]}
                for frame in manifest["source_frames"]
            ]
            binding["production_entrypoint_bindings"][0]["source_frame_map"] = {
                frame["symbol"]: {"path": frame["path"], "sha256": frame["sha256"]}
                for frame in manifest["source_frames"]
            }
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
            binding_path.write_text(json.dumps(binding, sort_keys=True), encoding="utf-8")
            for artifact in lock_data["artifacts"].values():
                artifact["sha256"] = sha256(root / artifact["path"])
            lock_path = root / "docs/design/semantic_ingestion_canonical_evidence/candidate-lock-v1.json"
            lock_path.write_text(json.dumps(lock_data, sort_keys=True), encoding="utf-8")
            return root, resolve_lock(root, lock_path=lock_path)

        _, baseline_lock = authority_root("baseline")
        candidate_root, candidate_lock = authority_root("candidate")

        def records(lock: ResolvedLock, kind: str, prefix: str, baseline_latency_hash: str | None = None) -> tuple[Path, Path]:
            diagnostic = _self_test_record(kind=kind, authority_lock=lock, evidence_stage="implementation_capture")
            latency = copy.deepcopy(diagnostic)
            latency["mode"] = "latency_unprofiled"
            for cell in latency["cells"]:
                cell.pop("profiled_code_identity")
                cell["wall_ns_samples"] = [100 if kind == "candidate" else 200] * 20
            latency["diagnostic_run_hash"] = _record_hash(diagnostic)
            if baseline_latency_hash is not None:
                latency["baseline_run_hash"] = baseline_latency_hash
            diagnostic_path, latency_path = workspace / f"{prefix}.diagnostic.json", workspace / f"{prefix}.latency.json"
            diagnostic_path.write_text(json.dumps(diagnostic, sort_keys=True), encoding="utf-8")
            latency_path.write_text(json.dumps(latency, sort_keys=True), encoding="utf-8")
            return diagnostic_path, latency_path

        base_diagnostic, base_latency = records(baseline_lock, "baseline", "baseline")
        candidate_diagnostic, candidate_latency = records(candidate_lock, "candidate", "candidate", _record_hash(_load_record(base_latency)))

        def side_locks(lock: ResolvedLock, kind: str, prefix: str, diagnostic: Path, latency: Path) -> tuple[Path, Path]:
            execution, result = workspace / f"{prefix}.execution.json", workspace / f"{prefix}.result.json"
            execution.write_text(json.dumps({"schema": "memorii.semantic-ingestion.canonical-evidence.execution-lock.v2", "kind": kind, "candidate_lock_hash": lock.lock_hash, "comparison_schedule_authority_hash": _schedule_authority(lock)[1], "artifacts": [{"role": "diagnostic", "path": str(diagnostic)}, {"role": "latency", "path": str(latency)}]}, sort_keys=True), encoding="utf-8")
            durable = [cell.get("terminal_durable_effect_receipt", {}) for cell in _load_record(diagnostic)["cells"]]
            result.write_text(json.dumps({"schema": "memorii.semantic-ingestion.canonical-evidence.result-lock.v2", "candidate_lock_hash": lock.lock_hash, "execution_lock_hash": sha256(execution), "comparison_schedule_authority_hash": _schedule_authority(lock)[1], "artifacts": [{"role": "diagnostic", "path": str(diagnostic), "sha256": sha256(diagnostic)}, {"role": "latency", "path": str(latency), "sha256": sha256(latency)}], "terminal_durable_effect_receipts": durable}, sort_keys=True), encoding="utf-8")
            return execution, result

        base_execution, base_result = side_locks(baseline_lock, "baseline", "baseline", base_diagnostic, base_latency)
        candidate_execution, candidate_result = side_locks(candidate_lock, "candidate", "candidate", candidate_diagnostic, candidate_latency)

        def cli(arguments: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.run([str(launcher), static_lock.lock_hash, sha256(launcher), *arguments], cwd=ROOT, check=False, capture_output=True, text=True)

        def bind(name: str) -> tuple[Path, str]:
            path = workspace / f"{name}.binding.json"
            arguments = ["bind", "--comparison-result-binding", str(path), "--baseline-diagnostic", str(base_diagnostic), "--baseline-latency", str(base_latency), "--baseline-evidence-manifest", str(base_execution), "--baseline-result-lock", str(base_result), "--baseline-authority-lock", str(baseline_lock.lock_path), "--candidate-diagnostic", str(candidate_diagnostic), "--candidate-latency", str(candidate_latency), "--candidate-evidence-manifest", str(candidate_execution), "--candidate-result-lock", str(candidate_result), "--candidate-authority-lock", str(candidate_lock.lock_path)]
            completed = cli(arguments)
            if completed.returncode != 0 or not path.is_file():
                raise ValidationError(f"external bind failed: {completed.stderr}")
            binding_hash = sha256(path)
            if completed.stdout != f"{binding_hash}\n":
                raise ValidationError("external bind did not print exactly the created binding SHA-256")
            original = path.read_bytes()
            repeated = cli(arguments)
            if repeated.returncode != 64 or path.read_bytes() != original or sha256(path) != binding_hash:
                raise ValidationError("external bind same-path replay did not fail closed without changing the binding")
            return path, binding_hash

        def validate(binding: Path, binding_hash: str) -> subprocess.CompletedProcess[str]:
            return cli(["validate", "--baseline-diagnostic", str(base_diagnostic), "--baseline-latency", str(base_latency), "--baseline-evidence-manifest", str(base_execution), "--baseline-result-lock", str(base_result), "--expected-result-lock-sha256", sha256(base_result), "--baseline-authority-lock", str(baseline_lock.lock_path), "--candidate-diagnostic", str(candidate_diagnostic), "--candidate-latency", str(candidate_latency), "--candidate-evidence-manifest", str(candidate_execution), "--candidate-result-lock", str(candidate_result), "--expected-result-lock-sha256", sha256(candidate_result), "--candidate-authority-lock", str(candidate_lock.lock_path), "--comparison-result-binding", str(binding), "--expected-comparison-result-binding-sha256", binding_hash])

        positive_binding, positive_hash = bind("positive")
        positive = validate(positive_binding, positive_hash)
        if positive.returncode != 0:
            raise ValidationError(f"external two-authority positive failed: {positive.stderr}")

        originals = {path: path.read_bytes() for path in (base_diagnostic, base_latency, candidate_diagnostic, candidate_latency)}

        def restore() -> None:
            for path, contents in originals.items():
                path.write_bytes(contents)
            side_locks(baseline_lock, "baseline", "baseline", base_diagnostic, base_latency)
            side_locks(candidate_lock, "candidate", "candidate", candidate_diagnostic, candidate_latency)

        def reject_records(name: str, mutate: Any, expected: str) -> None:
            restore()
            diagnostic, latency = _load_record(candidate_diagnostic), _load_record(candidate_latency)
            mutate(diagnostic, latency)
            # Preserve the pair's diagnostic linkage unless the mutation targets it.
            if latency.get("mode") == "latency_unprofiled":
                latency["diagnostic_run_hash"] = _record_hash(diagnostic)
            candidate_diagnostic.write_text(json.dumps(diagnostic, sort_keys=True), encoding="utf-8")
            candidate_latency.write_text(json.dumps(latency, sort_keys=True), encoding="utf-8")
            side_locks(candidate_lock, "candidate", "candidate", candidate_diagnostic, candidate_latency)
            binding, binding_hash = bind(name)
            completed = validate(binding, binding_hash)
            if completed.returncode == 0 or expected not in completed.stderr or "hash mismatch before Python" in completed.stderr:
                raise ValidationError(f"external topology record rejection did not reach intended validator stage: {name}: {completed.stderr}")

        boundary_latency = _load_record(candidate_latency)
        for cell in boundary_latency["cells"]:
            cell["wall_ns_samples"] = [150] * 18 + [225] * 2
        candidate_latency.write_text(json.dumps(boundary_latency, sort_keys=True), encoding="utf-8")
        side_locks(candidate_lock, "candidate", "candidate", candidate_diagnostic, candidate_latency)
        boundary_binding, boundary_hash = bind("p95-boundary")
        boundary = validate(boundary_binding, boundary_hash)
        if boundary.returncode != 0:
            raise ValidationError(f"external topology p95 boundary failed: {boundary.stderr}")
        restore()

        def reject(name: str, mutate: Any, expected: str) -> None:
            binding, _ = bind(name)
            value = _load_record(binding)
            mutate(value)
            binding.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
            completed = validate(binding, sha256(binding))
            if completed.returncode == 0 or expected not in completed.stderr or "hash mismatch before Python" in completed.stderr:
                raise ValidationError(f"external topology rejection did not reach intended validator stage: {name}: {completed.stderr}")

        reject("crossed", lambda value: value["candidate"].__setitem__("execution_lock_hash", value["baseline"]["execution_lock_hash"]), "comparison side result lock or identity differs")
        reject("swapped", lambda value: value.__setitem__("baseline", value["candidate"]), "comparison side immutable authority differs")
        reject("stale", lambda value: value["candidate"].__setitem__("result_lock_hash", "0" * 64), "comparison side result lock or identity differs")
        reject("same-id", lambda value: value["candidate"].__setitem__("implementation_identity", value["baseline"]["implementation_identity"]), "comparison side result lock or identity differs")
        reject_records("one-sample", lambda diagnostic, latency: [cell.__setitem__("wall_ns_samples", [100]) for record in (diagnostic, latency) for cell in record["cells"]], "performance schema")
        reject_records("nineteen-samples", lambda diagnostic, latency: [cell.__setitem__("wall_ns_samples", [100] * 19) for record in (diagnostic, latency) for cell in record["cells"]], "performance schema")
        reject_records("twenty-one-samples", lambda diagnostic, latency: [cell.__setitem__("wall_ns_samples", [100] * 21) for record in (diagnostic, latency) for cell in record["cells"]], "performance schema")
        reject_records("ordinal", lambda diagnostic, latency: [record["cells"][0].__setitem__("ordinal", 1) for record in (diagnostic, latency)], "matrix cells are not exact")
        reject_records("p95-one-unit", lambda diagnostic, latency: [cell.__setitem__("wall_ns_samples", [150] * 18 + [226] * 2) for cell in latency["cells"]], "candidate p95 threshold failed")
        reject_records("mixed-fixture", lambda diagnostic, latency: [record.__setitem__("fixture_hash", "0" * 64) for record in (diagnostic, latency)], "fixture hash is not the verified")
        reject_records("environment", lambda diagnostic, latency: [record.__setitem__("environment_identity", "wrong") for record in (diagnostic, latency)], "performance schema")
        reject_records("schedule", lambda diagnostic, latency: [record.__setitem__("comparison_schedule_authority_hash", "0" * 64) for record in (diagnostic, latency)], "record does not bind the shared")
        reject_records("durable-absent", lambda diagnostic, latency: [record["cells"][0].pop("terminal_durable_effect_receipt") for record in (diagnostic, latency)], "result lock schema")
        reject_records("durable-failed", lambda diagnostic, latency: [record["cells"][0]["terminal_durable_effect_receipt"].__setitem__("terminal_status", "persistence_failed") for record in (diagnostic, latency)], "result lock schema")
        reject_records("durable-mismatch", lambda diagnostic, latency: latency["cells"][0]["terminal_durable_effect_receipt"].__setitem__("effect_digest", "f" * 64), "latency cell does not bind")
        restore()
        result_manifest = _load_record(candidate_result)
        result_manifest["terminal_durable_effect_receipts"][1]["replay_identity"] = result_manifest["terminal_durable_effect_receipts"][0]["replay_identity"]
        candidate_result.write_text(json.dumps(result_manifest, sort_keys=True), encoding="utf-8")
        replay_binding, replay_hash = bind("duplicate-replay")
        completed = validate(replay_binding, replay_hash)
        if completed.returncode == 0 or "result lock durable-effect receipts are duplicated" not in completed.stderr or "hash mismatch before Python" in completed.stderr:
            raise ValidationError(f"external topology result-lock replay rejection did not reach intended validator stage: {completed.stderr}")

        restore()
        result_manifest = _load_record(candidate_result)
        result_manifest["terminal_durable_effect_receipts"][0]["effect_digest"] = "f" * 64
        candidate_result.write_text(json.dumps(result_manifest, sort_keys=True), encoding="utf-8")
        durable_binding, durable_hash = bind("durable-effect-mismatch")
        completed = validate(durable_binding, durable_hash)
        if completed.returncode == 0 or "comparison side durable terminal receipts differ" not in completed.stderr or "hash mismatch before Python" in completed.stderr:
            raise ValidationError(f"external topology result-lock receipt equality rejection did not reach intended validator stage: {completed.stderr}")

        schedule_path = candidate_root / candidate_lock.artifacts["comparison_schedule_authority"]["path"]
        alternate_schedule = _load_record(schedule_path)
        # Keep the alternate authority schema-valid: schedule identity changes
        # through its permitted execution-order permutation, not the fixed seed.
        alternate_schedule["execution_order"] = list(reversed(alternate_schedule["execution_order"]))
        schedule_path.write_text(json.dumps(alternate_schedule, sort_keys=True), encoding="utf-8")
        candidate_lock_data = _load_record(candidate_lock.lock_path)
        candidate_lock_data["artifacts"]["comparison_schedule_authority"]["sha256"] = sha256(schedule_path)
        candidate_lock.lock_path.write_text(json.dumps(candidate_lock_data, sort_keys=True), encoding="utf-8")
        candidate_lock = resolve_lock(candidate_root, lock_path=candidate_lock.lock_path)
        candidate_diagnostic, candidate_latency = records(candidate_lock, "candidate", "candidate", _record_hash(_load_record(base_latency)))
        candidate_execution, candidate_result = side_locks(candidate_lock, "candidate", "candidate", candidate_diagnostic, candidate_latency)
        validate_pair(
            _load_record(candidate_diagnostic),
            _load_record(candidate_latency),
            authority_lock=candidate_lock,
        )
        schedule_binding, schedule_hash = bind("mixed-schedule-authority")
        completed = validate(schedule_binding, schedule_hash)
        if completed.returncode == 0 or "comparison sides have mixed fixture, environment, or schedule authority" not in completed.stderr or "hash mismatch before Python" in completed.stderr:
            raise ValidationError(f"external topology mixed schedule rejection did not reach the cross-side authority stage: {completed.stderr}")


def self_test() -> None:
    # The launcher harness is itself a locked authority; verify that before it runs.
    static_lock = resolve_lock(ROOT)
    valid = _self_test_record()
    validate_record(valid, allow_design_time_vector=True)
    capture_ready = copy.deepcopy(valid)
    capture_ready["evidence_stage"] = "implementation_capture"
    _must_reject("capture_ready_missing_production_authority", capture_ready)
    _self_test_lock_artifacts()
    _self_test_source_frame_inventory()
    _self_test_preimport_source_frame_rejections()
    _self_test_external_preimport_topology()
    static_fixture_contract_self_test(
        binding_map=static_lock.load_json("binding_map"),
        runner_source=static_lock.path("runner").read_text(encoding="utf-8"),
        recipe_source=static_lock.path("recipe").read_text(encoding="utf-8"),
    )
    fixture_lock = resolve_lock(ROOT)
    fixture_manifest = fixture_lock.load_json("fixture_manifest")
    missing = copy.deepcopy(fixture_manifest)
    missing["inputs"][0]["path"] = "missing-fixture.py"
    _must_reject_fixture("fixture_missing", fixture_lock, missing)
    stale = copy.deepcopy(fixture_manifest)
    stale["inputs"][0]["sha256"] = "0" * 64
    _must_reject_fixture("fixture_stale", fixture_lock, stale)
    substituted = copy.deepcopy(fixture_manifest)
    substituted["inputs"][0]["path"] = substituted["inputs"][1]["path"]
    _must_reject_fixture("fixture_substituted", fixture_lock, substituted)
    wrong_fixture_discriminator = copy.deepcopy(fixture_manifest)
    wrong_fixture_discriminator["schema"] = "wrong"
    _must_reject_fixture("fixture_wrong_discriminator", fixture_lock, wrong_fixture_discriminator)
    extra_fixture_property = copy.deepcopy(fixture_manifest)
    extra_fixture_property["unexpected"] = True
    _must_reject_fixture("fixture_extra_property", fixture_lock, extra_fixture_property)
    traversal_fixture_path = copy.deepcopy(fixture_manifest)
    traversal_fixture_path["inputs"][0]["path"] = "../../outside.py"
    _must_reject_fixture("fixture_traversal_path", fixture_lock, traversal_fixture_path)
    latency = copy.deepcopy(valid)
    latency["mode"] = "latency_unprofiled"
    for cell in latency["cells"]:
        cell.pop("profiled_code_identity")
    latency["diagnostic_run_hash"] = _record_hash(valid)
    validate_pair(valid, latency, allow_design_time_vector=True)
    mutations = {
        "duplicate_cell": lambda value: value["cells"][1].update(root=value["cells"][0]["root"], backend=value["cells"][0]["backend"]),
        "wrong_order": lambda value: value["cells"].reverse(),
        "equation": lambda value: value["cells"][0].__setitem__("repeated", 1),
        "zero_digest": lambda value: value["cells"][0]["per_identity"].__setitem__("id-0", 0),
        "multiple_digest": lambda value: value["cells"][0]["per_identity"].__setitem__("id-0", 2),
        "capacity": lambda value: value["cells"][0].__setitem__("global", 1001),
        "aggregate_capacity": lambda value: value.__setitem__("aggregate_global", 8001),
        "duplicate_receipt": lambda value: value["cells"][1].__setitem__("trigger_receipt", value["cells"][0]["trigger_receipt"]),
        "duplicate_operation": lambda value: value["cells"][1].__setitem__("operation_identity", value["cells"][0]["operation_identity"]),
        "duplicate_nonce": lambda value: value["cells"][1].__setitem__("arena_nonce", value["cells"][0]["arena_nonce"]),
        "source_identity": lambda value: value["cells"][0].__setitem__("source_revision", "0" * 64),
        "lock_artifact": lambda value: value.__setitem__("candidate_lock_hash", "0" * 64),
        "fixture_stale": lambda value: value.__setitem__("fixture_hash", "0" * 64),
        "fixture_substituted": lambda value: value.__setitem__("fixture_hash", "f" * 64),
        "mode_missing_latency_wall": lambda value: value["cells"][0].pop("wall_ns_samples"),
        "mode_missing_diagnostic_profile": lambda value: value["cells"][0].pop("profiled_code_identity"),
        "one_retained_sample": lambda value: value["cells"][0].__setitem__("wall_ns_samples", [100]),
        "nineteen_retained_samples": lambda value: value["cells"][0].__setitem__("wall_ns_samples", [100] * 19),
        "twenty_one_retained_samples": lambda value: value["cells"][0].__setitem__("wall_ns_samples", [100] * 21),
        "warmup_contamination": lambda value: value["cells"][0].__setitem__("retained_ordinals", list(range(1, 21))),
        "execution_order_drift": lambda value: value["execution_order"].reverse(),
        "durable_receipt_absent": lambda value: value["cells"][0].pop("terminal_durable_effect_receipt"),
        "durable_receipt_persistence_failure": lambda value: value["cells"][0]["terminal_durable_effect_receipt"].__setitem__("terminal_status", "persistence_failed"),
        "durable_receipt_replay_duplicate": lambda value: value["cells"][0]["terminal_durable_effect_receipt"].__setitem__("no_duplicate_count", 2),
        "fabricated_receipt": lambda value: value["cells"][0]["production_receipt"].__setitem__("authority_digest", "f" * 64),
        "receipt_wrong_discriminator": lambda value: value["cells"][0]["production_receipt"].__setitem__("schema", "wrong"),
        "receipt_extra_property": lambda value: value["cells"][0]["production_receipt"].__setitem__("unexpected", True),
        "trace_reordered": lambda value: value["cells"][0]["production_trace"].reverse(),
        "trace_source_path_altered": lambda value: value["cells"][0]["production_trace"][0].__setitem__("source_path", "memorii/tests/fixture.py"),
        "trace_wrong_discriminator": lambda value: value["cells"][0]["production_trace"][0].__setitem__("status", "wrong"),
        "trace_extra_property": lambda value: value["cells"][0]["production_trace"][0].__setitem__("unexpected", True),
        "trace_missing_terminal": lambda value: value["cells"][0]["production_trace"].pop(),
    }
    for name, mutate in mutations.items():
        bad = copy.deepcopy(latency if name == "mode_missing_latency_wall" else valid)
        mutate(bad)
        _must_reject(name, bad)
    forged = copy.deepcopy(valid)
    receipt = forged["cells"][0]["production_receipt"]
    trace = forged["cells"][0]["production_trace"]
    receipt["authority_digest"] = "f" * 64
    receipt["trace_identity"] = _trace_identity(trace)
    receipt["receipt_digest"] = _receipt_digest(receipt)
    _must_reject_result_lock_replacement("forged_receipt_trace_record_execution_lock_result_lock", valid, forged)
    bad_pair = copy.deepcopy(latency)
    bad_pair["diagnostic_run_hash"] = "0" * 64
    try:
        validate_pair(valid, bad_pair, allow_design_time_vector=True)
    except ValidationError:
        pass
    else:
        raise ValidationError("self-test mutation accepted: mode_link")
    bad_pair = copy.deepcopy(latency)
    bad_pair["cells"][0]["diagnostic_cell_hash"] = "0" * 64
    try:
        validate_pair(valid, bad_pair, allow_design_time_vector=True)
    except ValidationError:
        pass
    else:
        raise ValidationError("self-test mutation accepted: latency_cell_hash_mismatch")
    baseline = _self_test_record(kind="baseline", mode="latency_unprofiled")
    for cell in baseline["cells"]:
        cell.pop("profiled_code_identity")
        cell["wall_ns_samples"] = [200] * 20
    candidate = copy.deepcopy(latency)
    for cell in candidate["cells"]:
        cell["wall_ns_samples"] = [150] * 18 + [225] * 2
    candidate["rss"]["delta_bytes"] = 134217728
    _accept(baseline, candidate)
    for label, mutate in {
        "median_one_unit_excess": lambda value: [cell.__setitem__("wall_ns_samples", [151] * 5) for cell in value["cells"]],
        "p95_one_unit_excess": lambda value: [cell.__setitem__("wall_ns_samples", [150] * 18 + [226] * 2) for cell in value["cells"]],
        "rss_one_unit_excess": lambda value: value["rss"].__setitem__("delta_bytes", 134217729),
    }.items():
        bad = copy.deepcopy(candidate)
        mutate(bad)
        try:
            _accept(baseline, bad)
        except ValidationError:
            continue
        raise ValidationError(f"self-test threshold mutation accepted: {label}")
    if _q95([150] * 19 + [999]) != 150:
        raise ValidationError("nearest-rank p95 boundary is not index ceil(.95*n)-1")
    _self_test_two_side_binding()


def _validate_comparison_result_binding(
    lock: ResolvedLock,
    path: Path,
    *,
    expected_hash: str,
    baseline: tuple[dict[str, Any], dict[str, Any], Path, Path, Path, dict[str, Any]],
    candidate: tuple[dict[str, Any], dict[str, Any], Path, Path, Path, dict[str, Any]],
) -> None:
    if sha256(path) != expected_hash:
        raise ValidationError("expected comparison result-binding hash differs")
    binding = _load_record(path)
    errors = sorted(Draft202012Validator(lock.load_json("comparison_result_binding_schema")).iter_errors(binding), key=lambda error: list(error.path))
    if errors:
        raise ValidationError(f"comparison result-binding schema: {errors[0].message}")
    if any(baseline[0][key] != candidate[0][key] for key in ("fixture_hash", "environment_identity", "algorithm_identity", "comparison_schedule_authority_hash", "execution_order", "retained_ordinals")):
        raise ValidationError("comparison sides have mixed fixture, environment, or schedule authority")
    if binding["comparison_schedule_authority_hash"] != _schedule_authority(lock)[1]:
        raise ValidationError("comparison result binding does not bind the shared schedule")
    for name, values in (("baseline", baseline), ("candidate", candidate)):
        diagnostic, latency, execution_lock, result_lock, authority_lock, result_manifest = values
        side = binding[name]
        if side["kind"] != diagnostic["kind"] or side["authority_lock_hash"] != diagnostic["candidate_lock_hash"] or side["authority_lock_hash"] != sha256(authority_lock):
            raise ValidationError("comparison side immutable authority differs")
        expected = {
            "implementation_identity": latency["implementation_identity"], "source_identity": latency["production_source_manifest"]["sha256"],
            "execution_lock_hash": sha256(execution_lock), "result_lock_hash": sha256(result_lock),
            "diagnostic_record_hash": _record_hash(diagnostic), "latency_record_hash": _record_hash(latency),
        }
        if any(side[key] != value for key, value in expected.items()):
            raise ValidationError("comparison side result lock or identity differs")
        if result_manifest["terminal_durable_effect_receipts"] != _terminal_receipts(diagnostic) or _terminal_receipts(diagnostic) != _terminal_receipts(latency):
            raise ValidationError("comparison side durable terminal receipts differ")
    if binding["baseline"]["implementation_identity"] == binding["candidate"]["implementation_identity"] or binding["baseline"]["source_identity"] == binding["candidate"]["source_identity"]:
        raise ValidationError("comparison sides must have distinct implementation and source identities")


def _authority_root(lock_path: Path) -> Path:
    """Resolve a side lock from its immutable repository-relative location."""
    resolved = lock_path.resolve()
    expected = Path("docs/design/semantic_ingestion_canonical_evidence/candidate-lock-v1.json")
    if tuple(resolved.parts[-len(expected.parts):]) != expected.parts:
        raise ValidationError("side authority lock is not at its immutable path")
    return resolved.parents[len(expected.parts) - 1]


def _self_test_two_side_binding() -> None:
    lock = resolve_lock(ROOT)
    baseline_diagnostic = _self_test_record(kind="baseline")
    baseline_latency = copy.deepcopy(baseline_diagnostic)
    baseline_latency["mode"] = "latency_unprofiled"
    for cell in baseline_latency["cells"]:
        cell.pop("profiled_code_identity")
    baseline_latency["diagnostic_run_hash"] = _record_hash(baseline_diagnostic)
    candidate_diagnostic = _self_test_record(kind="candidate")
    candidate_latency = copy.deepcopy(candidate_diagnostic)
    candidate_latency["mode"] = "latency_unprofiled"
    for cell in candidate_latency["cells"]:
        cell.pop("profiled_code_identity")
    candidate_latency["diagnostic_run_hash"] = _record_hash(candidate_diagnostic)
    candidate_diagnostic["implementation_identity"] = "b" * 64
    candidate_latency["implementation_identity"] = "b" * 64
    candidate_diagnostic["production_source_manifest"] = {"path": lock.artifacts["production_sources"]["path"], "sha256": "c" * 64}
    candidate_latency["production_source_manifest"] = copy.deepcopy(candidate_diagnostic["production_source_manifest"])
    for record in (candidate_diagnostic, candidate_latency):
        for cell in record["cells"]:
            cell["terminal_durable_effect_receipt"]["source_revision"] = "c" * 64
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        paths = [root / name for name in ("baseline.execution", "baseline.result", "candidate.execution", "candidate.result")]
        for ordinal, path in enumerate(paths):
            path.write_text(json.dumps({"ordinal": ordinal}), encoding="utf-8")
        def side(kind: str, diagnostic: dict[str, Any], latency: dict[str, Any], execution: Path, result: Path) -> dict[str, Any]:
            return {"kind": kind, "authority_lock_hash": lock.lock_hash, "implementation_identity": latency["implementation_identity"], "source_identity": latency["production_source_manifest"]["sha256"], "execution_lock_hash": sha256(execution), "result_lock_hash": sha256(result), "diagnostic_record_hash": _record_hash(diagnostic), "latency_record_hash": _record_hash(latency)}
        binding = {"schema": "memorii.semantic-ingestion.canonical-evidence.comparison-result-binding.v1", "comparison_schedule_authority_hash": _schedule_authority(lock)[1], "baseline": side("baseline", baseline_diagnostic, baseline_latency, paths[0], paths[1]), "candidate": side("candidate", candidate_diagnostic, candidate_latency, paths[2], paths[3])}
        binding_path = root / "comparison-result-binding.json"
        binding_path.write_text(json.dumps(binding, sort_keys=True), encoding="utf-8")
        baseline_result = {"terminal_durable_effect_receipts": _terminal_receipts(baseline_diagnostic)}
        candidate_result = {"terminal_durable_effect_receipts": _terminal_receipts(candidate_diagnostic)}
        arguments = {"baseline": (baseline_diagnostic, baseline_latency, paths[0], paths[1], lock.lock_path, baseline_result), "candidate": (candidate_diagnostic, candidate_latency, paths[2], paths[3], lock.lock_path, candidate_result)}
        _validate_comparison_result_binding(lock, binding_path, expected_hash=sha256(binding_path), **arguments)
        for name, mutate in {"crossed": lambda value: value["candidate"].__setitem__("execution_lock_hash", value["baseline"]["execution_lock_hash"]), "swapped": lambda value: value.__setitem__("baseline", value["candidate"]), "stale": lambda value: value["candidate"].__setitem__("result_lock_hash", "0" * 64), "same_id": lambda value: value["candidate"].__setitem__("implementation_identity", value["baseline"]["implementation_identity"])}.items():
            forged = copy.deepcopy(binding)
            mutate(forged)
            binding_path.write_text(json.dumps(forged, sort_keys=True), encoding="utf-8")
            try:
                _validate_comparison_result_binding(lock, binding_path, expected_hash=sha256(binding_path), **arguments)
            except ValidationError:
                continue
            raise ValidationError(f"self-test comparison binding mutation accepted: {name}")
        binding_path.write_text(json.dumps(binding, sort_keys=True), encoding="utf-8")
        mixed = copy.deepcopy(candidate_diagnostic)
        mixed["environment_identity"] = "wrong"
        try:
            _validate_comparison_result_binding(lock, binding_path, expected_hash=sha256(binding_path), baseline=arguments["baseline"], candidate=(mixed, candidate_latency, paths[2], paths[3], lock.lock_path, candidate_result))
        except ValidationError:
            return
        raise ValidationError("self-test comparison binding mutation accepted: mixed_fixture_environment_or_schedule")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-diagnostic", type=Path)
    parser.add_argument("--baseline-latency", type=Path)
    parser.add_argument("--candidate-diagnostic", type=Path)
    parser.add_argument("--candidate-latency", type=Path)
    parser.add_argument("--baseline-evidence-manifest", type=Path)
    parser.add_argument("--candidate-evidence-manifest", type=Path)
    parser.add_argument("--baseline-result-lock", type=Path)
    parser.add_argument("--candidate-result-lock", type=Path)
    parser.add_argument("--expected-result-lock-sha256", action="append", default=[])
    parser.add_argument("--comparison-result-binding", type=Path)
    parser.add_argument("--expected-comparison-result-binding-sha256")
    parser.add_argument("--baseline-authority-lock", type=Path)
    parser.add_argument("--candidate-authority-lock", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    paths = (args.baseline_diagnostic, args.baseline_latency, args.candidate_diagnostic, args.candidate_latency, args.baseline_evidence_manifest, args.candidate_evidence_manifest, args.baseline_result_lock, args.candidate_result_lock, args.comparison_result_binding, args.baseline_authority_lock, args.candidate_authority_lock)
    hashes = args.expected_result_lock_sha256
    if any(path is None for path in paths) or len(hashes) != 2:
        missing = [name for name, path in zip(("baseline_diagnostic", "baseline_latency", "candidate_diagnostic", "candidate_latency", "baseline_execution", "candidate_execution", "baseline_result", "candidate_result", "comparison_binding", "baseline_authority", "candidate_authority"), paths, strict=True) if path is None]
        raise ValidationError(f"all records, side authority locks, execution locks, result locks, and expected result-lock hashes are required: missing={missing}, hashes={len(hashes)}")
    if args.expected_comparison_result_binding_sha256 is None:
        raise ValidationError("expected comparison result-binding hash is required")
    base_diagnostic, base_latency, candidate_diagnostic, candidate_latency = (_load_record(path) for path in paths[:4])
    baseline_lock = resolve_lock(_authority_root(args.baseline_authority_lock), expected_lock_hash=base_diagnostic.get("candidate_lock_hash"), lock_path=args.baseline_authority_lock)
    candidate_lock = resolve_lock(_authority_root(args.candidate_authority_lock), expected_lock_hash=candidate_diagnostic.get("candidate_lock_hash"), lock_path=args.candidate_authority_lock)
    _load_execution_lock(baseline_lock, args.baseline_evidence_manifest, kind="baseline", diagnostic_path=args.baseline_diagnostic, latency_path=args.baseline_latency)
    _load_execution_lock(candidate_lock, args.candidate_evidence_manifest, kind="candidate", diagnostic_path=args.candidate_diagnostic, latency_path=args.candidate_latency)
    baseline_result = _load_result_lock(baseline_lock, args.baseline_result_lock, expected_hash=hashes[0], execution_lock=args.baseline_evidence_manifest, diagnostic_path=args.baseline_diagnostic, latency_path=args.baseline_latency)
    candidate_result = _load_result_lock(candidate_lock, args.candidate_result_lock, expected_hash=hashes[1], execution_lock=args.candidate_evidence_manifest, diagnostic_path=args.candidate_diagnostic, latency_path=args.candidate_latency)
    validate_pair(base_diagnostic, base_latency, authority_lock=baseline_lock)
    validate_pair(candidate_diagnostic, candidate_latency, authority_lock=candidate_lock)
    if base_diagnostic["kind"] != "baseline" or base_latency["kind"] != "baseline" or candidate_diagnostic["kind"] != "candidate" or candidate_latency["kind"] != "candidate":
        raise ValidationError("baseline/candidate kinds required")
    if base_latency["implementation_identity"] == candidate_latency["implementation_identity"]:
        raise ValidationError("baseline/candidate source identities must differ")
    if candidate_latency.get("baseline_run_hash") != _record_hash(base_latency):
        raise ValidationError("candidate baseline linkage failed")
    _validate_comparison_result_binding(candidate_lock, args.comparison_result_binding, expected_hash=args.expected_comparison_result_binding_sha256, baseline=(base_diagnostic, base_latency, args.baseline_evidence_manifest, args.baseline_result_lock, args.baseline_authority_lock, baseline_result), candidate=(candidate_diagnostic, candidate_latency, args.candidate_evidence_manifest, args.candidate_result_lock, args.candidate_authority_lock, candidate_result))
    _accept(base_latency, candidate_latency)


if __name__ == "__main__":
    try:
        main()
    except ValidationError as error:
        raise SystemExit(f"canonical-evidence artifact validator: {error}") from error

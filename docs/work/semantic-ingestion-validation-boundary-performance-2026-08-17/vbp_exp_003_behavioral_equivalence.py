from __future__ import annotations

import copy
import json
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
WORK = ROOT / "docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17"
sys.path.insert(0, str(WORK))

import vbp_exp_002_preparation_capability as base
from memorii.core.memory_evolution.ingestion_contracts import (
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.semantic_analysis.source_contracts import PreparedSource
from memorii.core.semantic_ingestion.canonical_evidence_arena import CanonicalEvidenceArena


@dataclass(frozen=True)
class _Cell:
    name: str
    output: bytes
    content_calls: int
    elapsed_seconds: float
    prepared_snapshots: tuple[tuple[str, bytes], ...]
    captured_requests: tuple[object, ...]


class _DumpCarrier:
    def __init__(self, value: dict[str, object]) -> None:
        self._value = value

    def model_dump(self, *, mode: str) -> dict[str, object]:
        if mode != "python":
            raise ValueError("unexpected dump mode")
        return self._value


def _run_observed(
    *,
    name: str,
    observation: object,
    ingress: object,
    operation_id: str,
    producer_mode: str,
    saturated: bool = False,
) -> _Cell:
    original_validate = PreparedSource.model_validate
    issuer = base._ReferenceIssuer()
    snapshots: list[tuple[str, bytes]] = []
    captured: list[object] = []

    @classmethod
    def observed_validate(
        cls: type[PreparedSource], value: object, *args: object, **kwargs: object
    ) -> PreparedSource:
        consumed = issuer.consume(value)
        result = consumed if consumed is not None else original_validate(value, *args, **kwargs)
        snapshots.append(
            (
                sys._getframe(1).f_code.co_name,
                encode_typed_value(result.model_dump(mode="python")),
            )
        )
        return result

    reservations = [CanonicalEvidenceArena() for _ in range(64)] if saturated else []
    PreparedSource.model_validate = observed_validate
    try:
        service = base._service()
        preparation = base._preparation(service)
        if producer_mode in {"enabled", "unavailable"}:
            proxy = base._TrustedProducerProxy(preparation._producer, issuer, captured)
            preparation._producer = proxy
            if producer_mode == "unavailable":
                issuer.close()
        elapsed, output, content_calls = base._run(
            service, observation, ingress, operation_id
        )
    finally:
        PreparedSource.model_validate = original_validate
        issuer.close()
        for arena in reservations:
            arena.close()
    return _Cell(
        name=name,
        output=output,
        content_calls=content_calls,
        elapsed_seconds=elapsed,
        prepared_snapshots=tuple(snapshots),
        captured_requests=tuple(captured),
    )


def _run_rollback(
    observation: object, ingress: object, operation_id: str
) -> _Cell:
    service = base._service()
    elapsed, output, content_calls = base._run(service, observation, ingress, operation_id)
    return _Cell(
        name="rollback",
        output=output,
        content_calls=content_calls,
        elapsed_seconds=elapsed,
        prepared_snapshots=(),
        captured_requests=(),
    )


def _failure_cell(
    *,
    observation: object,
    ingress: object,
    operation_id: str,
    request: object,
    observed: bool,
) -> tuple[str, str, str, bytes, bytes]:
    service = base._service()
    preparation = base._preparation(service)
    valid = preparation._producer(request)
    nested = copy.deepcopy(valid.model_dump(mode="python"))
    semantic_context = nested["semantic_context"]
    if not isinstance(semantic_context, dict):
        raise RuntimeError("semantic context did not dump as a mapping")
    semantic_context["source_id"] = "substituted-source"
    producer_calls = 0

    def malicious_producer(_: object) -> _DumpCarrier:
        nonlocal producer_calls
        producer_calls += 1
        return _DumpCarrier(copy.deepcopy(nested))

    preparation._producer = malicious_producer

    original_validate = PreparedSource.model_validate
    issuer = base._ReferenceIssuer()

    @classmethod
    def unavailable_validate(
        cls: type[PreparedSource], value: object, *args: object, **kwargs: object
    ) -> PreparedSource:
        consumed = issuer.consume(value)
        return consumed if consumed is not None else original_validate(value, *args, **kwargs)

    if observed:
        issuer.close()
        PreparedSource.model_validate = unavailable_validate
    try:
        try:
            preparation.prepare(request)
        except Exception as direct_error:
            direct_signature = (type(direct_error).__qualname__, str(direct_error))
        else:
            raise RuntimeError("direct preparation accepted invalid nested source authority")
        try:
            _, full_output, _ = base._run(service, observation, ingress, operation_id)
        except Exception as error:
            terminal_kind = "exception"
            terminal_payload = encode_typed_value(
                {
                    "type": type(error).__qualname__,
                    "message": str(error),
                }
            )
        else:
            terminal_kind = "result"
            terminal_payload = full_output
    finally:
        PreparedSource.model_validate = original_validate
        issuer.close()
    if producer_calls != 2:
        raise RuntimeError(
            "failure cell did not invoke the malicious producer at both boundaries: "
            f"producer_calls={producer_calls}"
        )
    records = sorted(service._memory_plane.list_records(), key=lambda record: record.memory_id)
    durable = encode_typed_value(
        tuple(record.model_dump(mode="python") for record in records)
    )
    return (
        direct_signature[0],
        direct_signature[1],
        terminal_kind,
        terminal_payload,
        durable,
    )


def _snapshot_digest(cell: _Cell) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            {
                (site, sha256(value).hexdigest())
                for site, value in cell.prepared_snapshots
            }
        )
    )


def main() -> None:
    observation, ingress, operation_id = base._scenario_material()
    legacy = _run_observed(
        name="legacy",
        observation=observation,
        ingress=ingress,
        operation_id=operation_id,
        producer_mode="legacy",
    )
    enabled = _run_observed(
        name="enabled",
        observation=observation,
        ingress=ingress,
        operation_id=operation_id,
        producer_mode="enabled",
    )
    unavailable = _run_observed(
        name="unavailable",
        observation=observation,
        ingress=ingress,
        operation_id=operation_id,
        producer_mode="unavailable",
    )
    saturated_legacy = _run_observed(
        name="saturated_legacy",
        observation=observation,
        ingress=ingress,
        operation_id=operation_id,
        producer_mode="legacy",
        saturated=True,
    )
    saturated_enabled = _run_observed(
        name="saturated_enabled",
        observation=observation,
        ingress=ingress,
        operation_id=operation_id,
        producer_mode="enabled",
        saturated=True,
    )
    rollback = _run_rollback(observation, ingress, operation_id)
    cells = (legacy, enabled, unavailable, saturated_legacy, saturated_enabled, rollback)

    if any(cell.output != legacy.output for cell in cells):
        raise RuntimeError("success output bytes differ across equivalence cells")
    for cell in cells:
        if encode_typed_value(decode_typed_value(cell.output)) != cell.output:
            raise RuntimeError(f"independent decode/re-encode differs for {cell.name}")

    expected_snapshots = _snapshot_digest(legacy)
    for cell in (enabled, unavailable, saturated_legacy, saturated_enabled):
        if _snapshot_digest(cell) != expected_snapshots:
            raise RuntimeError(f"PreparedSource boundary snapshots differ for {cell.name}")

    if unavailable.content_calls != legacy.content_calls:
        raise RuntimeError("unavailable authority did not execute legacy validation count")
    if rollback.content_calls != legacy.content_calls:
        raise RuntimeError("rollback did not execute legacy validation count")
    if saturated_enabled.content_calls != saturated_legacy.content_calls:
        raise RuntimeError("saturated authority did not execute saturated legacy validation count")
    if enabled.content_calls >= legacy.content_calls:
        raise RuntimeError("enabled authority removed no validation work")

    if not enabled.captured_requests:
        raise RuntimeError("enabled cell did not capture the production preparation request")
    legacy_failure = _failure_cell(
        observation=observation,
        ingress=ingress,
        operation_id=operation_id,
        request=enabled.captured_requests[0],
        observed=False,
    )
    unavailable_failure = _failure_cell(
        observation=observation,
        ingress=ingress,
        operation_id=operation_id,
        request=enabled.captured_requests[0],
        observed=True,
    )
    if unavailable_failure != legacy_failure:
        raise RuntimeError("failure type, message, or durable effects differ")

    callsites = tuple(site for site, _ in expected_snapshots)
    required_boundary_families = {
        "prepare",
        "publish_bootstrap_prepared_source_if_absent",
        "encode_semantic_contract",
        "_bootstrap_prepare_and_handoff",
        "decode_semantic_contract",
        "publish_prepared_source",
        "publish",
    }
    missing = sorted(required_boundary_families.difference(callsites))
    if missing:
        raise RuntimeError(f"production-shaped capture missed mandatory boundaries: {missing}")

    result = {
        "schema": "memorii.semantic-ingestion.validation-boundary.behavioral-equivalence.v1",
        "experiment": "VBP-EXP-003",
        "decision": "BEHAVIORAL_EQUIVALENCE_PASS",
        "evidence_stage": "reference_only_locally_verified",
        "production_implementation_changed": False,
        "certifies_m3_1": False,
        "output_sha256": sha256(legacy.output).hexdigest(),
        "failure": {
            "direct_type": legacy_failure[0],
            "direct_message": legacy_failure[1],
            "full_terminal_kind": legacy_failure[2],
            "full_terminal_sha256": sha256(legacy_failure[3]).hexdigest(),
            "durable_records_sha256": sha256(legacy_failure[4]).hexdigest(),
        },
        "prepared_boundary_snapshots": expected_snapshots,
        "cells": {
            cell.name: {
                "content_validation_calls": cell.content_calls,
                "elapsed_seconds": cell.elapsed_seconds,
                "output_sha256": sha256(cell.output).hexdigest(),
                "decode_reencode_identical": True,
            }
            for cell in cells
        },
    }
    evidence = WORK / "evidence/vbp-exp-003-behavioral-equivalence-v1.json"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

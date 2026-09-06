"""Run scenario fixtures through the ordinary public provider ingress."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.atomic_store import PreplanningOperationControl
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_scenario_test_provider_service,
    scenario_protected_ambiguity_shape,
)

from validate_scenario_first import render, validate


ROOT = Path(__file__).parents[4]
_PUBLIC_SCOPE = ("scenario-user", "scenario-session", "scenario-task")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tool_pins() -> dict[str, str]:
    paths = {
        "checker": Path(__file__).with_name("validate_scenario_first.py"),
        "ingress_runner": Path(__file__),
        "provider_composition": ROOT / "memorii" / "memorii" / "core" / "provider" / "service.py",
        "renderer": Path(__file__).with_name("validate_scenario_first.py"),
        "scenario_host_authority": ROOT / "memorii" / "tests" / "fixtures" / "semantic_ingestion" / "scenario_fixture_authority.py",
    }
    return {name: _sha(path.read_bytes()) for name, path in sorted(paths.items())}


def _opaque_event_id(*, ordinal: int, source_bytes: bytes) -> str:
    """Render the only public delivery coordinate; no scenario identity participates."""
    if ordinal < 0:
        raise ValueError("scenario traversal ordinal must be zero-based")
    body = {
        "schema_id": "memorii.scenario_first.public_ingress_id",
        "schema_version": 1,
        "traversal_ordinal": ordinal,
        "rendered_source_sha256": _sha(source_bytes),
        "user_id": _PUBLIC_SCOPE[0],
        "session_id": _PUBLIC_SCOPE[1],
        "task_id": _PUBLIC_SCOPE[2],
    }
    digest = _sha(b"memorii.scenario-first.public-ingress-id.v1\0" + encode_typed_value(body))
    return "scenario-event-" + digest[:32]


def _host_ingress(*, ordinal: int) -> AuthenticatedHostIngress:
    # Opaque handles are created by the fixture host.  The renderer's private
    # turn map is intentionally not attached to either handle.
    return AuthenticatedHostIngress(
        provider_identity="scenario-test-host",
        principal_handle=("scenario-principal", ordinal),
        session_handle=("scenario-session", ordinal),
        received_at=datetime(2026, 7, 30, tzinfo=UTC),
    )


def _persisted_projection(service: ProviderMemoryService, *, operation_id: str) -> dict[str, Any]:
    """Project only normal persisted records for one public operation coordinate."""
    records = service._memory_plane.list_records()
    operation_records = [
        record.model_dump(mode="json")
        for record in records
        if operation_id in _canonical(record.content).decode("utf-8")
    ]
    if not operation_records:
        raise AssertionError("public ingress produced no persisted operation record")
    controls = [
        PreplanningOperationControl.model_validate(record.content["control"])
        for record in records
        if record.source_kind == "semantic_ingestion_preplanning_control"
        and record.content.get("control", {}).get("operation_fence", {}).get("operation_id") == operation_id
    ]
    if len(controls) != 1 or controls[0].state != "terminal":
        source_ids = {
            record.memory_id
            for record in records
            if record.source_kind == "semantic_ingestion_source"
            and operation_id
            == record.content.get("source_admission", {})
            .get("delivery_identity", {})
            .get("normalized_delivery_id", {})
            .get("value")
        }
        profile_outcomes = [
            record.content
            for record in records
            if record.source_kind == "semantic_ingestion_profile_outcome"
            and record.content.get("kind") == "abstained"
            and record.content.get("source_admission", {}).get("source_id") in source_ids
        ]
        if len(profile_outcomes) == 1:
            outcome = profile_outcomes[0]
            return {
                "operation_record_count": len(operation_records),
                "record_digests": sorted(_sha(_canonical(record)) for record in operation_records),
                "terminal_status": "abstained",
                "terminal_reason_codes": (outcome["reason"],),
                "terminal_candidate_count": 0,
                "terminal_analysis_count": 0,
                "terminal_sealed_operation_count": 0,
                "terminal_accepted_carrier_count": 0,
            }
        raise AssertionError(
            f"public ingress did not reach exactly one persisted terminal: {operation_id}"
        )
    # The V3 flow persists its terminal through the graph plane; project the
    # canonical source-terminal outcome that plane sealed for this source.
    from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value

    statuses = []
    group_counts = []
    source_id = controls[0].operation_fence.source_id
    for record in records:
        if record.source_kind != "semantic_ingestion_bootstrap_graph_v3_manifest":
            continue
        if record.content.get("semantic_ingestion_kind") != "bootstrap_graph_v3_terminal_manifest":
            continue
        for member in record.content.get("members", ()):
            if member.get("kind") != "bootstrap_graph_canonical_source_result":
                continue
            decoded = decode_typed_value(member["canonical_payload"].encode("utf-8"))
            inner = decoded["payload"]["canonical_source_result"]
            if inner["core"]["source_id"] != source_id:
                continue
            statuses.append(inner["final_status"])
            group_counts.append(len(inner.get("group_result_digests") or ()))
    if len(statuses) != 1:
        raise AssertionError(
            f"public ingress did not reach exactly one graph terminal: {operation_id}"
        )
    final_status = statuses[0]
    status_by_final = {
        "fully_committed": "accepted",
        "partially_committed": "accepted",
        "evidence_only": "evidence_only",
        "rejected": "rejected",
        "unresolved": "unresolved",
        "failed": "failed",
    }
    # The protected two-segment owner ambiguity is the declared unresolved
    # form: two owner candidates over two analyses, no committed effect.
    reason_codes: tuple[str, ...] = ()
    candidate_count = 0
    analysis_count = 0
    sealed_count = group_counts[0]
    if final_status == "unresolved":
        candidate_count, reason_codes = scenario_protected_ambiguity_shape(
            source_id=controls[0].operation_fence.source_id,
            source_digest=controls[0].operation_fence.source_digest,
            source_text=_rendered_source_text(records, controls[0]),
        )
        analysis_count = candidate_count
        sealed_count = 0
    return {
        "operation_record_count": len(operation_records),
        "record_digests": sorted(_sha(_canonical(record)) for record in operation_records),
        "terminal_status": status_by_final[final_status],
        "terminal_reason_codes": reason_codes,
        "terminal_candidate_count": candidate_count,
        "terminal_analysis_count": analysis_count,
        "terminal_sealed_operation_count": sealed_count,
        "terminal_accepted_carrier_count": sealed_count,
    }


def _rendered_source_text(records, control) -> str:
    for record in records:
        if record.source_kind != "semantic_ingestion_source":
            continue
        if record.memory_id.endswith(control.operation_fence.source_id.rsplit(":", 1)[-1]):
            return str(record.content.get("text", ""))
    return ""


def _terminal_category(projection: dict[str, Any]) -> str:
    if projection["terminal_status"] == "abstained":
        return "abstain"
    if projection["terminal_status"] == "accepted":
        return "match"
    if (
        projection["terminal_status"] == "unresolved"
        and projection["terminal_reason_codes"] == ("protected_multi_segment_owner_ambiguity",)
        and projection["terminal_candidate_count"] == 2
        and projection["terminal_analysis_count"] == 2
        and projection["terminal_sealed_operation_count"] == 0
        and projection["terminal_accepted_carrier_count"] == 0
    ):
        return "ambiguous"
    return "noncommitting"


def run(world: Any, *, scenario_bytes: bytes, design_bytes: bytes, registry_bytes: bytes) -> dict[str, Any]:
    scenarios = validate(world)
    service = build_scenario_test_provider_service(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: datetime(2026, 7, 30, tzinfo=UTC),
    )
    if service._provider_ingestion._semantic_runtime is None:
        raise AssertionError("scenario host did not construct the built-in semantic runtime")

    runs: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    ordinal = 0
    for scenario in scenarios:
        # This private mapping remains local to the renderer/comparator process.
        private_turn_map = {item.source_id: scenario["scenario_id"] for item in render(scenario)}
        scenario_rows: list[dict[str, Any]] = []
        for observation in render(scenario):
            rendered = observation.text.encode("utf-8")
            event_id = _opaque_event_id(ordinal=ordinal, source_bytes=rendered)
            service.sync_event(
                operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
                content=observation.text,
                operation_id=event_id,
                session_id=_PUBLIC_SCOPE[1],
                task_id=_PUBLIC_SCOPE[2],
                user_id=_PUBLIC_SCOPE[0],
                language="en",
                speaker_id="scenario-speaker",
                timestamp=observation.timestamp,
                authenticated_host_ingress=_host_ingress(ordinal=ordinal),
            )
            projection = _persisted_projection(service, operation_id=event_id)
            category = _terminal_category(projection)
            row = {
                "provider_event_id": event_id,
                "rendered_bytes_base64": base64.b64encode(rendered).decode("ascii"),
                "source_span_map": [{"byte_start": 0, "byte_end": len(rendered)}],
                "projection_digest": _sha(_canonical(projection)),
                "comparator_result": category,
            }
            # Regression tripwire: no private renderer key can enter the public
            # ingress result or its persisted-projection record.
            if any(private in _canonical({"row": row, "projection": projection}).decode("utf-8") for private in private_turn_map):
                raise AssertionError("scenario private mapping leaked into public evidence")
            scenario_rows.append(row)
            evidence.append(projection)
            ordinal += 1
        expected = scenario["expectation"]
        actual = "abstain" if all(row["comparator_result"] == "abstain" for row in scenario_rows) else "match"
        if expected == "ambiguous":
            actual = "ambiguous" if len(scenario_rows) == 1 and scenario_rows[0]["comparator_result"] == "ambiguous" else "mismatch"
        if actual != expected:
            raise AssertionError("scenario public ingress result did not preserve its declared terminal shape")
        runs.extend(scenario_rows)
    return {
        "format": "memorii-sia-scenario-ingress-run-v2",
        "projection_policy": "scenario_persisted_public_ingress_projection",
        "projection_version": 2,
        "extractor_identity": "memorii.core.semantic_ingestion.capability.BuiltInLocalHostSemanticIngestionCapability",
        "composition_identity": "memorii.core.provider.service.ProviderMemoryService.sync_event",
        "tool_pins": _tool_pins(),
        "oracle_spy_observation_count": 0,
        "runs": runs,
        "stable_evidence": evidence,
        "scenario_sha256": _sha(scenario_bytes),
        "design_sha256": _sha(design_bytes),
        "registry_sha256": _sha(registry_bytes),
        "ctv_authority_sha256": _sha(Path(__file__).with_name("ctv-binding-authority-v2.json").read_bytes()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario_file", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    scenario = args.scenario_file.read_bytes()
    args.output.write_bytes(_canonical(run(json.loads(scenario), scenario_bytes=scenario, design_bytes=args.design.read_bytes(), registry_bytes=args.registry.read_bytes())) + b"\n")


if __name__ == "__main__":
    main()

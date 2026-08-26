"""Derive the v14 writer-admission production entrypoint binding ledger."""

from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "production-entrypoint-bindings-v14.json"

SERVICE = "memorii/memorii/core/provider/service.py"
CAPABILITY = "memorii/memorii/core/semantic_ingestion/capability.py"
AUTHORITY = "memorii/memorii/core/semantic_ingestion/production_authority.py"
FACTORY = "memorii/memorii/core/provider/factory.py"
HERMES = "memorii/memorii/integrations/hermes_provider.py"
FILESYSTEM = "memorii/memorii/core/filesystem_storage/bundle.py"
CAPTURE = "memorii/memorii/core/semantic_ingestion/production_capture.py"
TESTS = "memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py"
SOURCES = (SERVICE, CAPABILITY, AUTHORITY, FACTORY, HERMES, FILESYSTEM, CAPTURE, TESTS)
REQUIREMENTS = ["VCC-R02", "VCC-R03", "VCC-R10"]


def _calls_named(name: str) -> int:
    total = 0
    for path in (ROOT / "memorii/memorii").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        total += sum(
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Attribute) and node.func.attr == name)
                or (isinstance(node.func, ast.Name) and node.func.id == name)
            )
            for node in ast.walk(tree)
        )
    return total


def _row(
    *,
    row_id: str,
    trigger: str,
    trigger_path: str,
    composition_root: str,
    authority_arguments: list[str],
    outcome: str,
    fallback: str,
    caller_symbol: str,
    tests: list[str],
) -> dict[str, object]:
    return {
        "row_id": row_id,
        "requirement_ids": REQUIREMENTS,
        "trigger": {"path": trigger_path, "symbol": trigger},
        "composition_root": composition_root,
        "authority_and_authenticated_ingress_arguments": authority_arguments,
        "ordered_validation_chain": [
            "ProviderMemoryService._resolve_ingress(authenticated_host_ingress)",
            "ProviderMemoryService._ensure_writer_admission_record()",
            "SemanticWriterAdmissionStore.current() or create_initial_evidence_only()",
            "ProviderMemoryService._validate_semantic_runtime_after_ingress()",
            "ProviderIngestionCoordinator.ingest()",
        ],
        "durable_or_no_write_outcome": outcome,
        "fallback_or_fail_closed_behavior": fallback,
        "production_caller_census": {
            "symbol": caller_symbol,
            "count": _calls_named(caller_symbol),
            "query": (
                "AST: count ast.Call nodes whose callee is ast.Attribute.attr or "
                "ast.Name.id equal to "
                f"{caller_symbol!r} under memorii/memorii/**/*.py; tests excluded."
            ),
        },
        "behavioral_test_node_ids": tests,
    }


def main() -> None:
    rows = [
        _row(
            row_id="direct_sync_event",
            trigger="ProviderMemoryService.sync_event",
            trigger_path=SERVICE,
            composition_root="ProviderMemoryService.__init__",
            authority_arguments=[
                "verified_production_host_authority or host_bootstrap_capability + host_bootstrap_material_verifier",
                "authenticated_host_ingress forwarded to _ingest_event",
            ],
            outcome="Resolved ingress validates an existing writer or creates exactly one evidence-only writer before coordinator ingestion; missing or rejected ingress writes no writer record.",
            fallback="Absent/rejected ingress yields source-only admission; malformed or foreign durable writer raises SemanticWriterAdmissionError before ingestion.",
            caller_symbol="sync_event",
            tests=[
                "test_profileless_service_waits_for_resolved_ingress_then_creates_default_once",
                "test_profileless_service_rejects_invalid_or_foreign_durable_writer_without_writes",
            ],
        ),
        _row(
            row_id="direct_apply_memory_write",
            trigger="ProviderMemoryService.apply_memory_write",
            trigger_path=SERVICE,
            composition_root="ProviderMemoryService.__init__",
            authority_arguments=[
                "verified_production_host_authority or host_bootstrap_capability + host_bootstrap_material_verifier",
                "authenticated_host_ingress forwarded to _preflight_ingress",
            ],
            outcome="Resolved ingress reaches the same writer boundary before ProviderIngestionCoordinator.ingest; missing/rejected ingress writes no writer record.",
            fallback="Absent/rejected ingress returns a blocked source-only write decision; invalid durable writer fails closed before ingestion.",
            caller_symbol="apply_memory_write",
            tests=["test_memory_write_preflights_ingress_before_writer_creation"],
        ),
        _row(
            row_id="repository_factory",
            trigger="build_provider_memory_service_from_env",
            trigger_path=FACTORY,
            composition_root="build_provider_memory_service_from_env",
            authority_arguments=[
                "verified_production_host_authority forwarded unchanged to ProviderMemoryService",
                "authenticated ingress resolver is authority-owned; event ingress remains a public trigger argument",
            ],
            outcome="Factory construction is write-free; downstream resolved public ingress owns writer validation/creation.",
            fallback="Legacy authority injection with verified authority is rejected; no optional authority fallback bypasses the service preflight.",
            caller_symbol="build_provider_memory_service_from_env",
            tests=["test_builtin_local_capability_wires_provider_hermes_and_filesystem_without_entrypoint_patch"],
        ),
        _row(
            row_id="configured_hermes_sync_turn",
            trigger="HermesMemoryProvider.sync_turn",
            trigger_path=HERMES,
            composition_root="HermesMemoryProvider.__init__",
            authority_arguments=[
                "service=None composes memory_plane + verified_production_host_authority or host capability/material verifier",
                "authenticated_host_ingress forwarded to both _sync_composite_event calls",
            ],
            outcome="Construction and rejected ingress are write-free; authenticated turn creates one writer through the canonical service preflight.",
            fallback="Invalid service-plus-authority composition raises ValueError; rejected ingress cannot create durable writer state.",
            caller_symbol="sync_turn",
            tests=["test_configured_hermes_constructs_write_free_then_creates_once_after_authenticated_turn"],
        ),
        _row(
            row_id="configured_hermes_memory_write",
            trigger="HermesMemoryProvider.on_memory_write",
            trigger_path=HERMES,
            composition_root="HermesMemoryProvider.__init__",
            authority_arguments=[
                "configured Hermes service authority is retained by self._service",
                "authenticated_host_ingress forwarded unchanged to apply_memory_write",
            ],
            outcome="Resolved ingress reaches the service preflight before writer creation; missing/rejected ingress is write-free.",
            fallback="Target classification is typed; malformed or foreign durable writer fails closed in the canonical service owner.",
            caller_symbol="on_memory_write",
            tests=["test_memory_write_preflights_ingress_before_writer_creation"],
        ),
        _row(
            row_id="filesystem_root",
            trigger="build_filesystem_provider",
            trigger_path=FILESYSTEM,
            composition_root="FilesystemStorageBundle.build_provider_memory_service",
            authority_arguments=[
                "verified_production_host_authority forwarded through filesystem bundle to repository factory",
                "authenticated ingress remains the subsequent ProviderMemoryService public trigger argument",
            ],
            outcome="Filesystem composition is write-free; resolved public ingress writes at most one canonical writer record.",
            fallback="No authority means source-only behavior; invalid durable JSONL writer fails closed before a new ingestion record.",
            caller_symbol="build_filesystem_provider",
            tests=["test_builtin_local_capability_wires_provider_hermes_and_filesystem_without_entrypoint_patch"],
        ),
    ]
    payload = {
        "schema": "memorii.production-entrypoint-bindings.v14",
        "supersedes": "production-entrypoint-bindings-v13.json",
        "family": "writer_admission_authenticated_ingress",
        "source_hashes": {
            path: sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCES
        },
        "rows": rows,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

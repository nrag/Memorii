"""Contract checks for the opaque scenario public-ingress runner."""

from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.atomic_store import PreplanningStoreError
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.local_analyzer import (
    _analysis_spans_are_valid,
    _is_protected_scenario_owner_pair,
)
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_scenario_test_host_capability,
    build_scenario_test_provider_service,
)

ROOT = Path(__file__).resolve().parents[4]
RUNNER = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/run_scenario_ingress.py"


def _runner_module():
    sys.path.insert(0, str(RUNNER.parent))
    spec = importlib.util.spec_from_file_location("scenario_public_ingress_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


def test_scenario_runner_uses_provider_ingress_and_opaque_nonreusable_ids() -> None:
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "EnglishRuleMemoryExtractor" not in imported
    assert "ProductionLocalSemanticAnalyzer" not in imported
    assert "ProviderMemoryService" in imported
    assert "build_scenario_test_provider_service" in RUNNER.read_text(encoding="utf-8")

    runner = _runner_module()
    first = runner._opaque_event_id(ordinal=0, source_bytes=b"Atlas owner is Alice.")
    assert first.startswith("scenario-event-") and len(first) == 47
    assert first != runner._opaque_event_id(ordinal=1, source_bytes=b"Atlas owner is Alice.")
    assert first != runner._opaque_event_id(ordinal=0, source_bytes=b"Atlas owner is Bob.")
    body = {
        "schema_id": "memorii.scenario_first.public_ingress_id",
        "schema_version": 1,
        "traversal_ordinal": 0,
        "rendered_source_sha256": hashlib.sha256(b"Atlas owner is Alice.").hexdigest(),
        "user_id": "scenario-user",
        "session_id": "scenario-session",
        "task_id": "scenario-task",
    }
    expected = "scenario-event-" + hashlib.sha256(
        b"memorii.scenario-first.public-ingress-id.v1\0"
        + runner.encode_typed_value(body)
    ).hexdigest()[:32]
    assert first == expected
    assert first != "scenario-event-" + hashlib.sha256(
        b"memorii.scenario-first.public-ingress-id.v1\0"
        + json.dumps(body, sort_keys=True).encode("utf-8")
    ).hexdigest()[:32]


def test_scenario_host_explicitly_activates_only_its_verified_writer() -> None:
    def now() -> datetime:
        return datetime(2026, 7, 30, tzinfo=UTC)

    activated = build_scenario_test_provider_service(
        memory_plane=None, now_provider=now
    )
    assert activated._semantic_writer_admission.current().active_runtime_mode == "verified_semantic"

    unactivated = ProviderMemoryService._from_scenario_test_host(
        host_bootstrap_capability=replace(
            build_scenario_test_host_capability(), initial_writer_activation=None
        ),
        now_provider=now,
    )
    assert unactivated._semantic_writer_admission.current().active_runtime_mode == "evidence_only"

    default_root = ProviderMemoryService(
        host_bootstrap_capability=build_scenario_test_host_capability(), now_provider=now
    )
    assert default_root._bootstrap_profile is None
    assert default_root._provider_ingestion._semantic_runtime is None


def test_scenario_host_activation_changes_the_public_sync_event_effect_boundary() -> None:
    """The host activation is causal: only it permits the accepted public effect."""

    def now() -> datetime:
        return datetime(2026, 7, 30, tzinfo=UTC)

    def sync_owner_event(service: ProviderMemoryService, *, content: str = "Atlas owner is Alice."):
        return service.sync_event(
            operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
            content=content,
            operation_id="scenario-activation-public-event",
            session_id="scenario-session",
            task_id="scenario-task",
            user_id="scenario-user",
            language="en",
            speaker_id="scenario-speaker",
            timestamp=now(),
            authenticated_host_ingress=_runner_module()._host_ingress(ordinal=0),
        )

    activated = build_scenario_test_provider_service(
        memory_plane=MemoryPlaneService(), now_provider=now
    )
    sync_owner_event(activated)
    activated_projection = _runner_module()._persisted_projection(
        activated, operation_id="scenario-activation-public-event"
    )
    assert activated_projection["terminal_status"] == "accepted"
    assert activated_projection["terminal_sealed_operation_count"] == 1
    assert activated_projection["terminal_accepted_carrier_count"] == 1

    unactivated = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        host_bootstrap_capability=replace(
            build_scenario_test_host_capability(), initial_writer_activation=None
        ),
        now_provider=now,
    )
    with pytest.raises(
        PreplanningStoreError,
        match="semantic ingestion terminal-group retry budget exhausted",
    ) as rejected:
        sync_owner_event(unactivated)
    assert isinstance(rejected.value.__cause__, PreplanningStoreError)
    assert str(rejected.value.__cause__) == "evidence-only writer cannot publish graph or event effects"
    unactivated_member_kinds = {
        record.content["member"]["kind"]
        for record in unactivated._memory_plane.list_records()
        if record.source_kind == "semantic_ingestion_generation_member"
    }
    assert "graph_delta" not in unactivated_member_kinds
    assert "event_batch" not in unactivated_member_kinds


def test_scenario_runner_uses_one_protected_ambiguity_event_without_effects() -> None:
    runner = _runner_module()
    scenario_path = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/scenario-first-v1.json"
    result = runner.run(
        json.loads(scenario_path.read_text(encoding="utf-8")),
        scenario_bytes=scenario_path.read_bytes(),
        design_bytes=(ROOT / "docs/design/semantic_ingestion_architecture.md").read_bytes(),
        registry_bytes=(
            ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
        ).read_bytes(),
    )
    assert len(result["runs"]) == 4
    ambiguity = result["runs"][-1]
    assert ambiguity["comparator_result"] == "ambiguous"
    protected = result["stable_evidence"][-1]
    assert protected["terminal_status"] == "unresolved"
    assert protected["terminal_sealed_operation_count"] == 0
    assert protected["terminal_accepted_carrier_count"] == 0


@pytest.mark.parametrize(
    ("content", "expected_terminal", "expected_reason"),
    (
        (
            "Atlas owner is Alice. Atlas owner is Bob.",
            "unresolved",
            "protected_multi_segment_owner_ambiguity",
        ),
        ("Atlas owner is Alice.", "accepted", None),
        (
            "Atlas owner is Alice. Atlas owner is Bob.x",
            None,
            "unsupported_grammar",
        ),
        (
            "Atlas owner is Alice.xAtlas owner is Bob.",
            None,
            "unsupported_grammar",
        ),
    ),
)
def test_provider_ingress_partitions_each_child_without_a_whole_source_corpus_row(
    content: str, expected_terminal: str | None, expected_reason: str | None,
) -> None:
    """Only sealed child literals, never a synthetic combined literal, select V1."""

    runner = _runner_module()
    operation_id = "scenario-child-corpus-" + hashlib.sha256(content.encode()).hexdigest()[:16]
    service = build_scenario_test_provider_service(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: datetime(2026, 7, 30, tzinfo=UTC),
    )
    result = service.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content=content,
        operation_id=operation_id,
        session_id="scenario-session",
        task_id="scenario-task",
        user_id="scenario-user",
        language="en",
        speaker_id="scenario-speaker",
        timestamp=datetime(2026, 7, 30, tzinfo=UTC),
        authenticated_host_ingress=runner._host_ingress(ordinal=41),
    )
    if expected_terminal is None:
        assert result.blocked_reasons["semantic_ingestion"] == "source_only"
        assert not result.candidate_ids
        outcomes = [
            record.content
            for record in service._memory_plane.list_records()
            if record.source_kind == "semantic_ingestion_profile_outcome"
            and record.content.get("source_admission", {}).get("source_id")
            in result.transcript_ids
        ]
        assert len(outcomes) == 1
        assert outcomes[0]["kind"] == "unsupported_input"
        assert outcomes[0]["reason"] == expected_reason
        return

    projection = runner._persisted_projection(service, operation_id=operation_id)
    assert projection["terminal_status"] == expected_terminal
    if expected_reason is None:
        assert projection["terminal_reason_codes"] == ()
    else:
        assert projection["terminal_reason_codes"] == (expected_reason,)


def test_multi_segment_route_selection_rejects_swapped_duplicate_and_wrong_source_evidence() -> None:
    """Each analysis must retain its own child route; source-wide fallback is forbidden."""

    source_id, source_digest = "source:pair", "a" * 64
    first_route = SimpleNamespace(
        route_digest="1" * 64,
        segment_text_artifact_id="local:first",
        segment_text_artifact_digest="2" * 64,
        segment_text_content_digest="3" * 64,
    )
    second_route = SimpleNamespace(
        route_digest="4" * 64,
        segment_text_artifact_id="local:second",
        segment_text_artifact_digest="5" * 64,
        segment_text_content_digest="6" * 64,
    )
    prepared = SimpleNamespace(
        preparation_fingerprint="7" * 64,
        segments=(
            SimpleNamespace(segment_id="child:first", parent_projection_segment_id="parent:first"),
            SimpleNamespace(segment_id="child:second", parent_projection_segment_id="parent:second"),
        ),
        segment_language_routes=SimpleNamespace(routes=(first_route, second_route)),
    )

    def span_for(route, parent):
        artifact = SimpleNamespace(
            artifact_id=route.segment_text_artifact_id,
            artifact_digest=route.segment_text_artifact_digest,
            content_digest=route.segment_text_content_digest,
        )
        return SimpleNamespace(
            source_id=source_id,
            projection_segment_id=parent,
            segment_local_span=SimpleNamespace(artifact=artifact),
        )

    def analysis_for(*, segment_id, route, parent, candidate_id, analysis_source_id=source_id):
        span = span_for(route, parent)
        interpretation = SimpleNamespace(
            predicate_head_span=span,
            assignments=(SimpleNamespace(argument_span=span),),
        )
        consensus = SimpleNamespace(
            source_id=analysis_source_id,
            source_digest=source_digest,
            preparation_fingerprint=prepared.preparation_fingerprint,
            segment_id=segment_id,
            segment_language_route_digest=route.route_digest,
            primary_interpretation=interpretation,
            corroborating_interpretation=interpretation,
        )
        return SimpleNamespace(
            candidate_id=candidate_id,
            source_id=analysis_source_id,
            source_digest=source_digest,
            parser_consensus=consensus,
        )

    first = analysis_for(
        segment_id="child:first", route=first_route, parent="parent:first", candidate_id="alice"
    )
    second = analysis_for(
        segment_id="child:second", route=second_route, parent="parent:second", candidate_id="bob"
    )
    authority = SimpleNamespace(source_digest=source_digest)
    assert _analysis_spans_are_valid(
        analysis=second,
        source_id=source_id,
        source_text="ignored-by-bound-span-validation",
        prepared_source=prepared,
        source_authority_evidence=authority,
        source_interval_evidence=None,
    )

    # A second-segment analysis cannot relabel its copied spans with the first
    # route's local artifact, even though both routes belong to the same source.
    swapped = analysis_for(
        segment_id="child:second", route=first_route, parent="parent:second", candidate_id="bob"
    )
    assert not _analysis_spans_are_valid(
        analysis=swapped,
        source_id=source_id,
        source_text="ignored-by-bound-span-validation",
        prepared_source=prepared,
        source_authority_evidence=authority,
        source_interval_evidence=None,
    )

    candidates = (
        SimpleNamespace(assertion_quote="Atlas owner is Alice.", predicate_id="owner", candidate_id="alice"),
        SimpleNamespace(assertion_quote="Atlas owner is Bob.", predicate_id="owner", candidate_id="bob"),
    )
    assert _is_protected_scenario_owner_pair(candidates, (first, second))
    duplicate_route = analysis_for(
        segment_id="child:first", route=first_route, parent="parent:first", candidate_id="bob"
    )
    assert not _is_protected_scenario_owner_pair(
        candidates, (first, duplicate_route)
    )
    assert not _is_protected_scenario_owner_pair(
        candidates,
        (first, analysis_for(
            segment_id="child:second", route=second_route, parent="parent:second",
            candidate_id="bob", analysis_source_id="source:other",
        )),
    )
    equal_value = (
        SimpleNamespace(assertion_quote="Atlas owner is Alice.", predicate_id="owner", candidate_id="alice"),
        SimpleNamespace(assertion_quote="Atlas owner is Alice.", predicate_id="owner", candidate_id="bob"),
    )
    assert not _is_protected_scenario_owner_pair(equal_value, (first, second))


def test_scenario_runner_emits_opaque_ids_for_the_actual_public_events() -> None:
    runner = _runner_module()
    scenario_path = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/scenario-first-v1.json"
    result = runner.run(
        json.loads(scenario_path.read_text(encoding="utf-8")),
        scenario_bytes=scenario_path.read_bytes(),
        design_bytes=(ROOT / "docs/design/semantic_ingestion_architecture.md").read_bytes(),
        registry_bytes=(
            ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
        ).read_bytes(),
    )

    emitted_ids = [row["provider_event_id"] for row in result["runs"]]
    assert emitted_ids == [
        runner._opaque_event_id(
            ordinal=ordinal,
            source_bytes=base64.b64decode(row["rendered_bytes_base64"]),
        )
        for ordinal, row in enumerate(result["runs"])
    ]
    assert len(emitted_ids) == len(set(emitted_ids))
    assert all(event_id.startswith("scenario-event-") and len(event_id) == 47 for event_id in emitted_ids)


def test_scenario_public_sync_event_reopens_retries_exactly_and_rejects_substitution(
    tmp_path: Path,
) -> None:
    """A real JSONL reopen retains the exact public event, never a substitute."""

    def now() -> datetime:
        return datetime(2026, 7, 30, tzinfo=UTC)

    storage = tmp_path / "scenario-public-reopen"
    first = build_scenario_test_provider_service(
        memory_plane=MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage)),
        now_provider=now,
    )
    kwargs = {
        "operation": ProviderOperation.MEMORY_WRITE_LONGTERM,
        "content": "Atlas owner is Alice.",
        "operation_id": "scenario-jsonl-public-event",
        "session_id": "scenario-session",
        "task_id": "scenario-task",
        "user_id": "scenario-user",
        "language": "en",
        "speaker_id": "scenario-speaker",
        "timestamp": now(),
        "authenticated_host_ingress": _runner_module()._host_ingress(ordinal=0),
    }
    first.sync_event(**kwargs)
    first_records = tuple(first._memory_plane.list_records())

    reopened = build_scenario_test_provider_service(
        memory_plane=MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage)),
        now_provider=now,
    )
    reopened.sync_event(**kwargs)
    assert tuple(reopened._memory_plane.list_records()) == first_records

    with pytest.raises(PreplanningStoreError, match="atomic admission evidence is partial or mismatched"):
        reopened.sync_event(**{**kwargs, "content": "Atlas owner is Bob."})
    assert tuple(reopened._memory_plane.list_records()) == first_records

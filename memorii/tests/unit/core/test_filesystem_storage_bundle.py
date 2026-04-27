from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.decision_state import DecisionStateService
from memorii.core.filesystem_storage import (
    FilesystemStorageBundle,
    FilesystemStoragePolicy,
    collect_storage_status,
    ensure_within_soft_limits,
)
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.work_state import WorkStateService
from memorii.domain.enums import CommitStatus, MemoryDomain


def _timestamp() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


def test_from_root_creates_expected_store_paths_directories(tmp_path) -> None:
    root = tmp_path / "storage"
    bundle = FilesystemStorageBundle.from_root(root)

    assert bundle.work_state_store._base_path == root / "work_state"
    assert bundle.decision_state_store._base_path == root / "decision_state"
    assert bundle.memory_plane_store._base_path == root / "memory_plane"
    assert bundle.llm_trace_store._path == root / "llm_decision" / "traces.jsonl"
    assert bundle.eval_snapshot_store._path == root / "llm_decision" / "eval_snapshots.jsonl"
    assert bundle.golden_candidate_store._path == root / "llm_decision" / "golden_candidates.jsonl"

    assert (root / "work_state").is_dir()
    assert (root / "decision_state").is_dir()
    assert (root / "memory_plane").is_dir()


def test_build_work_state_service_persists_across_fresh_bundles(tmp_path) -> None:
    root = tmp_path / "storage"
    first = FilesystemStorageBundle.from_root(root)
    first_service = first.build_work_state_service()

    created = first_service.open_or_resume_work(
        title="Persisted work",
        summary="original",
        session_id="session:1",
        task_id="task:1",
        user_id="user:1",
    )

    second_service = FilesystemStorageBundle.from_root(root).build_work_state_service()
    loaded = second_service.get_state(created.work_state_id)
    assert loaded is not None
    assert loaded.title == "Persisted work"


def test_build_decision_state_service_persists_across_fresh_bundles(tmp_path) -> None:
    root = tmp_path / "storage"
    first = FilesystemStorageBundle.from_root(root)
    decision = first.build_decision_state_service().open_decision(
        question="Which approach should we choose?",
        session_id="session:1",
        task_id="task:1",
    )

    second_service = FilesystemStorageBundle.from_root(root).build_decision_state_service()
    loaded = second_service.get_decision(decision.decision_id)
    assert loaded is not None
    assert loaded.question == "Which approach should we choose?"


def test_build_memory_plane_service_persists_across_fresh_bundles(tmp_path) -> None:
    root = tmp_path / "storage"
    first = FilesystemStorageBundle.from_root(root)
    first_plane = first.build_memory_plane_service()
    first_plane.stage_record(
        CanonicalMemoryRecord(
            memory_id="cand:mem:1",
            domain=MemoryDomain.EPISODIC,
            text="Persist me",
            content={"text": "Persist me"},
            status=CommitStatus.CANDIDATE,
            source_kind="provider:test",
            timestamp=_timestamp(),
            task_id="task:1",
            session_id="session:1",
        )
    )

    second_plane = FilesystemStorageBundle.from_root(root).build_memory_plane_service()
    loaded = second_plane.get_record("cand:mem:1")
    assert loaded is not None
    assert loaded.text == "Persist me"


def test_build_provider_memory_service_wires_services_together(tmp_path) -> None:
    provider = FilesystemStorageBundle.from_root(tmp_path / "storage").build_provider_memory_service()

    assert isinstance(provider._memory_plane, MemoryPlaneService)
    assert isinstance(provider._work_state_service, WorkStateService)
    assert isinstance(provider._decision_state_service, DecisionStateService)
    assert provider._llm_decision_trace_store is not None


def test_provider_record_progress_writes_work_state_event_and_memory_candidate(tmp_path) -> None:
    provider = FilesystemStorageBundle.from_root(tmp_path / "storage").build_provider_memory_service()
    open_result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {"title": "Ship release", "task_id": "task:1", "session_id": "session:1"},
    )
    assert open_result.ok is True

    progress_result = provider.handle_tool_call(
        "memorii_record_progress",
        {
            "task_id": "task:1",
            "session_id": "session:1",
            "content": "Completed release dry run",
            "evidence_ids": ["ev:1"],
        },
    )
    assert progress_result.ok is True

    reopened = FilesystemStorageBundle.from_root(tmp_path / "storage")
    work_events = reopened.build_work_state_service().list_work_state_events(
        progress_result.result["work_state_id"]
    )
    assert any(event.event_id == progress_result.result["event_id"] for event in work_events)

    candidate_id = progress_result.result["memory_candidate_id"]
    candidate = reopened.build_memory_plane_service().get_record(candidate_id)
    assert candidate is not None
    assert candidate.domain == MemoryDomain.EPISODIC
    assert candidate.status == CommitStatus.CANDIDATE


def test_llm_trace_store_persists_promotion_trace_when_provider_records_outcome(tmp_path) -> None:
    provider = FilesystemStorageBundle.from_root(tmp_path / "storage").build_provider_memory_service()
    provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {"title": "Investigate timeout", "task_id": "task:trace", "session_id": "session:trace"},
    )

    outcome_result = provider.handle_tool_call(
        "memorii_record_outcome",
        {
            "task_id": "task:trace",
            "session_id": "session:trace",
            "outcome": "completed",
            "content": "Timeout root cause confirmed",
            "evidence_ids": ["evidence:1"],
        },
    )
    assert outcome_result.ok is True

    traces = FilesystemStorageBundle.from_root(tmp_path / "storage").llm_trace_store.list_traces()
    assert traces
    assert outcome_result.result["promotion_trace_id"] in {trace.trace_id for trace in traces}


def test_collect_storage_status_reports_total_bytes_and_file_statuses(tmp_path) -> None:
    root = tmp_path / "storage"
    nested = root / "nested"
    nested.mkdir(parents=True)
    one = nested / "a.bin"
    two = root / "b.bin"
    one.write_bytes(b"1234")
    two.write_bytes(b"123456")

    status = collect_storage_status(root, FilesystemStoragePolicy(max_file_bytes=5, max_total_bytes=20))
    assert status.total_bytes == 10
    assert status.exceeds_total_limit is False
    by_path = {item.path: item for item in status.files}
    assert by_path[str(one)].size_bytes == 4
    assert by_path[str(one)].exceeds_file_limit is False
    assert by_path[str(two)].size_bytes == 6
    assert by_path[str(two)].exceeds_file_limit is True


def test_ensure_within_soft_limits_marks_exceeded_without_deleting(tmp_path) -> None:
    root = tmp_path / "storage"
    path = root / "large.bin"
    root.mkdir(parents=True)
    payload = b"x" * 9
    path.write_bytes(payload)

    status = ensure_within_soft_limits(
        root,
        FilesystemStoragePolicy(
            max_file_bytes=5,
            max_total_bytes=8,
            archive_enabled=False,
            compact_enabled=False,
        ),
    )

    assert status.exceeds_total_limit is True
    assert status.files[0].exceeds_file_limit is True
    assert path.exists()
    assert path.read_bytes() == payload


def test_default_in_memory_constructors_unchanged_outside_bundle() -> None:
    provider = ProviderMemoryService()
    memory_plane = MemoryPlaneService()
    work_state = WorkStateService()
    decision_state = DecisionStateService()

    assert provider._work_state_service is None
    assert provider._llm_decision_trace_store is None
    assert memory_plane._records.__class__.__name__ == "InMemoryMemoryPlaneStore"
    assert work_state._store.__class__.__name__ == "InMemoryWorkStateStore"
    assert decision_state._store.__class__.__name__ == "InMemoryDecisionStateStore"

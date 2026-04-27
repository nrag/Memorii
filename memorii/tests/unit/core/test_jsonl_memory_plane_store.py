from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.domain.enums import CommitStatus, MemoryDomain


def _record(
    memory_id: str,
    *,
    status: CommitStatus = CommitStatus.CANDIDATE,
    domain: MemoryDomain = MemoryDomain.EPISODIC,
    source_kind: str = "provider:memory_write",
    text: str = "candidate memory",
    content: dict | None = None,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=domain,
        text=text,
        content=content or {"text": text},
        status=status,
        source_kind=source_kind,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        task_id="task-1",
        session_id="session-1",
    )


def test_stage_then_get_by_id(tmp_path) -> None:
    store = JsonlMemoryPlaneStore(tmp_path / "memory_plane")
    record = _record("cand:1")
    store.stage_record(record)

    loaded = store.get_record("cand:1")
    assert loaded == record


def test_latest_record_wins_by_memory_id(tmp_path) -> None:
    store = JsonlMemoryPlaneStore(tmp_path / "memory_plane")
    store.stage_record(_record("cand:1", text="old text"))
    store.upsert_record(_record("cand:1", text="new text", content={"text": "new text", "version": 2}))

    loaded = store.get_record("cand:1")
    assert loaded is not None
    assert loaded.text == "new text"
    assert loaded.content["version"] == 2


def test_list_records_returns_latest_only(tmp_path) -> None:
    store = JsonlMemoryPlaneStore(tmp_path / "memory_plane")
    store.stage_record(_record("cand:1", text="first"))
    store.upsert_record(_record("cand:1", text="second"))
    store.stage_record(_record("cand:2", text="other"))

    items = store.list_records()
    by_id = {item.memory_id: item for item in items}
    assert len(items) == 2
    assert by_id["cand:1"].text == "second"
    assert by_id["cand:2"].text == "other"


def test_list_filters_match_in_memory_shape(tmp_path) -> None:
    store = JsonlMemoryPlaneStore(tmp_path / "memory_plane")
    store.stage_record(_record("cand:1", status=CommitStatus.CANDIDATE, domain=MemoryDomain.EPISODIC, source_kind="provider:sync_turn"))
    store.stage_record(_record("mem:1", status=CommitStatus.COMMITTED, domain=MemoryDomain.SEMANTIC, source_kind="provider_seed"))
    store.stage_record(_record("tx:1", status=CommitStatus.COMMITTED, domain=MemoryDomain.TRANSCRIPT, source_kind="provider"))

    committed = store.list_records(status=CommitStatus.COMMITTED)
    assert {item.memory_id for item in committed} == {"mem:1", "tx:1"}

    semantic = store.list_records(domains=[MemoryDomain.SEMANTIC])
    assert [item.memory_id for item in semantic] == ["mem:1"]

    provider_seed = store.list_records(source_kind="provider_seed")
    assert [item.memory_id for item in provider_seed] == ["mem:1"]


def test_committed_promoted_record_survives_replay(tmp_path) -> None:
    store = JsonlMemoryPlaneStore(tmp_path / "memory_plane")
    store.stage_record(_record("cand:1", status=CommitStatus.CANDIDATE, text="candidate"))
    store.upsert_record(
        _record(
            "cand:1",
            status=CommitStatus.CANDIDATE,
            content={"text": "candidate", "promotion_trace": {"decision": "commit"}},
        )
    )
    store.stage_record(
        _record(
            "mem:episodic:cand:1",
            status=CommitStatus.COMMITTED,
            domain=MemoryDomain.EPISODIC,
            text="candidate",
            content={"text": "candidate", "promotion_state": "committed"},
        )
    )

    reopened = JsonlMemoryPlaneStore(tmp_path / "memory_plane")
    committed = reopened.get_record("mem:episodic:cand:1")
    assert committed is not None
    assert committed.status == CommitStatus.COMMITTED
    assert committed.content["promotion_state"] == "committed"


def test_promotion_metadata_and_lineage_metadata_survive_replay(tmp_path) -> None:
    store = JsonlMemoryPlaneStore(tmp_path / "memory_plane")
    store.stage_record(
        _record(
            "cand:merge-1",
            content={
                "text": "user prefers concise release notes",
                "promotion_metadata": {"reason_codes": ["stable_preference", "multi_turn_signal"]},
                "lineage": {"supersedes": ["mem:user:old-1"], "merged_from": ["cand:a", "cand:b"]},
                "provenance": {"source_ids": ["evt:1", "evt:2"]},
            },
        )
    )

    reopened = JsonlMemoryPlaneStore(tmp_path / "memory_plane")
    loaded = reopened.get_record("cand:merge-1")
    assert loaded is not None
    assert loaded.content["promotion_metadata"]["reason_codes"] == ["stable_preference", "multi_turn_signal"]
    assert loaded.content["lineage"]["supersedes"] == ["mem:user:old-1"]
    assert loaded.content["provenance"]["source_ids"] == ["evt:1", "evt:2"]


def test_missing_file_returns_empty_list(tmp_path) -> None:
    store = JsonlMemoryPlaneStore(tmp_path / "memory_plane")
    assert store.list_records() == []
    assert store.get_record("missing") is None


def test_fresh_store_reads_previous_records(tmp_path) -> None:
    path = tmp_path / "memory_plane"
    first = JsonlMemoryPlaneStore(path)
    first.stage_record(_record("cand:1"))
    first.stage_record(_record("cand:2", domain=MemoryDomain.USER))

    second = JsonlMemoryPlaneStore(path)
    assert {item.memory_id for item in second.list_records()} == {"cand:1", "cand:2"}


def test_jsonl_file_keeps_append_history(tmp_path) -> None:
    path = tmp_path / "memory_plane"
    store = JsonlMemoryPlaneStore(path)
    store.stage_record(_record("cand:1", text="v1"))
    store.upsert_record(_record("cand:1", text="v2"))
    store.upsert_record(_record("cand:1", text="v3"))

    with (path / "memory_records.jsonl").open("r", encoding="utf-8") as handle:
        lines = [line.strip() for line in handle if line.strip()]

    assert len(lines) == 3
    assert '"text":"v1"' in lines[0]
    assert '"text":"v2"' in lines[1]
    assert '"text":"v3"' in lines[2]

"""Bounded design feasibility probe; not production or certification evidence."""

from pathlib import Path
from tempfile import TemporaryDirectory

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import InMemoryMemoryPlaneStore, JsonlMemoryPlaneStore
from memorii.domain.enums import CommitStatus, MemoryDomain


def probe(store):
    record = CanonicalMemoryRecord(
        memory_id="source-example", domain=MemoryDomain.TRANSCRIPT,
        text="original evidence", content={"text": "original evidence"},
        status=CommitStatus.COMMITTED, task_id="task-example", is_raw_event=True,
    )
    store.write_records((record,))
    revision, rows = store.read_snapshot()
    rows[0].content["text"] = "mutated caller copy"
    assert store.get_record(record.memory_id).content["text"] == "original evidence"
    retained_revision, retained = store.read_snapshot()
    store.write_records((record.model_copy(update={"memory_id": "other-source"}),))
    current_revision, current = store.read_snapshot()
    assert revision == retained_revision < current_revision
    assert len(retained) == 1 and len(current) == 2
    assert retained[0].text == "original evidence"
    return {"snapshot_is_detached": True, "retained_snapshot_stable": True,
            "runtime_revision_advanced": True}


if __name__ == "__main__":
    print("memory", probe(InMemoryMemoryPlaneStore()))
    with TemporaryDirectory() as temp:
        path = Path(temp) / "records.jsonl"
        print("jsonl", probe(JsonlMemoryPlaneStore(path)))
        assert len(JsonlMemoryPlaneStore(path).read_snapshot()[1]) == 2
        print("jsonl reopen retains both records: true")

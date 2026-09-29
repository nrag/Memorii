"""Fresh-process persistence over the shared SQLite application-data partition.

Process A writes canonical memory batches; independent processes B and C open
the same partition by path and must observe identical records, order and both
revision counters without any in-process state from A.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.domain.enums import CommitStatus, MemoryDomain

_WRITER_PROGRAM = """
import sys
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility


def record(memory_id: str, visibility: MemoryRecordVisibility) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.SEMANTIC,
        text=f"from-process:{memory_id}",
        content={"writer": "subprocess"},
        status=CommitStatus.COMMITTED,
        source_kind="partition_recovery",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        visibility=visibility,
    )


store = SqliteMemoryPlaneStore(Path(sys.argv[1]))
store.stage_record(record("mem:writer:one", MemoryRecordVisibility.RUNTIME_CONTEXT))
store.stage_record(record("mem:writer:internal", MemoryRecordVisibility.INTERNAL_CONTROL))
store.stage_record(record("mem:writer:two", MemoryRecordVisibility.RUNTIME_CONTEXT))
print(store.revision(), store.read_write_snapshot()[0])
"""

_READER_PROGRAM = """
import sys
from pathlib import Path

from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore

store = SqliteMemoryPlaneStore(Path(sys.argv[1]))
revision, records = store.read_snapshot()
write_revision = store.read_write_snapshot()[0]
print(revision, write_revision, [record.memory_id for record in records])
"""


def test_independent_processes_share_one_partition_state(tmp_path: Path) -> None:
    partition_dir = tmp_path / "store"

    writer = subprocess.run(
        [sys.executable, "-c", _WRITER_PROGRAM, str(partition_dir)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert writer.stdout.strip() == "2 3"

    reader = subprocess.run(
        [sys.executable, "-c", _READER_PROGRAM, str(partition_dir)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert (
        reader.stdout.strip()
        == "2 3 ['mem:writer:one', 'mem:writer:internal', 'mem:writer:two']"
    )

    parent_store = SqliteMemoryPlaneStore(partition_dir)
    parent_store.stage_record(
        CanonicalMemoryRecord(
            memory_id="mem:parent:append",
            domain=MemoryDomain.SEMANTIC,
            text="from-parent",
            status=CommitStatus.COMMITTED,
            source_kind="partition_recovery",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    final_reader = subprocess.run(
        [sys.executable, "-c", _READER_PROGRAM, str(partition_dir)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert (
        final_reader.stdout.strip()
        == "3 4 ['mem:writer:one', 'mem:writer:internal', 'mem:writer:two', 'mem:parent:append']"
    )


def test_cross_process_compare_and_swap_serializes_writers(tmp_path: Path) -> None:
    partition_dir = tmp_path / "store"
    parent_store = SqliteMemoryPlaneStore(partition_dir)
    parent_store.stage_record(
        CanonicalMemoryRecord(
            memory_id="mem:cas:seed",
            domain=MemoryDomain.SEMANTIC,
            text="seed",
            status=CommitStatus.COMMITTED,
            source_kind="partition_recovery",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    stale_data_revision = parent_store.revision()

    competing_writer = subprocess.run(
        [
            sys.executable,
            "-c",
            _WRITER_PROGRAM,
            str(partition_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert competing_writer.stdout.strip() == "3 4"

    import pytest
    from memorii.core.memory_plane.store import MemoryPlaneRevisionConflictError

    with pytest.raises(MemoryPlaneRevisionConflictError):
        parent_store.apply_batch(
            (
                CanonicalMemoryRecord(
                    memory_id="mem:cas:stale",
                    domain=MemoryDomain.SEMANTIC,
                    text="stale",
                    status=CommitStatus.COMMITTED,
                    source_kind="partition_recovery",
                    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                ),
            ),
            expected_revision=stale_data_revision,
        )
    reopened = SqliteMemoryPlaneStore(partition_dir)
    assert reopened.get_record("mem:cas:stale") is None
    assert reopened.revision() == 3

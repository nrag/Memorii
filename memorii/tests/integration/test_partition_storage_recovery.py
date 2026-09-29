"""Fresh-process persistence over the shared SQLite application-data partition.

Process A writes canonical memory batches; independent processes B and C open
the same partition by path and must observe identical records, order and both
revision counters without any in-process state from A.
"""

from __future__ import annotations

import signal
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


_STAGED_PUBLICATION_PROGRAM = '''
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence.contracts import RuntimePublicationIntent
from memorii.core.storage_administration.service import (
    StorageAdministrationService,
    _position_digest,
    _position_sequence,
)
from memorii.domain.enums import CommitStatus, MemoryDomain

root = Path(sys.argv[1])
with StorageAdministrationService(root) as service:
    service.initialize()
    store = service.memory_plane_store()
    service.publish_memory_plane_batch(
        (
            CanonicalMemoryRecord(
                memory_id="mem:published:one",
                domain=MemoryDomain.SEMANTIC,
                text="published",
                status=CommitStatus.COMMITTED,
                source_kind="partition_recovery",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
        store=store,
    )
    # Stage the next publication to the crash boundary: durable intent and a
    # committed data generation, but no control finalization (process "dies").
    state = service._require_operational()
    finalized = service._control.read_publication_state(service._repository_id())
    partition = service.partition()
    with partition.manual_write_transaction() as handle:
        connection = handle.connection
        store.apply_batch_in_transaction(
            connection,
            (
                CanonicalMemoryRecord(
                    memory_id="mem:published:two",
                    domain=MemoryDomain.SEMANTIC,
                    text="staged",
                    status=CommitStatus.COMMITTED,
                    source_kind="partition_recovery",
                    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                ),
            ),
            expected_revision=None,
        )
        candidate = service._candidate_from_transaction(
            connection,
            generation_id=finalized.data_generation_id,
            epoch=state.eligibility_epoch,
        )
        partition.write_publication_row(
            connection,
            ordinal=candidate.vector.partition_ordinal,
            position_kind="batch",
            position_sequence=_position_sequence(candidate),
            position_digest=_position_digest(candidate),
            tuple_digest=candidate.payload_digest(),
            generation_id=finalized.data_generation_id,
            vector_json=candidate.vector.model_dump_json(),
            manifest_digest=candidate.manifest_digest,
        )
        service._control.write_intent(
            RuntimePublicationIntent(
                intent_id=uuid.uuid4().hex,
                repository_id=service._repository_id(),
                expected_old_discriminator=finalized.payload_digest(),
                candidate_state=candidate,
                operation_binding="memory_plane_batch",
                authority_epoch=state.eligibility_epoch,
                fence_token=finalized.vector.partition_ordinal + 1,
            ),
            service._journal_entry(
                operation="publication_prepared",
                before_digest=finalized.payload_digest(),
                after_digest=candidate.payload_digest(),
            ),
        )
        handle.commit()
print("staged")
'''

_RECOVERY_PROGRAM = '''
import sys
from pathlib import Path

from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.storage_administration.service import StorageAdministrationService

with StorageAdministrationService(Path(sys.argv[1])) as service:
    resolution = service.resolve_pending_publication()
    snapshot = service.acquire_verified_snapshot()
    store = SqliteMemoryPlaneStore(service.partition())
    print(resolution.disposition, snapshot.ordinal, store.revision())
'''


def test_dead_process_publication_is_recovered_by_a_fresh_process(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    staged = subprocess.run(
        [sys.executable, "-c", _STAGED_PUBLICATION_PROGRAM, str(root)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert staged.stdout.strip() == "staged"

    recovered = subprocess.run(
        [sys.executable, "-c", _RECOVERY_PROGRAM, str(root)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert recovered.stdout.strip() == "finalized 2 2"


_SEMANTIC_OWNER_PROGRAM = '''
import sys
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.persistence.factory import open_managed_partition
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility


def control_record(memory_id: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.SEMANTIC,
        text=f"owner-write:{memory_id}",
        status=CommitStatus.COMMITTED,
        source_kind="semantic_owner_journey",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


administration, memory_plane = open_managed_partition(Path(sys.argv[1]))
try:
    revision = memory_plane.conditionally_write_records(
        (control_record("mem:owner:bootstrap"),),
        preconditions=(),
    )
    revision = memory_plane.conditionally_write_records(
        (control_record("mem:owner:second"),),
        preconditions=(),
    )
    store = memory_plane._records
    print(store.revision(), store.read_write_snapshot()[0])
finally:
    administration.close()
'''


def test_semantic_owner_control_writes_persist_on_the_managed_partition(
    tmp_path: Path,
) -> None:
    """The domain-owner conditional-write path drives the selected backend."""
    from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
    from memorii.core.persistence.factory import open_managed_partition
    from memorii.core.storage_administration.service import (
        StorageAdministrationService,
    )

    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()

    writer = subprocess.run(
        [sys.executable, "-c", _SEMANTIC_OWNER_PROGRAM, str(root)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    # Internal-control batches do not advance the data revision; both batches
    # advance the write revision.
    assert writer.stdout.strip() == "0 2"

    administration, memory_plane = open_managed_partition(root)
    try:
        store = SqliteMemoryPlaneStore(administration.partition())
        records = {record.memory_id for record in store.list_records()}
        assert {"mem:owner:bootstrap", "mem:owner:second"} <= records
        snapshot = administration.acquire_verified_snapshot()
        assert snapshot.vector.memory_write_revision == 2
        assert snapshot.vector.memory_data_revision == 0
    finally:
        administration.close()
    del memory_plane


_CONCURRENT_PUBLISHER_PROGRAM = '''
import sys
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence.factory import open_managed_partition
from memorii.domain.enums import CommitStatus, MemoryDomain

root = Path(sys.argv[1])
index = sys.argv[2]
administration, memory_plane = open_managed_partition(root)
try:
    outcome = memory_plane._records.apply_batch(
        (
            CanonicalMemoryRecord(
                memory_id=f"mem:concurrent:{index}",
                domain=MemoryDomain.SEMANTIC,
                text=f"concurrent:{index}",
                status=CommitStatus.COMMITTED,
                source_kind="partition_recovery",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
        expected_revision=None,
    )
    print(outcome)
finally:
    administration.close()
'''


def test_concurrent_publishers_serialize_on_the_publication_fence(tmp_path: Path) -> None:
    from memorii.core.storage_administration.service import StorageAdministrationService

    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()

    processes = [
        subprocess.Popen(
            [sys.executable, "-c", _CONCURRENT_PUBLISHER_PROGRAM, str(root), str(index)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        for index in range(2)
    ]
    outputs = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=120)
        assert process.returncode == 0, stderr
        outputs.append(stdout.strip())

    assert sorted(outputs) == ["1", "2"]
    with StorageAdministrationService(root) as verifier:
        snapshot = verifier.acquire_verified_snapshot()
        assert snapshot.ordinal == 2
        assert snapshot.vector.memory_write_revision == 2
        store = SqliteMemoryPlaneStore(verifier.partition())
        assert {r.memory_id for r in store.list_records()} == {
            "mem:concurrent:0",
            "mem:concurrent:1",
        }


_KILLED_MID_TRANSACTION_PROGRAM = '''
import os
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence.factory import open_managed_partition
from memorii.domain.enums import CommitStatus, MemoryDomain

root = Path(sys.argv[1])
administration, memory_plane = open_managed_partition(root)
partition = administration.partition()
store = memory_plane._records._inner
# Open a write transaction, mutate rows, then die before commit: the next
# opener must observe the exact old state with no partial batch.
with partition.manual_write_transaction() as handle:
    connection = handle.connection
    store.apply_batch_in_transaction(
        connection,
        (
            CanonicalMemoryRecord(
                memory_id="mem:killed:uncommitted",
                domain=MemoryDomain.SEMANTIC,
                text="uncommitted",
                status=CommitStatus.COMMITTED,
                source_kind="partition_recovery",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
        expected_revision=None,
    )
    os.kill(os.getpid(), signal.SIGKILL)
'''


def test_sigkill_mid_transaction_leaves_exact_old_state(tmp_path: Path) -> None:
    from memorii.core.storage_administration.service import StorageAdministrationService

    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()

    killed = subprocess.run(
        [sys.executable, "-c", _KILLED_MID_TRANSACTION_PROGRAM, str(root)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert killed.returncode == -signal.SIGKILL

    with StorageAdministrationService(root) as verifier:
        snapshot = verifier.acquire_verified_snapshot()
        assert snapshot.ordinal == 0
        store = SqliteMemoryPlaneStore(verifier.partition())
        assert store.get_record("mem:killed:uncommitted") is None
        assert store.read_write_snapshot()[0] == 0

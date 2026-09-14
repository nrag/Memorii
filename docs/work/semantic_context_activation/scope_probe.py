"""Show why null scope cannot prove an explicitly global historical record."""

from datetime import UTC, datetime

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain


def main():
    fields = dict(
        memory_id="legacy-source", domain=MemoryDomain.TRANSCRIPT,
        text="source", status=CommitStatus.COMMITTED,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    omitted = CanonicalMemoryRecord(**fields)
    explicit = CanonicalMemoryRecord(
        **fields, task_id=None, session_id=None, user_id=None, agent_id=None,
        execution_node_id=None, solver_run_id=None,
    )
    assert omitted.model_dump(mode="json") == explicit.model_dump(mode="json")
    print("Persisted canonical shapes cannot distinguish omitted and explicit null scope.")


if __name__ == "__main__":
    main()

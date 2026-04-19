from datetime import UTC, datetime

from memorii.domain.common import Provenance, RoutingInfo
from memorii.domain.enums import CommitStatus, Durability, MemoryDomain, MemoryScope, SourceType
from memorii.domain.memory_object import MemoryObject


def test_memory_object_is_json_serializable() -> None:
    memory = MemoryObject(
        memory_id="memory-1",
        memory_type=MemoryDomain.TRANSCRIPT,
        scope=MemoryScope.TASK,
        durability=Durability.SESSION,
        status=CommitStatus.CANDIDATE,
        content={"message": "hello"},
        provenance=Provenance(
            source_type=SourceType.USER,
            source_refs=["msg-1"],
            created_at=datetime.now(UTC),
            created_by="tester",
        ),
        routing=RoutingInfo(primary_store="transcript", secondary_stores=["execution"]),
    )

    payload = memory.model_dump(mode="json")
    assert payload["memory_type"] == "transcript"
    assert payload["routing"]["primary_store"] == "transcript"

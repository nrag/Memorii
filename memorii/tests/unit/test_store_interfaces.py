from memorii.stores.base.interfaces import (
    DirectoryStore,
    EventLogStore,
    ExecutionGraphStore,
    MemoryObjectStore,
    OverlayStore,
    SolverGraphStore,
)


def test_store_interfaces_are_abstract() -> None:
    for cls in [
        MemoryObjectStore,
        ExecutionGraphStore,
        SolverGraphStore,
        EventLogStore,
        OverlayStore,
        DirectoryStore,
    ]:
        assert hasattr(cls, "__abstractmethods__")
        assert len(cls.__abstractmethods__) > 0

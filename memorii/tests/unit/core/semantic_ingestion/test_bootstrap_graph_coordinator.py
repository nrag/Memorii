from types import SimpleNamespace

from memorii.core.semantic_ingestion.bootstrap_graph_coordinator import (
    BootstrapGraphDependentCoordinatorV3,
)


def test_pre_graph_transition_mismatch_returns_closed_noncommit() -> None:
    """The coordinator must not persist or invoke a producer before epoch authority joins."""
    coordinator = BootstrapGraphDependentCoordinatorV3(
        epoch_repository=SimpleNamespace(),
        plan_repository=SimpleNamespace(),
        terminal_port=SimpleNamespace(),
        compiler=SimpleNamespace(),
        authorizer=SimpleNamespace(),
        group_commit_repository=SimpleNamespace(),
        terminal_preparer=SimpleNamespace(),
        terminal_host_authority=SimpleNamespace(),
    )
    result = coordinator.coordinate(
        request=SimpleNamespace(request_core_digest="a" * 64, request_digest="b" * 64),
        transition=SimpleNamespace(request_core_digest="c" * 64),
    )

    assert result.kind == "pre_graph_noncommit"
    assert result.reason == "authority_unavailable"
    assert result.request_digest == "b" * 64

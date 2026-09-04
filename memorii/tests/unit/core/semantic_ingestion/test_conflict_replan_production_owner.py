"""Production clarification-winner replan proof through the provider root.

The store-level race proof
(``test_prepared_projection_and_claimed_clarification_completion_have_one_cas_winner``)
establishes that a committed conflict clarification makes the stale projection
publisher's terminal persistence raise ``SemanticEventReplayError`` with zero
writes.  This module proves the production owner of the reload/replan loop:
the provider ingestion coordinator replans exactly once from a fresh internal
``conflict-replan:v1:`` delivery coordinate and completes the replanned
delivery, while a second consecutive staleness propagates fail-closed.  The
losing-race condition is injected at the exact persistence boundary the store
raises it, with the losing-race signal itself already proven by the
store-level reproducer.
"""


from memorii.core.memory_evolution.ingestion_contracts import (
    derive_conflict_replan_delivery_id,
)
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.semantic_ingestion.bootstrap_graph_host import (
    BootstrapGraphHostBundleBuilder,
)
from memorii.core.semantic_ingestion.event_replay import SemanticEventReplayError
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
    DeterministicBootstrapGraphAuthorityProviderV3,
)
from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import (
    provider_service,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _host_ingress,
    _v3_normalization_host_builder,
)

_OPERATION_ID = "conflict-replan-proof"


def _replan_service() -> object:
    normalization, _calls = _v3_normalization_host_builder()
    return provider_service(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                successful_calls=[]
            )
        ),
    )


def _control_states(service: object) -> dict[str, str]:
    states: dict[str, str] = {}
    for record in service._memory_plane.list_records(
        source_kind="semantic_ingestion_preplanning_control"
    ):
        control = record.content["control"]
        states[str(control["operation_fence"]["operation_id"])] = str(
            control["state"]
        )
    return states


def test_stale_projection_publication_replans_once_and_completes() -> None:
    service = _replan_service()
    coordinator = service._provider_ingestion
    # A terminal without server-owned policy is a real non-committing terminal
    # that flows to the terminal-persistence seam; the graph coordinator's own
    # CAS replan is out of scope for this proof.
    coordinator._semantic_policy_provider = None
    real_persist = coordinator._persist_semantic_terminal
    persist_operations: list[str] = []

    def stale_once(fence, terminal, *, authorization_guard):
        persist_operations.append(fence.operation_id)
        if len(persist_operations) == 1:
            raise SemanticEventReplayError(
                "event compilation state does not match repository graph revision"
            )
        return real_persist(
            fence, terminal, authorization_guard=authorization_guard
        )

    coordinator._persist_semantic_terminal = stale_once

    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id=_OPERATION_ID,
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )

    # The replan is internal: the public outcome keeps the ordinary shape.
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(persist_operations) == 2
    assert persist_operations[0] == _OPERATION_ID
    assert persist_operations[1] == derive_conflict_replan_delivery_id(
        _OPERATION_ID
    )
    states = _control_states(service)
    replan_id = derive_conflict_replan_delivery_id(_OPERATION_ID)
    assert states[replan_id] == "terminal"
    assert states[_OPERATION_ID] != "terminal"
    # Both deliveries retained their governed admission evidence: the public
    # delivery and exactly one internal replan delivery.
    admissions = service._memory_plane.list_records(
        source_kind="semantic_ingestion_admission_index"
    )
    assert len(admissions) == 2


def test_second_consecutive_staleness_propagates_fail_closed() -> None:
    service = _replan_service()
    coordinator = service._provider_ingestion
    coordinator._semantic_policy_provider = None
    persist_operations: list[str] = []

    def always_stale(fence, terminal, *, authorization_guard):
        persist_operations.append(fence.operation_id)
        raise SemanticEventReplayError(
            "event compilation state does not match repository graph revision"
        )

    coordinator._persist_semantic_terminal = always_stale
    try:
        service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id=_OPERATION_ID,
            task_id="task:one",
            user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )
    except SemanticEventReplayError:
        pass
    else:
        raise AssertionError("second staleness must propagate fail-closed")
    assert len(persist_operations) == 2
